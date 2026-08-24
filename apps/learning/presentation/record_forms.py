import json

from django import forms

from apps.learning.contracts import (
    QuizAttemptSource,
    QuizAttemptStatus,
    QuizMasteryStatus,
)


class WrongQuestionFilterForm(forms.Form):
    mastery_status = forms.ChoiceField(
        required=False,
        choices=(
            (QuizMasteryStatus.TO_REVIEW, "待复习"),
            (QuizMasteryStatus.MASTERED, "已掌握"),
            ("ALL", "全部"),
        ),
        initial=QuizMasteryStatus.TO_REVIEW,
        label="掌握状态",
    )
    bank_id = forms.ChoiceField(required=False, label="题库")
    page_size = forms.TypedChoiceField(
        required=False,
        choices=((20, "每页 20 条"), (50, "每页 50 条")),
        coerce=int,
        initial=20,
        label="每页数量",
    )

    def __init__(self, *args, bank_options=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bank_id"].choices = (("", "全部题库"),) + tuple(
            (str(item.bank_id), f"{item.bank_title}（{item.item_count}）")
            for item in bank_options
            if item.bank_id is not None
        )


class QuizRecordFilterForm(forms.Form):
    bank_id = forms.ChoiceField(required=False, label="题库")
    source = forms.ChoiceField(
        required=False,
        choices=(
            ("", "全部来源"),
            (QuizAttemptSource.QUESTION_BANK, "题库"),
            (QuizAttemptSource.WRONG_QUESTIONS, "错题本"),
        ),
        label="来源",
    )
    status = forms.ChoiceField(
        required=False,
        choices=(
            ("", "全部状态"),
            (QuizAttemptStatus.IN_PROGRESS, "进行中"),
            (QuizAttemptStatus.SUBMITTED, "已提交"),
        ),
        label="完成状态",
    )
    started_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="开始日期",
    )
    started_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="结束日期",
    )
    page_size = forms.TypedChoiceField(
        required=False,
        choices=((20, "每页 20 条"), (50, "每页 50 条")),
        coerce=int,
        initial=20,
        label="每页数量",
    )

    def __init__(self, *args, bank_options=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bank_id"].choices = (("", "全部题库"),) + tuple(
            (str(item.bank_id), f"{item.bank_title}（{item.item_count}）")
            for item in bank_options
        )

    def clean(self):
        cleaned = super().clean()
        started_from = cleaned.get("started_from")
        started_to = cleaned.get("started_to")
        if started_from and started_to and started_from > started_to:
            self.add_error("started_to", "结束日期不能早于开始日期。")
        return cleaned


class WrongQuestionMasteryForm(forms.Form):
    wrong_question_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput())
    mastery_status = forms.ChoiceField(
        choices=QuizMasteryStatus.choices,
        widget=forms.HiddenInput(),
    )


class QuizRecordActionForm(forms.Form):
    attempt_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput())


class QuizRecordBatchForm(forms.Form):
    expected_count = forms.IntegerField(min_value=1, max_value=50)
    expected_versions = forms.CharField(widget=forms.HiddenInput())

    def versions(self) -> dict[str, int]:
        try:
            value = json.loads(self.cleaned_data["expected_versions"])
        except (TypeError, ValueError):
            raise forms.ValidationError("版本参数不合法。") from None
        if not isinstance(value, dict):
            raise forms.ValidationError("版本参数不合法。")
        try:
            return {str(key): int(version) for key, version in value.items()}
        except (TypeError, ValueError):
            raise forms.ValidationError("版本参数不合法。") from None


class QuizRecordClearForm(forms.Form):
    expected_count = forms.IntegerField(min_value=0)


__all__ = [
    "QuizRecordActionForm",
    "QuizRecordBatchForm",
    "QuizRecordClearForm",
    "QuizRecordFilterForm",
    "WrongQuestionFilterForm",
    "WrongQuestionMasteryForm",
]
