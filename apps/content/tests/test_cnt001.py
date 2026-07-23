import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models.deletion import ProtectedError

from apps.content.models import Article, ArticleRevision

pytestmark = pytest.mark.django_db(transaction=True)


def _author(label: str = "author"):
    account_model = apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=f"{label}@kaj.test",
        password="Valid-password-1",
    )


def _article_with_revision(*, author=None):
    owner = author or _author()
    article = Article.objects.create(author=owner)
    revision = ArticleRevision.objects.create(
        article=article,
        sequence=1,
        created_by=owner,
        content_format=ArticleRevision.ContentFormat.MARKDOWN,
        title="第一篇文章",
        body_markdown="正文",
    )
    article.working_revision = revision
    article.save(update_fields=("working_revision", "updated_at"))
    return article, revision


def test_article_uses_ulids_and_orthogonal_revision_pointers() -> None:
    article, revision = _article_with_revision()

    assert len(article.id) == 26
    assert len(revision.id) == 26
    assert article.publication_state == Article.PublicationState.DRAFT
    assert article.working_revision_id == revision.id
    assert article.published_revision_id is None
    assert article.scheduled_revision_id is None
    assert article.deleted_at is None
    assert article.purge_after is None
    assert article.row_version == 0


def test_revision_sequence_is_unique_inside_an_article() -> None:
    article, revision = _article_with_revision()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ArticleRevision.objects.create(
                article=article,
                sequence=revision.sequence,
                created_by=article.author,
                content_format=ArticleRevision.ContentFormat.MARKDOWN,
                title="重复序号",
                body_markdown="正文",
            )


def test_article_revision_pointers_must_belong_to_the_same_article() -> None:
    first, _ = _article_with_revision(author=_author("pointer-owner"))
    other = Article.objects.create(author=first.author)
    foreign_revision = ArticleRevision.objects.create(
        article=other,
        sequence=1,
        created_by=first.author,
        content_format=ArticleRevision.ContentFormat.MARKDOWN,
        title="另一篇文章",
        body_markdown="正文",
    )

    first.published_revision = foreign_revision
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            first.save(update_fields=("published_revision", "updated_at"))


@pytest.mark.parametrize(
    ("content_format", "body_markdown", "body_tiptap"),
    [
        (ArticleRevision.ContentFormat.MARKDOWN, None, None),
        (ArticleRevision.ContentFormat.MARKDOWN, "正文", {"type": "doc"}),
        (ArticleRevision.ContentFormat.TIPTAP_JSON, "正文", None),
        (ArticleRevision.ContentFormat.TIPTAP_JSON, None, None),
    ],
)
def test_revision_format_requires_exactly_its_matching_body_column(
    content_format: str,
    body_markdown: str | None,
    body_tiptap: dict | None,
) -> None:
    article = Article.objects.create(author=_author(f"body-{content_format.lower()}"))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ArticleRevision.objects.create(
                article=article,
                sequence=1,
                created_by=article.author,
                content_format=content_format,
                title="正文格式",
                body_markdown=body_markdown,
                body_tiptap=body_tiptap,
            )


def test_soft_delete_timestamps_are_paired_and_ordered() -> None:
    article, _ = _article_with_revision()
    article.deleted_at = article.created_at
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            article.save(update_fields=("deleted_at", "updated_at"))


def test_author_cannot_be_changed_or_deleted_while_article_exists() -> None:
    article, _ = _article_with_revision()
    owner = article.author
    other = _author("new-owner")
    article.author = other
    with pytest.raises(ValidationError):
        article.save(update_fields=("author", "updated_at"))

    with pytest.raises(ProtectedError):
        owner.delete()


def test_revision_rows_reject_update_and_delete() -> None:
    _, revision = _article_with_revision()
    revision.title = "被篡改"
    with pytest.raises(ValidationError):
        revision.save(update_fields=("title",))
    with pytest.raises(ValidationError):
        revision.delete()


def test_database_rejects_revision_update_and_author_transfer() -> None:
    article, revision = _article_with_revision()
    other = _author("database-owner")

    with pytest.raises(IntegrityError):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE article_revision SET title = %s WHERE id = %s",
                ["被篡改", revision.id],
            )
    with pytest.raises(IntegrityError):
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE article SET author_id = %s WHERE id = %s",
                [other.id, article.id],
            )


def test_article_delete_can_cascade_immutable_revisions() -> None:
    article, revision = _article_with_revision()
    article_id = article.id
    revision_id = revision.id

    Article.objects.filter(pk=article_id).delete()

    assert not Article.objects.filter(pk=article_id).exists()
    assert not ArticleRevision.objects.filter(pk=revision_id).exists()


def test_cnt001_named_database_constraints_exist() -> None:
    expected = {
        "article_working_revision_same_article_fk",
        "article_published_revision_same_article_fk",
        "article_scheduled_revision_same_article_fk",
        "article_deletion_times_shape",
        "article_schedule_shape",
        "article_revision_sequence_unique",
        "article_revision_body_shape",
    }
    with connection.cursor() as cursor:
        rows = connection.introspection.get_constraints(cursor, "article")
        rows.update(
            connection.introspection.get_constraints(cursor, "article_revision")
        )
    assert expected <= set(rows)
