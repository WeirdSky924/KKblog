from django import forms

from apps.navigation.public import (
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
    registration_enabled = forms.BooleanField(label="开放直接注册", required=False)
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
    backup_destination = forms.ChoiceField(
        label="备份目标",
        choices=(("local", "local（本机）"),),
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput)


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
    name = forms.CharField(label="站点名称", max_length=80)
    url = forms.URLField(
        label="HTTPS 地址",
        max_length=255,
        assume_scheme="https",
    )
    description = forms.CharField(label="描述", max_length=300)
    logo_asset_id = forms.CharField(
        label="Logo",
        max_length=26,
        widget=forms.HiddenInput,
    )
    position = forms.IntegerField(label="位置", min_value=0, required=False)
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


__all__ = [
    "FriendLinkDeleteForm",
    "FriendLinkForm",
    "GuestbookSettingsForm",
    "SiteConfigurationForm",
    "StaticPageForm",
    "TrustedSourceForm",
]
