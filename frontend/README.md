# FinePrint UI

FinePrint Python RAG/Agent와 연결된 React UI입니다.

## 1. Python 백엔드 실행

FinePrint 백엔드 저장소에서 다음을 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
# .env에 OPENAI_API_KEY와 필요 시 TAVILY_API_KEY 입력
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## 2. UI 실행

이 폴더에서 다음을 실행합니다.

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`을 엽니다. Python API 주소를 바꾸려면
`.env`의 `VITE_FINEPRINT_API_URL`을 수정합니다.

## 실제 연결 흐름

1. 서비스명 입력
2. Python이 ChromaDB 확인
3. 문서가 없으면 `search_fineprint_v2.py`로 공식 약관 자동 수집
4. 자동 수집까지 실패하면 UI가 공식 URL 또는 PDF/TXT 입력을 요청
5. 질문 입력 후 Hybrid RAG 검색 → 답변 생성 → 근거 검증 Agent 실행
6. 문제 유형, 약관 근거, 출처, 확인사항, 다음 행동, 준비자료, 문의 초안을 화면에 표시

PDF/TXT는 브라우저에서 텍스트로 흉내 내지 않고 실제 파일을 Python API로 전송합니다.
