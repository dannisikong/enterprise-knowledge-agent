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
8. Stream answer tokens and source metadata over SSE.

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
export OPENAI_BASE_URL="https://api.openai.com/v1"
export EMBEDDING_MODEL="text-embedding-3-small"
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

- `GET /health` — service health
- `POST /documents` — upload and parse a document (multipart field: `file`)
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

The frontend consumes the SSE stream using Fetch and a readable stream, so the POST request body and browser streaming are both supported.

## Retrieval experiment and evaluation

- Sample document: `samples/employee-handbook.md`
- Comparison guide: `docs/retrieval-experiment.md`
- Evaluation dataset: `backend/evaluation/retrieval_dataset.json`
- Evaluation script: `backend/scripts/evaluate_retrieval.py`
- Metrics: single-gold-passage Recall@K and MRR

Run the API, upload the sample handbook, then run `python scripts/evaluate_retrieval.py` from `backend`.

## Current limitations

- This is a local-development demo. Do not upload confidential company documents.
- SQLite and local disk are used for simplicity; PostgreSQL/pgvector and object storage are future improvements.
- Existing chunks are not automatically re-embedded when the embedding model changes.
- Keyword matching is a lightweight token-presence baseline, not BM25 or production-grade Chinese full-text search.
- RRF cannot compensate for missing retrieval candidates; the evaluation dataset is small and not a production benchmark.
- The RAG prompt asks the model to cite retrieved source IDs, but LLM output is not yet independently verified against each claim. Treat citations as model-generated references, not a formal guarantee.
- Authentication, tenant isolation, permissions, OCR, background jobs, observability and production deployment are not implemented.

## Roadmap

1. ~~Document ingestion and parsing~~
2. ~~Chunking, embeddings and retrieval~~
3. ~~Hybrid RRF and optional reranking~~
4. ~~RAG answer generation, source metadata and SSE streaming~~
5. Retrieval quality improvements, citation validation and evaluation of answer faithfulness
6. Authentication, tenant isolation, observability and deployment
