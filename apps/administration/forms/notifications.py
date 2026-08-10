from django import forms

from apps.notifications.public import (
    BROADCAST_MESSAGE_MAX_LENGTH,
    BroadcastError,
    normalize_broadcast_message_markdown,
)


def _plain_text(value: str, *, single_line: bool = False) -> str:
    normalized = value.strip()
    if (
        not normalized
        or "\x00" in normalized
        or "<" in normalized
        or ">" in normalized
        or "://" in normalized
        or (single_line and ("\n" in normalized or "\r" in normalized))
        or any(
            not character.isprintable() and character not in "\n\t"
            for character in normalized
        )
    ):
        raise forms.ValidationError("请输入安全的纯文本内容。")
    return normalized


class BroadcastForm(forms.Form):
    headline = forms.CharField(
        label="通知标题",
        max_length=100,
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    message = forms.CharField(
        label="通知内容（Markdown）",
        max_length=BROADCAST_MESSAGE_MAX_LENGTH,
        widget=forms.Textarea(attrs={"rows": 10}),
    )

    def clean_headline(self) -> str:
        return _plain_text(self.cleaned_data["headline"], single_line=True)

    def clean_message(self) -> str:
        try:
            return normalize_broadcast_message_markdown(self.cleaned_data["message"])
        except BroadcastError:
            raise forms.ValidationError("请输入有效的 Markdown 通知内容。") from None


class BroadcastConfirmationForm(BroadcastForm):
    headline = forms.CharField(max_length=100, widget=forms.HiddenInput)
    message = forms.CharField(
        max_length=BROADCAST_MESSAGE_MAX_LENGTH,
        widget=forms.HiddenInput,
    )
    confirm = forms.ChoiceField(
        choices=(("broadcast", "确认群发"),),
        widget=forms.HiddenInput,
    )


class BroadcastVisibilityForm(forms.Form):
    notification_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(widget=forms.HiddenInput)

    def __init__(self, *args, operation: str, **kwargs):
        super().__init__(*args, **kwargs)
        if operation not in {"hide", "restore", "delete"}:
            raise ValueError("Invalid broadcast visibility operation")
        self.fields["confirm"].choices = ((operation, operation),)
