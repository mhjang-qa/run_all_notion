import asyncio
from datetime import datetime
from pathlib import Path
import re
from playwright.async_api import Page

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

    async def click_tab_if_exists(tab_name: str, result_name: str):
        try:
            tab = page.get_by_role("tab", name=re.compile(rf"^{re.escape(tab_name)}"))

            if await tab.count() == 0:
                result.append((result_name, f"N/A ({tab_name} 탭 미노출로 스킵)"))
                return

            target = tab.first

            if not await target.is_visible():
                result.append((result_name, f"N/A ({tab_name} 탭 비노출로 스킵)"))
                return

            if await target.get_attribute("aria-selected") == "false":
                await target.click()

            await asyncio.sleep(1)
            result.append((result_name, "PASS"))

        except Exception as e:
            result.append((result_name, f"FAIL ({str(e)})"))

    async def wait_for_home_travel_section():
        """
        여행 홈 주요 CTA가 다시 보이는지 확인
        """
        candidates = [
            page.get_by_role("button", name="예약내역 보기", exact=True),
            page.get_by_role("button", name="약국", exact=True),
            page.get_by_role("button", name="택시", exact=True),
            page.get_by_role("button", name="Go Card", exact=True),
        ]

        last_error = None
        for locator in candidates:
            try:
                await locator.wait_for(state="visible", timeout=5000)
                return
            except Exception as e:
                last_error = e

        raise RuntimeError(f"여행 홈 영역 복귀 확인 실패: {last_error}")
    
    async def handle_bus_flow():
        """
        버스 클릭 후 동일 탭 외부 이동을 기다리고,
        로딩 완료 후 뒤로가기로 복귀한 다음
        여행 홈 섹션 복귀 여부를 확인한다.
        """
        current_url = page.url

        bus_button = page.get_by_role("button", name="버스", exact=True)
        await bus_button.wait_for(state="visible", timeout=10000)
        await bus_button.click()

        # 1) 동일 탭 URL 변경 또는 확인 버튼 노출 대기
        url_changed = False
        confirm_clicked = False

        for _ in range(15):
            await asyncio.sleep(1)

            if page.url != current_url:
                url_changed = True
                break

            confirm_btn = page.get_by_role("button", name="확인", exact=True)
            try:
                if await confirm_btn.count() > 0 and await confirm_btn.first.is_visible():
                    await confirm_btn.first.click(timeout=5000)
                    await asyncio.sleep(1)
                    confirm_clicked = True
                    break
            except Exception:
                pass

        # 2) URL이 바뀐 경우 외부 페이지 로딩 대기
        if url_changed:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass

            # 필요 시 networkidle까지 추가 시도
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass

            # 뒤로가기
            try:
                await page.go_back(timeout=20000)
            except Exception:
                raise RuntimeError(f"버스 외부 페이지에서 뒤로가기 실패. current_url={page.url}")

        # 3) 팝업형 확인 버튼만 처리된 경우도 원래 홈 복귀 확인
        if not url_changed and not confirm_clicked:
            raise RuntimeError("버스 클릭 후 URL 변경 또는 확인 버튼 노출이 감지되지 않았습니다.")

        # 4) 원래 여행 홈 섹션 복귀 확인
        await wait_for_home_travel_section()












    async def scroll_route_panel_down():
        """
        경로 결과 패널 내부를 아래로 스크롤
        드래그 대신 실제 스크롤 컨테이너를 찾아 scrollBy 처리
        """
        candidate_selectors = [
            "div.overflow-y-auto",
            "div[class*='overflow-y-auto']",
            "[data-radix-scroll-area-viewport]",
            "main div[class*='overflow']",
        ]

        scroll_container = None

        for selector in candidate_selectors:
            locator = page.locator(selector)
            count = await locator.count()
            for i in range(count):
                item = locator.nth(i)
                try:
                    if await item.is_visible():
                        scroll_height = await item.evaluate("(el) => el.scrollHeight")
                        client_height = await item.evaluate("(el) => el.clientHeight")
                        if scroll_height > client_height:
                            scroll_container = item
                            break
                except Exception:
                    continue
            if scroll_container:
                break

        if not scroll_container:
            raise RuntimeError("경로 결과 스크롤 컨테이너를 찾지 못했습니다.")

        for _ in range(2):
            await scroll_container.evaluate("(el) => el.scrollBy(0, 500)")
            await asyncio.sleep(0.6)







    async def drag_bottom_sheet(page: Page, direction: str = "up", distance: int = 260):
        """
        Bottom Sheet 자체를 접거나 펼치는 제스처
        내부 리스트 영역이 아니라 '내 주변 관광지' 텍스트 위 핸들 영역을 기준으로 드래그
        """
        sheet_title = page.locator("text=내 주변 관광지").first
        await sheet_title.wait_for(state="visible", timeout=5000)

        box = await sheet_title.bounding_box()
        if not box:
            raise RuntimeError("Bottom Sheet 헤더 영역을 찾지 못했습니다.")

        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] - 18

        end_y = start_y - distance if direction == "up" else start_y + distance

        await page.mouse.move(start_x, start_y)
        await page.mouse.down()
        await page.mouse.move(start_x, end_y, steps=35)
        await page.mouse.up()
        await asyncio.sleep(1)

    async def scroll_bs_list_down():
        """
        관광지 Bottom Sheet 내부 카드 리스트 스크롤
        BS 자체 드래그와 분리
        """
        scroll_container = page.locator("div.overflow-y-auto.overflow-x-hidden").first
        await scroll_container.wait_for(state="visible", timeout=5000)

        for _ in range(2):
            await scroll_container.evaluate("(el) => el.scrollBy(0, 500)")
            await asyncio.sleep(0.5)

    # 1. 여행 탭 이동
    await page.get_by_role("button").filter(
        has=page.get_by_alt_text("여행")
    ).click()
    await asyncio.sleep(5)

    # 2. 검색 창 선택
    await page.locator("input[placeholder='어디로 갈까요?']").locator("..").click()
    await asyncio.sleep(1)

    # 3. POI 입력
    poi_input = page.locator("input[placeholder='도착지를 입력해주세요.']")
    await poi_input.wait_for(state="visible")
    await poi_input.click()
    await poi_input.fill("")
    await poi_input.type("국립중앙박물관", delay=80)
    await asyncio.sleep(3)

    # 자동완성 리스트 대기 후 첫번째 선택
    await page.locator("text=국립중앙박물관").first.click()
    await asyncio.sleep(3)

    # 3-1. 경로 결과 패널 스크롤
    await step("route_panel_scroll_down", scroll_route_panel_down)
    await asyncio.sleep(1)

    # 3-2. 교통 탭 선택
    await click_tab_if_exists("택시", "taxi_tab_click")
    await click_tab_if_exists("버스", "bus_tab_click")
    await click_tab_if_exists("지하철", "metro_tab_click")

    # 3-3. 뒤로가기
    await step("route_back_click_1", lambda: page.go_back())
    await asyncio.sleep(1)

    await step("route_back_click_2", lambda: page.go_back())
    await asyncio.sleep(1)

    # 4. 맛집 TOP 10
    await page.get_by_role("button", name="맛집 TOP 10").click()
    await asyncio.sleep(2)

    # 4-1. 뒤로가기
    await step("food_top10_back_click", lambda: page.go_back())
    await asyncio.sleep(1)

    # 4-2. 관광지/문화시설
    await page.get_by_role("button", name="관광지/문화시설").click()
    await asyncio.sleep(2)

    # Bottom Sheet 펼치기
    await step(
        "bottom_sheet_drag_up",
        lambda: drag_bottom_sheet(page, direction="up", distance=240)
    )
    await asyncio.sleep(1)

    # Bottom Sheet 내부 리스트 스크롤
    await step("tour_bs_list_scroll_down", scroll_bs_list_down)
    await asyncio.sleep(1)

    # Bottom Sheet 접기
    await step(
        "bottom_sheet_drag_down",
        lambda: drag_bottom_sheet(page, direction="down", distance=280)
    )
    await asyncio.sleep(1)

    await step("tour_back_click", lambda: page.go_back())
    await asyncio.sleep(1)

    # 4-3. 약국
    await step(
        "pharmacy_click",
        lambda: page.get_by_role("button", name="약국", exact=True).click()
    )
    await asyncio.sleep(1)

    await step("pharmacy_back_click", lambda: page.go_back())
    await asyncio.sleep(1)

    # 5-1. 택시
    await step(
        "taxi_click",
        lambda: page.get_by_role("button", name="택시", exact=True).click()
    )
    await asyncio.sleep(1)
    
    #5-1. 택시 bs닫기 
    await step(
        "Taxi_BS_closed_click",
        lambda: page.locator(
            "button:has(img[src*='ico18-close.svg'])"
        ).click()
    )
    await asyncio.sleep(1)
    
    # 5-2. ktx
    await step(
        "ktx_click",
        lambda: page.get_by_role("button", name="KTX", exact=True).click()
    )
    await asyncio.sleep(1)
    
    # 5-2. ktx 팝업 닫기
    await step(
        "ktx_popup_closed_click",
        lambda: page.get_by_role("button", name="확인", exact=True).click()
    )
    await asyncio.sleep(1)
    
    # 5-3. 버스

    await step("bus_flow_handle", handle_bus_flow)
    await asyncio.sleep(1)
    
    # 5-4. 예약 내역 보기
    await step(
        "My_Bookings_click",
        lambda: page.get_by_role("button", name="예약내역 보기", exact=True).click()
    )
    await asyncio.sleep(1)
    await step("My_Bookings_back_click", lambda: page.go_back())
    await step("My_Bookings_back_click", lambda: page.go_back())
    await asyncio.sleep(1)
    
    # 6.교통카드 + USIM
    await step(
        "Transit-enabled_SIM_click",
        lambda: page.get_by_role("button", name="신청하기", exact=True).click()
    )
    await asyncio.sleep(1)
    await step("Transit-enabled_SIM_back_click", lambda: page.go_back())
    await asyncio.sleep(1)
    
    # 6-1. GO card
    await step(
        "gocard_click",
        lambda: page.get_by_role("button", name="Go Card", exact=True).click()
    )
    await asyncio.sleep(1)
    await step("Go Card_back_click", lambda: page.go_back())
    await asyncio.sleep(1)
     
    #아래로 스크롤
    await page.evaluate("window.scrollBy(0, 800)")
    await asyncio.sleep(1)
    
        

    # 99. 홈 복귀 검증
    async def check_home_success():
        try:
            await page.wait_for_selector("button[aria-label='select_region']", timeout=8000)
        except Exception:
            await page.wait_for_selector("text=한국에서 뭐하지?", timeout=3000)

    await step("home_result_check", check_home_success)

    # 스크린샷
    await page.screenshot(path=f"output/{scenario_name}_{timestamp}.png")

    return result
