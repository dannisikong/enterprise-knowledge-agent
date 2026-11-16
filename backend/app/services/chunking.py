from __future__ import annotations

import re


def split_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """Split text into readable character-based chunks with a small overlap."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Invalid chunk_size/overlap configuration.")

    normalized = re.sub(r"\r\n?", "\n", text).strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(normalized)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            # Prefer a paragraph or sentence boundary near the end of the window.
            boundary = max(
                normalized.rfind("\n\n", start, end),
                normalized.rfind("。", start, end),
                normalized.rfind(". ", start, end),
                normalized.rfind("！", start, end),
                normalized.rfind("？", start, end),
            )
            if boundary > start + chunk_size // 2:
                end = boundary + 1

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(end - overlap, start + 1)

    return chunks
