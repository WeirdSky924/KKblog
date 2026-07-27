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
        "edit_token": session.token,
        "title": snapshot.title,
        "body": serialized_body(snapshot.content_format, snapshot.body),
        "summary_mode": snapshot.summary_mode,
        "custom_summary": snapshot.custom_summary or "",
        "visibility": snapshot.visibility,
        "section_id": str(snapshot.section_id or ""),
        "tag_ids": tuple(str(value) for value in snapshot.tag_ids),
        "cover_asset_id": snapshot.cover_asset_id or "",
        "comments_enabled": snapshot.comments_enabled,
        "comments_view_login": snapshot.comments_view_login,
        "comments_post_login": snapshot.comments_post_login,
    }


def preview_from_form(form, content_format: str):
    source = form["body"].value() or ""
    try:
        body = (
            source if content_format == ContentFormat.MARKDOWN else json.loads(source)
        )
        return preview_article_body(content_format=content_format, body=body), ""
    except (ArticlePreviewError, json.JSONDecodeError, TypeError):
        return None, "正文格式不合法，无法生成预览。"
