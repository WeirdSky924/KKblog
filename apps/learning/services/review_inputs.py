import re

from apps.learning.contracts import LearningCommandError

MAX_REVIEW_BLOCK_BYTES = 16 * 1024
MAX_REVIEW_BLOCKS = 128
MAX_REVIEW_INPUT_BYTES = 2 * 1024 * 1024
_DANGEROUS_LINK = re.compile(r"(?i)\]\(\s*(?:javascript|data|file|vbscript)\s*:")
_STRUCTURAL_LINE = re.compile(r"^\s*(?:#{1,6}\s|[-+*]\s|\d+[.)]\s)")
_LONG_REPEAT = re.compile(r"(.)\1{8191,}", re.DOTALL)


def _paragraphs(content: str) -> tuple[str, ...]:
    result: list[str] = []
    current: list[str] = []
    for line in content.splitlines(keepends=True):
        if current and _STRUCTURAL_LINE.match(line):
            result.append("".join(current))
            current = []
        current.append(line)
        if not line.strip():
            result.append("".join(current))
            current = []
    if current:
        result.append("".join(current))
    return tuple(result)


def _split_piece(piece: str) -> tuple[str, ...]:
    if len(piece.encode("utf-8")) <= MAX_REVIEW_BLOCK_BYTES:
        return (piece,)
    chunks: list[str] = []
    current: list[str] = []
    current_bytes = 0
    for character in piece:
        encoded_bytes = len(character.encode("utf-8"))
        if current and current_bytes + encoded_bytes > MAX_REVIEW_BLOCK_BYTES:
            chunks.append("".join(current))
            current = []
            current_bytes = 0
        current.append(character)
        current_bytes += encoded_bytes
    if current:
        chunks.append("".join(current))
    return tuple(chunks)


def review_input_blocks(content: str) -> tuple[str, ...]:
    if not isinstance(content, str) or not content:
        raise LearningCommandError(
            "learning.review_input_invalid.v1", "审核输入不合法。"
        )
    encoded_size = len(content.encode("utf-8"))
    if encoded_size > MAX_REVIEW_INPUT_BYTES:
        raise LearningCommandError(
            "learning.review_input_too_large.v1", "知识文档超过审核输入上限。"
        )
    if _DANGEROUS_LINK.search(content):
        raise LearningCommandError(
            "learning.document_link_unsafe.v1", "知识文档包含危险链接。"
        )
    if (
        _LONG_REPEAT.search(content)
        or content.count("\n") > 100_000
        or sum(1 for line in content.splitlines() if line.startswith("#")) > 10_000
        or any(len(line.encode("utf-8")) > 64 * 1024 for line in content.splitlines())
    ):
        raise LearningCommandError(
            "learning.document_structure_invalid.v1", "知识文档结构超出安全上限。"
        )

    blocks: list[str] = []
    current = ""
    for paragraph in _paragraphs(content):
        for piece in _split_piece(paragraph):
            if (
                current
                and len((current + piece).encode("utf-8")) > MAX_REVIEW_BLOCK_BYTES
            ):
                blocks.append(current)
                current = ""
            current += piece
    if current:
        blocks.append(current)
    if not blocks or len(blocks) > MAX_REVIEW_BLOCKS or "".join(blocks) != content:
        raise LearningCommandError(
            "learning.review_input_invalid.v1", "审核输入无法安全分块。"
        )
    return tuple(blocks)


__all__ = [
    "MAX_REVIEW_BLOCK_BYTES",
    "MAX_REVIEW_BLOCKS",
    "review_input_blocks",
]
