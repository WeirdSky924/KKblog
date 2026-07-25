from django import forms

from ..models import ReportReason


class ReportForm(forms.Form):
    reason = forms.ChoiceField(
        label="举报理由",
        choices=(("", "请选择举报理由"), *ReportReason.choices),
        error_messages={
            "required": "请选择举报理由。",
            "invalid_choice": "请选择有效的举报理由。",
        },
    )
    description = forms.CharField(
        label="补充说明（可选）",
        required=False,
        max_length=200,
        strip=True,
        error_messages={"max_length": "补充说明不能超过 200 字。"},
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "maxlength": 200,
                "placeholder": "补充需要管理员了解的信息",
            }
        ),
    )
    evidence_ref_1 = forms.CharField(required=False, max_length=2048)
    evidence_ref_2 = forms.CharField(required=False, max_length=2048)
    evidence_ref_3 = forms.CharField(required=False, max_length=2048)

    def __init__(self, *args, comment_id: str, **kwargs) -> None:
        kwargs.setdefault("auto_id", f"comment-report-{comment_id}-%s")
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        refs = tuple(
            value
            for name in ("evidence_ref_1", "evidence_ref_2", "evidence_ref_3")
            if (value := cleaned.get(name))
        )
        if len(set(refs)) != len(refs):
            raise forms.ValidationError("证据图片不能重复。")
        cleaned["evidence_refs"] = refs
        return cleaned

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        if not self.is_valid():
            return ()
        return self.cleaned_data["evidence_refs"]


class ArticleAppealForm(forms.Form):
    statement = forms.CharField(
        required=False,
        max_length=200,
        strip=True,
        error_messages={"max_length": "申诉说明不能超过 200 字。"},
    )
    evidence_ref_1 = forms.CharField(required=False, max_length=2048)
    evidence_ref_2 = forms.CharField(required=False, max_length=2048)
    evidence_ref_3 = forms.CharField(required=False, max_length=2048)

    def clean(self):
        cleaned = super().clean()
        refs = tuple(
            value
            for name in ("evidence_ref_1", "evidence_ref_2", "evidence_ref_3")
            if (value := cleaned.get(name))
        )
        if len(set(refs)) != len(refs):
            raise forms.ValidationError("申诉证据图片不能重复。")
        cleaned["evidence_refs"] = refs
        return cleaned

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        if not self.is_valid():
            return ()
        return self.cleaned_data["evidence_refs"]
