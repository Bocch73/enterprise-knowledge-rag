"""Deterministic, boundary-aware text chunking with source offsets."""

from dataclasses import dataclass
from hashlib import sha256

BOUNDARIES = (
    "\r\n\r\n",
    "\n\n",
    "\r\n",
    "\n",
    "\u3002",
    "\uff01",
    "\uff1f",
    "\uff1b",
    ". ",
    "! ",
    "? ",
    "; ",
)


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One ordered piece of text and its exact position in the parsed source."""

    index: int
    content: str
    start_offset: int
    end_offset: int
    content_sha256: str


def _choose_end(text: str, start: int, hard_end: int) -> int:
    """Prefer a natural boundary in the final 40 percent of the allowed window."""
    minimum_boundary = start + int((hard_end - start) * 0.6)
    for separator in BOUNDARIES:
        position = text.rfind(separator, minimum_boundary, hard_end)
        if position >= 0:
            return position + len(separator)
    return hard_end


def split_text(text: str, *, chunk_size: int, overlap: int) -> list[TextChunk]:
    """Split text without losing source offsets or exceeding the configured size."""
    if chunk_size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk overlap must be non-negative and smaller than chunk size")
    if not text.strip():
        raise ValueError("text must contain visible characters")

    chunks: list[TextChunk] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        while start < text_length and text[start].isspace():
            start += 1
        if start >= text_length:
            break

        hard_end = min(start + chunk_size, text_length)
        end = _choose_end(text, start, hard_end) if hard_end < text_length else text_length
        while end > start and text[end - 1].isspace():
            end -= 1
        if end <= start:
            end = hard_end

        content = text[start:end]
        chunks.append(
            TextChunk(
                index=len(chunks),
                content=content,
                start_offset=start,
                end_offset=end,
                content_sha256=sha256(content.encode("utf-8")).hexdigest(),
            )
        )
        if end >= text_length:
            break
        start = max(end - overlap, start + 1)

    return chunks
