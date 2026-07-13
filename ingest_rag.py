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


ARTICLE_PATTERN = re.compile(r"(?=제\s*\d+조(?:의\s*\d+)?\s*\()")
GUIDELINE_PATTERN = re.compile(r"(?=^\s*\d+\.\s+.+$)", re.MULTILINE)
ARTICLE_NO_PATTERN = re.compile(r"제\s*(\d+조(?:의\s*\d+)?)")

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
    if doc_type == "law":
        chunks = split_by_pattern(text, ARTICLE_PATTERN)
        if chunks:
            print("[INFO] 법률 문서: 조문 단위 청킹")
            return split_long_chunks(chunks)

    if doc_type == "guideline":
        chunks = split_by_pattern(text, GUIDELINE_PATTERN)
        if chunks:
            print("[INFO] 행정지침 문서: 번호 제목 단위 청킹")
            return split_long_chunks(chunks)

    print("[INFO] 일반 문서/약관: 글자 수 기반 청킹")
    docs = fallback_splitter.create_documents([text])
    return [doc.page_content for doc in docs]


def extract_article(chunk: str) -> str:
    match = ARTICLE_NO_PATTERN.search(chunk)
    return match.group(0).replace(" ", "") if match else "unknown"


def make_chunk_id(path: Path, index: int, chunk: str) -> str:
    raw = f"{path.as_posix()}::{index}::{chunk[:80]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def iter_source_files(base_path: str = RAG_PATH) -> list[Path]:
    base = Path(base_path)

    if not base.exists():
        print(f"[ERROR] RAG 폴더가 없습니다: {base_path}")
        return []

    files = list(base.rglob("*.txt")) + list(base.rglob("*.pdf"))
    return sorted(files)


def upsert_chunks(
    path: Path,
    doc_type: str,
    service_name: str,
    chunks: list[str],
) -> None:
    for index, chunk in enumerate(chunks):
        collection.upsert(
            ids=[make_chunk_id(path, index, chunk)],
            documents=[chunk],
            metadatas=[
                {
                    "type": doc_type,
                    "service_name": service_name,
                    "source": str(path),
                    "source_file": path.name,
                    "chunk_index": index,
                    "article": extract_article(chunk),
                    "content_hash": hashlib.md5(chunk.encode("utf-8")).hexdigest(),
                }
            ],
        )


def ingest_file(path: Path) -> bool:
    doc_type = infer_doc_type(path)
    service_name = infer_service_name(path, doc_type)

    if doc_type == "unknown":
        print(
            f"[WARNING] 문서 타입을 알 수 없습니다: {path.name} "
            "RAG/law, RAG/guideline, RAG/terms 하위에 넣어주세요."
        )

    print(f"[LOAD] {path}")
    print(f"[META] type={doc_type}, service_name={service_name}")

    text = load_file(path)

    if not text or not text.strip():
        print(f"[SKIP] 비어 있거나 읽을 수 없는 문서: {path}")
        return False

    chunks = chunk_text(text, doc_type)

    if not chunks:
        print(f"[SKIP] 청킹 결과 없음: {path}")
        return False

    upsert_chunks(path, doc_type, service_name, chunks)

    print(f"[DONE] {path.name} -> {len(chunks)} chunks")
    return True


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

    print()
    print(f"[SUMMARY] 성공: {success_count}")
    print(f"[SUMMARY] 실패: {fail_count}")
    print(f"[SUMMARY] 전체 파일: {len(files)}")
    print(f"[SUMMARY] DB 전체 청크 수: {collection.count()}")


if __name__ == "__main__":
    ingest_all()