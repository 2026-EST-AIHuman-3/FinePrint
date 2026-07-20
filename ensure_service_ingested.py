"""
ensure_service_ingested.py
--------------------------------
"DB에 없는 서비스 약관을 그 자리에서 크롤링해 즉시 검색 가능하게 만든다"는
동적 참조 시나리오를 위한 wrapper.

크롤링(search_tos.py) -> 저장(RAG/terms/<service>/terms.txt)
-> ingest(ingest_rag.ingest_file) -> 검색(search_utils.collection)
까지를 한 프로세스 안에서 순서대로 처리한다.

search_tos.py는 건드리지 않는다 —
search_tos / select_best_result / extract_raw_tos 세 함수만 가져다 쓰고,
저장은 이 파일의 save_terms()가 alias 테이블을 참고해 별도로 처리한다.
기존 save_tos_to_file()은 사용하지 않는다.
"""

from __future__ import annotations

import re
from pathlib import Path

from config import SERVICE_NAME_ALIASES, normalize_service_key
from ingest_rag import ingest_file, check_document_exists


RAG_TERMS_DIR = Path(__file__).resolve().parent / "RAG" / "terms"


def has_korean(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text))


def resolve_canonical_service_name(user_input: str) -> str:
    """SERVICE_NAME_ALIASES를 참고해 폴더명(=DB의 service_name)으로 쓸 이름을 정한다.
    기존 DB 컨벤션(한글 폴더명)을 우선하고, 테이블에 없는 새 서비스는 입력값 그대로 쓴다.
    SERVICE_NAME_ALIASES는 한글->영문/영문->한글 양방향으로 등록돼 있어서,
    단순 조회만 하면 한글 입력이 영문으로 뒤집힐 수 있으므로 방향을 명시적으로 정리한다."""
    normalized = normalize_service_key(user_input)
    alias = SERVICE_NAME_ALIASES.get(normalized)

    if alias and has_korean(alias):
        return alias          # 영문 입력("tving") -> 기존 한글 폴더("티빙")로 매핑
    if has_korean(user_input):
        return user_input     # 이미 한글로 입력했으면 그대로 사용
    if alias:
        return alias          # 한글 별칭이 없는 예외적인 경우
    return user_input         # alias 테이블에 없는 완전히 새로운 서비스


def save_terms(service_name: str, content: str) -> Path:
    """RAG/terms/<canonical_service_name>/terms.txt 로 저장.
    ingest_rag.infer_service_name이 이 경로 규칙(RAG/terms/<service>/*)을
    그대로 폴더명 기준 service_name 추론에 사용하므로, 여기서 정확한
    이름으로 저장해두는 것이 중요하다."""
    canonical_name = resolve_canonical_service_name(service_name)
    service_dir = RAG_TERMS_DIR / canonical_name
    service_dir.mkdir(parents=True, exist_ok=True)

    file_path = service_dir / "terms.txt"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def ensure_service_ingested(service_name: str) -> bool:
    """service_name의 약관이 DB에 이미 있으면 True를 즉시 반환.
    없으면 크롤링 -> 저장 -> ingest까지 수행한 뒤 성공 여부를 반환한다.

    ingest 후 동일 프로세스 내에서 바로 검색 가능하도록
    ingest_rag와 search_utils가 같은 collection 객체를 공유한다.
    """
    canonical_name = resolve_canonical_service_name(service_name)

    if check_document_exists(
        canonical_name,
        doc_subtype="terms_of_use",
    ):
        print(f"[SKIP] 이미 이용약관이 DB에 있음: {canonical_name}")
        return True
    # 여기부터 실제 크롤링 필요
    from search_tos import (
        search_tos,
        select_best_result,
        extract_raw_tos,
    )

    print(f"[CRAWL] '{service_name}' 약관 검색 중...")

    search_results = search_tos(service_name)
    if not search_results:
        print(f"[FAIL] 검색 결과 없음: {service_name}")
        return False

    best = select_best_result(service_name, search_results)
    if best is None:
        print(f"[FAIL] 약관 페이지를 찾지 못함: {service_name}")
        return False

    print(f"[CRAWL] 선택된 URL: {best['url']}")
    raw_content = extract_raw_tos(best["url"])
    if not raw_content:
        print(f"[FAIL] 본문 추출 실패: {best['url']}")
        return False

    file_path = save_terms(service_name, raw_content)
    print(f"[SAVE] {file_path}")

    success = ingest_file(file_path)
    if success:
        print(f"[DONE] '{canonical_name}' ingest 완료, 바로 검색 가능")
    return success


if __name__ == "__main__":
    # 간단한 수동 테스트용. 실제 서비스 코드에서는 agent가 이 함수를
    # 질문 처리 흐름 안에서 직접 호출하면 된다.
    name = input("확인/크롤링할 서비스명을 입력하세요: ").strip()
    ok = ensure_service_ingested(name)
    print("성공" if ok else "실패")