import json
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from PIL import Image

from apps.content.models import Article, ArticleRevision
from apps.content.public import (
    ArticleRenderingMode,
    ArticleSnapshot,
    ContentCommandError,
    ContentFormat,
    article_for_reader,
    create_article,
    create_section,
    export_revision_payloads,
    prepare_publication,
    prepare_restore_revision,
    preview_article_body,
    public_article_cache_snapshot,
    publish_article,
    sanitized_article_plain_text,
    save_revision,
    visible_article_page,
)
from apps.content.rendering_policy import content_rendering_version
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock
from apps.media.public import MediaPurpose, TrustedEmbedPolicy, stage_upload
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


def _author(label: str, *, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _section(actor, name: str):
    return create_section(
        actor_id=actor.id,
        name=name,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 9), "#197278").save(output, format="PNG")
    return output.getvalue()


def _asset(*, owner, article_id: str, root) -> object:
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.BODY,
        original_name="body.png",
        declared_content_type="image/png",
        chunks=[_png()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        target_id=article_id,
    )


def _attachment(*, owner, article_id: str, root) -> object:
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.ATTACHMENT,
        original_name="reader-guide.txt",
        declared_content_type="text/plain",
        chunks=["附件说明".encode()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        target_id=article_id,
    )


def _empty_snapshot(section_id) -> ArticleSnapshot:
    return ArticleSnapshot(
        content_format=ContentFormat.TIPTAP_JSON,
        title="TipTap contract",
        body={"type": "doc", "content": []},
        section_id=section_id,
    )


def test_text_blocks_and_marks_survive_revision_publish_and_public_read() -> None:
    actor = _author("tiptap-text-contract", administrator=True)
    section = _section(actor, "TipTap text contract section")
    created = create_article(
        actor_id=actor.id,
        snapshot=_empty_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    body = {
        "type": "doc",
        "content": [
            *[
                {
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": [{"type": "text", "text": f"Heading {level}"}],
                }
                for level in range(1, 7)
            ],
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "bold", "marks": [{"type": "bold"}]},
                    {"type": "text", "text": "italic", "marks": [{"type": "italic"}]},
                    {"type": "text", "text": "strike", "marks": [{"type": "strike"}]},
                    {
                        "type": "text",
                        "text": "underline",
                        "marks": [{"type": "underline"}],
                    },
                    {"type": "text", "text": "code", "marks": [{"type": "code"}]},
                    {
                        "type": "text",
                        "text": "linked",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {
                                    "href": "https://example.com/read?q=1",
                                    "title": "Reference",
                                },
                            }
                        ],
                    },
                    {"type": "hardBreak"},
                    {"type": "text", "text": "next line"},
                ],
            },
        ],
    }
    saved = save_revision(
        actor_id=actor.id,
        article_id=created.article_id,
        expected_row_version=created.row_version,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.TIPTAP_JSON,
            title="TipTap text contract",
            body=body,
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    revision = ArticleRevision.objects.get(pk=saved.revision_id)
    assert revision.tiptap_schema_version == 2
    assert revision.body_tiptap == body

    preview = preview_article_body(
        content_format=ContentFormat.TIPTAP_JSON,
        body=body,
        tiptap_schema_version=revision.tiptap_schema_version,
    )
    restore_preview = prepare_restore_revision(
        actor_id=actor.id,
        article_id=saved.article_id,
        source_revision_id=saved.revision_id,
    )
    historical = preview_article_body(
        content_format=restore_preview.source.content_format,
        body=restore_preview.source.body,
        body_asset_ids=restore_preview.source.body_asset_ids,
        tiptap_schema_version=restore_preview.source.tiptap_schema_version,
        attachment_asset_id=restore_preview.source.attachment_asset_id,
        mode=ArticleRenderingMode.READER,
    )
    assert historical.html == preview.html

    clock = FrozenClock(datetime(2026, 8, 8, 5, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    reader = article_for_reader(actor_id=None, article_id=saved.article_id)
    exported = export_revision_payloads(revision_ids=(saved.revision_id,))[0]
    listing = visible_article_page(actor_id=None, page=1, page_size=10)
    listed = next(item for item in listing.items if item.article_id == saved.article_id)
    cache_snapshot = public_article_cache_snapshot(article_id=saved.article_id)
    assert review.sanitized_html == preview.html
    assert reader.rendered_body_html == review.sanitized_html
    plain_text = sanitized_article_plain_text(preview.html)
    assert exported.convenience_markdown == "\n\n".join(
        [
            *[f"{'#' * level} Heading {level}" for level in range(1, 7)],
            "bolditalicstrikeunderlinecodelinked\nnext line",
        ]
    )
    assert listed.summary == plain_text[:100]
    assert cache_snapshot.sanitizer_version == content_rendering_version()
    assert len(reader.outline) == 6
    for level in range(1, 7):
        assert f'<h{level} id="kaj-h-legacy-' in reader.rendered_body_html
        assert f">Heading {level}</h{level}>" in reader.rendered_body_html
    assert "<strong>bold</strong>" in reader.rendered_body_html
    assert "<em>italic</em>" in reader.rendered_body_html
    assert "<s>strike</s>" in reader.rendered_body_html
    assert "<u>underline</u>" in reader.rendered_body_html
    assert "<code>code</code>" in reader.rendered_body_html
    assert (
        '<a href="https://example.com/read?q=1" title="Reference" '
        'rel="noopener noreferrer" target="_blank">linked</a>'
        in reader.rendered_body_html
    )
    assert "<br>next line" in reader.rendered_body_html


def test_trusted_embed_survives_publish_and_degrades_after_source_is_disabled(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "apps.content.rendering_policy._provider",
        lambda: TrustedEmbedPolicy(("bilibili",)),
    )
    actor = _author("tiptap-embed-contract", administrator=True)
    section = _section(actor, "TipTap embed contract section")
    created = create_article(
        actor_id=actor.id,
        snapshot=_empty_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    body = {
        "type": "doc",
        "content": [
            {
                "type": "embed",
                "attrs": {"source": "bilibili", "url": url},
            }
        ],
    }
    saved = save_revision(
        actor_id=actor.id,
        article_id=created.article_id,
        expected_row_version=created.row_version,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.TIPTAP_JSON,
            title="TipTap embed contract",
            body=body,
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    revision = ArticleRevision.objects.get(pk=saved.revision_id)
    assert revision.tiptap_schema_version == 2
    assert revision.body_tiptap == body

    clock = FrozenClock(datetime(2026, 8, 9, 5, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    reader = article_for_reader(actor_id=None, article_id=saved.article_id)
    assert reader.rendered_body_html == review.sanitized_html
    assert 'data-kaj-embed-card="bilibili"' in reader.rendered_body_html
    assert "https://player.bilibili.com/player.html" in reader.rendered_body_html
    assert f'href="{url}"' in reader.rendered_body_html

    monkeypatch.setattr(
        "apps.content.rendering_policy._provider",
        lambda: TrustedEmbedPolicy(()),
    )
    historical = article_for_reader(actor_id=None, article_id=saved.article_id)
    assert 'data-kaj-embed-fallback="bilibili"' in historical.rendered_body_html
    assert f'href="{url}"' in historical.rendered_body_html
    assert "player.bilibili.com" not in historical.rendered_body_html

    exported = export_revision_payloads(revision_ids=(saved.revision_id,))[0]
    assert exported.body_tiptap == body
    assert exported.tiptap_schema_version == 2
    assert exported.convenience_markdown == ""


def test_revision_media_publish_and_public_read_share_rendering_contract(
    tmp_path,
) -> None:
    actor = _author("tiptap-contract", administrator=True)
    other = _author("tiptap-foreign-media")
    section = _section(actor, "TipTap contract section")
    created = create_article(
        actor_id=actor.id,
        snapshot=_empty_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    body_asset = _asset(owner=actor, article_id=created.article_id, root=tmp_path)
    foreign_asset = _asset(
        owner=other,
        article_id=created.article_id,
        root=tmp_path,
    )
    body = {
        "type": "doc",
        "content": [
            {
                "type": "callout",
                "attrs": {"kind": "info"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": "<script>alert(1)</script>",
                                "marks": [{"type": "bold"}],
                            }
                        ],
                    }
                ],
            },
            {
                "type": "image",
                "attrs": {
                    "src": f"media:{body_asset.id}",
                    "alt": 'image" onerror="alert(1)',
                    "width": 50,
                },
            },
        ],
    }
    saved = save_revision(
        actor_id=actor.id,
        article_id=created.article_id,
        expected_row_version=created.row_version,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.TIPTAP_JSON,
            title="TipTap contract",
            body=body,
            section_id=section.section_id,
            body_asset_ids=(body_asset.id,),
        ),
        capacity_check=lambda: None,
    )
    revision = ArticleRevision.objects.get(pk=saved.revision_id)
    assert revision.tiptap_schema_version == 2
    assert revision.body_tiptap == body
    assert (tmp_path / body_asset.storage_key).is_file()

    clock = FrozenClock(datetime(2026, 8, 8, 4, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    reader = article_for_reader(actor_id=None, article_id=saved.article_id)
    assert reader.rendered_body_html == review.sanitized_html
    assert "<script" not in reader.rendered_body_html
    assert ' onerror="' not in reader.rendered_body_html
    assert f'src="/_kaj/media/{body_asset.id}"' in reader.rendered_body_html
    assert 'data-width="50"' in reader.rendered_body_html

    revision_count = ArticleRevision.objects.filter(article_id=saved.article_id).count()
    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=actor.id,
            article_id=saved.article_id,
            expected_row_version=saved.row_version,
            snapshot=ArticleSnapshot(
                content_format=ContentFormat.TIPTAP_JSON,
                title="TipTap contract",
                body={
                    "type": "doc",
                    "content": [
                        {
                            "type": "image",
                            "attrs": {"src": f"media:{foreign_asset.id}"},
                        }
                    ],
                },
                section_id=section.section_id,
                body_asset_ids=(foreign_asset.id,),
            ),
            capacity_check=lambda: None,
        )
    assert captured.value.code == "content.media_invalid.v1"
    assert (
        ArticleRevision.objects.filter(article_id=saved.article_id).count()
        == revision_count
    )


def test_attachment_card_uses_revision_binding_metadata_across_publish_and_read(
    tmp_path,
) -> None:
    actor = _author("tiptap-attachment-contract", administrator=True)
    actor.attachment_upload_enabled = True
    actor.save(update_fields=["attachment_upload_enabled"])
    section = _section(actor, "TipTap attachment contract section")
    created = create_article(
        actor_id=actor.id,
        snapshot=_empty_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    attachment = _attachment(
        owner=actor,
        article_id=created.article_id,
        root=tmp_path,
    )
    body = {
        "type": "doc",
        "content": [
            {
                "type": "attachment",
                "attrs": {"src": f"media:{attachment.id}"},
            }
        ],
    }
    saved = save_revision(
        actor_id=actor.id,
        article_id=created.article_id,
        expected_row_version=created.row_version,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.TIPTAP_JSON,
            title="TipTap attachment card",
            body=body,
            section_id=section.section_id,
            attachment_asset_id=attachment.id,
        ),
        capacity_check=lambda: None,
    )
    clock = FrozenClock(datetime(2026, 8, 8, 6, 0, tzinfo=UTC))
    review = prepare_publication(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=actor.id,
        article_id=saved.article_id,
        revision_id=saved.revision_id,
        expected_row_version=saved.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    reader = article_for_reader(actor_id=None, article_id=saved.article_id)

    assert reader.rendered_body_html == review.sanitized_html
    assert 'data-kaj-attachment-card="true"' in reader.rendered_body_html
    assert "reader-guide.txt" in reader.rendered_body_html
    assert "TXT" in reader.rendered_body_html
    assert f'href="/_kaj/media/{attachment.id}"' in reader.rendered_body_html
    assert ArticleRevision.objects.get(pk=saved.revision_id).body_tiptap == body


def test_invalid_nested_table_is_rejected_without_creating_a_revision() -> None:
    actor = _author("tiptap-table-contract", administrator=True)
    section = _section(actor, "TipTap table contract section")
    created = create_article(
        actor_id=actor.id,
        snapshot=_empty_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    nested_table = {
        "type": "table",
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {
                        "type": "tableCell",
                        "content": [
                            {
                                "type": "table",
                                "content": [
                                    {
                                        "type": "tableRow",
                                        "content": [
                                            {
                                                "type": "tableCell",
                                                "content": [
                                                    {"type": "paragraph", "content": []}
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    with pytest.raises(ContentCommandError) as captured:
        save_revision(
            actor_id=actor.id,
            article_id=created.article_id,
            expected_row_version=created.row_version,
            snapshot=ArticleSnapshot(
                content_format=ContentFormat.TIPTAP_JSON,
                title="TipTap table contract",
                body={"type": "doc", "content": [nested_table]},
                section_id=section.section_id,
            ),
            capacity_check=lambda: None,
        )

    assert captured.value.code == "content.body_invalid.v1"
    assert ArticleRevision.objects.filter(article_id=created.article_id).count() == 1
    article = Article.objects.get(pk=created.article_id)
    assert article.row_version == created.row_version
    assert article.working_revision_id == created.revision_id


def test_editor_http_rejects_invalid_nested_table_with_422(client) -> None:
    actor = _author("tiptap-table-http", administrator=True)
    section = _section(actor, "TipTap table HTTP section")
    created = create_article(
        actor_id=actor.id,
        snapshot=_empty_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    token, _ = apps.get_model("accounts", "LoginSession").issue(
        account=actor,
        remember=False,
    )
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    url = reverse("authoring:edit", args=(created.article_id,))
    opened = client.get(url)
    assert opened.status_code == 200
    form = opened.context["editor_form"]
    inner_table = {
        "type": "table",
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {
                        "type": "tableCell",
                        "content": [{"type": "paragraph", "content": []}],
                    }
                ],
            }
        ],
    }
    outer_table = {
        "type": "table",
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {
                        "type": "tableCell",
                        "content": [inner_table],
                    }
                ],
            }
        ],
    }
    response = client.post(
        url,
        {
            "content_format": ContentFormat.TIPTAP_JSON,
            "upload_scope": form["upload_scope"].value(),
            "baseline_revision_id": form["baseline_revision_id"].value(),
            "edit_token": form["edit_token"].value(),
            "title": "TipTap table HTTP contract",
            "body": json.dumps({"type": "doc", "content": [outer_table]}),
            "summary_mode": "AUTO",
            "visibility": "PUBLIC",
            "section_id": section.section_id,
            "comments_enabled": "on",
        },
    )

    assert response.status_code == 422
    assert "正文格式不合法，请修正后重试。" in response.content.decode()
    assert ArticleRevision.objects.filter(article_id=created.article_id).count() == 1


def test_persisted_v1_revision_degrades_unsafe_links_and_missing_media() -> None:
    actor = _author("tiptap-legacy", administrator=True)
    section = _section(actor, "TipTap legacy section")
    created = create_article(
        actor_id=actor.id,
        snapshot=_empty_snapshot(section.section_id),
        capacity_check=lambda: None,
    )
    article = Article.objects.get(pk=created.article_id)
    base = ArticleRevision.objects.get(pk=created.revision_id)
    missing_media_id = new_ulid()
    legacy = ArticleRevision.objects.create(
        article=article,
        sequence=2,
        based_on=base,
        created_by=actor,
        content_format=ContentFormat.TIPTAP_JSON,
        title="Legacy TipTap",
        body_tiptap={
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "legacy",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {"href": "javascript:alert(1)"},
                                }
                            ],
                        }
                    ],
                },
                {
                    "type": "image",
                    "attrs": {"src": f"media:{missing_media_id}"},
                },
            ],
        },
        tiptap_schema_version=1,
        section_id=section.section_id,
    )
    published_at = datetime(2026, 8, 8, 5, 0, tzinfo=UTC)
    article.working_revision = legacy
    article.published_revision = legacy
    article.publication_state = Article.PublicationState.PUBLISHED
    article.published_at = published_at
    article.last_published_at = published_at
    article.row_version += 1
    article.save(
        update_fields=(
            "working_revision",
            "published_revision",
            "publication_state",
            "published_at",
            "last_published_at",
            "row_version",
            "updated_at",
        )
    )

    reader = article_for_reader(actor_id=None, article_id=article.id)
    assert "javascript:" not in reader.rendered_body_html
    assert "<a>legacy</a>" in reader.rendered_body_html
    assert "图片不可用" in reader.rendered_body_html
    assert missing_media_id not in reader.rendered_body_html

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ArticleRevision.objects.create(
                article=article,
                sequence=3,
                based_on=legacy,
                created_by=actor,
                content_format=ContentFormat.TIPTAP_JSON,
                title="Invalid schema version",
                body_tiptap={"type": "doc", "content": []},
                tiptap_schema_version=3,
                section_id=section.section_id,
            )
