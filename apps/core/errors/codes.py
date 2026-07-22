from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "core.validation_failed.v1"
    AUTHENTICATION_REQUIRED = "core.authentication_required.v1"
    PERMISSION_DENIED = "core.permission_denied.v1"
    NOT_FOUND = "core.not_found.v1"
    CONFLICT = "core.conflict.v1"
    RATE_LIMITED = "core.rate_limited.v1"
    SERVICE_UNAVAILABLE = "core.service_unavailable.v1"
    IMAGE_CREATION_BLOCKED = "operations.image_creation_blocked.v1"
    CONTENT_CREATION_BLOCKED = "operations.content_creation_blocked.v1"
    INTERNAL_ERROR = "core.internal_error.v1"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    code: ErrorCode
    status: int
    message: str


_SPECS = MappingProxyType(
    {
        ErrorCode.VALIDATION_FAILED: ErrorSpec(
            ErrorCode.VALIDATION_FAILED, 422, "请检查输入后重试。"
        ),
        ErrorCode.AUTHENTICATION_REQUIRED: ErrorSpec(
            ErrorCode.AUTHENTICATION_REQUIRED, 401, "请先登录后继续。"
        ),
        ErrorCode.PERMISSION_DENIED: ErrorSpec(
            ErrorCode.PERMISSION_DENIED, 403, "你没有执行此操作的权限。"
        ),
        ErrorCode.NOT_FOUND: ErrorSpec(ErrorCode.NOT_FOUND, 404, "未找到请求的内容。"),
        ErrorCode.CONFLICT: ErrorSpec(
            ErrorCode.CONFLICT, 409, "内容已发生变化，请刷新后重试。"
        ),
        ErrorCode.RATE_LIMITED: ErrorSpec(
            ErrorCode.RATE_LIMITED, 429, "操作过于频繁，请稍后再试。"
        ),
        ErrorCode.SERVICE_UNAVAILABLE: ErrorSpec(
            ErrorCode.SERVICE_UNAVAILABLE, 503, "服务暂时不可用，请稍后重试。"
        ),
        ErrorCode.IMAGE_CREATION_BLOCKED: ErrorSpec(
            ErrorCode.IMAGE_CREATION_BLOCKED, 503, "暂时不支持上传图片。"
        ),
        ErrorCode.CONTENT_CREATION_BLOCKED: ErrorSpec(
            ErrorCode.CONTENT_CREATION_BLOCKED,
            503,
            "磁盘空间不足，暂时无法创建新内容。",
        ),
        ErrorCode.INTERNAL_ERROR: ErrorSpec(
            ErrorCode.INTERNAL_ERROR, 500, "系统暂时无法处理请求，请稍后重试。"
        ),
    }
)


def spec_for(code: ErrorCode) -> ErrorSpec:
    return _SPECS[code]
