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

    def __init__(self, *args, noun: str = "评论", **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if noun not in {"评论", "留言"}:
            raise ValueError("Unsupported comment noun")
        field = self.fields["body"]
        field.label = f"{noun}内容"
        field.widget.attrs["placeholder"] = f"写下{noun}"
        field.error_messages.update(
            {
                "required": f"请输入{noun}内容。",
                "min_length": f"请输入{noun}内容。",
                "max_length": f"{noun}正文不能超过 100 字。",
            }
        )

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


class ReplyCommentForm(forms.Form):
    body = forms.CharField(
        min_length=1,
        max_length=100,
        strip=True,
        label="回复内容",
        error_messages={
            "required": "请输入回复内容。",
            "min_length": "请输入回复内容。",
            "max_length": "回复正文不能超过 100 字。",
        },
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "maxlength": 100,
                "placeholder": "写下回复",
            }
        ),
    )
