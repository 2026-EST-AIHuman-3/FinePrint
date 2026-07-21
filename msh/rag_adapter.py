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
from Siyeong.ensure_service_ingested import prepare_knowledge_base

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

# 다른 서비스의 사례가 일반 가이드라인 검색 결과에 섞이는 것을 방지
KNOWN_SERVICE_NAMES = {
    "넷플릭스",
    "네이버",
    "카카오",
    "쿠팡",
    "티빙",
    "유튜브",
    "웨이브",
    "디즈니플러스",
    "배민",
    "코웨이",
}


def filter_other_service_examples(
    results: list,
    current_service: str,
) -> list:
    filtered_results = []

    for result in results:
        # hybrid_search 결과가 dict인 경우
        if isinstance(result, dict):
            content = (
                result.get("document")
                or result.get("content")
                or result.get("page_content")
                or ""
            )
            metadata = result.get("metadata", {})
        else:
            # LangChain Document 형태인 경우
            content = getattr(result, "page_content", "")
            metadata = getattr(result, "metadata", {}) or {}

        other_services = [
            service
            for service in KNOWN_SERVICE_NAMES
            if service != current_service
            and service in content
        ]

        if other_services:
            print(
                "[FILTER] 다른 서비스 사례 제외:",
                other_services,
                metadata.get("source", "출처 없음"),
            )
            continue

        filtered_results.append(result)

    return filtered_results

def retrieve_rag_context(
    service_name: str,
    user_question: str,
    improvement_instruction: str = "",
    policy_urls: dict[str, str] | None = None,
) -> dict:
    knowledge_base_status = prepare_knowledge_base(
        service_name,
        policy_urls=policy_urls,
    )
    canonical_service_name = str(
        knowledge_base_status.get("service_name", service_name)
    )
    query_parts = [user_question]

    if improvement_instruction:
        query_parts.append(improvement_instruction)

    search_query = "\n".join(query_parts)

    terms_results = hybrid_search(
        query=search_query,
        n_results=6,
        candidate_pool=20,
        doc_type="terms",
        service_name=canonical_service_name,
    )

    consumer_results = search_law_and_guideline(
        query=search_query,
        n_results=3,
        candidate_pool=15,
    )

    consumer_results = filter_other_service_examples(
        results=consumer_results,
        current_service=canonical_service_name,
    )[:3]

    return {
        "knowledge_base_status": knowledge_base_status,
        "terms_context": format_search_results(terms_results),
        "consumer_protection_context": format_search_results(
            consumer_results
        ),
    }
