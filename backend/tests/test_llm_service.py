from app.services.llm_service import build_grounded_messages


def test_build_grounded_messages_maps_source_ids_and_context():
    results = [{
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "filename": "handbook.md",
        "chunk_index": 2,
        "content": "员工每年享有 10 天年假。",
        "score": 0.81,
    }]

    messages, sources = build_grounded_messages("年假有几天？", results)

    assert sources[0]["id"] == 1
    assert sources[0]["chunk_id"] == "chunk-1"
    assert "[1] 文件：handbook.md（片段 3）" in messages[1]["content"]
    assert "员工每年享有 10 天年假。" in messages[1]["content"]
    assert "[1]" in messages[0]["content"]


def test_empty_context_is_represented_without_fabricated_sources():
    messages, sources = build_grounded_messages("未知问题", [])

    assert sources == []
    assert "检索资料：" in messages[1]["content"]
