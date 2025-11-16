#!/usr/bin/env python3
"""
BrowserLikeClient를 사용하여 스마트스토어 요청 테스트
"""
import asyncio
import sys
import importlib.util

async def test_browser_client():
    """BrowserLikeClient를 사용한 테스트"""
    # cashtree_bot 모듈 로드
    spec = importlib.util.spec_from_file_location("cashtree_bot", "/home/user/cashtree_bot/cashtree_bot.py")
    cashtree_bot = importlib.util.module_from_spec(spec)

    print("모듈 로딩 중...")
    try:
        spec.loader.exec_module(cashtree_bot)
    except Exception as e:
        print(f"모듈 로드 오류: {e}")
        # 필요한 클래스만 추출 시도
        import traceback
        traceback.print_exc()
        return

    # BrowserLikeClient 생성
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    store_nnb = 'TEST'
    store_fwb = 'TEST'
    store_buc = 'TEST'
    store_token = 'TEST'

    print("BrowserLikeClient 생성 중...")
    client = cashtree_bot.BrowserLikeClient(
        user_agent=user_agent,
        store_nnb=store_nnb,
        store_fwb=store_fwb,
        store_buc=store_buc,
        store_token=store_token,
        proxy_config=None
    )

    url = "https://smartstore.naver.com/bkbk4470/products/500680413"

    print(f"\n요청 URL: {url}")
    print("요청 중...\n")

    try:
        response = await client.get(url)
        print(f"응답 상태 코드: {response.status_code}")
        print(f"\n응답 헤더:")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")

        if response.status_code == 200:
            print("\n✓ 성공! 200 응답을 받았습니다.")
            # 응답 내용의 일부 출력
            content = response.text[:500]
            print(f"\n응답 내용 일부:\n{content}...")
        else:
            print(f"\n✗ 실패! {response.status_code} 응답을 받았습니다.")
            if response.status_code == 403:
                print("403 Forbidden - 접근이 거부되었습니다.")
            print(f"응답 내용:\n{response.text[:1000]}")

    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_browser_client())
