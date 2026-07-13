"""
ingest_rag.py
--------------------------------
문서 로딩, 청킹, 임베딩, ChromaDB 저장 담당 파일.

RAG 폴더 권장 구조:

RAG/
├── law/
├── guideline/
└── terms/
    ├── 넷플릭스/
    ├── 카카오/
    ├── 쿠팡/
    ├── 유튜브/
    └── 티빙/
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader


DB_PATH = "./db"
RAG_PATH = "./RAG"
COLLECTION_NAME = "RAG_system"
EMBEDDING_MODEL = "paraphrase-multilingual-mpnet-base-v2"


embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBEDDING_MODEL
)

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_fn,
)


def check_document_exists(service_name: str, doc_subtype: str | None = None) -> bool:
    """이 서비스의 (특정 종류) 약관/정책이 DB에 이미 존재하는지 확인 (Tavily 크롤링 여부 결정용).
    file_name이 아닌 service_name 기준으로 체크한다 —
    크롤링 전 시점에는 아직 file_name을 알 수 없기 때문.
    doc_subtype을 지정하면 "이용약관"과 "개인정보처리방침"처럼 같은 서비스의
    서로 다른 문서 종류를 구분해서 확인할 수 있다."""
    conditions = [
        {"service_name": service_name},
        {"type": "terms"},
    ]
    if doc_subtype is not None:
        conditions.append({"doc_subtype": doc_subtype})

    where = conditions[0] if len(conditions) == 1 else {"$and": conditions}
    results = collection.get(where=where)
    return len(results["ids"]) > 0

ARTICLE_PATTERN = re.compile(r"(?=제\s*\d+\s*조(?:\s*의\s*\d+)?)")
NUMBERED_OUTLINE_PATTERN = re.compile(r"(?=^\d+(?:\.\d+)*\.\s+.+$)", re.MULTILINE)
GUIDELINE_PATTERN = re.compile(r"(?=^\s*\d+\.\s+.+$)", re.MULTILINE)
ARTICLE_NO_PATTERN = re.compile(r"제\s*(\d+\s*조(?:\s*의\s*\d+)?)")

HEADING_ENDINGS = ("다", "요", "함", "임", "됨", "음", ".", ")", ":", "」")

fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=120,
)


def load_txt(path: Path) -> str | None:
    for encoding in ["utf-8-sig", "utf-8", "utf-16", "cp949", "euc-kr"]:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeError:
            continue

    print(f"[ERROR] 텍스트 파일 인코딩 실패: {path}")
    return None


def load_pdf(path: Path) -> str | None:
    reader = PdfReader(str(path))
    text = ""
    empty_pages = 0
    total_pages = len(reader.pages)

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text and page_text.strip():
            text += page_text + "\n"
        else:
            empty_pages += 1

    if total_pages > 0 and (
        empty_pages == total_pages or empty_pages / total_pages > 0.7
    ):
        print(
            f"[INFO] {path.name}: 텍스트 레이어가 거의 없습니다 "
            f"({empty_pages}/{total_pages} pages). OCR을 시도합니다."
        )

        ocr_text = ocr_pdf(path)
        if ocr_text:
            return ocr_text

        print(f"[WARNING] {path.name}: OCR 실패. 정리된 .txt 파일 사용을 권장합니다.")
        return None

    return text


def ocr_pdf(path: Path) -> str | None:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        print(
            "[ERROR] OCR을 사용하려면 pdf2image, pytesseract 설치가 필요합니다. "
            "추가로 poppler, tesseract-ocr 시스템 설치도 필요할 수 있습니다."
        )
        return None

    try:
        images = convert_from_path(str(path))
        text = ""

        for index, image in enumerate(images):
            text += pytesseract.image_to_string(image, lang="kor+eng") + "\n"
            print(f"[OCR] {path.name} - page {index + 1}/{len(images)}")

        return text if text.strip() else None

    except Exception as exc:
        print(f"[ERROR] OCR 처리 실패: {exc}")
        return None


def load_file(path: Path) -> str | None:
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return load_txt(path)

    if suffix == ".pdf":
        return load_pdf(path)

    return None


def infer_doc_type(path: Path) -> str:
    parts = path.parts

    if "law" in parts:
        return "law"

    if "guideline" in parts:
        return "guideline"

    if "terms" in parts:
        return "terms"

    return "unknown"


def infer_service_name(path: Path, doc_type: str) -> str:
    if doc_type != "terms":
        return "none"

    parts = path.parts

    if "terms" not in parts:
        return "unknown"

    terms_index = parts.index("terms")

    if len(parts) > terms_index + 1:
        return parts[terms_index + 1]

    return "unknown"


DOC_SUBTYPE_KEYWORDS = {
    "privacy_policy": ["개인정보", "프라이버시", "privacy"],
    "refund_policy": ["환불", "취소", "refund"],
    "payment_policy": ["결제", "자동결제", "payment"],
    "terms_of_use": ["이용약관", "서비스약관", "이용규칙", "terms"],
}


def infer_doc_subtype(path: Path) -> str:
    """파일명 키워드로 문서 종류를 구분 (이용약관 / 개인정보처리방침 / 환불정책 등).
    같은 service_name이라도 문서 종류가 다르면 check_document_exists에서
    별개로 취급해야 하므로 별도 필드로 관리한다."""
    name = path.stem

    for subtype, keywords in DOC_SUBTYPE_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return subtype

    return "unknown"


def clean_scraped_text(text: str) -> str:
    """웹 크롤링(아코디언/라벨 UI 등)으로 수집된 문서의 노이즈 정리."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    # "처리목적처리목적내용..." 처럼 라벨이 바로 반복되는 경우 정리
    text = re.sub(r"\b(\S{2,10})\1\b", r"\1", text)
    return text.strip()


def is_heading_line(line: str) -> bool:
    line = line.strip()
    if not (2 <= len(line) <= 20):
        return False
    if line.endswith(HEADING_ENDINGS):
        return False
    return True


def split_by_heading(text: str, min_parts: int = 3) -> list[str]:
    """제O조 형식이 아닌 소제목 기반 약관(예: 유튜브 서비스 약관) 분리.
    직전 소제목을 청크 맨 앞에 [소제목] 형태로 남겨 근거 추적에 사용."""
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current: list[str] = []
    current_heading = "본문"

    for line in lines:
        if is_heading_line(line) and current:
            sections.append((current_heading, "\n".join(current)))
            current_heading = line.strip()
            current = [line]
        else:
            current.append(line)

    if current:
        sections.append((current_heading, "\n".join(current)))

    result = [f"[{h}]\n{c.strip()}" for h, c in sections if c.strip()]
    return result if len(result) >= min_parts else []


def split_by_pattern(
    text: str,
    pattern: re.Pattern[str],
    min_parts: int = 3,
) -> list[str]:
    parts = [part.strip() for part in pattern.split(text) if part.strip()]
    return parts if len(parts) >= min_parts else []


def split_long_chunks(chunks: list[str], max_len: int = 1500) -> list[str]:
    result = []

    for chunk in chunks:
        if len(chunk) <= max_len:
            result.append(chunk)
        else:
            docs = fallback_splitter.create_documents([chunk])
            result.extend(doc.page_content for doc in docs)

    return result


def chunk_text(text: str, doc_type: str) -> list[str]:
    # 1순위: 제O조 형식 (law, terms 공통 - 카카오 이용약관 등)
    if doc_type in ("law", "terms"):
        chunks = split_by_pattern(text, ARTICLE_PATTERN)
        if chunks:
            print("[INFO] 조문(제O조) 단위 청킹")
            return split_long_chunks(chunks)

    # 2순위: 숫자 아웃라인 "1. Title" / "1.1. Title" (넷플릭스 영문 약관 등)
    if doc_type in ("law", "terms"):
        chunks = split_by_pattern(text, NUMBERED_OUTLINE_PATTERN)
        if chunks:
            print("[INFO] 숫자 아웃라인(1./1.1.) 단위 청킹")
            return split_long_chunks(chunks)

    # 3순위: 소제목 기반 (유튜브 서비스 약관 등, 번호 체계 없음)
    if doc_type in ("terms", "guideline"):
        chunks = split_by_heading(text)
        if chunks:
            print("[INFO] 소제목 단위 청킹")
            return split_long_chunks(chunks)

    # 4순위: 행정지침 번호 목록
    if doc_type == "guideline":
        chunks = split_by_pattern(text, GUIDELINE_PATTERN)
        if chunks:
            print("[INFO] 행정지침 문서: 번호 제목 단위 청킹")
            return split_long_chunks(chunks)

    print("[INFO] 일반 문서/약관: 글자 수 기반 청킹 (fallback)")
    docs = fallback_splitter.create_documents([text])
    return [doc.page_content for doc in docs]


def extract_article(chunk: str) -> str:
    match = ARTICLE_NO_PATTERN.search(chunk)
    return match.group(0).replace(" ", "") if match else "unknown"


def make_chunk_id(source_id: str, index: int, chunk: str) -> str:
    raw = f"{source_id}::{index}::{chunk[:80]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def delete_by_source(source_id: str) -> None:
    """같은 소스(파일 경로 / URL / 직접입력 식별자)에 속한 기존 청크를 전부 삭제.
    내용이 조금이라도 바뀌면 청크 경계/개수/ID가 통째로 달라지므로,
    upsert만으로는 구버전 청크가 잔존하는 문제를 막는다."""
    existing = collection.get(where={"source": source_id})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        print(f"[CLEANUP] 기존 청크 {len(existing['ids'])}개 삭제 (재삽입 전): {source_id}")


def upsert_chunks(
    source_id: str,
    source_label: str,
    doc_type: str,
    service_name: str,
    chunks: list[str],
    source_kind: str = "file",
    doc_subtype: str = "unknown",
) -> None:
    delete_by_source(source_id)

    if not chunks:
        return

    ids = []
    documents = []
    metadatas = []

    for index, chunk in enumerate(chunks):
        ids.append(make_chunk_id(source_id, index, chunk))
        documents.append(chunk)
        metadatas.append(
            {
                "type": doc_type,
                "doc_subtype": doc_subtype,  # terms_of_use / privacy_policy / refund_policy 등
                "service_name": service_name,
                "source": source_id,
                "source_file": source_label,
                "source_kind": source_kind,  # file / url / pasted
                "chunk_index": index,
                "article": extract_article(chunk),
                "content_hash": hashlib.md5(chunk.encode("utf-8")).hexdigest(),
            }
        )

    # 청크마다 upsert를 반복 호출하지 않고 한 번에 배치로 전송 (임베딩 계산도 배치로 처리됨)
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)


def ingest_text(
    source_id: str,
    source_label: str,
    doc_type: str,
    service_name: str,
    text: str,
    source_kind: str = "file",
    doc_subtype: str = "unknown",
) -> bool:
    """핵심 인제스트 로직. 파일이든 URL이든 직접입력이든,
    "고유 식별자 + 라벨 + 텍스트"만 있으면 동일하게 처리한다."""
    if not text or not text.strip():
        print(f"[SKIP] 비어 있는 텍스트: {source_label}")
        return False

    text = clean_scraped_text(text)
    chunks = chunk_text(text, doc_type)

    if not chunks:
        print(f"[SKIP] 청킹 결과 없음: {source_label}")
        return False

    upsert_chunks(source_id, source_label, doc_type, service_name, chunks, source_kind, doc_subtype)
    print(f"[DONE] {source_label} -> {len(chunks)} chunks")
    return True


ALLOWED_DOC_TYPES = {"law", "guideline", "terms"}


def _validate_manual_input(service_name: str, doc_type: str) -> None:
    """파일 경로 기반 추론(infer_doc_type/infer_service_name)의 안전망이 없는
    URL/직접입력 경로 전용 검증. 잘못된 값을 조용히 통과시키지 않고 즉시 실패시킨다."""
    if not service_name or not service_name.strip():
        raise ValueError("service_name은 빈 값일 수 없습니다.")

    if doc_type not in ALLOWED_DOC_TYPES:
        raise ValueError(
            f"doc_type='{doc_type}'은 허용되지 않습니다. {ALLOWED_DOC_TYPES} 중 하나여야 합니다."
        )


def ingest_from_url(
    url: str,
    service_name: str,
    extracted_text: str,
    doc_type: str = "terms",
    doc_subtype: str = "terms_of_use",
) -> bool:
    """URL에서 약관 본문을 성공적으로 추출한 경우 호출.
    실제 크롤링/추출(Tavily, Playwright, Trafilatura 등)은 이 함수 밖(탐색 담당 파트)에서 수행하고,
    추출된 텍스트만 여기로 넘긴다."""
    _validate_manual_input(service_name, doc_type)

    return ingest_text(
        source_id=url,
        source_label=url,
        doc_type=doc_type,
        service_name=service_name.strip(),
        text=extracted_text,
        source_kind="url",
        doc_subtype=doc_subtype,
    )


def ingest_from_pasted_text(
    service_name: str,
    pasted_text: str,
    doc_type: str = "terms",
    doc_subtype: str = "terms_of_use",
) -> bool:
    """URL에서 약관을 추출하지 못해 사용자가 직접 붙여넣은 텍스트를 처리."""
    _validate_manual_input(service_name, doc_type)

    service_name = service_name.strip()
    source_id = f"pasted::{service_name}::{hashlib.sha1(pasted_text.encode('utf-8')).hexdigest()[:12]}"
    return ingest_text(
        source_id=source_id,
        source_label=f"{service_name} (사용자 직접입력)",
        doc_type=doc_type,
        service_name=service_name,
        text=pasted_text,
        source_kind="pasted",
        doc_subtype=doc_subtype,
    )


def iter_source_files(base_path: str = RAG_PATH) -> list[Path]:
    base = Path(base_path)

    if not base.exists():
        print(f"[ERROR] RAG 폴더가 없습니다: {base_path}")
        return []

    files = list(base.rglob("*.txt")) + list(base.rglob("*.pdf"))
    return sorted(files)


def ingest_file(path: Path) -> bool:
    doc_type = infer_doc_type(path)
    service_name = infer_service_name(path, doc_type)
    doc_subtype = infer_doc_subtype(path)

    if doc_type == "unknown":
        print(
            f"[WARNING] 문서 타입을 알 수 없습니다: {path.name} "
            "RAG/law, RAG/guideline, RAG/terms 하위에 넣어주세요."
        )

    print(f"[LOAD] {path}")
    print(f"[META] type={doc_type}, service_name={service_name}, doc_subtype={doc_subtype}")

    text = load_file(path)

    return ingest_text(
        source_id=path.as_posix(),
        source_label=path.name,
        doc_type=doc_type,
        service_name=service_name,
        text=text or "",
        doc_subtype=doc_subtype,
    )


def sweep_stale_sources(base_path: str = RAG_PATH) -> None:
    """RAG 폴더에서 삭제되었거나 이름이 바뀐 '파일' 소스의 잔존 청크를 DB에서 정리.
    ingest_all() 전체 실행 후 1회 호출.
    URL/직접입력 소스(source_kind != "file")는 파일 시스템 스캔 대상이 아니므로 건드리지 않는다."""
    current_sources = {p.as_posix() for p in iter_source_files(base_path)}

    existing = collection.get(where={"source_kind": "file"})
    ids_to_delete = [
        chunk_id
        for chunk_id, meta in zip(existing["ids"], existing["metadatas"])
        if meta.get("source") not in current_sources
    ]

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
        print(f"[CLEANUP] 원본이 사라진(삭제/이름변경) 청크 {len(ids_to_delete)}개 정리")
    else:
        print("[CLEANUP] 정리할 구버전 청크 없음")


def ingest_all(base_path: str = RAG_PATH) -> None:
    files = iter_source_files(base_path)

    if not files:
        print(f"[WARNING] 처리할 파일이 없습니다: {base_path}")
        return

    success_count = 0
    fail_count = 0

    for path in files:
        try:
            if ingest_file(path):
                success_count += 1
            else:
                fail_count += 1

        except Exception as exc:
            print(f"[ERROR] 처리 실패: {path} / {exc}")
            fail_count += 1

    sweep_stale_sources(base_path)

    print()
    print(f"[SUMMARY] 성공: {success_count}")
    print(f"[SUMMARY] 실패: {fail_count}")
    print(f"[SUMMARY] 전체 파일: {len(files)}")
    print(f"[SUMMARY] DB 전체 청크 수: {collection.count()}")


if __name__ == "__main__":
    ingest_all()