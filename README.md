# FinePrint

구독 서비스의 이용약관·개인정보처리방침·환불 및 결제 정책을 수집하고, RAG 기반으로 관련 조항을 검색하기 위한 프로젝트입니다.

TXT, PDF, JSON, JSONL 문서를 불러와 구조에 맞게 청킹한 후 임베딩하고 ChromaDB에 저장합니다. 사용자 질문이 들어오면 의미 기반 검색과 키워드 가중치 재정렬을 통해 관련 약관과 법률 근거를 찾습니다.

## 주요 기능

- TXT·PDF 약관, 법률 및 행정지침 인제스트
- 크롤러가 생성한 `knowledge_base.jsonl` 인제스트
- FAQ JSON 항목별 인제스트
- 한국어·영문 약관 구조에 따른 자동 청킹
- 서비스명, 문서 종류 및 조항 메타데이터 저장
- 동일 문서 중복 입력 방지
- 변경되지 않은 일반 문서의 재임베딩 생략
- 삭제·이름 변경된 로컬 파일의 잔존 청크 정리
- Sentence Transformer 기반 Dense 검색
- 도메인 키워드 일치 가중치를 이용한 검색 결과 재정렬
- 서비스별 검색 및 기대 조항 검증

## 주요 파일

| 파일 | 역할 |
|---|---|
| `search_tos_fineprint.py` | 공식 약관·정책 검색, 본문 추출 및 JSONL 저장 |
| `ingest_rag.py` | 문서 로딩, 청킹, 임베딩 및 ChromaDB 저장 |
| `search_utils.py` | Dense 검색, 서비스 필터 및 키워드 가중치 재정렬 |
| `config.py` | DB 경로, 컬렉션명, 임베딩 모델 및 서비스 별칭 관리 |
| `verify_rag.py` | DB 메타데이터와 대표 검색 질의 검증 |
| `ensure_service_ingested.py` | DB에 없는 서비스 약관을 동적으로 수집하는 선택적 wrapper |

> `ensure_service_ingested.py`는 크롤러와 Python 호출 인터페이스가 연결된 환경에서 사용합니다. 발표용 사전 수집 흐름에서는 필수 파일이 아닙니다.

## 기본 실행 흐름

### 1. 약관과 정책 수집

```bash
python search_tos_fineprint.py --service "넷플릭스"
```

수집 결과는 기본적으로 다음 위치에 저장됩니다.

```text
RAG/terms/<서비스명>/knowledge_base.jsonl
```

조건을 만족하는 대표 이용약관은 기존 파이프라인과의 호환을 위해 `terms.txt`로도 저장될 수 있습니다.

이미 준비된 TXT, PDF, JSON 문서만 사용한다면 이 단계는 생략할 수 있습니다.

### 2. DB 인제스트

```bash
python ingest_rag.py
```

`RAG` 폴더의 TXT, PDF, JSON, JSONL 파일을 읽어 ChromaDB에 저장합니다.

### 3. DB 및 검색 검증

```bash
python verify_rag.py
```

다음 항목을 확인합니다.

- 전체 청크 수
- 파일별 `doc_subtype` 분류
- 인제스트 스키마 버전
- `article` 및 `article_no` 추출 결과
- 서비스 필터 동작
- 대표 질의의 기대 조항 검색 순위

## RAG 폴더 구조

```text
RAG/
├── law/
│   ├── 개인정보보호법.txt
│   └── 전자상거래법.txt
├── guideline/
│   └── 개인정보처리방침작성지침_2026/
├── faq/
│   └── 한국소비자원/
│       └── faq.json
└── terms/
    ├── 넷플릭스/
    │   ├── 이용약관.txt
    │   ├── 개인정보처리방침.pdf
    │   └── knowledge_base.jsonl
    ├── 카카오/
    ├── 쿠팡/
    ├── 유튜브/
    └── 티빙/
```

FAQ JSON은 `RAG/faq/<출처>/` 또는 `RAG/terms/<서비스>/` 아래에 둘 수 있습니다.

## 지원 파일 형식

| 형식 | 처리 방식 |
|---|---|
| `.txt` | 인코딩 감지 후 문서 구조에 따라 청킹 |
| `.pdf` | 텍스트 추출 후 필요하면 OCR 시도 |
| `.json` | FAQ 질문·답변을 항목별 청크로 저장 |
| `.jsonl` | 크롤러가 수집한 약관·정책 문서를 문서별로 인제스트 |

## 청킹 전략

TXT와 PDF 문서는 다음 우선순위로 청킹합니다.

| 우선순위 | 형식 | 예시 | 적용 대상 |
|---|---|---|---|
| 1 | 한국어 조문 | `제12조`, `제12조의3` | law, terms |
| 2 | 숫자 아웃라인 | `2.`, `2.7.`, `10.3.1.` | law, terms |
| 3 | 행정지침 번호 목록 | `1.`, `2.`, `3.` | guideline |
| 4 | 소제목 | `[계약 해지]` | terms, guideline |
| 5 | 글자 수 기반 fallback | 1,000자 단위 | 모든 문서 |

추가 처리:

- 기본 overlap은 120자입니다.
- 1,500자를 초과한 청크는 재분할합니다.
- 120자 미만의 청크는 주변 청크와 병합합니다.
- 연도 `2026.`처럼 4자리로 시작하는 값은 조항 번호로 인식하지 않습니다.
- FAQ JSON은 질문·답변 한 항목을 하나의 청크로 저장합니다.

## 문서 종류 자동 분류

TXT와 PDF는 파일명을 소문자로 변환한 뒤 다음 키워드로 `doc_subtype`을 추론합니다.

| `doc_subtype` | 대표 키워드 |
|---|---|
| `terms_of_use` | 이용약관, 서비스약관, 이용규칙, terms, terms_of_use, terms-of-use |
| `privacy_policy` | 개인정보, 프라이버시, privacy |
| `refund_policy` | 환불, 취소, 해지, refund, cancellation |
| `payment_policy` | 결제, 자동결제, 정기결제, payment, billing, renewal |
| `unknown` | 일치하는 키워드가 없는 경우 |

전체 이용약관 파일이 환불·결제 정책으로 잘못 분류되지 않도록 `terms_of_use` 키워드를 우선 검사합니다.

크롤러 JSONL은 파일명이 아니라 JSONL의 `document_type`을 다음과 같이 변환합니다.

```text
terms               → terms_of_use
privacy             → privacy_policy
refund_cancellation → refund_policy
billing_autorenewal → payment_policy
platform_refund     → refund_policy
```

FAQ의 `category`가 위 `doc_subtype` 값과 정확히 일치하면 해당 값을 사용합니다. 그 외에는 질문과 답변의 키워드로 다시 추론합니다.

## 조항 메타데이터

한국어 조문, 영문 숫자 섹션 및 대괄호 소제목을 지원합니다.

```text
제12조의3
→ article="제12조의3"
→ article_no="12조의3"

2.7. Refund Requests
→ article="2.7."
→ article_no="2.7"

[계약 해지]
→ article="[계약 해지]"
→ article_no="unknown"
```

번호가 없는 소제목은 `article`에는 저장하지만 번호 필드인 `article_no`에는 넣지 않습니다.

## 중복 및 갱신 처리

일반 문서는 전체 본문의 `document_hash`와 인제스트 스키마 버전을 확인합니다.

```text
같은 source + 같은 document_hash + 같은 schema
→ 재임베딩 없이 정상 스킵

같은 source + 변경된 본문 또는 변경된 schema
→ 기존 청크 삭제 후 재인제스트

다른 source + 같은 서비스 + 같은 본문
→ 중복 문서로 정상 스킵
```

현재 인제스트 스키마 버전은 다음과 같습니다.

```python
INGEST_SCHEMA_VERSION = 5
```

청킹 방식이나 메타데이터 구조가 변경되면 이 버전을 올려 기존 문서를 한 번 다시 인제스트합니다. 같은 본문과 같은 버전으로 다시 실행하면 일반 문서는 `[SKIP] 변경되지 않은 문서` 로그와 함께 정상 스킵됩니다.

FAQ JSON은 현재 실행할 때마다 기존 FAQ 청크를 삭제한 후 재삽입합니다.

## 주요 메타데이터

| 필드 | 값 예시 | 설명 |
|---|---|---|
| `type` | `law`, `guideline`, `terms`, `faq` | 문서의 상위 유형 |
| `doc_subtype` | `terms_of_use`, `refund_policy` | 서비스 문서의 세부 유형 |
| `service_name` | `넷플릭스`, `티빙`, `none` | 서비스 또는 자료 출처 |
| `source` | 파일 경로, URL, `pasted::...` | 원본 식별자 |
| `source_file` | `이용약관.pdf` | 표시용 원본 이름 |
| `source_kind` | `file`, `url`, `pasted`, `web_html`, `web_pdf` | 문서가 들어온 경로 |
| `scope` | `service_specific`, `shared` | 특정 서비스 전용 또는 공통 정책 |
| `article` | `제12조`, `2.7.`, `[계약 해지]` | 표시용 조항 또는 제목 |
| `article_no` | `12조`, `2.7`, `unknown` | 검색·필터용 조항 번호 |
| `chunk_index` | `0` | 문서 내 청크 순서 |
| `content_hash` | 해시 문자열 | 청크 단위 내용 식별자 |
| `document_hash` | 해시 문자열 | 문서 단위 중복 및 변경 감지 |
| `ingest_schema_version` | `5` | 인제스트 구조 버전 |
| `updated_at` | ISO 8601 시각 | 마지막 저장 시각 |

FAQ에는 추가로 다음 메타데이터가 저장됩니다.

| 필드 | 설명 |
|---|---|
| `question` | 질문 원문 |
| `answer` | 답변 원문 |

`scope="shared"`는 특정 서비스 전용이 아니라 여러 서비스에 공통 적용되는 정책을 의미합니다. 답변 생성 시 해당 사실을 함께 고려해야 합니다.

## DB 설정

인제스트와 검색은 반드시 동일한 설정을 사용해야 합니다.

```python
from config import DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL
```

임베딩 모델이 서로 다르면 저장된 문서와 질문이 다른 벡터 공간을 사용하게 되어 검색 품질이 크게 저하될 수 있습니다.

컬렉션은 `search_utils.py`에서 생성하고 `ingest_rag.py`가 같은 객체를 재사용합니다.

```python
from search_utils import collection
```

## 주요 인제스트 함수

### `check_document_exists(service_name, doc_subtype=None)`

해당 서비스의 `type="terms"` 문서가 DB에 존재하는지 확인합니다.

- `doc_subtype`을 생략하면 해당 서비스의 약관·정책 문서 중 하나라도 존재할 때 `True`를 반환합니다.
- `doc_subtype="terms_of_use"`를 지정하면 이용약관만 확인합니다.
- FAQ, 법령, 행정지침은 존재 여부 판단에서 제외합니다.

```python
from ingest_rag import check_document_exists

check_document_exists("넷플릭스")
check_document_exists("넷플릭스", "terms_of_use")
check_document_exists("넷플릭스", "privacy_policy")
```

### `ingest_from_url(...)`

URL에서 이미 추출한 본문을 DB에 저장합니다. 이 함수는 직접 웹 요청을 수행하지 않습니다.

```python
from ingest_rag import ingest_from_url

ingest_from_url(
    url="https://example.com/terms",
    service_name="서비스명",
    extracted_text="추출한 약관 본문",
    doc_type="terms",
    doc_subtype="terms_of_use",
)
```

`service_name`이 비어 있거나 `doc_type`이 `law`, `guideline`, `terms` 중 하나가 아니면 `ValueError`가 발생합니다.

### `ingest_from_pasted_text(...)`

사용자가 직접 제공한 텍스트를 DB에 저장합니다.

```python
from ingest_rag import ingest_from_pasted_text

ingest_from_pasted_text(
    service_name="티빙",
    pasted_text="사용자가 제공한 약관 본문",
    doc_subtype="refund_policy",
)
```

### `ingest_crawled_jsonl(path)`

`search_tos_fineprint.py`가 생성한 `knowledge_base.jsonl`을 DB에 저장합니다.

```python
from pathlib import Path
from ingest_rag import ingest_crawled_jsonl

ingest_crawled_jsonl(
    Path("RAG/terms/넷플릭스/knowledge_base.jsonl")
)
```

## 검색 사용 예시

```python
from search_utils import hybrid_search

results = hybrid_search(
    query="티빙캐시 환불은 어떻게 하나요?",
    service_name="티빙",
    doc_type="terms",
    n_results=5,
)

for result in results:
    print(result["metadata"].get("article"))
    print(result["text"])
```

현재 검색은 Sentence Transformer 기반 Dense 검색 결과에 도메인 키워드 일치 가중치를 적용해 재정렬합니다. BM25, RRF 및 Cross-Encoder reranker는 향후 고도화 항목입니다.

## 검증 결과

현재 대표 질의 검증 기준은 다음과 같습니다.

- 티빙 캐시 환불: `제12조`, `제17조`가 상위 5개에 포함
- 넷플릭스 환불: `2.7. Refund Requests`가 상위 3개에 포함
- 유튜브 구독 취소·환불: `4. 취소 및 환불`이 상위 5개에 포함

최근 검증 결과:

```text
3/3 통과
```

## 주의사항

- `RAG_PATH`가 상대 경로이므로 프로젝트 루트에서 `ingest_rag.py`를 실행하세요.
- DB를 다시 만들기 전에는 기존 `db` 폴더를 백업하는 것을 권장합니다.
- `scope="shared"`인 문서는 여러 서비스에 공통 적용되는 정책일 수 있습니다.
- 긴 조항이 여러 청크로 분리되면 일부 후속 청크의 `article`이 `unknown`일 수 있습니다.
- FAQ JSON은 일반 문서와 달리 현재 변경 감지 스킵을 적용하지 않습니다.
- HF Hub 미인증 경고는 다운로드 제한에 관한 경고입니다. 모델이 정상 로딩되면 검색 실행 오류는 아닙니다.

## 사용 모델 및 라이선스

이 프로젝트는 `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`
모델을 사용합니다.

- License: Apache License 2.0
- Model: https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2
- License: https://www.apache.org/licenses/LICENSE-2.0