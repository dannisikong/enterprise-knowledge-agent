from app.services.chunking import split_text


def test_split_text_returns_chunks_with_overlap():
    text = "甲" * 900
    chunks = split_text(text, chunk_size=400, overlap=50)
    assert len(chunks) >= 2
    assert all(0 < len(chunk) <= 400 for chunk in chunks)
    assert chunks[0][-50:] == chunks[1][:50]


def test_split_text_handles_empty_input():
    assert split_text("   ") == []


def test_split_text_rejects_invalid_overlap():
    try:
        split_text("hello", chunk_size=100, overlap=100)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")
