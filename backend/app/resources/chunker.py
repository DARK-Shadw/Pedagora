"""Structure-aware recursive text chunking for RAG pipeline."""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 512
DEFAULT_OVERLAP_TOKENS = 64
# Approximate: 1 token ≈ 4 chars for English text
CHARS_PER_TOKEN = 4


@dataclass
class Chunk:
    content: str
    context_prefix: str
    token_count: int
    page_number: int | None = None
    section_path: str = ""


def _estimate_tokens(text: str) -> int:
    """Rough token count estimate."""
    return len(text) // CHARS_PER_TOKEN


def _split_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Split text into chunks respecting sentence/paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + max_chars

        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Try to break at paragraph boundary
        para_break = text.rfind("\n\n", start + max_chars // 2, end)
        if para_break > start:
            end = para_break
        else:
            # Try sentence boundary
            for sep in [". ", ".\n", "! ", "? "]:
                sent_break = text.rfind(sep, start + max_chars // 2, end)
                if sent_break > start:
                    end = sent_break + len(sep)
                    break

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(chunk_text)

        start = max(start + 1, end - overlap_chars)

    return chunks


def chunk_sections(
    sections: list,  # list of ParsedSection
    file_name: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Chunk parsed sections with deterministic context prefixes.

    Rules:
    - Never split tables or formulas (content containing | or $$ markers)
    - Prepend context prefix: [Doc: {name}] [Section: {path}] [Page: {n}]
    - Respect max_tokens with overlap for context continuity
    """
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    chunks: list[Chunk] = []

    for section in sections:
        if not section.content:
            continue

        content = section.content.strip()
        if not content:
            continue

        # Build context prefix
        prefix_parts = [f"[Doc: {file_name}]"]
        if section.path:
            prefix_parts.append(f"[Section: {section.path}]")
        if section.page_start is not None:
            prefix_parts.append(f"[Page: {section.page_start}]")
        context_prefix = " ".join(prefix_parts)

        # Check if content contains tables or formulas that shouldn't be split
        has_table = "|" in content and content.count("|") > 4
        has_formula = "$$" in content or "\\begin{" in content

        if (has_table or has_formula) and _estimate_tokens(content) <= max_tokens * 2:
            # Keep intact even if slightly over limit
            chunks.append(Chunk(
                content=content,
                context_prefix=context_prefix,
                token_count=_estimate_tokens(content),
                page_number=section.page_start,
                section_path=section.path,
            ))
            continue

        # Split text into chunks
        text_chunks = _split_text(content, max_chars, overlap_chars)

        for text_chunk in text_chunks:
            if not text_chunk.strip():
                continue
            chunks.append(Chunk(
                content=text_chunk,
                context_prefix=context_prefix,
                token_count=_estimate_tokens(text_chunk),
                page_number=section.page_start,
                section_path=section.path,
            ))

    logger.info(f"Chunked {len(sections)} sections into {len(chunks)} chunks for {file_name}")
    return chunks
