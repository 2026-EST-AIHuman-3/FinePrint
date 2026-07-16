# playwright install chromium
# pip install playwright trafilatura

# source .venv/bin/activate
# cd /smhrd2/FinePrint/jhc
# python playwright_Trafilatura_crawling.py


import os
import asyncio
from playwright.async_api import async_playwright
import trafilatura

# 페이지 열고 HTML 가져오기
async def fetch_rendered_html(url: str, wait_selector: str = None, timeout: int = 30000) -> str:
    """
    Playwright로 URL에 접속해 JS 렌더링이 완료된 HTML을 가져옵니다.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        await page.goto(url, wait_until="networkidle", timeout=timeout) # 페이지 로딩이 끝날때까지 기다림
        
        if wait_selector:
            await page.wait_for_selector(wait_selector, timeout=timeout) # 특정 사이트에서 본문이 늦게 뜨면 사용

        await page.evaluate("""
            () => new Promise(resolve => {
                let total = 0;
                const step = 500;
                const timer = setInterval(() => {
                    window.scrollBy(0, step);
                    total += step;
                    if (total >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 200);
            })
        """)
        await page.wait_for_timeout(1000)

        html = await page.content()
        await browser.close()
        return html

# 본문만 추출
def extract_main_text(html: str, url: str = None) -> str:
    """
    Trafilatura로 HTML에서 본문(약관 내용)만 추출합니다.
    """
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False, # 댓글 영역 제외
        include_tables=True,    # 표 포함
        favor_recall=True,      # 최대한 모든 내용을 가져오기
        deduplicate=True,       # 같은 문단이 중복 등장하면 하나로 정리
    )
    return text or ""

# 약관의 내용을 추출한 뒤 저장
async def crawl_and_save(url: str, output_dir: str, filename: str, wait_selector: str = None):
    os.makedirs(output_dir, exist_ok=True)  # 데이터 폴더가 없으면 자동 생성, 있으면 그냥 넘어감
    output_path = os.path.join(output_dir, filename)

    print(f"[1/3] 페이지 렌더링 중... ({url})")
    html = await fetch_rendered_html(url, wait_selector=wait_selector)

    print("[2/3] 본문 텍스트 추출 중...")
    text = extract_main_text(html, url=url)

    # 추출된 텍스트가 비어있을 경우 파일을 저장하지 않고 종료
    if not text.strip():
        print("추출된 텍스트가 없습니다. wait_selector를 지정하거나 페이지 구조를 확인하세요.")
        return

    print(f"[3/3] 파일 저장 중... -> {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"완료! 총 {len(text):,}자 저장됨.")

# 스크립트 파일 자체의 위치를 기준으로 data 폴더 경로 계산
if __name__ == "__main__":
    # INPUT_URL = "https://www.kakao.com/policy/terms?type=a&lang=ko"  # URL 입력
    INPUT_URL = input("약관 URL을 입력해주세요 : ")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(BASE_DIR, "data")
    # OUTPUT_FILENAME = "카카오_이용약관2.txt"   # 파일 이름 설정
    OUTPUT_FILENAME = input("파일 이름을 설정해주세요 : ")
    asyncio.run(
        crawl_and_save(
            url=INPUT_URL,
            output_dir=OUTPUT_DIR,
            filename=OUTPUT_FILENAME,
            wait_selector=None,
        )
    )

# https://help.netflix.com/ko/legal/termsofuse
# python playwright_Trafilatura_crawling.py