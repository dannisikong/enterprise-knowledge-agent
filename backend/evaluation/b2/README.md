# Enterprise RAG B2 Compact Evaluation Corpus

## Contents
- `documents/`: six synthetic enterprise policy documents
- `retrieval_dataset_b2.json`: 40 questions with expected evidence anchors
- `manifest.json`: scope, counts, metrics, and limitations
- `validate_dataset.py`: local structural validator

## Corpus composition
| Category | Questions |
|---|---:|
| single_document | 10 |
| semantic_paraphrase | 8 |
| distractor | 8 |
| multi_document | 5 |
| no_answer | 4 |
| complex_scenario | 5 |
| **Total** | **40** |

## Evaluation protocol
Upload all six documents into one dedicated evaluation session. Run Keyword, Vector, and Hybrid against the same corpus and question set. Keep `text-embedding-v1` unchanged.

Report Recall@1/3/5, MRR, Evidence Recall@K, multi-document evidence completeness/source coverage, no-answer retrieval false-positive rate, and per-category results.

## Dataset schema
Each question has `id`, `category`, `query`, `answerable`, `required_evidence`, `expected_source_documents`, and `notes`. Unanswerable items have empty evidence/source arrays.

## Validation
Run `python validate_dataset.py`.

## Limitations
This is a synthetic benchmark, not a validated production benchmark. Evidence anchors are textual matching hints, not perfect semantic ground truth. The current application evaluator may not accept this schema directly; inspect its API contract before adapting it. Retrieval metrics do not measure answer correctness, citation faithfulness, prompt-injection resistance, or cross-session isolation.
