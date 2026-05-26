#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DATABASE_ID = "21473fbd1951800d8321fc2e34c2548e"
NOTION_VERSION = "2022-06-28"
OUT_FILE = "qa_heatmap_embed.html"
REPO_URL = "https://github.com/mhjang-qa/qa_hitmap.git"
PUBLISH_DIR = Path(".publish/qa_hitmap")
PUBLISH_BRANCH = "main"
SCRIPT_DIR = Path(__file__).resolve().parent


def load_env_file():
    env_file = SCRIPT_DIR / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def notion_request(path, payload=None):
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise RuntimeError("NOTION_TOKEN environment variable is required.")

    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"

    request = urllib.request.Request(
        f"https://api.notion.com/v1{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Notion API error {exc.code}: {body}") from exc


def prop_name(page, name):
    prop = page["properties"].get(name, {})
    value_type = prop.get("type")
    value = prop.get(value_type) if value_type else None

    if value_type in ("select", "status"):
        return value["name"] if value else ""
    if value_type == "title":
        return "".join(part.get("plain_text", "") for part in value)
    if value_type == "unique_id":
        prefix = value.get("prefix") or ""
        number = value.get("number")
        return f"{prefix}-{number}" if prefix and number is not None else str(number or "")
    if value_type in ("created_time", "last_edited_time"):
        return value or ""
    if value_type == "date":
        return value.get("start", "") if value else ""
    return ""


def classify_domain(target_version):
    value = (target_version or "").strip()
    compact = re.sub(r"\s+", "", value).upper()

    if re.match(r"^\[G\.?H\]V?\d+\.\d+\.\d+$", compact):
        return "방한 고한패스"
    if compact in {"GO.HANPASS", "GOHANPASS"}:
        return "방한 고한패스"
    if re.match(r"^\d+\.\d+\.\d+$", compact):
        return "한패스"
    return "미분류"


def version_tuple(target_version):
    compact = re.sub(r"\s+", "", target_version or "")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", compact)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def is_tracked_version(target_version):
    domain = classify_domain(target_version)
    if domain == "방한 고한패스":
        return True
    if domain != "한패스":
        return False

    version = version_tuple(target_version)
    return version is not None and version >= (5, 18, 0)


def extract_area(title, defect_type):
    match = re.match(r"^\s*\[([^\]]+)\]", title or "")
    if match:
        return match.group(1).strip()
    return defect_type or "미분류"


def is_done_status(status):
    value = status or ""
    return (
        "완료" in value
        or "Done" in value
        or "QA 검증" in value
        or "회귀" in value
        or "결함 아님" in value
        or "Not an issue" in value
    )


def is_future_fix_status(status):
    return "추후 수정 백로그 이관" in (status or "")


def fetch_pages():
    pages = []
    payload = {"page_size": 100}

    while True:
        response = notion_request(f"/databases/{DATABASE_ID}/query", payload)
        pages.extend(response.get("results", []))
        if not response.get("has_more"):
            return pages
        payload["start_cursor"] = response.get("next_cursor")


def normalize_pages(pages):
    rows = []
    for page in pages:
        title = prop_name(page, "결함 요약")
        target_version = prop_name(page, "목표버전")
        severity = prop_name(page, "심각도") or "미지정"
        status = prop_name(page, "상태") or "미지정"
        priority = prop_name(page, "우선순위") or "미지정"
        defect_type = prop_name(page, "결함 유형") or "미지정"
        issue_id = prop_name(page, "ID")
        created_at = prop_name(page, "생성 일시")

        if not is_tracked_version(target_version):
            continue

        rows.append(
            {
                "id": issue_id,
                "title": title,
                "area": extract_area(title, defect_type),
                "defectType": defect_type,
                "targetVersion": target_version or "미지정",
                "domain": classify_domain(target_version),
                "severity": severity,
                "status": status,
                "priority": priority,
                "createdAt": created_at,
                "url": page.get("url", ""),
            }
        )
    return rows


def make_summary(rows):
    total = len(rows)
    future_fix_rows = [row for row in rows if is_future_fix_status(row["status"])]
    open_rows = [
        row
        for row in rows
        if not is_done_status(row["status"]) and not is_future_fix_status(row["status"])
    ]
    major_plus = [row for row in rows if row["severity"] in {"Critical", "Major"}]
    critical = [row for row in rows if row["severity"] == "Critical"]
    domain_counts = Counter(row["domain"] for row in rows)
    return {
        "total": total,
        "open": len(open_rows),
        "futureFix": len(future_fix_rows),
        "majorPlus": len(major_plus),
        "critical": len(critical),
        "domains": dict(domain_counts),
    }


def build_html(rows):
    generated_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    data_json = json.dumps(
        {"generatedAt": generated_at, "rows": rows, "summary": make_summary(rows)},
        ensure_ascii=False,
        indent=2,
    )
    safe_json = data_json.replace("</script", "<\\/script")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>QA 결함 히트맵</title>
  <style>
    * {{ box-sizing: border-box; }}
    :root {{
      color-scheme: light dark;
      --text: #20242c;
      --muted: #78716c;
      --muted-2: #8f8881;
      --line: #e7e2dc;
      --tab-line: #cfd6e3;
      --surface-total: linear-gradient(135deg, rgba(239, 246, 255, .96), rgba(255, 255, 255, .74));
      --surface-open: linear-gradient(135deg, rgba(254, 242, 242, .96), rgba(255, 255, 255, .74));
      --surface-future: linear-gradient(135deg, rgba(255, 251, 235, .96), rgba(255, 255, 255, .74));
      --surface-risk-low: linear-gradient(135deg, rgba(240, 253, 244, .96), rgba(255, 255, 255, .74));
      --surface-risk-medium: linear-gradient(135deg, rgba(255, 251, 235, .96), rgba(255, 255, 255, .74));
      --surface-risk-high: linear-gradient(135deg, rgba(254, 242, 242, .96), rgba(255, 255, 255, .74));
      --surface-panel: linear-gradient(135deg, rgba(255, 255, 255, .8), rgba(248, 250, 252, .66));
      --tab-bg: #fff;
      --tab-active: linear-gradient(135deg, #1f2937, #111827);
      --tab-active-text: #fff;
      --panel-solid: #ffffff;
      --panel-head: #f8fafc;
      --row-solid: #ffffff;
      --row-hover: #f8fafc;
      --input-bg: #ffffff;
      --shadow-inset: inset 0 1px 0 rgba(255, 255, 255, .65);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --text: #f4f4f5;
        --muted: #b8afa6;
        --muted-2: #a8a29e;
        --line: rgba(255, 255, 255, .13);
        --tab-line: rgba(255, 255, 255, .16);
        --surface-total: linear-gradient(135deg, rgba(30, 64, 175, .58), rgba(24, 24, 27, .72));
        --surface-open: linear-gradient(135deg, rgba(153, 27, 27, .62), rgba(24, 24, 27, .72));
        --surface-future: linear-gradient(135deg, rgba(146, 64, 14, .62), rgba(24, 24, 27, .72));
        --surface-risk-low: linear-gradient(135deg, rgba(22, 101, 52, .58), rgba(24, 24, 27, .72));
        --surface-risk-medium: linear-gradient(135deg, rgba(146, 64, 14, .62), rgba(24, 24, 27, .72));
        --surface-risk-high: linear-gradient(135deg, rgba(153, 27, 27, .62), rgba(24, 24, 27, .72));
        --surface-panel: linear-gradient(135deg, rgba(39, 39, 42, .78), rgba(24, 24, 27, .68));
        --tab-bg: rgba(39, 39, 42, .86);
        --tab-active: linear-gradient(135deg, #e5e7eb, #a1a1aa);
        --tab-active-text: #18181b;
        --panel-solid: #18181b;
        --panel-head: #27272a;
        --row-solid: #202024;
        --row-hover: #2a2a30;
        --input-bg: #202024;
        --shadow-inset: inset 0 1px 0 rgba(255, 255, 255, .08);
      }}
    }}
    html {{
      width: 100%;
      min-height: 100%;
      overflow-x: hidden;
    }}
    body {{
      width: 100%;
      min-height: 100vh;
      overflow-x: hidden;
    }}
    body {{
      margin: 0;
      padding: max(10px, env(safe-area-inset-top)) max(10px, env(safe-area-inset-right)) max(10px, env(safe-area-inset-bottom)) max(10px, env(safe-area-inset-left));
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: transparent;
      color: var(--text);
      overflow: hidden;
      -webkit-text-size-adjust: 100%;
    }}
    img, svg, canvas {{ max-width: 100%; }}
    .dashboard {{
      width: 100%;
      max-width: 1600px;
      min-width: 0;
      height: calc(100vh - 20px);
      margin: 0 auto;
      background: transparent;
      border: 0;
      border-radius: 0;
      padding: 0;
      display: flex;
      flex-direction: column;
    }}
    .fixed-zone {{
      flex: 0 0 auto;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      margin-bottom: 8px;
    }}
    .title {{ font-size: 18px; font-weight: 800; }}
    .subtitle {{ margin-top: 4px; color: var(--muted); font-size: 12px; line-height: 1.35; }}
    .meta {{ text-align: right; font-size: 11px; color: var(--muted); white-space: nowrap; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 8px;
      margin-bottom: 8px;
    }}
    .growth {{
      display: grid;
      grid-template-columns: 190px 1fr;
      gap: 8px;
      align-items: stretch;
      margin-bottom: 8px;
      background: var(--surface-panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
    }}
    .growth-title {{
      color: var(--muted);
      font-size: 11px;
      line-height: 1.3;
    }}
    .growth-title strong {{
      display: block;
      margin-top: 4px;
      color: var(--text);
      font-size: 16px;
      line-height: 1.1;
    }}
    .funnel {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 5px;
    }}
    .funnel-step {{
      min-width: 0;
      border-radius: 7px;
      padding: 7px 8px;
      background: rgba(255, 255, 255, .48);
      border: 1px solid var(--line);
    }}
    .funnel-label {{
      color: var(--muted);
      font-size: 10px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .funnel-value {{
      margin-top: 4px;
      color: var(--text);
      font-size: 14px;
      font-weight: 800;
    }}
    .funnel-bar {{
      height: 5px;
      margin-top: 7px;
      overflow: hidden;
      border-radius: 99px;
      background: rgba(120, 113, 108, .16);
    }}
    .funnel-bar > span {{
      display: block;
      height: 100%;
      width: var(--w, 0%);
      border-radius: inherit;
      background: linear-gradient(90deg, #38bdf8, #2563eb);
    }}
    .funnel-step.delta .funnel-value {{ color: #dc2626; }}
    .funnel-step.delta .funnel-bar > span {{ background: linear-gradient(90deg, #fbbf24, #dc2626); }}
    .card {{
      background: var(--surface-panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      min-width: 0;
      position: relative;
      overflow: hidden;
      cursor: pointer;
      box-shadow: var(--shadow-inset);
    }}
    .card:hover {{ filter: brightness(.98); }}
    .card::before {{
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 5px;
      background: var(--accent, #94a3b8);
    }}
    .card.total {{ --accent: #2563eb; background: var(--surface-total); }}
    .card.open {{ --accent: #dc2626; background: var(--surface-open); }}
    .card.future {{ --accent: #d97706; background: var(--surface-future); }}
    .card.risk {{ --accent: #16a34a; background: var(--surface-risk-low); }}
    .card.risk.medium {{ --accent: #d97706; background: var(--surface-risk-medium); }}
    .card.risk.high {{ --accent: #dc2626; background: var(--surface-risk-high); }}
    .card-label {{ color: var(--muted); font-size: 11px; margin-bottom: 5px; padding-left: 2px; }}
    .card-value {{ color: var(--accent, var(--text)); font-size: 20px; font-weight: 800; line-height: 1.05; }}
    .card-note {{
      margin-top: 4px;
      color: var(--muted-2);
      font-size: 10px;
      line-height: 1.3;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .panel {{
      background: var(--surface-panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
      min-height: 0;
    }}
    .panel-title {{
      padding: 8px 10px;
      color: var(--text);
      font-size: 12px;
      font-weight: 700;
    }}
    .panel-title::before {{
      content: "";
      display: inline-block;
      width: 8px;
      height: 8px;
      margin-right: 7px;
      border-radius: 99px;
      background: linear-gradient(135deg, #2563eb, #dc2626);
      vertical-align: 1px;
    }}
    .panel-body {{
      border-top: 1px solid var(--line);
      padding: 8px;
      display: flex;
      flex-direction: column;
      min-height: 0;
      flex: 1 1 auto;
    }}
    .detail-fixed {{
      flex: 0 0 auto;
    }}
    .detail-scroll {{
      min-height: 0;
      flex: 1 1 auto;
      overflow-x: hidden;
      overflow-y: hidden;
      overscroll-behavior: contain;
      padding-right: 4px;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-direction: row;
      gap: 8px;
      margin-bottom: 8px;
    }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .tab {{
      border: 1px solid var(--tab-line);
      background: var(--tab-bg);
      color: var(--text);
      padding: 6px 9px;
      border-radius: 7px;
      font-size: 11px;
      cursor: pointer;
    }}
    .tab.active {{ background: var(--tab-active); color: var(--tab-active-text); border-color: transparent; }}
    .search-wrap {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin-left: auto;
      min-width: 260px;
    }}
    .issue-search {{
      width: 100%;
      min-width: 0;
      height: 30px;
      border: 1px solid var(--tab-line);
      border-radius: 7px;
      background: var(--input-bg);
      color: var(--text);
      padding: 0 10px;
      font: inherit;
      font-size: 12px;
      outline: none;
    }}
    .issue-search::placeholder {{ color: var(--muted-2); }}
    .issue-search:focus {{
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, .14);
    }}
    .search-clear {{
      flex: 0 0 auto;
      height: 30px;
      border: 1px solid var(--tab-line);
      border-radius: 7px;
      background: var(--tab-bg);
      color: var(--muted);
      padding: 0 9px;
      font-size: 11px;
      font-weight: 800;
      cursor: pointer;
    }}
    .legend {{ display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--muted); white-space: nowrap; }}
    .legend-box {{ width: 18px; height: 10px; border-radius: 3px; }}
    .detail-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 8px;
      align-items: stretch;
      min-height: 0;
      flex: 1 1 auto;
    }}
    .detail-scroll::-webkit-scrollbar {{
      width: 10px;
    }}
    .detail-scroll::-webkit-scrollbar-track {{
      background: rgba(120, 113, 108, .12);
      border-radius: 99px;
    }}
    .detail-scroll::-webkit-scrollbar-thumb {{
      background: rgba(120, 113, 108, .42);
      border-radius: 99px;
      border: 2px solid transparent;
      background-clip: content-box;
    }}
    .detail-card {{
      min-width: 0;
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: rgba(255, 255, 255, .34);
      display: flex;
      flex-direction: column;
    }}
    .detail-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 11px;
    }}
    .detail-head strong {{
      color: var(--text);
      font-size: 13px;
    }}
    .heatmap-widget {{
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: rgba(255, 255, 255, .18);
      display: flex;
      flex-direction: column;
      flex: 1 1 auto;
      min-height: 0;
    }}
    .heatmap-topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      min-height: 34px;
      padding: 6px 8px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, .36);
    }}
    .heatmap-controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .hm-control {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      min-height: 26px;
      padding: 4px 7px;
      border: 1px solid var(--tab-line);
      border-radius: 6px;
      background: var(--tab-bg);
      color: var(--text);
      font-size: 11px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .hm-control .swatch {{
      display: inline-grid;
      grid-template-columns: repeat(2, 5px);
      grid-template-rows: repeat(2, 5px);
      gap: 2px;
    }}
    .hm-control .swatch i {{
      display: block;
      width: 5px;
      height: 5px;
      border-radius: 1px;
    }}
    .hm-control .swatch i:nth-child(1) {{ background: #38bdf8; }}
    .hm-control .swatch i:nth-child(2) {{ background: #22c55e; }}
    .hm-control .swatch i:nth-child(3) {{ background: #fbbf24; }}
    .hm-control .swatch i:nth-child(4) {{ background: #dc2626; }}
    .heatmap-actions {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .heatmap {{
      position: relative;
      height: 360px;
      min-height: 0;
      overflow: hidden;
      border-radius: 0;
      background: rgba(120, 113, 108, .08);
      flex: 1 1 auto;
    }}
    .heatmap-scale {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 6px 8px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 10px;
    }}
    .scale-bar {{
      display: grid;
      grid-template-columns: repeat(5, minmax(28px, 1fr));
      width: min(360px, 60%);
      height: 8px;
      overflow: hidden;
      border-radius: 99px;
    }}
    .scale-bar span:nth-child(1) {{ background: #38bdf8; }}
    .scale-bar span:nth-child(2) {{ background: #2563eb; }}
    .scale-bar span:nth-child(3) {{ background: #fbbf24; }}
    .scale-bar span:nth-child(4) {{ background: #ef4444; }}
    .scale-bar span:nth-child(5) {{ background: #7f1d1d; }}
    .chart {{
      min-height: 0;
      flex: 1 1 auto;
      display: flex;
      flex-direction: column;
    }}
    .chart-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 11px;
    }}
    .chart-head strong {{ color: var(--text); font-size: 13px; }}
    .chart-sub {{
      margin-top: 3px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.3;
    }}
    .version-select-wrap {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 210px;
      justify-content: flex-end;
      flex-wrap: wrap;
    }}
    .version-select-label {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      white-space: nowrap;
    }}
    .version-select {{
      min-width: 160px;
      max-width: 260px;
      width: 100%;
      height: 28px;
      border: 1px solid var(--tab-line);
      border-radius: 7px;
      background: var(--tab-bg);
      color: var(--text);
      padding: 0 8px;
      font: inherit;
      font-size: 12px;
      outline: none;
    }}
    .version-select:focus {{
      border-color: #2563eb;
      box-shadow: 0 0 0 3px rgba(37, 99, 235, .14);
    }}
    .version-select:disabled {{
      opacity: .55;
      cursor: not-allowed;
    }}
    .version-buttons {{
      display: none;
    }}
    .version-tab {{
      border: 1px solid var(--tab-line);
      background: var(--tab-bg);
      color: var(--text);
      padding: 6px 9px;
      border-radius: 7px;
      font-size: 12px;
      cursor: pointer;
    }}
    .version-tab.active {{
      background: var(--tab-active);
      color: var(--tab-active-text);
      border-color: transparent;
    }}
    .chart svg {{ display: block; width: 100%; height: auto; overflow: visible; }}
    .axis-label {{ fill: currentColor; color: var(--muted); font-size: 13px; font-weight: 700; }}
    .chart-count {{ fill: currentColor; color: var(--text); font-size: 13px; font-weight: 800; }}
    .trend-line {{ fill: none; stroke: #2563eb; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; }}
    .trend-dot {{ fill: #dc2626; stroke: rgba(255, 255, 255, .7); stroke-width: 2; }}
    .trend-dot.selected {{ fill: #fbbf24; stroke: #dc2626; stroke-width: 3; }}
    .trend-bar {{ fill: rgba(37, 99, 235, .22); }}
    .trend-bar.selected {{ fill: rgba(220, 38, 38, .28); }}
    .distribution {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      margin-top: 8px;
    }}
    .dist-block {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: rgba(255, 255, 255, .28);
    }}
    .dist-title {{
      margin-bottom: 6px;
      color: var(--text);
      font-size: 11px;
      font-weight: 800;
    }}
    .dist-row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 54px 48px;
      gap: 8px;
      align-items: center;
      margin-top: 5px;
      color: var(--muted);
      font-size: 11px;
      border-radius: 6px;
      padding: 4px 6px;
    }}
    .dist-name {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .dist-count, .dist-rate {{
      color: var(--text);
      text-align: right;
      font-weight: 700;
    }}
    .severity-critical .dist-name,
    .severity-critical .dist-count,
    .severity-critical .dist-rate {{
      color: #dc2626;
      font-weight: 900;
    }}
    .severity-major .dist-name,
    .severity-major .dist-count,
    .severity-major .dist-rate {{
      color: #d97706;
      font-weight: 800;
    }}
    .severity-minor .dist-name,
    .severity-minor .dist-count,
    .severity-minor .dist-rate {{
      color: #2563eb;
      font-weight: 800;
    }}
    .type-hot {{
      background: linear-gradient(135deg, rgba(220, 38, 38, .18), rgba(255, 255, 255, .04));
    }}
    .type-warm {{
      background: linear-gradient(135deg, rgba(217, 119, 6, .16), rgba(255, 255, 255, .04));
    }}
    .type-cool {{
      background: linear-gradient(135deg, rgba(37, 99, 235, .14), rgba(255, 255, 255, .04));
    }}
    .type-hot .dist-name, .type-hot .dist-count, .type-hot .dist-rate {{
      color: #dc2626;
      font-weight: 900;
    }}
    .type-warm .dist-name, .type-warm .dist-count, .type-warm .dist-rate {{
      color: #d97706;
      font-weight: 800;
    }}
    .type-cool .dist-name, .type-cool .dist-count, .type-cool .dist-rate {{
      color: #2563eb;
      font-weight: 800;
    }}
    .tile {{
      position: relative;
      border: 0;
      border-radius: 8px;
      padding: 9px;
      color: white;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
      cursor: pointer;
      min-width: 0;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, .18);
    }}
    .heatmap .tile {{
      position: absolute;
      width: var(--w);
      height: var(--h);
      left: var(--x);
      top: var(--y);
      min-width: 0;
      min-height: 0;
    }}
    .tile:hover {{ filter: brightness(0.96); }}
    .tile.small {{ padding: 6px; }}
    .tile.small .area {{ font-size: 12px; }}
    .tile.small .count {{ font-size: 14px; margin-top: 3px; }}
    .tile.small .detail {{ display: none; }}
    .tile.small .badge,
    .tile.small .ratio {{ font-size: 8px; }}
    .area {{ font-weight: 800; font-size: 13px; line-height: 1.2; word-break: keep-all; }}
    .count {{ margin-top: 5px; font-size: 16px; font-weight: 800; }}
    .detail {{ margin-top: 5px; font-size: 10px; opacity: .9; }}
    .badge {{ position: absolute; top: 6px; left: 8px; font-size: 9px; opacity: .9; }}
    .ratio {{ position: absolute; right: 8px; bottom: 6px; font-size: 9px; opacity: .9; }}
    .blue {{ background: linear-gradient(135deg, #38bdf8, #2563eb); }}
    .orange {{ background: linear-gradient(135deg, #fbbf24, #d97706); }}
    .red1 {{ background: linear-gradient(135deg, #fb7185, #ef4444); }}
    .red2 {{ background: linear-gradient(135deg, #f43f5e, #dc2626); }}
    .red3 {{ background: linear-gradient(135deg, #dc2626, #7f1d1d); }}
    .gray {{ background: linear-gradient(135deg, #cbd5e1, #64748b); }}
    .footer {{
      display: flex;
      justify-content: space-between;
      flex-direction: column;
      gap: 4px;
      margin-top: 6px;
      color: var(--muted);
      font-size: 9px;
    }}
    .empty {{
      padding: 48px 12px;
      color: var(--muted);
      text-align: center;
      border: 1px dashed var(--tab-line);
      border-radius: 8px;
      grid-column: 1 / -1;
    }}
    .issue-panel {{
      position: fixed;
      inset: 10px;
      z-index: 20;
      display: none;
      grid-template-rows: auto 1fr;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel-solid);
      box-shadow: 0 20px 60px rgba(0, 0, 0, .22);
    }}
    .issue-panel.open {{ display: grid; }}
    .issue-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-head);
    }}
    .issue-title {{
      min-width: 0;
      color: var(--text);
      font-size: 14px;
      font-weight: 900;
    }}
    .issue-meta {{
      margin-top: 3px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 500;
    }}
    .issue-close {{
      border: 1px solid var(--tab-line);
      background: var(--tab-bg);
      color: var(--text);
      border-radius: 7px;
      padding: 7px 10px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 800;
    }}
    .issue-list {{
      overflow-y: auto;
      padding: 10px;
      background: var(--panel-solid);
    }}
    .issue-row {{
      display: grid;
      grid-template-columns: 86px minmax(0, 1fr) 96px 98px 128px;
      gap: 10px;
      align-items: center;
      width: 100%;
      margin-bottom: 7px;
      padding: 9px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--row-solid);
      color: var(--text);
      text-align: left;
      cursor: pointer;
      font: inherit;
    }}
    .issue-row:hover {{ background: var(--row-hover); }}
    .issue-id, .issue-severity, .issue-status, .issue-version {{
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .issue-name {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 12px;
      font-weight: 800;
    }}
    .issue-severity.critical {{ color: #dc2626; font-weight: 900; }}
    .issue-severity.major {{ color: #d97706; font-weight: 900; }}
    .issue-severity.minor {{ color: #2563eb; font-weight: 900; }}
    @media (max-width: 1180px) {{
      .dashboard {{ max-width: 100%; height: calc(100vh - 20px); }}
      .detail-grid {{ grid-template-columns: 1fr; min-height: 1320px; }}
      .heatmap {{ height: 620px; }}
      .chart {{ min-height: 520px; }}
    }}
    @media (max-width: 760px) {{
      body {{ padding: 10px; }}
      .dashboard {{ min-width: 0; height: calc(100vh - 20px); }}
      .header {{ align-items: flex-start; flex-direction: column; }}
      .meta {{ text-align: left; }}
      .summary {{ grid-template-columns: 1fr; }}
      .growth {{ grid-template-columns: 1fr; }}
      .funnel {{ grid-template-columns: 1fr; }}
      .toolbar {{ align-items: flex-start; flex-direction: column; }}
      .search-wrap {{ width: 100%; min-width: 0; margin-left: 0; }}
      .detail-grid {{ grid-template-columns: 1fr; }}
      .heatmap {{ height: 520px; }}
      .distribution {{ grid-template-columns: 1fr; }}
      .issue-row {{ grid-template-columns: 70px minmax(0, 1fr); }}
      .issue-status, .issue-version, .issue-severity {{ display: none; }}
    }}
  </style>
</head>
<body>
  <div class="dashboard">
    <div class="fixed-zone">
      <div class="header">
        <div>
          <div class="title">QA 결함 히트맵</div>
          <div class="subtitle">5.18.0 이후 / 목표버전 기준</div>
        </div>
        <div class="meta">마지막 생성<br /><strong id="updatedAt">-</strong></div>
      </div>

      <div class="summary">
        <div class="card total">
          <div class="card-label">전체 결함</div>
          <div class="card-value" id="totalDefects">0</div>
          <div class="card-note">Notion QA_ISSUES</div>
        </div>
        <div class="card open">
          <div class="card-label">미완료 결함</div>
          <div class="card-value" id="openDefects">0</div>
          <div class="card-note">Done/QA검증/결함아님/추후수정 제외</div>
        </div>
        <div class="card future">
          <div class="card-label">추후 수정</div>
          <div class="card-value" id="futureFix">0</div>
          <div class="card-note">추후 수정 백로그 이관</div>
        </div>
        <div class="card risk" id="riskCard">
          <div class="card-label">Release Risk</div>
          <div class="card-value" id="riskLevel">-</div>
          <div class="card-note" id="riskNote">-</div>
        </div>
      </div>

      <div class="growth" id="growthFunnel"></div>
    </div>

    <section class="panel">
      <div class="panel-title">결함 상세</div>
      <div class="panel-body">
        <div class="detail-fixed">
          <div class="toolbar">
            <div class="tabs" id="tabs"></div>
            <div class="search-wrap">
              <input class="issue-search" id="issueSearch" type="search" placeholder="결함 검색" autocomplete="off" />
              <button class="search-clear" id="issueSearchClear" type="button">초기화</button>
            </div>
          </div>
        </div>
        <div class="detail-scroll">
          <div class="detail-grid">
            <section class="detail-card">
              <div class="detail-head">
                <strong>결함 히트맵</strong>
                <span>영역별 결함 밀도 / 클릭 시 Notion 이동</span>
              </div>
              <div class="heatmap-widget">
                <div class="heatmap-topbar">
                  <div class="heatmap-controls">
                    <span class="hm-control">
                      <span class="swatch"><i></i><i></i><i></i><i></i></span>
                      색상 위험도
                    </span>
                  </div>
                  <div class="heatmap-actions">Treemap</div>
                </div>
                <div class="heatmap" id="heatmap"></div>
                <div class="heatmap-scale">
                  낮음
                  <span class="scale-bar"><span></span><span></span><span></span><span></span><span></span></span>
                  높음
                </div>
              </div>
            </section>
            <section class="detail-card">
              <div class="detail-head">
                <div>
                  <strong>타겟 버전별 결함 추이</strong>
                  <div class="chart-sub">최근 5개 기본 표출 / 버전 선택 가능</div>
                </div>
                <div class="version-select-wrap">
                  <label class="version-select-label" for="versionSelect">버전</label>
                  <select class="version-select" id="versionSelect" disabled></select>
                </div>
              </div>
              <div class="chart-head">
                <span id="chartMeta">-</span>
              </div>
              <div class="chart" id="versionChart"></div>
            </section>
          </div>
        </div>
        <div class="footer">
          <div>기준: 5.18.0 이후, GO.Hanpass 포함</div>
          <div>영역: 결함 요약 첫 태그</div>
        </div>
      </div>
    </section>
  </div>

  <div class="issue-panel" id="issuePanel" aria-live="polite">
    <div class="issue-head">
      <div>
        <div class="issue-title" id="issuePanelTitle">결함 리스트</div>
        <div class="issue-meta" id="issuePanelMeta">-</div>
      </div>
      <button class="issue-close" type="button" id="issuePanelClose">닫기</button>
    </div>
    <div class="issue-list" id="issueList"></div>
  </div>

  <script>
    const DATA = {safe_json};
    const FILTERS = [
      {{ key: "all", label: "전체" }},
      {{ key: "hanpass", label: "한패스" }},
      {{ key: "gohanpass", label: "방한 고한패스" }},
      {{ key: "major", label: "Major+" }}
    ];
    let activeFilter = "all";
    let selectedVersion = "";
    let searchQuery = "";

    function isDone(row) {{
      return row.status.includes("완료") ||
        row.status.includes("Done") ||
        row.status.includes("QA 검증") ||
        row.status.includes("회귀") ||
        row.status.includes("결함 아님") ||
        row.status.includes("Not an issue");
    }}

    function isFutureFix(row) {{
      return row.status.includes("추후 수정 백로그 이관");
    }}

    function isMajorPlus(row) {{
      return row.severity === "Critical" || row.severity === "Major";
    }}

    function matchesSearch(row) {{
      if (!searchQuery) return true;
      return [
        row.id,
        row.title,
        row.area,
        row.domain,
        row.targetVersion,
        row.severity,
        row.status,
        row.defectType
      ].some(value => String(value || "").toLowerCase().includes(searchQuery));
    }}

    function rowsByFilter() {{
      return DATA.rows.filter(row => {{
        if (activeFilter === "hanpass" && row.domain !== "한패스") return false;
        if (activeFilter === "gohanpass" && row.domain !== "방한 고한패스") return false;
        if (activeFilter === "major" && !isMajorPlus(row)) return false;
        return matchesSearch(row);
      }});
    }}

    function colorByScore(count, majorPlus, maxCount) {{
      const ratio = maxCount ? count / maxCount : 0;
      if (majorPlus >= 3 || ratio >= .8) return "red3";
      if (majorPlus >= 2 || ratio >= .6) return "red2";
      if (majorPlus >= 1 || ratio >= .4) return "red1";
      if (ratio >= .2) return "orange";
      if (count > 0) return "blue";
      return "gray";
    }}

    function groupRows(rows) {{
      const map = new Map();
      rows.forEach(row => {{
        if (!map.has(row.area)) {{
          map.set(row.area, {{
            area: row.area,
            count: 0,
            open: 0,
            majorPlus: 0,
            critical: 0,
            severities: {{}},
            types: {{}},
            domains: {{}},
            examples: [],
            rows: [],
            landingUrl: "",
            landingTitle: ""
          }});
        }}
        const item = map.get(row.area);
        item.count += 1;
        if (!isDone(row) && !isFutureFix(row)) item.open += 1;
        if (isMajorPlus(row)) item.majorPlus += 1;
        if (row.severity === "Critical") item.critical += 1;
        item.severities[row.severity] = (item.severities[row.severity] || 0) + 1;
        item.types[row.defectType] = (item.types[row.defectType] || 0) + 1;
        item.domains[row.domain] = (item.domains[row.domain] || 0) + 1;
        item.rows.push(row);
        if (item.examples.length < 3) item.examples.push(row.title);
        if (!item.landingUrl && row.url) {{
          item.landingUrl = row.url;
          item.landingTitle = row.title;
        }}
      }});
      return Array.from(map.values()).sort((a, b) =>
        b.count - a.count || b.majorPlus - a.majorPlus || a.area.localeCompare(b.area, "ko")
      );
    }}

    function topLabel(counter) {{
      const entries = Object.entries(counter).sort((a, b) => b[1] - a[1]);
      return entries.length ? `${{entries[0][0]}} ${{entries[0][1]}}` : "-";
    }}

    function renderTabs() {{
      const tabs = document.getElementById("tabs");
      tabs.innerHTML = "";
      FILTERS.forEach(filter => {{
        const button = document.createElement("button");
        button.className = `tab ${{activeFilter === filter.key ? "active" : ""}}`;
        button.type = "button";
        button.textContent = filter.label;
        button.addEventListener("click", () => {{
          activeFilter = filter.key;
          render();
        }});
        tabs.appendChild(button);
      }});
    }}

    function dateKey(row) {{
      return row.createdAt ? row.createdAt.slice(0, 10) : "";
    }}

    function addDays(dateKeyValue, days) {{
      const date = new Date(`${{dateKeyValue}}T00:00:00Z`);
      date.setUTCDate(date.getUTCDate() + days);
      return date.toISOString().slice(0, 10);
    }}

    function renderGrowthFunnel(rows) {{
      const container = document.getElementById("growthFunnel");
      const latest = DATA.generatedAt ? DATA.generatedAt.slice(0, 10) : "";
      if (!latest) {{
        container.innerHTML = '<div class="growth-title">전일 대비<strong>-</strong></div><div class="funnel"><div class="empty">집계일 데이터가 없습니다.</div></div>';
        return;
      }}

      const previous = addDays(latest, -1);
      const latestCount = rows.length;
      const previousCount = rows.filter(row => {{
        const key = dateKey(row);
        return !key || key <= previous;
      }}).length;
      const delta = latestCount - previousCount;
      const max = Math.max(latestCount, previousCount, Math.abs(delta), 1);
      const deltaText = delta > 0 ? `+${{delta}}` : String(delta);
      const deltaLabel = `${{previous}} 기준`;

      container.innerHTML = `
        <div class="growth-title">
          전일 기준 결함 증가
          <strong>${{deltaText}}건</strong>
          <span>${{deltaLabel}}</span>
        </div>
        <div class="funnel">
          <div class="funnel-step">
            <div class="funnel-label">이전 집계일 ${{previous || "-"}}</div>
            <div class="funnel-value">${{previousCount}}건</div>
            <div class="funnel-bar"><span style="--w: ${{Math.round((previousCount / max) * 100)}}%"></span></div>
          </div>
          <div class="funnel-step">
            <div class="funnel-label">최신 집계일 ${{latest}}</div>
            <div class="funnel-value">${{latestCount}}건</div>
            <div class="funnel-bar"><span style="--w: ${{Math.round((latestCount / max) * 100)}}%"></span></div>
          </div>
          <div class="funnel-step delta">
            <div class="funnel-label">증가분</div>
            <div class="funnel-value">${{deltaText}}건</div>
            <div class="funnel-bar"><span style="--w: ${{Math.round((Math.abs(delta) / max) * 100)}}%"></span></div>
          </div>
        </div>
      `;
    }}

    function renderSummary(rows) {{
      const total = rows.length;
      const open = rows.filter(row => !isDone(row) && !isFutureFix(row)).length;
      const futureFix = rows.filter(isFutureFix).length;
      const majorPlus = rows.filter(isMajorPlus).length;
      const critical = rows.filter(row => row.severity === "Critical").length;
      const risk = critical > 0 || majorPlus >= 5 ? "High" : majorPlus > 0 ? "Medium" : "Low";
      const domainCounts = rows.reduce((acc, row) => {{
        acc[row.domain] = (acc[row.domain] || 0) + 1;
        return acc;
      }}, {{}});

      document.getElementById("totalDefects").textContent = total;
      document.getElementById("openDefects").textContent = open;
      document.getElementById("futureFix").textContent = futureFix;
      document.getElementById("riskLevel").textContent = risk;
      document.getElementById("riskCard").className = `card risk ${{risk.toLowerCase()}}`;
      document.getElementById("riskNote").textContent =
        `Major+ ${{majorPlus}} / ${{Object.entries(domainCounts).map(([key, value]) => `${{key}} ${{value}}`).join(" / ") || "-"}}`;
    }}

    function severityNameClass(severity) {{
      const value = String(severity || "").toLowerCase();
      if (value.includes("critical")) return "critical";
      if (value.includes("major")) return "major";
      if (value.includes("minor")) return "minor";
      return "";
    }}

    function escapeHtml(value) {{
      return String(value ?? "").replace(/[&<>"']/g, char => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }}[char]));
    }}

    function sortIssues(rows) {{
      const severityRank = {{ Critical: 0, Major: 1, Minor: 2 }};
      return [...rows].sort((a, b) => {{
        const leftRank = severityRank[a.severity] ?? 9;
        const rightRank = severityRank[b.severity] ?? 9;
        if (leftRank !== rightRank) return leftRank - rightRank;
        return String(b.createdAt || "").localeCompare(String(a.createdAt || ""));
      }});
    }}

    function openIssueList(title, rows, description = "") {{
      const panel = document.getElementById("issuePanel");
      const list = document.getElementById("issueList");
      const sorted = sortIssues(rows);
      document.getElementById("issuePanelTitle").textContent = title;
      document.getElementById("issuePanelMeta").textContent = `${{sorted.length}}건${{description ? " / " + description : ""}}`;
      list.innerHTML = sorted.length ? sorted.map(row => `
        <button class="issue-row" type="button" data-url="${{escapeHtml(row.url || "")}}">
          <span class="issue-id">${{escapeHtml(row.id || "-")}}</span>
          <span class="issue-name" title="${{escapeHtml(row.title || "-")}}">${{escapeHtml(row.title || "-")}}</span>
          <span class="issue-severity ${{severityNameClass(row.severity)}}">${{escapeHtml(row.severity || "-")}}</span>
          <span class="issue-status" title="${{escapeHtml(row.status || "-")}}">${{escapeHtml(row.status || "-")}}</span>
          <span class="issue-version">${{escapeHtml(row.targetVersion || "-")}}</span>
        </button>
      `).join("") : '<div class="empty">표시할 결함이 없습니다.</div>';

      list.querySelectorAll(".issue-row").forEach(button => {{
        button.addEventListener("click", () => {{
          const url = button.dataset.url;
          if (url) window.open(url, "_blank", "noopener");
        }});
      }});

      panel.classList.add("open");
    }}

    function closeIssueList() {{
      document.getElementById("issuePanel").classList.remove("open");
    }}

    function versionSortKey(version) {{
      const normalized = String(version || "").replace(/\\s+/g, "");
      const plain = normalized.match(/^(\\d+)\\.(\\d+)\\.(\\d+)$/);
      if (plain) return [0, Number(plain[1]), Number(plain[2]), Number(plain[3])];
      const gh = normalized.toUpperCase().match(/^\\[G\\.?H\\]V?(\\d+)\\.(\\d+)\\.(\\d+)$/);
      if (gh) return [1, Number(gh[1]), Number(gh[2]), Number(gh[3])];
      return [2, normalized];
    }}

    function compareVersions(a, b) {{
      const left = versionSortKey(a);
      const right = versionSortKey(b);
      for (let index = 0; index < Math.max(left.length, right.length); index += 1) {{
        if ((left[index] ?? 0) < (right[index] ?? 0)) return -1;
        if ((left[index] ?? 0) > (right[index] ?? 0)) return 1;
      }}
      return String(a).localeCompare(String(b), "ko");
    }}

    function visibleVersionWindow(items, currentVersion, size = 5) {{
      if (!items.length) return [];
      const index = Math.max(0, items.findIndex(item => item.version === currentVersion));
      const endIndex = index >= 0 ? index : items.length - 1;
      const startIndex = Math.max(0, endIndex - (size - 1));
      return items.slice(startIndex, endIndex + 1);
    }}

    function countBy(rows, key) {{
      return rows.reduce((acc, row) => {{
        const value = row[key] || "미지정";
        acc[value] = (acc[value] || 0) + 1;
        return acc;
      }}, {{}});
    }}

    function severityClass(name) {{
      const value = String(name || "").toLowerCase();
      if (value.includes("critical")) return "severity-critical";
      if (value.includes("major")) return "severity-major";
      if (value.includes("minor")) return "severity-minor";
      return "";
    }}

    function heatClass(count, max) {{
      const ratio = max ? count / max : 0;
      if (ratio >= .75) return "type-hot";
      if (ratio >= .35) return "type-warm";
      return "type-cool";
    }}

    function renderDistributionBlock(title, counter, total, mode = "default") {{
      const entries = Object.entries(counter).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ko"));
      if (!entries.length) {{
        return `<div class="dist-block"><div class="dist-title">${{title}}</div><div class="dist-row"><span class="dist-name">데이터 없음</span><span class="dist-count">0건</span><span class="dist-rate">0%</span></div></div>`;
      }}
      const maxCount = Math.max(...entries.map(([, count]) => count), 1);
      return `
        <div class="dist-block">
          <div class="dist-title">${{title}}</div>
          ${{entries.map(([name, count]) => `
            <div class="dist-row ${{mode === "severity" ? severityClass(name) : heatClass(count, maxCount)}}">
              <span class="dist-name" title="${{name}}">${{name}}</span>
              <span class="dist-count">${{count}}건</span>
              <span class="dist-rate">${{total ? Math.round((count / total) * 100) : 0}}%</span>
            </div>
          `).join("")}}
        </div>
      `;
    }}

    function renderVersionChart(rows) {{
      const chart = document.getElementById("versionChart");
      const select = document.getElementById("versionSelect");
      const versionMap = new Map();
      rows.forEach(row => {{
        const version = row.targetVersion || "미지정";
        if (!versionMap.has(version)) {{
          versionMap.set(version, {{ version, total: 0, open: 0, majorPlus: 0, rows: [] }});
        }}
        const item = versionMap.get(version);
        item.total += 1;
        if (!isDone(row) && !isFutureFix(row)) item.open += 1;
        if (isMajorPlus(row)) item.majorPlus += 1;
        item.rows.push(row);
      }});

      const items = Array.from(versionMap.values()).sort((a, b) => compareVersions(a.version, b.version));
      if (!items.length) {{
        chart.innerHTML = '<div class="empty">표시할 버전 데이터가 없습니다.</div>';
        if (select) {{
          select.innerHTML = "";
          select.disabled = true;
        }}
        return;
      }}

      if (!selectedVersion || !versionMap.has(selectedVersion)) {{
        selectedVersion = items[items.length - 1].version;
      }}
      const selected = versionMap.get(selectedVersion);
      const visibleItems = visibleVersionWindow(items, selectedVersion, 5);
      const visibleVersions = new Set(visibleItems.map(item => item.version));

      const width = 1120;
      const height = 290;
      const padX = 54;
      const padY = 38;
      const plotW = width - padX * 2;
      const plotH = height - padY * 2;
      const max = Math.max(...visibleItems.map(item => item.total), 1);
      const step = visibleItems.length > 1 ? plotW / (visibleItems.length - 1) : plotW;
      const points = visibleItems.map((item, index) => {{
        const x = padX + (visibleItems.length > 1 ? index * step : plotW / 2);
        const y = padY + plotH - (item.total / max) * plotH;
        return {{ ...item, x, y }};
      }});
      const path = points.map(point => `${{point.x}},${{point.y}}`).join(" ");

      if (select) {{
        select.disabled = false;
        select.innerHTML = items.map(item => `
          <option value="${{item.version}}" ${{item.version === selectedVersion ? "selected" : ""}}>
            ${{item.version}} · ${{item.total}}건
          </option>
        `).join("");
        select.onchange = () => {{
          selectedVersion = select.value;
          renderVersionChart(rows);
        }};
      }}

      document.getElementById("chartMeta").textContent = `최근 ${{visibleItems.length}}개 / 선택 ${{selectedVersion}} / ${{selected.total}}건`;
      chart.innerHTML = `
        <svg viewBox="0 0 ${{width}} ${{height}}" role="img" aria-label="타겟 버전별 결함 추이 그래프">
          <line x1="${{padX}}" y1="${{height - padY}}" x2="${{width - padX}}" y2="${{height - padY}}" stroke="currentColor" opacity=".18" />
          ${{points.map(point => `
            <rect class="trend-bar ${{point.version === selectedVersion ? "selected" : ""}}" x="${{point.x - 18}}" y="${{point.y}}" width="36" height="${{height - padY - point.y}}" rx="7"></rect>
          `).join("")}}
          <polyline class="trend-line" points="${{path}}"></polyline>
          ${{points.map((point, index) => `
            <circle class="trend-dot ${{point.version === selectedVersion ? "selected" : ""}}" cx="${{point.x}}" cy="${{point.y}}" r="7"></circle>
            <text class="chart-count" x="${{point.x}}" y="${{point.y - 14}}" text-anchor="middle">${{point.total}}</text>
            <text class="axis-label" x="${{point.x}}" y="${{height - 12}}" text-anchor="middle">${{point.version}}</text>
          `).join("")}}
        </svg>
        <div class="distribution">
          ${{renderDistributionBlock("심각도 분포", countBy(selected.rows, "severity"), selected.total, "severity")}}
          ${{renderDistributionBlock("결함유형 분포", countBy(selected.rows, "defectType"), selected.total, "type")}}
        </div>
      `;
    }}

    function normalizeRect(rect) {{
      return {{
        x: rect.x,
        y: rect.y,
        w: Math.max(0, rect.w),
        h: Math.max(0, rect.h)
      }};
    }}

    function splitTreemap(items, rect) {{
      if (!items.length) return [];
      if (items.length === 1) return [{{ item: items[0], rect: normalizeRect(rect) }}];

      const total = items.reduce((sum, item) => sum + item.count, 0);
      const half = total / 2;
      let acc = 0;
      let splitIndex = 0;
      for (let index = 0; index < items.length - 1; index += 1) {{
        if (acc + items[index].count > half && index > 0) break;
        acc += items[index].count;
        splitIndex = index + 1;
      }}

      const leftItems = items.slice(0, splitIndex);
      const rightItems = items.slice(splitIndex);
      const leftTotal = leftItems.reduce((sum, item) => sum + item.count, 0);
      const ratio = total ? leftTotal / total : .5;

      if (rect.w >= rect.h) {{
        const leftW = rect.w * ratio;
        return [
          ...splitTreemap(leftItems, {{ x: rect.x, y: rect.y, w: leftW, h: rect.h }}),
          ...splitTreemap(rightItems, {{ x: rect.x + leftW, y: rect.y, w: rect.w - leftW, h: rect.h }})
        ];
      }}

      const topH = rect.h * ratio;
      return [
        ...splitTreemap(leftItems, {{ x: rect.x, y: rect.y, w: rect.w, h: topH }}),
        ...splitTreemap(rightItems, {{ x: rect.x, y: rect.y + topH, w: rect.w, h: rect.h - topH }})
      ];
    }}

    function renderHeatmap(groups) {{
      const heatmap = document.getElementById("heatmap");
      heatmap.innerHTML = "";
      if (!groups.length) {{
        heatmap.innerHTML = '<div class="empty">표시할 결함이 없습니다.</div>';
        return;
      }}

      const maxCount = Math.max(...groups.map(group => group.count));
      const width = heatmap.clientWidth || 720;
      const height = heatmap.clientHeight || 560;
      const gap = 4;
      const layout = splitTreemap(groups, {{ x: 0, y: 0, w: width, h: height }});

      layout.forEach((entry, index) => {{
        const group = entry.item;
        const rect = entry.rect;
        const tile = document.createElement("button");
        const color = colorByScore(group.count, group.majorPlus, maxCount);
        const isSmall = group.count < 10 || rect.w < 120 || rect.h < 90;
        tile.className = `tile ${{color}} ${{isSmall ? "small" : ""}}`;
        tile.type = "button";
        tile.style.setProperty("--x", `${{rect.x + gap / 2}}px`);
        tile.style.setProperty("--y", `${{rect.y + gap / 2}}px`);
        tile.style.setProperty("--w", `${{Math.max(24, rect.w - gap)}}px`);
        tile.style.setProperty("--h", `${{Math.max(24, rect.h - gap)}}px`);
        tile.title = [
          `${{group.area}}: ${{group.count}}건`,
          `Major+ ${{group.majorPlus}}건`,
          "클릭 시 결함 리스트 표시",
          `주요 유형: ${{topLabel(group.types)}}`,
          ...group.examples
        ].join("\\n");
        tile.addEventListener("click", () => {{
          openIssueList(`${{group.area}} 결함 리스트`, group.rows, `미완료 ${{group.open}} / Major+ ${{group.majorPlus}}`);
        }});
        tile.innerHTML = `
          <div class="badge">${{group.majorPlus ? "Major+ " + group.majorPlus : "Minor 중심"}}</div>
          <div class="area">${{group.area}}</div>
          <div class="count">${{group.count}}건</div>
          <div class="detail">미완료 ${{group.open}} / ${{topLabel(group.types)}}</div>
          <div class="ratio">${{Math.round((group.count / maxCount) * 100)}}%</div>
        `;
        heatmap.appendChild(tile);
      }});
    }}

    function render() {{
      renderTabs();
      const filtered = rowsByFilter();
      const searchInput = document.getElementById("issueSearch");
      if (searchInput && searchInput.value.trim().toLowerCase() !== searchQuery) {{
        searchInput.value = searchQuery;
      }}
      renderSummary(filtered);
      renderGrowthFunnel(filtered);
      renderHeatmap(groupRows(filtered));
      renderVersionChart(filtered);
      document.querySelector(".card.total").onclick = () =>
        openIssueList("전체 결함 리스트", filtered, "현재 선택 필터 기준");
      document.querySelector(".card.open").onclick = () =>
        openIssueList("미완료 결함 리스트", filtered.filter(row => !isDone(row) && !isFutureFix(row)), "Done/QA검증/결함아님/추후수정 제외");
      document.querySelector(".card.future").onclick = () =>
        openIssueList("추후 수정 결함 리스트", filtered.filter(isFutureFix), "추후 수정 백로그 이관");
      document.getElementById("updatedAt").textContent = DATA.generatedAt;
    }}

    render();
    document.getElementById("issueSearch").addEventListener("input", event => {{
      searchQuery = event.target.value.trim().toLowerCase();
      render();
    }});
    document.getElementById("issueSearchClear").addEventListener("click", () => {{
      searchQuery = "";
      const input = document.getElementById("issueSearch");
      input.value = "";
      render();
      input.focus();
    }});
    document.getElementById("issuePanelClose").addEventListener("click", closeIssueList);
    document.getElementById("issuePanel").addEventListener("click", event => {{
      if (event.target.id === "issuePanel") closeIssueList();
    }});
    window.addEventListener("keydown", event => {{
      if (event.key === "Escape") closeIssueList();
    }});
    window.addEventListener("resize", () => {{
      window.clearTimeout(window.__heatmapResizeTimer);
      window.__heatmapResizeTimer = window.setTimeout(render, 120);
    }});
  </script>
</body>
</html>
"""


def run_git(args, cwd=None, check=True):
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result


def ensure_publish_repo():
    PUBLISH_DIR.parent.mkdir(parents=True, exist_ok=True)

    if not (PUBLISH_DIR / ".git").exists():
        if PUBLISH_DIR.exists():
            raise RuntimeError(f"{PUBLISH_DIR} exists but is not a git repository.")
        run_git(["clone", REPO_URL, str(PUBLISH_DIR)])

    run_git(["config", "user.name", "QA Heatmap Bot"], cwd=PUBLISH_DIR)
    run_git(["config", "user.email", "qa-hitmap@users.noreply.github.com"], cwd=PUBLISH_DIR)

    branch_check = run_git(["rev-parse", "--verify", PUBLISH_BRANCH], cwd=PUBLISH_DIR, check=False)
    if branch_check.returncode == 0:
        run_git(["checkout", PUBLISH_BRANCH], cwd=PUBLISH_DIR)
        run_git(["pull", "--ff-only", "origin", PUBLISH_BRANCH], cwd=PUBLISH_DIR, check=False)
    else:
        run_git(["checkout", "-B", PUBLISH_BRANCH], cwd=PUBLISH_DIR)


def publish_html():
    source = Path(OUT_FILE)
    if not source.exists():
        raise RuntimeError(f"{OUT_FILE} does not exist.")

    ensure_publish_repo()
    shutil.copyfile(source, PUBLISH_DIR / OUT_FILE)

    for extra_file in ("index.html", "README.md", ".nojekyll"):
        path = PUBLISH_DIR / extra_file
        if path.exists():
            path.unlink()

    run_git(["add", "-A"], cwd=PUBLISH_DIR)
    diff = run_git(["diff", "--cached", "--quiet"], cwd=PUBLISH_DIR, check=False)
    if diff.returncode == 0:
        print("No GitHub changes to publish.")
        return

    timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    run_git(["commit", "-m", f"Update QA heatmap {timestamp}"], cwd=PUBLISH_DIR)
    run_git(["push", "-u", "origin", PUBLISH_BRANCH], cwd=PUBLISH_DIR)
    print(f"Published {OUT_FILE} to {REPO_URL}")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate Notion QA heatmap HTML.")
    publish_group = parser.add_mutually_exclusive_group()
    publish_group.add_argument(
        "--publish",
        dest="publish",
        action="store_true",
        help="After generating HTML, commit and push it to the GitHub repository.",
    )
    publish_group.add_argument(
        "--no-publish",
        dest="publish",
        action="store_false",
        help="Generate the HTML locally only and skip GitHub upload.",
    )
    parser.set_defaults(publish=True)
    return parser.parse_args()


def main():
    load_env_file()
    args = parse_args()
    pages = fetch_pages()
    rows = normalize_pages(pages)
    html = build_html(rows)
    with open(OUT_FILE, "w", encoding="utf-8") as file:
        file.write(html)
    print(f"Generated {OUT_FILE} with {len(rows)} Notion rows.")
    if args.publish:
        publish_html()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
