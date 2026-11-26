#!/usr/bin/env python3
"""Structural validator for the Enterprise RAG B2 compact corpus."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "single_document": 10, "semantic_paraphrase": 8, "distractor": 8,
    "multi_document": 5, "no_answer": 4, "complex_scenario": 5,
}
data = json.loads((ROOT / "retrieval_dataset_b2.json").read_text(encoding="utf-8"))
docs, questions = data["documents"], data["questions"]
assert len(docs) == 6, f"Expected 6 documents, got {len(docs)}"
for name in docs:
    assert (ROOT / "documents" / name).is_file(), f"Missing document: {name}"
assert len(questions) == 40, f"Expected 40 questions, got {len(questions)}"
assert len({q["id"] for q in questions}) == 40, "Question IDs must be unique"
counts = {}
for q in questions:
    counts[q["category"]] = counts.get(q["category"], 0) + 1
    assert q["query"].strip(), f"Empty query: {q['id']}"
    if q["answerable"]:
        assert q["required_evidence"], f"Missing evidence: {q['id']}"
        for e in q["required_evidence"]:
            assert e["document"] in docs, f"Unknown document in {q['id']}"
            assert e["evidence_phrase"].strip(), f"Empty evidence in {q['id']}"
    else:
        assert q["category"] == "no_answer", f"Unexpected unanswerable item: {q['id']}"
        assert not q["required_evidence"] and not q["expected_source_documents"], q["id"]
assert counts == EXPECTED, f"Category counts mismatch: {counts}"
assert next(q["query"] for q in questions if q["id"] == "CX-004") == "P3 故障最长多久内响应？"
print("PASS: 6 documents, 40 unique questions, category counts and evidence references valid.")
