from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from PIL import Image

from apps.content.models import Article, ArticleRevision
from apps.content.public import (
    ArticleBodyLimit,
    ArticleSnapshot,
    ContentCommandError,
    ContentFormat,
    SummaryMode,
    Visibility,
    create_article,
    save_revision,
)
from apps.media.public import MediaPurpose, stage_upload
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, author: bool = False):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if author:
        role_model.objects.create(account=account, role="AUTHOR")
    return account


def _markdown_snapshot(body: str = "正文", **overrides) -> ArticleSnapshot:
    values = {
        "content_format": ContentFormat.MARKDOWN,
        "title": "第一篇文章",
        "body": body,
    }
    values.update(overrides)
    return ArticleSnapshot(**values)


def _create(author, snapshot=None, *, body_limit=None):
    return create_article(
        actor_id=author.id,
        snapshot=snapshot or _markdown_snapshot(),
        body_limit=body_limit,
        capacity_check=lambda: None,
    )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 9), "#197278").save(output, format="PNG")
    return output.getvalue()


def _asset(owner, root: Path, purpose: MediaPurpose, article_id: str):
    return stage_upload(
        owner_id=owner.id,
        purpose=purpose,
        original_name="article.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        target_id=article_id,
    )


def test_create_article_persists_documented_defaults() -> None:
    author = _account("defaults", author=True)

    result = _create(author)

    article = Article.objects.get(pk=result.article_id)
    revision = ArticleRevision.objects.get(pk=result.revision_id)
    assert article.author_id == author.id
    assert article.publication_state == Article.PublicationState.DRAFT
    assert article.working_revision_id == revision.id
    assert article.published_revision_id is None
    assert article.scheduled_revision_id is None
    assert article.row_version == 1
    assert revision.sequence == 1
    assert revision.visibility == Visibility.PUBLIC
    assert revision.summary_mode == SummaryMode.AUTO
    assert revision.comments_enabled is True
    assert revision.comments_view_login is False
    assert revision.comments_post_login is False


def test_create_and_save_support_markdown_and_tiptap_json() -> None:
    author = _account("formats", author=True)
    markdown = _create(author)
    tiptap = _create(
        author,
        ArticleSnapshot(
            content_format=ContentFormat.TIPTAP_JSON,
            title="富文本文章",
            body={
                "type": "doc",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "富文本正文"}],
                    }
                ],
            },
        ),
    )

    assert ArticleRevision.objects.get(pk=markdown.revision_id).body_markdown == "正文"
    rich_revision = ArticleRevision.objects.get(pk=tiptap.revision_id)
    assert rich_revision.body_tiptap["type"] == "doc"
    assert rich_revision.body_markdown is None


@pytest.mark.parametrize("maximum", [64 * 1024, 2 * 1024 * 1024])
def test_body_limit_accepts_exact_boundary_and_rejects_one_extra(maximum: int) -> None:
    author = _account(f"limit-{maximum}", author=True)
    policy = ArticleBodyLimit(maximum)

    accepted = _create(author, _markdown_snapshot("a" * maximum), body_limit=policy)
    assert ArticleRevision.objects.get(pk=accepted.revision_id).body_markdown

    with pytest.raises(ContentCommandError) as captured:
        _create(author, _markdown_snapshot("a" * (maximum + 1)), body_limit=policy)
    assert captured.value.code == "content.body_too_large.v1"


@pytest.mark.parametrize("maximum", [64 * 1024 - 1, 2 * 1024 * 1024 + 1])
def test_body_limit_configuration_cannot_leave_safe_range(maximum: int) -> None:
    with pytest.raises(ValueError):
        ArticleBodyLimit(maximum)


def test_summary_and_body_media_reference_sets_are_validated() -> None:
    author = _account("snapshot-validation", author=True)
    with pytest.raises(ContentCommandError) as captured:
        _create(
            author,
            _markdown_snapshot(
                custom_summary="不应保存",
                summary_mode=SummaryMode.NONE,
            ),
        )
    assert captured.value.code == "content.summary_invalid.v1"

    unlisted = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    with pytest.raises(ContentCommandError) as captured:
        _create(author, _markdown_snapshot(f"![未提交](media:{unlisted})"))
    assert captured.value.code == "content.media_invalid.v1"


def test_non_author_and_disabled_author_cannot_create_or_save() -> None:
    user = _account("plain-user")
    with pytest.raises(ContentCommandError) as captured:
        _create(user)
    assert captured.value.code == "content.author_required.v1"

    author = _account("disabled-author", author=True)
    created = _create(author)
    author.status = "DISABLED"
    author.save(update_fields=("status", "updated_at"))
    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=author.id,
            article_id=created.article_id,
            expected_row_version=1,
            snapshot=_markdown_snapshot("修改"),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.author_required.v1"


def test_save_creates_new_immutable_revision_and_rejects_format_switch() -> None:
    author = _account("save", author=True)
    created = _create(author)

    saved = save_revision(
        actor_id=author.id,
        article_id=created.article_id,
        expected_row_version=created.row_version,
        snapshot=_markdown_snapshot("第二版正文"),
        capacity_check=lambda: None,
    )

    article = Article.objects.get(pk=created.article_id)
    old_revision = ArticleRevision.objects.get(pk=created.revision_id)
    assert saved.revision_id != old_revision.id
    assert article.working_revision_id == saved.revision_id
    assert article.row_version == 2
    assert old_revision.body_markdown == "正文"
    assert ArticleRevision.objects.get(pk=saved.revision_id).sequence == 2

    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=author.id,
            article_id=article.id,
            expected_row_version=article.row_version,
            snapshot=ArticleSnapshot(
                content_format=ContentFormat.TIPTAP_JSON,
                title="不能切换格式",
                body={"type": "doc", "content": []},
            ),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.format_immutable.v1"


def test_media_binding_checks_owner_purpose_and_rolls_back_revision(
    isolated_media_root: Path,
) -> None:
    author = _account("media-owner", author=True)
    other = _account("media-other", author=True)
    created = _create(author)
    body = _asset(author, isolated_media_root, MediaPurpose.BODY, created.article_id)
    cover = _asset(author, isolated_media_root, MediaPurpose.COVER, created.article_id)
    foreign = _asset(other, isolated_media_root, MediaPurpose.BODY, created.article_id)

    saved = save_revision(
        actor_id=author.id,
        article_id=created.article_id,
        expected_row_version=created.row_version,
        snapshot=_markdown_snapshot(
            f"![正文图](media:{body.id})",
            cover_asset_id=cover.id,
            body_asset_ids=(body.id,),
        ),
        capacity_check=lambda: None,
    )
    binding_model = apps.get_model("media", "MediaBinding")
    assert set(
        binding_model.objects.filter(target_id=saved.revision_id).values_list(
            "asset_id", "slot"
        )
    ) == {(cover.id, "cover"), (body.id, f"body-{body.id}")}

    repeated = save_revision(
        actor_id=author.id,
        article_id=created.article_id,
        expected_row_version=saved.row_version,
        snapshot=_markdown_snapshot(
            f"![正文图](media:{body.id})\n\n第三版",
            cover_asset_id=cover.id,
            body_asset_ids=(body.id,),
        ),
        capacity_check=lambda: None,
    )
    assert (
        binding_model.objects.filter(
            asset_id=body.id,
            target_id__in=(saved.revision_id, repeated.revision_id),
        ).count()
        == 2
    )
    assert (
        binding_model.objects.filter(
            asset_id=cover.id,
            target_id__in=(saved.revision_id, repeated.revision_id),
        ).count()
        == 2
    )

    before_count = ArticleRevision.objects.filter(article_id=created.article_id).count()
    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=author.id,
            article_id=created.article_id,
            expected_row_version=repeated.row_version,
            snapshot=_markdown_snapshot(
                f"![越权图](media:{foreign.id})",
                body_asset_ids=(foreign.id,),
            ),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.media_invalid.v1"
    assert (
        ArticleRevision.objects.filter(article_id=created.article_id).count()
        == before_count
    )
    assert not binding_model.objects.filter(asset_id=foreign.id).exists()

    other_article = _create(author)
    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=author.id,
            article_id=other_article.article_id,
            expected_row_version=other_article.row_version,
            snapshot=_markdown_snapshot(
                f"![跨文章复用](media:{body.id})",
                body_asset_ids=(body.id,),
            ),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.media_invalid.v1"

    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=author.id,
            article_id=created.article_id,
            expected_row_version=repeated.row_version,
            snapshot=_markdown_snapshot(
                f"![用途错误](media:{cover.id})",
                body_asset_ids=(cover.id,),
            ),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.media_invalid.v1"
