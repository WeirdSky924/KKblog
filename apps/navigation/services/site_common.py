import unicodedata
from uuid import UUID

from apps.accounts.public import is_administrator


class SiteContentCommandError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


def require_administrator(value) -> UUID:
    try:
        actor_id = UUID(str(value))
    except (TypeError, ValueError):
        raise SiteContentCommandError(
            "navigation.site_admin_required.v1",
            "只有管理员可以修改站点设置。",
        ) from None
    if not is_administrator(actor_id):
        raise SiteContentCommandError(
            "navigation.site_admin_required.v1",
            "只有管理员可以修改站点设置。",
        )
    return actor_id


def require_version(value) -> int:
    if isinstance(value, bool):
        raise SiteContentCommandError(
            "navigation.site_version_invalid.v1", "设置版本不合法。"
        )
    try:
        version = int(value)
    except (TypeError, ValueError):
        raise SiteContentCommandError(
            "navigation.site_version_invalid.v1", "设置版本不合法。"
        ) from None
    if version < 1:
        raise SiteContentCommandError(
            "navigation.site_version_invalid.v1", "设置版本不合法。"
        )
    return version


def normalized_text(value, *, field: str, maximum: int, required: bool) -> str:
    if not isinstance(value, str):
        raise SiteContentCommandError(
            "navigation.site_value_invalid.v1", f"{field}不合法。"
        )
    normalized = unicodedata.normalize("NFKC", value).strip()
    if (required and not normalized) or len(normalized) > maximum:
        requirement = f"1 至 {maximum}" if required else f"最多 {maximum}"
        raise SiteContentCommandError(
            "navigation.site_value_invalid.v1",
            f"{field}须为{requirement}个字符。",
        )
    if any(ord(character) < 32 and character not in "\n\t" for character in normalized):
        raise SiteContentCommandError(
            "navigation.site_value_invalid.v1", f"{field}含有不支持的字符。"
        )
    return normalized


__all__ = [
    "SiteContentCommandError",
    "normalized_text",
    "require_administrator",
    "require_version",
]
