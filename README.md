# FinePrint

> 구독 서비스 약관과 소비자 보호 자료를 함께 검색해, 사용자가 확인해야 할 조항과 다음 행동을 안내하는 근거 기반 AI 서비스

FinePrint는 해지, 환불, 자동결제, 개인정보 문제를 겪은 사용자가 긴 약관을 직접 탐색하지 않아도 관련 조항과 소비자 보호 근거를 확인할 수 있도록 만든 팀 프로젝트입니다.

이 브랜치는 전체 서비스 중 제가 담당한 **문서 전처리, 임베딩, ChromaDB 지식베이스, 검색 및 검증 코드**를 중심으로 정리한 개인 포트폴리오 브랜치입니다.

- 개발 기간: **2026.07.01 ~ 2026.07.22**
- 팀 구성: 5명
- 담당 영역: **Embedding / Knowledge Base**
- 팀 최종 결과물: [`main` 브랜치](../../tree/main)

---

## 프로젝트 배경

구독 서비스는 가입은 쉽지만 해지와 환불 조건을 확인하는 과정은 복잡합니다.

사용자는 다음 내용을 동시에 확인해야 합니다.

- 서비스 약관에서 내 상황에 해당하는 조항
- 환불·해지·자동갱신에 적용되는 조건
- 소비자 보호 법령과 행정지침
- 실제 문의나 이의제기를 위해 준비해야 할 정보

FinePrint는 서비스 약관과 소비자 보호 자료를 검색 가능한 지식베이스로 만들고, Agent가 근거를 바탕으로 답변을 생성하고 검증할 수 있도록 설계했습니다.

---

## 전체 서비스 흐름

```text
공식 문서 수집
    ↓
문서 유형 분류 및 구조 기반 청킹
    ↓
다국어 임베딩 생성
    ↓
ChromaDB 영속 저장
    ↓
서비스·문서 유형 필터
    ↓
Dense 검색 + 키워드 재정렬
    ↓
LangGraph Agent의 답변 생성·검증·복구
    ↓
근거·출처·확인사항·다음 행동 제공
```

LangGraph 기반 생성·검증 Agent는 팀원이 담당했으며, 저는 Agent가 사용할 근거를 안정적으로 반환하는 **RAG 지식베이스와 Retrieval 계층**을 담당했습니다.

---

## 담당 기능

### 1. 문서 형식별 인제스트

다음 형식의 약관과 소비자 보호 자료를 하나의 ChromaDB 컬렉션으로 적재할 수 있도록 구현했습니다.

| 형식 | 처리 방법 |
|---|---|
| TXT | 인코딩 감지 후 구조 기반 청킹 |
| PDF | 텍스트 추출, 품질이 낮으면 OCR 시도 |
| JSON | FAQ 질문·답변을 항목 단위로 저장 |
| JSONL | 크롤러가 수집한 약관·정책을 문서 단위로 저장 |
| URL 본문 | 추출된 본문을 공통 인제스트 함수로 전달 |
| 직접 입력 | 사용자가 붙여넣은 텍스트를 약관 문서로 저장 |

파일, URL, 직접 입력은 최종적으로 `ingest_text()`를 거치도록 통합하여 입력 경로가 달라도 같은 청킹·메타데이터·중복 검사 규칙을 적용했습니다.

### 2. 문서 구조 기반 청킹

고정 길이로만 자르면 조항 제목과 예외 조건이 분리될 수 있기 때문에 문서 구조를 먼저 인식하도록 구현했습니다.

청킹 우선순위:

1. 한국어 조문: `제12조`, `제12조의3`
2. 영문 숫자 섹션: `2.`, `2.7.`, `10.3.1.`
3. 행정지침 번호 목록
4. 대괄호 및 소제목
5. 구조를 찾지 못한 경우 글자 수 기반 분할

Fallback 설정:

```python
chunk_size = 1000
chunk_overlap = 120
```

추가로 다음 보정 로직을 적용했습니다.

- 1,500자를 초과하는 조항은 재분할
- 120자 미만의 짧은 조각은 주변 청크와 병합
- `2026.`처럼 연도로 판단되는 값은 조항 번호에서 제외
- FAQ는 질문과 답변 한 쌍을 하나의 청크로 저장

즉, `1,000/120`은 모든 문서에 일괄 적용되는 기준이 아니라 **문서 구조를 인식하지 못하거나 조항이 지나치게 긴 경우 사용하는 보조 전략**입니다.

### 3. 다국어 임베딩과 ChromaDB

사용 모델:

```text
sentence-transformers/paraphrase-multilingual-mpnet-base-v2
```

- 한국어와 영어 약관을 동일한 의미 공간에서 검색
- 768차원 문장 임베딩
- ChromaDB `PersistentClient`를 이용한 로컬 영속 저장
- 인제스트와 검색이 동일한 모델·DB·컬렉션 설정을 공유

`config.py`에서 다음 값을 공통 관리해 저장 시점과 검색 시점의 임베딩 모델이 달라지는 문제를 방지했습니다.

```python
DB_PATH
COLLECTION_NAME
EMBEDDING_MODEL
```

### 4. 검색 및 재정렬

현재 구현은 BM25와 Dense Retrieval을 결합한 전통적인 Hybrid Search가 아닙니다.

구현된 검색 흐름은 다음과 같습니다.

1. 서비스명과 문서 유형으로 검색 범위 필터링
2. Sentence Transformer 기반 Dense 검색
3. 최대 15개 후보 청크 확보
4. 질문의 도메인 키워드와 문서 내용 비교
5. 키워드 일치 수에 따라 거리 점수를 보정
6. 재정렬된 Top-K 결과 반환

```python
adjusted_score = distance - (keyword_match * 0.15)
```

사용한 주요 키워드는 청약철회, 환불, 해지, 위약금, 자동결제, 자동갱신, 개인정보, 제3자 제공, 손해배상 등입니다.

서비스명이 `Netflix`, `NETFLIX`, `넷플릭스`처럼 다르게 입력될 수 있어 한글·영문 별칭을 검색 후보로 확장하는 로직도 추가했습니다.

BM25, RRF, Cross-Encoder reranker는 향후 고도화 항목입니다.

---

## 데이터 정합성 관리

### 문서 해시 기반 중복·변경 감지

전체 문서의 `document_hash`를 계산해 다음 상황을 구분합니다.

```text
같은 source + 같은 본문 + 같은 schema
→ 재임베딩 없이 SKIP

같은 source + 변경된 본문
→ 기존 청크 삭제 후 재인제스트

같은 source + 변경된 schema
→ 본문이 같아도 재인제스트

다른 source + 같은 서비스 + 같은 본문
→ 중복 문서로 판단하고 SKIP
```

### 스키마 버전

```python
INGEST_SCHEMA_VERSION = 5
```

스키마 버전은 DB 파일의 존재 여부가 아니라 해당 데이터를 생성한 규칙을 식별합니다.

청킹 방식이나 메타데이터 구조가 변경되면 버전을 올려 기존 본문을 다시 인제스트합니다. 개발 중 persistent DB를 삭제했더라도, 이후 동일한 규칙으로 생성된 데이터인지 판별할 수 있도록 버전 값은 유지했습니다.

### 기존 청크 삭제 후 Upsert

문서가 변경되었을 때 단순 `upsert`만 수행하면 이전 버전에서 생성된 청크 수가 더 많았던 경우 일부 구버전 청크가 남을 수 있습니다.

따라서 같은 source를 갱신할 때는:

```text
기존 source 청크 삭제
→ 새 청킹 결과 생성
→ 배치 Upsert
```

순서로 교체합니다.

청크마다 DB 요청을 보내지 않고 `ids`, `documents`, `metadatas`를 모아 한 번에 Upsert하여 임베딩과 저장을 배치 처리했습니다.

---

## 주요 메타데이터

| 필드 | 설명 |
|---|---|
| `type` | law, guideline, terms, faq |
| `doc_subtype` | 이용약관, 개인정보, 환불, 결제 정책 구분 |
| `service_name` | 문서가 적용되는 서비스 |
| `source` | 파일 경로, URL 또는 직접 입력 식별자 |
| `source_kind` | file, url, pasted, web_html, web_pdf |
| `scope` | 특정 서비스 전용 또는 공통 정책 |
| `article` | 화면에 표시할 조항 또는 소제목 |
| `article_no` | 검색·검증에 사용할 정규화된 조항 번호 |
| `chunk_index` | 문서 내 청크 순서 |
| `content_hash` | 청크 단위 내용 식별자 |
| `document_hash` | 문서 단위 중복·변경 식별자 |
| `ingest_schema_version` | 인제스트 규칙 버전 |
| `updated_at` | 마지막 저장 시각 |

---

## 검증

`verify_rag.py`에서 다음 항목을 확인합니다.

- 전체 청크 수와 문서별 메타데이터
- 조항 및 조항 번호 추출 결과
- 서비스명 필터 동작
- 기대 조항의 Top-K 포함 여부
- FAQ 검색 결과
- 지원 범위 밖 질문의 검색 결과
- 검색 거리, 키워드 일치 수, 보정 점수 로그

대표 검색 검증:

| 질문 | 기대 근거 |
|---|---|
| 티빙캐시 환불은 어떻게 하나요? | 제12조, 제17조 |
| Netflix cancellation refund policy | 2.7. Refund Requests |
| 유튜브 프리미엄 구독 취소·환불 | 4. 취소 및 환불 |

대표 3개 조항 검색 테스트에서 기대 조항이 지정된 Top-K 안에 포함되는 것을 확인했습니다.

팀 통합 단계에서는 별도로 환불, 자동갱신, 개인정보 시나리오를 평가했습니다.

- 환불: 첫 검증에서 `PASS`
- 자동갱신: `REGENERATE` 후 `PASS`
- 개인정보: `RETRIEVE_AGAIN` 후 `PASS`

이 결과는 Retrieval 단독 평가가 아니라 LangGraph Agent까지 연결한 전체 흐름의 평가입니다.

---

## 기술 스택

### 개인 담당 영역

- Python
- ChromaDB
- Sentence Transformers
- LangChain Text Splitters
- PyPDF2
- pdf2image / pytesseract

### 팀 전체 서비스

- React 19 / TypeScript / Vite / Tailwind CSS
- FastAPI / Uvicorn / Pydantic
- LangGraph / LangChain / OpenAI GPT-4o
- Tavily / Playwright / Trafilatura
- ChromaDB / Sentence Transformers

---

## 주요 파일

| 파일 | 역할 |
|---|---|
| `Siyeong/config.py` | DB 경로, 컬렉션, 임베딩 모델, 서비스 별칭 |
| `Siyeong/ingest_rag.py` | 로딩, OCR, 청킹, 중복 검사, DB 적재 |
| `Siyeong/search_utils.py` | 필터링, Dense 검색, 키워드 재정렬 |
| `Siyeong/verify_rag.py` | 메타데이터 및 기대 조항 검색 검증 |
| `Siyeong/ensure_service_ingested.py` | 미수집 서비스의 선택적 인제스트 연결 |
| `RAG/` | 약관·법령·지침·FAQ 원본 데이터 |
| `siyeong_requirements.txt` | 개인 개발 환경 의존성 |

---

## 실행 방법

```bash
git clone https://github.com/smf3446/FinePrint-Hybrid-Retrieval.git
cd FinePrint-Hybrid-Retrieval
git switch siyeong
```

의존성 설치:

```bash
pip install -r siyeong_requirements.txt
```

프로젝트 루트에서 인제스트:

```bash
python Siyeong/ingest_rag.py
```

DB 및 검색 검증:

```bash
python Siyeong/verify_rag.py
```

ChromaDB는 기본적으로 다음 위치에 생성됩니다.

```text
Siyeong/db/
```

---

## 개발 일정

| 기간 | 작업 |
|---|---|
| 07.01–07.10 | 서비스 기획, 시나리오 및 전체 구조 설계 |
| 07.13–07.16 | 공식 문서 수집, RAG·Agent 구현, UI 프로토타입 |
| 07.17–07.20 | Hybrid Retrieval, 검증·복구 루프, 반복 테스트 |
| 07.21 | 코드 병합, FastAPI 연결, 공용 경로 정리 |
| 07.21–07.22 | UI·백엔드 연결, 전체 테스트, 발표·시연 준비 |

---

## 한계 및 개선 방향

- 현재 키워드 재정렬은 정해진 도메인 키워드에 의존
- 청킹 및 키워드 가중치 `0.15`에 대한 정량적 최적화가 필요
- FAQ는 일반 문서와 달리 변경 감지 스킵을 적용하지 않음
- 약관의 유효기간과 최신 버전을 자동 선택하는 기능은 미완성
- BM25, RRF 및 Cross-Encoder 기반 재정렬은 미구현
- 현재 평가는 제한된 대표 질문 중심

향후에는 Recall@K 기반 검색 평가셋, 약관 버전 라이프사이클, Sparse Retrieval과 RRF, 국내법과 서비스 약관 비교 기능을 추가할 수 있습니다.

---

## 브랜치 안내

| 브랜치 | 내용 |
|---|---|
| `siyeong` | 개인 담당 RAG·Embedding·Knowledge Base 구현 |
| `main` | 팀 프로젝트 최종 통합 코드 |

---

## 유의사항

FinePrint는 약관과 소비자 보호 근거를 쉽게 확인하기 위한 보조 서비스입니다. 제공되는 답변은 법률적 판단이나 전문 법률 자문을 대신하지 않습니다.
