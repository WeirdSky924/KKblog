from django import forms

from apps.accounts.public import (
    MAX_VERIFICATION_EMAIL_TEMPLATE_BYTES,
    EmailTemplateError,
    validate_verification_email_template,
)
from apps.navigation.public import (
    DEFAULT_FOCUS_IDLE_TIMEOUT_MINUTES,
    DEFAULT_FOCUS_MANUAL_PAUSE_LIMIT,
    MAX_FOCUS_IDLE_TIMEOUT_MINUTES,
    MAX_FOCUS_MANUAL_PAUSE_LIMIT,
    MIN_FOCUS_IDLE_TIMEOUT_MINUTES,
    MIN_FOCUS_MANUAL_PAUSE_LIMIT,
    SITE_MAX_ARTICLE_BODY_BYTES,
    SITE_MIN_ARTICLE_BODY_BYTES,
    STATIC_PAGE_FORMAT_CHOICES,
    STATIC_PAGE_TYPE_CHOICES,
)


class SiteConfigurationForm(forms.Form):
    site_name = forms.CharField(label="站点名称", max_length=100)
    site_description = forms.CharField(
        label="站点描述",
        max_length=200,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    copyright_text = forms.CharField(label="版权信息", max_length=200, required=False)
    registration_enabled = forms.BooleanField(
        label="开放直接注册",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
    )
    article_body_max_bytes = forms.IntegerField(
        label="正文上限（字节）",
        min_value=SITE_MIN_ARTICLE_BODY_BYTES,
        max_value=SITE_MAX_ARTICLE_BODY_BYTES,
    )
    logo_asset_id = forms.CharField(
        label="Logo",
        max_length=26,
        required=False,
        widget=forms.HiddenInput,
    )
    hero_asset_id = forms.CharField(
        label="首页主视觉",
        max_length=26,
        required=False,
        widget=forms.HiddenInput,
    )
    backup_destination = forms.ChoiceField(
        label="备份目标",
        choices=(("local", "local（本机）"),),
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


class VerificationEmailTemplateForm(forms.Form):
    template_file = forms.FileField(
        label="HTML 模板文件",
        required=False,
        widget=forms.FileInput(attrs={"accept": ".html,.htm,text/html"}),
    )
    mode = forms.ChoiceField(
        choices=(("upload", "上传"), ("reset", "恢复默认")),
        widget=forms.HiddenInput,
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    def clean_template_file(self):
        upload = self.cleaned_data.get("template_file")
        if upload is None:
            return None
        if upload.size > MAX_VERIFICATION_EMAIL_TEMPLATE_BYTES:
            raise forms.ValidationError("邮件模板不能超过 48 KiB。")
        if not upload.name.lower().endswith((".html", ".htm")):
            raise forms.ValidationError("请选择 .html 或 .htm 文件。")
        if upload.content_type not in {"text/html", "application/xhtml+xml"}:
            raise forms.ValidationError("邮件模板的文件类型必须是 HTML。")
        try:
            source = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise forms.ValidationError("邮件模板必须使用 UTF-8 编码。") from None
        try:
            return validate_verification_email_template(source)
        except EmailTemplateError as error:
            raise forms.ValidationError(str(error)) from None

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode")
        upload = cleaned.get("template_file")
        if mode == "upload" and upload is None and "template_file" not in self.errors:
            self.add_error("template_file", "请选择需要上传的 HTML 模板。")
        if mode == "reset" and upload is not None:
            self.add_error("template_file", "恢复默认模板时不需要选择文件。")
        cleaned["template_source"] = upload if mode == "upload" else ""
        return cleaned


class StaticPageForm(forms.Form):
    page_type = forms.ChoiceField(
        choices=STATIC_PAGE_TYPE_CHOICES,
        widget=forms.HiddenInput,
    )
    content_format = forms.ChoiceField(
        label="编辑格式",
        choices=STATIC_PAGE_FORMAT_CHOICES,
    )
    source = forms.CharField(
        label="页面正文",
        required=False,
        widget=forms.Textarea(attrs={"rows": 8}),
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


class FriendLinkForm(forms.Form):
    link_id = forms.CharField(widget=forms.HiddenInput, required=False)
    name = forms.CharField(
        label="站点名称",
        max_length=80,
        widget=forms.TextInput(attrs={"autocomplete": "off", "autofocus": True}),
    )
    url = forms.URLField(
        label="HTTPS 地址",
        max_length=255,
        assume_scheme="https",
        widget=forms.URLInput(
            attrs={
                "autocomplete": "url",
                "inputmode": "url",
                "spellcheck": "false",
            }
        ),
    )
    description = forms.CharField(
        label="描述",
        max_length=300,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    position = forms.IntegerField(label="排序位置", min_value=0)
    expected_version = forms.IntegerField(widget=forms.HiddenInput, required=False)


class FriendLinkDeleteForm(forms.Form):
    link_id = forms.CharField(widget=forms.HiddenInput)
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


class TrustedSourceForm(forms.Form):
    source_key = forms.CharField(widget=forms.HiddenInput)
    enabled = forms.BooleanField(label="允许 Bilibili 视频", required=False)
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


class GuestbookSettingsForm(forms.Form):
    comments_enabled = forms.BooleanField(label="允许留言", required=False)
    post_login_required = forms.BooleanField(label="留言需要登录", required=False)


class ArticleExplanationSettingsForm(forms.Form):
    daily_limit = forms.IntegerField(
        label="每用户每日解释次数",
        min_value=1,
        max_value=1_000,
        help_text="达到上限后不调用 AGENT，只在解释面板提示原因。",
    )
    minute_limit = forms.IntegerField(
        label="每用户每分钟解释次数",
        min_value=1,
        max_value=60,
        help_text="按账户滚动 60 秒窗口限制，避免短时间重复请求。",
    )
    selection_limit = forms.IntegerField(
        label="单次选区最大字符数",
        min_value=1,
        max_value=10_000,
        help_text="超出后截断，但仍继续请求，并在结果中说明原始与处理字数。",
    )
    history_limit = forms.IntegerField(
        label="每账户本地历史条数",
        min_value=1,
        max_value=100,
        help_text="只影响浏览器 localStorage，超过后从最早记录开始挤出。",
    )
    focus_idle_timeout_minutes = forms.IntegerField(
        label="专注模式无操作提醒时间（分钟）",
        initial=DEFAULT_FOCUS_IDLE_TIMEOUT_MINUTES,
        min_value=MIN_FOCUS_IDLE_TIMEOUT_MINUTES,
        max_value=MAX_FOCUS_IDLE_TIMEOUT_MINUTES,
        help_text="达到该时间后暂停专注计时并提醒；键盘、滚动和触屏操作也会重置计时。",
    )
    focus_manual_pause_limit = forms.IntegerField(
        label="每次专注允许的手动暂停次数",
        initial=DEFAULT_FOCUS_MANUAL_PAUSE_LIMIT,
        min_value=MIN_FOCUS_MANUAL_PAUSE_LIMIT,
        max_value=MAX_FOCUS_MANUAL_PAUSE_LIMIT,
        help_text="达到上限后结束本次专注；失焦和无操作触发的自动暂停不计入。",
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


__all__ = [
    "FriendLinkDeleteForm",
    "ArticleExplanationSettingsForm",
    "FriendLinkForm",
    "GuestbookSettingsForm",
    "SiteConfigurationForm",
    "StaticPageForm",
    "TrustedSourceForm",
    "VerificationEmailTemplateForm",
]
