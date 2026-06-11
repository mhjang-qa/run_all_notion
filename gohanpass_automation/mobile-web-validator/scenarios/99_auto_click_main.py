import asyncio
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

from playwright.async_api import Page

from scenarios._auth import ensure_logged_in

scenario_name = Path(__file__).stem
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


# =========================
# LOGGER (GUI 연결용)
# =========================
async def log(message: str):
    try:
        logger = getattr(log, "logger", None)
        if logger:
            logger(message)
    except Exception:
        pass


# =========================
# FILTER 조건
# =========================
EXCLUDE_ARIA = {
    "챗봇", "가상키보드", "닫기", "초기화", "한개지움",
    "입력완료", "확인", "재배열", "대문자변환",
    "대문자고정", "소문자변환", "특수문자변환", "공백",
}

EXCLUDE_ALT = {"챗봇"}
EXCLUDE_TEXT_EXACT = {"", "닫기", "초기화", "한개지움", "입력완료", "확인", "재배열"}
EXCLUDE_TEXT_CONTAINS = {"가상키패드"}


# =========================
# STEP
# =========================
async def step(result: list, name: str, func):
    try:
        await func()
        await log(f"  - {name}: PASS")
        result.append((name, "PASS"))
    except Exception as e:
        await log(f"  - {name}: FAIL ({e})")
        result.append((name, "FAIL"))


# =========================
# POPUP
# =========================
async def dismiss_service_popup(page: Page) -> bool:
    try:
        popup = page.get_by_text("서비스 준비중입니다.", exact=False)
        if await popup.count() > 0 and await popup.first.is_visible():
            btn = page.get_by_role("button", name="확인")
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(0.8)
                return True
    except Exception:
        pass
    return False


# =========================
# CLICKABLE 수집
# =========================
async def get_visible_clickables(page: Page) -> List[Dict[str, Any]]:
    script = """
    () => {
        const isVisible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                style.opacity !== '0' &&
                rect.width > 0 &&
                rect.height > 0
            );
        };

        const elements = Array.from(document.querySelectorAll('button, a, [role="button"]'));
        const result = [];

        for (const el of elements) {
            if (!isVisible(el)) continue;

            const rect = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            const aria = (el.getAttribute('aria-label') || '').trim();
            const href = (el.getAttribute('href') || '').trim();

            const img = el.querySelector('img');
            const alt = img ? (img.getAttribute('alt') || '') : '';
            const src = img ? (img.getAttribute('src') || '') : '';

            result.push({
                text, aria, href, alt, src,
                x: rect.x, y: rect.y,
                width: rect.width, height: rect.height,
                centerX: rect.x + rect.width / 2,
                centerY: rect.y + rect.height / 2
            });
        }
        return result;
    }
    """

    raw = await page.evaluate(script)

    filtered = []
    seen = set()

    for item in raw:
        text = item.get("text", "")
        aria = item.get("aria", "")
        alt = item.get("alt", "")
        src = item.get("src", "")

        if aria in EXCLUDE_ARIA:
            continue
        if alt in EXCLUDE_ALT:
            continue
        if text in EXCLUDE_TEXT_EXACT:
            continue
        if any(k in text for k in EXCLUDE_TEXT_CONTAINS):
            continue
        if "chatbot" in src:
            continue

        key = f"{text}|{aria}|{item.get('href')}|{item.get('x')}"
        if key in seen:
            continue
        seen.add(key)

        filtered.append(item)

    filtered.sort(key=lambda x: (x["y"], x["x"]))
    return filtered


def make_label(item: Dict[str, Any], idx: int):
    return item.get("text") or item.get("aria") or item.get("alt") or f"clickable_{idx}"


# =========================
# CLICK
# =========================
async def safe_click(page: Page, item: Dict[str, Any]):
    text = item.get("text")
    aria = item.get("aria")
    href = item.get("href")
    alt = item.get("alt")

    if href:
        loc = page.locator(f'a[href="{href}"]').first
        if await loc.count():
            await loc.click()
            return

    if aria:
        loc = page.locator(f'[aria-label="{aria}"]').first
        if await loc.count():
            await loc.click()
            return

    if text:
        loc = page.get_by_text(text, exact=True).first
        if await loc.count():
            await loc.click()
            return

    if alt:
        loc = page.locator(f'img[alt="{alt}"]').first
        if await loc.count():
            await loc.click()
            return

    await page.mouse.click(item["centerX"], item["centerY"])


# =========================
# BACK
# =========================
async def safe_back(page: Page, home_url: str):
    try:
        await page.go_back()
        await asyncio.sleep(1)
        return
    except:
        pass

    await page.goto(home_url)
    await asyncio.sleep(1)


# =========================
# MAIN
# =========================
async def run(page: Page):
    result = []
    home_url = "https://go.hanpass.com"

    await step(result, "ensure_login", lambda: ensure_logged_in(page))
    await step(result, "open_url", lambda: page.goto(home_url))
    await asyncio.sleep(2)

    items = await get_visible_clickables(page)
    await log(f"수집된 클릭 후보: {len(items)}개")

    for i, item in enumerate(items, 1):
        label = make_label(item, i)

        async def check_click_target(target=item, target_label=label):
            await log(f"    · 클릭 시도: {target_label}")

            await page.goto(home_url)
            await asyncio.sleep(1)

            before_url = page.url
            before_len = await page.evaluate("() => document.body.innerText.length")

            await safe_click(page, target)
            await asyncio.sleep(0.5)

            after_url = page.url
            after_len = await page.evaluate("() => document.body.innerText.length")

            if before_url != after_url:
                await log("      ↳ URL 변경")
                await asyncio.sleep(1)

            popup = await dismiss_service_popup(page)
            if popup:
                await log("      ↳ 팝업 처리")
                await asyncio.sleep(1)

            elif abs(after_len - before_len) > 30:
                await log("      ↳ DOM 변경")
                await asyncio.sleep(1)

            await safe_back(page, home_url)

        safe_label = "".join(ch if ch.isalnum() else "_" for ch in label)[:40] or f"target_{i}"
        await step(result, f"main_click_{i:02d}_{safe_label}", check_click_target)

    return result
