from app.services.reranker_service import apply_rerank_order


def test_apply_rerank_order_uses_provider_indices_and_scores():
    candidates = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
    ranked = [
        {"index": 2, "relevance_score": 0.98},
        {"index": 0, "relevance_score": 0.71},
    ]
    results = apply_rerank_order(candidates, ranked, limit=2)
    assert [item["chunk_id"] for item in results] == ["c", "a"]
    assert results[0]["rerank_score"] == 0.98


def test_apply_rerank_order_ignores_invalid_and_duplicate_indices():
    candidates = [{"chunk_id": "a"}, {"chunk_id": "b"}]
    ranked = [
        {"index": 1, "relevance_score": 0.8},
        {"index": 1, "relevance_score": 0.7},
        {"index": 8, "relevance_score": 0.9},
        {"index": -1, "relevance_score": 0.9},
    ]
    assert [item["chunk_id"] for item in apply_rerank_order(candidates, ranked, 5)] == ["b"]
