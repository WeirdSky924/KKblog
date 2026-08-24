import unicodedata

from django.db import IntegrityError
from django.db.models import Case, F, IntegerField, Value, When
from django.utils import timezone

from apps.learning.contracts import LearningCommandError
from apps.learning.models import (
    QuestionBankSeries,
    QuestionBankTag,
    QuestionBankTagAssignment,
)


def _tag_identity(value: object) -> tuple[str, str]:
    if not isinstance(value, str):
        raise LearningCommandError("learning.bank_tag_invalid.v1", "题库标签不合法。")
    display = " ".join(unicodedata.normalize("NFKC", value).split())
    if (
        not 1 <= len(display) <= 80
        or "\x00" in display
        or any(not character.isprintable() for character in display)
    ):
        raise LearningCommandError("learning.bank_tag_invalid.v1", "题库标签不合法。")
    return display.casefold(), display


def normalized_question_bank_tags(names: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(names, tuple):
        raise LearningCommandError("learning.bank_tag_invalid.v1", "题库标签不合法。")
    normalized = {}
    for name in names:
        identity, display = _tag_identity(name)
        normalized.setdefault(identity, display)
    if not 1 <= len(normalized) <= 20:
        raise LearningCommandError(
            "learning.bank_tag_invalid.v1", "题库标签数量不合法。"
        )
    return tuple(sorted(normalized.items()))


def _tag(*, normalized_name: str, display_name: str, source: str):
    try:
        tag, created = QuestionBankTag.objects.get_or_create(
            normalized_name=normalized_name,
            defaults={"display_name": display_name, "source": source},
        )
    except IntegrityError:
        tag = QuestionBankTag.objects.get(normalized_name=normalized_name)
        created = False
    if tag.status != QuestionBankTag.Status.ACTIVE:
        raise LearningCommandError(
            "learning.bank_tag_conflict.v1", "题库标签当前不可用。"
        )
    return tag, created


def replace_question_bank_tags(
    *,
    series: QuestionBankSeries,
    names: tuple[str, ...],
    source: str,
) -> None:
    if not isinstance(series, QuestionBankSeries) or source not in {
        QuestionBankTag.Source.AGENT,
        QuestionBankTag.Source.OWNER,
        QuestionBankTag.Source.ADMINISTRATOR,
    }:
        raise LearningCommandError("learning.bank_tag_invalid.v1", "题库标签不合法。")
    desired = dict(normalized_question_bank_tags(names))
    current = {
        assignment.tag.normalized_name: assignment
        for assignment in series.tag_assignments.select_related("tag").all()
    }
    removed = [current[name] for name in sorted(set(current) - set(desired))]
    for assignment in removed:
        tag_id = assignment.tag_id
        assignment.delete()
        QuestionBankTag.objects.filter(pk=tag_id).update(
            usage_count=Case(
                When(usage_count__gt=0, then=F("usage_count") - 1),
                default=Value(0),
                output_field=IntegerField(),
            ),
            updated_at=timezone.now(),
        )
    for normalized_name in sorted(set(desired) - set(current)):
        tag, created = _tag(
            normalized_name=normalized_name,
            display_name=desired[normalized_name],
            source=source,
        )
        QuestionBankTagAssignment.objects.create(series=series, tag=tag)
        updated = QuestionBankTag.objects.filter(
            pk=tag.pk,
            status=QuestionBankTag.Status.ACTIVE,
        ).update(
            usage_count=F("usage_count") + 1,
            source=(source if created else QuestionBankTag.Source.REUSED),
            updated_at=timezone.now(),
        )
        if updated != 1:
            raise LearningCommandError(
                "learning.bank_tag_conflict.v1", "题库标签当前不可用。"
            )


__all__ = ["normalized_question_bank_tags", "replace_question_bank_tags"]
