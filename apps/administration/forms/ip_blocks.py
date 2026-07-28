from django import forms


class IpBlockForm(forms.Form):
    address = forms.GenericIPAddressField(
        label="IP 地址",
        protocol="both",
        unpack_ipv4=True,
        error_messages={"invalid": "请输入有效的 IP 地址。"},
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "inputmode": "text",
                "placeholder": "IPv4 或 IPv6",
            }
        ),
    )
    note = forms.CharField(
        label="备注",
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean_note(self) -> str:
        value = self.cleaned_data["note"].strip()
        if "\x00" in value:
            raise forms.ValidationError("备注包含无效字符。")
        return value


class IpBlockConfirmationForm(IpBlockForm):
    address = forms.GenericIPAddressField(
        protocol="both", unpack_ipv4=True, widget=forms.HiddenInput
    )
    note = forms.CharField(max_length=500, required=False, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("block", "确认封禁"),),
        widget=forms.HiddenInput,
    )


class IpUnblockConfirmationForm(forms.Form):
    block_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("unblock", "确认解除"),),
        widget=forms.HiddenInput,
    )


class IpRestrictionForm(forms.Form):
    address = forms.GenericIPAddressField(
        label="IP 地址",
        protocol="both",
        unpack_ipv4=True,
        error_messages={"invalid": "请输入有效的 IP 地址。"},
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "inputmode": "text",
                "placeholder": "IPv4 或 IPv6",
            }
        ),
    )


class IpRestrictionConfirmationForm(IpRestrictionForm):
    address = forms.GenericIPAddressField(
        protocol="both",
        unpack_ipv4=True,
        widget=forms.HiddenInput,
    )
    confirm = forms.ChoiceField(
        choices=(("clear_ip_restriction", "确认清除"),),
        widget=forms.HiddenInput,
    )


__all__ = [
    "IpBlockConfirmationForm",
    "IpBlockForm",
    "IpRestrictionConfirmationForm",
    "IpRestrictionForm",
    "IpUnblockConfirmationForm",
]
