from django import forms

from apps.learning.contracts import (
    QUIZ_DURATION_OPTIONS,
    QuizAttemptMode,
    QuizAttemptSource,
)


class MultipleHiddenValueField(forms.Field):
    """Keep repeated hidden inputs as a list instead of stringifying them."""

    widget = forms.MultipleHiddenInput

    def to_python(self, value):
        if value in self.empty_values:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        return [value]


class QuizStartForm(forms.Form):
    bank_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_revision_id = forms.UUIDField(widget=forms.HiddenInput())
    source = forms.ChoiceField(
        choices=QuizAttemptSource.choices,
        widget=forms.HiddenInput(),
        initial=QuizAttemptSource.QUESTION_BANK,
    )
    mode = forms.ChoiceField(
        label="答题模式",
        choices=(
            (QuizAttemptMode.EXAM, "考试模式（提交整套后查看解析）"),
            (QuizAttemptMode.PRACTICE, "刷题模式（提交每题后查看解析）"),
        ),
        initial=QuizAttemptMode.EXAM,
        required=False,
    )
    question_types = forms.MultipleChoiceField(
        required=True, widget=forms.CheckboxSelectMultiple()
    )
    question_count = forms.IntegerField(label="题量", min_value=1, max_value=2_000)
    timed = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"role": "switch"})
    )
    duration_minutes = forms.TypedChoiceField(
        label="答题时长",
        required=False,
        choices=((value, f"{value} 分钟") for value in QUIZ_DURATION_OPTIONS),
        coerce=int,
    )
    random_questions = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
    )
    random_options = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
    )
    expected_source_keys = MultipleHiddenValueField(
        required=False, widget=forms.MultipleHiddenInput()
    )

    def __init__(self, *args, question_type_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["question_types"].choices = question_type_choices

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        cleaned["mode"] = cleaned.get("mode") or QuizAttemptMode.EXAM
        if cleaned.get("timed") and not cleaned.get("duration_minutes"):
            self.add_error("duration_minutes", "请选择答题时长。")
        if not cleaned.get("timed"):
            cleaned["duration_minutes"] = None
        if cleaned.get("source") not in QuizAttemptSource.values:
            self.add_error("source", "题库来源不合法。")
        return cleaned

    def source_keys(self) -> tuple[str, ...]:
        return tuple(self.cleaned_data.get("expected_source_keys") or ())


class QuizResponseForm(forms.Form):
    attempt_id = forms.UUIDField(widget=forms.HiddenInput())
    response_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)
    request_id = forms.CharField(widget=forms.HiddenInput(), max_length=128)
    answer = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    question_type = forms.CharField(widget=forms.HiddenInput())


class QuizSubmitForm(forms.Form):
    attempt_id = forms.UUIDField(widget=forms.HiddenInput())
    request_id = forms.CharField(widget=forms.HiddenInput(), max_length=128)


class QuizAssessmentForm(forms.Form):
    attempt_id = forms.UUIDField(widget=forms.HiddenInput())
    response_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)
    request_id = forms.CharField(widget=forms.HiddenInput(), max_length=128)
    self_assessment = forms.ChoiceField(
        choices=(
            ("MASTERED", "已掌握"),
            ("NOT_MASTERED", "未掌握"),
        )
    )


__all__ = [
    "QuizAssessmentForm",
    "QuizResponseForm",
    "QuizStartForm",
    "QuizSubmitForm",
]
