import hashlib
import hmac
from collections.abc import Iterable
from functools import partial
from uuid import UUID

from django.conf import settings
from django.core import signing

from apps.accounts.public import is_active_account, is_administrator, is_ip_blocked
from apps.core.ids import normalize_ulid
from apps.media.public import (
    BindingInput,
    MediaBindingError,
    MediaPurpose,
    MediaTargetType,
    MediaUploadError,
    TargetAccessDecision,
    bind_assets,
    register_target_access,
    stage_upload,
)
from apps.media.storage import FilesystemMediaStorage
from apps.moderation.public import (
    ReportAppealEvidenceError,
    ReportAppealEvidenceUpload,
    ReportEvidenceError,
    ReportEvidenceUpload,
    report_appeal_evidence_access,
    report_evidence_access,
)
from apps.operations.public import require_image_creation_capacity

_EVIDENCE_REF_SALT = "moderation.evidence-ref.v1"
_EVIDENCE_REF_MAX_AGE_SECONDS = 86_400
_APPEAL_EVIDENCE_REF_SALT = "moderation.appeal-evidence-ref.v1"
_APPEAL_EVIDENCE_REF_MAX_AGE_SECONDS = 86_400


class _ModerationAccountPolicy:
    is_active_account = staticmethod(is_active_account)
    is_administrator = staticmethod(is_administrator)
    is_ip_blocked = staticmethod(is_ip_blocked)


def moderation_account_policy() -> _ModerationAccountPolicy:
    return _ModerationAccountPolicy()


def _actor(value) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise ReportEvidenceError(
            "moderation.evidence_actor_invalid.v1",
            "当前身份无法上传证据图片。",
        ) from None


def _comment_id(value) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ReportEvidenceError(
            "moderation.evidence_target_invalid.v1",
            "证据归属评论无效。",
        ) from None


def _subject_digest(actor_id: UUID) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"report-evidence:{actor_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _appeal_subject_digest(actor_id: UUID, report_id: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"report-appeal-evidence:{actor_id}:{report_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _media_target_access(request) -> TargetAccessDecision:
    access = report_evidence_access(
        actor_id=request.actor_id,
        report_id=request.target_id,
    )
    return TargetAccessDecision(
        exists=access.exists,
        can_bind=access.can_bind,
        can_read=access.can_read,
        public_immutable=False,
    )


def _register_report_media_target() -> None:
    register_target_access(
        MediaTargetType.REPORT,
        _media_target_access,
        replace=True,
    )


def _appeal_media_target_access(request) -> TargetAccessDecision:
    access = report_appeal_evidence_access(
        actor_id=request.actor_id,
        appeal_id=request.target_id,
    )
    return TargetAccessDecision(
        exists=access.exists,
        can_bind=access.can_bind,
        can_read=access.can_read,
        public_immutable=False,
    )


def _register_report_appeal_media_target() -> None:
    register_target_access(
        MediaTargetType.REPORT_APPEAL,
        _appeal_media_target_access,
        replace=True,
    )


class _ReportEvidenceGateway:
    def stage_evidence(
        self,
        *,
        actor_id: UUID,
        target_comment_id: str,
        original_name: str,
        declared_content_type: str,
        chunks: Iterable[bytes],
    ) -> ReportEvidenceUpload:
        actor = _actor(actor_id)
        comment_id = _comment_id(target_comment_id)
        try:
            asset = stage_upload(
                owner_id=actor,
                purpose=MediaPurpose.EVIDENCE,
                original_name=original_name,
                declared_content_type=declared_content_type,
                chunks=chunks,
                storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
                capacity_check=partial(
                    require_image_creation_capacity,
                    settings.MEDIA_ROOT,
                ),
                target_id=comment_id,
            )
        except MediaUploadError as exc:
            raise ReportEvidenceError(exc.code, exc.safe_message) from None
        evidence_ref = signing.dumps(
            {
                "v": 1,
                "asset_id": asset.id,
                "owner_id": str(actor),
                "target_comment_id": comment_id,
                "subject": _subject_digest(actor),
            },
            salt=_EVIDENCE_REF_SALT,
            compress=True,
        )
        return ReportEvidenceUpload(asset_id=asset.id, evidence_ref=evidence_ref)

    def bind_evidence(
        self,
        *,
        report_id: str,
        actor_id: UUID,
        target_comment_id: str,
        evidence_refs: tuple[str, ...],
    ) -> tuple[str, ...]:
        actor = _actor(actor_id)
        comment_id = _comment_id(target_comment_id)
        expected_keys = {
            "v",
            "asset_id",
            "owner_id",
            "target_comment_id",
            "subject",
        }
        asset_ids = []
        for evidence_ref in evidence_refs:
            try:
                payload = signing.loads(
                    evidence_ref,
                    salt=_EVIDENCE_REF_SALT,
                    max_age=_EVIDENCE_REF_MAX_AGE_SECONDS,
                )
            except signing.BadSignature:
                raise ReportEvidenceError(
                    "moderation.evidence_ref_invalid.v1",
                    "证据图片引用无效或已过期。",
                ) from None
            if (
                not isinstance(payload, dict)
                or set(payload) != expected_keys
                or payload["v"] != 1
                or payload["owner_id"] != str(actor)
                or payload["target_comment_id"] != comment_id
                or payload["subject"] != _subject_digest(actor)
                or not isinstance(payload["asset_id"], str)
            ):
                raise ReportEvidenceError(
                    "moderation.evidence_ref_invalid.v1",
                    "证据图片与当前举报不匹配。",
                )
            asset_ids.append(payload["asset_id"])
        if len(set(asset_ids)) != len(asset_ids):
            raise ReportEvidenceError(
                "moderation.evidence_ref_invalid.v1",
                "证据图片不能重复。",
            )
        if not asset_ids:
            return ()
        _register_report_media_target()
        try:
            bindings = bind_assets(
                actor_id=actor,
                target_type=MediaTargetType.REPORT,
                target_id=report_id,
                inputs=tuple(
                    BindingInput(asset_id=asset_id, slot=f"evidence-{index}")
                    for index, asset_id in enumerate(asset_ids, 1)
                ),
            )
        except MediaBindingError as exc:
            raise ReportEvidenceError(exc.code, exc.safe_message) from None
        return tuple(binding.asset_id for binding in bindings)


def _appeal_identity(value, *, label: str) -> str:
    try:
        return normalize_ulid(value)
    except (TypeError, ValueError):
        raise ReportAppealEvidenceError(
            "moderation.appeal_evidence_target_invalid.v1",
            f"{label}无效。",
        ) from None


class _ReportAppealEvidenceGateway:
    def stage_evidence(
        self,
        *,
        actor_id: UUID,
        report_id: str,
        original_name: str,
        declared_content_type: str,
        chunks: Iterable[bytes],
    ) -> ReportAppealEvidenceUpload:
        actor = _actor(actor_id)
        report = _appeal_identity(report_id, label="申诉举报")
        try:
            asset = stage_upload(
                owner_id=actor,
                purpose=MediaPurpose.EVIDENCE,
                original_name=original_name,
                declared_content_type=declared_content_type,
                chunks=chunks,
                storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
                capacity_check=partial(
                    require_image_creation_capacity,
                    settings.MEDIA_ROOT,
                ),
                target_id=report,
            )
        except MediaUploadError as exc:
            raise ReportAppealEvidenceError(exc.code, exc.safe_message) from None
        evidence_ref = signing.dumps(
            {
                "v": 1,
                "asset_id": asset.id,
                "owner_id": str(actor),
                "report_id": report,
                "subject": _appeal_subject_digest(actor, report),
            },
            salt=_APPEAL_EVIDENCE_REF_SALT,
            compress=True,
        )
        return ReportAppealEvidenceUpload(
            asset_id=asset.id,
            evidence_ref=evidence_ref,
        )

    def bind_evidence(
        self,
        *,
        appeal_id: str,
        report_id: str,
        actor_id: UUID,
        evidence_refs: tuple[str, ...],
    ) -> tuple[str, ...]:
        actor = _actor(actor_id)
        appeal = _appeal_identity(appeal_id, label="申诉")
        report = _appeal_identity(report_id, label="申诉举报")
        expected_keys = {"v", "asset_id", "owner_id", "report_id", "subject"}
        asset_ids = []
        for evidence_ref in evidence_refs:
            try:
                payload = signing.loads(
                    evidence_ref,
                    salt=_APPEAL_EVIDENCE_REF_SALT,
                    max_age=_APPEAL_EVIDENCE_REF_MAX_AGE_SECONDS,
                )
            except signing.BadSignature:
                raise ReportAppealEvidenceError(
                    "moderation.appeal_evidence_ref_invalid.v1",
                    "申诉证据图片引用无效或已过期。",
                ) from None
            if (
                not isinstance(payload, dict)
                or set(payload) != expected_keys
                or payload["v"] != 1
                or payload["owner_id"] != str(actor)
                or payload["report_id"] != report
                or payload["subject"] != _appeal_subject_digest(actor, report)
                or not isinstance(payload["asset_id"], str)
            ):
                raise ReportAppealEvidenceError(
                    "moderation.appeal_evidence_ref_invalid.v1",
                    "申诉证据图片与当前案件不匹配。",
                )
            asset_ids.append(payload["asset_id"])
        if len(set(asset_ids)) != len(asset_ids):
            raise ReportAppealEvidenceError(
                "moderation.appeal_evidence_ref_invalid.v1",
                "申诉证据图片不能重复。",
            )
        if not asset_ids:
            return ()
        _register_report_appeal_media_target()
        try:
            bindings = bind_assets(
                actor_id=actor,
                target_type=MediaTargetType.REPORT_APPEAL,
                target_id=appeal,
                inputs=tuple(
                    BindingInput(asset_id=asset_id, slot=f"evidence-{index}")
                    for index, asset_id in enumerate(asset_ids, 1)
                ),
            )
        except MediaBindingError as exc:
            raise ReportAppealEvidenceError(exc.code, exc.safe_message) from None
        return tuple(binding.asset_id for binding in bindings)


def report_evidence_gateway() -> _ReportEvidenceGateway:
    _register_report_media_target()
    return _ReportEvidenceGateway()


def report_appeal_evidence_gateway() -> _ReportAppealEvidenceGateway:
    _register_report_appeal_media_target()
    return _ReportAppealEvidenceGateway()


def configure_moderation_integrations() -> None:
    _register_report_media_target()
    _register_report_appeal_media_target()
