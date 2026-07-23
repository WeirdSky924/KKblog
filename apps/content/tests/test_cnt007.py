from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from PIL import Image

from apps.content.models import Article, ArticleRestoreGrant, ArticleRevision
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    PublicationCommandError,
    RestoreCommandError,
    SummaryMode,
    Visibility,
    create_article,
    create_section,
    create_tag,
    prepare_publication,
    prepare_restore_revision,
    publish_article,
    republish_saved_revision,
    restore_revision,
    revision_timeline,
    save_revision,
)
from apps.core.observability.trace import new_trace_code
from apps.media.public import MediaPurpose, stage_upload
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


def _admin(label: str = "restore-admin"):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _context() -> dict[str, str]:
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 12), "#d95d39").save(output, format="PNG")
    return output.getvalue()


def _asset(owner, root: Path, purpose: MediaPurpose, article_id: str):
    return stage_upload(
        owner_id=owner.id,
        purpose=purpose,
        original_name="restore.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        target_id=article_id,
    )


def _snapshot(
    *,
    section_id,
    body: str,
    title: str = "恢复文章",
    tag_ids=(),
    cover_asset_id=None,
    body_asset_ids=(),
    visibility=Visibility.PUBLIC,
    summary_mode=SummaryMode.AUTO,
    custom_summary=None,
    comments_enabled=True,
    comments_view_login=False,
    comments_post_login=False,
):
    return ArticleSnapshot(
        content_format=ContentFormat.MARKDOWN,
        title=title,
        body=body,
        section_id=section_id,
        tag_ids=tuple(tag_ids),
        cover_asset_id=cover_asset_id,
        body_asset_ids=tuple(body_asset_ids),
        visibility=visibility,
        summary_mode=summary_mode,
        custom_summary=custom_summary,
        comments_enabled=comments_enabled,
        comments_view_login=comments_view_login,
        comments_post_login=comments_post_login,
    )


def test_restore_copies_full_snapshot_and_requires_final_review(
    isolated_media_root: Path,
) -> None:
    admin = _admin()
    first_section = create_section(actor_id=admin.id, name="旧分区", **_context())
    second_section = create_section(actor_id=admin.id, name="新分区", **_context())
    first_tag = create_tag(actor_id=admin.id, name="旧标签", **_context())
    second_tag = create_tag(actor_id=admin.id, name="新标签", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section_id=first_section.section_id, body="初始"),
        capacity_check=lambda: None,
    )
    body_asset = _asset(
        admin, isolated_media_root, MediaPurpose.BODY, article.article_id
    )
    cover_asset = _asset(
        admin, isolated_media_root, MediaPurpose.COVER, article.article_id
    )
    source = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(
            section_id=first_section.section_id,
            title="完整旧版本",
            body=f"![旧图](media:{body_asset.id})",
            tag_ids=(first_tag.tag_id,),
            cover_asset_id=cover_asset.id,
            body_asset_ids=(body_asset.id,),
            visibility=Visibility.PRIVATE,
            summary_mode=SummaryMode.CUSTOM,
            custom_summary="旧摘要",
            comments_enabled=False,
            comments_view_login=True,
            comments_post_login=True,
        ),
        capacity_check=lambda: None,
    )
    review = prepare_publication(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=source.revision_id,
        expected_row_version=source.row_version,
    )
    publish_article(
        actor_id=admin.id,
        article_id=article.article_id,
        revision_id=source.revision_id,
        expected_row_version=source.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
    )
    current = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=source.row_version,
        snapshot=_snapshot(
            section_id=second_section.section_id,
            title="当前版本",
            body="当前正文",
            tag_ids=(second_tag.tag_id,),
            visibility=Visibility.PUBLIC,
        ),
        capacity_check=lambda: None,
    )

    preview = prepare_restore_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        source_revision_id=source.revision_id,
    )
    assert set(preview.changed_fields) >= {
        "title",
        "body",
        "cover",
        "visibility",
        "section",
        "tags",
        "summary",
        "comments",
    }
    grant = ArticleRestoreGrant.objects.get(pk=preview.grant_id)
    assert preview.token not in grant.token_digest
    restored = restore_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        source_revision_id=source.revision_id,
        expected_row_version=current.row_version,
        restore_token=preview.token,
    )

    aggregate = Article.objects.get(pk=article.article_id)
    revision = ArticleRevision.objects.get(pk=restored.revision_id)
    assert revision.restore_source_id == source.revision_id
    assert revision.based_on_id == current.revision_id
    assert revision.title == "完整旧版本"
    assert revision.body_markdown == f"![旧图](media:{body_asset.id})"
    assert revision.cover_asset_id == cover_asset.id
    assert revision.visibility == Visibility.PRIVATE
    assert revision.section_id == first_section.section_id
    assert revision.summary_mode == SummaryMode.CUSTOM
    assert revision.custom_summary == "旧摘要"
    assert revision.comments_enabled is False
    assert revision.comments_view_login is True
    assert revision.comments_post_login is True
    assert aggregate.working_revision_id == revision.id
    assert aggregate.published_revision_id == source.revision_id
    revision_tag = apps.get_model("content", "RevisionTag")
    article_tag = apps.get_model("content", "ArticleTag")
    binding = apps.get_model("media", "MediaBinding")
    assert revision_tag.objects.get(revision=revision).tag_id == first_tag.tag_id
    assert article_tag.objects.get(article=aggregate).tag_id == first_tag.tag_id
    assert set(
        binding.objects.filter(target_id=revision.id).values_list("asset_id", flat=True)
    ) == {
        body_asset.id,
        cover_asset.id,
    }

    with pytest.raises(PublicationCommandError) as captured:
        republish_saved_revision(
            actor_id=admin.id,
            article_id=article.article_id,
            revision_id=revision.id,
            expected_row_version=aggregate.row_version,
            auto_republish_enabled=True,
            trace_code=new_trace_code(),
        )
    assert captured.value.code == "content.final_review_required.v1"


def test_restore_token_detects_conflict_and_timeline_contains_no_body() -> None:
    admin = _admin("restore-conflict")
    section = create_section(actor_id=admin.id, name="恢复冲突", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=_snapshot(section_id=section.section_id, body="版本一"),
        capacity_check=lambda: None,
    )
    second = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=article.row_version,
        snapshot=_snapshot(section_id=section.section_id, body="版本二"),
        capacity_check=lambda: None,
    )
    preview = prepare_restore_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        source_revision_id=article.revision_id,
    )
    third = save_revision(
        actor_id=admin.id,
        article_id=article.article_id,
        expected_row_version=second.row_version,
        snapshot=_snapshot(section_id=section.section_id, body="版本三"),
        capacity_check=lambda: None,
    )
    with pytest.raises(RestoreCommandError) as captured:
        restore_revision(
            actor_id=admin.id,
            article_id=article.article_id,
            source_revision_id=article.revision_id,
            expected_row_version=third.row_version,
            restore_token=preview.token,
        )
    assert captured.value.code == "content.edit_conflict.v1"

    timeline = revision_timeline(actor_id=admin.id, article_id=article.article_id)
    assert [item.sequence for item in timeline] == [3, 2, 1]
    assert "版本一" not in repr(timeline)
    assert "版本二" not in repr(timeline)
    assert "版本三" not in repr(timeline)
