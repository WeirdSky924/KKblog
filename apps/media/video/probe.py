import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath

from apps.media.errors import MediaUploadError
from apps.media.imaging.sanitize import MAX_LONGEST_EDGE, MAX_STATIC_PIXELS
from apps.media.models.constants import DetectedFormat

MAX_HERO_VIDEO_DURATION_MS = 30_000
VIDEO_PROBE_TIMEOUT_SECONDS = 5
_WORKER = Path(__file__).with_name("worker.py")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FORMAT_BY_EXTENSION = {
    "mp4": DetectedFormat.MP4,
    "webm": DetectedFormat.WEBM,
}


@dataclass(frozen=True, slots=True)
class VideoProbeResult:
    detected_mime: DetectedFormat
    extension: str
    width: int
    height: int
    duration_ms: int


def _extension(original_name: str) -> str | None:
    if not isinstance(original_name, str):
        return None
    name = PurePath(original_name.replace("\\", "/")).name
    extension = PurePath(name).suffix.casefold().lstrip(".")
    return extension if extension in _FORMAT_BY_EXTENSION else None


def is_hero_video_name(original_name: str) -> bool:
    return _extension(original_name) is not None


def _validate_header(content: bytes, expected: DetectedFormat) -> None:
    valid = False
    if expected == DetectedFormat.MP4 and len(content) >= 16:
        box_size = int.from_bytes(content[:4], "big")
        valid = content[4:8] == b"ftyp" and 16 <= box_size <= len(content)
    elif expected == DetectedFormat.WEBM:
        header = content[:4096]
        valid = header.startswith(b"\x1a\x45\xdf\xa3") and b"\x42\x82\x84webm" in header
    if not valid:
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频文件内容与格式不匹配。",
        )


def _positive_integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not math.isfinite(number) or number < 1 or not number.is_integer():
        raise ValueError
    return int(number)


def _duration(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError
    return max(1, round(number))


def validate_video_probe(
    content: bytes,
    original_name: str,
    result: VideoProbeResult,
) -> VideoProbeResult:
    extension = _extension(original_name)
    if extension is None or not isinstance(result, VideoProbeResult):
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频文件内容与格式不匹配。",
        )
    expected = _FORMAT_BY_EXTENSION[extension]
    _validate_header(content, expected)
    if result.detected_mime != expected or result.extension != extension:
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频文件内容与格式不匹配。",
        )
    if (
        result.width < 1
        or result.height < 1
        or max(result.width, result.height) > MAX_LONGEST_EDGE
        or result.width * result.height > MAX_STATIC_PIXELS
    ):
        raise MediaUploadError(
            "media.video_dimensions_exceeded.v1",
            "视频尺寸超过安全上限。",
        )
    if not 1 <= result.duration_ms <= MAX_HERO_VIDEO_DURATION_MS:
        raise MediaUploadError(
            "media.video_duration_exceeded.v1",
            "首页视频时长不能超过 30 秒。",
        )
    return result


def _probe_environment() -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "PYTHONNOUSERSITE": "1",
    }


def _worker_payload(content: bytes) -> dict[str, object]:
    try:
        completed = subprocess.run(
            [sys.executable, str(_WORKER)],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=_PROJECT_ROOT,
            env=_probe_environment(),
            timeout=VIDEO_PROBE_TIMEOUT_SECONDS,
            check=False,
            close_fds=True,
        )
    except subprocess.TimeoutExpired:
        raise MediaUploadError(
            "media.video_probe_timeout.v1",
            "视频校验超时，请压缩后重试。",
        ) from None
    if completed.returncode != 0 or len(completed.stdout) > 4096:
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频无法安全解析，请选择其他文件。",
        )
    try:
        payload = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频无法安全解析，请选择其他文件。",
        ) from None
    if not isinstance(payload, dict):
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频无法安全解析，请选择其他文件。",
        )
    return payload


def _validated_worker_result(
    payload: dict[str, object], expected: DetectedFormat
) -> VideoProbeResult:
    general_format = str(payload.get("general_format", "")).casefold()
    detected_mime = str(payload.get("detected_mime", "")).casefold()
    video_format = str(payload.get("video_format", "")).casefold()
    codec_id = str(payload.get("codec_id", "")).casefold()
    if expected == DetectedFormat.MP4:
        valid_container = general_format == "mpeg-4" and detected_mime == "video/mp4"
        valid_codec = video_format == "avc" or codec_id.startswith("avc")
        extension = "mp4"
    else:
        valid_container = general_format == "webm" and detected_mime == "video/webm"
        valid_codec = video_format in {"vp8", "vp9", "av1"} or codec_id in {
            "v_vp8",
            "v_vp9",
            "v_av1",
        }
        extension = "webm"
    if not valid_container or not valid_codec:
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频编码或容器格式不受支持。",
        )
    try:
        width = _positive_integer(payload.get("width"))
        height = _positive_integer(payload.get("height"))
        duration_ms = _duration(payload.get("duration_ms"))
    except (TypeError, ValueError, OverflowError):
        raise MediaUploadError(
            "media.invalid_video.v1",
            "视频缺少有效的尺寸或时长信息。",
        ) from None
    return VideoProbeResult(expected, extension, width, height, duration_ms)


def probe_video(content: bytes, original_name: str) -> VideoProbeResult:
    extension = _extension(original_name)
    if extension is None or not isinstance(content, bytes):
        raise MediaUploadError(
            "media.format_not_allowed.v1",
            "首页视频仅支持 MP4 和 WebM 格式。",
        )
    expected = _FORMAT_BY_EXTENSION[extension]
    _validate_header(content, expected)
    result = _validated_worker_result(_worker_payload(content), expected)
    return validate_video_probe(content, original_name, result)
