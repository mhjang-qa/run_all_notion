import asyncio
from datetime import datetime
from pathlib import Path

from scenarios._auth import ensure_logged_in

scenario_name = Path(__file__).stem
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

async def run(page):
    result = []

    async def step(name, func):
        try:
            await func()
            result.append((name, "PASS"))
        except Exception as e:
            result.append((name, f"FAIL ({str(e)})"))

    await step("ensure_login", lambda: ensure_logged_in(page))

    async def select_region(region_name: str):
        # 지역 선택 버튼 (명확하게 1개만 잡기)
        await page.get_by_role("button", name="지역 선택").click()
        await asyncio.sleep(0.5)

        # 바텀시트 내부에서만 선택
        region_sheet = page.locator("div.flex.flex-col.gap-18")
        await region_sheet.get_by_text(region_name, exact=True).click()
        await asyncio.sleep(0.5)

    # 1. 위치 버튼 선택
    await step(
        "region_open_click",
        lambda: page.locator(
            "button:has(img[src*='ico16-btn-arrow-down2.svg'])"
        ).click()
    )
    await asyncio.sleep(1)

    # 1-1. 위치 바텀시트 닫기
    await step(
        "region_close_click",
        lambda: page.locator(
            "button:has(img[src*='ico18-close.svg'])"
        ).click()
    )
    await asyncio.sleep(1)

    # 2. 날씨 화면 진입
    await step(
        "weather_click",
        lambda: page.locator("button:has-text('℃')").first.click()
    )
    await asyncio.sleep(2)

    # 2-1. 아래로 스크롤
    async def scroll_down():
        for _ in range(3):
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(0.3)

    await step("scroll_down", scroll_down)
    await asyncio.sleep(1)

    # 2-2. 위로 스크롤
    async def scroll_up():
        for _ in range(2):
            await page.mouse.wheel(0, -800)
            await asyncio.sleep(0.2)

    await step("scroll_up", scroll_up)
    await asyncio.sleep(1)
    
    # 2-3. 지역선택 아이콘 선택
    for region in ["서울", "인천", "부산"]:
        await step(
            f"select_region_{region}",
            lambda r=region: select_region(r)
        )
    await asyncio.sleep(1)
    

    # 2-9. 뒤로가기
    await step(
        "back_click",
        lambda: page.locator(
            "button:has(img[src*='ico24-back.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
    
    # 3. 전체 메뉴 진입
    await step(
        "menu_open_click",
        lambda: page.locator(
            "button:has(img[src*='icon_main_menu.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
    
    # 3-1. 아래로 스크롤
    async def scroll_down():
        for _ in range(3):
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(0.3)

    await step("scroll_down", scroll_down)
    await asyncio.sleep(1)

    # 3-2. 위로 스크롤
    async def scroll_up():
        for _ in range(2):
            await page.mouse.wheel(0, -800)
            await asyncio.sleep(0.2)

    await step("scroll_up", scroll_up)
    await asyncio.sleep(1)
    
    # 3-3. 고객센터 이동
    await step(
        "Customer_Service_open_click",
        lambda: page.locator(
            "button:has(img[src*='ico24_headphones.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
    # 3-9. 고객센터 에서 뒤로가기
    await step(
        "memu_back_click",
        lambda: page.locator(
            "button:has(img[src*='ico24-back.svg'])"
        ).click()
    )
    await asyncio.sleep(1)

    # 4. 푸시 노티 알림 확인
    await step(
        "push_noti_click",
        lambda: page.locator(
            "button:has(img[src*='ico20-caution-light-gray.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
    
    # 4-9. 푸시 알림 뒤로가기
    await step(
        "menu_back_click",
        lambda: page.go_back()
    )
    await asyncio.sleep(1)
    
    # 5. 월렛 bs 확인
    await step(
        "memu_back_click",
        lambda: page.locator(
            "button:has(img[src*='ico16-line-info.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
    # 5-1. bs 닫기
    await step(
        "memu_back_click",
        lambda: page.locator(
            "button:has(img[src*='ico18-close.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
    
    # 3-1. 아래로 스크롤
    async def scroll_down():
        for _ in range(3):
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(0.3)

    await step("main_scroll_down", scroll_down)
    await asyncio.sleep(1)
    
    # 6. 추천여행지 가로 롤링 배너우측 스와이프
    async def swipe_banner_right():
        banner = page.locator("div.overflow-x-auto.scroll-hidden").first
        await banner.evaluate("(el) => el.scrollBy({ left: 220, behavior: 'smooth' })")
        await asyncio.sleep(1)

    await step("banner_swipe_right", swipe_banner_right)
    async def swipe_banner_left():
        banner = page.locator("div.overflow-x-auto.scroll-hidden").first
        await banner.evaluate("(el) => el.scrollBy({ left: -220, behavior: 'smooth' })")
        await asyncio.sleep(1)

    await step("banner_swipe_left", swipe_banner_left)
    
    #7. 교통카드 충전
    await step(
        "Top_Up_Transit_Card_click",
        lambda: page.locator(
            "button:has(img[src*='transport-img-01@4x.png'])"
        ).click()
    )
    await asyncio.sleep(1)
    
    #7-1. 교통카드 충전 bs 닫기
    await step(
        "Top_Up_Transit_Card_BS_closed_click",
        lambda: page.locator(
            "button:has(img[src*='ico18-close.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
  
   
    #8. 텍시
    await step(
        "taxi_click",
        lambda: page.locator(
            "button:has(img[src*='transport-img-02@4x.png'])"
        ).click()
    )
    await asyncio.sleep(1)
    
    #8-1. 택시 bs 닫기
    await step(
        "Top_Up_Transit_Card_BS_closed_click",
        lambda: page.locator(
            "button:has(img[src*='ico18-close.svg'])"
        ).click()
    )
    await asyncio.sleep(1)

    #9. 버스
    await step(
        "bus_click",
        lambda: page.locator(
            "button:has(img[src*='transport-img-04@4x.png'])"
        ).click()
    )
    await asyncio.sleep(3)
    
    #9-1. 버스 뒤로 가기
    await step(
        "menu_back_click",
        lambda: page.go_back()
    )
    await asyncio.sleep(1)
    
    #10. 여행 컨텐츠 더보기
    await page.get_by_role("button", name="여행 컨텐츠 더보기").click()
    await asyncio.sleep(1)
    
    #10-1. 한국에서 뭐하지 bs 닫기
    await step(
        "BS_closed_click",
        lambda: page.locator(
            "button:has(img[src*='ico18-close.svg'])"
        ).click()
    )
    await asyncio.sleep(1)


    # 99. 홈 복귀 검증
    async def check_home_success():
        try:
            await page.wait_for_selector("button[aria-label='select_region']", timeout=8000)
        except Exception:
            await page.wait_for_selector("text=한국에서 뭐하지?", timeout=3000)

    await step("home_result_check", check_home_success)

    # 4. 스크린샷
    await page.screenshot(path=f"output/{scenario_name}_{timestamp}.png")

    return result
