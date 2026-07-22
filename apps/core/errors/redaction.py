import ipaddress
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from apps.core.observability.context import current_trace_code

REDACTED = "[REDACTED]"
MASKED_PATH = "[PATH]"

_SECRET_PARTS = {
    "authorization",
    "body",
    "connection",
    "content",
    "cookie",
    "database_url",
    "password",
    "passphrase",
    "raw",
    "secret",
    "token",
}
_KEY_VALUE = re.compile(
    r"(?i)\b(password|passphrase|verification[_-]?code|token|cookie|authorization|"
    r"database[_-]?url|connection[_-]?string|body|content)\s*[:=]\s*"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
_CREDENTIAL_URL = re.compile(r"(?i)\b(postgres(?:ql)?|mysql|redis|rediss)://[^@\s]+@")
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_EMAIL = re.compile(
    r"(?<![\w.+-])([\w.+-])[^@\s]*@([A-Za-z0-9-])[^@\s.]*\.([A-Za-z]{2,})"
)
_IPV4 = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_PATH = re.compile(r"(?<![:\w])/(?:[^\s/]+/)*[^\s,;]*")


class RedactionPolicy:
    def redact(self, value: Any, *, key: str | None = None) -> Any:
        normalized_key = (key or "").casefold()
        if self._is_secret_key(normalized_key):
            return REDACTED
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            if normalized_key.endswith("email"):
                return self.mask_email(value)
            if normalized_key.endswith("ip") or normalized_key == "ip":
                return self.mask_ip(value)
            if "path" in normalized_key:
                return MASKED_PATH
            if "user_agent" in normalized_key:
                return "[USER_AGENT]"
            return self.redact_text(value)
        if isinstance(value, bytes):
            return "[BYTES]"
        if isinstance(value, Mapping):
            return {
                str(item_key): self.redact(item, key=str(item_key))
                for item_key, item in value.items()
            }
        if isinstance(value, Sequence):
            return [self.redact(item) for item in value]
        if isinstance(value, BaseException):
            return f"<{type(value).__name__}>"
        return f"<{type(value).__name__}>"

    def redact_text(self, value: str) -> str:
        redacted = _CREDENTIAL_URL.sub(
            lambda match: f"{match.group(1)}://{REDACTED}@", value
        )
        redacted = _BEARER.sub(f"Bearer {REDACTED}", redacted)
        redacted = _KEY_VALUE.sub(
            lambda match: f"{match.group(1)}={REDACTED}", redacted
        )
        redacted = _EMAIL.sub(r"\1***@\2***.\3", redacted)
        redacted = _IPV4.sub(self.mask_ip, redacted)
        return _PATH.sub(lambda _: MASKED_PATH, redacted)

    @staticmethod
    def mask_email(value: str) -> str:
        if "@" not in value:
            return "[EMAIL]"
        local, domain = value.rsplit("@", 1)
        domain_head, separator, suffix = domain.partition(".")
        return f"{local[:1]}***@{domain_head[:1]}***{separator}{suffix}"

    @staticmethod
    def mask_ip(value: str | re.Match[str]) -> str:
        text = value.group(0) if isinstance(value, re.Match) else value
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            return "[IP]"
        if address.version == 4:
            octets = text.split(".")
            return ".".join([*octets[:3], "x"])
        network = ipaddress.ip_network(f"{address}/64", strict=False)
        return f"{network.network_address.compressed}/64"

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        normalized = key.replace("-", "_")
        code_keys = {
            "code",
            "email_code",
            "invite_code",
            "one_time_code",
            "verification_code",
        }
        if normalized in code_keys or normalized.endswith("_verification_code"):
            return True
        return any(
            part == normalized or part in normalized.split("_")
            for part in _SECRET_PARTS
        )


DEFAULT_REDACTION_POLICY = RedactionPolicy()


class RedactingFilter(logging.Filter):
    def __init__(self, policy: RedactionPolicy | None = None) -> None:
        super().__init__()
        self.policy = policy or DEFAULT_REDACTION_POLICY

    def filter(self, record: logging.LogRecord) -> bool:
        request = getattr(record, "request", None)
        trace_code = (
            getattr(record, "trace_code", None)
            or getattr(request, "trace_code", None)
            or current_trace_code()
            or "-"
        )
        if record.exc_info:
            record.exception_type = record.exc_info[0].__name__
            record.exc_info = None
        record.stack_info = None
        record.pathname = MASKED_PATH
        record.filename = "[FILE]"
        record.module = "[MODULE]"
        if isinstance(record.msg, Mapping):
            rendered_message = str(self.policy.redact(record.msg))
        else:
            try:
                rendered_message = record.getMessage()
            except (TypeError, ValueError):
                rendered_message = "[UNFORMATTABLE_LOG_MESSAGE]"
        record.msg = self.policy.redact_text(rendered_message)
        record.args = ()
        for key in tuple(record.__dict__):
            if key.startswith("_") or key in _LOG_RECORD_FIELDS:
                continue
            record.__dict__[key] = self.policy.redact(record.__dict__[key], key=key)
        record.trace_code = trace_code
        return True


_LOG_RECORD_FIELDS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
)
