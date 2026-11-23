import asyncio

from app.services import embedding_service


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    batches = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers, json):
        self.batches.append(json["input"])
        data = [
            {"index": index, "embedding": [float(len(text)), 1.0]}
            for index, text in reversed(list(enumerate(json["input"])))
        ]
        return FakeResponse({"data": data})


def test_create_embeddings_batches_and_restores_input_order(monkeypatch):
    FakeClient.batches = []
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setattr(embedding_service.httpx, "AsyncClient", FakeClient)

    texts = [f"text-{index}" for index in range(23)]
    vectors = asyncio.run(embedding_service.create_embeddings(texts))

    assert [len(batch) for batch in FakeClient.batches] == [10, 10, 3]
    assert vectors == [[float(len(text)), 1.0] for text in texts]


def test_create_embeddings_returns_none_when_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert asyncio.run(embedding_service.create_embeddings(["hello"])) is None
