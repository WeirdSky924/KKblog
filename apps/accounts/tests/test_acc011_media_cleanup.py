from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from PIL import Image

from apps.accounts.deletion import (
    AccountDeletionDisposition,
    AuthorArticleDecision,
)
from apps.accounts.services.lifecycle import delete_account
from apps.core.ids import new_ulid
from apps.media.public import (
    BindingInput,
    MediaPurpose,
    MediaTargetType,
    replace_bindings,
    stage_upload,
)
from apps.media.storage import FilesystemMediaStorage

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, administrator: bool = False):
    account_model = apps.get_model("accounts", "Account")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if administrator:
        role_model = apps.get_model("accounts", "RoleAssignment")
        role_model.objects.create(account=account, role="AUTHOR")
        role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _asset(owner, root: Path):
    output = BytesIO()
    Image.new("RGB", (24, 18), "#7e2637").save(output, format="PNG")
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.AVATAR,
        original_name="account-cleanup.png",
        declared_content_type="image/png",
        chunks=[output.getvalue()],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
    )


def test_account_deletion_rollback_retains_media_then_commit_cleans_it(
    isolated_media_root: Path,
) -> None:
    administrator = _account("cleanup-admin", administrator=True)
    owner = _account("cleanup-account")
    asset = _asset(owner, isolated_media_root)
    replace_bindings(
        actor_id=owner.id,
        target_type=MediaTargetType.ACCOUNT_PROFILE,
        target_id=str(owner.id),
        inputs=(BindingInput(asset.id, "avatar"),),
        purpose=MediaPurpose.AVATAR,
    )
    disposition = AccountDeletionDisposition(
        disposition_id=new_ulid(),
        account_id=owner.id,
        decision=AuthorArticleDecision.NO_ARTICLES,
        article_count=0,
    )
    arguments = {
        "actor_id": administrator.id,
        "account_id": owner.id,
        "author_disposition": disposition,
        "verify_author_disposition": lambda value: value == disposition,
        "client_ip": "127.0.0.1",
        "trace_code": "trc_01ky0000000000000000000000",
        "audit_writer": lambda **values: values,
    }
    storage = FilesystemMediaStorage(isolated_media_root)

    with pytest.raises(IntegrityError), transaction.atomic():
        owner.delete()
    owner.refresh_from_db()
    asset.refresh_from_db()
    assert asset.owner_id == owner.id
    assert asset.state == "ACTIVE"

    with pytest.raises(RuntimeError), transaction.atomic():
        delete_account(**arguments)
        assert storage.exists(asset.storage_key)
        raise RuntimeError("rollback account deletion")
    owner.refresh_from_db()
    asset.refresh_from_db()
    assert asset.state == "ACTIVE"
    assert asset.owner_id == owner.id
    assert asset.bindings.exists()
    assert storage.exists(asset.storage_key)

    delete_account(**arguments)
    asset.refresh_from_db()
    assert asset.owner_id is None
    assert asset.state == "DELETED"
    assert not asset.bindings.exists()
    assert not storage.exists(asset.storage_key)
