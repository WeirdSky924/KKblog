from django import forms

from ..policies import CommentDeletionMode
from ..services.deletion import CommentDeletionError, normalize_deletion_reason


class CommentDeletionForm(forms.Form):
    mode = forms.ChoiceField(
        choices=tuple((mode.value, mode.value) for mode in CommentDeletionMode),
        widget=forms.HiddenInput,
    )
    reason = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "maxlength": 200,
                "placeholder": "可选，填写后会展示在相关通知中",
            }
        ),
    )

    def clean_reason(self) -> str:
        try:
            return normalize_deletion_reason(self.cleaned_data.get("reason")) or ""
        except CommentDeletionError as exc:
            raise forms.ValidationError(exc.safe_message, code=exc.code) from None
