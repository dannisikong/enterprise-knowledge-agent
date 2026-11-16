# Enterprise Knowledge Agent

企业知识库助手 Demo：从企业文档上传、解析、分块，到关键词、向量和混合检索的端到端应用。

## Tech stack

- Frontend: React 18, TypeScript, Vite
- Backend: Python 3.12, FastAPI
- Parsing: pypdf, python-docx
- Chunking: overlapping character chunks with paragraph/sentence boundary preference
- Embeddings: OpenAI-compatible Embeddings API (optional)
- Local persistence: SQLite
- Hybrid ranking: Reciprocal Rank Fusion (RRF)

## Current capabilities

1. Upload PDF, DOCX, TXT and Markdown files (10 MB per file).
2. Extract readable text and persist original files locally.
3. Split extracted text into chunks (default 800 characters, 120-character overlap).
4. Optionally generate embeddings and persist vectors with each chunk.
5. Compare keyword retrieval, vector cosine similarity and hybrid retrieval.
6. Hybrid retrieval independently ranks keyword/vector results, then fuses the top 50 from each branch with RRF. It does not add incomparable raw scores.
7. Browse document metadata, chunk counts and embedding status in the UI.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Optional: configure an OpenAI-compatible embedding endpoint. Copy `.env.example` to `.env` and set the values, then export them in your shell or load them with your preferred environment manager:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://api.openai.com/v1"
export EMBEDDING_MODEL="text-embedding-3-small"
```

Without an API key, document ingestion and keyword retrieval still work. Newly uploaded chunks will have no vectors until embeddings are configured. Existing chunks are not automatically backfilled yet.

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Docker Compose

From the repository root, export the embedding variables if you want vector search, then run:

```bash
docker compose up --build
```

## API

- `GET /health` — service health
- `POST /documents` — upload and parse a document (multipart field: `file`)
- `GET /documents` — list documents and chunk/vector counts
- `GET /documents/{id}/text` — inspect extracted text
- `POST /search` — retrieve relevant chunks

Example hybrid request:

```json
{
  "query": "公司的报销政策是什么？",
  "limit": 5,
  "mode": "hybrid"
}
```

Supported modes:
- `keyword`: lightweight token-presence matching; not BM25.
- `vector`: embedding cosine similarity; requires query and document vectors.
- `hybrid`: RRF fusion of keyword and vector rankings; falls back to keyword results when vectors are unavailable.
- `auto`: same hybrid-first behavior and keyword fallback as `hybrid`.

## Retrieval experiment

- Sample document: `samples/employee-handbook.md`
- Step-by-step comparison of keyword and vector retrieval: [`docs/retrieval-experiment.md`](docs/retrieval-experiment.md)
- The UI compares all three strategies for the same query.
- RRF uses a rank constant of 60 and merges duplicate chunks by `chunk_id`.

## Current limitations

- This is a local-development demo. Do not upload confidential company documents.
- SQLite and local disk are used for simplicity; PostgreSQL/pgvector and object storage are planned.
- Existing chunks are not automatically re-embedded when the embedding model changes.
- Keyword matching is a simple token-presence baseline, not BM25 or a production-grade Chinese full-text search engine. It does not perform robust Chinese word segmentation.
- RRF improves rank fusion but cannot compensate for poor retrieval candidates; the top 50 from each branch are considered.
- Authentication, tenant isolation, malware scanning, background jobs, OCR, reranking, answer generation and evaluation are not implemented yet.

## Roadmap

1. ~~Document ingestion and parsing~~
2. ~~Chunking and embedding foundation~~
3. ~~Keyword/vector comparison and hybrid RRF retrieval~~
4. Reranking and retrieval evaluation
5. LangGraph answer workflow with source citations
6. Authentication, tenant isolation, observability and deployment
