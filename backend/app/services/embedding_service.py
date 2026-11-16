from __future__ import annotations

import os

import httpx


def embeddings_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


async def create_embeddings(texts: list[str]) -> list[list[float]] | None:
    """Call an OpenAI-compatible embeddings endpoint in bounded batches."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not texts:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    timeout = httpx.Timeout(60.0, connect=10.0)
    vectors: list[list[float]] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for offset in range(0, len(texts), 64):
            batch = texts[offset:offset + 64]
            response = await client.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": batch},
            )
            response.raise_for_status()
            payload = response.json()
            items = sorted(payload["data"], key=lambda item: item["index"])
            batch_vectors = [item["embedding"] for item in items]
            if len(batch_vectors) != len(batch):
                raise RuntimeError("Embedding provider returned an unexpected vector count.")
            vectors.extend(batch_vectors)

    return vectors
