from typing import List

import tiktoken


def chunk_text_tokens(
    text: str,
    chunk_tokens: int = 800,
    overlap_tokens: int = 120,
    model: str = "gpt-4o-mini",
) -> List[str]:
    """
    Token-based chunking to avoid overflow and keep context aligned with model limits.
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    enc = tiktoken.encoding_for_model(model)
    tokens = enc.encode(cleaned)
    if not tokens:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + chunk_tokens, len(tokens))
        chunk = tokens[start:end]
        chunks.append(enc.decode(chunk))
        if end == len(tokens):
            break
        start = max(0, end - overlap_tokens)
    return chunks
