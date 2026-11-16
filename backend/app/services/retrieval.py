from __future__ import annotations

import re
from typing import Any


def keyword_score(query: str, content: str) -> float:
    """A lightweight token-presence score; not BM25 or a Chinese segmenter."""
    terms = {term.lower() for term in re.findall(r"[\\w\\u4e00-\\u9fff]+", query) if len(term) > 1}
    if not terms:
        return 0.0
    target = content.lower()
    matched = sum(1 for term in terms if term in target)
    return matched / len(terms)


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    limit: int,
    rank_constant: int = 60,
) -> list[dict[str, Any]]:
    """Fuse ranked result lists using RRF, deduplicating by chunk_id."""
    fused: dict[str, dict[str, Any]] = {}
    for source_name, results in zip(("keyword_rank", "vector_rank"), ranked_lists):
        for rank, result in enumerate(results, start=1):
            chunk_id = result["chunk_id"]
            if chunk_id not in fused:
                fused[chunk_id] = {**result, "score": 0.0}
            fused[chunk_id]["score"] += 1.0 / (rank_constant + rank)
            fused[chunk_id][source_name] = rank
    return sorted(fused.values(), key=lambda item: item["score"], reverse=True)[:limit]
