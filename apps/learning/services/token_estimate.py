from __future__ import annotations


def estimate_text_tokens(content: str) -> int:
    """Return a conservative provider-independent estimate for UTF-8 text."""
    if not isinstance(content, str) or not content:
        return 1
    encoded_bytes = len(content.encode("utf-8"))
    # Two bytes per token is deliberately conservative for CJK/Markdown text;
    # the provider's trusted usage remains the settlement authority.
    return max(1, (encoded_bytes + 1) // 2)


__all__ = ["estimate_text_tokens"]
