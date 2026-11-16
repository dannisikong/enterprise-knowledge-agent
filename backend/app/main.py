from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.services.document_service import get_document_text, initialize_storage, list_documents, upload_document


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_storage()
    yield


app = FastAPI(title="Enterprise Knowledge Agent API", version="0.2.0", description="API for an enterprise knowledge-base assistant.", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


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
