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
        'button:has(img[alt="여행"])',
        'button:has(img[alt="결제"])',
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


async def open_travel_tab(page: Page):
    selectors = [
        'button:has(img[alt="여행"])',
        'div.fixed.bottom-0 button:has(img[alt="여행"])',
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

    raise RuntimeError(f"여행 탭 클릭 실패: {last_error}")


async def safe_back_to_travel(page: Page, home_url: str):
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
    await open_travel_tab(page)


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


TRAVEL_TARGETS: List[Tuple[str, List[str]]] = [
    (
        "검색 입력영역",
        [
            'input[placeholder="어디로 갈까요?"]',
            'div:has(input[placeholder="어디로 갈까요?"])',
            'text=어디로 갈까요?',
        ],
    ),
    ("맛집 TOP 10", ['text_exact=맛집 TOP 10']),
    ("관광지/문화시설", ['text_exact=관광지/문화시설']),
    ("약국 키워드", ['text_exact=약국']),
    ("병원/응급실 키워드", ['text_exact=병원/응급실']),
    ("자전거", ['text_exact=자전거']),
    ("더보기", ['text_exact=더보기']),
    ("택시", ['text_exact=택시']),
    ("KTX", ['text_exact=KTX']),
    ("버스", ['text_exact=버스']),
    ("예약내역 보기", ['text_exact=예약내역 보기']),
    ("신청하기", ['text_exact=신청하기']),
    ("Go Card", ['text_exact=Go Card']),
    ("공공자전거 대여 현황", ['text_exact=공공자전거 대여 현황']),
    ("병원/응급실 대여정보", ['text=병원/응급실']),
    ("약국 대여정보", ['text=약국']),
    ("축제 전체보기", ['text_exact=전체보기']),
]


async def run(page: Page):
    result = []
    home_url = "https://go.hanpass.com"

    await step(result, "ensure_login", lambda: ensure_logged_in(page))
    await step(result, "open_home", lambda: goto_home(page, home_url))
    await step(result, "open_travel_tab", lambda: open_travel_tab(page))

    for label, selectors in TRAVEL_TARGETS:
        async def check_travel_target(target_label=label, target_selectors=selectors):
            await log(f"    · 여행탭 클릭 시도: {target_label}")

            await goto_home(page, home_url)
            await open_travel_tab(page)

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

            await safe_back_to_travel(page, home_url)
            await asyncio.sleep(0.8)

        await step(result, f"travel_menu_{label}", check_travel_target)

    return result
