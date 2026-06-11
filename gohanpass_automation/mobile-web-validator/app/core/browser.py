from playwright.async_api import async_playwright


async def create_browser():
    p = await async_playwright().start()

    browser = await p.chromium.launch(
        headless=False,
        args=[
            "--window-size=500,920",
            "--window-position=80,60",
            "--force-device-scale-factor=1",
            "--disable-features=TranslateUI",
            "--lang=ko-KR",
            "--disable-translate",
            "--no-first-run",
        ],
    )

    context = await browser.new_context(
        viewport={"width": 500, "height": 812},
        screen={"width": 500, "height": 812},
        is_mobile=True,
        has_touch=True,
        device_scale_factor=1,
        permissions=["geolocation"],
        geolocation={"latitude": 37.5665, "longitude": 126.9780},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 12; Pixel 5) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Mobile Safari/537.36"
        ),
        extra_http_headers={
            "Accept-Language": "ko-KR,ko;q=0.9"
        },
    )

    await context.grant_permissions(
        ["geolocation"],
        origin="https://go.hanpass.com",
    )

    page = await context.new_page()
    return p, browser, context, page