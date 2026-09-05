from __future__ import annotations

import json
import unicodedata
from datetime import datetime

from django import forms

from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    SummaryMode,
    Visibility,
)
from apps.core.ids import normalize_ulid
from apps.media.public import (
    CURRENT_TIPTAP_SCHEMA_VERSION,
    RenderingError,
    markdown_media_ids,
    tiptap_media_ids,
)

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
_PUBLICATION_CHOICES = (
    ("IMMEDIATE", "立即发布"),
    ("SCHEDULED", "定时发布"),
)


class PublicationReviewForm(forms.Form):
    revision_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    review_token = forms.CharField(max_length=128, widget=forms.HiddenInput)
    publication_mode = forms.ChoiceField(
        label="发布方式",
        choices=_PUBLICATION_CHOICES,
        widget=forms.RadioSelect,
    )
    scheduled_local = forms.CharField(
        label="上海时间",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "step": "60"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    def clean_revision_id(self) -> str:
        try:
            return normalize_ulid(self.cleaned_data["revision_id"])
        except (TypeError, ValueError):
            raise forms.ValidationError("终稿审查已失效，请重新审查。") from None

    def clean_review_token(self) -> str:
        value = self.cleaned_data["review_token"]
        if value.count(".") != 1:
            raise forms.ValidationError("终稿审查已失效，请重新审查。")
        return value

    def clean(self):
        values = super().clean()
        raw = (values.get("scheduled_local") or "").strip()
        if values.get("publication_mode") != "SCHEDULED":
            values["scheduled_local"] = None
            return values
        if not raw:
            self.add_error("scheduled_local", "请选择定时发布的上海时间。")
            return values
        try:
            values["scheduled_local"] = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
        except ValueError:
            self.add_error("scheduled_local", "请选择有效的上海日期和时间。")
        return values


class RestoreRevisionForm(forms.Form):
    source_revision_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    restore_token = forms.CharField(max_length=128, widget=forms.HiddenInput)

    def clean_source_revision_id(self) -> str:
        try:
            return normalize_ulid(self.cleaned_data["source_revision_id"])
        except (TypeError, ValueError):
            raise forms.ValidationError("历史版本选择已失效，请重试。") from None

    def clean_restore_token(self) -> str:
        value = self.cleaned_data["restore_token"]
        if value.count(".") != 1:
            raise forms.ValidationError("恢复审查已失效，请重新操作。")
        return value


class CloudDraftDiscardForm(forms.Form):
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("discard", "确认删除云端草稿"),),
        widget=forms.HiddenInput,
    )


class ArticleDeleteForm(forms.Form):
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("delete", "确认删除文章"),),
        widget=forms.HiddenInput,
    )
    return_state = forms.ChoiceField(
        choices=tuple(
            (state, state) for state in ("PUBLISHED", "DRAFT", "SCHEDULED", "DELETED")
        ),
        widget=forms.HiddenInput,
    )
    return_page = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class ArticleRestoreForm(forms.Form):
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("restore", "确认恢复文章"),),
        widget=forms.HiddenInput,
    )
    return_state = forms.ChoiceField(
        choices=tuple(
            (state, state) for state in ("PUBLISHED", "DRAFT", "SCHEDULED", "DELETED")
        ),
        widget=forms.HiddenInput,
    )
    return_page = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


class EditConflictResolutionForm(forms.Form):
    conflict_token = forms.CharField(max_length=128, widget=forms.HiddenInput)
    local_baseline_revision_id = forms.CharField(
        max_length=26,
        widget=forms.HiddenInput,
    )
    selected_revision_id = forms.ChoiceField(
        label="选择新的编辑基线",
        widget=forms.RadioSelect,
    )
    preserve_local_input = forms.BooleanField(
        label="选择后恢复冲突前的本地输入",
        required=False,
        initial=True,
    )

    def __init__(self, *args, revisions=(), **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["selected_revision_id"].choices = tuple(
            (item.revision_id, item.revision_id) for item in revisions
        )

    def clean_conflict_token(self) -> str:
        value = self.cleaned_data["conflict_token"]
        if value.count(".") != 1:
            raise forms.ValidationError("冲突选择已失效，请刷新页面后重试。")
        return value

    def clean_local_baseline_revision_id(self) -> str:
        try:
            return normalize_ulid(self.cleaned_data["local_baseline_revision_id"])
        except (TypeError, ValueError):
            raise forms.ValidationError(
                "本地稿基线已失效，请刷新页面后重试。"
            ) from None


class ArticleEditorForm(forms.Form):
    content_format = forms.ChoiceField(
        choices=_FORMAT_CHOICES,
        widget=forms.HiddenInput,
    )
    upload_scope = forms.CharField(max_length=26, widget=forms.HiddenInput)
    baseline_revision_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    edit_token = forms.CharField(required=False, widget=forms.HiddenInput)
    import_job_id = forms.CharField(
        required=False,
        max_length=26,
        widget=forms.HiddenInput,
    )
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
    proposed_tag_names = forms.CharField(
        required=False,
        max_length=1024,
        initial="[]",
        widget=forms.HiddenInput(attrs={"data-proposed-tag-names": ""}),
    )
    cover_asset_id = forms.CharField(
        required=False,
        max_length=26,
        widget=forms.HiddenInput,
    )
    attachment_asset_id = forms.CharField(
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
        self.tag_normalized_names = {
            str(item.tag_id): unicodedata.normalize("NFKC", item.name)
            .strip()
            .casefold()
            for item in tags
        }
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

    def clean_import_job_id(self) -> str:
        value = self.cleaned_data["import_job_id"]
        if not value:
            return ""
        try:
            return normalize_ulid(value)
        except (TypeError, ValueError):
            raise forms.ValidationError("导入内容已失效，请重新上传文档。") from None

    def clean_cover_asset_id(self) -> str | None:
        value = self.cleaned_data["cover_asset_id"]
        if not value:
            return None
        try:
            return normalize_ulid(value)
        except (TypeError, ValueError):
            raise forms.ValidationError("封面引用无效，请重新上传。") from None

    def clean_attachment_asset_id(self) -> str | None:
        value = self.cleaned_data["attachment_asset_id"]
        if not value:
            return None
        try:
            return normalize_ulid(value)
        except (TypeError, ValueError):
            raise forms.ValidationError("附件引用无效，请重新上传。") from None

    def clean_tag_ids(self) -> tuple[str, ...]:
        values = tuple(self.cleaned_data["tag_ids"])
        if len(values) > 10:
            raise forms.ValidationError("每篇文章最多选择 10 个标签。")
        return values

    def clean_proposed_tag_names(self) -> tuple[str, ...]:
        raw = self.cleaned_data.get("proposed_tag_names") or "[]"
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise forms.ValidationError("标签申请信息不完整，请重新选择。") from None
        if (
            not isinstance(values, list)
            or len(values) > 10
            or any(not isinstance(value, str) for value in values)
        ):
            raise forms.ValidationError("标签申请信息不完整，请重新选择。")
        names: list[str] = []
        normalized: set[str] = set()
        for value in values:
            display = unicodedata.normalize("NFKC", value).strip()
            key = display.casefold()
            if (
                not display
                or len(display) > 50
                or any(ord(char) < 32 for char in display)
            ):
                raise forms.ValidationError("标签名称须为 1 至 50 个字符。")
            if key not in normalized:
                normalized.add(key)
                names.append(display)
        return tuple(names)

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
                    try:
                        values["body_media_ids"] = tiptap_media_ids(
                            document,
                            schema_version=CURRENT_TIPTAP_SCHEMA_VERSION,
                        )
                    except RenderingError:
                        self.add_error("body", "正文格式不合法，请修正后重试。")
        elif content_format == ContentFormat.MARKDOWN:
            values["body_document"] = body_source
            try:
                values["body_media_ids"] = markdown_media_ids(body_source)
            except RenderingError:
                self.add_error("body", "正文格式不合法，请修正后重试。")
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
        tag_ids = values.get("tag_ids") or ()
        proposed_names = values.get("proposed_tag_names") or ()
        selected_names = {
            self.tag_normalized_names.get(str(tag_id), "") for tag_id in tag_ids
        }
        additional_names = {
            unicodedata.normalize("NFKC", name).strip().casefold()
            for name in proposed_names
        } - selected_names
        if len(tag_ids) + len(additional_names) > 10:
            self.add_error("proposed_tag_names", "每篇文章最多选择 10 个标签。")
        return values

    def snapshot(self) -> ArticleSnapshot:
        if not self.is_valid():
            raise ValueError("Cannot create an article snapshot from an invalid form")
        body = self.cleaned_data["body_document"]
        return ArticleSnapshot(
            content_format=self.cleaned_data["content_format"],
            title=self.cleaned_data["title"],
            body=body,
            summary_mode=self.cleaned_data["summary_mode"],
            custom_summary=self.cleaned_data["custom_summary"],
            visibility=self.cleaned_data["visibility"],
            section_id=self.cleaned_data["section_id"] or None,
            tag_ids=tuple(self.cleaned_data["tag_ids"]),
            proposed_tag_names=tuple(self.cleaned_data["proposed_tag_names"]),
            cover_asset_id=self.cleaned_data["cover_asset_id"],
            attachment_asset_id=self.cleaned_data["attachment_asset_id"],
            body_asset_ids=self.cleaned_data["body_media_ids"],
            comments_enabled=self.cleaned_data["comments_enabled"],
            comments_view_login=self.cleaned_data["comments_view_login"],
            comments_post_login=self.cleaned_data["comments_post_login"],
        )
