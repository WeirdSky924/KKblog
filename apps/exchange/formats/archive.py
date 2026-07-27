from __future__ import annotations

import os
import stat
import unicodedata
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from apps.exchange.limits import ImportLimits

_CHUNK_SIZE = 64 * 1024


class ArchiveError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _safe_parts(info: ZipInfo, limits: ImportLimits) -> tuple[str, ...]:
    raw = unicodedata.normalize("NFC", info.filename.replace("\\", "/"))
    windows = PureWindowsPath(raw)
    path = PurePosixPath(raw)
    if (
        not raw
        or "\x00" in raw
        or raw.startswith("/")
        or windows.drive
        or windows.is_absolute()
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(not part.isprintable() for part in path.parts)
    ):
        raise ArchiveError("exchange.archive_path_unsafe.v1")
    parts = path.parts
    directory_depth = len(parts) if info.is_dir() else len(parts) - 1
    if directory_depth > limits.path_depth:
        raise ArchiveError("exchange.archive_depth_limit.v1")
    return parts


def _validate_entry_type(info: ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise ArchiveError("exchange.archive_entry_unsafe.v1")
    mode = info.external_attr >> 16
    file_type = stat.S_IFMT(mode)
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
        raise ArchiveError("exchange.archive_entry_unsafe.v1")
    if info.is_dir() and file_type not in {0, stat.S_IFDIR}:
        raise ArchiveError("exchange.archive_entry_unsafe.v1")


def _validate_metadata(infos: list[ZipInfo], limits: ImportLimits) -> None:
    if len(infos) > limits.item_count:
        raise ArchiveError("exchange.archive_item_limit.v1")
    expanded = 0
    compressed = 0
    normalized_paths: set[str] = set()
    for info in infos:
        parts = _safe_parts(info, limits)
        _validate_entry_type(info)
        normalized = "/".join(parts).casefold()
        if normalized in normalized_paths:
            raise ArchiveError("exchange.archive_path_unsafe.v1")
        normalized_paths.add(normalized)
        expanded += info.file_size
        compressed += info.compress_size
        if expanded > limits.expanded_bytes:
            raise ArchiveError("exchange.archive_expanded_limit.v1")
        if info.file_size and (
            info.compress_size == 0
            or info.file_size > info.compress_size * limits.compression_ratio
        ):
            raise ArchiveError("exchange.archive_ratio_limit.v1")
    if expanded and (
        compressed == 0 or expanded > compressed * limits.compression_ratio
    ):
        raise ArchiveError("exchange.archive_ratio_limit.v1")


def _destination(root: Path, parts: tuple[str, ...]) -> Path:
    candidate = root.joinpath(*parts)
    candidate.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if candidate.is_symlink():
        raise ArchiveError("exchange.archive_path_unsafe.v1")
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError:
        raise ArchiveError("exchange.archive_path_unsafe.v1") from None
    return candidate


def extract_zip(
    archive_path: Path,
    destination_root: Path,
    *,
    limits: ImportLimits,
) -> tuple[Path, ...]:
    total_written = 0
    files: list[Path] = []
    try:
        with ZipFile(archive_path) as archive:
            infos = archive.infolist()
            _validate_metadata(infos, limits)
            for info in infos:
                parts = _safe_parts(info, limits)
                target = _destination(destination_root, parts)
                if info.is_dir():
                    target.mkdir(mode=0o700, exist_ok=False)
                    continue
                descriptor = os.open(
                    target,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                try:
                    with (
                        archive.open(info) as source,
                        os.fdopen(descriptor, "wb") as output,
                    ):
                        descriptor = -1
                        while chunk := source.read(_CHUNK_SIZE):
                            total_written += len(chunk)
                            if total_written > limits.expanded_bytes:
                                raise ArchiveError("exchange.archive_expanded_limit.v1")
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                except Exception:
                    if descriptor >= 0:
                        os.close(descriptor)
                    target.unlink(missing_ok=True)
                    raise
                files.append(target)
    except ArchiveError:
        raise
    except (BadZipFile, EOFError, OSError, RuntimeError, ValueError):
        raise ArchiveError("exchange.archive_invalid.v1") from None
    return tuple(files)
