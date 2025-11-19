#!/usr/bin/env python3
"""
독립적인 쿠키 수집 테스트 스크립트
"""

import asyncio
import traceback
from typing import Dict, List, Tuple
from playwright.async_api import async_playwright


async def fetch_with_playwright(url: str) -> Tuple[str, int, List[Dict], str]:
    """
    Playwright를 사용하여 URL을 가져옵니다. 네이버의 봇 감지를 우회하기 위한 다양한 기법을 사용합니다.

    실제 사용자처럼 행동하여 자연스럽게 쿠키를 획득합니다.

    Args:
        url: 가져올 URL

    Returns:
        Tuple[str, int, List[Dict], str]: (HTML 콘텐츠, HTTP 상태 코드, 브라우저 쿠키 리스트, 사용한 User-Agent)
    """
    try:
        async with async_playwright() as p:
            # 실제 Chrome/Edge 바이너리 사용 (Chromium은 봇 탐지됨)
            browser = None

            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
            ]

            # Edge User-Agent (브라우저와 일치)
            edge_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'

            # Edge만 사용 (Windows 기본 설치)
            try:
                browser = await p.chromium.launch(
                    channel='msedge',
                    headless=True,
                    args=launch_args
                )
                print(f'fetch_with_playwright: Using Edge (channel=msedge)')
            except Exception as edge_error:
                # Edge 없으면 조용히 실패 (Chromium은 봇 탐지되므로 사용 안함)
                print(f'fetch_with_playwright: Edge not found. {str(edge_error)[:150]}')
                return "", 0, [], edge_ua

            # 컨텍스트 생성
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=edge_ua,
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

            # 페이지 생성 (실제 브라우저처럼 새로운 세션으로 시작)
            page = await context.new_page()

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
            try:
                await page.goto('https://www.naver.com', wait_until='load', timeout=30000)
                # 충분한 대기 시간을 주어 JavaScript가 쿠키를 설정하도록 함
                await page.wait_for_timeout(5000)  # 5초 대기 (쿠키 설정 완료 대기)

                # 현실적인 사용자 행동 시뮬레이션
                try:
                    # 페이지 스크롤 (사용자처럼 보이기 위해)
                    await page.evaluate('window.scrollTo(0, 500)')
                    await page.wait_for_timeout(500)
                    await page.evaluate('window.scrollTo(0, 1000)')
                    await page.wait_for_timeout(500)
                    await page.evaluate('window.scrollTo(0, 0)')
                    await page.wait_for_timeout(1000)
                except:
                    pass  # 스크롤 실패해도 계속 진행
            except Exception as e:
                # 메인 페이지 로드 실패해도 계속 진행 (단, CancelledError는 재발생)
                if isinstance(e, asyncio.CancelledError):
                    raise
                print(f'fetch_with_playwright: Naver main page load failed: {str(e)}')

            # 페이지 로드 (타임아웃 60초) with Referer 헤더
            try:
                response = await page.goto(url, wait_until='load', timeout=60000, referer='https://www.naver.com/')
                status_code = response.status if response else 0
            except Exception as e:
                # 페이지 로드 실패 (타임아웃, 네트워크 오류 등)
                print(f'fetch_with_playwright: Failed to load {url}: {str(e)}')
                status_code = 0
                html_content = ""
                browser_cookies = []

                try:
                    await browser.close()
                except:
                    pass  # 브라우저가 이미 닫혔을 수 있음

                return html_content, status_code, browser_cookies, edge_ua

            html_content = ""
            browser_cookies = []

            try:
                if status_code == 200:
                    # 추가 대기 (동적 콘텐츠 및 쿠키 설정 완료 대기)
                    await page.wait_for_timeout(10000)  # 10초 대기 (매우 긴 대기)

                    # 현실적인 사용자 행동 시뮬레이션 (타겟 페이지에서도)
                    try:
                        await page.evaluate('window.scrollTo(0, 300)')
                        await page.wait_for_timeout(1200)
                        await page.evaluate('window.scrollTo(0, 600)')
                        await page.wait_for_timeout(1200)
                        await page.evaluate('window.scrollTo(0, 900)')
                        await page.wait_for_timeout(1200)

                        # 상품 이미지 클릭 시도 (실제 상호작용)
                        try:
                            await page.click('img', timeout=2000)
                            await page.wait_for_timeout(500)
                        except:
                            pass
                    except:
                        pass

                    # HTML 콘텐츠 가져오기
                    html_content = await page.content()
                elif status_code:
                    # 상태 코드가 있지만 200이 아닌 경우 (403, 429 등)
                    await page.wait_for_timeout(5000)  # 5초 대기
                    html_content = await page.content()
                else:
                    html_content = ""

                # 브라우저에서 쿠키 가져오기 (API 요청에 사용하기 위해)
                # context.cookies()는 파라미터 없이 호출하면 모든 도메인의 쿠키를 반환함
                browser_cookies = await context.cookies()

                # 디버깅: 쿠키 개수와 이름 로그
                cookie_names = [c['name'] for c in browser_cookies]
                cookie_domains = list(set([c.get('domain', 'unknown') for c in browser_cookies]))
                print(f'fetch_with_playwright: Retrieved {len(browser_cookies)} cookies from domains {cookie_domains}: {cookie_names}')
            except Exception as e:
                # 브라우저가 크래시되었거나 페이지가 닫힌 경우
                print(f'fetch_with_playwright: Browser error while processing {url}: {str(e)}')

            # 브라우저 종료
            try:
                await browser.close()
            except:
                pass  # 브라우저가 이미 닫혔을 수 있음

            return html_content, status_code, browser_cookies, edge_ua

    except Exception as e:
        msg = f'fetch_with_playwright error: {str(e)}\n{traceback.format_exc()}'
        print(msg)
        # 실패 시에도 Edge UA 반환
        edge_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'
        return "", 0, [], edge_ua


async def test_cookie_collection():
    """쿠키 수집 테스트"""

    # 네이버 스마트스토어 URL 테스트
    test_url = "https://brand.naver.com/sisem/products/4752033819"

    print("=" * 80)
    print("쿠키 수집 테스트")
    print("=" * 80)
    print(f"테스트 URL: {test_url}")
    print("-" * 80)

    try:
        # fetch_with_playwright 호출
        html, status_code, browser_cookies, user_agent = await fetch_with_playwright(test_url)

        print(f"\n✅ fetch_with_playwright 완료")
        print(f"  - HTTP 상태 코드: {status_code}")
        print(f"  - HTML 길이: {len(html)} bytes")
        print(f"  - User-Agent: {user_agent[:50]}...")
        print(f"  - 쿠키 개수: {len(browser_cookies)}")
        print()

        if browser_cookies:
            print("🍪 수집된 쿠키 목록:")
            print("-" * 80)

            # 도메인별로 그룹화
            cookies_by_domain = {}
            for cookie in browser_cookies:
                domain = cookie.get('domain', 'unknown')
                if domain not in cookies_by_domain:
                    cookies_by_domain[domain] = []
                cookies_by_domain[domain].append(cookie)

            # 도메인별로 출력
            for domain, cookies in sorted(cookies_by_domain.items()):
                print(f"\n📍 도메인: {domain}")
                print(f"   쿠키 수: {len(cookies)}")
                for cookie in cookies:
                    name = cookie.get('name', 'unknown')
                    value = cookie.get('value', '')
                    path = cookie.get('path', '/')
                    secure = cookie.get('secure', False)
                    httpOnly = cookie.get('httpOnly', False)
                    sameSite = cookie.get('sameSite', 'None')

                    # 값이 길면 잘라서 표시
                    value_display = value[:30] + "..." if len(value) > 30 else value

                    flags = []
                    if secure:
                        flags.append("Secure")
                    if httpOnly:
                        flags.append("HttpOnly")
                    if sameSite != 'None':
                        flags.append(f"SameSite={sameSite}")

                    flags_str = f" [{', '.join(flags)}]" if flags else ""

                    print(f"   - {name} = {value_display}{flags_str}")
                    print(f"     Path: {path}")
        else:
            print("❌ 쿠키가 수집되지 않았습니다!")

        print()
        print("-" * 80)

        # 성공 여부 판단
        if status_code == 200 and len(browser_cookies) > 1:
            print("✅ 테스트 성공!")
            print(f"   - 200 OK 응답")
            print(f"   - {len(browser_cookies)}개의 쿠키 수집")
            return True
        elif status_code == 429:
            print("⚠️  429 Too Many Requests - Rate limit 도달")
            print(f"   하지만 {len(browser_cookies)}개의 쿠키는 수집됨")
            return len(browser_cookies) > 1
        else:
            print(f"❌ 테스트 실패!")
            print(f"   - 상태 코드: {status_code}")
            print(f"   - 쿠키 개수: {len(browser_cookies)}")

            # 429가 아닌 경우 HTML 일부 출력
            if status_code != 429 and html:
                print(f"\n응답 내용 미리보기 (첫 500자):")
                print(html[:500])

            return False

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        traceback.print_exc()
        return False

    print("=" * 80)


async def main():
    """메인 함수"""
    success = await test_cookie_collection()

    if success:
        print("\n🎉 쿠키 수집이 정상적으로 작동합니다!")
        return 0
    else:
        print("\n💥 쿠키 수집에 문제가 있습니다. 코드를 수정해야 합니다.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
