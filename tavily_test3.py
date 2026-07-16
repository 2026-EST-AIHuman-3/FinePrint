"""
1. 라이브러리 다운로드
pip install tavily-python openai

2. 설정
conda activate fineprint311
cd /smhrd2/FinePrint/jhc

3. 환경변수 등록
export TAVILY_API_KEY="YOUR_TAVILY_API_KEY"
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

4. 실행
python tavily_test3.py
"""

import os
import json
from tavily import TavilyClient
from openai import OpenAI
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# 1. API 키 등록
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 2. 구독형 서비스명 입력
def get_service_name():
    service_name = input("구독형 서비스명을 입력하세요: ").strip()
    return service_name

# 3. Tavily 약관 검색
def search_tos(service_name, max_results=10):
    query = f"{service_name} 약관 OR {service_name} terms of service"
    response = tavily_client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_raw_content=False,
    )
    return response.get("results", [])

# 4. gpt-40-mini로 검색 결과 필터링
def select_best_result(service_name, search_results):
    if not search_results:
        return None

    listing = ""
    for i, r in enumerate(search_results):
        listing += (
            f"[{i}] URL: {r.get('url')}\n"
            f"제목: {r.get('title')}\n"
            f"내용 일부: {r.get('content', '')[:300]}\n\n"
        )

    system_prompt = """
    너는 구독형 서비스의 '이용약관 원문 페이지'만을 정확히 골라내는 판별기다.

    아래 검색 결과 목록을 검토하여, 진짜 이용약관 원문일 가능성이 높은 순서대로 정렬하라.

    1. 공식 도메인 요건
        - 해당 구독형 서비스를 실제로 제공/운영하는 회사가 소유한 도메인에서 게시된 페이지여야 한다.
        - 뉴스, 기사, 블로그, 위키, 커뮤니티, 리뷰 사이트, 법률 정보 큐레이션 사이트는 도메인이 아무리 신뢰도 높아 보여도 전부 제외한다.
        - 동일하거나 유사한 이름을 쓰더라도 실제 서비스가 아닌 굿즈/커머스몰, 팬사이트, 파트너사·대리점 사이트는 제외한다.

    2. 문서 성격 요건
        - 페이지 자체가 약관 조항을 직접 나열한 원문이어야 한다 (예: 제1조, 제2조 / Article 1, Section 2 등 조항 번호 구조가 본문에 존재해야 함).
        - 약관을 단순히 '언급'하거나 '링크만 걸어둔' 페이지(공지사항, FAQ, 특허 안내, 저작권 안내, 회사 소개 페이지 등)는 제외한다.
        - 약관을 요약·해설·번역·재구성한 2차 콘텐츠(기사, 블로그의 "OO 서비스 약관 정리" 류)는 제외한다.

    3. 적용 대상 요건
        - 해당 서비스를 실제로 이용하는 일반 사용자(고객)에게 적용되는 약관이어야 한다.
        - 개발자용 API 이용약관, B2B 파트너 계약서, 개인정보처리방침 단독 페이지, 쿠키 정책 단독 페이지는 제외한다 (단, 종합 이용약관 안에 이런 내용이 일부 포함된 것은 허용).

    4. 제외 판단 시 주의사항
        - 검색 스니펫에 '이용약관'이라는 단어가 등장하더라도, 그 페이지가 약관을 인용/참조만 하고 실제 조항 본문이 없다면 하위 순위로 내려라.
        - 여러 언어/지역 버전이 있다면 한국어 사용자 대상 페이지를 우선하되, 없으면 영어 원문도 허용한다.

    [출력 규칙]
        - 조건에 맞는 결과가 하나도 없으면 빈 리스트를 반환하라.
        - 반드시 아래 JSON 형식으로만 답하라. 다른 설명, 마크다운, 코드블록 표시는 절대 포함하지 마라.
        {"ranked_indices": [<가능성이 높은 순서대로 나열한 번호들>]}"""

    user_prompt = f"서비스명: {service_name}\n\n검색 결과 목록:\n{listing}"

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    result = json.loads(response.choices[0].message.content)
    ranked = result.get("ranked_indices", [])

    if not ranked:
        print("조건에 맞는 후보를 찾지 못했습니다.")
        return None

    valid_ranked = [i for i in ranked if 0 <= i < len(search_results)]
    if not valid_ranked:
        print("유효한 인덱스가 없습니다.")
        return None

    return search_results[valid_ranked[0]]  # 1순위 반환

    if idx is None or idx == -1 or not (0 <= idx < len(search_results)):
        print(f"선정 실패 사유: {result.get('reason')}")
        return None

    return search_results[idx]

# 5. Tavily extract로 원문 추출
def extract_raw_tos(url):
    response = tavily_client.extract(urls=[url])
    results = response.get("results", [])
    if not results:
        return None
    return results[0].get("raw_content")

# 6. 약관 txt파일을 data 폴더에 저장
def save_tos_to_file(service_name, content):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    safe_name = service_name.replace(" ", "_")
    file_path = os.path.join(data_dir, f"{safe_name}_이용약관.txt")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path

# 7. 실행 코드
def main():
    service_name = get_service_name()
    print(f"'{service_name}' 약관 검색 중...")

    search_results = search_tos(service_name)
    if not search_results:
        print("검색 결과가 없습니다.")
        return

    best = select_best_result(service_name, search_results)
    if best is None:
        print("조건에 맞는 공식 약관 페이지를 찾지 못했습니다.")
        return

    print(f"선택된 URL: {best['url']}")

    raw_content = extract_raw_tos(best["url"])
    if not raw_content:
        print("본문 추출에 실패했습니다.")
        return

    file_path = save_tos_to_file(service_name, raw_content)
    print(f"저장 완료: {file_path}")


if __name__ == "__main__":
    main()