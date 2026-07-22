# FinePrint

구독형 서비스의 공식 약관·정책과 소비자 보호 자료를 함께 검색해 문제 해결
근거와 다음 행동을 안내하는 RAG 기반 Agent입니다.

## 통합 흐름

1. `jhc/search_fineprint_v2.py`: 공식 약관·개인정보처리방침 탐색 및 수집
2. `Siyeong/ingest_rag.py`: PDF/TXT 전처리, 청킹, 임베딩 및 ChromaDB 저장
3. `Siyeong/search_utils.py`: 약관 DB와 소비자 보호 DB Hybrid RAG 검색
4. `msh/agent`: 의도 분류, 근거 검색, 답변 생성, 검증 및 재검색

소비자 보호 및 기존 원천 문서는 `Siyeong/data`, 최종 수집기가 찾은 서비스별
약관·정책은 `jhc/RAG/terms`에 저장됩니다. 각각 `FINEPRINT_DATA_PATH`,
`FINEPRINT_POLICY_DATA_PATH` 환경 변수로 위치를 변경할 수 있습니다.

## 실행 준비

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

`.env` 또는 실행 환경에 `OPENAI_API_KEY`를 설정합니다. 등록되지 않은 서비스의
공식 문서를 Tavily로 자동 탐색하려면 `TAVILY_API_KEY`도 설정합니다.

## 실행

Agent 통합 테스트:

```powershell
python -m msh.test_agent
```

수집기만 대화형으로 실행:

```powershell
python -m jhc.search_fineprint_v2 --service 넷플릭스
```

검색 전에 `msh/rag_adapter.py`가 소비자 보호 자료와 해당 서비스 문서의 DB 상태를
확인합니다. 사용자가 공식 URL을 지정했다면 그 URL을 먼저 사용하고, 로컬 문서,
등록된 공식 URL, Tavily 자동 탐색 순으로 보완합니다. 수집된 파일은 같은
프로세스에서 즉시 인제스트합니다.

공식 URL을 CLI에서 직접 지정할 수도 있습니다.

```powershell
python -m jhc.search_fineprint_v2 --service 넷플릭스 `
  --terms-url "https://help.netflix.com/ko/legal/termsofuse" `
  --privacy-url "https://help.netflix.com/ko/legal/privacy"
```

Agent 상태로 전달할 때는 `policy_urls` 선택 필드를 사용합니다.

```python
initial_state = {
    "service_name": "넷플릭스",
    "user_question": "해지했는데 다음 달에도 결제됐어요",
    "policy_urls": {
        "terms": "https://help.netflix.com/ko/legal/termsofuse",
        "privacy": "https://help.netflix.com/ko/legal/privacy",
    },
    "retry_count": 0,
    "round_logs": [],
}
```

UI에서 사용자가 PDF/TXT 또는 URL을 직접 지정한 경우에는 다음 공개 함수를 호출합니다.

```python
from Siyeong.ensure_service_ingested import ingest_user_document, ingest_user_url

ingest_user_document(path, service_name="넷플릭스")
ingest_user_url(url, service_name="넷플릭스", document_type="terms")
```

## React UI 연결용 API

React UI는 Python 모듈을 직접 실행하지 않고 `api.py`의 HTTP API를 호출합니다.

```powershell
Copy-Item .env.example .env
# .env에 OPENAI_API_KEY와 필요 시 TAVILY_API_KEY 입력
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

주요 엔드포인트는 다음과 같습니다.

- `POST /services/prepare`: DB 확인 후 없으면 자동 수집·인제스트
- `POST /services/url`: 사용자가 입력한 공식 URL 수집·인제스트
- `POST /services/document`: PDF/TXT 업로드·인제스트
- `POST /questions`: Hybrid RAG 검색과 검증 Agent 실행

서비스명 준비 결과의 `service_documents_ready`가 `false`이면 UI가 URL 또는
문서 입력 화면으로 전환합니다.

React 화면은 `frontend/`에 있습니다. Python API를 먼저 실행한 뒤 새 터미널에서
다음 명령으로 UI를 실행합니다.

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run dev
```

기본 접속 주소는 `http://localhost:3000`, Python API 주소는
`http://127.0.0.1:8000`입니다.
