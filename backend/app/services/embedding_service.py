from __future__ import annotations

import os

import httpx


def embeddings_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


async def create_embeddings(texts: list[str]) -> list[list[float]] | None:
    """Call an OpenAI-compatible embeddings endpoint; return None if not configured."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not texts:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    timeout = httpx.Timeout(60.0, connect=10.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "input": texts},
        )
        response.raise_for_status()
        payload = response.json()

    items = sorted(payload["data"], key=lambda item: item["index"])
    vectors = [item["embedding"] for item in items]
    if len(vectors) != len(texts):
        raise RuntimeError("Embedding provider returned an unexpected vector count.")
    return vectors
