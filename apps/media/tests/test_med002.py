from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.media.imaging.sanitize import sanitize_image, validate_decoded_limits
from apps.media.models import DetectedFormat, MediaAsset, MediaPurpose, MediaState
from apps.media.services.uploads import MediaUploadError, stage_upload
from apps.media.storage.filesystem import FilesystemMediaStorage
from apps.media.storage.port import StorageLimitExceeded

pytestmark = pytest.mark.django_db(transaction=True)


def _owner():
    account_model = apps.get_model("accounts", "Account")
    return account_model.objects.create_account(
        email=f"upload-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _authenticate(client, owner) -> None:
    session_model = apps.get_model("accounts", "LoginSession")
    raw_token, _ = session_model.issue(account=owner, remember=False)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = raw_token


def _image_bytes(
    image_format: str,
    *,
    size: tuple[int, int] = (32, 24),
    exif_description: str | None = None,
) -> bytes:
    stream = BytesIO()
    image = Image.new("RGB", size, "#7e2637")
    options = {}
    if exif_description is not None:
        exif = Image.Exif()
        exif[0x010E] = exif_description
        options["exif"] = exif
    image.save(stream, format=image_format, **options)
    return stream.getvalue()


def _animated_gif() -> bytes:
    stream = BytesIO()
    frames = [
        Image.new("RGBA", (12, 12), "#7e2637"),
        Image.new("RGBA", (12, 12), "#2f6b4f"),
    ]
    frames[0].save(
        stream,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=[80, 120],
        loop=0,
    )
    return stream.getvalue()


def _many_frame_gif(frame_count: int) -> bytes:
    stream = BytesIO()
    frames = [
        Image.new("RGB", (2, 1), (index % 251, (index * 3) % 251, 30))
        for index in range(frame_count)
    ]
    frames[0].save(
        stream,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=20,
        loop=0,
        optimize=False,
    )
    return stream.getvalue()


def _upload(
    isolated_media_root: Path,
    payload: bytes,
    *,
    purpose: MediaPurpose = MediaPurpose.AVATAR,
    original_name: str = "avatar.png",
    declared_content_type: str = "image/png",
) -> MediaAsset:
    owner = _owner()
    return stage_upload(
        owner_id=owner.id,
        purpose=purpose,
        original_name=original_name,
        declared_content_type=declared_content_type,
        chunks=(
            payload[index : index + 4096] for index in range(0, len(payload), 4096)
        ),
        storage=FilesystemMediaStorage(isolated_media_root),
        capacity_check=lambda: None,
    )


def test_real_format_wins_and_jpeg_metadata_is_removed(
    isolated_media_root: Path,
) -> None:
    asset = _upload(
        isolated_media_root,
        _image_bytes("JPEG", exif_description="private location"),
        original_name="portrait.png.exe",
        declared_content_type="image/png",
    )

    asset.refresh_from_db()
    assert asset.detected_mime == DetectedFormat.JPEG
    assert asset.state == MediaState.ACTIVE
    assert asset.storage_key.endswith(".jpg")
    assert "portrait" not in asset.storage_key
    stored = (isolated_media_root / asset.storage_key).read_bytes()
    with Image.open(BytesIO(stored)) as decoded:
        assert decoded.format == "JPEG"
        assert not decoded.getexif()


def test_gif_reencoding_preserves_animation(isolated_media_root: Path) -> None:
    asset = _upload(
        isolated_media_root,
        _animated_gif(),
        original_name="motion.gif",
        declared_content_type="image/gif",
    )
    stored = (isolated_media_root / asset.storage_key).read_bytes()
    with Image.open(BytesIO(stored)) as decoded:
        assert decoded.format == "GIF"
        assert decoded.n_frames == 2
        assert decoded.info.get("loop") == 0


def test_real_decoder_applies_edge_and_frame_limits(
    isolated_media_root: Path,
) -> None:
    accepted = _upload(
        isolated_media_root,
        _image_bytes("PNG", size=(8192, 1)),
    )
    assert accepted.width == 8192

    for payload in (
        _image_bytes("PNG", size=(8193, 1)),
        _many_frame_gif(201),
    ):
        with pytest.raises(MediaUploadError) as captured:
            _upload(isolated_media_root, payload)
        assert captured.value.code == "media.decode_limit_exceeded.v1"


def test_decoder_rejects_header_limits_before_loading_pixels(monkeypatch) -> None:
    payload = _image_bytes("PNG", size=(8193, 1))
    load_calls = 0

    def unexpected_load(*args, **kwargs):
        nonlocal load_calls
        del args, kwargs
        load_calls += 1
        raise AssertionError("oversized pixels must not be loaded")

    monkeypatch.setattr(Image.Image, "load", unexpected_load)

    with pytest.raises(MediaUploadError) as captured:
        sanitize_image(BytesIO(payload), MediaPurpose.AVATAR)

    assert captured.value.code == "media.decode_limit_exceeded.v1"
    assert load_calls == 0


def test_streaming_limit_accepts_exact_size_and_rejects_one_more_byte(
    isolated_media_root: Path,
) -> None:
    storage = FilesystemMediaStorage(isolated_media_root)
    staged = storage.stage([b"x" * (2 * 1024 * 1024)], max_bytes=2 * 1024 * 1024)
    assert staged.size_bytes == 2 * 1024 * 1024
    storage.discard(staged)

    with pytest.raises(StorageLimitExceeded):
        storage.stage([b"x" * (2 * 1024 * 1024), b"x"], max_bytes=2 * 1024 * 1024)


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (b"not an image", "media.invalid_image.v1"),
        (b"x" * (2 * 1024 * 1024 + 1), "media.file_too_large.v1"),
    ],
)
def test_bad_or_oversized_upload_never_becomes_active(
    isolated_media_root: Path, payload: bytes, expected_code: str
) -> None:
    with pytest.raises(MediaUploadError) as captured:
        _upload(isolated_media_root, payload)
    assert captured.value.code == expected_code
    assert not MediaAsset.objects.exists()
    assert not any(path.is_file() for path in isolated_media_root.rglob("*"))


def test_upload_view_preserves_safe_failure_context(
    client, isolated_media_root: Path
) -> None:
    owner = _owner()
    _authenticate(client, owner)
    response = client.post(
        reverse("media:upload-avatar"),
        {"file": SimpleUploadedFile("broken-image.png", b"broken", "image/png")},
    )

    assert response.status_code == 422
    assert response.headers["Cache-Control"] == "no-store"
    assert "图片无法安全解码" in response.content.decode("utf-8")
    assert "broken-image.png" in response.content.decode("utf-8")
    assert not MediaAsset.objects.exists()


def test_upload_view_returns_only_an_active_staged_asset(
    client, isolated_media_root: Path
) -> None:
    owner = _owner()
    _authenticate(client, owner)
    response = client.post(
        reverse("media:upload-avatar"),
        {
            "file": SimpleUploadedFile(
                "actual.jpeg",
                _image_bytes("JPEG"),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 201
    asset = MediaAsset.objects.get(owner=owner)
    assert asset.state == MediaState.ACTIVE
    assert asset.id in response.content.decode("utf-8")
    assert (isolated_media_root / asset.storage_key).is_file()


def test_logo_accepts_ico_but_avatar_rejects_it(isolated_media_root: Path) -> None:
    ico = _image_bytes("ICO", size=(32, 32))
    logo = _upload(
        isolated_media_root,
        ico,
        purpose=MediaPurpose.LOGO,
        original_name="site.ico",
        declared_content_type="image/x-icon",
    )
    assert logo.detected_mime == DetectedFormat.ICO

    with pytest.raises(MediaUploadError) as captured:
        _upload(isolated_media_root, ico, purpose=MediaPurpose.AVATAR)
    assert captured.value.code == "media.format_not_allowed.v1"


@pytest.mark.parametrize(
    "frame_sizes",
    [
        [(8192, 1)],
        [(5000, 5000)],
        [(1000, 500)] * 200,
    ],
)
def test_decode_limits_accept_exact_boundaries(
    frame_sizes: list[tuple[int, int]],
) -> None:
    validate_decoded_limits(frame_sizes)


@pytest.mark.parametrize(
    "frame_sizes",
    [
        [(8193, 1)],
        [(5001, 5000)],
        [(1, 1)] * 201,
        [(1000, 501)] * 200,
    ],
)
def test_decode_limits_reject_values_above_boundaries(
    frame_sizes: list[tuple[int, int]],
) -> None:
    with pytest.raises(MediaUploadError) as captured:
        validate_decoded_limits(frame_sizes)
    assert captured.value.code == "media.decode_limit_exceeded.v1"
