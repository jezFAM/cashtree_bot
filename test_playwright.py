#!/usr/bin/env python3
"""
Playwright를 사용한 테스트 - 실제 브라우저로 봇 감지 우회
"""
import asyncio
from playwright.async_api import async_playwright

async def test_with_playwright():
    """Playwright를 사용한 실제 브라우저 테스트"""
    url = "https://smartstore.naver.com/bkbk4470/products/500680413"

    print(f"요청 URL: {url}")
    print("Playwright (실제 Chromium 브라우저)를 사용\n")

    async with async_playwright() as p:
        try:
            # Chromium 브라우저 실행 (headless 감지 우회 설정)
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',  # 자동화 플래그 숨기기
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )

            # 새로운 컨텍스트 생성 (실제 브라우저 환경 시뮬레이션)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='ko-KR',
                ignore_https_errors=True,  # SSL 인증서 오류 무시
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Sec-CH-UA': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                    'Sec-CH-UA-Mobile': '?0',
                    'Sec-CH-UA-Platform': '"Windows"',
                }
            )

            # navigator.webdriver를 undefined로 설정하여 자동화 감지 우회
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            # 새 페이지 생성
            page = await context.new_page()

            # 먼저 네이버 메인 페이지 방문 (쿠키 획득)
            print("네이버 메인 페이지 방문 중...")
            await page.goto('https://www.naver.com', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)  # 잠시 대기

            print(f"스마트스토어 페이지 방문 중...\n")
            # 페이지 이동
            response = await page.goto(url, wait_until='domcontentloaded', timeout=30000)

            status = response.status
            print(f"응답 상태 코드: {status}")

            if status == 200:
                print("\n✓ 성공! 200 응답을 받았습니다!")

                # 페이지 내용 가져오기
                content = await page.content()
                print(f"응답 내용 길이: {len(content)} bytes")
                print(f"\n응답 내용 일부:\n{content[:500]}...")
            else:
                print(f"\n✗ 실패! {status} 응답을 받았습니다.")
                content = await page.content()
                print(f"응답 내용:\n{content[:1000]}")

            await browser.close()

        except Exception as e:
            print(f"\n오류 발생: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_with_playwright())
