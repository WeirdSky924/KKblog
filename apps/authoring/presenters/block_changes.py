from dataclasses import dataclass

from apps.content.public import BlockChangeSummary


@dataclass(frozen=True, slots=True)
class BlockChangePresentation:
    available: bool
    before_blocks: int
    after_blocks: int
    labels: tuple[str, ...]


def block_change_presentation(
    summary: BlockChangeSummary,
) -> BlockChangePresentation:
    if not isinstance(summary, BlockChangeSummary):
        raise TypeError("block change summary is required")
    labels = []
    for count, label in (
        (summary.added_blocks, "新增 {count} 个块"),
        (summary.deleted_blocks, "删除 {count} 个块"),
        (summary.moved_blocks, "移动 {count} 个块"),
        (summary.type_changed_blocks, "{count} 个块类型变化"),
        (summary.content_changed_blocks, "修改 {count} 个块"),
    ):
        if count:
            labels.append(label.format(count=count))
    return BlockChangePresentation(
        available=summary.available,
        before_blocks=summary.before_blocks,
        after_blocks=summary.after_blocks,
        labels=tuple(labels),
    )


__all__ = [
    "BlockChangePresentation",
    "block_change_presentation",
]
