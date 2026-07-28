from django import forms

from apps.accounts.public import ADMIN_ACCOUNT_STATUSES


def _boolean(value: str) -> bool:
    if value == "1":
        return True
    if value == "0":
        return False
    raise ValueError("Invalid boolean choice")


class AdminUserFilterForm(forms.Form):
    q = forms.CharField(
        label="邮箱或昵称",
        max_length=254,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "placeholder": "输入邮箱或昵称",
            }
        ),
    )
    status = forms.ChoiceField(
        label="账户状态",
        required=False,
        choices=(
            ("", "全部状态"),
            (ADMIN_ACCOUNT_STATUSES[0], "正常"),
            (ADMIN_ACCOUNT_STATUSES[1], "禁用"),
        ),
    )

    def clean_q(self) -> str:
        value = self.cleaned_data["q"].strip()
        if "\x00" in value:
            raise forms.ValidationError("搜索条件包含无效字符。")
        return value


class AccountRoleConfirmationForm(forms.Form):
    account_id = forms.UUIDField(widget=forms.HiddenInput)
    enabled = forms.TypedChoiceField(
        choices=(("1", "授予"), ("0", "撤销")),
        coerce=_boolean,
        widget=forms.HiddenInput,
    )
    confirm = forms.ChoiceField(
        choices=(("role", "确认角色变更"),),
        widget=forms.HiddenInput,
    )


class AccountStatusConfirmationForm(forms.Form):
    account_id = forms.UUIDField(widget=forms.HiddenInput)
    enabled = forms.TypedChoiceField(
        choices=(("1", "启用"), ("0", "禁用")),
        coerce=_boolean,
        widget=forms.HiddenInput,
    )
    confirm = forms.ChoiceField(
        choices=(("status", "确认账户状态变更"),),
        widget=forms.HiddenInput,
    )


class AccountDeletionConfirmationForm(forms.Form):
    account_id = forms.UUIDField(widget=forms.HiddenInput)
    expected_article_count = forms.IntegerField(
        min_value=0,
        max_value=1_000_000,
        widget=forms.HiddenInput,
    )
    confirm = forms.ChoiceField(
        choices=(("delete", "确认删除账户"),),
        widget=forms.HiddenInput,
    )


__all__ = [
    "AccountDeletionConfirmationForm",
    "AccountRoleConfirmationForm",
    "AccountStatusConfirmationForm",
    "AdminUserFilterForm",
]
