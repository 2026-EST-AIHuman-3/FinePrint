# FinePrint
RAG-based AI Agent for analyzing subscription service terms and policies.

PDF 파싱 및 청킹, 임베딩 후 ChromaDB에 저장하는 파일입니다. (`ingest_rag.py`)
RAG에 자료를 넣어둔 후 py파일을 실행합니다.

## 구조

- **`ingest_rag.py`**: 문서 로딩, 청킹, 임베딩, ChromaDB 저장 담당
- **`search_utils.py`**: 하이브리드 검색(의미 기반 + 키워드 가중치) 담당 
- **`config.py`**: 공유 설정 (DB 경로, 임베딩 모델 등)

## 사용 흐름
RAG/ 폴더에 약관/법령 문서 추가 <br>
　　　　　　　↓ <br>
python ingest_rag.py  
(같은 source는 기존 청크 삭제 후 재삽입)  
　　　　　　　↓ <br>
ChromaDB에 저장됨 (search_utils로 검색 가능)<br>



---

## RAG 폴더 구조

RAG/  
├── law/ # 법령   
　├── 개인정보보호법.txt   
　└── 전자상거래법.txt   
├── guideline/ # 정부 소비자보호 지침   
　└── 개인정보처리방침작성지침.txt   
├── terms/ # 서비스 약관   
　├── 넷플릭스/   
　├── 카카오/   
　├── 쿠팡/   
　├── 유튜브/   
　├── 티빙/   
　└── 한국소비자원/   
　　└── faq.json 

※ FAQ는 각 서비스 폴더에 자유롭게 둘 수 있습니다.  
예) terms/넷플릭스/faq.json

**파일명 규칙 - `doc_subtype` 자동 추론:**
- `privacy`, `개인정보` 포함 → `privacy_policy`
- `refund`, `환불`, `취소` 포함 → `refund_policy`
- `payment`, `결제`, `자동결제` 포함 → `payment_policy`
- `terms`, `이용약관`, `서비스약관` 포함 → `terms_of_use`
- 매칭 안 됨 → `unknown`

---

## 청킹 전략 (자동 선택)

문서 타입에 따라 **우선순위 기반 청킹**이 자동으로 적용됩니다:

| 우선순위 | 형식 | 예시 | 대상 |
|---------|------|------|------|
| 1순위 | 제O조 형식 | `제1조 (목적)` | law, terms |
| 2순위 | 숫자 아웃라인 | `1. Title` / `1.1. Subtitle` | law, terms |
| 3순위 | 번호 목록 (행정지침) | `1. / 2. / 3.` | guideline |
| 4순위 | 소제목 기반 | `[소제목]` | terms, guideline |
| 5순위 | 글자 수 기반 (fallback) | 1000자 단위 분할 | 모든 문서 |

**청킹 후 처리:**
- `split_long_chunks()`: 1500자 초과 청크 재분할
- `merge_short_chunks()`: 120자 미만 청크 통합 (초소형 조각 방지)

👉 **매 실행마다 같은 source의 기존 청크를 삭제하고 재삽입** (중복 방지)

---

# DB 모듈

## 사전 준비

```python
from config import DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL
```

DB 접속/검색 코드에서 위 3개 값을 직접 하드코딩하지 말고 **반드시 `config.py`에서 import**해서 쓰세요. <br>
임베딩 모델이 인제스트 때와 검색 때가 다르면 벡터 공간이 어긋나서 검색이 전부 이상하게 나옵니다.


```python
import chromadb
from chromadb.utils import embedding_functions
from config import DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_collection(
    name=COLLECTION_NAME,
    embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    ),
)
```
---

## 사용 가능한 함수

### 1. `check_document_exists(service_name, doc_subtype=None)`

```python
check_document_exists(service_name: str, doc_subtype: str | None = None) -> bool
```

* 해당 서비스의 (특정 종류) 문서가 DB에 존재하는지 확인
* `doc_subtype`을 생략하면 그 서비스의 아무 문서(이용약관이든 개인정보처리방침이든)나 있으면 `True`
* `doc_subtype`을 지정하면 그 종류만 정확히 체크 (예: 이용약관은 없는데 개인정보처리방침만 있는 경우를 구분 가능)
* **반환값**: `True` / `False`만 나옵니다. 예외 안 던짐.

```python
check_document_exists("넷플릭스")                          # 넷플릭스 문서가 뭐든 하나라도 있으면 True
check_document_exists("넷플릭스", "terms_of_use")           # 이용약관만 콕 집어서 확인
check_document_exists("넷플릭스", "privacy_policy")         # 개인정보처리방침만 콕 집어서 확인
```

`doc_subtype`으로 쓸 수 있는 값: `terms_of_use`, `privacy_policy`, `refund_policy`, `payment_policy`, `unknown`

---

### 2. `ingest_from_url(url, service_name, extracted_text, doc_type="terms", doc_subtype="terms_of_use")`

```python
ingest_from_url(
    url: str,
    service_name: str,
    extracted_text: str,
    doc_type: str = "terms",
    doc_subtype: str = "terms_of_use",
) -> bool
```

* URL에서 추출한 텍스트를 DB에 저장
* **반환값**: 저장 성공하면 `True`, 텍스트가 비어있거나 청킹 결과가 없으면 `False`
* **⚠️ 이 두 파라미터는 값 검증이 있습니다:**
  * `service_name`이 빈 문자열이면 `ValueError` 발생
  * `doc_type`이 `{"law", "guideline", "terms"}` 중 하나가 아니면 `ValueError` 발생 (오타/대소문자 주의 — `"Terms"`, `"term"` 다 에러남)
* 이미 같은 `url`로 저장된 게 있으면, 호출 시 **기존 청크를 지우고 새로 저장**합니다 (중복 안 쌓임 — 재크롤링해서 다시 넣어도 안전).

```python
ingest_from_url(
    url="https://www.coupang.com/np/policies/loyalty",
    service_name="쿠팡",
    extracted_text=크롤링해서_뽑은_본문_텍스트,
    doc_subtype="terms_of_use",
)
```

---

### 3. `ingest_from_pasted_text(service_name, pasted_text, doc_type="terms", doc_subtype="terms_of_use")`

```python
ingest_from_pasted_text(
    service_name: str,
    pasted_text: str,
    doc_type: str = "terms",
    doc_subtype: str = "terms_of_use",
) -> bool
```

* URL에서 약관 추출 실패 시, 사용자가 직접 붙여넣은 텍스트를 DB에 저장
* 반환값/검증 규칙은 `ingest_from_url`과 동일

```python
ingest_from_pasted_text(
    service_name="티빙",
    pasted_text=사용자가_붙여넣은_텍스트,
    doc_subtype="refund_policy",
)
```
### 4. check_db_status.py

```
python check_db_status.py
```
DB 상태를 한눈에 확인:

- 전체 청크 수
- 서비스별 청크 수
- 문서 타입(type)별 청크 수
- doc_subtype별 청크 수
- source_kind별 청크 수 (file/url/pasted)
- scope별 청크 수 (service_specific/shared)
- 구버전 스키마 잔존 여부 체크 ⚠️

## 검색 시 참고할 메타데이터 필드

저장된 모든 청크에는 아래 메타데이터가 붙어있어서, `collection.get()`/`collection.query()`의 `where` 필터로 활용 가능합니다.

| 필드 | 값 예시 | 설명 |
|---|---|---|
| `type` | `law` / `guideline` / `terms` / `faq` | 법령 / 소비자보호 지침 / 서비스 약관 / 질의응답 |
| `doc_subtype` | `terms_of_use` / `privacy_policy` / `refund_policy` / `payment_policy` / `unknown` | 문서 종류 |
| `service_name` | `넷플릭스`, `쿠팡` 등 (law/guideline은 `none`) | 서비스명 |
| `source` | 파일경로 / URL / `pasted::...` | 원본 식별자 |
| `source_kind` | `file` / `url` / `pasted` | 어떤 경로로 들어왔는지 |
| `scope` | `service_specific` / `shared` | ⚠️ 아래 참고 |
| `article` | `"1조"` 또는 `"unknown"` | 조문 번호 (제O조 형식 문서만) |
| `chunk_index` | 정수 | 문서 내 청크 순서 |

### FAQ 문서 메타데이터
`type="faq"`인 문서에서만 사용됩니다.

|필드|	값 예시|	설명|
|---|---|---|
|question|	"미성년자 피해 시 어떻게 되나요?"|	질문 원문 (인용용)|
|answer|	"법정대리인이 대신 신청 가능합니다."|	답변 원문 (인용용)|


**⚠️ `scope="shared"` 주의사항**: 유튜브 개인정보처리방침처럼 "구글 전체 서비스에 공통 적용"되는 문서는 자동으로 `scope="shared"`가 붙습니다.  
이런 문서는 유튜브와 무관한 내용(Gmail, 검색 등)이 섞여 있을 수 있으니, 검색 결과에 이 필드가 `shared`로 나오면 답변 생성 시  
"이 조항은 구글 서비스 전반에 적용되는 내용"이라는 걸 참고해서 처리해주세요.

```python
# 필터링 예시
collection.get(where={"$and": [{"service_name": "넷플릭스"}, {"type": "terms"}]})
```


