from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from app.config import NOTION_DB_ID, NOTION_TOKEN, NOTION_VERSION


class NotionClient:
    def __init__(self) -> None:
        if not NOTION_TOKEN or not NOTION_DB_ID:
            raise RuntimeError("NOTION_TOKEN and NOTION_DB_ID are required")

        self.database_id = NOTION_DB_ID
        self.headers = {
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def query_database(self, page_size: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        payload: dict[str, Any] = {
            "page_size": min(page_size, 100),
            "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
        }

        while True:
            response = requests.post(
                f"https://api.notion.com/v1/databases/{self.database_id}/query",
                headers=self.headers,
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            results.extend(data.get("results", []))

            if not data.get("has_more") or len(results) >= page_size:
                return results[:page_size]
            payload["start_cursor"] = data.get("next_cursor")


def plain_text(prop: dict[str, Any] | None) -> str:
    if not prop:
        return ""

    prop_type = prop.get("type")
    if prop_type in ("title", "rich_text"):
        return "".join(item.get("plain_text", "") for item in prop.get(prop_type, []))
    if prop_type in ("select", "status"):
        return (prop.get(prop_type) or {}).get("name", "")
    if prop_type == "number":
        value = prop.get("number")
        return "" if value is None else str(value)
    if prop_type == "date":
        return (prop.get("date") or {}).get("start", "")
    if prop_type == "formula":
        return formula_value(prop)
    if prop_type == "url":
        return prop.get("url") or ""
    return ""


def number_value(prop: dict[str, Any] | None) -> int:
    if not prop:
        return 0
    if prop.get("type") == "number":
        return int(prop.get("number") or 0)
    if prop.get("type") == "formula":
        formula = prop.get("formula") or {}
        if formula.get("type") == "number":
            return int(formula.get("number") or 0)
    try:
        return int(float(plain_text(prop) or 0))
    except ValueError:
        return 0


def formula_value(prop: dict[str, Any]) -> str:
    formula = prop.get("formula") or {}
    formula_type = formula.get("type")
    if formula_type == "string":
        return formula.get("string") or ""
    if formula_type == "number":
        value = formula.get("number")
        return "" if value is None else str(value)
    if formula_type == "boolean":
        return "true" if formula.get("boolean") else "false"
    if formula_type == "date":
        return (formula.get("date") or {}).get("start", "")
    return ""


def first_prop(properties: dict[str, Any], names: list[str]) -> dict[str, Any] | None:
    for name in names:
        if name in properties:
            return properties[name]
    return None


def parse_page(page: dict[str, Any]) -> dict[str, Any]:
    properties = page.get("properties", {})
    title = plain_text(first_prop(properties, ["제목", "Name", "Title", "리포트명"])) or page.get("id", "")
    status = plain_text(first_prop(properties, ["상태", "Status"]))
    test_result = plain_text(first_prop(properties, ["테스트 결과", "Test Result", "결과"]))
    version = plain_text(first_prop(properties, ["버전", "Version"]))
    platform = plain_text(first_prop(properties, ["플랫폼", "Platform"]))
    result_text = plain_text(first_prop(properties, ["결과", "Result", "실행 로그", "Raw Log", "Raw"]))
    created = plain_text(first_prop(properties, ["등록일", "Created", "Date"])) or page.get("created_time")

    pass_count = number_value(first_prop(properties, ["PASS", "Pass"]))
    fail_count = number_value(first_prop(properties, ["FAIL", "Fail"]))
    na_count = number_value(first_prop(properties, ["N/A", "N/ A", "NA"]))
    total_count = number_value(first_prop(properties, ["Total", "전체", "총 TC"]))

    if total_count == 0:
        total_count = pass_count + fail_count + na_count

    snapshots = extract_files(properties)
    failed_items = extract_failed_items(result_text)
    normalized_status = normalize_status(status or test_result, fail_count)

    return {
        "id": page.get("id"),
        "url": page.get("url"),
        "title": title,
        "version": version or "unversioned",
        "platform": platform or "WEB",
        "status": normalized_status,
        "statusText": status or test_result or normalized_status,
        "pass": pass_count,
        "fail": fail_count,
        "na": na_count,
        "total": total_count,
        "resultText": result_text,
        "failedItems": failed_items,
        "snapshots": snapshots,
        "createdAt": created,
        "lastEditedAt": page.get("last_edited_time"),
    }


def extract_files(properties: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for prop in properties.values():
        if prop.get("type") != "files":
            continue
        for item in prop.get("files", []):
            file_type = item.get("type")
            if file_type == "external":
                url = (item.get("external") or {}).get("url")
            else:
                url = (item.get("file") or {}).get("url")
            if url:
                urls.append(url)
    return urls


def extract_failed_items(result_text: str) -> list[dict[str, str]]:
    failed: list[dict[str, str]] = []
    scenario = "테스트 결과"
    for line in result_text.splitlines():
        text = line.strip()
        if text.startswith("[") and text.endswith("]"):
            scenario = text.strip("[]")
            continue
        if not text.startswith("- "):
            continue
        body = text[2:]
        name, _, status = body.partition(":")
        if status.strip().upper().startswith("FAIL"):
            failed.append({"scenario": scenario, "name": name.strip(), "status": status.strip()})
    return failed


def normalize_status(status_text: str, fail_count: int) -> str:
    text = status_text.lower()
    if fail_count > 0 or any(token in text for token in ["실패", "fail", "error", "blocked"]):
        return "failed"
    if any(token in text for token in ["running", "진행", "실행중"]):
        return "running"
    if any(token in text for token in ["성공", "완료", "success", "done", "complete"]):
        return "passed"
    return "unknown"


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()
