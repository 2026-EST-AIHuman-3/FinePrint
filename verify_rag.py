# verify_rag.py - 전체 코드 수정

"""
DB 적재 및 검증 스크립트.

실행: python verify_rag.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from search_utils import hybrid_search, collection, print_results

def show_terms_subtypes():
    data = collection.get(where={"type": "terms"})

    print("\n=== 이용약관·정책 파일별 doc_subtype ===")
    seen = set()

    for meta in data["metadatas"]:
        key = (
            meta.get("service_name"),
            meta.get("source_file"),
            meta.get("doc_subtype", "unknown"),
            meta.get("ingest_schema_version"),
        )

        if key in seen:
            continue

        seen.add(key)
        print(
            f"service={key[0]} | "
            f"file={key[1]} | "
            f"doc_subtype={key[2]} | "
            f"schema={key[3]}"
        )

def show_metadata_samples(limit=5):
    """저장된 문서의 메타데이터 샘플을 출력."""
    all_data = collection.get(limit=limit)
    if not all_data["ids"]:
        print("[INFO] DB가 비어 있습니다. ingest_rag.py를 먼저 실행하세요.")
        return
    

    print("\n=== DB 메타데이터 샘플 (첫 %d개) ===" % limit)
    for i, meta in enumerate(all_data["metadatas"]):
        print(f"[{i+1}]")
        print(f"  service_name: {meta.get('service_name')}")
        print(f"  type:         {meta.get('type')}")
        print(f"  doc_subtype:  {meta.get('doc_subtype', 'unknown')}")
        print(f"  article:      {meta.get('article', 'unknown')}")
        print(f"  article_no:   {meta.get('article_no', 'unknown')}")
        print(f"  source:       {meta.get('source')}")
        doc = all_data["documents"][i]
        preview = doc[:100].replace('\n', ' ') + "..."
        print(f"  chunk:        {preview}")
        print("-" * 50)


def test_search(service_name, query, expected_articles=None, max_rank=5):
    """
    서비스명 필터링 검색 테스트.
    
    expected_articles: set(str) - 상위 max_rank 안에 포함되어야 할 조항 번호들
    max_rank: int - 검증할 상위 몇 개까지 볼 것인지
    """
    print(f"\n=== 검색 테스트: service='{service_name}', query='{query}' ===")
    print(f"기대 조항: {expected_articles if expected_articles else '없음'}")
    print(f"검증 범위: 상위 {max_rank}개")
    
    results = hybrid_search(
        query=query,
        n_results=max_rank,
        doc_type="terms",
        service_name=service_name
    )
    
    if not results:
        print("[결과] 검색 결과가 없습니다.")
        return False

    print_results(results, preview_chars=150)

    # expected_articles가 없으면 단순 통과
    if not expected_articles:
        print("⚠️ 기대 조항이 없어 검증 생략")
        return True

    # 상위 max_rank 내에서 기대 조항이 모두 포함되었는지 확인
    found_articles = set()
    for res in results:
        article = res["metadata"].get("article_no", "")
        # article에서 숫자/특수문자 제거한 값으로도 비교 (2.7. → 27)
        article_normalized = re.sub(r"[^0-9]", "", article)
        
        for expected in expected_articles:
            expected_normalized = re.sub(r"[^0-9]", "", expected)
            if expected in article or expected_normalized in article_normalized:
                found_articles.add(expected)

    missing = expected_articles - found_articles
    
    if missing:
        print(f"❌ 실패: 상위 {max_rank}개 내에 다음 조항이 없음: {missing}")
        return False
    else:
        print(f"✅ 성공: 모든 기대 조항이 상위 {max_rank}개 내에 포함됨")
        return True


def verify_article_extraction():
    """
    article과 article_no 추출 현황 확인.
    
    실제 추출 기준:
    - 한국어 "제12조"   → article="제12조", article_no="12조"
    - 영문 "2.7."       → article="2.7.", article_no="2.7"
    - 대괄호 "[계약]"   → article="[계약]", article_no="unknown"
    - 연도 "2026."      → article="2026." (오탐, 패턴 수정 필요)
    """
    all_data = collection.get()
    if not all_data["ids"]:
        print("[INFO] DB가 비어 있습니다.")
        return

    print("\n=== article / article_no 추출 현황 ===")
    stats = {"total": 0, "has_article": 0, "has_article_no": 0}
    samples = []
    
    for meta, doc in zip(all_data["metadatas"], all_data["documents"]):
        stats["total"] += 1
        if meta.get("article") and meta.get("article") != "unknown":
            stats["has_article"] += 1
        if meta.get("article_no") and meta.get("article_no") != "unknown":
            stats["has_article_no"] += 1
        if len(samples) < 5:
            samples.append((
                meta.get("service_name"),
                meta.get("article"),
                meta.get("article_no"),
                doc[:80]
            ))

    print(f"전체 청크 수: {stats['total']}")
    print(f"article 있음: {stats['has_article']} ({stats['has_article']/stats['total']*100:.1f}%)")
    print(f"article_no 있음: {stats['has_article_no']} ({stats['has_article_no']/stats['total']*100:.1f}%)")
    print("\n⚠️ 주의: '있음' 비율이 높다고 무조건 좋은 것은 아닙니다.")
    print("   - 조항 구조가 없는 문서는 unknown이 정상입니다.")
    print("   - 숫자로 시작한다고 모두 실제 조항인 것은 아니므로 샘플 확인이 필요합니다.\n")

    print("샘플 청크:")
    for svc, art, art_no, doc in samples:
        print(f"  service: {svc}, article: {art}, article_no: {art_no}")
        print(f"    청크: {doc}...")


def run_all_tests():
    print("=== RAG 시스템 검증 시작 ===")

    # 1. 메타데이터 샘플
    show_metadata_samples(5)

    show_terms_subtypes()

    # 2. article 추출 현황
    verify_article_extraction()

    # 3. 검색 테스트 (엄격한 기준)
    test_cases = [
        {
            "service": "티빙",
            "query": "티빙캐시 환불은 어떻게 하나요?",
            "expected_articles": {"제12조", "제17조"},  # 둘 다 상위 5개 안에 있어야 함
            "max_rank": 5,
        },
        {
            "service": "넷플릭스",
            "query": "cancellation refund policy",
            "expected_articles": {"2.7."},  # Refund Requests 조항
            "max_rank": 3,
        },
        {
            "service": "유튜브",
            "query": "프리미엄 구독 취소 환불",
            "expected_articles": {"4."},  # 취소 및 환불 섹션
            "max_rank": 5,
        },
    ]

    passed = 0
    for tc in test_cases:
        result = test_search(
            service_name=tc["service"],
            query=tc["query"],
            expected_articles=set(tc["expected_articles"]),
            max_rank=tc["max_rank"]
        )
        if result:
            passed += 1

    print(f"\n=== 검증 결과: {passed}/{len(test_cases)} 통과 ===")


if __name__ == "__main__":
    run_all_tests()