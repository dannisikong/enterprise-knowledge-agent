from __future__ import annotations

import os

import httpx


# Bailian text-embedding-v4 accepts at most 10 input texts per request.
EMBEDDING_BATCH_SIZE = 10


def embeddings_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


async def create_embeddings(texts: list[str]) -> list[list[float]] | None:
    """Call an OpenAI-compatible embeddings endpoint in bounded batches."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not texts:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
    timeout = httpx.Timeout(60.0, connect=10.0)
    vectors: list[list[float]] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for offset in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[offset:offset + EMBEDDING_BATCH_SIZE]
            response = await client.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": batch},
            )
            response.raise_for_status()
            try:
                payload = response.json()
                items = sorted(payload["data"], key=lambda item: item["index"])
                batch_vectors = [item["embedding"] for item in items]
            except (KeyError, TypeError, ValueError) as error:
                raise RuntimeError("Embedding provider returned an invalid response payload.") from error

            if len(batch_vectors) != len(batch):
                raise RuntimeError(
                    f"Embedding provider returned {len(batch_vectors)} vectors for {len(batch)} inputs."
                )
            if not batch_vectors:
                raise RuntimeError("Embedding provider returned no vectors.")

            if any(
                not isinstance(vector, list)
                or not vector
                or any(not isinstance(value, (int, float)) for value in vector)
                for vector in batch_vectors
            ):
                raise RuntimeError("Embedding provider returned vectors with invalid dimensions or values.")
            dimensions = {len(vector) for vector in batch_vectors}
            if len(dimensions) != 1:
                raise RuntimeError("Embedding provider returned inconsistent vector dimensions.")

            vectors.extend([[float(value) for value in vector] for vector in batch_vectors])

    dimensions = {len(vector) for vector in vectors}
    if len(vectors) != len(texts) or len(dimensions) != 1:
        raise RuntimeError("Embedding provider returned inconsistent vector dimensions.")
    return vectors
