from dataclasses import dataclass
from enum import StrEnum

from apps.core.ids import normalize_ulid

GUESTBOOK_TARGET_ID = "site"


class DiscussionTargetType(StrEnum):
    ARTICLE = "ARTICLE"
    GUESTBOOK = "GUESTBOOK"


class DiscussionTargetError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DiscussionTarget:
    target_type: DiscussionTargetType
    target_id: str


def normalize_target(target_type, target_id: str) -> DiscussionTarget:
    try:
        normalized_type = DiscussionTargetType(target_type)
    except (TypeError, ValueError):
        raise DiscussionTargetError("讨论目标类型无效") from None
    if normalized_type is DiscussionTargetType.ARTICLE:
        try:
            normalized_id = normalize_ulid(target_id)
        except (TypeError, ValueError):
            raise DiscussionTargetError("文章讨论目标无效") from None
    elif target_id == GUESTBOOK_TARGET_ID:
        normalized_id = GUESTBOOK_TARGET_ID
    else:
        raise DiscussionTargetError("留言板讨论目标无效")
    return DiscussionTarget(normalized_type, normalized_id)


def registered_target_types() -> tuple[str, ...]:
    return tuple(item.value for item in DiscussionTargetType)
