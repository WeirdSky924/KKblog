import os
import re
from pathlib import Path

from apps.core.ids import normalize_ulid

_ARCHIVE_KEY = re.compile(r"^(?P<job>[0-9A-HJKMNP-TV-Z]{26})\.zip$")


class ExportArchiveBoundaryError(ValueError):
    pass


class ExportArchiveStorage:
    def __init__(self, root: Path | str) -> None:
        configured = Path(root)
        if not configured.is_absolute():
            raise ExportArchiveBoundaryError("导出归档根目录必须是绝对路径")
        configured.mkdir(mode=0o700, parents=True, exist_ok=True)
        if configured.is_symlink():
            raise ExportArchiveBoundaryError("导出归档根目录不能是符号链接")
        self._root = configured.resolve(strict=True)

    @property
    def root(self) -> Path:
        return self._root

    def archive_key(self, job_id: str) -> str:
        return f"{normalize_ulid(job_id)}.zip"

    def _archive_path(self, archive_key: str) -> Path:
        if not isinstance(archive_key, str):
            raise ExportArchiveBoundaryError("导出归档键无效")
        match = _ARCHIVE_KEY.fullmatch(archive_key)
        if match is None:
            raise ExportArchiveBoundaryError("导出归档键无效")
        normalize_ulid(match.group("job"))
        path = self._root / archive_key
        if path.is_symlink():
            raise ExportArchiveBoundaryError("导出归档不能是符号链接")
        return path

    def part_path(self, job_id: str) -> Path:
        path = self._root / f"{normalize_ulid(job_id)}.zip.part"
        if path.is_symlink():
            raise ExportArchiveBoundaryError("导出临时归档不能是符号链接")
        return path

    def open_part(self, job_id: str):
        path = self.part_path(job_id)
        descriptor = os.open(
            path,
            os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        return os.fdopen(descriptor, "w+b")

    def open_part_read(self, job_id: str):
        try:
            descriptor = os.open(
                self.part_path(job_id),
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
        except FileNotFoundError:
            raise FileNotFoundError("导出临时归档不存在") from None
        return os.fdopen(descriptor, "rb")

    def commit_part(self, job_id: str) -> str:
        source = self.part_path(job_id)
        archive_key = self.archive_key(job_id)
        target = self._archive_path(archive_key)
        if target.exists():
            raise FileExistsError("导出归档已存在")
        os.rename(source, target)
        directory = os.open(self._root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return archive_key

    def discard_part(self, job_id: str) -> bool:
        try:
            self.part_path(job_id).unlink()
        except FileNotFoundError:
            return False
        return True

    def archive_exists(self, archive_key: str) -> bool:
        return self._archive_path(archive_key).is_file()

    def open_archive(self, archive_key: str):
        path = self._archive_path(archive_key)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            raise FileNotFoundError("导出归档不存在") from None
        return os.fdopen(descriptor, "rb")

    def delete_archive(self, archive_key: str) -> bool:
        try:
            self._archive_path(archive_key).unlink()
        except FileNotFoundError:
            return False
        return True
