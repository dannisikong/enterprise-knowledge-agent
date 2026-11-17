from __future__ import annotations

import os

import httpx


def reranker_configured() -> bool:
    return bool(os.getenv("RERANK_API_KEY"))


def rerank_config() -> tuple[str, str, str]:
    base_url = os.getenv("RERANK_BASE_URL", "https://api.cohere.com/v2").rstrip("/")
    model = os.getenv("RERANK_MODEL", "rerank-v3.5")
    api_key = os.getenv("RERANK_API_KEY", "")
    return base_url, model, api_key


def apply_rerank_order(candidates: list[dict], ranked_indices: list[dict], limit: int) -> list[dict]:
    """Reorder candidates using provider-returned indices and attach reranker scores."""
    reranked = []
    seen: set[int] = set()
    for item in ranked_indices:
        index = item.get("index")
        if not isinstance(index, int) or index < 0 or index >= len(candidates) or index in seen:
            continue
        seen.add(index)
        candidate = {**candidates[index], "rerank_score": round(float(item.get("relevance_score", 0.0)), 6)}
        reranked.append(candidate)
    return reranked[:limit]


async def rerank_documents(query: str, candidates: list[dict], limit: int) -> list[dict]:
    """Call a Cohere v2-compatible rerank endpoint."""
    if not candidates:
        return []
    base_url, model, api_key = rerank_config()
    if not api_key:
        raise RuntimeError("Reranker is not configured.")
    payload = {
        "model": model,
        "query": query,
        "documents": [item["content"] for item in candidates],
        "top_n": min(limit, len(candidates)),
    }
    timeout = httpx.Timeout(45.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/rerank",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json().get("results", [])
    return apply_rerank_order(candidates, data, limit)
