# Enterprise Knowledge Agent

企业知识库助手 Demo：从企业文档上传、解析、分块，到混合检索、Reranker 和带来源引用的 RAG 问答。

## Tech stack

- Frontend: React 18, TypeScript, Vite
- Backend: Python 3.12, FastAPI
- Parsing: pypdf, python-docx
- Chunking: overlapping character chunks with paragraph/sentence boundary preference
- Embeddings: OpenAI-compatible Embeddings API (optional)
- Local persistence: SQLite
- Hybrid ranking: Reciprocal Rank Fusion (RRF)
- Optional reranking: Cohere v2-compatible rerank API
- Answer generation: OpenAI-compatible Chat Completions API
- Streaming: Server-Sent Events (SSE)

## Current capabilities

1. Upload PDF, DOCX, TXT and Markdown files (10 MB per file).
2. Extract readable text and persist original files locally.
3. Split extracted text into chunks (default 800 characters, 120-character overlap).
4. Optionally generate embeddings and persist vectors with each chunk.
5. Compare keyword retrieval, vector cosine similarity and hybrid retrieval.
6. Fuse independent keyword/vector rankings with RRF; optionally rerank candidates.
7. Generate grounded answers from retrieved chunks and attach numbered source citations.
8. Stream answer tokens and source metadata over SSE.\n9. Give each visitor an isolated temporary knowledge base using an anonymous session token.\n10. Let visitors supply their own chat model API key, Base URL and model name for the current page session.

## Run in GitHub Codespaces

This repository includes a Dev Container configuration for an online development environment.

1. Open the repository on GitHub.
2. Select **Code → Codespaces → Create codespace on main**.
3. Wait for the Dev Container to build and install the Python and frontend dependencies.
4. Open two terminal sessions and start the backend and frontend separately.

Backend terminal:

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend terminal:

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

Codespaces forwards ports 5173 (frontend) and 8000 (backend). Open the forwarded frontend URL from the **Ports** tab. The Vite development proxy forwards `/api/*` requests to the backend; for example, the health endpoint is available at `/api/health`.

Run backend tests from the repository root:

```bash
cd backend
python -m pytest -q
```

Check the frontend TypeScript build:

```bash
cd frontend
npm run build
```

Model API credentials are optional for starting the services and running unit tests. Add the required variables as Codespaces Secrets or to a local, untracked environment file when you want to test real embedding, reranking or chat requests. Never commit API keys. Uploaded documents and the SQLite database are stored under `backend/data/`, which is excluded from Git.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` and export the variables in your shell or load them with your preferred environment manager:

```bash
export OPENAI_API_KEY="your-embedding-api-key"
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export EMBEDDING_MODEL="text-embedding-v4"
export RERANK_API_KEY="your-rerank-api-key"
export RERANK_BASE_URL="https://api.cohere.com/v2"
export RERANK_MODEL="rerank-v3.5"
export LLM_API_KEY="your-chat-api-key"
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="gpt-4o-mini"
```

The embedding, reranking and chat services are independently configurable. You may use compatible providers and their corresponding base URLs/models. Without `LLM_API_KEY`, retrieval still works but chat endpoints return a configuration error. Never commit real API keys.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

### Docker Compose

From the repository root, export the environment variables you need and run:

```bash
docker compose up --build
```

## API

- `GET /health` — service health\n- `POST /session` — create an anonymous session and receive its token\n- `POST /model/test` — test a visitor-supplied chat model configuration
- `POST /documents` — upload and parse a document (multipart field: `file`)
- `POST /documents/reindex` — regenerate embeddings for all documents in the current anonymous session
- `GET /documents` — list documents and chunk/vector counts
- `GET /documents/{id}/text` — inspect extracted text
- `POST /search` — retrieve relevant chunks
- `POST /chat` — generate an answer with source metadata
- `POST /chat/stream` — stream source metadata and answer tokens using SSE

Chat request:

```json
{
  "query": "员工年假有多少天？",
  "limit": 5,
  "rerank": false
}
```

Non-streaming response contains `answer`, `sources` and retrieval metadata. The model is instructed to answer only from retrieved context, say when evidence is insufficient, and cite source IDs such as `[1]`. The UI displays the matching filename and chunk for each source.

SSE events:
- `sources`: source list and retrieval metadata, sent before answer tokens
- `token`: one generated text fragment in `content`
- `done`: generation completed
- `error`: generation failed

The frontend consumes the SSE stream using Fetch and a readable stream, so the POST request body and browser streaming are both supported. All document, search, chat and model-test endpoints require the `X-Session-Token` header returned by `POST /session`.


## Public demo deployment (Render Free)

The demo can be deployed as two Render services:

1. Create a **Static Site** from the repository and set its root directory to `frontend`.
   - Build command: `npm install && npm run build`
   - Publish directory: `dist`
   - Set `VITE_API_BASE_URL` to the public HTTPS URL of the backend Web Service, without a trailing slash.
2. Create a **Web Service** from the repository and set its root directory to `backend`.
   - Runtime: Docker
   - Set `CORS_ORIGINS` to the exact public frontend URL.
   - Set `DATA_DIR` to a writable directory if needed (for example `/tmp/knowledge-data`).
   - Render supplies `PORT`; the Docker command uses it automatically.
   - Health check path: `/health`.

The free Web Service is suitable only for a trial/demo. It may spin down after inactivity and take time to wake. Its local filesystem is ephemeral: SQLite data and uploaded files can disappear after restart, redeploy or instance replacement. Free instances do not support Persistent Disks. Do not upload confidential or irreplaceable documents, and do not promise visitors persistent storage.

### Anonymous sessions and model credentials

- A browser receives a random anonymous session token. The server stores only its SHA-256 hash; the browser stores the token in `sessionStorage`.
- Each session's uploaded documents, extracted text, chunks, retrieval results and citations are isolated. Sessions expire after 24 hours of inactivity; expired records and uploaded files are cleaned in batches during startup and API requests.
- Visitors configure the chat model in **模型设置**. The API key is held in page memory and sent only with the model test/chat request. It is not stored in SQLite, browser persistent storage or frontend build output. Refreshing the page clears the key.
- Custom model Base URLs must use HTTPS on port 443 and resolve to public IP addresses. Redirects are disabled. This is a demo-level SSRF guard, not a substitute for a production egress allowlist or network firewall.
- Embedding and reranking credentials remain server-side environment variables (`OPENAI_API_KEY`, `RERANK_API_KEY`); visitors cannot change them.
- The in-memory rate limiter resets on process restart and is not production-grade abuse protection.

Never expose a backend provider key in frontend environment variables or commit real credentials.
\n## Retrieval experiment and evaluation

- Sample document: `samples/employee-handbook.md`
- Comparison guide: `docs/retrieval-experiment.md`
- Evaluation dataset: `backend/evaluation/retrieval_dataset.json`
- Evaluation script: `backend/scripts/evaluate_retrieval.py`
- Metrics: single-gold-passage Recall@K and MRR

Run the API and upload the sample handbook. **Compatibility note:** the legacy `scripts/evaluate_retrieval.py` utility currently does not create or send an anonymous session token, so it cannot call the authenticated `/search` endpoint until that script is updated. It is intentionally not changed in this P6 scope.

## Current limitations

- This is a local-development demo. Do not upload confidential company documents.
- SQLite and local disk are used for simplicity; PostgreSQL/pgvector and object storage are future improvements.
- Existing chunks must be re-embedded through `POST /documents/reindex` after configuring or changing the embedding model. The endpoint processes documents in the current anonymous session only; keep the same browser session while reindexing.
- Keyword matching is a lightweight token-presence baseline, not BM25 or production-grade Chinese full-text search.
- RRF cannot compensate for missing retrieval candidates; the evaluation dataset is small and not a production benchmark.
- The RAG prompt asks the model to cite retrieved source IDs, but LLM output is not yet independently verified against each claim. Treat citations as model-generated references, not a formal guarantee.
- This demo uses anonymous session isolation, not verified user authentication or enterprise authorization.\n- The free Render filesystem is ephemeral; durable storage, distributed rate limiting, stronger outbound network controls, OCR, background jobs and production observability are not implemented.

## Roadmap

1. ~~Document ingestion and parsing~~
2. ~~Chunking, embeddings and retrieval~~
3. ~~Hybrid RRF and optional reranking~~
4. ~~RAG answer generation, source metadata and SSE streaming~~
5. Retrieval quality improvements, citation validation and evaluation of answer faithfulness
6. Authentication, tenant isolation, observability and deployment
