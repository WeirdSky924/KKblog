import re
from uuid import uuid4

from django import forms

from apps.learning.contracts import (
    CURRENT_UPLOAD_STATEMENT_VERSION,
    GenerationQuestionTypes,
    QuestionContentDraft,
    QuestionOptionDraft,
)
from apps.learning.services.appeals import MAX_APPEAL_MARKDOWN_LENGTH


class KnowledgeDocumentSubmitForm(forms.Form):
    source_asset_id = forms.CharField(widget=forms.HiddenInput())
    statement_version = forms.CharField(
        initial=CURRENT_UPLOAD_STATEMENT_VERSION,
        widget=forms.HiddenInput(),
    )
    accepted = forms.BooleanField(
        required=True,
        label=(
            "我确认有权上传并允许站点配置的模型服务处理该文档，"
            "理解生成的题库、答案与解析可能公开，且不会上传无权处理的隐私、机密或侵权内容。"
        ),
        error_messages={"required": "必须明确同意当前上传声明。"},
    )
    idempotency_key = forms.CharField(
        initial=lambda: f"knowledge:{uuid4()}",
        widget=forms.HiddenInput(),
    )


class KnowledgeDocumentActionForm(forms.Form):
    document_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput())


class QuestionBankGenerationForm(forms.Form):
    document_id = forms.UUIDField(widget=forms.HiddenInput())
    base_title = forms.CharField(label="题库标题", max_length=160)
    description = forms.CharField(
        label="简介",
        max_length=1_000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    single_choice = forms.BooleanField(
        label="单选题",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
    )
    multiple_choice = forms.BooleanField(
        label="多选题",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
    )
    true_false = forms.BooleanField(
        label="判断题",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
    )
    short_answer = forms.BooleanField(
        label="简答题",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
    )
    idempotency_key = forms.CharField(
        initial=lambda: f"generation:{uuid4()}",
        widget=forms.HiddenInput(),
    )

    def clean(self):
        cleaned = super().clean()
        if not any(
            cleaned.get(field)
            for field in (
                "single_choice",
                "multiple_choice",
                "true_false",
                "short_answer",
            )
        ):
            raise forms.ValidationError("至少选择一种题型。")
        return cleaned

    def question_types(self) -> GenerationQuestionTypes:
        if not self.is_valid():
            raise ValueError("Question bank generation form is invalid")
        return GenerationQuestionTypes(
            single_choice=self.cleaned_data["single_choice"],
            multiple_choice=self.cleaned_data["multiple_choice"],
            true_false=self.cleaned_data["true_false"],
            short_answer=self.cleaned_data["short_answer"],
        )


class QuestionBankMetadataForm(forms.Form):
    series_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput())
    base_title = forms.CharField(label="题库标题", max_length=160)
    description = forms.CharField(
        label="简介",
        max_length=1_000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    tags = forms.CharField(
        label="标签",
        max_length=1_619,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def clean(self):
        cleaned = super().clean()
        values = tuple(
            line.strip()
            for line in cleaned.get("tags", "").replace(",", "\n").splitlines()
            if line.strip()
        )
        if not values:
            self.add_error("tags", "至少保留一个标签。")
        cleaned["parsed_tags"] = values
        return cleaned

    def tag_names(self) -> tuple[str, ...]:
        if not self.is_valid():
            raise ValueError("Question bank metadata form is invalid")
        return self.cleaned_data["parsed_tags"]


class QuestionBankRetryForm(forms.Form):
    series_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput())
    idempotency_key = forms.CharField(
        initial=lambda: f"generation-retry:{uuid4()}",
        widget=forms.HiddenInput(),
    )


class QuestionEditForm(forms.Form):
    bank_id = forms.UUIDField(widget=forms.HiddenInput())
    logical_id = forms.CharField(max_length=64, widget=forms.HiddenInput())
    expected_bank_version = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )
    stem_markdown = forms.CharField(
        label="题干",
        max_length=8_000,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    options_text = forms.CharField(
        label="选项",
        required=False,
        max_length=4_600,
        widget=forms.Textarea(attrs={"rows": 6, "placeholder": "a | 选项内容"}),
    )
    correct_option_ids = forms.CharField(
        label="正确选项",
        required=False,
        max_length=520,
    )
    boolean_answer = forms.ChoiceField(
        label="判断答案",
        required=False,
        choices=(("", "未选择"), ("true", "正确"), ("false", "错误")),
    )
    reference_answer = forms.CharField(
        label="参考答案",
        required=False,
        max_length=4_000,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    scoring_points = forms.CharField(
        label="评分要点",
        required=False,
        max_length=10_019,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    explanation_markdown = forms.CharField(
        label="解析",
        max_length=8_000,
        widget=forms.Textarea(attrs={"rows": 5}),
    )
    revision_reason = forms.CharField(label="修订原因", max_length=500)

    def __init__(self, *args, question_type: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.question_type = question_type

    def clean(self):
        cleaned = super().clean()
        option_lines = [
            line.strip()
            for line in cleaned.get("options_text", "").splitlines()
            if line.strip()
        ]
        options = []
        for line in option_lines:
            identity, separator, text = line.partition("|")
            if not separator or not identity.strip() or not text.strip():
                self.add_error("options_text", "选项格式不合法。")
                continue
            options.append(QuestionOptionDraft(identity.strip(), text.strip()))
        correct_ids = tuple(
            value
            for value in re.split(r"[\s,]+", cleaned.get("correct_option_ids", ""))
            if value
        )
        boolean_value = cleaned.get("boolean_answer", "")
        boolean_answer = (
            True
            if boolean_value == "true"
            else False
            if boolean_value == "false"
            else None
        )
        scoring_points = tuple(
            line.strip()
            for line in cleaned.get("scoring_points", "").splitlines()
            if line.strip()
        )
        if self.question_type in {"SINGLE_CHOICE", "MULTIPLE_CHOICE"}:
            if not options:
                self.add_error("options_text", "选择题需要选项。")
            if not correct_ids:
                self.add_error("correct_option_ids", "请选择正确选项。")
        elif self.question_type == "TRUE_FALSE" and boolean_answer is None:
            self.add_error("boolean_answer", "请选择判断答案。")
        elif self.question_type == "SHORT_ANSWER":
            if not cleaned.get("reference_answer", "").strip():
                self.add_error("reference_answer", "请输入参考答案。")
            if not scoring_points:
                self.add_error("scoring_points", "请输入评分要点。")
        cleaned["parsed_options"] = tuple(options)
        cleaned["parsed_correct_ids"] = correct_ids
        cleaned["parsed_boolean_answer"] = boolean_answer
        cleaned["parsed_scoring_points"] = scoring_points
        return cleaned

    def content_draft(self) -> QuestionContentDraft:
        if not self.is_valid():
            raise ValueError("Question edit form is invalid")
        return QuestionContentDraft(
            logical_id=self.cleaned_data["logical_id"],
            stem_markdown=self.cleaned_data["stem_markdown"],
            options=self.cleaned_data["parsed_options"],
            correct_option_ids=self.cleaned_data["parsed_correct_ids"],
            boolean_answer=self.cleaned_data["parsed_boolean_answer"],
            reference_answer=self.cleaned_data["reference_answer"],
            scoring_points=self.cleaned_data["parsed_scoring_points"],
            explanation_markdown=self.cleaned_data["explanation_markdown"],
        )


class LearningAppealForm(KnowledgeDocumentActionForm):
    reason_markdown = forms.CharField(
        label="申诉理由",
        max_length=MAX_APPEAL_MARKDOWN_LENGTH,
        widget=forms.Textarea(
            attrs={
                "rows": 8,
                "placeholder": "说明希望重新审核的原因。",
            }
        ),
    )


class LearningAppealWithdrawForm(forms.Form):
    appeal_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput())


__all__ = [
    "KnowledgeDocumentActionForm",
    "KnowledgeDocumentSubmitForm",
    "LearningAppealForm",
    "LearningAppealWithdrawForm",
    "QuestionBankGenerationForm",
    "QuestionBankMetadataForm",
    "QuestionBankRetryForm",
    "QuestionEditForm",
]
