"""FinePrint React UI와 Python RAG/Agent를 연결하는 HTTP API."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field, HttpUrl

# 로컬 프로젝트에서 명시적으로 설정한 .env를 상속된 오래된 키보다 우선한다.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from Siyeong.ensure_service_ingested import (
    ingest_user_document,
    ingest_user_url,
    prepare_knowledge_base,
)
from msh.agent.workflow import graph
from msh.agent.runtime import run_agent_workflow


class PrepareServiceRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)


class IngestUrlRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    document_type: str = "terms"


class QuestionRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    policy_urls: dict[str, HttpUrl] = Field(default_factory=dict)
    include_trace: bool = False


class AgentAnswer(BaseModel):
    problem_type: str | None = None
    terms_evidence: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)
    simple_explanation: str | None = None
    check_items: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    required_materials: list[str] = Field(default_factory=list)
    inquiry_draft: str | None = None
    follow_up_questions: list[str] = Field(default_factory=list)
    message: str | None = None


class AgentRunMeta(BaseModel):
    primary_intent: str | None = None
    related_intents: list[str] = Field(default_factory=list)
    is_in_scope: bool | None = None
    verification_status: str | None = None
    verification_reason: str | None = None
    retry_count: int = 0
    trace: list[dict[str, Any]] | None = None


class QuestionResponse(BaseModel):
    answer: AgentAnswer
    knowledge_base_status: dict[str, Any]
    meta: AgentRunMeta


def _cors_origins() -> list[str]:
    configured = os.getenv("FINEPRINT_CORS_ORIGINS", "")
    if configured.strip():
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


app = FastAPI(title="FinePrint API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _validate_document_type(document_type: str) -> str:
    if document_type not in {"terms", "privacy"}:
        raise HTTPException(
            status_code=400,
            detail="document_type은 terms 또는 privacy여야 합니다.",
        )
    return document_type


def _agent_http_exception(exc: Exception) -> HTTPException:
    """외부 AI 오류를 비밀정보가 포함되지 않은 API 오류로 변환한다."""

    status_code = getattr(exc, "status_code", None)
    if status_code == 401:
        return HTTPException(
            status_code=502,
            detail={
                "code": "OPENAI_AUTH_FAILED",
                "message": "OpenAI 인증에 실패했습니다. 서버의 OPENAI_API_KEY를 확인해 주세요.",
            },
        )
    if status_code == 429:
        return HTTPException(
            status_code=503,
            detail={
                "code": "OPENAI_RATE_LIMITED",
                "message": "OpenAI 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.",
            },
        )
    return HTTPException(
        status_code=500,
        detail={
            "code": "AGENT_EXECUTION_FAILED",
            "message": "Agent 실행 중 오류가 발생했습니다. 서버 로그를 확인해 주세요.",
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/services/prepare")
def prepare_service(payload: PrepareServiceRequest) -> dict[str, object]:
    try:
        return prepare_knowledge_base(payload.service_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"서비스 준비 실패: {exc}") from exc


@app.post("/services/url")
def ingest_url(payload: IngestUrlRequest) -> dict[str, object]:
    document_type = _validate_document_type(payload.document_type)
    try:
        ingested = ingest_user_url(
            url=str(payload.url),
            service_name=payload.service_name,
            document_type=document_type,
        )
        if not ingested:
            raise HTTPException(
                status_code=422,
                detail="입력한 URL에서 약관 본문을 가져오지 못했습니다.",
            )
        return prepare_knowledge_base(payload.service_name)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"URL 수집 실패: {exc}") from exc


@app.post("/services/document")
async def ingest_document(
    service_name: str = Form(..., min_length=1, max_length=200),
    document_type: str = Form("terms"),
    file: UploadFile = File(...),
) -> dict[str, object]:
    document_type = _validate_document_type(document_type)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        raise HTTPException(status_code=400, detail="PDF와 TXT 파일만 업로드할 수 있습니다.")

    temporary_path: Path | None = None
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="업로드한 파일이 비어 있습니다.")
        if len(content) > 20 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="파일은 20MB 이하여야 합니다.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary:
            temporary.write(content)
            temporary_path = Path(temporary.name)

        subtype = "terms_of_use" if document_type == "terms" else "privacy_policy"
        ingested = await asyncio.to_thread(
            ingest_user_document,
            path=temporary_path,
            service_name=service_name,
            doc_subtype=subtype,
        )
        if not ingested:
            raise HTTPException(status_code=422, detail="문서를 읽거나 DB에 저장하지 못했습니다.")
        return await asyncio.to_thread(prepare_knowledge_base, service_name)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"문서 처리 실패: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()


@app.post("/questions", response_model=QuestionResponse)
@app.post("/api/v1/agent/analyze", response_model=QuestionResponse)
async def ask_question(payload: QuestionRequest) -> QuestionResponse:
    try:
        # 문서 탐색/인제스트와 RAG/LLM 실행은 모두 블로킹 I/O를 포함할 수 있다.
        status = await asyncio.to_thread(
            prepare_knowledge_base,
            payload.service_name,
            policy_urls={
                name: str(url)
                for name, url in payload.policy_urls.items()
            },
        )
        if not status.get("service_documents_ready"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "POLICY_INPUT_REQUIRED",
                    "message": "약관을 찾지 못했습니다. 공식 URL 또는 PDF/TXT 파일을 입력해 주세요.",
                    "knowledge_base_status": status,
                },
            )

        result = await run_agent_workflow(
            graph,
            service_name=str(status.get("service_name", payload.service_name)),
            user_question=payload.question,
            policy_urls={
                name: str(url)
                for name, url in payload.policy_urls.items()
            },
        )
        return QuestionResponse(
            answer=AgentAnswer.model_validate(result["final_answer"]),
            knowledge_base_status=result.get("knowledge_base_status", status),
            meta=AgentRunMeta(
                primary_intent=result.get("primary_intent"),
                related_intents=result.get("related_intents", []),
                is_in_scope=result.get("is_in_scope"),
                verification_status=result.get("verification_status"),
                verification_reason=result.get("verification_reason"),
                retry_count=result.get("retry_count", 0),
                trace=result.get("round_logs") if payload.include_trace else None,
            ),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _agent_http_exception(exc) from exc

