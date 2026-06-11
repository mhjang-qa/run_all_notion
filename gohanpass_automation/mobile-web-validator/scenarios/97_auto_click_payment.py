import asyncio
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

from playwright.async_api import Page

from scenarios._auth import ensure_logged_in


scenario_name = Path(__file__).stem
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


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
        result.append((name, "FAIL"))


async def dismiss_service_popup(page: Page) -> bool:
    try:
        popup = page.get_by_text("서비스 준비중입니다.", exact=False)
        if await popup.count() > 0 and await popup.first.is_visible():
            confirm_btn = page.get_by_role("button", name="확인")
            if await confirm_btn.count() > 0:
                await confirm_btn.first.click()
                await asyncio.sleep(1)
                return True
    except Exception:
        pass
    return False


async def assert_authenticated(page: Page):
    popup = page.get_by_text("로그인 후 이용해주세요.", exact=False)
    try:
        if await popup.count() > 0 and await popup.first.is_visible():
            close_btn = page.get_by_role("button", name="닫기")
            if await close_btn.count() > 0:
                await close_btn.first.click(timeout=2000)
            await ensure_logged_in(page)
            return
    except RuntimeError:
        raise
    except Exception:
        pass

    if await page.get_by_placeholder("이메일").count() > 0:
        await ensure_logged_in(page)


async def is_home_ready(page: Page) -> bool:
    if "go.hanpass.com" not in page.url:
        return False

    selectors = [
        'button:has(img[alt="결제"])',
        'button:has(img[alt="여행"])',
        'button[aria-label="select_region"]',
        'text=한국에서 뭐하지?',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            pass
    return False


async def goto_home(page: Page, home_url: str):
    await assert_authenticated(page)
    if await is_home_ready(page):
        return

    await page.goto(home_url, wait_until="domcontentloaded")
    await asyncio.sleep(1.5)
    await assert_authenticated(page)


async def open_payment_tab(page: Page):
    selectors = [
        'button:has(img[alt="결제"])',
        'div.fixed.bottom-0 button:has(img[alt="결제"])',
    ]

    last_error = None

    for selector in selectors:
        try:
            loc = page.locator(selector).last
            if await loc.count() == 0:
                continue

            await loc.scroll_into_view_if_needed()
            await asyncio.sleep(0.3)

            try:
                await loc.click(timeout=3000)
            except Exception:
                await loc.click(timeout=3000, force=True)

            await asyncio.sleep(1.5)
            await assert_authenticated(page)
            return
        except Exception as e:
            last_error = e

    raise RuntimeError(f"결제 탭 클릭 실패: {last_error}")


async def safe_back_to_payment(page: Page, home_url: str):
    back_selectors = [
        'button:has(img[alt="back"])',
        'button:has(img[src*="back"])',
        'button[aria-label="뒤로가기"]',
        'button[aria-label="back"]',
        'button[aria-label="닫기"]',
    ]

    for selector in back_selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count():
                await loc.click(timeout=2000)
                await asyncio.sleep(1)
                return
        except Exception:
            pass

    try:
        await page.go_back(wait_until="domcontentloaded", timeout=5000)
        await asyncio.sleep(1)
        return
    except Exception:
        pass

    await goto_home(page, home_url)
    await open_payment_tab(page)


async def click_target(page: Page, label: str, selectors: List[str]) -> None:
    last_error = None

    for selector in selectors:
        try:
            if selector.startswith("text_exact="):
                target = page.get_by_text(selector.replace("text_exact=", ""), exact=True).first
            elif selector.startswith("text="):
                target = page.get_by_text(selector.replace("text=", ""), exact=False).first
            else:
                target = page.locator(selector).first

            if await target.count() == 0:
                continue

            await target.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)

            try:
                await target.click(timeout=4000)
                return
            except Exception:
                pass

            try:
                await target.click(timeout=4000, force=True)
                return
            except Exception:
                pass

            handle = await target.element_handle()
            if handle:
                await page.evaluate("(el) => el.click()", handle)
                await asyncio.sleep(0.5)
                return

        except Exception as e:
            last_error = e

    raise RuntimeError(f"{label} 클릭 실패: {last_error}")


PAYMENT_TARGETS: List[Tuple[str, List[str]]] = [
    ("충전", ['text_exact=충전']),
    ("출금", ['text_exact=출금']),
    ("내역", ['text_exact=내역']),
    ("송금", ['text_exact=송금']),
    ("올리브영", ['text_exact=올리브영']),
    ("GS25", ['text_exact=GS25']),
    ("다이소", ['text_exact=다이소']),
    ("설빙", ['text_exact=설빙']),
    ("공차", ['text_exact=공차']),
    ("아트박스", ['text_exact=아트박스']),
    ("모두 보기", ['text_exact=모두 보기']),
    ("GO Hanpass Card", ['text_exact=GO Hanpass Card']),
    ("카드 신청", ['text_exact=신청']),
    ("K-Style PICK 전체보기", ['text_exact=전체보기']),
]


async def run(page: Page):
    result = []
    home_url = "https://go.hanpass.com"

    await step(result, "ensure_login", lambda: ensure_logged_in(page))
    await step(result, "open_home", lambda: goto_home(page, home_url))
    await step(result, "open_payment_tab", lambda: open_payment_tab(page))

    for label, selectors in PAYMENT_TARGETS:
        async def check_payment_target(target_label=label, target_selectors=selectors):
            await log(f"    · 결제탭 클릭 시도: {target_label}")

            await goto_home(page, home_url)
            await open_payment_tab(page)

            before_url = page.url
            before_len = await page.evaluate("() => document.body.innerText.length")

            await click_target(page, target_label, target_selectors)
            await asyncio.sleep(0.8)
            await assert_authenticated(page)

            after_url = page.url
            after_len = await page.evaluate("() => document.body.innerText.length")

            if before_url != after_url:
                await log("      ↳ 페이지 이동 감지 (URL 변경)")
                await asyncio.sleep(1)

            popup_closed = await dismiss_service_popup(page)
            if popup_closed:
                await log("      ↳ 서비스 준비중 팝업 확인 클릭")
                await asyncio.sleep(1)

            elif abs(after_len - before_len) > 20:
                await log("      ↳ 화면 변화 감지 (DOM)")
                await asyncio.sleep(1)

            await safe_back_to_payment(page, home_url)
            await asyncio.sleep(0.8)

        await step(result, f"payment_menu_{label}", check_payment_target)

    return result
