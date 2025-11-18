#!/usr/bin/env python3
"""
Playwright를 사용한 네이버 스마트스토어 봇 감지 우회 테스트 스크립트
"""

import asyncio
import os
import traceback
from typing import Dict, Tuple
from playwright.async_api import async_playwright


async def fetch_with_playwright(url: str, user_agent: str = None) -> Tuple[str, int, list]:
    """
    Playwright를 사용하여 URL을 가져옵니다. 네이버의 봇 감지를 우회하기 위한 다양한 기법을 사용합니다.

    Args:
        url: 가져올 URL
        user_agent: 사용할 User-Agent (None이면 기본값 사용)

    Returns:
        Tuple[str, int, list]: (HTML 콘텐츠, HTTP 상태 코드, 브라우저 쿠키)
    """
    try:
        async with async_playwright() as p:
            print(f"🚀 브라우저 시작 중...")
            # 실제 Chrome/Edge 바이너리 사용 (더 탐지하기 어려움)
            browser = None
            browser_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/usr/bin/microsoft-edge",
            ]

            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]

            # 1. Chrome channel 시도
            try:
                print(f"  → Chrome 사용 시도 (channel='chrome')...")
                browser = await p.chromium.launch(
                    channel='chrome',
                    headless=True,
                    args=launch_args
                )
                print(f"  ✅ Chrome 사용 성공 (channel='chrome')")
            except Exception as chrome_error:
                print(f"  ⚠️  channel='chrome' 실패: {str(chrome_error)[:100]}")

                # 2. Edge channel 시도
                try:
                    print(f"  → Edge 사용 시도 (channel='msedge')...")
                    browser = await p.chromium.launch(
                        channel='msedge',
                        headless=True,
                        args=launch_args
                    )
                    print(f"  ✅ Edge 사용 성공 (channel='msedge')")
                except Exception as edge_error:
                    print(f"  ⚠️  channel='msedge' 실패: {str(edge_error)[:100]}")
                    print(f"  → 시스템 브라우저 경로 검색 중...")

                    # 3. 직접 경로로 시도
                    for browser_path in browser_paths:
                        if os.path.exists(browser_path):
                            try:
                                print(f"  → 브라우저 경로 시도: {browser_path}")
                                browser = await p.chromium.launch(
                                    executable_path=browser_path,
                                    headless=True,
                                    args=launch_args
                                )
                                print(f"  ✅ 브라우저 사용 성공: {browser_path}")
                                break
                            except Exception as path_error:
                                print(f"  ⚠️  경로 실패: {str(path_error)[:100]}")
                                continue

                    # 모든 시도 실패
                    if browser is None:
                        raise Exception(
                            f"Chrome 또는 Edge 브라우저를 찾을 수 없습니다. "
                            f"시스템에 Chrome 또는 Edge를 설치하거나 PLAYWRIGHT_BROWSERS_PATH 환경변수를 설정하세요."
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

            print(f"🔒 봇 감지 우회 스크립트 적용 중 (강화된 버전)...")

            # WebDriver 속성 제거 및 다양한 봇 감지 우회 (강화된 버전)
            await page.add_init_script("""
                // WebDriver 속성 완전 제거
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });

                delete Object.getPrototypeOf(navigator).webdriver;

                // Chrome 객체 추가 (더 완전하게)
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {
                        isInstalled: false,
                        InstallState: {
                            DISABLED: 'disabled',
                            INSTALLED: 'installed',
                            NOT_INSTALLED: 'not_installed'
                        },
                        RunningState: {
                            CANNOT_RUN: 'cannot_run',
                            READY_TO_RUN: 'ready_to_run',
                            RUNNING: 'running'
                        }
                    }
                };

                // Permissions 덮어쓰기
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Plugins 설정 (더 현실적으로)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => {
                        const plugins = [
                            {
                                0: {type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format'},
                                description: 'Portable Document Format',
                                filename: 'internal-pdf-viewer',
                                length: 1,
                                name: 'Chrome PDF Plugin'
                            },
                            {
                                0: {type: 'application/pdf', suffixes: 'pdf', description: ''},
                                description: '',
                                filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                                length: 1,
                                name: 'Chrome PDF Viewer'
                            },
                            {
                                0: {type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable'},
                                1: {type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable'},
                                description: '',
                                filename: 'internal-nacl-plugin',
                                length: 2,
                                name: 'Native Client'
                            }
                        ];
                        plugins.length = 3;
                        return plugins;
                    }
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
                        saveData: false,
                        onchange: null,
                        ontypechange: null
                    })
                });

                // maxTouchPoints 설정
                Object.defineProperty(navigator, 'maxTouchPoints', {
                    get: () => 0
                });

                // Battery API 숨기기
                if ('getBattery' in navigator) {
                    navigator.getBattery = undefined;
                }

                // WebGL Vendor/Renderer 정보 수정
                const getParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(parameter) {
                    if (parameter === 37445) {
                        return 'Intel Inc.';
                    }
                    if (parameter === 37446) {
                        return 'Intel Iris OpenGL Engine';
                    }
                    return getParameter.apply(this, [parameter]);
                };

                // Canvas fingerprinting 방지
                const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                HTMLCanvasElement.prototype.toDataURL = function(type) {
                    if (type === 'image/png' && this.width === 16 && this.height === 16) {
                        return originalToDataURL.apply(this, arguments);
                    }
                    return originalToDataURL.apply(this, arguments);
                };

                // Notification.permission 설정
                if ('Notification' in window) {
                    Notification.permission = 'default';
                }
            """)

            # 먼저 네이버 메인 페이지 방문 (정상 사용자 행동 모방, 쿠키 획득)
            print(f"🏠 네이버 메인 페이지 방문 중...")
            try:
                await page.goto('https://www.naver.com', wait_until='load', timeout=30000)
                print(f"⏳ 쿠키 설정 대기 중 (7초)...")
                await page.wait_for_timeout(7000)  # 7초 대기

                print(f"🖱️  사용자 행동 시뮬레이션 중...")
                # 현실적인 사용자 행동 시뮬레이션
                try:
                    await page.evaluate('window.scrollTo(0, 500)')
                    await page.wait_for_timeout(800)
                    await page.evaluate('window.scrollTo(0, 1000)')
                    await page.wait_for_timeout(800)
                    await page.evaluate('window.scrollTo(0, 1500)')
                    await page.wait_for_timeout(800)
                    await page.evaluate('window.scrollTo(0, 0)')
                    await page.wait_for_timeout(1500)

                    # 검색 박스 클릭 시뮬레이션
                    try:
                        await page.click('input[type="text"]', timeout=2000)
                        await page.wait_for_timeout(500)
                        print(f"  ✅ 검색 박스 클릭 성공")
                    except:
                        print(f"  ⚠️  검색 박스 클릭 실패")
                except Exception as scroll_error:
                    print(f"  ⚠️  스크롤 시뮬레이션 실패: {str(scroll_error)[:50]}")

                # 네이버 메인 페이지에서 쿠키 확인
                main_page_cookies = await context.cookies()
                print(f"🍪 네이버 메인 페이지 쿠키 개수: {len(main_page_cookies)}")
                if main_page_cookies:
                    for cookie in main_page_cookies:
                        print(f"  - {cookie['name']}: {cookie['domain']}")
            except Exception as e:
                if isinstance(e, asyncio.CancelledError):
                    raise
                print(f"⚠️  네이버 메인 페이지 로드 실패, 계속 진행: {str(e)}")

            print(f"🌐 페이지 로드 중: {url}")
            # 직접 타겟 페이지로 이동 (간소화된 접근)
            try:
                response = await page.goto(url, wait_until='load', timeout=60000, referer='https://www.naver.com/')
                status_code = response.status if response else 0
            except Exception as e:
                # 페이지 로드 실패 (타임아웃, 네트워크 오류 등)
                print(f"❌ 페이지 로드 실패: {str(e)}")
                status_code = 0
                html_content = ""
                browser_cookies = []

                try:
                    await browser.close()
                except:
                    pass  # 브라우저가 이미 닫혔을 수 있음

                return html_content, status_code, browser_cookies

            print(f"📊 HTTP 상태 코드: {status_code}")

            html_content = ""
            browser_cookies = []

            try:
                print(f"⏳ 동적 콘텐츠 및 쿠키 설정 대기 중 (10초)...")
                # 추가 대기 (동적 콘텐츠 및 쿠키 설정 완료 대기)
                await page.wait_for_timeout(10000)  # 10초 대기 (매우 긴 대기)

                print(f"🖱️  타겟 페이지 사용자 행동 시뮬레이션 중...")
                # 현실적인 사용자 행동 시뮬레이션 (타겟 페이지에서도)
                try:
                    await page.evaluate('window.scrollTo(0, 300)')
                    await page.wait_for_timeout(1200)
                    await page.evaluate('window.scrollTo(0, 600)')
                    await page.wait_for_timeout(1200)
                    await page.evaluate('window.scrollTo(0, 900)')
                    await page.wait_for_timeout(1200)

                    # 상품 이미지 클릭 시도
                    try:
                        await page.click('img', timeout=2000)
                        await page.wait_for_timeout(500)
                        print(f"  ✅ 이미지 클릭 성공")
                    except:
                        print(f"  ⚠️  이미지 클릭 실패")
                except Exception as scroll_error:
                    print(f"  ⚠️  스크롤 시뮬레이션 실패: {str(scroll_error)[:50]}")

                # HTML 콘텐츠 가져오기 (모든 상태 코드에 대해)
                html_content = await page.content()

                # 브라우저에서 쿠키 가져오기
                browser_cookies = await context.cookies()

                print(f"📄 HTML 길이: {len(html_content)} bytes")
                print(f"🍪 쿠키 개수: {len(browser_cookies)}")

                # 쿠키 상세 정보 출력
                if browser_cookies:
                    print(f"🍪 쿠키 상세:")
                    for cookie in browser_cookies:
                        print(f"  - {cookie['name']}: {cookie['domain']}")
            except Exception as e:
                # 브라우저가 크래시되었거나 페이지가 닫힌 경우
                print(f"❌ 브라우저 오류: {str(e)}")

            # 브라우저 종료
            try:
                await browser.close()
            except:
                pass  # 브라우저가 이미 닫혔을 수 있음

            return html_content, status_code, browser_cookies

    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        print(traceback.format_exc())
        return "", 0, []


async def main():
    """메인 함수"""
    test_url = "https://smartstore.naver.com/bkbk4470/products/500680413"

    print("=" * 80)
    print("네이버 스마트스토어 봇 감지 우회 테스트")
    print("=" * 80)
    print(f"테스트 URL: {test_url}")
    print("-" * 80)

    # 페이지 가져오기
    html, status_code, cookies = await fetch_with_playwright(test_url)

    print("-" * 80)
    print("결과:")
    print(f"  상태 코드: {status_code}")
    print(f"  쿠키 개수: {len(cookies)}")

    if cookies:
        print(f"  쿠키 목록:")
        for cookie in cookies[:5]:  # 처음 5개만 표시
            print(f"    - {cookie['name']}: {cookie['value'][:50]}...")

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
