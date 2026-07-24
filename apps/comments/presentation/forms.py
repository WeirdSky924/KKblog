from django import forms


class TopLevelCommentForm(forms.Form):
    body = forms.CharField(
        min_length=1,
        max_length=100,
        strip=True,
        error_messages={
            "required": "请输入评论内容。",
            "min_length": "请输入评论内容。",
            "max_length": "评论正文不能超过 100 字。",
        },
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "maxlength": 100,
                "placeholder": "写下你的评论",
                "aria-describedby": "comment-body-help",
            }
        ),
    )
    image_ref_1 = forms.CharField(required=False, max_length=2_048)
    image_ref_2 = forms.CharField(required=False, max_length=2_048)
    image_ref_3 = forms.CharField(required=False, max_length=2_048)

    def clean(self):
        cleaned = super().clean()
        refs = tuple(
            value
            for name in ("image_ref_1", "image_ref_2", "image_ref_3")
            if (value := cleaned.get(name))
        )
        if len(set(refs)) != len(refs):
            raise forms.ValidationError("评论图片不能重复。")
        cleaned["image_refs"] = refs
        return cleaned

    @property
    def image_refs(self) -> tuple[str, ...]:
        if not self.is_valid():
            return ()
        return self.cleaned_data["image_refs"]
