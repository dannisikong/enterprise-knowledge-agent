from __future__ import annotations


DEFAULT_CUTOFFS = (1, 3, 5)


def reciprocal_rank(results: list[dict], gold_phrase: str) -> float:
    """Return reciprocal rank of the first result containing the gold phrase."""
    for rank, result in enumerate(results, start=1):
        if gold_phrase in result.get("content", ""):
            return 1.0 / rank
    return 0.0


def recall_at_k(results: list[dict], gold_phrase: str, k: int = 5) -> float:
    """Single-gold-passage recall: 1 when the relevant passage appears in top k."""
    if k < 1:
        raise ValueError("k must be greater than or equal to 1.")
    return float(any(gold_phrase in item.get("content", "") for item in results[:k]))


def evaluate_query(
    results: list[dict],
    gold_phrase: str,
    k: int = 5,
    cutoffs: tuple[int, ...] = DEFAULT_CUTOFFS,
) -> dict:
    metrics = {f"recall@{cutoff}": recall_at_k(results, gold_phrase, cutoff) for cutoff in cutoffs}
    if k not in cutoffs:
        metrics[f"recall@{k}"] = recall_at_k(results, gold_phrase, k)
    metrics["mrr"] = reciprocal_rank(results, gold_phrase)
    return metrics


def aggregate_metrics(rows: list[dict], k: int = 5) -> dict:
    if not rows:
        return {
            "recall@1": 0.0,
            "recall@3": 0.0,
            "recall@5": 0.0,
            **({f"recall@{k}": 0.0} if k not in DEFAULT_CUTOFFS else {}),
            "mrr": 0.0,
            "query_count": 0,
        }
    keys = [key for key in rows[0] if key.startswith("recall@") or key == "mrr"]
    return {
        **{
            key: round(sum(row[key] for row in rows) / len(rows), 4)
            for key in keys
        },
        "query_count": len(rows),
    }
