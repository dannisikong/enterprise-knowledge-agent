from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import httpx


def llm_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY"))


def _settings() -> tuple[str, str, str]:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured.")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    return api_key, base_url, model


def build_grounded_messages(question: str, results: list[dict]) -> tuple[list[dict], list[dict]]:
    sources = [
        {
            "id": index,
            "chunk_id": item["chunk_id"],
            "document_id": item["document_id"],
            "filename": item["filename"],
            "chunk_index": item["chunk_index"],
            "content": item["content"],
            "score": item.get("score"),
            "rerank_score": item.get("rerank_score"),
        }
        for index, item in enumerate(results, start=1)
    ]
    context = "\n\n".join(
        f"[{source['id']}] 文件：{source['filename']}（片段 {source['chunk_index'] + 1}）\n{source['content']}"
        for source in sources
    )
    system = (
        "你是企业内部知识库助手。只能依据用户提供的检索资料回答。"
        "如果资料没有明确依据，必须说明知识库中没有足够信息，不得猜测或补造政策。"
        "回答中的事实性结论必须使用 [1] 这样的来源编号标注；编号只能来自给定资料。"
        "用简洁、清晰的中文回答。"
    )
    user = (
        f"问题：{question}\n\n检索资料：\n{context}\n\n"
        "请根据资料回答，并在相关句子后标注来源编号。若资料不支持答案，请明确说明。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], sources


async def generate_answer(messages: list[dict]) -> str:
    api_key, base_url, model = _settings()
    timeout = httpx.Timeout(90.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "temperature": 0.2, "stream": False},
        )
        response.raise_for_status()
        payload = response.json()
    return payload["choices"][0]["message"]["content"]


async def _iter_sse_data(lines: AsyncIterator[str]) -> AsyncIterator[str]:
    """Yield complete SSE data payloads, including multi-line data fields."""
    data_lines: list[str] = []
    async for line in lines:
        if line == "":
            if data_lines:
                yield "\n".join(data_lines)
                data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if field != "data":
            continue
        if separator and value.startswith(" "):
            value = value[1:]
        data_lines.append(value)

    if data_lines:
        yield "\n".join(data_lines)


async def stream_answer(messages: list[dict]) -> AsyncIterator[str]:
    api_key, base_url, model = _settings()
    timeout = httpx.Timeout(90.0, connect=10.0, read=90.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "temperature": 0.2, "stream": True},
        ) as response:
            response.raise_for_status()
            async for data in _iter_sse_data(response.aiter_lines()):
                if data == "[DONE]":
                    break
                if not data:
                    continue
                payload = json.loads(data)
                choices = payload.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if isinstance(content, str) and content:
                    yield content
