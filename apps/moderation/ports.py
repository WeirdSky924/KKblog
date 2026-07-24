from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from django.conf import settings
from django.utils.module_loading import import_string


class ModerationAccountPolicy(Protocol):
    def is_active_account(self, account_id: UUID | None) -> bool: ...

    def is_administrator(self, account_id: UUID | None) -> bool: ...

    def is_ip_blocked(self, client_ip: str) -> bool: ...


class ReportEvidenceError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


@dataclass(frozen=True, slots=True)
class ReportEvidenceUpload:
    asset_id: str
    evidence_ref: str


class ReportEvidenceGateway(Protocol):
    def stage_evidence(
        self,
        *,
        actor_id: UUID,
        target_comment_id: str,
        original_name: str,
        declared_content_type: str,
        chunks: Iterable[bytes],
    ) -> ReportEvidenceUpload: ...

    def bind_evidence(
        self,
        *,
        report_id: str,
        actor_id: UUID,
        target_comment_id: str,
        evidence_refs: tuple[str, ...],
    ) -> tuple[str, ...]: ...


def _provider(setting_name: str):
    path = getattr(settings, setting_name, "")
    if not isinstance(path, str) or not path:
        raise RuntimeError(f"Missing provider setting: {setting_name}")
    return import_string(path)()


def default_moderation_account_policy() -> ModerationAccountPolicy:
    return _provider("MODERATION_ACCOUNT_POLICY_PROVIDER")


def default_report_evidence_gateway() -> ReportEvidenceGateway:
    return _provider("MODERATION_EVIDENCE_GATEWAY_PROVIDER")
