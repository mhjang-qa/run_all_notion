import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import Page

from scenarios._auth import ensure_logged_in

scenario_name = Path(__file__).stem
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

async def run(page):
    result = []

    # 공통 유틸
    async def step(name, func):
        try:
            await func()
            result.append((name, "PASS"))
        except Exception as e:
            result.append((name, f"FAIL ({str(e)})"))

    


    async def dismiss_service_popup(page: Page) -> bool:
        try:
            popup_text = page.get_by_text("서비스 준비중입니다.", exact=False)
            if await popup_text.count() > 0 and await popup_text.first.is_visible():
                confirm_btn = page.get_by_role("button", name="확인")
                if await confirm_btn.count() > 0:
                    await confirm_btn.first.click()
                    await asyncio.sleep(0.8)
                    return True
        except Exception:
            pass
        return False

    async def has_login_required_popup() -> bool:
        popup = page.get_by_text("로그인 후 이용해주세요.", exact=False)
        try:
            return await popup.count() > 0 and await popup.first.is_visible()
        except Exception:
            return False

    async def assert_no_login_required_popup():
        if await has_login_required_popup():
            await ensure_logged_in(page)

    async def has_auth_storage() -> bool:
        storage = await page.evaluate(
            """
            () => {
                const collect = (store) => {
                    const items = [];
                    for (let i = 0; i < store.length; i += 1) {
                        const key = store.key(i);
                        items.push(`${key}=${store.getItem(key)}`);
                    }
                    return items;
                };
                return [...collect(localStorage), ...collect(sessionStorage)].join("\\n");
            }
            """
        )
        lowered = storage.lower()
        if any(
            keyword in lowered
            for keyword in ["token", "access", "refresh", "auth", "session", "member", "user"]
        ):
            return True

        cookies = await page.context.cookies("https://go.hanpass.com")
        cookie_text = "\n".join(f"{item.get('name')}={item.get('value')}" for item in cookies)
        lowered = cookie_text.lower()
        return any(
            keyword in lowered
            for keyword in ["token", "access", "refresh", "auth", "session", "member", "user"]
        )

    async def verify_protected_menu_access():
        selectors = [
            'button:has(img[alt="결제"])',
            'div.fixed.bottom-0 button:has(img[alt="결제"])',
        ]

        last_error = None
        for selector in selectors:
            try:
                target = page.locator(selector).last
                if await target.count() == 0:
                    continue
                await target.click(timeout=4000)
                await asyncio.sleep(1.5)
                await assert_no_login_required_popup()
                return
            except Exception as e:
                last_error = e

        raise Exception(f"로그인 보호 메뉴 접근 확인 실패: {last_error}")
    async def click_keypad_char(ch: str):
        selector = f"button[nfiltercode='{ch}']"
        await page.wait_for_selector(selector, timeout=5000)
        await page.locator(selector).first.click()

    async def click_keypad_command(command: str):
        command_map = {
            "shift": "#nfilter_shift_l, #nfilter_shift_u, #nfilter_shift_s",
            "backspace": "#nfilter_backspace",
            "renew": "#nfilter_renew",
            "special": "#nfilter_lower2special, #nfilter_upper2special",
            "char": "#nfilter_change_char",
            "clear": "#nfilter_clear",
        }

        if command not in command_map:
            raise Exception(f"지원하지 않는 command: {command}")

        await page.locator(command_map[command]).first.click()

    async def enter_password_by_keypad(password: str):
        for ch in password:
            if ch.islower() or ch.isdigit() or ch == " ":
                await click_keypad_char(ch)

            elif ch.isupper():
                await click_keypad_command("shift")
                await click_keypad_char(ch)

            elif ch in "!@#$%^&*()~-_=+|[]{};:,.?/<>":
                await click_keypad_command("special")
                await click_keypad_char(ch)
                await click_keypad_command("char")

            else:
                raise Exception(f"지원하지 않는 문자: {ch}")

            await asyncio.sleep(0.2)

    # 1. URL 접속
    await step("open_url", lambda: page.goto("https://go.hanpass.com"))
    
    await asyncio.sleep(3)

    # 2. title 확인
    async def check_title():
        title = await page.title()
        if not title:
            raise Exception("title 없음")

    await step("title_check", check_title)

    # 3. 로그인 진입 버튼 클릭
    await page.locator(
        "button:has(img[src*='ico16-btn-arrow-right-grayscale-05.svg'])"
    ).click()

    await asyncio.sleep(3)

    # 4. 이메일 입력
    await step(
        "email_input",
        lambda: page.locator("input[placeholder='이메일']").type(
            "hanpassqa5@gmail.com",
            delay=80  # ms (사람처럼 입력)
        )
    )

    await asyncio.sleep(2)

    # 5. 비밀번호 입력창 클릭
    await step(
        "password_input_click",
        lambda: page.get_by_placeholder("비밀번호").click()
    )

    await asyncio.sleep(2)

    # 6. 비밀번호 키패드 입력
    async def password_keypad_input():
        await enter_password_by_keypad("xptmxm123!")

    await step("password_keypad_input", password_keypad_input)

    await asyncio.sleep(2)

    # 7. 확인 버튼 클릭
    async def confirm_click():
        confirm_btn = page.locator("button.bg-primary.text-white.w-full:has-text('확인')")
        await confirm_btn.wait_for(state="visible", timeout=5000)
        await confirm_btn.click()

    await step("confirm_click", confirm_click)
    await asyncio.sleep(4)

    # 8. 결과 존재 확인
    async def check_login_success():
        await assert_no_login_required_popup()

        if await page.get_by_placeholder("이메일").count() > 0:
            raise Exception("로그인 입력 화면이 남아있습니다.")

        try:
            await page.wait_for_selector("button[aria-label='select_region']", timeout=5000)
        except Exception:
            await page.wait_for_selector("text=한국에서 뭐하지?", timeout=3000)

        await verify_protected_menu_access()
        await has_auth_storage()

    await step("login_result_check", check_login_success)

    # 스크린샷
    await page.screenshot(path=f"output/{scenario_name}_{timestamp}.png")



    return result
