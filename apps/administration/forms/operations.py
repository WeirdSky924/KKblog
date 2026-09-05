from django import forms

TASK_STATES = (
    ("", "全部状态"),
    ("pending", "等待执行"),
    ("running", "进行中"),
    ("retry_wait", "等待重试"),
    ("succeeded", "已成功"),
    ("final_failed", "最终失败"),
)

EXPORT_SCOPES = (
    ("ALL", "全站"),
    ("AUTHOR", "指定作者"),
    ("SECTION", "指定分区"),
    ("ARTICLES", "指定文章"),
)


class TaskRunFilterForm(forms.Form):
    status = forms.ChoiceField(label="任务状态", required=False, choices=TASK_STATES)
    page = forms.IntegerField(required=False, min_value=1, initial=1)


class ExportRequestForm(forms.Form):
    scope = forms.ChoiceField(label="导出范围", choices=EXPORT_SCOPES)
    scope_author_id = forms.ChoiceField(label="作者", required=False)
    scope_section_id = forms.ChoiceField(label="分区", required=False)
    article_ids = forms.MultipleChoiceField(
        label="文章",
        required=False,
        widget=forms.SelectMultiple(attrs={"size": 8}),
    )

    def __init__(
        self,
        *args,
        author_choices=(),
        section_choices=(),
        article_choices=(),
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["scope_author_id"].choices = (("", "请选择作者"), *author_choices)
        self.fields["scope_section_id"].choices = (
            ("", "请选择分区"),
            *section_choices,
        )
        self.fields["article_ids"].choices = article_choices

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("scope")
        author_id = cleaned.get("scope_author_id") or ""
        section_id = cleaned.get("scope_section_id") or ""
        article_ids = cleaned.get("article_ids") or []
        valid = (
            scope == "ALL"
            and not author_id
            and not section_id
            and not article_ids
            or scope == "AUTHOR"
            and bool(author_id)
            and not section_id
            and not article_ids
            or scope == "SECTION"
            and not author_id
            and bool(section_id)
            and not article_ids
            or scope == "ARTICLES"
            and not author_id
            and not section_id
            and bool(article_ids)
        )
        if not valid:
            raise forms.ValidationError("导出范围与所选条件不匹配。")
        return cleaned


class ExportCancellationForm(forms.Form):
    job_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("cancel", "确认取消"),),
        widget=forms.HiddenInput,
    )


__all__ = ["ExportCancellationForm", "ExportRequestForm", "TaskRunFilterForm"]
