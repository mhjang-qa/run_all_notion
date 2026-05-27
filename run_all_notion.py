#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parent
HEATMAP_DIR = ROOT / "notion_hit"
HQI_DIR = ROOT / "HQI"
MONITOR_DIR = ROOT / "gohanpass_automation" / "Monitor"
DEFECT_DASHBOARD_DIR = ROOT / "Bug_Dashboard"

DEFAULT_MONITOR_REPO_URL = "https://github.com/mhjang-qa/gohanpass-web-monitor.git"
DEFAULT_MONITOR_PUBLISH_DIR = MONITOR_DIR / ".publish" / "gohanpass-web-monitor"
DEFAULT_BRANCH = "main"
NOTION_VERSION = "2022-06-28"


class StepError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[notion-runner] {message}", flush=True)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_all_env() -> None:
    for env_path in (
        ROOT / ".env",
        HEATMAP_DIR / ".env",
        HQI_DIR / ".env",
        MONITOR_DIR / ".env",
        DEFECT_DASHBOARD_DIR / ".env",
    ):
        load_env_file(env_path)


def run_command(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    log(f"run: {' '.join(args)} (cwd={cwd})")
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.stdout.strip():
        print(result.stdout.rstrip())
    if check and result.returncode != 0:
        raise StepError(f"command failed ({result.returncode}): {' '.join(args)}")
    return result


def run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(["git", *args], cwd=cwd, check=check)


def ensure_git_branch(repo_dir: Path, branch: str = DEFAULT_BRANCH) -> None:
    run_git(["config", "user.name", "Notion Dashboard Bot"], cwd=repo_dir)
    run_git(["config", "user.email", "notion-dashboard@users.noreply.github.com"], cwd=repo_dir)
    run_git(["fetch", "origin"], cwd=repo_dir, check=False)

    local_branch = run_git(["rev-parse", "--verify", branch], cwd=repo_dir, check=False)
    remote_branch = run_git(["rev-parse", "--verify", f"origin/{branch}"], cwd=repo_dir, check=False)
    current_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir, check=False)

    if local_branch.returncode == 0:
        if current_branch.stdout.strip() != branch:
            run_git(["checkout", branch], cwd=repo_dir)
    elif remote_branch.returncode == 0:
        run_git(["checkout", "-B", branch, f"origin/{branch}"], cwd=repo_dir)
    else:
        run_git(["checkout", "-B", branch], cwd=repo_dir)

    if remote_branch.returncode == 0:
        run_git(["pull", "--ff-only", "origin", branch], cwd=repo_dir, check=False)


def ensure_git_repo(repo_url: str, publish_dir: Path, branch: str = DEFAULT_BRANCH) -> None:
    publish_dir.parent.mkdir(parents=True, exist_ok=True)
    if not (publish_dir / ".git").exists():
        if publish_dir.exists() and any(publish_dir.iterdir()):
            raise StepError(f"{publish_dir} exists but is not an empty git repository.")
        run_git(["clone", repo_url, str(publish_dir)], cwd=publish_dir.parent)

    ensure_git_branch(publish_dir, branch)


def commit_and_push(repo_dir: Path, message: str, branch: str = DEFAULT_BRANCH) -> bool:
    ensure_git_branch(repo_dir, branch)
    run_git(["add", "-A"], cwd=repo_dir)
    diff = run_git(["diff", "--cached", "--quiet"], cwd=repo_dir, check=False)
    if diff.returncode == 0:
        log(f"no git changes: {repo_dir}")
        return False
    run_git(["commit", "-m", message], cwd=repo_dir)
    run_git(["push", "-u", "origin", branch], cwd=repo_dir)
    return True


@contextmanager
def isolated_import(project_dir: Path):
    old_cwd = Path.cwd()
    old_path = list(sys.path)
    old_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "app" or name.startswith("app.")
    }
    for name in list(old_modules):
        sys.modules.pop(name, None)
    os.chdir(project_dir)
    sys.path.insert(0, str(project_dir))
    try:
        yield
    finally:
        for name in [name for name in sys.modules if name == "app" or name.startswith("app.")]:
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)
        sys.path[:] = old_path
        os.chdir(old_cwd)


def load_module(module_name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise StepError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_tree_contents(source: Path, target: Path, exclude: set[str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in exclude:
            continue
        dest = target / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store", "*.pyc"))
        else:
            shutil.copy2(item, dest)


def generate_heatmap(publish: bool) -> dict[str, Any]:
    if not (HEATMAP_DIR / "generate_heatmap.py").exists():
        return {"skipped": True, "reason": "notion_hit/generate_heatmap.py not found"}
    args = [sys.executable, "generate_heatmap.py", "--publish" if publish else "--no-publish"]
    run_command(args, cwd=HEATMAP_DIR)
    return {
        "skipped": False,
        "output": str(HEATMAP_DIR / "qa_heatmap_embed.html"),
        "published": publish,
    }


def generate_hqi(force: bool, publish: bool) -> dict[str, Any]:
    if not (HQI_DIR / "app.py").exists():
        return {"skipped": True, "reason": "HQI/app.py not found"}

    module = load_module("hqi_app_runner", HQI_DIR / "app.py")
    result = module.calculate_and_store_all_projects(force=force)
    payload = module.get_saved_hqi()
    output_path = HQI_DIR / "embed-data.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    published = False
    if publish and (HQI_DIR / ".git").exists():
        timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        published = commit_and_push(HQI_DIR, f"Update HQI dashboard {timestamp}")

    return {
        "skipped": False,
        "updatedCount": result.get("updatedCount", 0),
        "reusedCount": result.get("reusedCount", 0),
        "errorCount": result.get("errorCount", 0),
        "output": str(output_path),
        "published": published,
    }


def notion_post(path: str, payload: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    token = os.getenv("NOTION_TOKEN", "").strip()
    if not token:
        raise StepError("NOTION_TOKEN is required")
    request = urllib.request.Request(
        f"https://api.notion.com/v1{path}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": os.getenv("NOTION_VERSION", NOTION_VERSION),
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def query_monitor_database(page_size: int = 100) -> list[dict[str, Any]]:
    database_id = os.getenv("NOTION_DB_ID", "").strip()
    if not database_id:
        raise StepError("NOTION_DB_ID is required for automation monitor")

    results: list[dict[str, Any]] = []
    payload: dict[str, Any] = {
        "page_size": min(page_size, 100),
        "sorts": [{"timestamp": "last_edited_time", "direction": "descending"}],
    }
    while True:
        data = notion_post(f"/databases/{database_id}/query", payload)
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
    if prop_type == "url":
        return prop.get("url") or ""
    return ""


def number_value(prop: dict[str, Any] | None) -> int:
    try:
        return int(float(plain_text(prop) or 0))
    except ValueError:
        return 0


def first_prop(properties: dict[str, Any], names: list[str]) -> dict[str, Any] | None:
    for name in names:
        if name in properties:
            return properties[name]
    return None


def extract_files(properties: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for prop in properties.values():
        if prop.get("type") != "files":
            continue
        for item in prop.get("files", []):
            file_type = item.get("type")
            url = (item.get(file_type) or {}).get("url") if file_type else None
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
        name, _, status = text[2:].partition(":")
        if status.strip().upper().startswith("FAIL"):
            failed.append({"scenario": scenario, "name": name.strip(), "status": status.strip()})
    return failed


def normalize_monitor_status(status_text: str, fail_count: int) -> str:
    text = status_text.lower()
    if fail_count > 0 or any(token in text for token in ["실패", "fail", "error", "blocked"]):
        return "failed"
    if any(token in text for token in ["running", "진행", "실행중"]):
        return "running"
    if any(token in text for token in ["성공", "완료", "success", "done", "complete"]):
        return "passed"
    return "unknown"


def parse_monitor_page(page: dict[str, Any]) -> dict[str, Any]:
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

    return {
        "id": page.get("id"),
        "url": page.get("url"),
        "title": title,
        "version": version or "unversioned",
        "platform": platform or "WEB",
        "status": normalize_monitor_status(status or test_result, fail_count),
        "statusText": status or test_result,
        "pass": pass_count,
        "fail": fail_count,
        "na": na_count,
        "total": total_count,
        "resultText": result_text,
        "failedItems": extract_failed_items(result_text),
        "snapshots": extract_files(properties),
        "createdAt": created,
        "lastEditedAt": page.get("last_edited_time"),
    }


def generate_monitor(publish: bool, repo_url: str, publish_dir: Path) -> dict[str, Any]:
    if not (MONITOR_DIR / "app" / "main.py").exists():
        return {"skipped": True, "reason": "gohanpass_automation/Monitor/app/main.py not found"}

    with isolated_import(MONITOR_DIR):
        analytics = __import__("app.analytics", fromlist=["build_monitor_payload"])
        payload = analytics.build_monitor_payload(
            [parse_monitor_page(page) for page in query_monitor_database(page_size=100)],
            source="notion",
        )

    output_path = MONITOR_DIR / "app" / "static" / "monitor-data.json"
    root_output_path = MONITOR_DIR / "monitor-data.json"
    encoded_payload = json.dumps(payload, ensure_ascii=False, indent=2)
    output_path.write_text(encoded_payload, encoding="utf-8")
    root_output_path.write_text(encoded_payload, encoding="utf-8")

    published = False
    if publish:
        ensure_git_repo(repo_url, publish_dir)
        copy_tree_contents(
            MONITOR_DIR,
            publish_dir,
            exclude={".env", ".env.example", ".publish", "__pycache__"},
        )
        for legacy_name in ("config.js", "monitor-snapshot.json"):
            legacy_path = publish_dir / legacy_name
            if legacy_path.exists():
                legacy_path.unlink()
        timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        published = commit_and_push(publish_dir, f"Update automation monitor {timestamp}")

    return {
        "skipped": False,
        "source": payload.get("source"),
        "latestVersion": payload.get("kpi", {}).get("latestVersion"),
        "latestStatus": payload.get("kpi", {}).get("latestStatus"),
        "output": str(root_output_path),
        "published": published,
    }


def parse_last_json(output: str) -> dict[str, Any]:
    marker = output.rfind("\n{")
    raw = output[marker + 1 :] if marker >= 0 else output
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def generate_defect_dashboard(publish: bool, days: int) -> dict[str, Any]:
    script = DEFECT_DASHBOARD_DIR / "generate_defect_dashboard.py"
    if not script.exists():
        return {"skipped": True, "reason": "Bug_Dashboard/generate_defect_dashboard.py not found"}
    args = [
        sys.executable,
        "generate_defect_dashboard.py",
        "--days",
        str(days),
        "--publish" if publish else "--no-publish",
    ]
    result = run_command(args, cwd=DEFECT_DASHBOARD_DIR)
    parsed = parse_last_json(result.stdout)
    if parsed:
        return parsed
    return {
        "skipped": False,
        "output": str(DEFECT_DASHBOARD_DIR / "defect_dashboard_embed.html"),
        "published": publish,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all Notion-based dashboards except chatbot, then optionally publish to GitHub."
    )
    parser.add_argument("--skip-heatmap", action="store_true", help="Skip QA heatmap generation.")
    parser.add_argument("--skip-hqi", action="store_true", help="Skip HQI calculation.")
    parser.add_argument("--skip-monitor", action="store_true", help="Skip automation monitor refresh.")
    parser.add_argument("--skip-defect-dashboard", action="store_true", help="Skip defect dashboard generation.")
    parser.add_argument("--force-hqi", action="store_true", help="Recalculate HQI even when saved metadata matches.")
    parser.add_argument("--defect-days", type=int, default=30, choices=[7, 14, 30], help="Defect dashboard trend window.")
    parser.add_argument("--no-publish", action="store_true", help="Generate files locally without git commit/push.")
    parser.add_argument("--monitor-repo-url", default=os.getenv("MONITOR_REPO_URL", DEFAULT_MONITOR_REPO_URL))
    parser.add_argument(
        "--monitor-publish-dir",
        default=os.getenv("MONITOR_PUBLISH_DIR", str(DEFAULT_MONITOR_PUBLISH_DIR)),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    publish = not args.no_publish
    load_all_env()

    summary: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "publish": publish,
        "steps": {},
    }

    steps = [
        ("heatmap", not args.skip_heatmap, lambda: generate_heatmap(publish)),
        ("hqi", not args.skip_hqi, lambda: generate_hqi(args.force_hqi, publish)),
        (
            "monitor",
            not args.skip_monitor,
            lambda: generate_monitor(publish, args.monitor_repo_url, Path(args.monitor_publish_dir)),
        ),
        (
            "defect_dashboard",
            not args.skip_defect_dashboard,
            lambda: generate_defect_dashboard(publish, args.defect_days),
        ),
    ]

    failures: list[dict[str, str]] = []
    for name, enabled, callback in steps:
        if not enabled:
            summary["steps"][name] = {"skipped": True, "reason": "disabled by CLI option"}
            continue
        log(f"start: {name}")
        try:
            summary["steps"][name] = callback()
            log(f"done: {name}")
        except Exception as exc:
            failures.append({"step": name, "error": str(exc) or exc.__class__.__name__})
            summary["steps"][name] = {"failed": True, "error": str(exc) or exc.__class__.__name__}
            log(f"failed: {name}: {exc}")

    summary_path = ROOT / "notion_run_summary.json"
    summary["failures"] = failures
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"summary written: {summary_path}")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
