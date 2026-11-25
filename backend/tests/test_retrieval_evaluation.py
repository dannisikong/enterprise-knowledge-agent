from app.services.retrieval_evaluation import (
    aggregate_metrics,
    evaluate_query,
    recall_at_k,
    reciprocal_rank,
)


def result(content: str) -> dict:
    return {"content": content}


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
        "recall@1": 0.5,
        "recall@3": 0.5,
        "recall@5": 0.5,
        "mrr": 0.5,
        "query_count": 2,
    }


def test_aggregate_metrics_handles_empty_input():
    assert aggregate_metrics([]) == {
        "recall@1": 0.0,
        "recall@3": 0.0,
        "recall@5": 0.0,
        "mrr": 0.0,
        "query_count": 0,
    }
