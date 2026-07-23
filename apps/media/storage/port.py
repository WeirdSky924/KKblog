from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Protocol


class StorageBoundaryError(ValueError):
    pass


class StorageWriteError(OSError):
    pass


class StorageLimitExceeded(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StagedMedia:
    token: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        if self.size_bytes < 1 or len(self.sha256) != sha256().digest_size * 2:
            raise ValueError("暂存媒体元数据不合法")


class MediaStorage(Protocol):
    def stage(self, chunks: Iterable[bytes], *, max_bytes: int) -> StagedMedia: ...

    def open_staged(self, staged: StagedMedia): ...

    def commit(self, staged: StagedMedia, storage_key: str) -> None: ...

    def discard(self, staged: StagedMedia) -> bool: ...

    def discard_staged_before(self, cutoff: datetime) -> int: ...

    def write(self, storage_key: str, chunks: Iterable[bytes]) -> int: ...

    def read(self, storage_key: str) -> bytes: ...

    def exists(self, storage_key: str) -> bool: ...

    def delete(self, storage_key: str) -> bool: ...
