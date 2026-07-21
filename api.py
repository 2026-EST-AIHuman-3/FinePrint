"""FinePrint React UI와 Python RAG/Agent를 연결하는 HTTP API."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl

from Siyeong.ensure_service_ingested import (
    ingest_user_document,
    ingest_user_url,
    prepare_knowledge_base,
)
from msh.agent.workflow import graph


class PrepareServiceRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)


class IngestUrlRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    url: HttpUrl
    document_type: str = "terms"


class QuestionRequest(BaseModel):
    service_name: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)


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
        ingested = ingest_user_document(
            path=temporary_path,
            service_name=service_name,
            doc_subtype=subtype,
        )
        if not ingested:
            raise HTTPException(status_code=422, detail="문서를 읽거나 DB에 저장하지 못했습니다.")
        return prepare_knowledge_base(service_name)
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


@app.post("/questions")
def ask_question(payload: QuestionRequest) -> dict[str, object]:
    try:
        status = prepare_knowledge_base(payload.service_name)
        if not status.get("service_documents_ready"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "POLICY_INPUT_REQUIRED",
                    "message": "약관을 찾지 못했습니다. 공식 URL 또는 PDF/TXT 파일을 입력해 주세요.",
                    "knowledge_base_status": status,
                },
            )

        result = graph.invoke(
            {
                "service_name": str(status.get("service_name", payload.service_name)),
                "user_question": payload.question,
                "policy_urls": {},
                "retry_count": 0,
                "round_logs": [],
                "improvement_instruction": "",
            }
        )
        return {
            "answer": result.get("final_answer", {}),
            "knowledge_base_status": result.get("knowledge_base_status", status),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent 실행 실패: {exc}") from exc

