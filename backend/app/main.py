from contextlib import asynccontextmanager
import ipaddress
import json
import logging
import os
from typing import Literal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
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
    upload_zip_documents,
    reindex_documents,
    reindex_document,
    delete_document,
    cleanup_session_documents,
)
from app.services.llm_service import (
    build_grounded_messages,
    generate_answer,
    llm_configured,
    stream_answer,
    summarize_conversation,
    validate_model_config,
)
from app.schemas.session import SessionResponse
from app.services.session_service import create_session, get_session, initialize_sessions, cleanup_expired_sessions, delete_sessions
from app.services.rate_limit_service import rate_limiter, session_creation_limiter
from app.services.security_audit_service import audit_security_event
from app.services.conversation_service import (
    initialize_conversations, create_conversation, get_conversation, list_conversations,
    save_message, list_messages, recent_history, delete_conversation, cleanup_session_conversations,
    get_conversation_memory, messages_to_summarize, save_conversation_summary,
)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_storage()
    initialize_sessions()
    initialize_conversations()
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


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)
    rerank: bool = False
    model_settings: ModelConfig | None = None


def cleanup_expired_data() -> None:
    expired = cleanup_expired_sessions()
    cleanup_session_conversations(expired)
    cleanup_session_documents(expired)
    delete_sessions(expired)


def _session_creation_client_key(request: Request) -> str:
    # Use the ASGI peer address. Do not trust X-Forwarded-For unless a trusted
    # proxy chain is explicitly configured at the deployment boundary.
    if request.client is None:
        return "unknown"
    try:
        return ipaddress.ip_address(request.client.host).compressed
    except ValueError:
        return "unknown"


async def require_session(
    request: Request,
    x_session_token: str | None = Header(default=None),
) -> dict:
    cleanup_expired_data()
    session = get_session(x_session_token)
    if session is None:
        audit_security_event(
            "authentication_failed",
            client_ip=_session_creation_client_key(request),
            reason="missing_or_invalid_session",
        )
        raise HTTPException(status_code=401, detail="A valid demo session is required.")
    if not rate_limiter.allow(session["id"]):
        audit_security_event(
            "request_rate_limited",
            session_id=session["id"],
            client_ip=_session_creation_client_key(request),
        )
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    return session


@app.post("/session", response_model=SessionResponse, tags=["session"])
async def new_session(request: Request) -> dict[str, str]:
    client_key = _session_creation_client_key(request)
    if not session_creation_limiter.allow(client_key):
        audit_security_event(
            "session_creation_rate_limited",
            client_ip=client_key,
        )
        raise HTTPException(status_code=429, detail="Too many sessions created. Please try again later.")
    created = create_session()
    audit_security_event("session_created", session_id=created["session_id"], client_ip=client_key)
    return created


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
        audit_security_event(
            "document_upload_rejected",
            session_id=session["id"],
            reason=type(error).__name__,
        )
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        audit_security_event(
            "document_upload_failed",
            session_id=session["id"],
            reason=type(error).__name__,
        )
        raise HTTPException(status_code=422, detail="Unable to parse this document.") from error
    finally:
        await file.close()



@app.post("/documents/archive", tags=["documents"])
async def create_documents_archive(file: UploadFile = File(...), session: dict = Depends(require_session)) -> dict:
    try:
        return await upload_zip_documents(file, session["id"])
    except ValueError as error:
        audit_security_event(
            "document_archive_upload_rejected",
            session_id=session["id"],
            reason=type(error).__name__,
        )
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        audit_security_event(
            "document_archive_upload_failed",
            session_id=session["id"],
            reason=type(error).__name__,
        )
        logger.exception("ZIP document import failed")
        raise HTTPException(status_code=422, detail="Unable to process this ZIP archive.") from error
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


@app.delete("/documents/{document_id}", tags=["documents"])
async def remove_document(document_id: str, session: dict = Depends(require_session)) -> dict:
    if not delete_document(document_id, session["id"]):
        audit_security_event(
            "document_access_denied",
            session_id=session["id"],
            resource_id=document_id,
            reason="delete_not_found_or_not_owned",
        )
        raise HTTPException(status_code=404, detail="Document not found.")
    audit_security_event("document_deleted", session_id=session["id"], resource_id=document_id)
    return {"deleted": True}


@app.post("/documents/{document_id}/reindex", tags=["documents"])
async def reindex_one_document(document_id: str, session: dict = Depends(require_session)) -> dict:
    try:
        result = await reindex_document(document_id, session["id"])
        if result["status"] == "failed":
            audit_security_event(
                "document_reindex_failed",
                session_id=session["id"],
                resource_id=document_id,
                reason="embedding_generation_failed",
            )
        return result
    except ValueError as error:
        if str(error) == "Document not found.":
            audit_security_event(
                "document_access_denied",
                session_id=session["id"],
                resource_id=document_id,
                reason="reindex_not_found_or_not_owned",
            )
            raise HTTPException(status_code=404, detail="Document not found.") from error
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/documents/{document_id}/text", tags=["documents"])
async def document_text(document_id: str, session: dict = Depends(require_session)) -> dict:
    document = get_document_text(document_id, session["id"])
    if document is None:
        audit_security_event(
            "document_access_denied",
            session_id=session["id"],
            resource_id=document_id,
            reason="not_found_or_not_owned",
        )
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@app.post("/search", tags=["retrieval"])
async def search(request: SearchRequest, session: dict = Depends(require_session)) -> dict:
    try:
        return await search_chunks(request.query, request.limit, request.mode, request.rerank, session["id"])
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def _retrieve_for_chat(request: ChatRequest, session_id: str, history: list[dict] | None = None, summary: str | None = None) -> tuple[list[dict], list[dict]]:
    if not llm_configured(request.model_settings):
        raise HTTPException(status_code=503, detail="Please configure a valid chat model in Model Settings.")
    try:
        retrieval = await search_chunks(request.query, request.limit, "hybrid", request.rerank, session_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    messages, sources = build_grounded_messages(request.query, retrieval["results"], history=history, summary=summary)
    return messages, sources


async def _prepare_conversation_summary(conversation_id: str, model_settings=None) -> str:
    memory = get_conversation_memory(conversation_id)
    if not llm_configured(model_settings):
        return memory["summary"]
    pending = messages_to_summarize(conversation_id, keep_recent=6, batch_limit=20)
    if not pending:
        return memory["summary"]
    try:
        summary = await summarize_conversation(memory["summary"], pending, model_settings)
        save_conversation_summary(conversation_id, summary, pending[-1]["rowid"])
        return summary
    except Exception:
        # Summary is an optimization: never block a normal chat turn if summarization fails.
        logger.warning("Conversation summary update failed; using the previous summary", exc_info=True)
        return memory["summary"]




@app.post("/conversations", tags=["conversations"], status_code=201)
async def new_conversation(
    request: ConversationCreateRequest,
    session: dict = Depends(require_session),
) -> dict:
    return create_conversation(session["id"], request.title)


@app.get("/conversations", tags=["conversations"])
async def conversations(session: dict = Depends(require_session)) -> list[dict]:
    return list_conversations(session["id"])


@app.get("/conversations/{conversation_id}/messages", tags=["conversations"])
async def conversation_messages(
    conversation_id: str,
    session: dict = Depends(require_session),
) -> dict:
    conversation = get_conversation(conversation_id, session["id"])
    if conversation is None:
        audit_security_event(
            "conversation_access_denied",
            session_id=session["id"],
            resource_id=conversation_id,
            reason="not_found_or_not_owned",
        )
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"conversation": conversation, "messages": list_messages(conversation_id)}


@app.delete("/conversations/{conversation_id}", tags=["conversations"])
async def remove_conversation(
    conversation_id: str,
    session: dict = Depends(require_session),
) -> dict:
    if not delete_conversation(conversation_id, session["id"]):
        audit_security_event(
            "conversation_access_denied",
            session_id=session["id"],
            resource_id=conversation_id,
            reason="delete_not_found_or_not_owned",
        )
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": True}


@app.post("/conversations/{conversation_id}/messages/stream", tags=["conversations"])
async def conversation_chat_stream(
    conversation_id: str,
    request: ChatRequest,
    session: dict = Depends(require_session),
):
    conversation = get_conversation(conversation_id, session["id"])
    if conversation is None:
        audit_security_event(
            "conversation_access_denied",
            session_id=session["id"],
            resource_id=conversation_id,
            reason="message_not_found_or_not_owned",
        )
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    summary = await _prepare_conversation_summary(conversation_id, request.model_settings)
    history = recent_history(conversation_id, limit=6)
    messages, sources = await _retrieve_for_chat(request, session["id"], history=history, summary=summary)
    user_message = save_message(conversation_id, "user", request.query.strip())

    async def event_stream():
        def event(name: str, payload: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield event("sources", {
            "sources": sources,
            "retrieval": {"mode": "hybrid", "result_count": len(sources)},
            "user_message_id": user_message["id"],
        })
        if not sources:
            answer = "我暂时无法从知识库检索到相关资料，因此没有足够依据回答这个问题。请尝试换一种问法，或先上传相关文档。"
            assistant_message = save_message(conversation_id, "assistant", answer, [])
            yield event("token", {"content": answer})
            yield event("done", {"assistant_message_id": assistant_message["id"]})
            return

        answer_parts: list[str] = []
        try:
            async for token in stream_answer(messages, request.model_settings):
                answer_parts.append(token)
                yield event("token", {"content": token})
            answer = "".join(answer_parts)
            assistant_message = save_message(conversation_id, "assistant", answer, sources)
            yield event("done", {"assistant_message_id": assistant_message["id"]})
        except Exception:
            logger.exception("Conversation streaming response failed")
            yield event("error", {"message": "LLM 流式生成失败，请检查模型服务配置后重试。"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
