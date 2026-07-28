from pathlib import PurePath

from django import forms


class ArticleCommentsToggleForm(forms.Form):
    enabled = forms.BooleanField(required=False, label="允许新评论")


class ManagedCommentDeleteForm(forms.Form):
    confirm = forms.ChoiceField(
        choices=(("delete", "确认删除"),),
        widget=forms.HiddenInput,
    )


class ImportUploadForm(forms.Form):
    source = forms.FileField(
        label="Markdown 或 ZIP",
        widget=forms.ClearableFileInput(
            attrs={"accept": ".md,.zip", "data-error-focus": ""}
        ),
    )

    def clean_source(self):
        upload = self.cleaned_data["source"]
        suffix = PurePath(upload.name).suffix.casefold()
        if suffix not in {".md", ".zip"}:
            raise forms.ValidationError("请选择 .md 或 .zip 文件。")
        upload.source_kind = "MARKDOWN" if suffix == ".md" else "ZIP"
        return upload


class ImportDecisionForm(forms.Form):
    expected_preview_version = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput,
    )
    included = forms.BooleanField(required=False, label="导入此项")
    decision = forms.ChoiceField(
        label="处理方式",
        choices=(
            ("SKIP", "跳过"),
            ("UPDATE", "更新现有文章"),
            ("CREATE", "创建文章"),
        ),
    )
    section_id = forms.ChoiceField(required=False, label="分区")
    tag_ids = forms.MultipleChoiceField(
        required=False,
        label="已有标签",
        widget=forms.CheckboxSelectMultiple,
    )
    proposed_tag_names = forms.CharField(
        required=False,
        max_length=500,
        label="新标签",
        help_text="使用中文逗号或英文逗号分隔。",
    )

    def __init__(
        self,
        *args,
        sections=(),
        tags=(),
        allowed_decisions=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fields["section_id"].choices = (("", "未知分区"),) + tuple(
            (str(item.section_id), item.name) for item in sections
        )
        self.fields["tag_ids"].choices = tuple(
            (str(item.tag_id), item.name) for item in tags
        )
        if allowed_decisions is not None:
            labels = dict(self.fields["decision"].choices)
            self.fields["decision"].choices = tuple(
                (value, labels[value]) for value in allowed_decisions
            )

    def clean(self):
        values = super().clean()
        if not values.get("included"):
            values["decision"] = "SKIP"
        raw_names = values.get("proposed_tag_names", "")
        names = tuple(
            dict.fromkeys(
                value.strip()
                for value in raw_names.replace("，", ",").split(",")
                if value.strip()
            )
        )
        if len(names) > 10 or any(len(value) > 50 for value in names):
            self.add_error("proposed_tag_names", "新标签最多 10 个，每个不超过 50 字。")
        values["proposed_tag_names"] = names
        return values


class ImportConfirmForm(forms.Form):
    expected_preview_version = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput,
    )
