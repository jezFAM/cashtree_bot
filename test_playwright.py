#!/usr/bin/env python3
"""
Playwright를 사용한 네이버 스마트스토어 봇 감지 우회 테스트 스크립트
"""

import asyncio
import traceback
from typing import Dict, Tuple
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def fetch_with_playwright(url: str, user_agent: str = None) -> Tuple[str, int]:
    """
    Playwright를 사용하여 URL을 가져옵니다. 네이버의 봇 감지를 우회하기 위한 다양한 기법을 사용합니다.

    Args:
        url: 가져올 URL
        user_agent: 사용할 User-Agent (None이면 기본값 사용)

    Returns:
        Tuple[str, int]: (HTML 콘텐츠, HTTP 상태 코드)
    """
    try:
        async with async_playwright() as p:
            print(f"🚀 브라우저 시작 중...")
            # Chromium 브라우저 시작
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',  # /dev/shm 파티션 사용 비활성화
                    '--disable-accelerated-2d-canvas',  # 2D 캔버스 가속 비활성화
                    '--disable-gpu',  # GPU 가속 비활성화
                    '--single-process',  # 단일 프로세스 모드
                ]
            )

            # 컨텍스트 생성
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=user_agent if user_agent else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='ko-KR',
                timezone_id='Asia/Seoul',
                permissions=[],
                ignore_https_errors=True,  # SSL 인증서 오류 무시
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
            )

            # 페이지 생성
            page = await context.new_page()

            print(f"🔒 봇 감지 우회 스크립트 적용 중...")

            # WebDriver 속성 제거 및 다양한 봇 감지 우회
            await page.add_init_script("""
                // WebDriver 속성 제거
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // navigator.webdriver 완전 삭제
                delete navigator.__proto__.webdriver;

                // Chrome 객체 추가
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };

                // Permissions 덮어쓰기
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Plugins 설정 (실제와 유사하게)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {name: 'Chrome PDF Plugin', description: 'Portable Document Format', filename: 'internal-pdf-viewer'},
                        {name: 'Chrome PDF Viewer', description: '', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
                        {name: 'Native Client', description: '', filename: 'internal-nacl-plugin'}
                    ]
                });

                // Languages 설정
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ko-KR', 'ko', 'en-US', 'en']
                });

                // Platform 설정
                Object.defineProperty(navigator, 'platform', {
                    get: () => 'Win32'
                });

                // Vendor 설정
                Object.defineProperty(navigator, 'vendor', {
                    get: () => 'Google Inc.'
                });

                // Hardware Concurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', {
                    get: () => 8
                });

                // Device Memory
                Object.defineProperty(navigator, 'deviceMemory', {
                    get: () => 8
                });

                // Connection
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({
                        effectiveType: '4g',
                        rtt: 50,
                        downlink: 10,
                        saveData: false
                    })
                });
            """)

            # 먼저 네이버 메인 페이지 방문 (정상 사용자 행동 모방)
            print(f"🏠 네이버 메인 페이지 방문 중...")
            await page.goto('https://www.naver.com', wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(1000)  # 1초 대기

            # 마우스 움직임 시뮬레이션 (정상 사용자 행동)
            await page.mouse.move(100, 100)
            await page.mouse.move(200, 200)
            await page.wait_for_timeout(500)

            print(f"🌐 페이지 로드 중: {url}")
            # Referer 헤더 설정하여 페이지 로드
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000, referer='https://www.naver.com/')

            status_code = response.status if response else 0
            print(f"📊 HTTP 상태 코드: {status_code}")

            print(f"⏳ 동적 콘텐츠 로딩 대기 중...")
            # 추가 대기 (동적 콘텐츠 로드)
            await page.wait_for_timeout(3000)  # 3초 대기

            # HTML 콘텐츠 가져오기 (모든 상태 코드에 대해)
            html_content = await page.content()

            print(f"📄 HTML 길이: {len(html_content)} bytes")

            # 브라우저 종료
            await browser.close()

            return html_content, status_code

    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        print(traceback.format_exc())
        return "", 0


async def main():
    """메인 함수"""
    test_url = "https://smartstore.naver.com/bkbk4470/products/500680413"

    print("=" * 80)
    print("네이버 스마트스토어 봇 감지 우회 테스트")
    print("=" * 80)
    print(f"테스트 URL: {test_url}")
    print("-" * 80)

    # 페이지 가져오기
    html, status_code = await fetch_with_playwright(test_url)

    print("-" * 80)
    print("결과:")
    print(f"  상태 코드: {status_code}")

    if status_code == 200:
        print("  ✅ 성공! 200 응답을 받았습니다.")
        print(f"  HTML 미리보기 (첫 500자):")
        print(f"  {html[:500]}")
    else:
        print(f"  ❌ 실패! 예상: 200, 실제: {status_code}")
        if html:
            print(f"  응답 내용 (첫 1000자):")
            print(f"  {html[:1000]}")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
