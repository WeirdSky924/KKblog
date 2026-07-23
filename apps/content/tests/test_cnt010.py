import threading
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import close_old_connections

from apps.content.models import Article, ArticleRevision, Section
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    SectionCommandError,
    create_article,
    create_section,
    delete_section,
    rename_section,
    section_list,
    validate_publication_section,
)
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, author: bool = False, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if author or administrator:
        role_model.objects.create(account=account, role="AUTHOR")
    if administrator:
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _context() -> dict[str, str]:
    return {"trace_code": new_trace_code(), "client_ip": "127.0.0.1"}


def test_section_names_are_unicode_casefold_unique_under_concurrency() -> None:
    admin = _account("section-admin", administrator=True)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def create(name: str) -> None:
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            create_section(actor_id=admin.id, name=name, **_context())
        except SectionCommandError as error:
            outcomes.append(error.code)
        else:
            outcomes.append("created")
        finally:
            close_old_connections()

    workers = [
        threading.Thread(target=create, args=("Straße",)),
        threading.Thread(target=create, args=("STRASSE",)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert sorted(outcomes) == ["content.section_name_conflict.v1", "created"]
    section = Section.objects.get()
    assert section.name in {"Straße", "STRASSE"}
    assert section.normalized_name == "strasse"


def test_only_administrator_can_manage_sections_and_actions_are_audited() -> None:
    admin = _account("manage-admin", administrator=True)
    author = _account("manage-author", author=True)
    audit_model = apps.get_model("operations", "AuditEntry")

    with pytest.raises(SectionCommandError) as captured:
        create_section(actor_id=author.id, name="随笔", **_context())
    assert captured.value.code == "content.section_admin_required.v1"

    created = create_section(actor_id=admin.id, name=" 随笔 ", **_context())
    renamed = rename_section(
        actor_id=admin.id,
        section_id=created.section_id,
        name="技术",
        **_context(),
    )

    assert renamed.name == "技术"
    assert [item.name for item in section_list()] == ["技术"]
    assert list(
        audit_model.objects.order_by("created_at").values_list("action", flat=True)
    ) == ["content.section.create", "content.section.rename"]


def test_section_delete_keeps_article_and_moves_revisions_to_unknown() -> None:
    admin = _account("delete-admin", administrator=True)
    section = create_section(actor_id=admin.id, name="生活", **_context())
    article = create_article(
        actor_id=admin.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="有分区文章",
            body="正文",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    revision = ArticleRevision.objects.get(pk=article.revision_id)
    validate_publication_section(revision)

    deleted = delete_section(
        actor_id=admin.id,
        section_id=section.section_id,
        **_context(),
    )

    revision.refresh_from_db()
    assert deleted.affected_revision_count == 1
    assert Article.objects.filter(pk=article.article_id).exists()
    assert revision.section_id is None
    assert section_list() == ()
    assert not Section.objects.filter(name__icontains="未知").exists()
    with pytest.raises(SectionCommandError) as captured:
        validate_publication_section(revision)
    assert captured.value.code == "content.section_required.v1"
    validate_publication_section(revision, allow_unknown_import=True)

    audit_model = apps.get_model("operations", "AuditEntry")
    outbox_model = apps.get_model("core", "OutboxEvent")
    assert audit_model.objects.filter(action="content.section.delete").count() == 1
    assert outbox_model.objects.filter(event_type="section.changed.v1").count() == 2
