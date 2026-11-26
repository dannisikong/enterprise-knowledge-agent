# Enterprise Knowledge Agent — Project Context

> Last verified: 2026-11-26 (Asia/Taipei)  
> Purpose: durable handover document for continuing work across ChatGPT conversations.  
> Rule: distinguish verified repository facts, user-reported deployment state, and pending verification. Never infer a deployment from a merge or CI pass.

## 1. Project goal

Build an enterprise knowledge-base assistant (RAG / AI Agent application) as a practical portfolio project for transitioning into AI Agent application development. The focus is a credible end-to-end demo: ingestion, retrieval, grounded answers, citations, evaluation, security, and deployability.

## 2. Repository and environments

- GitHub: https://github.com/dannisikong/enterprise-knowledge-agent
- Backend (Render): https://enterprise-knowledge-agent-main.onrender.com
- Frontend (Render): https://enterprise-knowledge-agent-web.onrender.com
- Latest main commit verified 2026-11-26: `8807b5105cce05d85eef0e7944c422c7f99d5b98`
- Latest commit message: merge PR #6, manual retrieval evaluation workflow.
- Render deployment state: do not assume latest main is deployed unless user confirms or deployment is independently checked.

## 3. Technology and current configuration

- Frontend: React 18, TypeScript, Vite.
- Backend: Python 3.12, FastAPI.
- Document parsing: PDF / DOCX / TXT / Markdown.
- Persistence: SQLite and local filesystem.
- Retrieval: lightweight keyword matching, vector similarity, hybrid RRF; optional reranking.
- Answer generation: OpenAI-compatible Chat Completions API; SSE streaming.
- User-confirmed embedding baseline: DashScope `text-embedding-v1`. User explicitly chose to keep it for the current retrieval evaluation rather than replace it.
- User-confirmed chat default: DashScope compatible endpoint `https://dashscope.aliyuncs.com/compatible-mode/v1`, model `qwen-max`.
- Important: README examples may show other defaults (for example text-embedding-v4 or OpenAI defaults); do not treat examples as proof of the live Render environment. Confirm actual env/config when needed.
- Render Free backend data directory previously configured as `/tmp/knowledge-data`; ephemeral storage means files/SQLite may disappear after restart/redeploy. Keep source PDFs locally and use a dedicated evaluation session.

## 4. Existing capabilities

- Frontend/backend separated.
- Upload and parse PDF, DOCX, TXT and Markdown.
- Chunking (approx. 800 characters, 120 overlap, with boundary preference).
- Embedding generation and vector persistence.
- Keyword / Vector / Hybrid retrieval and optional reranking.
- RAG answers with source metadata and SSE streaming.
- Model configuration UI.
- Anonymous session isolation and security controls.

## 5. Security and engineering milestones

- Embedding API response and vector-dimension validation, plus reindex endpoint: merged and deployed per user confirmation.
- Security PR #3 commit: `f0956794e5465d1061e760375d8690bb4b0edf28`. Includes session creation rate limiting, hashed session tokens, sliding expiry, session isolation, audit/security checks, upload constraints. User confirmed deployment. Reported backend tests: 55 passed; frontend build succeeded.
- DashScope / Qwen default model changes include commits `eb074534`, `23130cb7`, `5bc4fb97`. CI passed; latest live deployment confirmation was not recorded.
- Production smoke PR #4 commit: `5d6c2ef2c081cdf18056f06b2b8f9839defe28fb`. Workflow/script are intended to avoid modifying user data, calling chat models, or reindexing vectors. User ran it, but a complete result report is not recorded.
- Retrieval evaluation PR #5 commit: `e76becfd823a2d2a7e88f01f859e6a9d28613019`. Adds a 35-question dataset and evaluation script, supports keyword/vector/hybrid and optional reranker. User confirmed deployed.
- Retrieval evaluation workflow PR #6 commit: `cd2c0a3cf5722d377dbf75bdabfd0a66d730bcad`; merged to main at `8807b5105cce05d85eef0e7944c422c7f99d5b98`. User successfully ran Actions; JSON artifacts retained for 14 days.

## 6. Retrieval baseline and interpretation

Baseline reported by user on 2026-11-25:
- Dataset: 35 questions.
- Corpus: one `employee-handbook.md`, two chunks.
- Embedding: `text-embedding-v1`.
- Keyword: 2/35 hits; Recall@1/3/5 and MRR each 5.71%.
- Vector: 35/35; metrics 100%.
- Hybrid: 35/35; metrics 100%; effective mode reported as hybrid, no fallback.
- Interpretation limits:
  - The sample is too small to claim production retrieval accuracy.
  - Vector and Hybrid tying at 100% does not establish Hybrid superiority.
  - gold rank 1 means the target evidence ranked first, not that the generated answer is correct.
  - Reranker has not yet been evaluated.
  - Keyword implementation is lightweight token/sub-string matching, not full BM25 or robust Chinese segmentation.

## 7. Current workstream — B2 compact multi-document benchmark

Goal: validate retrieval across multiple documents without changing embedding model or prematurely refactoring retrieval/chunking.

User approved the compact scope on 2026-11-26:
- 6 synthetic Markdown policy documents:
  - HR: employee-handbook.md, attendance-policy.md
  - IT: account-access-policy.md, incident-response-policy.md
  - Finance: travel-expense-policy.md
  - Security: data-security-policy.md
- 40 questions:
  - single_document: 10
  - semantic_paraphrase: 8
  - distractor: 8
  - multi_document: 5
  - no_answer: 4
  - complex_scenario: 5
- Keep embedding baseline `text-embedding-v1`.
- Required metrics: Recall@1/3/5, MRR, evidence recall@K, complete required-evidence/source coverage for multi-document questions, no-answer retrieval false-positive rate, and breakdown by question type.
- Manual corrections: HR-005 category must be `it`; CX-004 wording must be exactly “P3 故障最长多久内响应？”
- Dataset must be validated for unique IDs, source paths, exact evidence text, answerability labels, multi-document source coverage, and expected distribution.
- Status: approved specification only. The compact ZIP has NOT yet been successfully generated/validated/delivered. The earlier 15-document/80-question draft is not the approved final compact package.
- No GitHub code or Render changes are authorized by the B2 dataset approval.

## 8. Next actions

1. Generate and validate `enterprise-rag-evaluation-b2-compact.zip` (6 docs / 40 questions). Do not claim completion until file exists and validator passes.
2. Inspect current evaluation script/API contract and design a B2-compatible evaluation path; existing evaluator only models one gold phrase and one sample handbook, so it cannot fully score multiple required evidence items or no-answer false positives as-is.
3. Present a read-only implementation plan before changing application code. Wait for explicit approval before any code writes.
4. Run the benchmark in a dedicated isolated session; upload all six docs once, then compare modes against the same corpus/session where supported.
5. Report metrics with limitations; do not change embedding model during this experiment.

## 9. Collaboration and change-control rules

- Start new conversations by reading this file and the latest changelog entry.
- First inspect GitHub read-only; report current main SHA and relevant files.
- Before modifying code, provide a concrete plan and wait for explicit user approval.
- Keep docs-only project-record updates separate from application-code changes.
- Direct commits to main, PR merge, Render environment changes, and production deployment are separate high-impact steps; obtain explicit approval for each unless the user has explicitly granted a narrow recurring docs-only authorization.
- Never claim a commit is deployed merely because it is merged or CI passed.
- Batch related work where practical; avoid unnecessary one-step-at-a-time confirmations.
- Clearly label status as: verified in repository / user-confirmed live / pending verification / proposed.
- Never store API keys, tokens, passwords, or confidential source documents in project docs.

## 10. How to resume in a new ChatGPT conversation

Paste this instruction:

“请先阅读仓库 docs/PROJECT_CONTEXT.md 和 docs/CHANGELOG.md，以它们为项目交接依据。先核对 GitHub main 最新 Commit 和当前任务状态；区分仓库事实与线上部署状态。遵守文档中的变更审批规则，从 Next actions 第一项继续，不要从零规划。”
