import os
from collections.abc import Iterable
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from django.core.exceptions import ValidationError

from apps.core.ids import is_ulid, new_ulid
from apps.media.models.asset import validate_storage_key

from .port import (
    StagedMedia,
    StorageBoundaryError,
    StorageEmptyFile,
    StorageLimitExceeded,
    StorageWriteError,
)


class FilesystemMediaStorage:
    def __init__(self, root: Path | str) -> None:
        configured = Path(root)
        if not configured.is_absolute():
            raise StorageBoundaryError("媒体根目录必须是绝对路径")
        configured.mkdir(mode=0o700, parents=True, exist_ok=True)
        if configured.is_symlink():
            raise StorageBoundaryError("媒体根目录不能是符号链接")
        self._root = configured.resolve(strict=True)
        self._staging_root = self._root / ".staging"
        self._staging_root.mkdir(mode=0o700, exist_ok=True)
        if self._staging_root.is_symlink():
            raise StorageBoundaryError("媒体暂存目录不能是符号链接")

    @property
    def root(self) -> Path:
        return self._root

    def _validate_key(self, storage_key: str) -> None:
        try:
            validate_storage_key(storage_key)
        except ValidationError:
            raise StorageBoundaryError("媒体存储键越界") from None

    def _path(self, storage_key: str, *, create_parent: bool = False) -> Path:
        self._validate_key(storage_key)
        candidate = self._root.joinpath(*storage_key.split("/"))
        if create_parent:
            candidate.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            candidate.parent.resolve(strict=True).relative_to(self._root)
        except (FileNotFoundError, ValueError):
            raise StorageBoundaryError("媒体存储键越界") from None
        if candidate.is_symlink():
            raise StorageBoundaryError("媒体文件不能是符号链接")
        try:
            candidate.resolve(strict=False).relative_to(self._root)
        except ValueError:
            raise StorageBoundaryError("媒体存储键越界") from None
        return candidate

    def _staged_path(self, staged: StagedMedia) -> Path:
        if not isinstance(staged, StagedMedia) or not is_ulid(staged.token):
            raise StorageBoundaryError("媒体暂存标识不合法")
        path = self._staging_root / f"{staged.token}.part"
        if path.is_symlink():
            raise StorageBoundaryError("暂存媒体不能是符号链接")
        return path

    def stage(self, chunks: Iterable[bytes], *, max_bytes: int) -> StagedMedia:
        if (
            not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or max_bytes < 1
        ):
            raise ValueError("max_bytes 必须是正整数")
        token = new_ulid()
        path = self._staging_root / f"{token}.part"
        digest = sha256()
        total = 0
        try:
            descriptor = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise TypeError("媒体存储分块必须是 bytes")
                    total += len(chunk)
                    if total > max_bytes:
                        raise StorageLimitExceeded("媒体文件超过大小上限")
                    digest.update(chunk)
                    stream.write(chunk)
                if total < 1:
                    raise StorageEmptyFile("媒体文件不能为空")
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return StagedMedia(token=token, size_bytes=total, sha256=digest.hexdigest())

    def open_staged(self, staged: StagedMedia):
        path = self._staged_path(staged)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            raise FileNotFoundError("暂存媒体不存在") from None
        return os.fdopen(descriptor, "rb")

    def open_read(self, storage_key: str):
        path = self._path(storage_key)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            raise FileNotFoundError("媒体文件不存在") from None
        return os.fdopen(descriptor, "rb")

    def commit(self, staged: StagedMedia, storage_key: str) -> None:
        source = self._staged_path(staged)
        try:
            target = self._path(storage_key, create_parent=True)
            os.replace(source, target)
        except OSError as exc:
            raise StorageWriteError("媒体文件提交失败") from exc

    def discard(self, staged: StagedMedia) -> bool:
        path = self._staged_path(staged)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    def discard_staged_before(self, cutoff: datetime) -> int:
        if not isinstance(cutoff, datetime) or cutoff.tzinfo is None:
            raise ValueError("暂存清理时间必须包含时区")
        removed = 0
        with os.scandir(self._staging_root) as entries:
            for entry in entries:
                if entry.is_symlink():
                    raise StorageBoundaryError("暂存媒体不能是符号链接")
                token, separator, suffix = entry.name.partition(".")
                if (
                    separator != "."
                    or suffix != "part"
                    or not is_ulid(token)
                    or not entry.is_file(follow_symlinks=False)
                ):
                    raise StorageBoundaryError("暂存目录包含非受控文件")
                try:
                    modified_at = entry.stat(follow_symlinks=False).st_mtime
                except FileNotFoundError:
                    continue
                if modified_at > cutoff.timestamp():
                    continue
                try:
                    os.unlink(entry.path)
                except FileNotFoundError:
                    continue
                removed += 1
        return removed

    def write(self, storage_key: str, chunks: Iterable[bytes]) -> int:
        staged = self.stage(chunks, max_bytes=2**63 - 1)
        try:
            self.commit(staged, storage_key)
        except Exception:
            self.discard(staged)
            raise
        return staged.size_bytes

    def read(self, storage_key: str) -> bytes:
        path = self._path(storage_key)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError("媒体文件不存在") from None

    def exists(self, storage_key: str) -> bool:
        return self._path(storage_key).is_file()

    def delete(self, storage_key: str) -> bool:
        path = self._path(storage_key)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True
