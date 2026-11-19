import asyncio

from app.services.llm_service import _iter_sse_data


def collect_sse_data(lines: list[str]) -> list[str]:
    async def source():
        for line in lines:
            yield line

    async def collect() -> list[str]:
        return [item async for item in _iter_sse_data(source())]

    return asyncio.run(collect())


def test_sse_parser_collects_multiple_data_lines():
    assert collect_sse_data(["data: first", "data: second", "", ""]) == ["first\nsecond"]


def test_sse_parser_ignores_comments_and_non_data_fields():
    assert collect_sse_data([": keepalive", "event: message", "id: 7", "data: payload", ""]) == ["payload"]


def test_sse_parser_flushes_final_event_without_trailing_blank_line():
    assert collect_sse_data(["data: final payload"]) == ["final payload"]


def test_sse_parser_preserves_empty_data_field():
    assert collect_sse_data(["data:", ""]) == [""]
