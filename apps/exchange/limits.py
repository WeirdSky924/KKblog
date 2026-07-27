from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImportLimits:
    compressed_bytes: int
    expanded_bytes: int
    item_count: int
    path_depth: int
    compression_ratio: int
    body_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.compressed_bytes,
            self.expanded_bytes,
            self.item_count,
            self.path_depth,
            self.compression_ratio,
            self.body_bytes,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in values
        ):
            raise ValueError("Import limits must be positive integers")


DEFAULT_IMPORT_LIMITS = ImportLimits(
    compressed_bytes=64 * 1024 * 1024,
    expanded_bytes=256 * 1024 * 1024,
    item_count=1000,
    path_depth=8,
    compression_ratio=100,
    body_bytes=2 * 1024 * 1024,
)
