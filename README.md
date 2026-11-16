# Enterprise Knowledge Agent

企业知识库助手 Demo，目标是构建一个具备文档 ingestion、可追溯 RAG 检索和 Agent 工作流的端到端应用。

## Tech stack

- Frontend: React 18, TypeScript, Vite
- Backend: Python 3.12, FastAPI
- Document parsing: pypdf, python-docx, native text/Markdown
- Metadata: SQLite for local development
- Next: PostgreSQL + pgvector, hybrid retrieval, LangGraph

## Current milestone: document ingestion

- Upload PDF, DOCX, TXT and Markdown files (10 MB limit)
- Extract text from uploaded documents
- Store original files locally and metadata/extracted text in SQLite
- List uploaded documents and show extraction status

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Docker Compose

From the repository root:

```bash
docker compose up --build
```

## API

- `GET /health` — service health
- `POST /documents` — upload and parse a document (multipart field: `file`)
- `GET /documents` — list ingested documents
- `GET /documents/{id}/text` — inspect extracted text

## Notes

This is a local-development demo, not production document storage. Files and SQLite data are stored under `backend/data`; do not upload confidential company documents. Authentication, malware scanning, durable object storage, background jobs, and tenant isolation are not implemented yet.

## Roadmap

1. Document ingestion and parsing
2. Chunking and metadata enrichment
3. Embeddings and vector indexing
4. Hybrid retrieval and reranking
5. LangGraph answer workflow with citations
6. Evaluation, observability, and deployment
