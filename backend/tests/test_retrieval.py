from app.services.retrieval import keyword_score, reciprocal_rank_fusion


def item(chunk_id: str, score: float) -> dict:
    return {"chunk_id": chunk_id, "score": score, "content": chunk_id}


def test_keyword_score_counts_distinct_query_terms():
    assert keyword_score("年假 天数", "员工年假天数为十天") == 1.0
    assert keyword_score("不存在词语", "这里没有相关内容") == 0.0


def test_rrf_rewards_items_ranked_by_both_retrievers():
    keyword = [item("shared", 0.9), item("keyword-only", 0.8)]
    vector = [item("vector-only", 0.95), item("shared", 0.7)]
    results = reciprocal_rank_fusion([keyword, vector], limit=3)
    assert results[0]["chunk_id"] == "shared"
    assert results[0]["keyword_rank"] == 1
    assert results[0]["vector_rank"] == 2
    assert len({result["chunk_id"] for result in results}) == 3


def test_rrf_handles_empty_branch_and_limit():
    results = reciprocal_rank_fusion([[], [item("only-vector", 0.8)]], limit=1)
    assert [result["chunk_id"] for result in results] == ["only-vector"]
    assert reciprocal_rank_fusion([[], []], limit=5) == []
