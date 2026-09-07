from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.core.ids import new_ulid
from apps.media.models import (
    MAX_KNOWLEDGE_DOCUMENT_BYTES,
    DetectedFormat,
    MediaAsset,
    MediaPurpose,
    MediaState,
    MediaTargetType,
)
from apps.media.public import (
    BindingInput,
    MediaAccessError,
    MediaBindingError,
    MediaTextReadError,
    MediaUploadError,
    TargetAccessDecision,
    authorize_asset_read,
    bind_assets,
    release_target_assets,
    stage_upload,
    stream_authorized_text,
)
from apps.media.storage import FilesystemMediaStorage, StorageWriteError
from apps.media.targets import TargetAccessRegistry

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, attachment_capability: bool = False):
    account_model = apps.get_model("accounts", "Account")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    if attachment_capability:
        role_model = apps.get_model("accounts", "RoleAssignment")
        role_model.objects.create(account=account, role="AUTHOR")
        account.attachment_upload_enabled = True
        account.save(update_fields=("attachment_upload_enabled", "updated_at"))
    return account


def _authenticate(client, account) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=account, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token


def _stage(
    root: Path,
    owner,
    content: bytes,
    *,
    original_name: str = "knowledge.md",
) -> MediaAsset:
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.KNOWLEDGE_DOCUMENT,
        original_name=original_name,
        declared_content_type="application/octet-stream",
        chunks=(
            content[index : index + 8192] for index in range(0, len(content), 8192)
        ),
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
    )


def _target_registry(owner_id, target_id: str) -> TargetAccessRegistry:
    registry = TargetAccessRegistry()

    def decide(request):
        exists = request.target_id == target_id
        owner = exists and request.actor_id == owner_id
        return TargetAccessDecision(
            exists=exists,
            can_bind=owner,
            can_read=owner,
            public_immutable=False,
            binding_scope=target_id if exists else None,
        )

    registry.register(MediaTargetType.LEARNING_DOCUMENT, decide)
    return registry


def test_knowledge_upload_adapter_requires_current_attachment_capability(
    client,
    isolated_media_root: Path,
) -> None:
    denied = _account("knowledge-denied")
    _authenticate(client, denied)
    response = client.post(
        reverse("media:upload", kwargs={"adapter": "knowledge-document"}),
        {"file": SimpleUploadedFile("notes.md", b"# Notes\n", "text/markdown")},
    )
    assert response.status_code == 404
    assert not MediaAsset.objects.exists()

    allowed = _account("knowledge-allowed", attachment_capability=True)
    _authenticate(client, allowed)
    response = client.post(
        reverse("media:upload", kwargs={"adapter": "knowledge-document"}),
        {"file": SimpleUploadedFile("notes.md", b"# Notes\n", "text/markdown")},
    )
    asset = MediaAsset.objects.get(owner=allowed)
    assert response.status_code == 201
    assert "知识文档已通过校验" in response.content.decode("utf-8")
    assert asset.purpose == MediaPurpose.KNOWLEDGE_DOCUMENT
    assert asset.detected_mime == DetectedFormat.MARKDOWN
    assert asset.width is None and asset.height is None
    assert asset.original_name == "notes.md"
    assert "notes" not in asset.storage_key
    assert (isolated_media_root / asset.storage_key).is_file()


def test_knowledge_upload_storage_failure_returns_safe_retryable_partial(
    client,
    monkeypatch,
    isolated_media_root: Path,
) -> None:
    owner = _account("knowledge-storage-failure", attachment_capability=True)
    _authenticate(client, owner)

    def fail_stage_upload(**kwargs):
        del kwargs
        raise StorageWriteError("private filesystem detail")

    monkeypatch.setattr(
        "apps.media.presentation.upload_views.stage_upload", fail_stage_upload
    )
    response = client.post(
        reverse("media:upload", kwargs={"adapter": "knowledge-document"}),
        {"file": SimpleUploadedFile("notes.md", b"# Notes\n", "text/markdown")},
    )

    body = response.content.decode("utf-8")
    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "no-store"
    assert 'data-media-upload-result="error"' in body
    assert "知识文档暂时无法保存，请稍后重试。" in body
    assert "图片上传未完成" not in body
    assert "private filesystem detail" not in body
    assert not MediaAsset.objects.exists()


def test_knowledge_upload_frontend_uses_document_label() -> None:
    project_root = Path(__file__).resolve().parents[3]
    upload_script = (project_root / "static/src/media-upload.js").read_text(
        encoding="utf-8"
    )
    assert 'mediaLabel === "知识文档"' in upload_script
    assert '? "知识文档"' in upload_script


def test_storage_commit_wraps_parent_write_failure(
    isolated_media_root: Path,
    monkeypatch,
) -> None:
    owner = _account("knowledge-storage-commit", attachment_capability=True)
    storage = FilesystemMediaStorage(isolated_media_root)
    staged = storage.stage([b"# Notes\n"], max_bytes=1024)

    def fail_path(*args, **kwargs):
        del args, kwargs
        raise PermissionError("private filesystem detail")

    monkeypatch.setattr(storage, "_path", fail_path)
    with pytest.raises(StorageWriteError):
        storage.commit(
            staged,
            f"users/{owner.id}/knowledge-documents/{staged.token}.md",
        )


@pytest.mark.parametrize(
    ("name", "content", "expected_code"),
    [
        ("notes.txt", b"# Notes\n", "media.format_not_allowed.v1"),
        ("notes.md.exe", b"# Notes\n", "media.format_not_allowed.v1"),
        ("notes.md", b"bad\x00text", "media.invalid_knowledge_document.v1"),
        ("notes.md", b"\xff\xfe", "media.invalid_knowledge_document.v1"),
        ("notes.md", b"", "media.empty_knowledge_document.v1"),
        ("notes.md", b"\xef\xbb\xbf \r\n\t", "media.empty_knowledge_document.v1"),
        ("../notes.md", b"# Notes\n", "media.invalid_knowledge_document.v1"),
    ],
)
def test_knowledge_upload_rejects_disguised_or_invalid_text(
    isolated_media_root: Path,
    name: str,
    content: bytes,
    expected_code: str,
) -> None:
    owner = _account("knowledge-invalid", attachment_capability=True)

    with pytest.raises(MediaUploadError) as captured:
        _stage(isolated_media_root, owner, content, original_name=name)

    assert getattr(captured.value, "code", None) == expected_code
    assert not MediaAsset.objects.exists()
    assert not any(path.is_file() for path in isolated_media_root.rglob("*"))


def test_knowledge_upload_enforces_exact_two_mib_limit(
    isolated_media_root: Path,
) -> None:
    owner = _account("knowledge-size", attachment_capability=True)
    exact = b"# Notes\n" + b"a" * (MAX_KNOWLEDGE_DOCUMENT_BYTES - 8)

    asset = _stage(isolated_media_root, owner, exact)
    assert asset.size_bytes == MAX_KNOWLEDGE_DOCUMENT_BYTES

    with pytest.raises(MediaUploadError) as captured:
        _stage(isolated_media_root, owner, exact + b"a")
    assert getattr(captured.value, "code", None) == "media.file_too_large.v1"
    assert MediaAsset.objects.count() == 1


@pytest.mark.parametrize(
    ("detected_mime", "size_bytes", "width", "height"),
    [
        (DetectedFormat.PNG, 12, None, None),
        (
            DetectedFormat.MARKDOWN,
            MAX_KNOWLEDGE_DOCUMENT_BYTES + 1,
            None,
            None,
        ),
        (DetectedFormat.MARKDOWN, 12, 1, 1),
    ],
)
def test_database_rejects_invalid_knowledge_metadata(
    detected_mime: DetectedFormat,
    size_bytes: int,
    width: int | None,
    height: int | None,
) -> None:
    owner = _account("knowledge-constraint", attachment_capability=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        MediaAsset.objects.create(
            id=new_ulid(),
            owner=owner,
            purpose=MediaPurpose.KNOWLEDGE_DOCUMENT,
            storage_key=f"users/{owner.id}/knowledge-documents/{new_ulid()}.md",
            original_name="knowledge.md",
            detected_mime=detected_mime,
            size_bytes=size_bytes,
            sha256="a" * 64,
            width=width,
            height=height,
            state=MediaState.ACTIVE,
        )


def test_knowledge_binding_stream_and_cleanup_are_isolated(
    isolated_media_root: Path,
) -> None:
    owner = _account("knowledge-stream", attachment_capability=True)
    stranger = _account("knowledge-stranger", attachment_capability=True)
    target_id = new_ulid()
    content = "\ufeff# 标题\n\n正文内容\n"
    storage = FilesystemMediaStorage(isolated_media_root)
    asset = _stage(isolated_media_root, owner, content.encode())
    registry = _target_registry(owner.id, target_id)

    with pytest.raises(MediaAccessError):
        authorize_asset_read(actor_id=owner.id, asset_id=asset.id, registry=registry)

    bindings = bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.LEARNING_DOCUMENT,
        target_id=target_id,
        inputs=(BindingInput(asset.id, "source"),),
        registry=registry,
    )
    assert len(bindings) == 1
    assert bindings[0].slot == "source"

    with pytest.raises(MediaAccessError):
        with stream_authorized_text(
            actor_id=stranger.id,
            asset_id=asset.id,
            storage=storage,
            registry=registry,
        ):
            pytest.fail("unauthorized text must not be exposed")

    with stream_authorized_text(
        actor_id=owner.id,
        asset_id=asset.id,
        storage=storage,
        registry=registry,
    ) as opened:
        assert opened.asset_id == asset.id
        assert opened.original_name == "knowledge.md"
        assert opened.size_bytes == len(content.encode())
        assert opened.sha256 == asset.sha256
        assert not hasattr(opened, "storage_key")
        assert "".join(opened.chunks) == content

    second = _stage(isolated_media_root, owner, b"# Second\n")
    with pytest.raises(MediaBindingError) as slot_conflict:
        bind_assets(
            actor_id=owner.id,
            target_type=MediaTargetType.LEARNING_DOCUMENT,
            target_id=target_id,
            inputs=(BindingInput(second.id, "source"),),
            registry=registry,
        )
    assert slot_conflict.value.code == "media.binding_slot_conflict.v1"

    released = release_target_assets(
        target_type=MediaTargetType.LEARNING_DOCUMENT,
        target_ids=(target_id,),
        storage=storage,
    )
    asset.refresh_from_db()
    assert released.pending_asset_ids == (asset.id,)
    assert asset.state == MediaState.DELETED
    assert not storage.exists(asset.storage_key)


def test_stream_rejects_tampered_bytes_before_exposing_text(
    isolated_media_root: Path,
) -> None:
    owner = _account("knowledge-tamper", attachment_capability=True)
    target_id = new_ulid()
    storage = FilesystemMediaStorage(isolated_media_root)
    asset = _stage(isolated_media_root, owner, b"# Trusted\n")
    registry = _target_registry(owner.id, target_id)
    bind_assets(
        actor_id=owner.id,
        target_type=MediaTargetType.LEARNING_DOCUMENT,
        target_id=target_id,
        inputs=(BindingInput(asset.id, "source"),),
        registry=registry,
    )
    (isolated_media_root / asset.storage_key).write_bytes(b"\xff" * asset.size_bytes)

    with pytest.raises(MediaTextReadError) as captured:
        with stream_authorized_text(
            actor_id=owner.id,
            asset_id=asset.id,
            storage=storage,
            registry=registry,
        ):
            pytest.fail("tampered text must not be exposed")
    assert asset.storage_key not in str(captured.value)
