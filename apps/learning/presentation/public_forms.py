from uuid import UUID

from django import forms

from apps.learning.public import (
    MAX_PUBLIC_PAGE_SIZE,
    MIN_PUBLIC_PAGE_SIZE,
    PublicQuestionBankFilterOptions,
    PublicQuestionBankFilters,
    PublicQuestionBankSort,
    QuestionType,
)


class PublicQuestionBankFilterForm(forms.Form):
    page = forms.IntegerField(
        required=False,
        min_value=1,
        widget=forms.HiddenInput(),
    )
    page_size = forms.IntegerField(
        required=False,
        min_value=MIN_PUBLIC_PAGE_SIZE,
        max_value=MAX_PUBLIC_PAGE_SIZE,
        widget=forms.HiddenInput(),
    )
    q = forms.CharField(label="搜索", required=False, max_length=100)
    tags = forms.MultipleChoiceField(
        label="标签",
        required=False,
        widget=forms.CheckboxSelectMultiple(),
    )
    question_types = forms.MultipleChoiceField(
        label="题型",
        required=False,
        choices=QuestionType.choices,
        widget=forms.CheckboxSelectMultiple(),
    )
    min_questions = forms.IntegerField(
        label="最少题数",
        required=False,
        min_value=1,
        max_value=2_000,
    )
    max_questions = forms.IntegerField(
        label="最多题数",
        required=False,
        min_value=1,
        max_value=2_000,
    )
    published_from = forms.DateField(
        label="开始日期",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    published_to = forms.DateField(
        label="结束日期",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    author = forms.ChoiceField(label="作者", required=False)
    sort = forms.ChoiceField(
        label="排序",
        required=False,
        choices=(
            (PublicQuestionBankSort.LATEST, "最新发布"),
            (PublicQuestionBankSort.MOST_COMPLETED, "最多答题"),
            (PublicQuestionBankSort.QUESTION_COUNT_DESC, "题量从多到少"),
            (PublicQuestionBankSort.QUESTION_COUNT_ASC, "题量从少到多"),
        ),
    )

    def __init__(
        self,
        *args,
        options: PublicQuestionBankFilterOptions,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["tags"].choices = [
            (str(tag.tag_id), tag.name) for tag in options.tags
        ]
        self.fields["author"].choices = [
            ("", "全部作者"),
            *(
                (str(author.account_id), author.display_name)
                for author in options.authors
            ),
        ]

    def clean(self):
        cleaned = super().clean()
        minimum = cleaned.get("min_questions")
        maximum = cleaned.get("max_questions")
        if minimum is not None and maximum is not None and minimum > maximum:
            self.add_error("max_questions", "最多题数不能小于最少题数。")
        published_from = cleaned.get("published_from")
        published_to = cleaned.get("published_to")
        if published_from and published_to:
            if published_from > published_to:
                self.add_error("published_to", "结束日期不能早于开始日期。")
            elif (published_to - published_from).days > 3_653:
                self.add_error("published_to", "发布时间范围不能超过十年。")
        return cleaned

    def filters(self, *, page: int) -> PublicQuestionBankFilters:
        if not self.is_valid():
            raise ValueError("Public question bank filter form is invalid")
        author_value = self.cleaned_data.get("author") or ""
        return PublicQuestionBankFilters(
            tag_ids=tuple(UUID(value) for value in self.cleaned_data["tags"]),
            question_types=tuple(self.cleaned_data["question_types"]),
            min_questions=self.cleaned_data.get("min_questions"),
            max_questions=self.cleaned_data.get("max_questions"),
            published_from=self.cleaned_data.get("published_from"),
            published_to=self.cleaned_data.get("published_to"),
            author_id=UUID(author_value) if author_value else None,
            query=self.cleaned_data.get("q", ""),
            sort=self.cleaned_data.get("sort") or PublicQuestionBankSort.LATEST,
            page=self.cleaned_data.get("page") or page,
            page_size=self.cleaned_data.get("page_size") or 20,
        )


__all__ = ["PublicQuestionBankFilterForm"]
