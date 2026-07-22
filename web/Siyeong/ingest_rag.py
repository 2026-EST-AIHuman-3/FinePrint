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
from datetime import datetime, timezone
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from PyPDF2 import PdfReader
import json

# search_utils.py가 이미 만들어둔 collection을 그대로 재사용한다.
# ingest와 search가 각자 별도의 PersistentClient 인스턴스를 갖고 있으면
# (같은 프로세스 안에서도) 한쪽이 쓴 내용이 다른 쪽에 바로 반영된다는 보장이 없어서,
# "크롤링 -> ingest -> 바로 검색" 같은 한 흐름 안에서 방금 넣은 데이터가 안 보이는
# 문제가 생길 수 있다. 객체를 하나로 통일해 이 문제를 원천적으로 없앤다.
try:
    from .config import DATA_PATH
    from .search_utils import collection
except ImportError:
    from config import DATA_PATH
    from search_utils import collection

# 실행 위치에 따라 달라지던 ./RAG 대신 세 모듈이 공유하는 절대 데이터 경로를 사용한다.
RAG_PATH = str(DATA_PATH)

# 청킹 방식이나 메타데이터 구조가 바뀌면 값을 올린다.
# 본문이 같아도 이전 스키마로 저장된 레코드는 다시 인제스트되어야 한다.
INGEST_SCHEMA_VERSION = 5


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
NUMBERED_OUTLINE_PATTERN = re.compile(r"(?=^\d{1,3}(?:\.\d+)*\.\s+.+$)", re.MULTILINE)
GUIDELINE_PATTERN = re.compile(r"(?=^\s*\d+\.\s+.+$)", re.MULTILINE)
ARTICLE_NO_PATTERN = re.compile(r"제\s*(\d+\s*조(?:\s*의\s*\d+)?)")
NUMBERED_SECTION_PATTERN = re.compile(
    r"^\s*(\d{1,3}(?:\.\d+)*\.)\s+",  # {1,3} 추가!
    re.MULTILINE,
)
BRACKET_HEADING_PATTERN = re.compile(r"^\s*\[([^\]\r\n]{1,100})\]")

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


def is_ocr_quality_acceptable(text: str, path_name: str) -> bool:
    """OCR이 '성공'해도 실제로는 깨진 글자만 나온 경우를 걸러낸다."""
    if len(text.strip()) < 100:
        print(f"[WARNING] OCR 결과가 너무 짧습니다 ({len(text.strip())}자): {path_name}")
        return False

    korean_chars = sum(1 for c in text if "\uac00" <= c <= "\ud7a3")
    korean_ratio = korean_chars / len(text) if text else 0
    if korean_ratio < 0.1:
        print(
            f"[WARNING] OCR이 한글을 제대로 인식하지 못한 것으로 보입니다 "
            f"(한글 비율 {korean_ratio:.1%}): {path_name}"
        )
        return False

    return True


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

        if not text.strip():
            return None

        if not is_ocr_quality_acceptable(text, path.name):
            print(f"[FAIL] OCR 품질 검증 실패, 정리된 .txt 파일 사용을 권장합니다: {path.name}")
            return None

        return text

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


def infer_faq_service_name(path: Path) -> str:
    """FAQ 파일 경로 기반 service_name 추론.
    RAG/terms/<service>/*.json 또는 RAG/faq/<service>/*.json 형태면 해당 폴더명 사용.
    그 외(법률/공통 FAQ 등 특정 서비스에 속하지 않는 경우)는 law/guideline과 동일하게 'none'.
    infer_service_name과 달리, 하위 폴더가 없어 파일명이 그대로 service_name으로
    잘못 흡수되는 경우(RAG/faq/kca_faq.json -> "kca_faq")를 명시적으로 걸러낸다."""
    parts = path.parts

    if "terms" in parts:
        terms_index = parts.index("terms")
        if len(parts) > terms_index + 1:
            return parts[terms_index + 1]

    if "faq" in parts:
        faq_index = parts.index("faq")
        # parts[faq_index+1]이 파일명 자체라면(하위 폴더 없이 바로 파일) 서비스 폴더가 아니므로 제외
        if len(parts) > faq_index + 1 and parts[faq_index + 1] != path.name:
            return parts[faq_index + 1]

    return "none"


DOC_SUBTYPE_KEYWORDS = {
    "terms_of_use": [           # ⭐ 1순위: 이용약관 먼저 검사
        "이용약관",
        "서비스약관",
        "이용규칙",
        "terms_of_use",
        "terms-of-use",
        "terms",                # tos는 제외!
    ],
    "privacy_policy": [
        "개인정보",
        "프라이버시",
        "privacy",
    ],
    "refund_policy": [
        "환불",
        "취소",
        "해지",
        "refund",
        "cancellation",         # ⭐ 추가
    ],
    "payment_policy": [
        "결제",
        "자동결제",
        "정기결제",
        "payment",
        "billing",
        "renewal",              # ⭐ 추가
    ],
}


def infer_doc_subtype(path: Path) -> str:
    """파일명 키워드로 문서 종류를 구분 (이용약관 / 개인정보처리방침 / 환불정책 등).
    같은 service_name이라도 문서 종류가 다르면 check_document_exists에서
    별개로 취급해야 하므로 별도 필드로 관리한다."""
    name = path.stem.lower()

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


SHARED_SCOPE_MARKERS = [
    "모든 서비스에 적용",
    "전 서비스에 적용",
    "서비스 전반에 적용",
    "계열사가 제공하는 모든 서비스",
    "그룹사 전체",
]


def infer_scope(text: str) -> str:
    """구글 통합 개인정보처리방침처럼 특정 서비스 전용이 아니라
    여러 서비스에 공통 적용되는 문서인지 본문 내용으로 감지.
    (예: 유튜브 개인정보처리방침 = 구글 전체 서비스 공통 문서)
    이런 문서는 서비스와 무관한 내용(Gmail, 검색 등)이 섞여 있을 수 있어서,
    검색/답변 생성 단계에서 별도로 취급하는 게 안전하다."""
    return "shared" if any(marker in text for marker in SHARED_SCOPE_MARKERS) else "service_specific"


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


def merge_short_chunks(chunks: list[str], min_len: int = 120) -> list[str]:
    """너무 짧은 청크(예: 예시 목록 안에서 매번 1번부터 다시 시작하는
    "1. 자동화된 결정에 대한 거부" 같은 항목 하나짜리 청크)를 다음 청크와 합친다.
    split_long_chunks의 반대 짝: 저쪽은 "너무 긴 것"을, 이쪽은 "너무 짧아서
    혼자서는 맥락이 없는 것"을 처리한다."""
    if not chunks:
        return chunks

    merged: list[str] = []
    buffer = ""

    for chunk in chunks:
        if len(chunk) >= min_len:
            # 이 청크 자체가 이미 충분히 기니, 모아둔 짧은 버퍼를 먼저 정리하고
            # 이 청크는 병합 대상으로 삼지 않는다 (자연스러운 섹션 경계를 침범하지 않도록).
            if buffer:
                merged.append(buffer)
                buffer = ""
            merged.append(chunk)
            continue

        buffer = f"{buffer}\n{chunk}" if buffer else chunk
        if len(buffer) >= min_len:
            merged.append(buffer)
            buffer = ""

    if buffer:
        if merged:
            merged[-1] = f"{merged[-1]}\n{buffer}"
        else:
            merged.append(buffer)

    return merged


def chunk_text(text: str, doc_type: str) -> list[str]:
    # 1순위: 제O조 형식 (law, terms 공통 - 카카오 이용약관 등)
    if doc_type in ("law", "terms"):
        chunks = split_by_pattern(text, ARTICLE_PATTERN)
        if chunks:
            print("[INFO] 조문(제O조) 단위 청킹")
            return merge_short_chunks(split_long_chunks(chunks))

    # 2순위: 숫자 아웃라인 "1. Title" / "1.1. Title" (넷플릭스 영문 약관 등)
    if doc_type in ("law", "terms"):
        chunks = split_by_pattern(text, NUMBERED_OUTLINE_PATTERN)
        if chunks:
            print("[INFO] 숫자 아웃라인(1./1.1.) 단위 청킹")
            return merge_short_chunks(split_long_chunks(chunks))

    # 2.5순위: 행정지침의 "1. / 2. / 3." 번호 목록 (전자상거래 소비자보호 지침 등)
    #   split_by_heading보다 먼저 시도해야 함 - is_heading_line은 20자 넘는 줄을
    #   소제목으로 인정하지 않아서, 서술형으로 긴 번호 목록 제목을 놓치고
    #   앞 섹션에 흡수시켜버리는 문제가 실제로 확인됨 (예: "전자상거래 등에서 소비자 보호 지침").
    #   다만 "개인정보 처리방침 작성지침"류 문서는 "작성 예시" 안에서 1번부터 계속
    #   다시 시작하는 짧은 목록이 반복되므로, merge_short_chunks로 초소형 조각을 방지한다.
    if doc_type == "guideline":
        chunks = split_by_pattern(text, GUIDELINE_PATTERN)
        if chunks:
            print("[INFO] 행정지침 문서: 번호 제목 단위 청킹")
            return merge_short_chunks(split_long_chunks(chunks))

    # 3순위: 소제목 기반 (유튜브 서비스 약관, 로마숫자 목차형 가이드라인 등 번호 체계 없는 경우)
    if doc_type in ("terms", "guideline"):
        chunks = split_by_heading(text)
        if chunks:
            print("[INFO] 소제목 단위 청킹")
            return merge_short_chunks(split_long_chunks(chunks))

    print("[INFO] 일반 문서/약관: 글자 수 기반 청킹 (fallback)")
    docs = fallback_splitter.create_documents([text])
    return merge_short_chunks([doc.page_content for doc in docs])


def extract_article(chunk: str) -> str:
    match = ARTICLE_NO_PATTERN.search(chunk)
    if match:
        return re.sub(r"\s+", "", match.group(0))

    match = NUMBERED_SECTION_PATTERN.search(chunk)
    if match:
        return match.group(1)

    match = BRACKET_HEADING_PATTERN.match(chunk)
    if match:
        return f"[{match.group(1).strip()}]"

    return "unknown"


def extract_article_no(chunk: str) -> str:
    """한국어 조문 또는 숫자 섹션 번호를 검색·필터용 정규형으로 반환한다.

    ``제12조``는 ``12조``, ``제12조의3``은 ``12조의3``으로 저장해
    가지 조항의 번호가 유실되지 않도록 한다. 영문 약관의 ``2.7.``은
    ``2.7``로 저장한다. 번호가 없는 대괄호 제목은 ``unknown``을 반환한다.
    """
    match = ARTICLE_NO_PATTERN.search(chunk)
    if match:
        return re.sub(r"\s+", "", match.group(1))

    match = NUMBERED_SECTION_PATTERN.search(chunk)
    if match:
        return match.group(1).rstrip(".")

    return "unknown"


def make_chunk_id(source_id: str, index: int, chunk: str) -> str:
    # chunk 전체 내용에 대한 해시를 포함해 id 충돌 가능성 최소화
    content_hash = hashlib.sha1(chunk.encode("utf-8")).hexdigest()
    raw = f"{source_id}::{index}::{content_hash}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

def delete_by_source(source_id: str) -> None:
    """같은 소스(파일 경로 / URL / 직접입력 식별자)에 속한 기존 청크를 전부 삭제.
    내용이 조금이라도 바뀌면 청크 경계/개수/ID가 통째로 달라지므로,
    upsert만으로는 구버전 청크가 잔존하는 문제를 막는다."""
    existing = collection.get(where={"source": source_id})
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
        print(f"[CLEANUP] 기존 청크 {len(existing['ids'])}개 삭제 (재삽입 전): {source_id}")


def compute_document_hash(text: str) -> str:
    """공백 차이로 인한 해시 불일치를 줄이기 위해 정규화 후 해시.
    청크별 content_hash(청킹 이후, chunk 단위)와 달리 청킹 이전 전체 문서 기준으로 계산해,
    같은 문서가 URL 크롤링/붙여넣기 등 다른 경로로 들어와도 동일 해시를 갖도록 한다."""
    normalized = re.sub(r"\s+", "", text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def has_unchanged_source(source_id: str, document_hash: str) -> bool:
    """같은 소스가 같은 본문과 현재 인제스트 스키마로 저장됐는지 확인한다.

    스키마 버전까지 검사하므로 article_no 같은 메타데이터가 새로 추가된 경우에는
    본문이 같더라도 한 번 다시 인제스트된다.
    """
    if not source_id or not document_hash:
        return False

    results = collection.get(
        where={
            "$and": [
                {"source": source_id},
                {"document_hash": document_hash},
                {"ingest_schema_version": INGEST_SCHEMA_VERSION},
            ]
        },
        limit=1,
    )
    return bool(results["ids"])


def find_duplicate_source(
    service_name: str, document_hash: str, exclude_source_id: str
) -> str | None:
    """같은 service_name + 같은 document_hash를 가진 '다른' source_id가 이미 있는지 확인.
    같은 source_id의 재수집(약관 개정 등 업데이트)은 upsert_chunks의 delete_by_source가
    이미 교체 처리하므로 여기서는 대상이 아니다 — 이 함수는 '다른 경로로 들어온 동일 내용'
    (예: 같은 약관을 URL로도, 붙여넣기로도 넣은 경우)만 잡는다."""
    if not document_hash:
        return None

    results = collection.get(
        where={"$and": [{"service_name": service_name}, {"document_hash": document_hash}]}
    )
    for meta in results["metadatas"]:
        source = meta.get("source")
        if source and source != exclude_source_id:
            return source
    return None


def upsert_chunks(
    source_id: str,
    source_label: str,
    doc_type: str,
    service_name: str,
    chunks: list[str],
    source_kind: str = "file",
    doc_subtype: str = "unknown",
    scope: str = "service_specific",
    document_hash: str = "",
) -> None:
    delete_by_source(source_id)

    if not chunks:
        return

    ids = []
    documents = []
    metadatas = []
    updated_at = datetime.now(timezone.utc).isoformat()

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
                "scope": scope,  # service_specific / shared (여러 서비스 공통 문서, 예: 구글 통합 개인정보처리방침)
                "chunk_index": index,
                "article": extract_article(chunk),
                "article_no": extract_article_no(chunk),
                "content_hash": hashlib.md5(chunk.encode("utf-8")).hexdigest(),
                "document_hash": document_hash,  # 문서 단위 해시 (다른 source_id 간 중복 탐지용)
                "ingest_schema_version": INGEST_SCHEMA_VERSION,
                "updated_at": updated_at,  # 이 청크가 (재)삽입된 시각
            }
        )

    # 청크마다 upsert를 반복 호출하지 않고 한 번에 배치로 전송 (임베딩 계산도 배치로 처리됨)
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

def ingest_crawled_jsonl(path: Path) -> bool:
    """search_tos_fineprint.py가 생성한 knowledge_base.jsonl을 처리."""
    try:
        with path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"[ERROR] JSONL 읽기 실패: {path} / {e}")
        return False

    success = False
    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        # CollectedDocument 필드 추출
        service_name = data.get("service_name", "unknown")
        doc_type_raw = data.get("document_type", "terms")  # terms, privacy, refund_cancellation 등
        title = data.get("title", "")
        source_url = data.get("source_url", "")
        source_kind = data.get("source_kind", "web_html")
        revision_date = data.get("revision_date")
        text = data.get("text", "")

        if not text or len(text.strip()) < 200:
            continue

        # doc_type 매핑 (ingest_text는 "law"/"guideline"/"terms"만 허용)
        # → 일단 모두 "terms"로 저장하되, doc_subtype으로 구분
        doc_type = "terms"

        # doc_subtype 매핑
        doc_subtype_map = {
            "terms": "terms_of_use",
            "privacy": "privacy_policy",
            "refund_cancellation": "refund_policy",
            "billing_autorenewal": "payment_policy",
            "platform_refund": "refund_policy",
        }
        doc_subtype = doc_subtype_map.get(doc_type_raw, "unknown")

        # 개정일을 메타데이터에 포함시키기 위해 text에 추가 (또는 별도 처리)
        if revision_date and revision_date not in text:
            text = f"{text}\n\n[개정일: {revision_date}]"

        # source_id: URL이 없으면 파일명 사용
        source_id = source_url if source_url else path.as_posix()

        result = ingest_text(
            source_id=source_id,
            source_label=title or path.name,
            doc_type=doc_type,
            service_name=service_name,
            text=text,
            source_kind=source_kind,
            doc_subtype=doc_subtype,
        )
        if result:
            success = True

    return success


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
    document_hash = compute_document_hash(text)

    if has_unchanged_source(source_id, document_hash):
        print(f"[SKIP] 변경되지 않은 문서: {source_label}")
        return True

    duplicate_source = find_duplicate_source(
        service_name, document_hash, exclude_source_id=source_id
    )
    if duplicate_source:
        print(
            f"[SKIP] 동일 내용이 이미 다른 source로 등록되어 있습니다: "
            f"{duplicate_source} (신규 source: {source_id})"
        )
        return True  # False → True (정상 스킵으로 간주)

    scope = infer_scope(text)
    if scope == "shared":
        print(f"[WARNING] 여러 서비스 공통 적용 문서로 감지됨(scope=shared): {source_label}")

    chunks = chunk_text(text, doc_type)

    if not chunks:
        print(f"[SKIP] 청킹 결과 없음: {source_label}")
        return False

    upsert_chunks(
        source_id,
        source_label,
        doc_type,
        service_name,
        chunks,
        source_kind,
        doc_subtype,
        scope,
        document_hash,
    )
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


def ingest_uploaded_file(
    path: str | Path,
    service_name: str,
    doc_type: str = "terms",
    doc_subtype: str | None = None,
) -> bool:
    """UI로 업로드된 PDF/TXT를 경로 구조에 의존하지 않고 인제스트한다."""
    _validate_manual_input(service_name, doc_type)
    upload_path = Path(path).expanduser().resolve()
    if upload_path.suffix.lower() not in {".pdf", ".txt"}:
        raise ValueError("업로드 문서는 PDF 또는 TXT 형식이어야 합니다.")
    if not upload_path.is_file():
        raise FileNotFoundError(f"업로드 문서를 찾을 수 없습니다: {upload_path}")

    text = load_file(upload_path)
    if not text or not text.strip():
        return False

    resolved_subtype = doc_subtype or infer_doc_subtype(upload_path)
    if resolved_subtype == "unknown" and doc_type == "terms":
        resolved_subtype = "terms_of_use"

    document_hash = compute_document_hash(text)
    source_id = f"upload::{service_name.strip()}::{upload_path.name}::{document_hash[:12]}"
    return ingest_text(
        source_id=source_id,
        source_label=upload_path.name,
        doc_type=doc_type,
        service_name=service_name.strip(),
        text=text,
        source_kind="upload",
        doc_subtype=resolved_subtype,
    )


def iter_source_files(base_path: str = RAG_PATH) -> list[Path]:
    base = Path(base_path)

    if not base.exists():
        print(f"[ERROR] RAG 폴더가 없습니다: {base_path}")
        return []

    files = (
        list(base.rglob("*.txt"))
        + list(base.rglob("*.pdf"))
        + list(base.rglob("*.json"))
        + list(base.rglob("*.jsonl"))
    )
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

    if text is None:
        print(f"[ERROR] 파일 로드 실패: {path.name}")
        return False

    return ingest_text(
        source_id=path.as_posix(),
        source_label=path.name,
        doc_type=doc_type,
        service_name=service_name,
        text=text,
        doc_subtype=doc_subtype,
    )


def sweep_stale_sources(base_path: str = RAG_PATH) -> None:
    """RAG 폴더에서 삭제되었거나 이름이 바뀐 '파일' 소스의 잔존 청크를 DB에서 정리.
    ingest_all() 전체 실행 후 1회 호출.
    URL/직접입력 소스(source_kind != "file")는 파일 시스템 스캔 대상이 아니므로 건드리지 않는다."""
    current_sources = {p.as_posix() for p in iter_source_files(base_path)}
    existing = collection.get(where={
        "source_kind": "file"
    })
    ids_to_delete = [
        chunk_id
        for chunk_id, meta in zip(existing["ids"], existing["metadatas"])
        if meta.get("source") not in current_sources
    ]

    if ids_to_delete:
        collection.delete(ids=ids_to_delete)
        print(f"[CLEANUP] 원본이 사라진(삭제/이름변경) 청크 {len(ids_to_delete)}개 정리")
    else:
        print("[CLEANUP] 정리할 잔존 청크 없음")

# ===== FAQ 전용 로딩 및 처리 =====

def load_faq_json(path: Path) -> list[dict] | None:
    """
    FAQ JSON 파일 로드.
    
    기대 형식:
    [
        {
            "question": "미성년자가 피해를 입었을 때 어떻게 되나요?",
            "answer": "미성년자는 법정대리인(보호자)이 대신...",
            "category": "refund_policy",  (선택, 없으면 "unknown")
            "keywords": ["미성년자", "피해"]  (선택)
        },
        ...
    ]
    
    반환: list[dict] (성공) / None (실패)
    """
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        
        if not isinstance(data, list):
            print(f"[ERROR] FAQ JSON은 배열 형식이어야 합니다: {path.name}")
            return None
        
        # 기본 유효성 검사
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                print(f"[ERROR] FAQ 항목 {i}가 dict가 아닙니다: {path.name}")
                return None
            if "question" not in item or "answer" not in item:
                print(
                    f"[ERROR] FAQ 항목 {i}에 'question' 또는 'answer' 필드가 없습니다: {path.name}"
                )
                return None
        
        return data
    
    except json.JSONDecodeError as e:
        print(f"[ERROR] FAQ JSON 파싱 실패: {path.name} / {e}")
        return None
    except Exception as e:
        print(f"[ERROR] FAQ 파일 로드 실패: {path.name} / {e}")
        return None



def infer_faq_doc_subtype(item: dict) -> str:
    """FAQ 항목의 doc_subtype 추론.
    item["category"]가 우리가 이미 정의한 doc_subtype 값(예: refund_policy)과
    정확히 일치할 때만 그대로 사용한다. "FAQ"처럼 일반적인 라벨이면
    (실제 kca_faq.json이 그렇듯) 무시하고 질문+답변 텍스트 키워드로 추론한다."""
    category = item.get("category")
    if category in DOC_SUBTYPE_KEYWORDS:
        return category

    combined_text = f"{item.get('question', '')} {item.get('answer', '')}".lower()
    for subtype, keywords in DOC_SUBTYPE_KEYWORDS.items():
        if any(keyword.lower() in combined_text for keyword in keywords):
            return subtype

    return "unknown"


def make_faq_document(question: str, answer: str) -> str:
    """
    FAQ 질문+답변을 하나의 임베딩 대상 텍스트로 조합.
    
    형식:
    Q: {question}
    
    A: {answer}
    """
    return f"Q: {question.strip()}\n\nA: {answer.strip()}"


def upsert_faq_items(
    source_id: str,
    source_label: str,
    service_name: str,
    faq_items: list[dict],
) -> None:
    """
    FAQ 항목들을 ChromaDB에 upsert.
    
    각 FAQ 항목을 별도 청크로 저장 (이미 완벽하게 구분되어 있으므로 재청킹 X).
    """
    delete_by_source(source_id)
    
    if not faq_items:
        return
    
    ids = []
    documents = []
    metadatas = []
    updated_at = datetime.now(timezone.utc).isoformat()
    
    for index, item in enumerate(faq_items):
        question = item.get("question", "").strip()
        answer = item.get("answer", "").strip()
        
        if not question or not answer:
            print(f"[SKIP] FAQ 항목 {index}: 질문 또는 답변이 비어있음")
            continue
        
        # 임베딩 대상: 질문 + 답변 조합
        document = make_faq_document(question, answer)
        
        # doc_subtype 추론
        doc_subtype = infer_faq_doc_subtype(item)
        
        # 청크 ID: source + index + 질문 처음 50자
        chunk_id = make_chunk_id(source_id, index, document)
        
        ids.append(chunk_id)
        documents.append(document)
        metadatas.append(
            {
                "type": "faq",
                "doc_subtype": doc_subtype,
                "service_name": service_name,
                "source": source_id,
                "source_file": source_label,
                "source_kind": "file",  
                "scope": "service_specific",
                "chunk_index": index,
                "article": "unknown",
                # ✅ FAQ 전용 메타데이터
                "question": question,  # 질문 원문 (인용용)
                "answer": answer,      # 답변 원문 (인용용)
                "content_hash": hashlib.md5(document.encode("utf-8")).hexdigest(),
                "updated_at": updated_at,
            }
        )
    
    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        print(f"[DONE] {source_label} -> {len(ids)} FAQ items")


def ingest_faq_file(path: Path) -> bool:
    """
    FAQ JSON 파일을 DB에 임베딩.
    
    자동 추론:
    - service_name: 파일명 또는 폴더 구조에서 추론 (있으면)
    - doc_subtype: 각 항목의 category 필드 또는 텍스트 키워드 기반
    """
    faq_items = load_faq_json(path)
    
    if faq_items is None:
        return False
    
    # service_name 추론 (FAQ 전용: 서비스 폴더가 없으면 파일명이 아니라 "none"으로 처리)
    service_name = infer_faq_service_name(path)
    
    print(f"[LOAD] {path}")
    print(f"[META] type=faq, service_name={service_name}, items={len(faq_items)}")
    
    upsert_faq_items(
        source_id=path.as_posix(),
        source_label=path.name,
        service_name=service_name,
        faq_items=faq_items,
    )
    
    return True


def ingest_all(base_path: str = RAG_PATH) -> None:
    """
    RAG 폴더의 모든 파일(일반 문서 + FAQ JSON) 일괄 임베딩.
    """
    all_files = iter_source_files(base_path)

    if not all_files:
        print(f"[WARNING] 처리할 파일이 없습니다: {base_path}")
        return
    
    success_count = 0
    fail_count = 0
    
    for path in all_files:
        try:
            suffix = path.suffix.lower()
            
            # ✅ 수정: .jsonl을 먼저 체크
            if suffix == ".jsonl":
                # 크롤러 JSONL 처리
                if ingest_crawled_jsonl(path):
                    success_count += 1
                else:
                    fail_count += 1
            elif suffix == ".json":
                # FAQ 파일 처리
                if ingest_faq_file(path):
                    success_count += 1
                else:
                    fail_count += 1
            else:
                # 기존 문서 파일 처리 (.txt, .pdf)
                if ingest_file(path):
                    success_count += 1
                else:
                    fail_count += 1
        
        except Exception as exc:
            print(f"[ERROR] 처리 실패: {path} / {exc}")
            fail_count += 1
    
    sweep_stale_sources(base_path)  # 삭제·이름변경된 로컬 파일(source_kind="file") 정리
    
    print()
    print(f"[SUMMARY] 성공: {success_count}")
    print(f"[SUMMARY] 실패: {fail_count}")
    print(f"[SUMMARY] 전체 파일: {len(all_files)}")
    print(f"[SUMMARY] DB 전체 청크 수: {collection.count()}")


if __name__ == "__main__":
    ingest_all()

