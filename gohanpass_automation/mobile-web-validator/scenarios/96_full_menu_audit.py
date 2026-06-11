import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from playwright.async_api import Page

from scenarios._auth import ensure_logged_in, has_login_required_popup


scenario_name = Path(__file__).stem
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

HOME_URL = "https://go.hanpass.com"
MAX_MENU_ITEMS = 80

SKIP_KEYWORDS = {
    "로그아웃",
    "회원탈퇴",
    "탈퇴",
    "삭제",
    "초기화",
    "확인",
    "닫기",
    "취소",
    "가상키보드",
    "챗봇",
}


async def log(message: str):
    try:
        logger = getattr(log, "logger", None)
        if logger:
            logger(message)
    except Exception:
        pass


async def step(result: list, name: str, func):
    try:
        await func()
        await log(f"  - {name}: PASS")
        result.append((name, "PASS"))
    except Exception as e:
        await log(f"  - {name}: FAIL ({e})")
        result.append((name, f"FAIL ({e})"))


def normalize_label(value: str) -> str:
    return " ".join((value or "").split())


def is_safe_label(label: str) -> bool:
    if not label:
        return False
    return not any(keyword in label for keyword in SKIP_KEYWORDS)


def css_attr_selector(tag: str, attr: str, value: str) -> str:
    return f"{tag}[{attr}={json.dumps(value)}]"


def safe_step_name(prefix: str, label: str) -> str:
    normalized = normalize_label(label)
    safe = "".join(ch if ch.isalnum() else "_" for ch in normalized)
    safe = "_".join(part for part in safe.split("_") if part)
    return f"{prefix}_{safe[:40] or 'unknown'}"


async def is_logged_in_home(page: Page) -> bool:
    if await has_login_required_popup(page):
        await ensure_logged_in(page)
        return await is_logged_in_home(page)

    selectors = [
        'button:has(img[src*="icon_main_menu.svg"])',
        'button[aria-label="select_region"]',
        'text=한국에서 뭐하지?',
        'button:has(img[alt="여행"])',
        'button:has(img[alt="결제"])',
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            pass
    return False


async def goto_home(page: Page, force_reload: bool = False):
    if not force_reload and "go.hanpass.com" in page.url and await is_logged_in_home(page):
        return

    await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=20000)
    await asyncio.sleep(1.2)

    if await is_logged_in_home(page):
        return

    if await page.get_by_placeholder("이메일").count() > 0:
        raise RuntimeError("로그인 세션이 없습니다. 01_login.py 실행 직후 이어서 실행하세요.")

    if await has_login_required_popup(page):
        await ensure_logged_in(page)
        return

    raise RuntimeError("로그인 홈 화면을 확인하지 못했습니다.")


async def dismiss_service_popup(page: Page) -> bool:
    try:
        popup = page.get_by_text("서비스 준비중입니다.", exact=False)
        if await popup.count() > 0 and await popup.first.is_visible():
            confirm_btn = page.get_by_role("button", name="확인")
            if await confirm_btn.count() > 0:
                await confirm_btn.first.click(timeout=3000)
                await asyncio.sleep(0.8)
                return True
    except Exception:
        pass
    return False


async def close_overlay_if_visible(page: Page) -> bool:
    selectors = [
        'button:has(img[src*="ico18-close.svg"])',
        'button:has(img[src*="close"])',
        'button[aria-label="닫기"]',
        'button[aria-label="close"]',
    ]

    for selector in selectors:
        try:
            target = page.locator(selector).first
            if await target.count() > 0 and await target.is_visible():
                await target.click(timeout=2500)
                await asyncio.sleep(0.8)
                return True
        except Exception:
            pass
    return False


async def open_full_menu(page: Page):
    selectors = [
        'button:has(img[src*="icon_main_menu.svg"])',
        'button:has(img[alt*="메뉴"])',
        'button[aria-label*="menu"]',
        'button[aria-label*="메뉴"]',
    ]

    last_error = None
    for selector in selectors:
        try:
            target = page.locator(selector).first
            if await target.count() == 0:
                continue
            await target.click(timeout=4000)
            await asyncio.sleep(1)
            return
        except Exception as e:
            last_error = e

    raise RuntimeError(f"전체 메뉴 버튼을 찾지 못했습니다: {last_error}")


async def find_scroll_container(page: Page):
    selectors = [
        "[data-radix-scroll-area-viewport]",
        "div.overflow-y-auto",
        'div[class*="overflow-y-auto"]',
        "main",
        "body",
    ]

    for selector in selectors:
        locator = page.locator(selector)
        count = await locator.count()
        for idx in range(count):
            item = locator.nth(idx)
            try:
                if not await item.is_visible():
                    continue
                metrics = await item.evaluate(
                    "(el) => ({ scrollHeight: el.scrollHeight, clientHeight: el.clientHeight })"
                )
                if metrics["scrollHeight"] > metrics["clientHeight"] + 20:
                    return item
            except Exception:
                continue

    return page.locator("body").first


async def collect_visible_menu_items(page: Page, scroll_top: int) -> List[Dict[str, Any]]:
    script = """
    (scrollTop) => {
        const isVisible = (el) => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return (
                style.display !== 'none' &&
                style.visibility !== 'hidden' &&
                style.opacity !== '0' &&
                rect.width > 8 &&
                rect.height > 8 &&
                rect.bottom > 0 &&
                rect.top < window.innerHeight
            );
        };

        const nodes = Array.from(document.querySelectorAll('button, a, [role="button"]'));
        return nodes.filter(isVisible).map((el) => {
            const rect = el.getBoundingClientRect();
            const img = el.querySelector('img');
            return {
                text: (el.innerText || '').trim(),
                aria: (el.getAttribute('aria-label') || '').trim(),
                href: (el.getAttribute('href') || '').trim(),
                alt: img ? (img.getAttribute('alt') || '').trim() : '',
                src: img ? (img.getAttribute('src') || '').trim() : '',
                scrollTop,
                x: rect.x,
                y: rect.y,
                centerX: rect.x + rect.width / 2,
                centerY: rect.y + rect.height / 2,
            };
        });
    }
    """
    return await page.evaluate(script, scroll_top)


def menu_label(item: Dict[str, Any], idx: int) -> str:
    for key in ("text", "aria", "alt", "href"):
        label = normalize_label(item.get(key, ""))
        if label:
            return label[:80]
    return f"menu_item_{idx}"


async def collect_all_menu_items(page: Page) -> List[Dict[str, Any]]:
    await goto_home(page)
    await open_full_menu(page)

    scroll_container = await find_scroll_container(page)
    collected: List[Dict[str, Any]] = []
    seen = set()

    for round_idx in range(12):
        try:
            scroll_top = await scroll_container.evaluate("(el) => el.scrollTop || window.scrollY || 0")
        except Exception:
            scroll_top = round_idx * 700

        for item in await collect_visible_menu_items(page, int(scroll_top)):
            label = menu_label(item, len(collected) + 1)
            if not is_safe_label(label):
                continue
            if "chatbot" in item.get("src", "").lower():
                continue

            key = f"{label}|{item.get('href')}|{item.get('src')}"
            if key in seen:
                continue

            seen.add(key)
            item["label"] = label
            collected.append(item)

        before = scroll_top
        try:
            await scroll_container.evaluate("(el) => el.scrollBy(0, 650)")
        except Exception:
            await page.mouse.wheel(0, 650)
        await asyncio.sleep(0.5)

        try:
            after = await scroll_container.evaluate("(el) => el.scrollTop || window.scrollY || 0")
        except Exception:
            after = before + 650

        if after == before and round_idx >= 2:
            break
        if len(collected) >= MAX_MENU_ITEMS:
            break

    await log(f"전체 메뉴 수집 완료: {len(collected)}개")
    for idx, item in enumerate(collected, 1):
        await log(f"    [{idx:02d}] {item['label']}")

    return collected[:MAX_MENU_ITEMS]


async def click_collected_item(page: Page, item: Dict[str, Any]):
    await goto_home(page)
    await open_full_menu(page)

    scroll_container = await find_scroll_container(page)
    scroll_top = int(item.get("scrollTop", 0))
    try:
        await scroll_container.evaluate("(el, y) => { el.scrollTop = y; }", scroll_top)
    except Exception:
        await page.evaluate("(y) => window.scrollTo(0, y)", scroll_top)
    await asyncio.sleep(0.5)

    label = item["label"]
    locators = []
    if item.get("href"):
        locators.append(page.locator(css_attr_selector("a", "href", item["href"])).first)
    if item.get("aria"):
        locators.append(page.locator(css_attr_selector("*", "aria-label", item["aria"])).first)
    if item.get("text"):
        locators.append(page.get_by_text(item["text"], exact=True).first)
    if item.get("alt"):
        locators.append(page.locator(css_attr_selector("img", "alt", item["alt"])).first)

    for locator in locators:
        try:
            if await locator.count() == 0:
                continue
            await locator.scroll_into_view_if_needed()
            await locator.click(timeout=3000)
            await asyncio.sleep(1)
            return
        except Exception:
            pass

    await page.mouse.click(item["centerX"], item["centerY"])
    await asyncio.sleep(1)


async def inspect_after_click(page: Page, before_url: str, before_text_len: int) -> str:
    after_url = page.url
    try:
        after_text_len = await page.evaluate("() => document.body.innerText.length")
    except Exception:
        after_text_len = before_text_len

    popup_closed = await dismiss_service_popup(page)
    if popup_closed:
        return "서비스 준비중 팝업 확인"

    if before_url != after_url:
        return f"URL 변경: {after_url}"

    if abs(after_text_len - before_text_len) > 30:
        return "화면 내용 변경"

    if await close_overlay_if_visible(page):
        return "레이어/바텀시트 열림"

    return "클릭 가능 여부 확인"


async def recover_home(page: Page):
    if await close_overlay_if_visible(page):
        return

    try:
        await page.go_back(wait_until="domcontentloaded", timeout=5000)
        await asyncio.sleep(0.8)
    except Exception:
        pass

    if "go.hanpass.com" not in page.url:
        await goto_home(page)


async def run(page: Page):
    result = []

    await step(result, "ensure_login", lambda: ensure_logged_in(page))
    await step(result, "open_go_hanpass_home", lambda: goto_home(page))
    menu_items = await collect_all_menu_items(page)

    if not menu_items:
        result.append(("collect_full_menu_items", "FAIL (메뉴 항목 없음)"))
        return result

    result.append(("collect_full_menu_items", f"PASS ({len(menu_items)}개)"))

    for idx, item in enumerate(menu_items, 1):
        label = item["label"]
        step_name = safe_step_name(f"menu_{idx:02d}", label)
        await log(f"▶ 전체 메뉴 확인 시작: {label}")

        try:
            await goto_home(page)
            before_url = page.url
            before_text_len = await page.evaluate("() => document.body.innerText.length")

            await click_collected_item(page, item)
            outcome = await inspect_after_click(page, before_url, before_text_len)
            await log(f"    ↳ {outcome}")
            result.append((step_name, "PASS"))
        except Exception as e:
            await log(f"    ↳ 실패: {e}")
            result.append((step_name, f"FAIL ({e})"))
        finally:
            await recover_home(page)
            await asyncio.sleep(0.5)

    Path("output").mkdir(exist_ok=True)
    await page.screenshot(path=f"output/{scenario_name}_{timestamp}.png")

    return result
