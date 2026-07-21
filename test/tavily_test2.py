"""
# 필요 라이브러리 설치
pip install tavily-python requests

# 실행 전 
1. source .venv/bin/activate
2. cd /smhrd2/FinePrint/jhc
3. export TAVILY_API_KEY="YOUR_TAVILY_API_KEY"

# 실행
python tavily_test2.py
"""

import os
import json
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

MAP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_map.json")

def load_service_map(path=MAP_PATH):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_service_map(mapping, path=MAP_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)

# 서비스명 입력 파트
service_name = input("구독 서비스 이름을 입력하세요 : ").strip()

service_map = load_service_map()
service_name_en = service_map.get(service_name)

if service_name_en is None:
    service_name_en = input(f"'{service_name}'의 영문명을 입력하세요 (예: netflix): ").strip().lower()
    service_map[service_name] = service_name_en
    save_service_map(service_map)
    print(f"매핑 저장 완료: {service_name} → {service_name_en}")

# 웹 검색 파트
search_query = f"{service_name} {service_name_en} terms of use 이용약관"

search_res = client.search(
    query=search_query,
    search_depth="advanced",
    max_results=5,
    include_domains=[f"{service_name_en}.com", f"help.{service_name_en}.com"]
)

# 검색 결과가 없을 경우
if not search_res["results"]:
    print(f"'{service_name}'에 대한 공식 도메인 검색 결과가 없습니다.")
    # 도메인 제한 없이 재검색 (fallback)
    search_res = client.search(query=search_query, search_depth="advanced", max_results=10)

# 필터링
POLICY_KEYWORDS = ["약관", "정책"]
LEGAL_URL_KEYWORDS = ["legal", "terms", "agreement", "policy"]

def is_valid_result(result: dict) -> bool:
    title = result.get("title", "")
    content = result.get("content", "")
    url = result.get("url", "").lower()

    # 1. title에 service_name 포함
    cond1 = service_name in title

    # 2. content에 약관/정책 관련 단어 포함
    cond2 = any(keyword in content for keyword in POLICY_KEYWORDS)

    # 3. url에 영문명 포함
    cond3 = service_name_en in url

    # 4. url에 정책 용어 포함
    cond4 = any(keyword in url for keyword in LEGAL_URL_KEYWORDS)  # 추가

    return cond1 and cond2 and cond3 and cond4

filtered_results = [r for r in search_res["results"] if is_valid_result(r)]

if not filtered_results:
    print("조건을 만족하는 검색 결과가 없습니다.")
    print("전체 검색 결과:")
    for r in search_res["results"]:
        print(f" - {r['title']} | {r['url']}")
    exit()

# 필터링된 결과 중 최상위 후보 사용
top_result = filtered_results[0]
tos_url = top_result["url"]
print(f"필터링된 후보 URL: {tos_url}")

# URL에서 내용 추출
extract_res = client.extract(urls=[tos_url])

if not extract_res["results"]:
    print("Extract 실패:", extract_res["failed_results"])
    exit()

raw_text = extract_res["results"][0]["raw_content"]
extracted_url = extract_res["results"][0]["url"]
print(f"추출 완료 URL (글자수): {extracted_url} ({len(raw_text)}자)")

# data 폴더에 저장
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(data_dir, exist_ok=True)

file_path = os.path.join(data_dir, f"{service_name}_이용약관.txt")

# 중복 파일 체크
if os.path.exists(file_path):
    print(f"이미 존재하는 파일입니다: {file_path}")
else:
    # 파일 맨 위에 출처 URL도 함께 남겨두기
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"[출처 URL] {extracted_url}\n\n")
        f.write(raw_text)