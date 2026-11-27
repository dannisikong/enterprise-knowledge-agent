# Enterprise Knowledge Agent — Project Context

> Last verified: 2026-11-26 (Asia/Taipei), 19:21  
> Purpose: durable handover document for continuing work across ChatGPT conversations.  
> Rule: distinguish verified repository facts, user-reported deployment state, and pending verification. Never infer a deployment from a merge or CI pass.

## 1. Project goal

Build an enterprise knowledge-base assistant (RAG / AI Agent application) as a practical portfolio project for transitioning into AI Agent application development. The focus is a credible end-to-end demo: ingestion, retrieval, grounded answers, citations, evaluation, security, and deployability.

## 2. Repository and environments

- GitHub: https://github.com/dannisikong/enterprise-knowledge-agent
- Backend (Render): https://enterprise-knowledge-agent-main.onrender.com
- Frontend (Render): https://enterprise-knowledge-agent-web.onrender.com
- Latest application-code commit verified 2026-11-26, before this docs-only archive refresh: `a431fb4727818f9fab5c4bb3c1e85e7c466964c7`
- Application-code commit message: Adapt retrieval evaluator for multi-document B2 benchmark.
- The archive refresh added only `docs/PROJECT_CONTEXT.md` and `docs/CHANGELOG.md` commits after that application-code commit. Re-check the live `main` HEAD before continuing work.
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

- B2 compact benchmark corpus and evaluator changes were committed directly to main on 2026-11-26. The repository now contains six synthetic policy documents, a 40-question dataset, manifest, README, and structural validator under `backend/evaluation/b2/`; the retrieval evaluation service, CLI, and tests were also updated. See current workstream below.

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

Goal: validate retrieval across multiple documents without changing the embedding model or prematurely refactoring retrieval/chunking.

### Repository-verified implementation (2026-11-26)

- Latest application-code commit before the docs-only archive updates: `a431fb4727818f9fab5c4bb3c1e85e7c466964c7` (commit message: “Adapt retrieval evaluator for multi-document B2 benchmark”). The subsequent archive commits changed only the two project-record files.
- The 6-document corpus and 40-question dataset now exist in `backend/evaluation/b2/`:
  - HR: `employee-handbook.md`, `attendance-policy.md`
  - IT: `account-access-policy.md`, `incident-response-policy.md`
  - Finance: `travel-expense-policy.md`
  - Security: `data-security-policy.md`
- Dataset distribution verified from the repository JSON: single_document 10; semantic_paraphrase 8; distractor 8; multi_document 5; no_answer 4; complex_scenario 5.
- Dataset fields include `answerable`, `required_evidence`, and `expected_source_documents`. The repository also contains `manifest.json`, `README.md`, and `validate_dataset.py`.
- A read-only cross-check of the current dataset against all six Markdown files found every declared evidence phrase in its named document and no mismatch between evidence-document references and expected source-document lists. This was a content inspection, not execution of the validator script.
- Important content discrepancy to review: the current repository's six documents and almost all questions are English; only CX-004 is Chinese. The earlier planning conversation was conducted in Chinese. Confirm whether this English corpus is intentional or whether a Chinese-language benchmark is still expected.
- The earlier note about an `HR-005` category correction cannot be matched to the current dataset: current IDs use SD/SP/DI/MD/NA/CX prefixes and no `HR-005` exists. CX-004 currently matches the required exact wording: “P3 故障最长多久内响应？”
- The downloadable ZIP discussed in chat was not verified as generated. The repository corpus is now present and can be used directly; do not claim a ZIP deliverable exists.
- PR inventory: PRs #1–#6 are closed; no open PR was present in the inspected repository PR list. The B2 corpus/evaluator changes were committed directly to `main`, not merged through a new PR.

### Evaluator changes now on main

- `backend/app/services/retrieval_evaluation.py` now accepts multiple `required_evidence` items, expected source documents, and answerability.
- Answerable-query metrics include Recall@1/3/5, MRR, Evidence Recall@K, evidence completeness@K, and source coverage@K.
- For no-answer questions, the current metric is named `no_answer_nonempty@K`: it measures whether retrieval returned any candidates. It is **not** a judged false-positive rate and does not measure whether the answer generator abstains. This distinction must remain explicit in reports.
- `backend/scripts/evaluate_retrieval.py` now defaults to the B2 dataset, validates required fields, creates a dedicated session, uploads the six documents, and evaluates selected retrieval modes. Each script invocation creates its own session.
- Tests were added for multi-evidence, source coverage, no-answer candidate presence, and mixed aggregation.
- Latest CI run for HEAD `a431fb4`: run `45783910071`, completed successfully on 2026-11-26. Both “Backend tests” and “Frontend typecheck and build” jobs succeeded. An earlier intermediate CI run failed on evidence-recall rounding expectations; a follow-up correction commit passed, and the latest HEAD is green.
- No B2 production retrieval evaluation run is visible yet. The most recent `Retrieval Evaluation` workflow dispatch in the inspected Actions list is from 2026-11-25 on the pre-B2 commit `8807b5105cce05d85eef0e7944c422c7f99d5b98`.
- The current manual retrieval workflow still targets the Render production API and invokes each mode separately. Its comment still says the dataset has 35 questions, and `docs/retrieval-evaluation.md` still describes the old 35-question single-handbook experiment; both are stale relative to the B2 default.
- Latest main changes are repository-verified only. No user-confirmed Render deployment of HEAD `a431fb4` is recorded; do not assume it is live.

### Historical approval and experiment assumptions

- User approved the compact scope: six synthetic Markdown policy documents and 40 questions with the distribution above.
- Keep embedding baseline `text-embedding-v1`; do not replace it during this experiment.
- The earlier 35-question single-document baseline remains historical and is not a B2 result.
- Retrieval rank/evidence matching does not establish answer correctness, citation faithfulness, or safe refusal behavior.
- No application code, workflow, or Render changes are authorized by the recurring documentation task itself.

## 8. Next actions

1. Review the language/content discrepancy in the committed B2 corpus and decide whether the current English benchmark is acceptable or a Chinese benchmark is required. Also reconcile the obsolete `HR-005` note against the current SD/SP/DI/MD/NA/CX IDs.
2. Run `python backend/evaluation/b2/validate_dataset.py` in a suitable local environment and retain the output. The validator file exists, but the inspected latest CI jobs did not show that this script was executed.
3. Review the no-answer metric semantics. If the target remains “retrieval false-positive rate,” define relevance judgments for returned candidates; separately measure answer abstention. Do not relabel `no_answer_nonempty@K` as a false-positive rate.
4. Update the stale retrieval-evaluation guide and workflow comment, then check the B2 manual workflow's production API behavior. These are outside the recurring docs-only write scope and require normal user approval before changing files.
5. After the corpus and metrics are accepted, obtain explicit user approval before running the production B2 evaluation. Confirm that the intended Render version is deployed first; the workflow creates isolated sessions and uploads the six synthetic documents.
6. Compare Keyword, Vector, and Hybrid on the same benchmark definition; report category breakdowns, evidence completeness, source coverage, and no-answer limitations. Keep `text-embedding-v1` unchanged.
7. Then evaluate answer faithfulness, citation validity, refusal behavior, prompt injection, and cross-session isolation; prepare architecture diagrams, evaluation report, README/demo walkthrough, résumé bullets, and interview explanation.

## 9. Collaboration and change-control rules

- Start new conversations by reading this file and the latest changelog entry.
- First inspect GitHub read-only; report current main SHA and relevant files.
- Before modifying code, provide a concrete plan and wait for explicit user approval.
- Keep docs-only project-record updates separate from application-code changes.
- Direct commits to main, PR merge, Render environment changes, and production deployment are separate high-impact steps; obtain explicit approval for each unless the user has explicitly granted a narrow recurring docs-only authorization.
- Never claim a commit is deployed merely because it is merged or CI passed.
- Batch related work where practical; avoid unnecessary one-step-at-a-time confirmations.
- Clearly label status as: verified in repository / user-confirmed live / pending verification / proposed.
- Recurring project-archive maintenance is narrowly authorized to update only `docs/PROJECT_CONTEXT.md` and `docs/CHANGELOG.md`, committing docs-only changes to `main`; it must not change application code, workflows, configuration, branch protection, secrets, or Render.
- Never store API keys, tokens, passwords, or confidential source documents in project docs.

## 8. B2 retrieval evaluation — user-provided reports

### Evaluation evidence and scope

- User supplied Keyword, Vector, and Hybrid JSON reports for the same B2 dataset: `enterprise_rag_b2_compact`, version `1.0.0`, 40 questions, six synthetic policy documents, and the category distribution 10/8/8/5/4/5.
- All three reports show all six documents as `embedding_status: indexed` with two chunks each. Each report identifies its own effective mode (keyword, vector, or hybrid); Hybrid did not fall back to Keyword.
- All three reports state `reranker_statuses: ["not_requested"]`; this comparison is without reranking.
- These are user-provided workflow report contents, not independently re-fetched artifacts. Treat the reported metrics as user-supplied experimental evidence.
- The reports use the same dataset definition and embedding baseline, `text-embedding-v1`; no embedding-model change was made.

### Aggregate comparison

| Metric | Keyword | Vector | Hybrid |
|---|---:|---:|---:|
| Recall@1 | 0.8889 | 0.9167 | **0.9444** |
| Recall@3 | **1.0000** | 0.9722 | 0.9722 |
| Recall@5 | 1.0000 | 1.0000 | 1.0000 |
| Evidence Recall@1 | 0.8287 | 0.8657 | **0.8843** |
| Evidence Recall@3 | **0.9491** | 0.9444 | 0.9352 |
| Evidence Recall@5 | 0.9583 | 1.0000 | **1.0000** |
| Evidence Complete@1 | 0.7778 | 0.8056 | **0.8333** |
| Evidence Complete@3 | 0.8889 | **0.9167** | 0.8889 |
| Evidence Complete@5 | 0.9167 | **1.0000** | **1.0000** |
| Source Coverage@1 | 0.8611 | 0.9444 | 0.9167 |
| Source Coverage@3 | **1.0000** | **1.0000** | 0.9722 |
| Source Coverage@5 | 1.0000 | 1.0000 | 1.0000 |
| MRR | 0.9306 | 0.9514 | **0.9653** |

### Interpretation and decision

- Hybrid leads on top-1 retrieval: Recall@1, Evidence Recall@1, Evidence Complete@1, and MRR. It is the strongest current candidate for the default retrieval mode on this benchmark, subject to answer-quality testing; this is a recommendation, not a code/config change.
- Vector leads Evidence Complete@3 (0.9167 versus 0.8889 for Keyword and Hybrid) and ties Hybrid at 100% Evidence Complete@5.
- Keyword leads Recall@3 and Evidence Recall@3, so Hybrid is not uniformly best at every cutoff.
- At @5, Vector and Hybrid achieve full evidence recall/completeness; Keyword Evidence Complete@5 is 0.9167.
- Category-level patterns: all three modes are perfect on the 10 single-document questions at the reported cutoffs. Vector is strongest on the five multi-document questions (Evidence Recall@3/@5 and completeness@3/@5 all 1.0); Hybrid reaches full evidence completeness at @5 but its @3 completeness is 0.8. Complex scenarios remain the main weakness at small cutoffs: Hybrid and Vector reach Evidence Complete@1 of 0.2 and @3 of 0.6, while all modes reach full completeness by @5. Semantic paraphrase contains ranking misses, especially SP-002; the reports show that its gold evidence can rank as low as fourth.
- Cases worth retaining as regression examples include SP-002, MD-001, CX-001, CX-002, CX-003, and CX-005. Inspect per-question evidence before changing retrieval logic.
- The no-answer metric `no_answer_nonempty@K=1.0` only means retrieval returned candidates for all four no-answer questions. It does not measure false-positive relevance, answer hallucination, or whether the generator abstains. A separate judged refusal/answer-quality evaluation is required.
- The current benchmark is small and synthetic (six documents, 40 questions). Do not generalize these scores to production accuracy.

### Current stage status

- B2 Keyword / Vector / Hybrid retrieval comparison: complete based on the three user-provided reports.
- Reranker: not evaluated; all three reports say `not_requested`. Do not enable it by assumption. A focused reranker A/B test can be considered later if top-1 evidence ranking remains a bottleneck.
- No retrieval algorithm, embedding model, workflow, Render configuration, or deployment was changed as part of this evaluation.
- Recommended next workstream: move to the product-level multi-turn chat experience and conversation management, while preserving the current retrieval modes as evaluation baselines.

## 9. Next workstream — multi-turn chat and conversational UI

### P1 product scope

1. Chat interface: conversation list, new conversation, message history, distinct user/assistant message bubbles, persistent bottom composer, Markdown rendering, streaming output, stop generation, and per-answer source citations.
2. Backend conversation model: distinct Conversation ID (not the existing knowledge-base Session ID), bind each conversation to its authorized Session, persist messages, and retrieve bounded history server-side.
3. Multi-turn grounded context: resolve follow-up references using conversation context, but retrieve evidence for the current turn; prior assistant answers must not become authoritative facts. Keep each turn's citations attached to that answer.
4. Isolation and lifecycle: a new conversation must not inherit another conversation's history; conversations must not cross Session boundaries.

### Acceptance scenarios

- Ask annual-leave allowance, then follow up with “What about during probation?”; the follow-up should resolve correctly and cite current retrieved evidence.
- Ask about remote-work approval, then ask a short contextual follow-up such as “What about the start time?”.
- Switch to an unrelated travel-expense question and ensure stale context does not distort retrieval.
- Start a new conversation and verify it does not inherit the prior conversation's history.
- Stop a streaming response and verify the UI returns to an input-ready state.
- Verify citations/sources remain associated with the correct assistant message across multiple turns.

### Change-control

- The user confirmed the documentation/evaluation wrap-up and the proposed next-stage direction. This does not yet authorize application-code changes.
- Before changing application code, inspect the current frontend/backend implementation and present a consolidated implementation plan with API/data model, persistence implications, tests, and migration considerations. Wait for explicit approval before coding.
- Do not treat the existing knowledge-base Session as a Conversation ID. Do not assume Render's ephemeral filesystem is suitable for durable conversation history.

## 10. Historical follow-up notes and unresolved checks

- Earlier repository review flagged the B2 corpus as English-dominant (only CX-004 is Chinese) and found no `HR-005` in the current SD/SP/DI/MD/NA/CX dataset IDs. These are benchmark-design/documentation questions, not blockers to interpreting the three supplied runs; revisit only if a Chinese-language benchmark is required.
- The validator script exists, but unless a run result is captured, do not claim it was executed.
- The old `docs/retrieval-evaluation.md` and workflow comment may still describe the previous 35-question benchmark; they were not modified in this docs-only update.

## 11. How to resume in a new ChatGPT conversation

Paste this instruction:

“请先阅读仓库 docs/PROJECT_CONTEXT.md 和 docs/CHANGELOG.md，以它们为项目交接依据。先核对 GitHub main 最新 Commit 和当前任务状态；区分仓库事实与线上部署状态。B2 三种检索模式的用户报告已完成比较，下一步从多轮对话 UI 与后端 Conversation 设计开始。先只读检查现有实现并给出完整实施方案，等待我批准后再修改代码。”
