from pathlib import Path
import sys

# FinePrint 프로젝트 루트를 파이썬 모듈 검색 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from Siyeong.search_utils import (
    hybrid_search,
    search_law_and_guideline,
)

def format_search_results(results: list[dict]) -> str:
    if not results:
        return "검색된 근거가 없습니다."

    formatted = []

    for index, result in enumerate(results, start=1):
        metadata = result.get("metadata", {})

        formatted.append(
            f"""
[근거 {index}]
내용: {result.get("text", "")}
문서 유형: {metadata.get("type", "unknown")}
서비스명: {metadata.get("service_name", "none")}
조항: {metadata.get("article", "unknown")}
출처: {metadata.get("source", "unknown")}
검색 점수: {result.get("score")}
""".strip()
        )

    return "\n\n".join(formatted)


def retrieve_rag_context(
    service_name: str,
    user_question: str,
    improvement_instruction: str = "",
) -> dict:
    query_parts = [user_question]

    if improvement_instruction:
        query_parts.append(improvement_instruction)

    search_query = "\n".join(query_parts)

    terms_results = hybrid_search(
        query=search_query,
        n_results=3,
        candidate_pool=15,
        doc_type="terms",
        service_name=service_name,
    )

    consumer_results = search_law_and_guideline(
        query=search_query,
        n_results=3,
        candidate_pool=15,
    )

    return {
        "terms_context": format_search_results(terms_results),
        "consumer_protection_context": format_search_results(
            consumer_results
        ),
    }