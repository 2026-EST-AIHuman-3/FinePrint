"""
ensure_service_ingested.py
--------------------------------
DB에 없는 서비스 이용약관을 크롤링한 뒤 저장·인제스트하여
같은 프로세스에서 즉시 검색할 수 있도록 연결하는 wrapper.

흐름:
search_tos.py -> RAG/terms/<service>/terms.txt
-> ingest_rag.ingest_file() -> search_utils.collection

search_tos.py의 검색·선택·본문 추출 함수만 사용하며,
파일 저장은 서비스명 정규화를 위해 이 모듈에서 담당한다.
"""

from __future__ import annotations

import re
from pathlib import Path

from config import SERVICE_NAME_ALIASES, normalize_service_key
from ingest_rag import check_document_exists, ingest_file


RAG_TERMS_DIR = Path(__file__).resolve().parent / "RAG" / "terms"


def has_korean(text: str) -> bool:
    """문자열에 한글 완성형 문자가 포함되어 있는지 확인한다."""
    return bool(re.search(r"[\uac00-\ud7a3]", text))


def resolve_canonical_service_name(user_input: str) -> str:
    """입력된 서비스명을 DB 및 폴더에서 사용할 대표 이름으로 변환한다.

    기존 DB가 한글 폴더명을 사용하는 경우 한글 이름을 우선한다.
    별칭 테이블에 등록되지 않은 서비스는 공백을 제거한 입력값을 그대로 쓴다.
    """
    cleaned = user_input.strip()
    if not cleaned:
        raise ValueError("service_name은 빈 값일 수 없습니다.")

    normalized = normalize_service_key(cleaned)
    alias = SERVICE_NAME_ALIASES.get(normalized)

    if alias and has_korean(alias):
        return alias
    if has_korean(cleaned):
        return cleaned
    if alias:
        return alias
    return cleaned


def save_terms(service_name: str, content: str) -> Path:
    """크롤링한 약관을 RAG/terms/<service>/terms.txt에 UTF-8로 저장한다."""
    canonical_name = resolve_canonical_service_name(service_name)
    service_dir = RAG_TERMS_DIR / canonical_name
    service_dir.mkdir(parents=True, exist_ok=True)

    file_path = service_dir / "terms.txt"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def ensure_service_ingested(service_name: str) -> bool:
    """서비스 이용약관이 검색 가능한 상태인지 보장한다.

    이미 해당 서비스의 ``type=terms`` 및
    ``doc_subtype=terms_of_use`` 레코드가 있으면 크롤링을 생략한다.
    FAQ만 존재하는 경우에는 약관이 존재한다고 판단하지 않는다.

    약관이 없으면 검색, 원문 추출, 파일 저장, DB 인제스트를 순서대로
    실행하고 전체 과정의 성공 여부를 반환한다.
    """
    canonical_name = resolve_canonical_service_name(service_name)

    if check_document_exists(
        canonical_name,
        doc_subtype="terms_of_use",
    ):
        print(f"[SKIP] 이미 이용약관이 DB에 있음: {canonical_name}")
        return True

    # 약관이 이미 DB에 있으면 크롤링 의존성을 불러올 필요가 없다.
    # API 키나 선택적 패키지가 없는 환경에서도 DB 확인은 가능해야 한다.
    from search_tos import extract_raw_tos, search_tos, select_best_result

    print(f"[CRAWL] '{service_name}' 약관 검색 중...")

    search_results = search_tos(service_name)
    if not search_results:
        print(f"[FAIL] 검색 결과 없음: {service_name}")
        return False

    best = select_best_result(service_name, search_results)
    if best is None or not best.get("url"):
        print(f"[FAIL] 약관 페이지를 찾지 못함: {service_name}")
        return False

    selected_url = best["url"]
    print(f"[CRAWL] 선택된 URL: {selected_url}")

    raw_content = extract_raw_tos(selected_url)
    if not raw_content or not raw_content.strip():
        print(f"[FAIL] 본문 추출 실패: {selected_url}")
        return False

    file_path = save_terms(canonical_name, raw_content)
    print(f"[SAVE] {file_path}")

    success = ingest_file(file_path)
    if success:
        print(f"[DONE] '{canonical_name}' ingest 완료, 바로 검색 가능")
    else:
        print(f"[FAIL] '{canonical_name}' ingest 실패")
    return success


if __name__ == "__main__":
    name = input("확인/크롤링할 서비스명을 입력하세요: ").strip()
    try:
        ok = ensure_service_ingested(name)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        ok = False
    print("성공" if ok else "실패")
