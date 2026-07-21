# verify_rag.py
"""
DB 적재 및 검증 스크립트.

실행: python verify_rag.py
"""

import re
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

from search_utils import hybrid_search, collection, print_results

# 로그 파일 경로
LOG_PATH = Path("retrieval_logs.jsonl")


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


def log_retrieval_results(query, service, results, expected_articles, passed, missing, out_of_scope):
    """
    검색 결과와 판정 정보를 함께 로그에 저장.
    """
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query,
        "service": service,
        "expected_articles": list(expected_articles) if expected_articles else [],
        "out_of_scope": out_of_scope,
        "passed": passed if not out_of_scope else None,  # OOS는 통과/실패 없음
        "missing_articles": list(missing) if missing else [],
        "results": []
    }

    for rank, res in enumerate(results, start=1):
        meta = res.get("metadata", {})
        log_entry["results"].append({
            "rank": rank,
            "article": meta.get("article", "unknown"),
            "article_no": meta.get("article_no", "unknown"),
            "doc_subtype": meta.get("doc_subtype", "unknown"),
            "source": meta.get("source", "unknown"),
            "distance": res.get("distance"),
            "keyword_match": res.get("keyword_match"),
            "adjusted_score": res.get("score"),
            "text_preview": res.get("text", "")[:200] + "..." if res.get("text") else ""
        })

    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")



def test_faq_search(
    service_name,
    query,
    expected_keywords=None,
    top_k=5,
):
    results = hybrid_search(
        query=query,
        n_results=top_k,
        doc_type="faq",
        service_name=service_name,
    )

    if not results:
        print("[FAIL] FAQ 검색 결과가 없습니다.")
        return False

    for rank, result in enumerate(results, start=1):
        meta = result.get("metadata", {})
        searchable_text = " ".join([
            result.get("text", ""),
            str(meta.get("question", "")),
            str(meta.get("answer", "")),
        ]).lower()

        if expected_keywords and any(
            keyword.lower() in searchable_text
            for keyword in expected_keywords
        ):
            print(f"[PASS] FAQ 정답 발견: rank={rank}")
            return True

    print("[FAIL] FAQ 결과에서 예상 내용을 찾지 못했습니다.")
    return False


def test_search(service_name, query, expected_articles=None, max_rank=5, out_of_scope=False):
    """
    서비스명 필터링 검색 테스트.

    expected_articles: set(str) - 상위 max_rank 안에 포함되어야 할 조항 번호들
    max_rank: int - 검증할 상위 몇 개까지 볼 것인지
    out_of_scope: bool - 문서 범위 밖 질문인지 여부
    반환:
        True: 통과 (기대 조항 모두 포함)
        False: 실패 (일부 기대 조항 누락)
        None: Out-of-scope (통과/실패 판정 없음)
    """
    print(f"\n=== 검색 테스트: service='{service_name}', query='{query}' ===")
    print(f"기대 조항: {expected_articles if expected_articles else '없음'}")
    print(f"검증 범위: 상위 {max_rank}개")
    print(f"Out-of-scope: {out_of_scope}")

    results = hybrid_search(
        query=query,
        n_results=max_rank,
        doc_type="terms",
        service_name=service_name
    )

    if not results:
        print("[결과] 검색 결과가 없습니다.")
        # 결과가 없어도 로그는 남긴다
        log_retrieval_results(query, service_name, results, expected_articles or set(), False, set(), out_of_scope)
        return None if out_of_scope else False

    print_results(results, preview_chars=150)

    # Out-of-scope: 통과/실패 판정 없이 로그만 기록
    if out_of_scope:
        print("⚠️ Out-of-scope: Retrieval 순위만 기록하고 통과율에서 제외")
        log_retrieval_results(query, service_name, results, expected_articles or set(), None, set(), out_of_scope)
        return None

    # expected_articles가 없으면 검증 생략 (일반 테스트)
    if not expected_articles:
        print("⚠️ 기대 조항이 없어 검증 생략 (로그만 기록)")
        log_retrieval_results(query, service_name, results, set(), None, set(), False)
        return None

    # 상위 max_rank 내에서 기대 조항이 모두 포함되었는지 확인 (정확한 비교)
    found_articles = set()
    for res in results:
        article = res["metadata"].get("article", "")
        article_no = res["metadata"].get("article_no", "")

        for expected in expected_articles:
            # 정확한 비교: expected가 article 또는 article_no와 정확히 일치하는지
            if expected == article or expected == article_no:
                found_articles.add(expected)
                continue

            # 숫자만 추출한 값으로도 비교 (예: "제12조" → "12", "2.7." → "27")
            expected_normalized = re.sub(r"[^0-9]", "", expected)
            article_normalized = re.sub(r"[^0-9]", "", article)
            article_no_normalized = re.sub(r"[^0-9]", "", article_no)

            if expected_normalized and (
                expected_normalized == article_normalized or
                expected_normalized == article_no_normalized
            ):
                found_articles.add(expected)

    missing = expected_articles - found_articles

    passed = len(missing) == 0

    # 로그 기록 (판정 정보 포함)
    log_retrieval_results(query, service_name, results, expected_articles, passed, missing, out_of_scope)

    if missing:
        print(f"❌ 실패: 상위 {max_rank}개 내에 다음 조항이 없음: {missing}")
        return False
    else:
        print(f"✅ 성공: 모든 기대 조항이 상위 {max_rank}개 내에 포함됨")
        return True


def verify_article_extraction():
    """
    article과 article_no 추출 현황 확인.
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
    """전체 테스트 실행 및 로그 저장."""
    print("=== RAG 시스템 검증 시작 ===")

    if LOG_PATH.exists():
        LOG_PATH.unlink()
        print(f"[LOG] 기존 로그 삭제: {LOG_PATH}")

    # 1. 메타데이터 샘플
    show_metadata_samples(5)
    show_terms_subtypes()

    # 2. article 추출 현황
    verify_article_extraction()

    # ============================================================
    # 3. 약관(terms) 검색 테스트
    # ============================================================
    test_cases = [
        # 정상 작동 케이스 (5개)
        {"service": "티빙", "query": "티빙캐시 환불은 어떻게 하나요?", "expected_articles": {"제12조", "제17조"}, "max_rank": 5, "out_of_scope": False},
        {"service": "넷플릭스", "query": "cancellation refund policy", "expected_articles": {"2.7."}, "max_rank": 3, "out_of_scope": False},
        {"service": "유튜브", "query": "프리미엄 구독 취소 환불", "expected_articles": {"4."}, "max_rank": 5, "out_of_scope": False},
        # ✅ "자동결제 해지"는 FAQ 테스트로 이동했으므로 여기서 제거
        # {"service": "티빙", "query": "자동결제 해지는 어떻게 하나요?", "expected_articles": {"제15조"}, "max_rank": 5, "out_of_scope": False},
        {"service": "넷플릭스", "query": "membership cancellation", "expected_articles": {"2.6."}, "max_rank": 3, "out_of_scope": False},

        # 어려운 케이스
        {"service": "티빙", "query": "포인트로 결제한 캐시도 환불되나요?", "expected_articles": {"제12조"}, "max_rank": 5, "out_of_scope": False},

        # Out-of-scope (통과율에서 제외)
        {"service": "티빙", "query": "티빙 창업자는 누구인가요?", "expected_articles": set(), "max_rank": 3, "out_of_scope": True},
        {"service": "넷플릭스", "query": "넷플릭스 주가 전망", "expected_articles": set(), "max_rank": 3, "out_of_scope": True},
    ]

    terms_passed = 0
    terms_failed = 0
    terms_skipped = 0

    for tc in test_cases:
        result = test_search(
            service_name=tc["service"],
            query=tc["query"],
            expected_articles=set(tc["expected_articles"]) if tc["expected_articles"] else set(),
            max_rank=tc["max_rank"],
            out_of_scope=tc.get("out_of_scope", False)
        )

        if result is True:
            terms_passed += 1
        elif result is False:
            terms_failed += 1
        else:
            terms_skipped += 1

    # ============================================================
    # 4. FAQ 검색 테스트 (신규 추가)
    # ============================================================
    print("\n=== FAQ 검색 테스트 ===")

    faq_tests = [
        {
            "service": "티빙",
            "query": "자동결제를 해지하려면 어떻게 해야 하나요?",
            "expected_keywords": ["자동결제", "정기결제", "해지"],
            "top_k": 5,
        },
        # 추가 FAQ 테스트가 있다면 여기에 추가
    ]

    faq_passed = 0
    faq_total = len(faq_tests)

    for ft in faq_tests:
        if test_faq_search(
            service_name=ft["service"],
            query=ft["query"],
            expected_keywords=ft["expected_keywords"],
            top_k=ft["top_k"],
        ):
            faq_passed += 1

    # ============================================================
    # 5. 최종 결과 출력
    # ============================================================
    print(f"\n=== 검증 결과 ===")
    print(f"[약관 검색]")
    print(f"  ✅ 통과: {terms_passed}")
    print(f"  ❌ 실패: {terms_failed}")
    print(f"  ⏭️ 제외 (Out-of-scope): {terms_skipped}")
    terms_total = terms_passed + terms_failed
    if terms_total > 0:
        print(f"  📊 통과율: {terms_passed}/{terms_total} = {terms_passed/terms_total*100:.1f}%")

    print(f"\n[FAQ 검색]")
    print(f"  ✅ 통과: {faq_passed}/{faq_total}")

    print(f"\n📁 로그 저장 위치: {LOG_PATH}")


if __name__ == "__main__":
    run_all_tests()