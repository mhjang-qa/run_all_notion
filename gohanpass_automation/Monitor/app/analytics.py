from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any


def build_monitor_payload(runs: list[dict[str, Any]], source: str, error: str | None = None) -> dict[str, Any]:
    sorted_runs = sorted(runs, key=lambda item: item.get("createdAt") or item.get("lastEditedAt") or "", reverse=True)
    latest = sorted_runs[0] if sorted_runs else None
    totals = {
        "runs": len(sorted_runs),
        "pass": sum(item.get("pass", 0) for item in sorted_runs),
        "fail": sum(item.get("fail", 0) for item in sorted_runs),
        "na": sum(item.get("na", 0) for item in sorted_runs),
        "total": sum(item.get("total", 0) for item in sorted_runs),
    }
    totals["passRate"] = round((totals["pass"] / totals["total"]) * 100, 1) if totals["total"] else 0
    totals["failRate"] = round((totals["fail"] / totals["total"]) * 100, 1) if totals["total"] else 0

    failed_runs = [item for item in sorted_runs if item.get("status") == "failed" or item.get("fail", 0) > 0]
    active = latest if latest and latest.get("status") == "running" else None

    return {
        "source": source,
        "error": error,
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kpi": {
            **totals,
            "failedRuns": len(failed_runs),
            "latestStatus": latest.get("status") if latest else "unknown",
            "latestVersion": latest.get("version") if latest else "-",
        },
        "current": current_status(active, latest),
        "recentFailures": recent_failures(failed_runs),
        "repeatFailures": repeat_failures(sorted_runs),
        "latestSnapshot": latest_snapshot(sorted_runs),
        "versions": version_status(sorted_runs),
        "runs": sorted_runs,
        "notionGuide": notion_guide(),
    }


def current_status(active: dict[str, Any] | None, latest: dict[str, Any] | None) -> dict[str, Any]:
    target = active or latest
    if not target:
        return {"mode": "idle", "title": "데이터 없음", "message": "go.hanpass 자동화 Raw data 조회 대기"}
    if active:
        return {
            "mode": "running",
            "title": active.get("title"),
            "message": "go.hanpass 자동화 실행이 진행중입니다.",
            "version": active.get("version"),
            "startedAt": active.get("createdAt"),
        }
    return {
        "mode": "idle" if target.get("status") == "passed" else "attention",
        "title": target.get("title"),
        "message": "가장 최근 go.hanpass 자동화 실행 결과입니다.",
        "version": target.get("version"),
        "startedAt": target.get("createdAt"),
    }


def recent_failures(failed_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for run in failed_runs[:8]:
        failed_items = run.get("failedItems") or [{"scenario": "Run", "name": "FAIL 집계", "status": f"FAIL {run.get('fail', 0)}"}]
        for failed in failed_items[:3]:
            items.append(
                {
                    "title": run.get("title"),
                    "version": run.get("version"),
                    "createdAt": run.get("createdAt"),
                    "scenario": failed.get("scenario"),
                    "name": failed.get("name"),
                    "status": failed.get("status"),
                    "url": run.get("url"),
                }
            )
    return items[:10]


def repeat_failures(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    latest_seen: dict[str, str] = {}
    scenario_map: dict[str, str] = {}

    for run in runs:
        for item in run.get("failedItems", []):
            key = f"{item.get('scenario')}::{item.get('name')}"
            counter[key] += 1
            latest_seen.setdefault(key, run.get("createdAt") or "")
            scenario_map[key] = item.get("scenario") or ""

    result = []
    for key, count in counter.most_common(8):
        scenario, _, name = key.partition("::")
        result.append({"scenario": scenario_map.get(key) or scenario, "name": name, "count": count, "latestAt": latest_seen.get(key)})
    return result


def latest_snapshot(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for run in runs:
        snapshots = run.get("snapshots") or []
        if snapshots:
            return {"url": snapshots[0], "title": run.get("title"), "version": run.get("version"), "createdAt": run.get("createdAt")}
    return None


def version_status(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        grouped[run.get("version") or "unversioned"].append(run)

    versions = []
    for version, items in grouped.items():
        total = sum(item.get("total", 0) for item in items)
        passed = sum(item.get("pass", 0) for item in items)
        failed = sum(item.get("fail", 0) for item in items)
        versions.append(
            {
                "version": version,
                "runs": len(items),
                "passRate": round((passed / total) * 100, 1) if total else 0,
                "failed": failed,
                "status": "failed" if failed else "passed",
                "latestAt": max(item.get("createdAt") or "" for item in items),
            }
        )
    return sorted(versions, key=lambda item: item["latestAt"], reverse=True)


def notion_guide() -> dict[str, Any]:
    return {
        "columns": [
            ["제목", "title", "go.hanpass 자동리포트_YYYYMMDD_HHMM"],
            ["버전", "rich_text 또는 select", "릴리즈/빌드 버전"],
            ["플랫폼", "select", "WEB_CHROME_SERVER"],
            ["PASS", "number", "통과 TC 수"],
            ["FAIL", "number", "실패 TC 수"],
            ["N/A", "number", "제외/미실행 TC 수"],
            ["Total", "number", "전체 TC 수"],
            ["상태", "status 또는 select", "성공/실패/실행중"],
            ["테스트 결과", "select", "테스트 성공/테스트 실패"],
            ["결과", "rich_text", "Raw 실행 로그"],
            ["등록일", "date", "실행 시각"],
            ["스냅샷", "files", "실패/최신 화면 이미지"],
            ["실패율", "formula", "FAIL / Total"],
            ["관제상태", "formula", "정상/주의/장애"],
        ],
        "formulas": [
            ["실패율", "if(prop(\"Total\") == 0, 0, round(prop(\"FAIL\") / prop(\"Total\") * 1000) / 10)"],
            ["관제상태", "if(prop(\"FAIL\") > 0, \"장애\", if(prop(\"Total\") == 0, \"대기\", \"정상\"))"],
            ["통과율", "if(prop(\"Total\") == 0, 0, round(prop(\"PASS\") / prop(\"Total\") * 1000) / 10)"],
            ["반복실패키", "concat(prop(\"버전\"), \" / \", prop(\"플랫폼\"), \" / \", prop(\"상태\"))"],
        ],
        "automation": [
            "go.hanpass 자동화 실행 완료 시 PASS/FAIL/N/A/Total과 Raw 로그를 Notion DB에 upsert",
            "FAIL > 0이면 상태=실패, 테스트 결과=테스트 실패",
            "FAIL = 0이고 Total > 0이면 상태=성공, 테스트 결과=테스트 성공",
            "실패 스냅샷은 files 컬럼 또는 상세 페이지 image block에 첨부",
        ],
    }
