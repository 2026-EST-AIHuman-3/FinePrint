import os
import chromadb
from chromadb.utils import embedding_functions
from PyPDF2 import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# =========================
# 1. DB 초기화 (한국어 지원 임베딩 모델 사용)
# =========================
# 기본 임베딩(all-MiniLM-L6-v2)은 영어 중심이라 한국어 의미 구분이 잘 안 됨.
# 다국어 모델로 교체 (로컬 실행, API 키 불필요).
korean_ef = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="paraphrase-multilingual-mpnet-base-v2"
)

client = chromadb.PersistentClient(path="./db")
collection = client.get_or_create_collection(
    name="RAG_system",
    embedding_function=korean_ef
)

# =========================
# 2. 텍스트 로더 (PDF) - 이미지 기반 PDF는 OCR 폴백
# =========================
def load_pdf(path):
    reader = PdfReader(path)
    text = ""
    empty_pages = 0
    total_pages = len(reader.pages)

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text and page_text.strip():
            text += page_text + "\n"
        else:
            empty_pages += 1

    # 페이지 전부(또는 대부분) 텍스트가 안 뽑히면 이미지 기반 PDF로 판단 -> OCR 시도
    if empty_pages == total_pages or (total_pages > 0 and empty_pages / total_pages > 0.7):
        print(f"[INFO] {os.path.basename(path)}: 텍스트 레이어가 거의 없음 "
              f"({empty_pages}/{total_pages} 페이지). 이미지 기반 PDF로 판단, OCR 시도합니다.")
        ocr_text = ocr_pdf(path)
        if ocr_text:
            return ocr_text
        else:
            print(f"[WARNING] {os.path.basename(path)}: OCR도 실패했습니다. "
                  f"수동으로 텍스트를 정리한 .txt 파일로 대체하는 것을 권장합니다 "
                  f"(예: 표 구조는 OCR 정확도가 낮아 직접 정리한 텍스트가 훨씬 안전합니다).")
            return None

    return text


def ocr_pdf(path):
    """이미지 기반(스캔본) PDF에서 OCR로 텍스트 추출.
    표가 많은 문서(예: 소비자분쟁해결기준)는 OCR 정확도가 낮을 수 있으므로,
    가능하면 수동으로 정리한 .txt를 우선 사용하는 것을 권장.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        print("[ERROR] OCR을 위해 'pdf2image'와 'pytesseract' 설치가 필요합니다.")
        print("        pip install pdf2image pytesseract  (+ poppler, tesseract-ocr 시스템 설치 필요)")
        return None

    try:
        images = convert_from_path(path)
        text = ""
        for i, img in enumerate(images):
            page_text = pytesseract.image_to_string(img, lang="kor+eng")
            text += page_text + "\n"
            print(f"[OCR] {os.path.basename(path)} - {i+1}/{len(images)} 페이지 처리")
        return text if text.strip() else None
    except Exception as e:
        print(f"[ERROR] OCR 처리 중 예외 발생: {e}")
        return None

# =========================
# 3. 텍스트 로더 (TXT) - 인코딩 자동 감지
# =========================
def load_txt(path):
    # 흔한 인코딩들을 순서대로 시도
    encodings_to_try = ["utf-8", "utf-8-sig", "utf-16", "cp949", "euc-kr"]
    for enc in encodings_to_try:
        try:
            with open(path, "r", encoding=enc) as f:
                text = f.read()
            print(f"[INFO] {os.path.basename(path)} -> 인코딩 '{enc}'으로 읽음")
            return text
        except (UnicodeDecodeError, UnicodeError):
            continue
    print(f"[ERROR] {path}: 지원하는 인코딩으로 읽지 못했습니다.")
    return None

# =========================
# 4. Chunking (조문 단위)
# =========================
import re

# "제1조", "제17조의2" 같은 조문 시작 패턴
ARTICLE_PATTERN = re.compile(r"(?=제\s*\d+조(?:의\s*\d+)?\s*\()")

# 조문 단위로 잘랐을 때 하나의 조문이 너무 길면 추가로 쪼개기 위한 보조 스플리터
_fallback_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=100
)

MAX_ARTICLE_LEN = 1500  # 이보다 긴 조문은 fallback으로 추가 분할

def chunk_by_article(text):
    """
    법률/지침 텍스트를 '제○조(제목)' 단위로 분할.
    - 조문 패턴이 거의 안 잡히는 문서(예: 서술형 지침, 계약서 등)는
      기존 글자수 기반 청킹으로 자동 폴백.
    """
    parts = ARTICLE_PATTERN.split(text)
    # 첫 조각은 조문 시작 이전의 목차/서문 등이라 보통 노이즈 -> 내용 있으면만 살림
    parts = [p.strip() for p in parts if p.strip()]

    # 조문 패턴이 거의 안 잡혔다면 (조각이 1~2개뿐) -> 일반 문서로 판단, 기존 방식 사용
    if len(parts) <= 2:
        print("[INFO] 조문 패턴이 거의 발견되지 않음 -> 글자수 기반 청킹으로 폴백")
        docs = _fallback_splitter.create_documents([text])
        return [d.page_content for d in docs]

    chunks = []
    for part in parts:
        if len(part) <= MAX_ARTICLE_LEN:
            chunks.append(part)
        else:
            # 조문 하나가 너무 길면 (예: 긴 조항 + 여러 항/호 나열) 추가로 쪼갬
            sub_docs = _fallback_splitter.create_documents([part])
            chunks.extend([d.page_content for d in sub_docs])

    return chunks


def chunk_text(text):
    # 기존 함수명 유지 (다른 코드에서 호출하는 부분 안 바꿔도 되게)
    return chunk_by_article(text)

# =========================
# 5. DB 저장 (조문 번호 메타데이터 포함)
# =========================
ARTICLE_NUM_PATTERN = re.compile(r"제\s*(\d+조(?:의\s*\d+)?)")

def extract_article_no(chunk_text_):
    m = ARTICLE_NUM_PATTERN.search(chunk_text_)
    return m.group(0).replace(" ", "") if m else "unknown"

def save_to_db(chunks, doc_type, source):
    for i, chunk in enumerate(chunks):
        article_no = extract_article_no(chunk)
        collection.add(
            documents=[chunk],
            ids=[f"{doc_type}_{os.path.basename(source)}_{i}"],
            metadatas=[{
                "type": doc_type,
                "source": source,
                "article": article_no
            }]
        )

# =========================
# 6. 파일 로더 (PDF / TXT 자동 판별)
# =========================
def load_file(path):
    if path.endswith(".pdf"):
        return load_pdf(path)
    elif path.endswith(".txt"):
        return load_txt(path)
    else:
        return None

# =========================
# 7. RAG 폴더 스캔 (하위 폴더 있어도/없어도 둘 다 지원)
# =========================
FOLDER_TYPE_MAP = {
    "법률": "law",
    "행정지침": "guideline",
    "약관": "terms",
}

def load_all_files(base_path="./RAG"):
    print(f"[DEBUG] base_path exists? {os.path.exists(base_path)}")
    if not os.path.exists(base_path):
        print(f"[ERROR] {base_path} 폴더가 존재하지 않습니다.")
        return []

    contents = os.listdir(base_path)
    print(f"[DEBUG] base_path contents: {contents}")

    files = []

    for name in contents:
        full_path = os.path.join(base_path, name)

        # Case 1: 하위 폴더인 경우 (기존 로직)
        if os.path.isdir(full_path):
            doc_type = FOLDER_TYPE_MAP.get(name, "unknown")
            for file in os.listdir(full_path):
                if file.endswith(".pdf") or file.endswith(".txt"):
                    file_path = os.path.join(full_path, file)
                    files.append((file_path, doc_type))

        # Case 2: RAG 폴더 바로 밑에 파일이 있는 경우 (지금 상황)
        elif name.endswith(".pdf") or name.endswith(".txt"):
            # 파일명 기준으로 타입 추정 (필요시 규칙 조정)
            doc_type = "unknown"
            for keyword, mapped_type in [
                ("법", "law"),
                ("지침", "guideline"),
                ("약관", "terms"),
                ("정책", "terms"),
            ]:
                if keyword in name:
                    doc_type = mapped_type
                    break
            files.append((full_path, doc_type))

    print(f"[DEBUG] 발견된 파일 수: {len(files)}")
    for f, t in files:
        print(f"  - {f} (type={t})")

    return files

# =========================
# 8. 전체 ingestion 실행
# =========================
def ingest_all():
    files = load_all_files("./RAG")
    if not files:
        print("[WARNING] 로드할 파일이 없습니다. RAG 폴더 구조를 확인하세요.")
        return

    success_count = 0
    fail_count = 0

    for path, doc_type in files:
        print(f"[LOAD] {path}")
        try:
            text = load_file(path)
            if not text:
                print(f"[WARNING] 텍스트 추출 실패 (빈 문서이거나 스캔본 PDF일 수 있음): {path}")
                fail_count += 1
                continue
            chunks = chunk_text(text)
            if not chunks:
                print(f"[WARNING] 청킹 결과가 비었습니다: {path}")
                fail_count += 1
                continue
            save_to_db(chunks, doc_type, path)
            print(f"[DONE] {path} -> {len(chunks)} chunks")
            success_count += 1
        except Exception as e:
            # 파일 하나에서 에러가 나도 전체 ingestion은 계속 진행
            print(f"[ERROR] {path} 처리 중 예외 발생: {e}")
            fail_count += 1
            continue

    print(f"\n[SUMMARY] 성공: {success_count}개 / 실패: {fail_count}개 / 전체: {len(files)}개")

# =========================
# 9. 검색 테스트 (하이브리드: 키워드 필터/부스트 + 벡터 검색)
# =========================

# 도메인 핵심 키워드 사전 - 질문에 이 단어가 있으면 해당 단어가
# 포함된 문서를 우선적으로 검토 (표면적 "기간" 패턴에 임베딩이
# 과하게 반응하는 문제를 보완)
DOMAIN_KEYWORDS = [
    "청약철회", "청약 철회", "환불", "해지", "위약금", "자동결제",
    "자동갱신", "개인정보", "제3자 제공", "손해배상", "대금환급",
]

def extract_keywords_in_query(query):
    return [kw for kw in DOMAIN_KEYWORDS if kw.replace(" ", "") in query.replace(" ", "")]

def hybrid_search(query, n_results=3, candidate_pool=15):
    keywords = extract_keywords_in_query(query)
    print(f"[DEBUG] 질문에서 감지된 도메인 키워드: {keywords}")

    # 1) 먼저 순수 벡터 검색으로 후보군을 넉넉히 가져옴
    raw = collection.query(query_texts=[query], n_results=candidate_pool)

    docs = raw["documents"][0]
    metas = raw["metadatas"][0]
    dists = raw["distances"][0]

    reranked = []
    for doc, meta, dist in zip(docs, metas, dists):
        score = dist  # 거리는 작을수록 좋음 (낮을수록 유사)
        # 키워드가 실제 본문에 포함돼 있으면 거리 점수를 낮춰서(=더 유사하게) 우선순위 상승
        matched = sum(1 for kw in keywords if kw.replace(" ", "") in doc.replace(" ", ""))
        if matched > 0:
            score = score - (matched * 0.15)  # 키워드 1개당 보정치(경험적 값, 필요시 조정)
        reranked.append((score, doc, meta, dist, matched))

    # 보정된 score 기준으로 재정렬 (낮을수록 상위)
    reranked.sort(key=lambda x: x[0])
    return reranked[:n_results]


def search(query):
    count = collection.count()
    print(f"\n[DEBUG] 현재 DB에 저장된 청크 수: {count}")
    if count == 0:
        print("[ERROR] DB가 비어있습니다. ingest_all()이 제대로 실행됐는지 확인하세요.")
        return

    results = hybrid_search(query)

    print("\n======================")
    print(f"QUERY: {query}")
    print("======================")
    for i, (score, doc, meta, dist, matched) in enumerate(results):
        print(f"\n[{i+1}]")
        print("TEXT:", doc[:200])
        print("TYPE:", meta["type"])
        print("ARTICLE:", meta.get("article", "unknown"))
        print("SOURCE:", meta["source"])
        print(f"RAW_DIST: {dist:.4f} / KEYWORD_MATCH: {matched} / ADJUSTED_SCORE: {score:.4f}")

# =========================
# 10. 실행
# =========================
if __name__ == "__main__":
    ingest_all()
    search("제 3자에게 개인정보 넘기나요/")
    search("디지털콘텐츠도 청약철회가 되나요?")