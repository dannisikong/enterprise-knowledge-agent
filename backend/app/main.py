from contextlib import asynccontextmanager
import json
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.document_service import (
    get_document_text,
    initialize_storage,
    list_documents,
    search_chunks,
    upload_document,
)
from app.services.llm_service import (
    build_grounded_messages,
    generate_answer,
    llm_configured,
    stream_answer,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_storage()
    yield


app = FastAPI(
    title="Enterprise Knowledge Agent API",
    version="0.5.0",
    description="API for document ingestion, retrieval and grounded knowledge answers.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "enterprise-knowledge-agent"}


@app.post("/documents", tags=["documents"])
async def create_document(file: UploadFile = File(...)) -> dict:
    try:
        return await upload_document(file)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=422, detail="Unable to parse this document.") from error
    finally:
        await file.close()


@app.get("/documents", tags=["documents"])
async def documents() -> list[dict]:
    return list_documents()


@app.get("/documents/{document_id}/text", tags=["documents"])
async def document_text(document_id: str) -> dict:
    document = get_document_text(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@app.post("/search", tags=["retrieval"])
async def search(request: SearchRequest) -> dict:
    try:
        return await search_chunks(request.query, request.limit, request.mode, request.rerank)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


async def _retrieve_for_chat(request: ChatRequest) -> tuple[list[dict], list[dict]]:
    if not llm_configured():
        raise HTTPException(status_code=503, detail="LLM_API_KEY is not configured.")
    try:
        retrieval = await search_chunks(request.query, request.limit, "hybrid", request.rerank)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    messages, sources = build_grounded_messages(request.query, retrieval["results"])
    return messages, sources


@app.post("/chat", tags=["chat"])
async def chat(request: ChatRequest) -> dict:
    messages, sources = await _retrieve_for_chat(request)
    if not sources:
        return {
            "answer": "我暂时无法从知识库检索到相关资料，因此没有足够依据回答这个问题。请尝试换一种问法，或先上传相关文档。",
            "sources": [],
            "retrieval": {"mode": "hybrid", "result_count": 0},
        }
    try:
        answer = await generate_answer(messages)
    except Exception as error:
        raise HTTPException(status_code=502, detail="LLM provider request failed.") from error
    return {
        "answer": answer,
        "sources": sources,
        "retrieval": {"mode": "hybrid", "result_count": len(sources)},
    }


@app.post("/chat/stream", tags=["chat"])
async def chat_stream(request: ChatRequest):
    messages, sources = await _retrieve_for_chat(request)

    async def event_stream():
        def event(name: str, payload: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield event("sources", {"sources": sources, "retrieval": {"mode": "hybrid", "result_count": len(sources)}})
        if not sources:
            yield event("token", {"content": "我暂时无法从知识库检索到相关资料，因此没有足够依据回答这个问题。请尝试换一种问法，或先上传相关文档。"})
            yield event("done", {})
            return
        try:
            async for token in stream_answer(messages):
                yield event("token", {"content": token})
            yield event("done", {})
        except Exception:
            yield event("error", {"message": "LLM 流式生成失败，请检查模型服务配置后重试。"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
