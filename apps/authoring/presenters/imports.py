from collections.abc import Mapping
from dataclasses import dataclass

from apps.exchange.public import ImportPreview

_STATUS_LABELS = {
    "PREVIEW_READY": "预览就绪",
    "PROCESSING": "正在导入",
    "COMPLETED": "导入完成",
    "PARTIAL": "部分完成",
    "FAILED": "导入失败",
}
_CLASSIFICATION_LABELS = {
    "NEW": "新文章",
    "DUPLICATE_ID": "重复 ID",
    "TITLE_WARNING": "同标题提醒",
    "FOREIGN_CONFLICT": "跨作者 ID 冲突",
    "INVALID": "文件无效",
}
_RESULT_LABELS = {
    "PENDING": "待处理",
    "SUCCESS": "成功",
    "SKIPPED": "已跳过",
    "FAILED": "失败",
}
_REASON_LABELS = {
    "exchange.import_created.v1": "已创建文章",
    "exchange.import_updated.v1": "已创建新版本",
    "exchange.import_skipped.v1": "按选择跳过",
    "exchange.import_markdown_invalid.v1": "Markdown 无法读取",
    "exchange.import_image_invalid.v1": "引用图片无效",
    "exchange.import_item_failed.v1": "该项导入失败",
    "exchange.import_image_reference_invalid.v1": "正文中的图片引用无效",
    "exchange.import_target_invalid.v1": "目标文章信息无效",
    "content.import_title_invalid.v1": "文章标题不符合要求",
    "content.import_body_invalid.v1": "文章正文不符合要求",
    "content.import_visibility_invalid.v1": "文章可见范围无效",
    "content.import_comments_invalid.v1": "评论设置无效",
    "content.snapshot_invalid.v1": "文章设置不符合要求",
}
_ISSUE_LABELS = {
    "exchange.import_markdown_invalid.v1": "Markdown 无法读取",
    "exchange.import_image_invalid.v1": "引用图片无效",
    "exchange.front_matter_invalid.v1": "Front Matter 无法读取",
    "exchange.import_body_limit.v1": "正文超过当前长度上限",
}
_ALLOWED_DECISIONS = {
    "NEW": ("SKIP", "CREATE"),
    "TITLE_WARNING": ("SKIP", "CREATE"),
    "DUPLICATE_ID": ("SKIP", "UPDATE", "CREATE"),
    "FOREIGN_CONFLICT": (),
    "INVALID": (),
}


@dataclass(frozen=True, slots=True)
class ImportItemCard:
    item_id: str
    item_path: str
    title: str
    classification: str
    classification_label: str
    conflict_label: str
    issue_label: str
    decision: str
    included: bool
    mapped_section_id: str
    mapped_tag_ids: tuple[str, ...]
    proposed_tag_names: tuple[str, ...]
    preview_html: str
    allowed_decisions: tuple[str, ...]
    result_status: str
    result_label: str
    result_reason_label: str
    result_article_id: str


@dataclass(frozen=True, slots=True)
class ImportWorkspacePage:
    job_id: str
    status: str
    status_label: str
    preview_version: int
    preview_summary: Mapping[str, object]
    result_summary: Mapping[str, object]
    items: tuple[ImportItemCard, ...]

    @property
    def editable(self) -> bool:
        return self.status == "PREVIEW_READY"

    @property
    def processing(self) -> bool:
        return self.status == "PROCESSING"

    @property
    def terminal(self) -> bool:
        return self.status in {"COMPLETED", "PARTIAL", "FAILED"}


def import_workspace_page(source: ImportPreview) -> ImportWorkspacePage:
    return ImportWorkspacePage(
        job_id=source.job_id,
        status=source.status,
        status_label=_STATUS_LABELS.get(source.status, "导入状态未知"),
        preview_version=source.preview_version,
        preview_summary=source.preview_summary,
        result_summary=source.result_summary,
        items=tuple(
            ImportItemCard(
                item_id=item.item_id,
                item_path=item.item_path,
                title=item.title,
                classification=item.classification or "INVALID",
                classification_label=_CLASSIFICATION_LABELS.get(
                    item.classification or "INVALID", "文件无效"
                ),
                conflict_label=_conflict_label(item),
                issue_label=_ISSUE_LABELS.get(
                    item.parse_error_code,
                    "文件内容不符合导入要求" if item.parse_error_code else "",
                ),
                decision=item.decision or "SKIP",
                included=item.included,
                mapped_section_id=(
                    str(item.mapped_section_id) if item.mapped_section_id else ""
                ),
                mapped_tag_ids=tuple(str(value) for value in item.mapped_tag_ids),
                proposed_tag_names=item.proposed_tag_names,
                preview_html=item.preview_html,
                allowed_decisions=_ALLOWED_DECISIONS.get(
                    item.classification or "INVALID", ()
                ),
                result_status=item.result_status,
                result_label=_RESULT_LABELS.get(item.result_status, "待处理"),
                result_reason_label=_REASON_LABELS.get(
                    item.result_reason_code,
                    "导入失败" if item.result_status == "FAILED" else "",
                ),
                result_article_id=item.result_article_id or "",
            )
            for item in source.items
        ),
    )


def _conflict_label(item) -> str:
    classification = item.classification or "INVALID"
    if classification == "DUPLICATE_ID":
        return "检测到本人已有的相同文章 ID。"
    if classification == "FOREIGN_CONFLICT":
        return "此文章 ID 属于其他作者，不能导入。"
    if classification != "TITLE_WARNING":
        return ""
    scope = item.conflict_summary.get("owner_scope")
    count = item.conflict_summary.get("match_count", 0)
    owner_label = {
        "SELF": "本人文章",
        "FOREIGN": "其他作者文章",
        "MIXED": "本人和其他作者文章",
    }.get(scope, "站内文章")
    return f"检测到 {count} 篇同标题{owner_label}；标题相同不会自动覆盖。"
