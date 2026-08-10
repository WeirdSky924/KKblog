from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from django.core.exceptions import ValidationError

NICKNAME_BUDGET = 16


@dataclass(frozen=True, slots=True)
class ValidatedNickname:
    display: str | None
    normalized: str | None
    budget: int


def validate_nickname(value: str | None) -> ValidatedNickname:
    if value is None:
        return ValidatedNickname(None, None, 0)
    if not isinstance(value, str):
        raise ValidationError("昵称格式无效。", code="invalid")
    display = value.strip()
    if not display:
        return ValidatedNickname(None, None, 0)
    normalized_display = unicodedata.normalize("NFKC", display)
    if not _is_safe_visible_text(display) or not _is_safe_visible_text(
        normalized_display
    ):
        raise ValidationError(
            "昵称不能包含空白、控制或不可见字符。",
            code="invalid_characters",
        )
    budget = 0
    for character in display:
        if _is_han(character):
            budget += 2
        else:
            budget += 1
    if budget > NICKNAME_BUDGET:
        raise ValidationError(
            "昵称最多 16 个单位，汉字每个计 2，其他安全字符每个计 1。",
            code="budget_exceeded",
        )
    normalized = normalized_display.casefold()
    return ValidatedNickname(display, normalized, budget)


def _is_safe_visible_text(value: str) -> bool:
    return bool(value) and all(
        not character.isspace() and unicodedata.category(character)[0] not in {"C", "Z"}
        for character in value
    )


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return any(
        start <= codepoint <= end
        for start, end in (
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x20000, 0x2FA1F),
            (0x30000, 0x323AF),
        )
    )
