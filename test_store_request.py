#!/usr/bin/env python3
"""
네이버 스마트스토어 요청 테스트 스크립트
"""
import asyncio
import ssl
from httpx import AsyncClient, Limits

async def test_request():
    """스마트스토어 페이지 요청 테스트"""
    url = "https://smartstore.naver.com/bkbk4470/products/500680413"

    # SSL 컨텍스트 설정
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED

    limits = Limits(max_keepalive_connections=5, max_connections=10)

    # 기본 헤더 설정 (브라우저와 동일하게)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Connection': 'keep-alive',
        'Sec-CH-UA': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'Sec-CH-UA-Mobile': '?0',
        'Sec-CH-UA-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
    }

    async with AsyncClient(
        http2=False,  # HTTP/1.1 사용
        follow_redirects=True,
        verify=ssl_context,
        limits=limits
    ) as client:
        print(f"요청 URL: {url}")
        print(f"요청 헤더:")
        for key, value in headers.items():
            print(f"  {key}: {value}")
        print("\n요청 중...")

        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            print(f"\n응답 상태 코드: {response.status_code}")
            print(f"응답 헤더:")
            for key, value in response.headers.items():
                print(f"  {key}: {value}")

            if response.status_code == 200:
                print("\n✓ 성공! 200 응답을 받았습니다.")
                # 응답 내용의 일부 출력
                content = response.text[:500]
                print(f"\n응답 내용 일부:\n{content}...")
            else:
                print(f"\n✗ 실패! {response.status_code} 응답을 받았습니다.")
                print(f"응답 내용:\n{response.text[:1000]}")

        except Exception as e:
            print(f"\n오류 발생: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_request())
