"""FinePrint의 수집 -> 인제스트 -> 검색 준비 흐름을 연결한다.

최종 수집기인 ``jhc.search_fineprint_v2``가 공용 데이터 폴더에 문서를
저장하면, 이 모듈이 같은 파일을 ChromaDB에 즉시 인제스트한다.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    from .config import (
        COLLECTED_DATA_PATH,
        DATA_PATH,
        SERVICE_NAME_ALIASES,
        normalize_service_key,
    )
    from .ingest_rag import (
        check_document_exists,
        ingest_faq_file,
        ingest_file,
        ingest_uploaded_file,
    )
    from .search_utils import collection, warm_vector_index
except ImportError:
    from config import (
        COLLECTED_DATA_PATH,
        DATA_PATH,
        SERVICE_NAME_ALIASES,
        normalize_service_key,
    )
    from ingest_rag import (
        check_document_exists,
        ingest_faq_file,
        ingest_file,
        ingest_uploaded_file,
    )
    from search_utils import collection, warm_vector_index


DATA_ROOT = Path(DATA_PATH)
COLLECTED_DATA_ROOT = Path(COLLECTED_DATA_PATH)
TERMS_DATA_DIRS = (
    DATA_ROOT / "terms",
    COLLECTED_DATA_ROOT / "terms",
)
POLICY_SUBTYPES = {
    "terms": "terms_of_use",
    "privacy": "privacy_policy",
}
_reference_data_ready = False
_service_collection_attempted: set[str] = set()


def has_korean(text: str) -> bool:
    return bool(re.search(r"[\uac00-\ud7a3]", text))


def resolve_canonical_service_name(user_input: str) -> str:
    """영문/한글 별칭을 기존 DB 폴더명과 맞는 대표 서비스명으로 변환한다."""
    cleaned = user_input.strip()
    if not cleaned:
        raise ValueError("service_name은 빈 값일 수 없습니다.")

    alias = SERVICE_NAME_ALIASES.get(normalize_service_key(cleaned))
    if alias and has_korean(alias):
        return alias
    if has_korean(cleaned):
        return cleaned
    return alias or cleaned


def _policy_status(service_name: str) -> dict[str, bool]:
    return {
        document_type: check_document_exists(service_name, subtype)
        for document_type, subtype in POLICY_SUBTYPES.items()
    }


def _matching_service_directories(service_name: str) -> list[Path]:
    canonical_name = resolve_canonical_service_name(service_name)
    matches: list[Path] = []
    for terms_data_dir in TERMS_DATA_DIRS:
        if not terms_data_dir.is_dir():
            continue
        for directory in terms_data_dir.iterdir():
            if not directory.is_dir():
                continue
            if resolve_canonical_service_name(directory.name) == canonical_name:
                matches.append(directory)
    return matches


def ingest_local_service_documents(service_name: str) -> int:
    """이미 수집되어 있는 서비스 문서를 먼저 DB에 반영한다."""
    success_count = 0
    for directory in _matching_service_directories(service_name):
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() in {".txt", ".pdf"}:
                success_count += int(ingest_file(path))
            elif path.suffix.lower() == ".json":
                success_count += int(ingest_faq_file(path))
    return success_count


def _has_document_type(doc_type: str) -> bool:
    result = collection.get(where={"type": doc_type}, limit=1)
    return bool(result.get("ids"))


def ensure_reference_data_ingested() -> bool:
    """소비자 보호 법률·가이드라인을 프로세스당 한 번 준비한다."""
    global _reference_data_ready
    if _reference_data_ready:
        return True

    required_types = ("law", "guideline")
    if all(_has_document_type(doc_type) for doc_type in required_types):
        _reference_data_ready = True
        return True

    for folder_name in required_types:
        folder = DATA_ROOT / folder_name
        if not folder.is_dir():
            print(f"[WARNING] 소비자 보호 데이터 폴더가 없습니다: {folder}")
            continue
        for path in sorted(folder.rglob("*")):
            if path.suffix.lower() not in {".txt", ".pdf"}:
                continue
            try:
                ingest_file(path)
            except Exception as exc:
                print(f"[ERROR] 소비자 보호 문서 인제스트 실패: {path} / {exc}")

    _reference_data_ready = all(
        _has_document_type(doc_type) for doc_type in required_types
    )
    return _reference_data_ready


def ensure_service_ingested(
    service_name: str,
    policy_urls: dict[str, str] | None = None,
) -> bool:
    """URL·로컬 문서를 우선 사용하고, 부족하면 자동 수집 후 즉시 인제스트한다."""
    canonical_name = resolve_canonical_service_name(service_name)
    explicit_urls = {
        document_type: url.strip()
        for document_type, url in (policy_urls or {}).items()
        if url and url.strip()
    }
    invalid_types = [name for name in explicit_urls if name not in POLICY_SUBTYPES]
    if invalid_types:
        raise ValueError(f"지원하지 않는 URL 문서 유형입니다: {invalid_types}")

    status = _policy_status(canonical_name)
    if all(status.values()) and not explicit_urls:
        print(f"[SKIP] 서비스 약관·정책이 DB에 있음: {canonical_name}")
        return True

    ingest_local_service_documents(canonical_name)
    status = _policy_status(canonical_name)
    missing_types = [name for name, exists in status.items() if not exists]
    requested_types = tuple(dict.fromkeys([*explicit_urls, *missing_types]))
    if not requested_types:
        return True
    if canonical_name in _service_collection_attempted and not explicit_urls:
        return any(status.values())

    _service_collection_attempted.add(canonical_name)

    try:
        from jhc.search_fineprint_v2 import collect_service_policies

        saved_paths = collect_service_policies(
            service_name=canonical_name,
            output_root=COLLECTED_DATA_ROOT,
            document_types=requested_types,
            policy_urls=explicit_urls,
            allow_manual_url=False,
        )
    except Exception as exc:
        print(f"[ERROR] 약관·정책 자동 수집 실패: {canonical_name} / {exc}")
        saved_paths = []

    for path in saved_paths:
        try:
            ingest_file(path)
        except Exception as exc:
            print(f"[ERROR] 수집 문서 인제스트 실패: {path} / {exc}")

    final_status = _policy_status(canonical_name)
    # 하나의 공식 정책만 확보된 경우에도 기존 근거로 질문 처리는 가능하다.
    return any(final_status.values())


def prepare_knowledge_base(
    service_name: str,
    policy_urls: dict[str, str] | None = None,
) -> dict[str, object]:
    """Agent 검색 전에 두 지식베이스를 준비하고 상태를 반환한다."""
    canonical_name = resolve_canonical_service_name(service_name)
    reference_ready = ensure_reference_data_ingested()
    service_ready = ensure_service_ingested(canonical_name, policy_urls=policy_urls)
    if reference_ready or service_ready:
        warm_vector_index()
    policy_status = _policy_status(canonical_name)
    missing_policy_types = [
        document_type
        for document_type, is_ready in policy_status.items()
        if not is_ready
    ]
    return {
        "service_name": canonical_name,
        "service_documents_ready": service_ready,
        "reference_documents_ready": reference_ready,
        "policy_status": policy_status,
        "missing_policy_types": missing_policy_types,
        "requires_policy_input": bool(missing_policy_types),
    }


def ingest_user_document(
    path: str | Path,
    service_name: str,
    doc_subtype: str | None = None,
) -> bool:
    """PDF/TXT 직접 업로드 시 UI가 호출할 공개 진입점."""
    canonical_name = resolve_canonical_service_name(service_name)
    return ingest_uploaded_file(
        path=path,
        service_name=canonical_name,
        doc_type="terms",
        doc_subtype=doc_subtype,
    )


def ingest_user_url(
    url: str,
    service_name: str,
    document_type: str = "terms",
) -> bool:
    """사용자가 지정한 공식 URL을 수집·저장하고 즉시 인제스트한다."""
    if document_type not in POLICY_SUBTYPES:
        raise ValueError(f"지원하지 않는 문서 유형입니다: {document_type}")

    canonical_name = resolve_canonical_service_name(service_name)
    try:
        from jhc.search_fineprint_v2 import collect_service_policies

        saved_paths = collect_service_policies(
            service_name=canonical_name,
            output_root=COLLECTED_DATA_ROOT,
            document_types=(document_type,),
            policy_urls={document_type: url},
            allow_manual_url=False,
        )
    except Exception as exc:
        print(f"[ERROR] 사용자 URL 수집 실패: {url} / {exc}")
        return False

    return bool(saved_paths) and all(ingest_file(path) for path in saved_paths)


if __name__ == "__main__":
    name = input("확인/수집할 서비스명을 입력하세요: ").strip()
    try:
        result = prepare_knowledge_base(name)
    except ValueError as exc:
        print(f"[FAIL] {exc}")
    else:
        print(result)
