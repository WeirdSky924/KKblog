from uuid import UUID, uuid4

from ulid import ULID


def new_uuid() -> UUID:
    return uuid4()


def new_ulid() -> str:
    return str(ULID())


def normalize_ulid(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("ULID value must be a string")
    return str(ULID.from_str(value.upper()))


def is_ulid(value: str) -> bool:
    try:
        normalize_ulid(value)
    except (TypeError, ValueError):
        return False
    return True
