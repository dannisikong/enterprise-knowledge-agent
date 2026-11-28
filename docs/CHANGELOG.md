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


### 2026-11-27 evening GitHub verification

- Verified current `main` HEAD `b11c73a701b62c3c2dee378f16efe7487821c9ef`; compare from application commit `a431fb4727818f9fab5c4bb3c1e85e7c466964c7` confirms subsequent changes are confined to the two project archive files.
- Current-main CI run [45989001273](https://github.com/dannisikong/enterprise-knowledge-agent/actions/runs/45989001273) completed successfully; Backend tests and Frontend typecheck/build both passed.
- Retrieval Evaluation runs [45986181481](https://github.com/dannisikong/enterprise-knowledge-agent/actions/runs/45986181481) and [45927059311](https://github.com/dannisikong/enterprise-knowledge-agent/actions/runs/45927059311) both completed successfully. Keyword, Vector, Hybrid, and artifact-upload steps passed; each produced a 10,791-byte report artifact retained until 2026-12-11. Artifact contents were not downloaded in this check, so no new metric values are asserted.
- PRs #1–#6 are closed; no open PR was returned. Render deployment commit remains unverified.
- No application code, workflow, configuration, or deployment setting was changed.


## 2026-11-28 — conversation delivery and current PR status

- Re-checked `main`: latest HEAD is `0101185aaef729b218d2e6611aa6f5968e73cf97`, the merge commit for PR #9. No newer main commit was present during this check.
- Verified PR #7 (backend conversation persistence/streaming), PR #8 (conversation chat UI), and PR #9 (mobile navigation/H5 layout) are merged. Their main-branch CI runs `45994164898`, `45997225402`, and `46003015497` all completed successfully; related PR CI runs also succeeded.
- User confirmed on 2026-11-27 that PC chat interaction and H5 layout/navigation were working. This is recorded as user-confirmed runtime behavior; Render deployment SHA remains unverified.
- Found PR #10, “feat: add rolling conversation summary memory”, still open and four commits ahead of main. Its PR CI run `46009069984` succeeded. The proposal summarizes older conversation messages while retaining the latest six raw messages; it is not merged and must not be treated as a main-branch or deployed capability.
- Updated current priorities: review PR #10; validate multi-turn follow-ups, long-context behavior, session/conversation isolation, history restoration, and per-message citations. Chat UI, backend conversation support, and H5 navigation are no longer listed as features awaiting initial implementation.
- No application code, workflow, configuration, branch protection, secrets, or Render settings were changed. Only the two authorized project archive files were updated.


## 2026-11-28 evening — document, conversation, and observability milestones

- Re-checked GitHub main and PRs: latest main HEAD is `5ea1833f601b018c922cd3c62ace9edb79235181`, the PR #15 merge commit. PRs #10–#15 are merged; PRs #1–#15 are closed and no open PR was returned.
- Recorded newly merged repository capabilities: PR #10 rolling conversation summary memory; #11 secure ZIP batch upload; #12 document management; #13 session-scoped RAG request tracing; #14 trace diagnostics and answer feedback; #15 secure admin observability APIs.
- Verified successful main CI runs for merges #11–#15: `46124754123`, `46126046945`, `46145701775`, `46146805050`, and `46147364491`. Final PR CI runs for #10–#15 also succeeded. Some intermediate PR commits had failed checks before fixes; final PR and main checks passed.
- Clarified that the new capabilities are repository-verified only. No Render deployment SHA or user confirmation of deployment of today's features was available in this check.
- Updated next validation priorities: ZIP/document lifecycle and concurrency; trace correctness, privacy, isolation and retention; admin auth/authorization; long-context summary quality; and confirmation of whether an admin observability frontend view exists.
- No application code, workflows, configuration, branch protection, secrets, or Render settings were modified. Only the two authorized archive files were updated.
