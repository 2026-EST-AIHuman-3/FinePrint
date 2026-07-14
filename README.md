# FinePrint
RAG-based AI Agent for analyzing subscription service terms and policies.

PDF 파싱 및 청킹, 임베딩 후 ChromaDB에 저장하는 py파일입니다. (PDF_Test.py)
RAG에 자료를 넣어둔 후 py파일을 실행합니다.

=================================================================================

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

---

## 검색 시 참고할 메타데이터 필드

저장된 모든 청크에는 아래 메타데이터가 붙어있어서, `collection.get()`/`collection.query()`의 `where` 필터로 활용 가능합니다.

| 필드 | 값 예시 | 설명 |
|---|---|---|
| `type` | `law` / `guideline` / `terms` | 법령 / 소비자보호 지침 / 서비스 약관 |
| `doc_subtype` | `terms_of_use` / `privacy_policy` / `refund_policy` / `payment_policy` / `unknown` | 문서 종류 |
| `service_name` | `넷플릭스`, `쿠팡` 등 (law/guideline은 `none`) | 서비스명 |
| `source` | 파일경로 / URL / `pasted::...` | 원본 식별자 |
| `source_kind` | `file` / `url` / `pasted` | 어떤 경로로 들어왔는지 |
| `scope` | `service_specific` / `shared` | ⚠️ 아래 참고 |
| `article` | `"1조"` 또는 `"unknown"` | 조문 번호 (제O조 형식 문서만) |
| `chunk_index` | 정수 | 문서 내 청크 순서 |

**⚠️ `scope="shared"` 주의사항**: 유튜브 개인정보처리방침처럼 "구글 전체 서비스에 공통 적용"되는 문서는 자동으로 `scope="shared"`가 붙습니다.<br>
이런 문서는 유튜브와 무관한 내용(Gmail, 검색 등)이 섞여 있을 수 있으니, 검색 결과에 이 필드가 `shared`로 나오면 답변 생성 시 "이 조항은 구글 서비스 전반에 적용되는 내용"이라는 걸 참고해서 처리해주세요.

```python
# 필터링 예시
collection.get(where={"$and": [{"service_name": "넷플릭스"}, {"type": "terms"}]})
```
