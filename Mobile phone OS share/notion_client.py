"""
Notion DB 조회/업로드 클라이언트.

기준월 + OS/Vendor 조합으로 기존 데이터를 조회해 중복 생성을 방지합니다.
DB 속성명이 달라지면 config.py의 NOTION_PROPERTIES를 수정하세요.
"""

from __future__ import annotations

from datetime import datetime
import mimetypes
from typing import Any

import requests

from config import NOTION_PROPERTIES, NOTION_WIDE_BROWSER_PROPERTIES, NOTION_WIDE_OS_PROPERTIES
from statcounter_client import StatCounterRecord


NOTION_API_VERSION = "2022-06-28"
NOTION_FILE_API_VERSION = "2026-03-11"


class NotionUploadError(RuntimeError):
    pass


class NotionClient:
    def __init__(self, token: str, database_id: str, timeout: int = 30) -> None:
        self.database_id = database_id
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json",
            }
        )
        self.database_properties = self._retrieve_database_properties()

    def supports_wide_os_schema(self) -> bool:
        """현재 DB가 `조사 일자`, `AOS`, `iOS`, `etc`, `구분` 구조인지 확인합니다."""
        return all(prop["name"] in self.database_properties for prop in NOTION_WIDE_OS_PROPERTIES.values())

    # ------------------------------------------------------------------
    # 브라우저 점유율 DB (wide-format)
    # ------------------------------------------------------------------

    def supports_wide_browser_schema(self) -> bool:
        """현재 DB가 브라우저 점유율 wide-format 구조인지 확인합니다."""
        return all(prop["name"] in self.database_properties for prop in NOTION_WIDE_BROWSER_PROPERTIES.values())

    def find_wide_browser_page(self, basis_month: str) -> dict[str, Any] | None:
        """브라우저 wide-format DB에서 특정 기준월의 page를 찾습니다."""
        expected_title = self._format_wide_title(basis_month)
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload: dict[str, Any] = {"page_size": 100}

        while True:
            data = self._post(url, payload)
            for page in data.get("results", []):
                properties = page.get("properties", {})
                title = self._read_plain_text(
                    properties.get(NOTION_WIDE_BROWSER_PROPERTIES["title"]["name"], {})
                )
                survey_date = self._read_basis_month(
                    properties.get(NOTION_WIDE_BROWSER_PROPERTIES["basis_month"]["name"], {})
                )
                if title == expected_title:
                    return page
                if survey_date == basis_month:
                    return page

            if not data.get("has_more"):
                break
            payload["start_cursor"] = data.get("next_cursor")

        return None

    def upsert_wide_browser_summary(
        self,
        records: list[StatCounterRecord],
        collected_at: datetime,
        chart_images: list[tuple[str, bytes]],
    ) -> str:
        """브라우저 wide-format DB에 최신 월 요약과 이미지 블록을 생성 또는 갱신합니다."""
        if not records:
            raise ValueError("업로드할 브라우저 레코드가 없습니다.")

        basis_month = records[0].basis_month
        page = self.find_wide_browser_page(basis_month)
        properties = self._build_wide_browser_properties(records, collected_at)

        if page:
            page_id = page["id"]
            self._patch(f"https://api.notion.com/v1/pages/{page_id}", {"properties": properties})
            self._replace_page_children(page_id, self._build_wide_browser_blocks(chart_images))
            return "updated"

        payload = {"parent": {"database_id": self.database_id}, "properties": properties}
        created = self._post("https://api.notion.com/v1/pages", payload)
        self._replace_page_children(created["id"], self._build_wide_browser_blocks(chart_images))
        return "created"

    def find_wide_os_page(self, basis_month: str) -> dict[str, Any] | None:
        """
        wide-format OS DB에서 특정 기준월의 page를 찾습니다.
        과거 잘못 업로드된 제목/날짜 포맷도 함께 흡수해 중복 생성을 막습니다.
        """
        expected_title = self._format_wide_title(basis_month)
        legacy_title = f"Mobile OS Share {basis_month}"
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        payload: dict[str, Any] = {"page_size": 100}

        while True:
            data = self._post(url, payload)
            for page in data.get("results", []):
                properties = page.get("properties", {})
                title = self._read_plain_text(properties.get(NOTION_WIDE_OS_PROPERTIES["title"]["name"], {}))
                survey_date = self._read_basis_month(properties.get(NOTION_WIDE_OS_PROPERTIES["basis_month"]["name"], {}))

                if title in {expected_title, legacy_title}:
                    return page
                if title.endswith(f"{basis_month[5:7]}월 ({basis_month[:4]})"):
                    return page
                if survey_date == basis_month and title == legacy_title:
                    return page

            if not data.get("has_more"):
                break
            payload["start_cursor"] = data.get("next_cursor")

        return None

    def upsert_wide_os_summary(
        self,
        records: list[StatCounterRecord],
        collected_at: datetime,
        chart_images: list[tuple[str, bytes]],
        browser_records: list[StatCounterRecord] | None = None,
        browser_chart_images: list[tuple[str, bytes]] | None = None,
    ) -> str:
        """wide-format OS DB에 최신 월 요약과 이미지 블록을 생성 또는 갱신합니다.

        browser_records / browser_chart_images 가 주어지면
        같은 페이지 하단에 브라우저 점유율 섹션을 함께 업로드합니다.
        """
        if not records:
            raise ValueError("업로드할 StatCounter 레코드가 없습니다.")

        basis_month = records[0].basis_month
        page = self.find_wide_os_page(basis_month)
        properties = self._build_wide_os_properties(records, collected_at)

        blocks = self._build_wide_os_blocks(
            chart_images,
            browser_records=browser_records,
            browser_chart_images=browser_chart_images,
        )

        if page:
            page_id = page["id"]
            self._patch(f"https://api.notion.com/v1/pages/{page_id}", {"properties": properties})
            self._replace_page_children(page_id, blocks)
            return "updated"

        payload = {"parent": {"database_id": self.database_id}, "properties": properties}
        created = self._post("https://api.notion.com/v1/pages", payload)
        self._replace_page_children(created["id"], blocks)
        return "created"

    def existing_keys(self, basis_month: str) -> set[tuple[str, str]]:
        """특정 기준월의 기존 (기준월, Vendor) 키를 조회합니다."""
        basis_prop = self._prop("basis_month")
        vendor_prop = self._prop("vendor")

        payload: dict[str, Any] = {
            "page_size": 100,
            "filter": self._build_basis_month_filter(basis_prop, basis_month),
        }

        keys: set[tuple[str, str]] = set()
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"

        while True:
            data = self._post(url, payload)
            for page in data.get("results", []):
                properties = page.get("properties", {})
                vendor = self._read_plain_text(properties.get(vendor_prop["name"], {}))
                month = self._read_basis_month(properties.get(basis_prop["name"], {}))
                if month and vendor:
                    keys.add((month, vendor))

            if not data.get("has_more"):
                break
            payload["start_cursor"] = data.get("next_cursor")

        return keys

    def create_record(self, record: StatCounterRecord, collected_at: datetime) -> None:
        """Notion DB에 단일 레코드를 page로 생성합니다."""
        properties = self._build_page_properties(record, collected_at)
        payload = {"parent": {"database_id": self.database_id}, "properties": properties}
        self._post("https://api.notion.com/v1/pages", payload)

    def _retrieve_database_properties(self) -> dict[str, Any]:
        url = f"https://api.notion.com/v1/databases/{self.database_id}"
        data = self._get_database_or_resolve_page(url)
        return data.get("properties", {})

    def _get_database_or_resolve_page(self, url: str) -> dict[str, Any]:
        """
        .env의 NOTION_DATABASE_ID는 원칙적으로 database ID여야 합니다.
        다만 Notion copy link가 database 자체가 아니라 상위 page ID를 주는 경우가 있어,
        HTTP 400 page-not-database 응답이면 해당 page 안의 child_database를 1회 탐색합니다.
        """
        response = self.session.get(url, timeout=self.timeout)
        if response.ok:
            return response.json()

        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text}

        message = str(body.get("message", ""))
        if response.status_code == 400 and "is a page, not a database" in message:
            resolved_database_id = self._resolve_child_database_id(self.database_id)
            print(
                "[INFO] NOTION_DATABASE_ID가 page ID로 감지되어 "
                f"하위 database ID로 전환합니다: {resolved_database_id}"
            )
            self.database_id = resolved_database_id
            data = self._get(f"https://api.notion.com/v1/databases/{self.database_id}")
            return data

        raise NotionUploadError(
            f"Notion API 실패: HTTP {response.status_code} - {body.get('message', body)}"
        )

    def _resolve_child_database_id(self, page_id: str) -> str:
        """상위 page 아래에 있는 child_database block을 찾아 database ID를 반환합니다."""
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        payload: dict[str, Any] = {"page_size": 100}
        database_ids: list[str] = []

        while True:
            data = self._get_with_params(url, payload)
            for block in data.get("results", []):
                if block.get("type") == "child_database":
                    database_ids.append(block["id"])

            if not data.get("has_more"):
                break
            payload["start_cursor"] = data.get("next_cursor")

        if not database_ids:
            raise ValueError(
                "입력한 ID는 page ID이고, 해당 page 아래에서 child database를 찾지 못했습니다. "
                "Notion에서 실제 database의 copy link 또는 database ID를 확인해 .env에 입력하세요."
            )
        if len(database_ids) > 1:
            raise ValueError(
                "입력한 page 아래에 database가 여러 개 있습니다. "
                f"실제 대상 database ID를 .env에 직접 입력하세요: {', '.join(database_ids)}"
            )

        return database_ids[0]

    def _prop(self, key: str) -> dict[str, Any]:
        prop = NOTION_PROPERTIES[key]
        if not prop.get("enabled", True):
            raise ValueError(f"필수 Notion 속성 '{key}'가 disabled 상태입니다.")
        if prop["name"] not in self.database_properties:
            raise ValueError(
                f"Notion DB에 '{prop['name']}' 속성이 없습니다. "
                f"config.py의 NOTION_PROPERTIES 매핑을 실제 DB 속성명에 맞게 수정하세요."
            )
        return prop

    def _enabled_prop(self, key: str) -> dict[str, Any] | None:
        prop = NOTION_PROPERTIES.get(key)
        if not prop or not prop.get("enabled", True):
            return None
        if prop["name"] not in self.database_properties:
            print(f"[WARN] Notion DB에 '{prop['name']}' 속성이 없어 업로드에서 제외합니다.")
            return None
        return prop

    def _build_basis_month_filter(self, prop: dict[str, Any], basis_month: str) -> dict[str, Any]:
        """기준월 속성 타입에 맞춰 Notion query filter를 생성합니다."""
        prop_type = prop["type"]
        prop_name = prop["name"]

        if prop_type == "date":
            return {"property": prop_name, "date": {"equals": f"{basis_month}-01"}}
        if prop_type == "rich_text":
            return {"property": prop_name, "rich_text": {"equals": basis_month}}
        if prop_type == "title":
            return {"property": prop_name, "title": {"equals": basis_month}}
        if prop_type == "select":
            return {"property": prop_name, "select": {"equals": basis_month}}

        raise ValueError(f"기준월 중복 조회에 지원하지 않는 Notion 타입입니다: {prop_type}")

    def _build_page_properties(self, record: StatCounterRecord, collected_at: datetime) -> dict[str, Any]:
        values = {
            "basis_month": f"{record.basis_month}-01",
            "vendor": record.vendor,
            "share": record.share,
            "country": record.country,
            "source": record.source,
            "collected_at": collected_at.isoformat(timespec="seconds"),
            "source_url": record.source_url,
        }

        page_props: dict[str, Any] = {}
        for key, value in values.items():
            prop = self._enabled_prop(key)
            if not prop:
                continue
            page_props[prop["name"]] = self._to_notion_property(prop["type"], value)

        return page_props

    def _build_wide_os_properties(
        self,
        records: list[StatCounterRecord],
        collected_at: datetime,
    ) -> dict[str, Any]:
        basis_month = records[0].basis_month
        shares = {record.vendor.strip().lower(): record.share for record in records}

        # Notion percent 포맷은 0.6714 -> 67.14%로 보이므로 100으로 나눈 값을 저장합니다.
        aos_ratio = shares.get("android", 0.0) / 100
        ios_ratio = shares.get("ios", 0.0) / 100
        etc_ratio = sum(
            record.share for record in records if record.vendor.strip().lower() not in {"android", "ios"}
        ) / 100

        values = {
            "title": self._format_wide_title(basis_month),
            "basis_month": collected_at.date().isoformat(),
            "aos": round(aos_ratio, 4),
            "ios": round(ios_ratio, 4),
            "etc": round(etc_ratio, 4),
        }

        properties: dict[str, Any] = {}
        for key, value in values.items():
            prop = NOTION_WIDE_OS_PROPERTIES[key]
            properties[prop["name"]] = self._to_notion_property(prop["type"], value)

        return properties

    def _build_wide_os_blocks(
        self,
        chart_images: list[tuple[str, bytes]],
        browser_records: list[StatCounterRecord] | None = None,
        browser_chart_images: list[tuple[str, bytes]] | None = None,
    ) -> list[dict[str, Any]]:
        if len(chart_images) != 3:
            raise ValueError("차트 이미지 3개(OS, Android, iOS)가 필요합니다.")

        os_upload_id = self._upload_file_bytes(*chart_images[0])
        android_upload_id = self._upload_file_bytes(*chart_images[1])
        ios_upload_id = self._upload_file_bytes(*chart_images[2])

        blocks: list[dict[str, Any]] = [
            self._paragraph_block("Operating System Market", bold=True),
            self._image_block(os_upload_id),
            self._paragraph_block(""),
            {"object": "block", "type": "divider", "divider": {}},
            self._paragraph_block("[AOS] Mobile Android Version Market", bold=True),
            self._image_block(android_upload_id),
            {"object": "block", "type": "divider", "divider": {}},
            self._paragraph_block("[iOS] Mobile iOS Version Market", bold=True),
            self._image_block(ios_upload_id),
            self._paragraph_block(""),
        ]

        # 브라우저 데이터가 있으면 같은 페이지 하단에 이어서 추가합니다.
        if browser_chart_images:
            if len(browser_chart_images) != 1:
                raise ValueError("브라우저 차트 이미지는 1개여야 합니다.")
            browser_upload_id = self._upload_file_bytes(*browser_chart_images[0])
            blocks += [
                {"object": "block", "type": "divider", "divider": {}},
                self._paragraph_block("Mobile Browser Market Share", bold=True),
                self._image_block(browser_upload_id),
                self._paragraph_block(""),
            ]

        return blocks

    def _build_wide_browser_properties(
        self,
        records: list[StatCounterRecord],
        collected_at: datetime,
    ) -> dict[str, Any]:
        basis_month = records[0].basis_month
        shares = {record.vendor.strip().lower(): record.share for record in records}

        # 주요 브라우저 3종 외 나머지를 etc로 합산합니다.
        known = {"chrome", "samsung internet", "safari"}
        chrome_ratio = shares.get("chrome", 0.0) / 100
        samsung_ratio = shares.get("samsung internet", 0.0) / 100
        safari_ratio = shares.get("safari", 0.0) / 100
        etc_ratio = sum(
            record.share for record in records if record.vendor.strip().lower() not in known
        ) / 100

        values = {
            "title": self._format_wide_title(basis_month),
            "basis_month": collected_at.date().isoformat(),
            "chrome": round(chrome_ratio, 4),
            "samsung_internet": round(samsung_ratio, 4),
            "safari": round(safari_ratio, 4),
            "etc": round(etc_ratio, 4),
        }

        properties: dict[str, Any] = {}
        for key, value in values.items():
            prop = NOTION_WIDE_BROWSER_PROPERTIES[key]
            properties[prop["name"]] = self._to_notion_property(prop["type"], value)

        return properties

    def _build_wide_browser_blocks(self, chart_images: list[tuple[str, bytes]]) -> list[dict[str, Any]]:
        if len(chart_images) != 1:
            raise ValueError("브라우저 차트 이미지 1개가 필요합니다.")

        browser_upload_id = self._upload_file_bytes(*chart_images[0])

        return [
            self._paragraph_block("Browser Market Share (Mobile)", bold=True),
            self._image_block(browser_upload_id),
            self._paragraph_block(""),
        ]

    def _replace_page_children(self, page_id: str, blocks: list[dict[str, Any]]) -> None:
        existing_blocks = self._list_block_children(page_id)
        for block in existing_blocks:
            self._delete_block(block["id"])
        self._append_block_children(page_id, blocks)

    def _list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        url = f"https://api.notion.com/v1/blocks/{block_id}/children"
        payload: dict[str, Any] = {"page_size": 100}
        blocks: list[dict[str, Any]] = []

        while True:
            data = self._get_with_params(url, payload)
            blocks.extend(data.get("results", []))
            if not data.get("has_more"):
                break
            payload["start_cursor"] = data.get("next_cursor")

        return blocks

    def _append_block_children(self, page_id: str, blocks: list[dict[str, Any]]) -> None:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        for index in range(0, len(blocks), 100):
            self._patch(url, {"children": blocks[index : index + 100]}, notion_version=NOTION_FILE_API_VERSION)

    def _delete_block(self, block_id: str) -> None:
        url = f"https://api.notion.com/v1/blocks/{block_id}"
        response = self.session.delete(url, timeout=self.timeout)
        self._handle_response(response)

    def _format_wide_title(self, basis_month: str) -> str:
        return f"대한민국 - {basis_month[5:7]}월 ({basis_month[:4]})"

    def _paragraph_block(self, text: str, bold: bool = False) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": text},
                        "annotations": {
                            "bold": bold,
                            "italic": False,
                            "strikethrough": False,
                            "underline": False,
                            "code": False,
                            "color": "default",
                        },
                    }
                ]
                if text
                else []
            },
        }

    def _image_block(self, file_upload_id: str) -> dict[str, Any]:
        return {
            "object": "block",
            "type": "image",
            "image": {"type": "file_upload", "file_upload": {"id": file_upload_id}, "caption": []},
        }

    def _upload_file_bytes(self, filename: str, content: bytes) -> str:
        """PNG 바이트를 Notion File Upload로 업로드한 뒤 upload id를 반환합니다."""
        content_type = mimetypes.guess_type(filename)[0] or "image/png"
        create_payload = {
            "mode": "single_part",
            "filename": filename,
            "content_type": content_type,
        }
        created = self._post(
            "https://api.notion.com/v1/file_uploads",
            create_payload,
            notion_version=NOTION_FILE_API_VERSION,
        )
        upload_id = created["id"]

        headers = {
            "Authorization": self.session.headers["Authorization"],
            "Notion-Version": NOTION_FILE_API_VERSION,
        }
        files = {"file": (filename, content, content_type)}
        send_response = requests.post(
            f"https://api.notion.com/v1/file_uploads/{upload_id}/send",
            headers=headers,
            files=files,
            timeout=self.timeout,
        )
        data = self._handle_response(send_response)
        status = data.get("status")
        if status != "uploaded":
            raise NotionUploadError(f"파일 업로드 상태가 uploaded가 아닙니다: {status}")

        return upload_id

    def _to_notion_property(self, prop_type: str, value: Any) -> dict[str, Any]:
        if prop_type == "title":
            return {"title": [{"text": {"content": str(value)}}]}
        if prop_type == "rich_text":
            return {"rich_text": [{"text": {"content": str(value)}}]}
        if prop_type == "number":
            return {"number": float(value)}
        if prop_type == "date":
            return {"date": {"start": str(value)}}
        if prop_type == "select":
            return {"select": {"name": str(value)}}
        if prop_type == "url":
            return {"url": str(value)}
        raise ValueError(f"지원하지 않는 Notion 속성 타입입니다: {prop_type}")

    def _read_plain_text(self, property_value: dict[str, Any]) -> str:
        prop_type = property_value.get("type")
        if prop_type in {"title", "rich_text"}:
            return "".join(item.get("plain_text", "") for item in property_value.get(prop_type, [])).strip()
        if prop_type == "select":
            selected = property_value.get("select")
            return selected.get("name", "").strip() if selected else ""
        return ""

    def _read_basis_month(self, property_value: dict[str, Any]) -> str:
        prop_type = property_value.get("type")
        if prop_type == "date":
            start = (property_value.get("date") or {}).get("start", "")
            return start[:7]
        return self._read_plain_text(property_value)

    def _get(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, timeout=self.timeout)
        return self._handle_response(response)

    def _get_with_params(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self.session.get(url, params=params, timeout=self.timeout)
        return self._handle_response(response)

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        notion_version: str | None = None,
    ) -> dict[str, Any]:
        headers = None
        if notion_version:
            headers = {
                "Authorization": self.session.headers["Authorization"],
                "Notion-Version": notion_version,
                "Content-Type": "application/json",
            }
        response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        return self._handle_response(response)

    def _patch(
        self,
        url: str,
        payload: dict[str, Any],
        notion_version: str | None = None,
    ) -> dict[str, Any]:
        headers = None
        if notion_version:
            headers = {
                "Authorization": self.session.headers["Authorization"],
                "Notion-Version": notion_version,
                "Content-Type": "application/json",
            }
        response = self.session.patch(url, json=payload, headers=headers, timeout=self.timeout)
        return self._handle_response(response)

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        if response.ok:
            return response.json()

        try:
            body = response.json()
        except ValueError:
            body = {"message": response.text}

        raise NotionUploadError(
            f"Notion API 실패: HTTP {response.status_code} - {body.get('message', body)}"
        )
