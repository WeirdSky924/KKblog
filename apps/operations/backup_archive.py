import io
import json
import os
import stat
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from apps.core.ids import normalize_ulid


class BackupArchiveError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BackupArchiveSummary:
    database_size_bytes: int
    media_size_bytes: int
    media_file_count: int


def _is_sensitive_path(path: Path, *, root: Path) -> bool:
    relative = path.relative_to(root)
    for part in relative.parts:
        lowered = part.casefold()
        if lowered == ".env" or lowered.startswith(".env."):
            return True
    name = relative.name.casefold()
    return name in {
        "credentials",
        "credentials.json",
        "id_ed25519",
        "id_rsa",
        "secrets.json",
    } or relative.suffix.casefold() in {".key", ".p12", ".pem", ".pfx"}


def _controlled_root(value: Path | str, *, backup_root: Path) -> Path:
    root = Path(value)
    if not root.is_absolute() or not root.exists() or root.is_symlink():
        raise BackupArchiveError("媒体根目录无效")
    resolved = root.resolve(strict=True)
    if not resolved.is_dir() or resolved == Path("/"):
        raise BackupArchiveError("媒体根目录无效")
    if resolved.is_relative_to(backup_root) or backup_root.is_relative_to(resolved):
        raise BackupArchiveError("媒体与备份根目录不能相互包含")
    return resolved


def _media_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for directory, names, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in names:
            candidate = base / name
            if (
                _is_sensitive_path(candidate, root=root)
                or candidate.is_symlink()
                or not candidate.is_dir()
            ):
                raise BackupArchiveError("媒体目录包含不受支持的文件类型")
        for name in filenames:
            candidate = base / name
            if _is_sensitive_path(candidate, root=root):
                raise BackupArchiveError("媒体目录包含不受支持的文件类型")
            try:
                metadata = candidate.lstat()
            except OSError:
                raise BackupArchiveError("媒体文件在归档前发生变化") from None
            if not stat.S_ISREG(metadata.st_mode):
                raise BackupArchiveError("媒体目录包含不受支持的文件类型")
            files.append(candidate)
    return tuple(sorted(files, key=lambda item: item.relative_to(root).as_posix()))


def _info(name: str, *, size: int, generated_at: datetime) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = 0o600
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = int(generated_at.timestamp())
    return info


def _add_regular_file(
    archive: tarfile.TarFile,
    *,
    path: Path,
    name: str,
    generated_at: datetime,
) -> int:
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
    except OSError:
        raise BackupArchiveError("备份源文件不可读取") from None
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
            raise BackupArchiveError("备份源文件无效")
        archive.addfile(
            _info(name, size=before.st_size, generated_at=generated_at),
            source,
        )
        after = os.fstat(source.fileno())
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise BackupArchiveError("备份源文件在归档时发生变化")
    return before.st_size


def write_backup_archive(
    stream,
    *,
    backup_id: str,
    week_id: str,
    generated_at: datetime,
    database_dump: Path,
    media_root: Path,
    backup_root: Path,
    heartbeat: Callable[[], object],
) -> BackupArchiveSummary:
    identity = normalize_ulid(backup_id)
    if not callable(heartbeat):
        raise TypeError("Backup archive heartbeat is required")
    controlled_media = _controlled_root(media_root, backup_root=backup_root)
    media_files = _media_files(controlled_media)
    try:
        database_size = database_dump.lstat().st_size
    except OSError:
        raise BackupArchiveError("数据库备份文件不存在") from None
    if database_dump.is_symlink() or database_size <= 0:
        raise BackupArchiveError("数据库备份文件无效")
    media_sizes = tuple(item.lstat().st_size for item in media_files)
    manifest = {
        "format": "kaj-server-backup",
        "version": 1,
        "backup_id": identity,
        "week_id": week_id,
        "destination": "local",
        "generated_at": generated_at.isoformat(),
        "database": {
            "path": "database.dump",
            "format": "postgres-custom",
            "size_bytes": database_size,
        },
        "media": {
            "path": "media/",
            "file_count": len(media_files),
            "size_bytes": sum(media_sizes),
        },
        "encrypted": False,
        "automatic_integrity_verified": False,
        "restore_verified": False,
    }
    payload = json.dumps(
        manifest,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    with tarfile.open(fileobj=stream, mode="w:gz", compresslevel=6) as archive:
        archive.addfile(
            _info("manifest.json", size=len(payload), generated_at=generated_at),
            io.BytesIO(payload),
        )
        heartbeat()
        actual_database_size = _add_regular_file(
            archive,
            path=database_dump,
            name="database.dump",
            generated_at=generated_at,
        )
        actual_media_size = 0
        for path in media_files:
            heartbeat()
            actual_media_size += _add_regular_file(
                archive,
                path=path,
                name=f"media/{path.relative_to(controlled_media).as_posix()}",
                generated_at=generated_at,
            )
    if actual_database_size != database_size or actual_media_size != sum(media_sizes):
        raise BackupArchiveError("备份源文件在归档时发生变化")
    return BackupArchiveSummary(
        database_size_bytes=actual_database_size,
        media_size_bytes=actual_media_size,
        media_file_count=len(media_files),
    )
