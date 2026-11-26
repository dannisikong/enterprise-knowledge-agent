from app.services.retrieval_evaluation import (
    aggregate_metrics,
    evaluate_query,
    recall_at_k,
    reciprocal_rank,
)


def result(content: str, filename: str | None = None) -> dict:
    item = {"content": content}
    if filename:
        item["filename"] = filename
    return item


def test_recall_at_k_finds_gold_passage_inside_cutoff():
    results = [result("irrelevant"), result("the policy says 10 days")]
    assert recall_at_k(results, "10 days", 5) == 1.0
    assert recall_at_k(results, "10 days", 1) == 0.0


def test_recall_at_k_rejects_invalid_cutoff():
    try:
        recall_at_k([result("gold")], "gold", 0)
    except ValueError as error:
        assert "k must be" in str(error)
    else:
        raise AssertionError("Expected invalid cutoff to raise ValueError")


def test_reciprocal_rank_uses_first_relevant_result():
    results = [result("irrelevant"), result("gold passage"), result("gold passage")]
    assert reciprocal_rank(results, "gold passage") == 0.5


def test_evaluate_query_reports_recall_at_1_3_5_and_mrr():
    results = [result("irrelevant"), result("irrelevant"), result("gold passage")]
    assert evaluate_query(results, "gold passage") == {
        "recall@1": 0.0,
        "recall@3": 1.0,
        "recall@5": 1.0,
        "mrr": 1 / 3,
    }


def test_evaluate_query_supports_custom_cutoff():
    metrics = evaluate_query([result("gold passage")], "gold passage", k=2)
    assert metrics["recall@1"] == 1.0
    assert metrics["recall@2"] == 1.0


def test_aggregate_metrics():
    rows = [
        evaluate_query([result("gold")], "gold"),
        evaluate_query([result("other")], "gold"),
    ]
    assert aggregate_metrics(rows) == {
        "mrr": 0.5,
        "query_count": 2,
        "recall@1": 0.5,
        "recall@3": 0.5,
        "recall@5": 0.5,
    }


def test_aggregate_metrics_handles_empty_input():
    assert aggregate_metrics([]) == {
        "recall@1": 0.0,
        "recall@3": 0.0,
        "recall@5": 0.0,
        "mrr": 0.0,
        "query_count": 0,
    }


def test_multi_evidence_metrics_measure_partial_and_complete_recall():
    evidence = [
        {"document": "hr.md", "evidence_phrase": "10 days annual leave"},
        {"document": "hr.md", "evidence_phrase": "request 5 days ahead"},
        {"document": "it.md", "evidence_phrase": "manager approval"},
    ]
    results = [
        result("10 days annual leave", "hr.md"),
        result("unrelated text", "other.md"),
        result("manager approval", "it.md"),
    ]

    metrics = evaluate_query(
        results,
        k=3,
        required_evidence=evidence,
        expected_source_documents=["hr.md", "it.md"],
    )

    assert metrics["recall@1"] == 1.0
    assert metrics["evidence_recall@1"] == 1 / 3
    assert metrics["evidence_recall@3"] == 2 / 3
    assert metrics["evidence_complete@3"] == 0.0
    assert metrics["source_coverage@1"] == 0.5
    assert metrics["source_coverage@3"] == 1.0


def test_multi_evidence_complete_when_all_required_phrases_are_found():
    evidence = ["approval in advance", "reachable during core hours"]
    results = [result("approval in advance"), result("reachable during core hours")]
    metrics = evaluate_query(results, required_evidence=evidence, k=2)
    assert metrics["evidence_recall@1"] == 0.5
    assert metrics["evidence_recall@3"] == 1.0
    assert metrics["evidence_complete@3"] == 1.0


def test_no_answer_reports_nonempty_candidates_without_claiming_false_positive():
    assert evaluate_query(
        [result("semantically similar but unsupported")],
        answerable=False,
    ) == {
        "no_answer_nonempty@1": 1.0,
        "no_answer_nonempty@3": 1.0,
        "no_answer_nonempty@5": 1.0,
    }
    assert evaluate_query([], answerable=False)["no_answer_nonempty@5"] == 0.0


def test_aggregate_metrics_handles_mixed_answerable_and_no_answer_rows():
    answerable = evaluate_query([result("gold")], "gold")
    no_answer = evaluate_query([], answerable=False)
    metrics = aggregate_metrics([answerable, no_answer])

    assert metrics["query_count"] == 2
    assert metrics["recall@5"] == 1.0
    assert metrics["no_answer_nonempty@5"] == 0.0


def test_answerable_query_requires_evidence():
    try:
        evaluate_query([result("anything")])
    except ValueError as error:
        assert "requires gold_phrase or required_evidence" in str(error)
    else:
        raise AssertionError("Expected missing evidence to raise ValueError")
