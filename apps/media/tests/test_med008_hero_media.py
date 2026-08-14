import base64
import subprocess
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from PIL import Image

from apps.media.errors import MediaUploadError
from apps.media.models import (
    MAX_HERO_VIDEO_BYTES,
    DetectedFormat,
    MediaAsset,
    MediaPurpose,
)
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage
from apps.media.video import VideoProbeResult, probe_video

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


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (48, 32), "#7e2637").save(output, format="PNG")
    return output.getvalue()


def _mp4_header() -> bytes:
    return b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isommp41"


def _webm_header() -> bytes:
    return (
        b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01\x42\xf7\x81\x01"
        b"\x42\xf2\x81\x04\x42\xf3\x81\x08\x42\x82\x84webm"
    )


def _result(
    detected: DetectedFormat = DetectedFormat.MP4,
    *,
    duration_ms: int = 12_000,
) -> VideoProbeResult:
    return VideoProbeResult(
        detected_mime=detected,
        extension="mp4" if detected == DetectedFormat.MP4 else "webm",
        width=1280,
        height=720,
        duration_ms=duration_ms,
    )


def _stage(
    root: Path,
    owner,
    payload: bytes,
    *,
    name: str,
    declared_content_type: str,
    video_probe=None,
) -> MediaAsset:
    kwargs = {}
    if video_probe is not None:
        kwargs["video_probe"] = video_probe
    return stage_upload(
        owner_id=owner.id,
        purpose=MediaPurpose.HERO,
        original_name=name,
        declared_content_type=declared_content_type,
        chunks=[payload],
        storage=FilesystemMediaStorage(root),
        capacity_check=lambda: None,
        **kwargs,
    )


def test_hero_image_reuses_image_sanitization_without_video_probe(
    isolated_media_root: Path,
) -> None:
    owner = _account("hero-image")

    def unexpected_probe(content: bytes, original_name: str) -> VideoProbeResult:
        del content, original_name
        raise AssertionError("Hero images must use the image sanitizer")

    asset = _stage(
        isolated_media_root,
        owner,
        _png(),
        name="hero.png",
        declared_content_type="application/octet-stream",
        video_probe=unexpected_probe,
    )

    assert asset.purpose == MediaPurpose.HERO
    assert asset.detected_mime == DetectedFormat.PNG
    assert (asset.width, asset.height) == (48, 32)
    assert asset.storage_key.startswith("site/hero/")


@pytest.mark.parametrize(
    ("payload", "name", "result"),
    [
        (_mp4_header(), "hero.mp4", _result()),
        (_webm_header(), "hero.webm", _result(DetectedFormat.WEBM)),
    ],
)
def test_hero_video_uses_probed_format_instead_of_declared_mime(
    isolated_media_root: Path,
    payload: bytes,
    name: str,
    result: VideoProbeResult,
) -> None:
    owner = _account("hero-video")
    asset = _stage(
        isolated_media_root,
        owner,
        payload,
        name=name,
        declared_content_type="image/png",
        video_probe=lambda content, original_name: result,
    )

    assert asset.detected_mime == result.detected_mime
    assert (asset.width, asset.height) == (result.width, result.height)
    assert asset.storage_key.endswith(f".{result.extension}")
    assert (isolated_media_root / asset.storage_key).read_bytes() == payload


@pytest.mark.parametrize(
    ("payload", "name", "probe_result", "expected_code"),
    [
        (_mp4_header(), "hero.webm", _result(), "media.invalid_video.v1"),
        (
            _mp4_header(),
            "hero.mp4",
            _result(DetectedFormat.WEBM),
            "media.invalid_video.v1",
        ),
        (
            _mp4_header(),
            "hero.mp4",
            _result(duration_ms=30_001),
            "media.video_duration_exceeded.v1",
        ),
    ],
)
def test_invalid_hero_video_never_persists_or_leaves_staging_files(
    isolated_media_root: Path,
    payload: bytes,
    name: str,
    probe_result: VideoProbeResult,
    expected_code: str,
) -> None:
    owner = _account("hero-invalid")
    with pytest.raises(MediaUploadError) as captured:
        _stage(
            isolated_media_root,
            owner,
            payload,
            name=name,
            declared_content_type="video/mp4",
            video_probe=lambda content, original_name: probe_result,
        )

    assert captured.value.code == expected_code
    assert not MediaAsset.objects.exists()
    assert not any(path.is_file() for path in isolated_media_root.rglob("*"))


def test_hero_video_streaming_limit_is_ten_mib_and_cleans_partial_file(
    isolated_media_root: Path,
) -> None:
    owner = _account("hero-limit")
    with pytest.raises(MediaUploadError) as captured:
        _stage(
            isolated_media_root,
            owner,
            b"x" * (MAX_HERO_VIDEO_BYTES + 1),
            name="hero.mp4",
            declared_content_type="video/mp4",
            video_probe=lambda content, original_name: _result(),
        )

    assert captured.value.code == "media.file_too_large.v1"
    assert not MediaAsset.objects.exists()
    assert not any(path.is_file() for path in isolated_media_root.rglob("*"))


@pytest.mark.parametrize(
    ("name", "expected_format"),
    [
        ("hero-sample.webm", DetectedFormat.WEBM),
        ("hero-sample.mp4", DetectedFormat.MP4),
    ],
)
def test_real_probe_reads_browser_generated_video_fixture(
    name: str,
    expected_format: DetectedFormat,
) -> None:
    fixture = Path(__file__).with_name("fixtures") / f"{name}.b64"
    content = base64.b64decode(b"".join(fixture.read_bytes().split()), validate=True)

    result = probe_video(content, name)

    assert result.detected_mime == expected_format
    assert (result.width, result.height) == (96, 54)
    assert 1_000 <= result.duration_ms <= 1_200


@pytest.mark.parametrize(
    ("content", "name"),
    [
        (_mp4_header(), "truncated.mp4"),
        (_webm_header(), "truncated.webm"),
    ],
)
def test_real_probe_rejects_truncated_container(content: bytes, name: str) -> None:
    with pytest.raises(MediaUploadError) as captured:
        probe_video(content, name)

    assert captured.value.code == "media.invalid_video.v1"


def test_probe_timeout_is_a_stable_safe_error(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        del args, kwargs
        raise subprocess.TimeoutExpired(cmd="media-probe", timeout=5)

    monkeypatch.setattr("apps.media.video.probe.subprocess.run", timeout)
    with pytest.raises(MediaUploadError) as captured:
        probe_video(_mp4_header(), "hero.mp4")

    assert captured.value.code == "media.video_probe_timeout.v1"
    assert "media-probe" not in captured.value.safe_message
