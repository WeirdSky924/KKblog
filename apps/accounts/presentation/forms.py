from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.profile_rules import validate_nickname
from apps.accounts.services.credentials import validate_password_strength
from apps.core.ids import normalize_ulid


class RegistrationCodeForm(forms.Form):
    invite_code = forms.CharField(label="邀请码", max_length=16, required=False)
    email = forms.EmailField(
        label="邮箱",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )


class RegistrationForm(RegistrationCodeForm):
    code = forms.RegexField(
        label="邮箱验证码",
        regex=r"[0-9]{6}",
        max_length=6,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}
        ),
    )
    password = forms.CharField(
        label="密码",
        min_length=8,
        validators=[validate_password_strength],
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    remember = forms.BooleanField(label="在此设备保持登录 30 天", required=False)


class PasswordLoginForm(forms.Form):
    email = forms.EmailField(
        label="邮箱",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    password = forms.CharField(
        label="密码",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    remember = forms.BooleanField(label="在此设备保持登录 30 天", required=False)


class LoginCodeRequestForm(forms.Form):
    email = forms.EmailField(
        label="邮箱",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )


class CodeLoginForm(LoginCodeRequestForm):
    code = forms.RegexField(
        label="邮箱验证码",
        regex=r"[0-9]{6}",
        max_length=6,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}
        ),
    )
    remember = forms.BooleanField(label="在此设备保持登录 30 天", required=False)


class PasswordResetCodeForm(forms.Form):
    email = forms.EmailField(
        label="已绑定邮箱",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )


class PasswordResetForm(PasswordResetCodeForm):
    code = forms.RegexField(
        label="邮箱验证码",
        regex=r"[0-9]{6}",
        max_length=6,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}
        ),
    )
    new_password = forms.CharField(
        label="新密码",
        min_length=8,
        validators=[validate_password_strength],
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )


class ChangePasswordForm(forms.Form):
    current_password = forms.CharField(
        label="当前密码",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    new_password = forms.CharField(
        label="新密码",
        min_length=8,
        validators=[validate_password_strength],
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )


class NewEmailCodeForm(forms.Form):
    new_email = forms.EmailField(
        label="新邮箱",
        max_length=254,
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )


class ChangeEmailForm(NewEmailCodeForm):
    code = forms.RegexField(
        label="新邮箱验证码",
        regex=r"[0-9]{6}",
        max_length=6,
        widget=forms.TextInput(
            attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}
        ),
    )


class RevokeSessionForm(forms.Form):
    session_id = forms.UUIDField(widget=forms.HiddenInput)


class RevokeAllSessionsForm(forms.Form):
    confirm = forms.ChoiceField(
        choices=(("all_devices", "退出所有设备"),),
        widget=forms.HiddenInput,
    )


class ProfileForm(forms.Form):
    nickname = forms.CharField(
        label="昵称",
        max_length=16,
        required=False,
        help_text="中文每个计 2，其他文字每个计 1，总计不超过 16。",
        widget=forms.TextInput(attrs={"autocomplete": "nickname"}),
    )
    avatar_asset_id = forms.CharField(
        required=False,
        max_length=26,
        widget=forms.HiddenInput,
    )

    def clean_nickname(self):
        try:
            return validate_nickname(self.cleaned_data["nickname"]).display
        except ValidationError as exc:
            raise forms.ValidationError(exc.messages) from None

    def clean_avatar_asset_id(self):
        value = self.cleaned_data["avatar_asset_id"]
        if not value:
            return None
        try:
            return normalize_ulid(value)
        except (TypeError, ValueError):
            raise forms.ValidationError("头像引用无效，请重新上传。") from None


class ThemeRadioSelect(forms.RadioSelect):
    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        option["attrs"]["data-theme-value"] = str(value)
        return option


class ThemeForm(forms.Form):
    theme = forms.ChoiceField(
        label="账户主题",
        choices=(
            ("light", "浅色"),
            ("dark", "深色"),
            ("eye-care", "护眼"),
        ),
        widget=ThemeRadioSelect,
    )


class AuthorPreferenceForm(forms.Form):
    auto_republish_enabled = forms.BooleanField(
        label="自动发布已保存的文章修改",
        required=False,
        help_text="仅用于已发布文章的普通编辑；首次发布和历史版本恢复仍需终稿审查。",
    )
