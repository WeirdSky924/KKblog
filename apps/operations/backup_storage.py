import os
import re
import shutil
from pathlib import Path
from uuid import UUID

from apps.core.ids import normalize_ulid

_ARCHIVE_KEY = re.compile(r"^(?P<backup>[0-9A-HJKMNP-TV-Z]{26})\.tar\.gz$")
_PART_KEY = re.compile(
    r"^(?P<backup>[0-9A-HJKMNP-TV-Z]{26})\."
    r"(?P<attempt>[0-9a-f]{32})\.tar\.gz\.part$"
)


class BackupStorageBoundaryError(ValueError):
    pass


class BackupStorage:
    def __init__(self, root: Path | str) -> None:
        configured = Path(root)
        if not configured.is_absolute() or configured == Path("/"):
            raise BackupStorageBoundaryError("备份根目录必须是受控绝对路径")
        configured.mkdir(mode=0o700, parents=True, exist_ok=True)
        if configured.is_symlink():
            raise BackupStorageBoundaryError("备份根目录不能是符号链接")
        self._root = configured.resolve(strict=True)
        self._work_root = self._root / ".work"
        self._work_root.mkdir(mode=0o700, exist_ok=True)
        if self._work_root.is_symlink():
            raise BackupStorageBoundaryError("备份工作目录不能是符号链接")

    @property
    def root(self) -> Path:
        return self._root

    def archive_key(self, backup_id: str) -> str:
        return f"{normalize_ulid(backup_id)}.tar.gz"

    def _attempt_key(self, attempt_token) -> str:
        try:
            return UUID(str(attempt_token)).hex
        except (AttributeError, TypeError, ValueError):
            raise BackupStorageBoundaryError("备份尝试标识无效") from None

    def _archive_path(self, archive_key: str) -> Path:
        if not isinstance(archive_key, str):
            raise BackupStorageBoundaryError("备份归档键无效")
        match = _ARCHIVE_KEY.fullmatch(archive_key)
        if match is None:
            raise BackupStorageBoundaryError("备份归档键无效")
        normalize_ulid(match.group("backup"))
        path = self._root / archive_key
        if path.is_symlink():
            raise BackupStorageBoundaryError("备份归档不能是符号链接")
        return path

    def part_path(self, backup_id: str, attempt_token) -> Path:
        path = self._root / (
            f"{normalize_ulid(backup_id)}.{self._attempt_key(attempt_token)}"
            ".tar.gz.part"
        )
        if path.is_symlink():
            raise BackupStorageBoundaryError("备份临时归档不能是符号链接")
        return path

    def _backup_work_root(self, backup_id: str) -> Path:
        path = self._work_root / normalize_ulid(backup_id)
        if path.is_symlink():
            raise BackupStorageBoundaryError("备份工作目录不能是符号链接")
        return path

    def workspace(self, backup_id: str, attempt_token) -> Path:
        return self._backup_work_root(backup_id) / self._attempt_key(attempt_token)

    def prepare_workspace(self, backup_id: str, attempt_token) -> Path:
        parent = self._backup_work_root(backup_id)
        parent.mkdir(mode=0o700, exist_ok=True)
        if parent.is_symlink():
            raise BackupStorageBoundaryError("备份工作目录不能是符号链接")
        path = self.workspace(backup_id, attempt_token)
        if path.is_symlink():
            raise BackupStorageBoundaryError("备份尝试目录不能是符号链接")
        path.mkdir(mode=0o700)
        return path

    def database_dump_path(self, backup_id: str, attempt_token) -> Path:
        return self.workspace(backup_id, attempt_token) / "database.dump"

    def open_part(self, backup_id: str, attempt_token):
        descriptor = os.open(
            self.part_path(backup_id, attempt_token),
            os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        return os.fdopen(descriptor, "w+b")

    def open_part_read(self, backup_id: str, attempt_token):
        descriptor = os.open(
            self.part_path(backup_id, attempt_token),
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        return os.fdopen(descriptor, "rb")

    def commit_part(self, backup_id: str, attempt_token) -> str:
        source = self.part_path(backup_id, attempt_token)
        archive_key = self.archive_key(backup_id)
        target = self._archive_path(archive_key)
        if target.exists():
            raise FileExistsError("备份归档已存在")
        os.rename(source, target)
        directory = os.open(self._root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return archive_key

    def discard_part(self, backup_id: str, attempt_token) -> bool:
        try:
            self.part_path(backup_id, attempt_token).unlink()
        except FileNotFoundError:
            return False
        return True

    def cleanup_workspace(self, backup_id: str, attempt_token) -> bool:
        parent = self._backup_work_root(backup_id)
        path = self.workspace(backup_id, attempt_token)
        if not path.exists():
            return False
        if path.is_symlink() or not path.is_dir():
            raise BackupStorageBoundaryError("备份工作目录无效")
        shutil.rmtree(path)
        try:
            parent.rmdir()
        except OSError:
            pass
        return True

    def incomplete_paths(self, backup_id: str) -> tuple[Path, ...]:
        identity = normalize_ulid(backup_id)
        paths = []
        for path in self._root.iterdir():
            match = _PART_KEY.fullmatch(path.name)
            if match is not None and match.group("backup") == identity:
                paths.append(path)
        work_root = self._backup_work_root(identity)
        if work_root.exists():
            paths.append(work_root)
        return tuple(sorted(paths, key=lambda item: item.as_posix()))

    def cleanup_attempts(self, backup_id: str) -> int:
        removed = 0
        for path in self.incomplete_paths(backup_id):
            if path.parent == self._work_root:
                if path.is_symlink() or not path.is_dir():
                    raise BackupStorageBoundaryError("备份工作目录无效")
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            removed += 1
        return removed

    def archive_exists(self, archive_key: str) -> bool:
        return self._archive_path(archive_key).is_file()

    def open_archive(self, archive_key: str):
        descriptor = os.open(
            self._archive_path(archive_key),
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        return os.fdopen(descriptor, "rb")

    def delete_archive(self, archive_key: str) -> bool:
        try:
            self._archive_path(archive_key).unlink()
        except FileNotFoundError:
            return False
        return True
