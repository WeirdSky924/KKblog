import warnings
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from apps.media.errors import MediaUploadError
from apps.media.models import DetectedFormat, MediaPurpose

MAX_LONGEST_EDGE = 8192
MAX_STATIC_PIXELS = 25_000_000
MAX_ANIMATED_FRAMES = 200
MAX_ANIMATED_PIXELS = 100_000_000

_PIL_FORMATS = {
    "PNG": DetectedFormat.PNG,
    "JPEG": DetectedFormat.JPEG,
    "GIF": DetectedFormat.GIF,
    "WEBP": DetectedFormat.WEBP,
    "ICO": DetectedFormat.ICO,
}
_ORDINARY_FORMATS = {
    DetectedFormat.PNG,
    DetectedFormat.JPEG,
    DetectedFormat.GIF,
    DetectedFormat.WEBP,
}
_EXTENSIONS = {
    DetectedFormat.PNG: "png",
    DetectedFormat.JPEG: "jpg",
    DetectedFormat.GIF: "gif",
    DetectedFormat.WEBP: "webp",
    DetectedFormat.ICO: "ico",
}


@dataclass(frozen=True, slots=True)
class SanitizedImage:
    content: bytes
    detected_mime: DetectedFormat
    extension: str
    width: int
    height: int
    frame_count: int


def validate_decoded_limits(frame_sizes: list[tuple[int, int]]) -> None:
    if not frame_sizes or len(frame_sizes) > MAX_ANIMATED_FRAMES:
        raise MediaUploadError(
            "media.decode_limit_exceeded.v1", "图片帧数超过安全上限。"
        )
    total_pixels = 0
    for width, height in frame_sizes:
        if width < 1 or height < 1 or max(width, height) > MAX_LONGEST_EDGE:
            raise MediaUploadError(
                "media.decode_limit_exceeded.v1", "图片尺寸超过安全上限。"
            )
        pixels = width * height
        if pixels > MAX_STATIC_PIXELS:
            raise MediaUploadError(
                "media.decode_limit_exceeded.v1", "图片像素超过安全上限。"
            )
        total_pixels += pixels
    limit = MAX_STATIC_PIXELS if len(frame_sizes) == 1 else MAX_ANIMATED_PIXELS
    if total_pixels > limit:
        raise MediaUploadError(
            "media.decode_limit_exceeded.v1", "图片解码量超过安全上限。"
        )


def _allowed_format(purpose: MediaPurpose, detected: DetectedFormat) -> None:
    allowed = (
        {DetectedFormat.PNG, DetectedFormat.ICO}
        if purpose == MediaPurpose.LOGO
        else _ORDINARY_FORMATS
    )
    if detected not in allowed:
        raise MediaUploadError(
            "media.format_not_allowed.v1", "此用途不支持该图片格式。"
        )


def _frame_copies(image: Image.Image, start: int, stop: int) -> Iterator[Image.Image]:
    for index in range(start, stop):
        image.seek(index)
        yield image.convert("RGBA").copy()


def _encode_animation(
    image: Image.Image,
    detected: DetectedFormat,
    durations: list[int],
) -> bytes:
    image.seek(0)
    first = image.convert("RGBA").copy()
    output = BytesIO()
    common = {
        "save_all": True,
        "append_images": _frame_copies(image, 1, image.n_frames),
        "duration": durations,
        "loop": int(image.info.get("loop", 0)),
    }
    if detected == DetectedFormat.GIF:
        first.save(output, format="GIF", disposal=2, optimize=True, **common)
    elif detected == DetectedFormat.WEBP:
        first.save(output, format="WEBP", lossless=True, method=4, **common)
    elif detected == DetectedFormat.PNG:
        first.save(output, format="PNG", disposal=2, blend=0, optimize=True, **common)
    else:
        raise MediaUploadError("media.format_not_allowed.v1", "此动画格式不受支持。")
    return output.getvalue()


def _encode_static(image: Image.Image, detected: DetectedFormat) -> bytes:
    image.seek(0)
    normalized = ImageOps.exif_transpose(image)
    output = BytesIO()
    if detected == DetectedFormat.JPEG:
        normalized.convert("RGB").save(
            output, format="JPEG", quality=90, optimize=True, progressive=True
        )
    elif detected == DetectedFormat.PNG:
        normalized.convert("RGBA").save(output, format="PNG", optimize=True)
    elif detected == DetectedFormat.GIF:
        normalized.convert("P", palette=Image.Palette.ADAPTIVE).save(
            output, format="GIF", optimize=True
        )
    elif detected == DetectedFormat.WEBP:
        normalized.convert("RGBA").save(output, format="WEBP", lossless=True, method=4)
    elif detected == DetectedFormat.ICO:
        normalized.convert("RGBA").save(output, format="ICO", sizes=[normalized.size])
    else:
        raise MediaUploadError("media.invalid_image.v1", "无法识别图片格式。")
    return output.getvalue()


def sanitize_image(stream, purpose: MediaPurpose | str) -> SanitizedImage:
    try:
        normalized_purpose = MediaPurpose(purpose)
    except (TypeError, ValueError):
        raise MediaUploadError("media.purpose_invalid.v1", "图片用途不合法。") from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(stream) as image:
                detected = _PIL_FORMATS.get(image.format or "")
                if detected is None:
                    raise MediaUploadError(
                        "media.format_not_allowed.v1", "不支持该图片格式。"
                    )
                _allowed_format(normalized_purpose, detected)
                frame_sizes: list[tuple[int, int]] = []
                durations: list[int] = []
                frame_count = getattr(image, "n_frames", 1)
                if not 1 <= frame_count <= MAX_ANIMATED_FRAMES:
                    raise MediaUploadError(
                        "media.decode_limit_exceeded.v1",
                        "图片帧数超过安全上限。",
                    )
                for index in range(frame_count):
                    image.seek(index)
                    frame_sizes.append(image.size)
                    validate_decoded_limits(frame_sizes)
                    durations.append(
                        max(10, min(int(image.info.get("duration", 100)), 60_000))
                    )
                    image.load()
                validate_decoded_limits(frame_sizes)
                if len(frame_sizes) > 1:
                    content = _encode_animation(image, detected, durations)
                else:
                    content = _encode_static(image, detected)
    except MediaUploadError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
    ):
        raise MediaUploadError(
            "media.invalid_image.v1", "图片无法安全解码，请选择其他文件。"
        ) from None
    width, height = frame_sizes[0]
    return SanitizedImage(
        content=content,
        detected_mime=detected,
        extension=_EXTENSIONS[detected],
        width=width,
        height=height,
        frame_count=len(frame_sizes),
    )
