from __future__ import annotations


def reciprocal_rank(results: list[dict], gold_phrase: str) -> float:
    """Return reciprocal rank of the first result containing the gold phrase."""
    for rank, result in enumerate(results, start=1):
        if gold_phrase in result.get("content", ""):
            return 1.0 / rank
    return 0.0


def recall_at_k(results: list[dict], gold_phrase: str, k: int = 5) -> float:
    """Single-gold-passage recall: 1 when the relevant passage appears in top k."""
    return float(any(gold_phrase in item.get("content", "") for item in results[:k]))


def evaluate_query(results: list[dict], gold_phrase: str, k: int = 5) -> dict:
    return {
        f"recall@{k}": recall_at_k(results, gold_phrase, k),
        "mrr": reciprocal_rank(results, gold_phrase),
    }


def aggregate_metrics(rows: list[dict], k: int = 5) -> dict:
    if not rows:
        return {f"recall@{k}": 0.0, "mrr": 0.0, "query_count": 0}
    return {
        f"recall@{k}": round(sum(row[f"recall@{k}"] for row in rows) / len(rows), 4),
        "mrr": round(sum(row["mrr"] for row in rows) / len(rows), 4),
        "query_count": len(rows),
    }
