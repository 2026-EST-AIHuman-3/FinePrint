"""
check_db_status.py
--------------------------------
ingest_rag.py로 저장해둔 ChromaDB 상태를 점검하는 스크립트.
같은 폴더에서 실행: python check_db_status.py
"""

from collections import Counter
from ingest_rag import collection


def main():
    total = collection.count()
    print(f"전체 청크 수: {total}\n")

    if total == 0:
        print("DB가 비어 있습니다.")
        return

    all_data = collection.get()
    metadatas = all_data["metadatas"]

    # 1. 서비스별 청크 수
    service_counter = Counter(m.get("service_name", "none") for m in metadatas)
    print("== 서비스별 청크 수 ==")
    for service, count in sorted(service_counter.items(), key=lambda x: -x[1]):
        print(f"  {service}: {count}")

    # 2. 문서 종류(type)별 청크 수
    type_counter = Counter(m.get("type", "unknown") for m in metadatas)
    print("\n== 문서 타입(type)별 청크 수 ==")
    for doc_type, count in type_counter.items():
        print(f"  {doc_type}: {count}")

    # 3. doc_subtype별 청크 수
    #    - law/guideline 문서도 파일명 키워드에 따라 doc_subtype이 채워질 수 있으나
    #      (예: "개인정보보호법.txt" -> privacy_policy), 실제로 doc_subtype이 의미를 갖는 건
    #      check_document_exists()가 필터로 쓰는 type=="terms" 문서뿐이다.
    #      따라서 전체 통계와 terms-only 통계를 분리해서 보여준다.
    subtype_counter = Counter(m.get("doc_subtype", "(필드 없음)") for m in metadatas)
    print("\n== doc_subtype별 청크 수 (전체, law/guideline 포함) ==")
    for subtype, count in subtype_counter.items():
        print(f"  {subtype}: {count}")

    terms_metadatas = [m for m in metadatas if m.get("type") == "terms"]
    terms_subtype_counter = Counter(m.get("doc_subtype", "(필드 없음)") for m in terms_metadatas)
    print("\n== doc_subtype별 청크 수 (terms 문서만 - 실제 의미있는 집계) ==")
    for subtype, count in terms_subtype_counter.items():
        print(f"  {subtype}: {count}")

    # 4. source_kind별 청크 수 (file/url/pasted)
    kind_counter = Counter(m.get("source_kind", "(필드 없음)") for m in metadatas)
    print("\n== source_kind별 청크 수 ==")
    for kind, count in kind_counter.items():
        print(f"  {kind}: {count}")

    # 4-1. scope별 청크 수 (service_specific / shared - 여러 서비스 공통 문서 여부)
    scope_counter = Counter(m.get("scope", "(필드 없음)") for m in metadatas)
    print("\n== scope별 청크 수 ==")
    for scope, count in scope_counter.items():
        print(f"  {scope}: {count}")
    shared_sources = sorted({
        (m.get("service_name"), m.get("source_file"))
        for m in metadatas
        if m.get("scope") == "shared"
    })
    if shared_sources:
        print("  ⚠️  shared로 분류된 문서 (다른 서비스와 내용이 섞여 있을 수 있음):")
        for service, source_file in shared_sources:
            print(f"     - {service}: {source_file}")

    # 5. 구버전 스키마(신규 필드 없음) 잔존 여부 체크 - 핵심 확인 포인트
    legacy_count = sum(
        1 for m in metadatas
        if "doc_subtype" not in m or "source_kind" not in m
    )
    print(f"\n== 구버전 스키마(doc_subtype/source_kind 필드 없음) 청크 수: {legacy_count} ==")
    if legacy_count > 0:
        print("⚠️  구버전 스키마로 저장된 청크가 남아있습니다.")
        print("    → 스키마가 섞여있으면 검색/필터링 시 혼란이 생길 수 있으니,")
        print("      ./db 를 삭제하고 python ingest_rag.py 를 다시 실행하는 걸 권장합니다.")
    else:
        print("✅ 모든 청크가 신규 스키마로 일관되게 저장되어 있습니다.")

    # 6. 서비스별 문서 종류 커버리지 (빠진 조합 파악용)
    print("\n== 서비스 x 문서종류 커버리지 ==")
    combos = set(
        (m.get("service_name", "none"), m.get("doc_subtype", "unknown"))
        for m in metadatas
        if m.get("service_name", "none") != "none"
    )
    for service, subtype in sorted(combos):
        print(f"  {service} - {subtype}")


if __name__ == "__main__":
    main()