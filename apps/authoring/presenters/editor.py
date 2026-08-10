import json

from apps.content.public import ArticlePreviewError, ContentFormat, preview_article_body

FORMAT_LABELS = {
    ContentFormat.MARKDOWN: "Markdown",
    ContentFormat.TIPTAP_JSON: "富文本",
}


def serialized_body(content_format: str, body) -> str:
    if content_format == ContentFormat.MARKDOWN:
        return body if isinstance(body, str) else ""
    if not isinstance(body, dict):
        return '{"type":"doc","content":[]}'
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


def initial_from_session(session) -> dict:
    snapshot = session.snapshot
    return {
        "content_format": snapshot.content_format,
        "upload_scope": session.article_id,
        "baseline_revision_id": session.baseline_revision_id,
        "edit_token": session.token,
        "title": snapshot.title,
        "body": serialized_body(snapshot.content_format, snapshot.body),
        "summary_mode": snapshot.summary_mode,
        "custom_summary": snapshot.custom_summary or "",
        "visibility": snapshot.visibility,
        "section_id": str(snapshot.section_id or ""),
        "tag_ids": tuple(str(value) for value in snapshot.tag_ids),
        "proposed_tag_names": "[]",
        "cover_asset_id": snapshot.cover_asset_id or "",
        "attachment_asset_id": snapshot.attachment_asset_id or "",
        "comments_enabled": snapshot.comments_enabled,
        "comments_view_login": snapshot.comments_view_login,
        "comments_post_login": snapshot.comments_post_login,
    }


def preview_from_form(
    form,
    content_format: str,
    *,
    tiptap_schema_version: int | None = None,
):
    source = form["body"].value() or ""
    try:
        body = (
            source if content_format == ContentFormat.MARKDOWN else json.loads(source)
        )
        return (
            preview_article_body(
                content_format=content_format,
                body=body,
                tiptap_schema_version=tiptap_schema_version,
                attachment_asset_id=(
                    form["attachment_asset_id"].value()
                    if "attachment_asset_id" in form.fields
                    else None
                ),
            ),
            "",
        )
    except ArticlePreviewError as exc:
        return None, exc.safe_message
    except (json.JSONDecodeError, TypeError):
        return None, "正文格式不合法，无法生成预览。"
