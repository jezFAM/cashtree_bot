#!/usr/bin/env python3
"""
fetch_with_playwright 함수의 쿠키 수집 기능 테스트
"""

import asyncio
import sys
from pathlib import Path

# cashtree_bot 모듈을 import하기 위해 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

# fetch_with_playwright 함수를 import (실제 구현된 함수 사용)
from cashtree_bot import fetch_with_playwright


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
            return False

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("=" * 80)


async def main():
    """메인 함수"""
    success = await test_cookie_collection()

    if success:
        print("\n🎉 쿠키 수집이 정상적으로 작동합니다!")
        sys.exit(0)
    else:
        print("\n💥 쿠키 수집에 문제가 있습니다. 코드를 수정해야 합니다.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
