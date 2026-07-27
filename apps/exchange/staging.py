from __future__ import annotations

import os
import re
import shutil
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path, PurePosixPath

from apps.core.ids import is_ulid

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_EXTENSION = re.compile(r"^(?:png|jpg|gif|webp)$")


class ImportStagingError(ValueError):
    pass


class ImportStaging:
    def __init__(self, root: Path | str) -> None:
        configured = Path(root)
        if not configured.is_absolute():
            raise ImportStagingError("Import staging root must be absolute")
        configured.mkdir(mode=0o700, parents=True, exist_ok=True)
        if configured.is_symlink():
            raise ImportStagingError("Import staging root cannot be a symlink")
        self._root = configured.resolve(strict=True)

    @property
    def root(self) -> Path:
        return self._root

    def job_root(self, job_id: str, *, create: bool = False) -> Path:
        if not is_ulid(job_id):
            raise ImportStagingError("Import job id is invalid")
        candidate = self._root / job_id
        if create:
            candidate.mkdir(mode=0o700, exist_ok=True)
        if candidate.is_symlink():
            raise ImportStagingError("Import job root cannot be a symlink")
        try:
            candidate.resolve(strict=False).relative_to(self._root)
        except ValueError:
            raise ImportStagingError("Import job root escapes staging") from None
        return candidate

    def stage_source(
        self,
        job_id: str,
        chunks: Iterable[bytes],
        *,
        max_bytes: int,
    ) -> Path:
        job_root = self.job_root(job_id, create=True)
        source_root = job_root / "source"
        source_root.mkdir(mode=0o700, exist_ok=False)
        path = source_root / "upload.part"
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
                        raise TypeError("Import source chunks must be bytes")
                    total += len(chunk)
                    if total > max_bytes:
                        raise ImportStagingError("Import source exceeds size limit")
                    stream.write(chunk)
                if total < 1:
                    raise ImportStagingError("Import source is empty")
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            self.cleanup_job(job_id)
            raise
        return path

    def extraction_root(self, job_id: str) -> Path:
        source_root = self.job_root(job_id) / "source"
        destination = source_root / "unpacked"
        destination.mkdir(mode=0o700, exist_ok=False)
        return destination

    def store_preview_image(
        self,
        job_id: str,
        *,
        digest: str,
        extension: str,
        content: bytes,
    ) -> str:
        if _DIGEST.fullmatch(digest) is None or _EXTENSION.fullmatch(extension) is None:
            raise ImportStagingError("Validated image metadata is invalid")
        if not isinstance(content, bytes) or not content:
            raise ImportStagingError("Validated image content is invalid")
        if sha256(content).hexdigest() != digest:
            raise ImportStagingError("Validated image digest does not match")
        image_root = self.job_root(job_id, create=True) / "preview-media"
        image_root.mkdir(mode=0o700, exist_ok=True)
        path = image_root / f"{digest}.{extension}"
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                raise ImportStagingError("Preview image path is inconsistent")
        else:
            descriptor = os.open(
                path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        return PurePosixPath(job_id, "preview-media", path.name).as_posix()

    def read_preview_image(
        self,
        job_id: str,
        *,
        staging_key: str,
        digest: str,
    ) -> bytes:
        if _DIGEST.fullmatch(digest) is None:
            raise ImportStagingError("Preview image digest is invalid")
        expected_prefix = PurePosixPath(job_id, "preview-media")
        try:
            relative = PurePosixPath(staging_key)
        except TypeError:
            raise ImportStagingError("Preview image key is invalid") from None
        if (
            relative.parent != expected_prefix
            or relative.name.split(".", 1)[0] != digest
        ):
            raise ImportStagingError("Preview image key is invalid")
        path = self.job_root(job_id) / "preview-media" / relative.name
        try:
            if path.is_symlink() or not path.is_file():
                raise OSError
            content = path.read_bytes()
        except OSError:
            raise ImportStagingError("Preview image is unavailable") from None
        if sha256(content).hexdigest() != digest:
            raise ImportStagingError("Preview image digest does not match")
        return content

    def cleanup_source(self, job_id: str) -> None:
        source_root = self.job_root(job_id) / "source"
        if source_root.is_symlink():
            raise ImportStagingError("Import source root cannot be a symlink")
        shutil.rmtree(source_root, ignore_errors=False)

    def cleanup_job(self, job_id: str) -> None:
        job_root = self.job_root(job_id)
        if not job_root.exists():
            return
        if job_root.is_symlink():
            raise ImportStagingError("Import job root cannot be a symlink")
        shutil.rmtree(job_root)
