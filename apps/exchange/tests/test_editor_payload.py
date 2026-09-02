from uuid import uuid4

import pytest
from django.apps import apps
from django.utils import timezone

from apps.exchange.models import ImportItem, ImportJob
from apps.exchange.services.imports import ImportPreviewError, import_editor_payload
from apps.exchange.services.processing import mark_import_job_final_failed

pytestmark = pytest.mark.django_db(transaction=True)


def _author():
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"editor-payload-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    return account


def test_import_editor_payload_orders_items_by_path_and_concatenates() -> None:
    author = _author()
    previewed_at = timezone.now()
    job = ImportJob.objects.create(
        author=author,
        source_kind=ImportJob.SourceKind.ZIP,
        source_name="bundle.zip",
        status=ImportJob.Status.PREVIEW_READY,
        preview_summary={"total": 2, "valid": 2, "invalid": 0},
        previewed_at=previewed_at,
    )
    for ordinal, path, body in (
        (2, "b.md", "# B"),
        (1, "a.md", "# A"),
    ):
        ImportItem.objects.create(
            job=job,
            ordinal=ordinal,
            item_key=f"{uuid4().hex:0<64}",
            item_path=path,
            detected_title=path,
            parse_status=ImportItem.ParseStatus.VALID,
            included=True,
            body_markdown=body,
            preview_html=f"<h1>{path}</h1>",
        )

    payload = import_editor_payload(
        actor_id=author.id,
        job_id=job.id,
        max_body_bytes=1024,
    )

    assert payload.source_name == "bundle.zip"
    assert payload.item_count == 2
    assert payload.body_markdown == "# A\n\n# B"


def test_import_editor_payload_rejects_combined_body_over_limit() -> None:
    author = _author()
    job = ImportJob.objects.create(
        author=author,
        source_kind=ImportJob.SourceKind.MARKDOWN,
        source_name="article.md",
        status=ImportJob.Status.PREVIEW_READY,
        preview_summary={"total": 1, "valid": 1, "invalid": 0},
        previewed_at=timezone.now(),
    )
    ImportItem.objects.create(
        job=job,
        ordinal=1,
        item_key=f"{uuid4().hex:0<64}",
        item_path="article.md",
        detected_title="article.md",
        parse_status=ImportItem.ParseStatus.VALID,
        included=True,
        body_markdown="# Article",
        preview_html="<h1>Article</h1>",
    )

    with pytest.raises(
        ImportPreviewError,
        match="拼接后的正文超过文章长度上限",
    ):
        import_editor_payload(
            actor_id=author.id,
            job_id=job.id,
            max_body_bytes=1,
        )


def test_final_failed_import_job_leaves_no_processing_state() -> None:
    author = _author()
    job = ImportJob.objects.create(
        author=author,
        source_kind=ImportJob.SourceKind.MARKDOWN,
        source_name="article.md",
        status=ImportJob.Status.PROCESSING,
        preview_summary={"total": 1, "valid": 1, "invalid": 0},
        previewed_at=timezone.now(),
        confirmed_preview_version=1,
        confirmed_at=timezone.now(),
    )
    item = ImportItem.objects.create(
        job=job,
        ordinal=1,
        item_key=f"{uuid4().hex:0<64}",
        item_path="article.md",
        detected_title="article.md",
        parse_status=ImportItem.ParseStatus.VALID,
        classification=ImportItem.Classification.NEW,
        decision=ImportItem.Decision.CREATE,
        included=True,
        body_markdown="# Article",
        preview_html="<h1>Article</h1>",
    )

    changed = mark_import_job_final_failed(
        job_id=job.id,
        preview_version=1,
        error_code="operations.task_unexpected.v1",
        completed_at=timezone.now(),
    )

    assert changed is True
    job.refresh_from_db()
    item.refresh_from_db()
    assert job.status == ImportJob.Status.FAILED
    assert job.error_code == "operations.task_unexpected.v1"
    assert item.result_status == ImportItem.ResultStatus.FAILED
    assert item.result_reason_code == "operations.task_unexpected.v1"
