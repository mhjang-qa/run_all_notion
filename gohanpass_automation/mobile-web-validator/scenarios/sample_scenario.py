# 반드시 async run(page) 형태

async def run(page):
    result = []

    # 1. URL 접속
    await page.goto("https://dev-go.hanpass.com")

    # 2. title 확인
    title = await page.title()
    result.append(("title_check", "PASS" if title else "FAIL"))

    # 3. body 존재 확인
    body = await page.query_selector("body")
    result.append(("body_check", "PASS" if body else "FAIL"))

    # 4. 스크린샷
    await page.screenshot(path="output/sample.png")
    
    print("⏸ 화면 확인 후 Enter 누르면 종료")
    input()

    return result