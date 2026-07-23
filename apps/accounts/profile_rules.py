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
    budget = 0
    for character in display:
        if _is_han(character):
            budget += 2
        elif character.isalpha():
            budget += 1
        else:
            raise ValidationError(
                "昵称只能使用文字，不能包含数字、空格或符号。",
                code="invalid_characters",
            )
    if budget > NICKNAME_BUDGET:
        raise ValidationError(
            "昵称最多 16 个英文单位，中文每个计 2。",
            code="budget_exceeded",
        )
    normalized = unicodedata.normalize("NFKC", display).casefold()
    return ValidatedNickname(display, normalized, budget)


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
