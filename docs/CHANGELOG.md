# Project Changelog

All entries are concise handover snapshots. This is not a raw chat transcript.

## 2026-11-26

- Established durable project handover documentation under `docs/`.
- Verified main HEAD: `8807b5105cce05d85eef0e7944c422c7f99d5b98` (merge PR #6, manual retrieval evaluation workflow).
- Added current architecture/configuration notes, milestone history, retrieval baseline interpretation, approval boundaries, and next actions to `PROJECT_CONTEXT.md`.
- User approved the compact B2 benchmark scope: 6 synthetic documents and 40 questions; embedding remains `text-embedding-v1`.
- At the initial snapshot, the downloadable B2 archive was not yet verified; the repository corpus was subsequently added later on 2026-11-26 (see evening refresh).
- No application code or Render configuration changed as part of this documentation setup.

### 2026-11-26 evening refresh

- Re-checked GitHub: the latest application-code commit at review time was `a431fb4727818f9fab5c4bb3c1e85e7c466964c7`; 14 commits had been added after the initial archive snapshot, including the B2 corpus and multi-evidence evaluator changes. The archive refresh then advanced `main` with docs-only commits.
- Verified the repository now contains the six-document, 40-question B2 corpus under `backend/evaluation/b2/`; category counts are 10/8/8/5/4/5. Read-only evidence-anchor/source-reference cross-check found no mismatches.
- Evaluator and tests now include multi-evidence, evidence completeness, source coverage, and no-answer candidate-presence metrics. The latter is `no_answer_nonempty@K`, not a judged false-positive rate.
- Latest CI run `45783910071` on HEAD completed successfully: backend tests and frontend typecheck/build both passed. No B2 production evaluation run or deployment confirmation was found.
- Flagged repository/documentation drift for follow-up: B2 documents and almost all questions are English; no `HR-005` exists in the current dataset; the workflow comment and `docs/retrieval-evaluation.md` still describe the old 35-question setup.
- No application code, workflow, configuration, or Render setting was changed by this archive refresh.


## 2026-11-27 — B2 evaluation wrap-up

- Recorded the user-provided Keyword, Vector, and Hybrid B2 reports (same 40-question / six-document dataset) in `PROJECT_CONTEXT.md`.
- Compared Recall, evidence recall/completeness, source coverage, and MRR. Hybrid is the strongest top-1 candidate; Vector leads Evidence Complete@3; Keyword leads Recall@3 and Evidence Recall@3. No mode dominates every cutoff.
- All three runs report six documents indexed and no reranker requested. No-answer candidate-presence is explicitly not treated as false-positive rate or successful refusal.
- Identified multi-document / complex-scenario evidence coverage and semantic-paraphrase ranking as the main follow-up evaluation areas. The benchmark remains small and synthetic.
- Closed the B2 three-mode comparison stage and documented the proposed P1 multi-turn chat UI / backend Conversation workstream and acceptance scenarios.
- No application code, workflow, model, embedding configuration, Render setting, or deployment was changed. Application-code work still requires a separate implementation plan and explicit approval.

## 2026-11-27

- Recorded the user-provided B2 Keyword, Vector, and Hybrid reports in `docs/PROJECT_CONTEXT.md`; all three use dataset `enterprise_rag_b2_compact` v1.0.0 (40 questions, six documents) and report all six documents indexed.
- Added the aggregate comparison for Recall, Evidence Recall, Evidence Complete, Source Coverage, and MRR. Hybrid leads on top-1 ranking; Vector leads Evidence Complete@3; Vector and Hybrid both reach 100% Evidence Complete@5; Keyword remains competitive at @3.
- Recorded limitations: reranker was not requested; `no_answer_nonempty@K` measures candidate presence only, not false positives or answer abstention; the synthetic six-document/40-question benchmark is not production-grade evidence.
- Provisional recommendation: Hybrid as the demo default, retaining Vector and Keyword for comparison. No retrieval algorithm, embedding model, application code, workflow, Render setting, or deployment was changed.
- Added the next workstream for conversational UI and backend conversation/history support, with acceptance scenarios and safety/grounding constraints. Implementation remains subject to normal code-change approval.
- Documentation commit for `PROJECT_CONTEXT.md`: `7c53bc550eb6391f09db1d677796500d3ae97f2c`.

