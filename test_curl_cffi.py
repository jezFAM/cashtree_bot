#!/usr/bin/env python3
"""
curl_cffi를 사용한 테스트 - TLS fingerprinting 우회
"""
import asyncio
from curl_cffi.requests import AsyncSession

async def test_with_curl_cffi():
    """curl_cffi를 사용한 테스트"""
    url = "https://smartstore.naver.com/bkbk4470/products/500680413"

    print(f"요청 URL: {url}")
    print("curl_cffi를 사용하여 Chrome 브라우저 impersonate\n")

    # Chrome 브라우저를 완벽하게 모방
    async with AsyncSession() as session:
        try:
            response = await session.get(
                url,
                impersonate="chrome131",  # Chrome 131 브라우저 완벽 모방
                timeout=30
            )

            print(f"응답 상태 코드: {response.status_code}")

            if response.status_code == 200:
                print("\n✓ 성공! 200 응답을 받았습니다!")
                print(f"응답 내용 길이: {len(response.text)} bytes")
                print(f"\n응답 내용 일부:\n{response.text[:500]}...")
            else:
                print(f"\n✗ 실패! {response.status_code} 응답을 받았습니다.")
                print(f"응답 내용:\n{response.text[:1000]}")

        except Exception as e:
            print(f"\n오류 발생: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_with_curl_cffi())
