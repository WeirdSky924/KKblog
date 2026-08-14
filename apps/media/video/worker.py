import json
import os
import resource
import sys
import tempfile

from pymediainfo import MediaInfo

_MAX_INPUT_BYTES = 10 * 1024 * 1024
_MAX_ADDRESS_SPACE_BYTES = 256 * 1024 * 1024


def _limit_resources() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (_MAX_ADDRESS_SPACE_BYTES,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_FSIZE, (_MAX_INPUT_BYTES + 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


def _track_value(track, name: str):
    value = getattr(track, name, None)
    return "" if value is None else value


def _metadata(path: str) -> dict[str, object]:
    parsed = MediaInfo.parse(path, full=True, parse_speed=1.0)
    general_tracks = [track for track in parsed.tracks if track.track_type == "General"]
    video_tracks = [track for track in parsed.tracks if track.track_type == "Video"]
    if len(general_tracks) != 1 or len(video_tracks) != 1:
        raise ValueError("expected exactly one general and video track")
    general = general_tracks[0]
    video = video_tracks[0]
    return {
        "general_format": _track_value(general, "format"),
        "detected_mime": _track_value(general, "internet_media_type"),
        "video_format": _track_value(video, "format"),
        "codec_id": _track_value(video, "codec_id"),
        "width": _track_value(video, "width"),
        "height": _track_value(video, "height"),
        "duration_ms": _track_value(video, "duration")
        or _track_value(general, "duration"),
    }


def main() -> int:
    _limit_resources()
    content = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
    if not 1 <= len(content) <= _MAX_INPUT_BYTES:
        return 2
    descriptor, path = tempfile.mkstemp(prefix="kaj-hero-probe-", suffix=".media")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        payload = _metadata(path)
        sys.stdout.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
        return 0
    except Exception:
        return 2
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
