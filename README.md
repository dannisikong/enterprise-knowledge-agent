# Enterprise Knowledge Agent

An enterprise knowledge-base assistant built with React, TypeScript, FastAPI, and an agentic RAG workflow.

## Project goals

- Upload and manage enterprise documents.
- Retrieve grounded answers from the knowledge base.
- Provide source citations for generated answers.
- Expose an observable, testable agent workflow.

## Development status

Project initialized. The first milestone is a runnable full-stack skeleton; retrieval and agent capabilities will be added incrementally.

## Planned stack

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Agent orchestration: LangGraph
- Storage and retrieval: PostgreSQL + pgvector
- Local development: Docker Compose

## Milestones

1. Project skeleton and health-check API
2. Document ingestion and parsing
3. Vector indexing and hybrid retrieval
4. RAG answer generation with citations
5. Agent workflow, evaluation, and observability
