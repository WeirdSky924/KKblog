from django import forms

from apps.accounts.services.credentials import validate_password_strength


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
