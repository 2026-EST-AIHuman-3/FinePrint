"""
1. 라이브러리 다운로드
pip install tavily-python langchain-openai langgraph pydantic

2. 설정
conda activate fineprint311
cd /smhrd2/FinePrint/jhc

3. 환경변수 등록
export TAVILY_API_KEY="YOUR_TAVILY_API_KEY"
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

4. 실행
python tavily_test4.py
"""

import os
from typing import TypedDict, List, Optional
from pydantic import BaseModel, Field
from tavily import TavilyClient
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv

load_dotenv()

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
llm = ChatOpenAI(model="gpt-4o-mini")

# 1. state 정의
class AgentState(TypedDict):
    service_name: str
    query: str
    search_results: list
    selected_urls: List[str]
    extracted_content: list
    validated_content: Optional[dict]
    failed_urls: List[str]
    attempt: int

# 2. 구조화된 출력 스키마
class URLSelection(BaseModel):
    selected_urls: List[str] = Field(description="추출할 가치가 있는 URL 목록, 우선순위 순")
    reasoning: str = Field(description="선택 이유")

structured_llm = llm.with_structured_output(URLSelection)

# 3. search 노드
def search_node(state: AgentState) -> dict:
    attempt = state.get("attempt", 0)
    failed_urls = state.get("failed_urls", [])

    # 재시도할 때는 쿼리를 살짝 바꿔서 같은 결과가 반복 선택되는 걸 줄임
    if attempt == 0:
        query = f"{state['service_name']} 이용약관 OR terms of service"
    else:
        query = f"{state['service_name']} 공식 이용약관 전문 site 원문"

    response = tavily_client.search(
        query=query,
        search_depth="advanced",
        max_results=10,
    )
    results = response.get("results", [])

    # 이미 실패한 URL은 후보에서 제거
    filtered = [r for r in results if r["url"] not in failed_urls]

    return {
        "query": query,
        "search_results": filtered,
        "attempt": attempt + 1,
    }

# 4. search_url 노드 (LLM 필터링)
def select_urls_node(state: AgentState) -> dict:
    if not state["search_results"]:
        return {"selected_urls": []}

    results_text = "\n".join(
        f"- URL: {r['url']}\n  제목: {r['title']}\n  내용: {r.get('content', '')[:300]}"
        for r in state["search_results"]
    )

    prompt = f"""너는 구독형 서비스의 '이용약관 원문 페이지'만을 정확히 골라내는 판별기다.

서비스명: {state['service_name']}

[선택 조건]
1. 공식 도메인 요건: 입력받은 서비스를 실제로 제공/운영하는 회사의 도메인이어야 한다.
   뉴스, 기사, 블로그, 위키, 커뮤니티, 리뷰 사이트, 법률 정보 큐레이션 사이트는 제외한다.
   동일하거나 유사한 이름을 쓰더라도 굿즈/커머스몰, 팬사이트, 파트너사 사이트는 제외한다.
2. 문서 성격 요건: 페이지 자체가 약관 조항(제1조, 제2조 / Article 1 등)을 직접 나열한 원문이어야 한다.
   약관을 '언급'만 하거나 링크만 걸어둔 페이지(특허 안내, FAQ, 공지사항, 회사 소개)는 제외한다.
   약관을 요약·해설한 2차 콘텐츠는 제외한다.
3. 적용 대상 요건: 일반 사용자(고객)에게 적용되는 약관이어야 한다.
   개발자용 API 약관, B2B 파트너 계약서, 개인정보처리방침 단독 페이지는 제외한다.

위 조건을 만족할 가능성이 높은 순서대로 최대 3개까지 선택하라.
조건에 맞는 게 하나도 없으면 빈 리스트를 반환하라.

검색 결과:
{results_text}
"""

    result = structured_llm.invoke(prompt)
    return {"selected_urls": result.selected_urls}

# 5. extract 노드
def extract_node(state: AgentState) -> dict:
    if not state["selected_urls"]:
        return {"extracted_content": []}

    response = tavily_client.extract(
        urls=state["selected_urls"],
        extract_depth="advanced",
    )
    return {"extracted_content": response.get("results", [])}

# 6. 검증 노드
def validate_node(state: AgentState) -> dict:
    markers = ["제1조", "제 1 조", "Article 1", "정의", "회원", "해지", "환불", "계약", state["service_name"]]

    for item in state["extracted_content"]:
        content = item.get("raw_content", "") or ""
        hit_count = sum(1 for m in markers if m in content)

        if len(content) >= 1500 and hit_count >= 2:
            return {
                "validated_content": {"url": item["url"], "content": content},
                "failed_urls": state.get("failed_urls", []),
            }

    # 유효한 게 하나도 없으면 실패 목록에 누적
    newly_failed = [item["url"] for item in state["extracted_content"]]
    return {
        "validated_content": None,
        "failed_urls": state.get("failed_urls", []) + newly_failed,
    }

# 7. 조건부 라우팅
MAX_ATTEMPTS = 3

def route_after_validate(state: AgentState) -> str:
    if state.get("validated_content"):
        return "save"
    if state.get("attempt", 0) < MAX_ATTEMPTS:
        return "search"
    return "give_up"

# 8. 저장 노드 & 종료 노드
def save_node(state: AgentState) -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    safe_name = state["service_name"].replace(" ", "_")
    file_path = os.path.join(data_dir, f"{safe_name}_이용약관.txt")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(state["validated_content"]["content"])

    print(f"저장 완료: {file_path} (출처: {state['validated_content']['url']})")
    return {}


def give_up_node(state: AgentState) -> dict:
    print(f"'{state['service_name']}'의 공식 약관 원문 페이지를 찾지 못했습니다.")
    print(f"시도한 URL: {state.get('failed_urls', [])}")
    return {}

# 9. 에이전트 생성 및 실행
graph = StateGraph(AgentState)
graph.add_node("search", search_node)
graph.add_node("select_urls", select_urls_node)
graph.add_node("extract", extract_node)
graph.add_node("validate", validate_node)
graph.add_node("save", save_node)
graph.add_node("give_up", give_up_node)

graph.add_edge(START, "search")
graph.add_edge("search", "select_urls")
graph.add_edge("select_urls", "extract")
graph.add_edge("extract", "validate")
graph.add_conditional_edges(
    "validate",
    route_after_validate,
    {"save": "save", "search": "search", "give_up": "give_up"},
)
graph.add_edge("save", END)
graph.add_edge("give_up", END)

app = graph.compile()


def get_service_name() -> str:
    return input("구독형 서비스명을 입력하세요: ").strip()


def main():
    service_name = get_service_name()
    initial_state = {
        "service_name": service_name,
        "query": "",
        "search_results": [],
        "selected_urls": [],
        "extracted_content": [],
        "validated_content": None,
        "failed_urls": [],
        "attempt": 0,
    }
    app.invoke(initial_state)


if __name__ == "__main__":
    main()