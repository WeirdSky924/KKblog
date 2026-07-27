from __future__ import annotations

import json

from django import forms

from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    SummaryMode,
    Visibility,
)
from apps.core.ids import normalize_ulid
from apps.media.public import markdown_media_ids, tiptap_media_ids

_FORMAT_CHOICES = (
    (ContentFormat.MARKDOWN, "Markdown"),
    (ContentFormat.TIPTAP_JSON, "富文本"),
)
_SUMMARY_CHOICES = (
    (SummaryMode.AUTO, "自动摘要"),
    (SummaryMode.CUSTOM, "自定义摘要"),
    (SummaryMode.NONE, "不显示摘要"),
)
_VISIBILITY_CHOICES = (
    (Visibility.PUBLIC, "大众可见"),
    (Visibility.AUTHENTICATED, "登录可见"),
    (Visibility.PRIVATE, "仅自己"),
)


class CloudDraftDiscardForm(forms.Form):
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("discard", "确认删除云端草稿"),),
        widget=forms.HiddenInput,
    )


class ArticleEditorForm(forms.Form):
    content_format = forms.ChoiceField(
        choices=_FORMAT_CHOICES,
        widget=forms.HiddenInput,
    )
    upload_scope = forms.CharField(max_length=26, widget=forms.HiddenInput)
    baseline_revision_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    edit_token = forms.CharField(required=False, widget=forms.HiddenInput)
    title = forms.CharField(
        label="标题",
        max_length=30,
        widget=forms.TextInput(attrs={"autocomplete": "off", "data-editor-title": ""}),
    )
    body = forms.CharField(
        label="正文",
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 24, "spellcheck": "true", "data-editor-source": ""}
        ),
    )
    summary_mode = forms.ChoiceField(
        label="摘要",
        choices=_SUMMARY_CHOICES,
        widget=forms.Select(attrs={"data-summary-mode": ""}),
    )
    custom_summary = forms.CharField(
        label="自定义摘要",
        max_length=100,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "data-custom-summary": ""}),
    )
    visibility = forms.ChoiceField(label="可见范围", choices=_VISIBILITY_CHOICES)
    section_id = forms.ChoiceField(label="分区", required=False)
    tag_ids = forms.MultipleChoiceField(
        label="标签",
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    cover_asset_id = forms.CharField(
        required=False,
        max_length=26,
        widget=forms.HiddenInput,
    )
    comments_enabled = forms.BooleanField(label="开启评论", required=False)
    comments_view_login = forms.BooleanField(label="登录后查看评论", required=False)
    comments_post_login = forms.BooleanField(label="登录后发表评论", required=False)

    def __init__(
        self,
        *args,
        sections=(),
        tags=(),
        locked_format: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.locked_format = locked_format
        self.fields["section_id"].choices = (
            ("", "未选择分区"),
            *((str(item.section_id), item.name) for item in sections),
        )
        self.fields["tag_ids"].choices = tuple(
            (
                str(item.tag_id),
                f"{item.name}（待审核）" if item.state == "PENDING" else item.name,
            )
            for item in tags
        )

    def clean_content_format(self) -> str:
        value = self.cleaned_data["content_format"]
        if self.locked_format is not None and value != self.locked_format:
            raise forms.ValidationError("文章格式已锁定，不能在普通编辑中切换。")
        return value

    def clean_upload_scope(self) -> str:
        try:
            return normalize_ulid(self.cleaned_data["upload_scope"])
        except (TypeError, ValueError):
            raise forms.ValidationError(
                "媒体上传作用域已失效，请重新打开页面。"
            ) from None

    def clean_baseline_revision_id(self) -> str:
        value = self.cleaned_data["baseline_revision_id"]
        if value == "NEW":
            return value
        try:
            return normalize_ulid(value)
        except (TypeError, ValueError):
            raise forms.ValidationError("编辑基线已失效，请重新打开页面。") from None

    def clean_cover_asset_id(self) -> str | None:
        value = self.cleaned_data["cover_asset_id"]
        if not value:
            return None
        try:
            return normalize_ulid(value)
        except (TypeError, ValueError):
            raise forms.ValidationError("封面引用无效，请重新上传。") from None

    def clean_tag_ids(self) -> tuple[str, ...]:
        values = tuple(self.cleaned_data["tag_ids"])
        if len(values) > 10:
            raise forms.ValidationError("每篇文章最多选择 10 个标签。")
        return values

    def clean(self):
        values = super().clean()
        content_format = values.get("content_format")
        body_source = values.get("body", "")
        if content_format == ContentFormat.TIPTAP_JSON:
            try:
                document = json.loads(body_source)
            except (TypeError, json.JSONDecodeError):
                self.add_error("body", "富文本正文数据不完整，请重新打开页面。")
            else:
                if not isinstance(document, dict):
                    self.add_error("body", "富文本正文数据不完整，请重新打开页面。")
                else:
                    values["body_document"] = document
        else:
            values["body_document"] = body_source
        summary_mode = values.get("summary_mode")
        custom_summary = (values.get("custom_summary") or "").strip()
        if summary_mode == SummaryMode.CUSTOM and not custom_summary:
            self.add_error("custom_summary", "自定义摘要不能为空。")
        if summary_mode != SummaryMode.CUSTOM:
            values["custom_summary"] = None
        else:
            values["custom_summary"] = custom_summary
        if not values.get("comments_enabled"):
            values["comments_view_login"] = False
            values["comments_post_login"] = False
        return values

    def snapshot(self) -> ArticleSnapshot:
        if not self.is_valid():
            raise ValueError("Cannot create an article snapshot from an invalid form")
        body = self.cleaned_data["body_document"]
        media_ids = (
            markdown_media_ids(body)
            if self.cleaned_data["content_format"] == ContentFormat.MARKDOWN
            else tiptap_media_ids(body)
        )
        return ArticleSnapshot(
            content_format=self.cleaned_data["content_format"],
            title=self.cleaned_data["title"],
            body=body,
            summary_mode=self.cleaned_data["summary_mode"],
            custom_summary=self.cleaned_data["custom_summary"],
            visibility=self.cleaned_data["visibility"],
            section_id=self.cleaned_data["section_id"] or None,
            tag_ids=tuple(self.cleaned_data["tag_ids"]),
            cover_asset_id=self.cleaned_data["cover_asset_id"],
            body_asset_ids=media_ids,
            comments_enabled=self.cleaned_data["comments_enabled"],
            comments_view_login=self.cleaned_data["comments_view_login"],
            comments_post_login=self.cleaned_data["comments_post_login"],
        )
