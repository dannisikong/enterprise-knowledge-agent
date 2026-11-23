from contextlib import asynccontextmanager
import json
import logging
import os
from typing import Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.schemas.model_config import ModelConfig, ModelTestResponse

from app.services.document_service import (
    get_document_text,
    initialize_storage,
    list_documents,
    search_chunks,
    upload_document,
    reindex_documents,
    cleanup_session_documents,
)
from app.services.llm_service import (
    build_grounded_messages,
    generate_answer,
    llm_configured,
    stream_answer,
    validate_model_config,
)
from app.schemas.session import SessionResponse
from app.services.session_service import create_session, get_session, initialize_sessions, cleanup_expired_sessions, delete_sessions
from app.services.rate_limit_service import rate_limiter


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_storage()
    initialize_sessions()
    cleanup_expired_data()
    yield


app = FastAPI(
    title="Enterprise Knowledge Agent API",
    version="0.5.0",
    description="API for document ingestion, retrieval and grounded knowledge answers.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)
    mode: Literal["auto", "keyword", "vector", "hybrid"] = "auto"
    rerank: bool = False


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)
    rerank: bool = False
    model_settings: ModelConfig | None = None


def cleanup_expired_data() -> None:
    expired = cleanup_expired_sessions()
    cleanup_session_documents(expired)
    delete_sessions(expired)


async def require_session(x_session_token: str | None = Header(default=None)) -> dict:
    cleanup_expired_data()
    session = get_session(x_session_token)
    if session is None:
        raise HTTPException(status_code=401, detail="A valid demo session is required.")
    if not rate_limiter.allow(session["id"]):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    return session


@app.post("/session", response_model=SessionResponse, tags=["session"])
async def new_session() -> dict[str, str]:
    return create_session()




@app.post("/model/test", response_model=ModelTestResponse, tags=["model"])
async def test_model(config: ModelConfig, session: dict = Depends(require_session)) -> dict:
    try:
        validate_model_config(config)
        await generate_answer(
            [{"role": "user", "content": "Reply with the single word OK."}],
            config,
        )
        return {"ok": True, "message": "Model connection successful."}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.warning("Model connection test failed for session %s", session["id"])
        raise HTTPException(status_code=502, detail="Model connection failed. Check the Base URL, model and API key.") from error


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "enterprise-knowledge-agent"}


@app.post("/documents", tags=["documents"])
async def create_document(file: UploadFile = File(...), session: dict = Depends(require_session)) -> dict:
    try:
        return await upload_document(file, session["id"])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=422, detail="Unable to parse this document.") from error
    finally:
        await file.close()


@app.get("/documents", tags=["documents"])
async def documents(session: dict = Depends(require_session)) -> list[dict]:
    return list_documents(session["id"])


@app.post("/documents/reindex", tags=["documents"])
async def reindex_session_documents(session: dict = Depends(require_session)) -> dict:
    try:
        return await reindex_documents(session["id"])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/documents/{document_id}/text", tags=["documents"])
async def document_text(document_id: str, session: dict = Depends(require_session)) -> dict:
    document = get_document_text(document_id, session["id"])
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@app.post("/search", tags=["retrieval"])
async def search(request: SearchRequest, session: dict = Depends(require_session)) -> dict:
    try:
        return await search_chunks(request.query, request.limit, request.mode, request.rerank, session["id"])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def _retrieve_for_chat(request: ChatRequest, session_id: str) -> tuple[list[dict], list[dict]]:
    if not llm_configured(request.model_settings):
        raise HTTPException(status_code=503, detail="Please configure a valid chat model in Model Settings.")
    try:
        retrieval = await search_chunks(request.query, request.limit, "hybrid", request.rerank, session_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    messages, sources = build_grounded_messages(request.query, retrieval["results"])
    return messages, sources


@app.post("/chat", tags=["chat"])
async def chat(request: ChatRequest, session: dict = Depends(require_session)) -> dict:
    messages, sources = await _retrieve_for_chat(request, session["id"])
    if not sources:
        return {
            "answer": "我暂时无法从知识库检索到相关资料，因此没有足够依据回答这个问题。请尝试换一种问法，或先上传相关文档。",
            "sources": [],
            "retrieval": {"mode": "hybrid", "result_count": 0},
        }
    try:
        answer = await generate_answer(messages, request.model_settings)
    except Exception as error:
        raise HTTPException(status_code=502, detail="LLM provider request failed.") from error
    return {
        "answer": answer,
        "sources": sources,
        "retrieval": {"mode": "hybrid", "result_count": len(sources)},
    }


@app.post("/chat/stream", tags=["chat"])
async def chat_stream(request: ChatRequest, session: dict = Depends(require_session)):
    messages, sources = await _retrieve_for_chat(request, session["id"])

    async def event_stream():
        def event(name: str, payload: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield event("sources", {"sources": sources, "retrieval": {"mode": "hybrid", "result_count": len(sources)}})
        if not sources:
            yield event("token", {"content": "我暂时无法从知识库检索到相关资料，因此没有足够依据回答这个问题。请尝试换一种问法，或先上传相关文档。"})
            yield event("done", {})
            return
        try:
            async for token in stream_answer(messages, request.model_settings):
                yield event("token", {"content": token})
            yield event("done", {})
        except Exception:
            logger.exception("LLM streaming response failed")
            yield event("error", {"message": "LLM 流式生成失败，请检查模型服务配置后重试。"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
