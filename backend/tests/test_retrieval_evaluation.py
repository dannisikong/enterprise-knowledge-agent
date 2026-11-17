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


def test_reciprocal_rank_uses_first_relevant_result():
    results = [result("irrelevant"), result("gold passage"), result("gold passage")]
    assert reciprocal_rank(results, "gold passage") == 0.5


def test_evaluate_and_aggregate_metrics():
    rows = [
        evaluate_query([result("gold")], "gold"),
        evaluate_query([result("other")], "gold"),
    ]
    assert aggregate_metrics(rows) == {"recall@5": 0.5, "mrr": 0.5, "query_count": 2}
