from collections.abc import Callable

AuditWriter = Callable[..., object]
_profile_audit_writer: AuditWriter | None = None


def configure_profile_audit_writer(writer: AuditWriter) -> None:
    global _profile_audit_writer
    if not callable(writer):
        raise TypeError("profile audit writer must be callable")
    _profile_audit_writer = writer


def record_profile_audit(**values):
    if _profile_audit_writer is None:
        raise RuntimeError("Profile audit writer is not configured")
    return _profile_audit_writer(**values)
