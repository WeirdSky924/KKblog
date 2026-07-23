import re
from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.core.ids import is_ulid
from apps.media.models import (
    MediaAsset,
    MediaBinding,
    MediaPurpose,
    MediaState,
    MediaTargetType,
)
from apps.media.services.cleanup import schedule_pending_cleanup
from apps.media.storage import MediaStorage
from apps.media.targets import (
    TargetAccessDecision,
    TargetAccessOperation,
    TargetAccessRegistry,
    TargetAccessRequest,
    default_target_access_registry,
    validate_binding_target,
)


class MediaBindingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.safe_message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class BindingInput:
    asset_id: str
    slot: str


@dataclass(frozen=True, slots=True)
class ReplaceBindingsResult:
    active_asset_ids: tuple[str, ...]
    pending_delete_asset_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TargetBindingSnapshot:
    asset_id: str
    purpose: str
    state: str
    slot: str


@dataclass(frozen=True, slots=True)
class _BindingRule:
    maximum: int
    slot_pattern: re.Pattern[str]


_RULES = {
    (MediaTargetType.ACCOUNT_PROFILE, MediaPurpose.AVATAR): _BindingRule(
        1, re.compile(r"^avatar$")
    ),
    (MediaTargetType.ARTICLE_REVISION, MediaPurpose.COVER): _BindingRule(
        1, re.compile(r"^cover$")
    ),
    (MediaTargetType.ARTICLE_REVISION, MediaPurpose.BODY): _BindingRule(
        1000, re.compile(r"^body-[0-9A-HJKMNP-TV-Z]{26}$")
    ),
    (MediaTargetType.COMMENT, MediaPurpose.COMMENT): _BindingRule(
        3, re.compile(r"^image-[1-3]$")
    ),
    (MediaTargetType.REPORT, MediaPurpose.EVIDENCE): _BindingRule(
        3, re.compile(r"^evidence-[1-3]$")
    ),
    (MediaTargetType.REPORT_APPEAL, MediaPurpose.EVIDENCE): _BindingRule(
        3, re.compile(r"^evidence-[1-3]$")
    ),
    (MediaTargetType.ARTICLE_APPEAL, MediaPurpose.EVIDENCE): _BindingRule(
        3, re.compile(r"^evidence-[1-3]$")
    ),
    (MediaTargetType.SITE_BRAND, MediaPurpose.LOGO): _BindingRule(
        1, re.compile(r"^logo$")
    ),
    (MediaTargetType.FRIEND_LINK, MediaPurpose.FRIEND_LOGO): _BindingRule(
        1, re.compile(r"^logo$")
    ),
    (MediaTargetType.IMPORT_JOB, MediaPurpose.IMPORT): _BindingRule(
        1000, re.compile(r"^source-[0-9A-HJKMNP-TV-Z]{26}$")
    ),
}


def _normalize_inputs(inputs: tuple[BindingInput, ...]) -> tuple[BindingInput, ...]:
    if len({item.asset_id for item in inputs}) != len(inputs) or len(
        {item.slot for item in inputs}
    ) != len(inputs):
        raise MediaBindingError("media.binding_duplicate.v1", "图片或槽位不能重复。")
    if any(
        not isinstance(item, BindingInput)
        or not is_ulid(item.asset_id)
        or not isinstance(item.slot, str)
        for item in inputs
    ):
        raise MediaBindingError("media.binding_invalid.v1", "媒体绑定信息不合法。")
    return inputs


def _target_decision(
    *,
    registry: TargetAccessRegistry,
    actor_id: UUID,
    target_type: MediaTargetType,
    target_id: str,
    purpose: MediaPurpose,
) -> TargetAccessDecision:
    try:
        validate_binding_target(purpose, target_type)
        decision = registry.decide(
            target_type,
            TargetAccessRequest(
                actor_id=actor_id,
                target_id=target_id,
                purpose=purpose,
                operation=TargetAccessOperation.BIND,
            ),
        )
    except ValidationError:
        raise MediaBindingError(
            "media.target_unavailable.v1", "媒体目标不存在或不可用。"
        ) from None
    if not decision.exists:
        raise MediaBindingError("media.target_not_found.v1", "媒体目标不存在。")
    if not decision.can_bind:
        raise MediaBindingError("media.binding_denied.v1", "不能为该目标设置图片。")
    return decision


def _locked_assets(
    inputs: tuple[BindingInput, ...], actor_id: UUID
) -> dict[str, MediaAsset]:
    assets = {
        asset.id: asset
        for asset in MediaAsset.objects.select_for_update().filter(
            id__in=[item.asset_id for item in inputs]
        )
    }
    if len(assets) != len(inputs):
        raise MediaBindingError("media.asset_not_found.v1", "图片不存在或不可用。")
    for asset in assets.values():
        if asset.owner_id != actor_id:
            raise MediaBindingError(
                "media.asset_owner_mismatch.v1", "图片不属于当前账户。"
            )
        if asset.state != MediaState.ACTIVE:
            raise MediaBindingError("media.asset_not_active.v1", "图片尚不可使用。")
    return assets


def _validate_rules(
    *,
    assets: dict[str, MediaAsset],
    inputs: tuple[BindingInput, ...],
    target_type: MediaTargetType,
) -> dict[MediaPurpose, _BindingRule]:
    rules: dict[MediaPurpose, _BindingRule] = {}
    counts: dict[MediaPurpose, int] = {}
    for item in inputs:
        purpose = MediaPurpose(assets[item.asset_id].purpose)
        rule = _RULES.get((target_type, purpose))
        if rule is None:
            raise MediaBindingError(
                "media.binding_purpose_mismatch.v1", "图片用途或槽位不匹配。"
            )
        rules[purpose] = rule
        counts[purpose] = counts.get(purpose, 0) + 1
    if any(counts[purpose] > rules[purpose].maximum for purpose in counts):
        raise MediaBindingError(
            "media.binding_limit_exceeded.v1", "图片数量超过此用途的上限。"
        )
    for item in inputs:
        purpose = MediaPurpose(assets[item.asset_id].purpose)
        if rules[purpose].slot_pattern.fullmatch(item.slot) is None:
            raise MediaBindingError(
                "media.binding_purpose_mismatch.v1", "图片用途或槽位不匹配。"
            )
    return rules


def bind_assets(
    *,
    actor_id: UUID,
    target_type: MediaTargetType | str,
    target_id: str,
    inputs: tuple[BindingInput, ...],
    registry: TargetAccessRegistry = default_target_access_registry,
) -> tuple[MediaBinding, ...]:
    if not isinstance(actor_id, UUID) or not inputs:
        raise MediaBindingError("media.binding_invalid.v1", "媒体绑定信息不合法。")
    normalized_inputs = _normalize_inputs(inputs)
    try:
        normalized_target = MediaTargetType(target_type)
    except (TypeError, ValueError):
        raise MediaBindingError(
            "media.target_unavailable.v1", "媒体目标不可用。"
        ) from None
    with transaction.atomic():
        assets = _locked_assets(normalized_inputs, actor_id)
        rules = _validate_rules(
            assets=assets, inputs=normalized_inputs, target_type=normalized_target
        )
        for purpose in rules:
            _target_decision(
                registry=registry,
                actor_id=actor_id,
                target_type=normalized_target,
                target_id=target_id,
                purpose=purpose,
            )
        existing = list(
            MediaBinding.objects.select_for_update()
            .select_related("asset")
            .filter(target_type=normalized_target, target_id=target_id)
        )
        by_slot = {binding.slot: binding for binding in existing}
        created: list[MediaBinding] = []
        for item in normalized_inputs:
            current = by_slot.get(item.slot)
            if current is not None:
                if current.asset_id != item.asset_id:
                    raise MediaBindingError(
                        "media.binding_slot_conflict.v1", "图片槽位已被占用。"
                    )
                created.append(current)
                continue
            asset = assets[item.asset_id]
            rule = rules[MediaPurpose(asset.purpose)]
            current_count = sum(
                binding.asset.purpose == asset.purpose for binding in existing
            )
            if current_count >= rule.maximum:
                raise MediaBindingError(
                    "media.binding_limit_exceeded.v1", "图片数量超过此用途的上限。"
                )
            if asset.bindings.exclude(
                target_type=normalized_target, target_id=target_id
            ).exists():
                raise MediaBindingError(
                    "media.asset_already_bound.v1", "图片已绑定到其他目标。"
                )
            try:
                binding = MediaBinding.objects.bind(
                    asset=asset,
                    target_type=normalized_target,
                    target_id=target_id,
                    slot=item.slot,
                )
            except (IntegrityError, ValidationError):
                raise MediaBindingError(
                    "media.binding_conflict.v1", "图片绑定发生冲突，请重试。"
                ) from None
            existing.append(binding)
            created.append(binding)
    return tuple(created)


def bind_revision_snapshot_assets(
    *,
    actor_id: UUID,
    target_id: str,
    inputs: tuple[BindingInput, ...],
    registry: TargetAccessRegistry = default_target_access_registry,
) -> tuple[MediaBinding, ...]:
    if not isinstance(actor_id, UUID) or not inputs:
        raise MediaBindingError("media.binding_invalid.v1", "媒体绑定信息不合法。")
    normalized_inputs = _normalize_inputs(inputs)
    target_type = MediaTargetType.ARTICLE_REVISION
    with transaction.atomic():
        assets = _locked_assets(normalized_inputs, actor_id)
        rules = _validate_rules(
            assets=assets,
            inputs=normalized_inputs,
            target_type=target_type,
        )
        target_decision = _target_decision(
            registry=registry,
            actor_id=actor_id,
            target_type=target_type,
            target_id=target_id,
            purpose=MediaPurpose(assets[normalized_inputs[0].asset_id].purpose),
        )
        if not target_decision.binding_scope:
            raise MediaBindingError(
                "media.binding_scope_invalid.v1", "媒体目标不能建立修订快照。"
            )
        for purpose in rules:
            _target_decision(
                registry=registry,
                actor_id=actor_id,
                target_type=target_type,
                target_id=target_id,
                purpose=purpose,
            )

        current = list(
            MediaBinding.objects.select_for_update()
            .select_related("asset")
            .filter(target_type=target_type, target_id=target_id)
        )
        by_slot = {binding.slot: binding for binding in current}
        created: list[MediaBinding] = []
        for item in normalized_inputs:
            current_slot = by_slot.get(item.slot)
            if current_slot is not None:
                if current_slot.asset_id != item.asset_id:
                    raise MediaBindingError(
                        "media.binding_slot_conflict.v1", "图片槽位已被占用。"
                    )
                created.append(current_slot)
                continue

            asset = assets[item.asset_id]
            purpose = MediaPurpose(asset.purpose)
            current_count = sum(binding.asset.purpose == purpose for binding in current)
            if current_count >= rules[purpose].maximum:
                raise MediaBindingError(
                    "media.binding_limit_exceeded.v1", "图片数量超过此用途的上限。"
                )
            for binding in asset.bindings.select_for_update().exclude(
                target_type=target_type,
                target_id=target_id,
            ):
                if binding.target_type != target_type:
                    raise MediaBindingError(
                        "media.asset_already_bound.v1", "图片已绑定到其他目标。"
                    )
                try:
                    source = registry.decide(
                        target_type,
                        TargetAccessRequest(
                            actor_id=actor_id,
                            target_id=binding.target_id,
                            purpose=purpose,
                            operation=TargetAccessOperation.BIND,
                        ),
                    )
                except ValidationError:
                    raise MediaBindingError(
                        "media.asset_already_bound.v1", "图片已绑定到其他目标。"
                    ) from None
                if (
                    not source.exists
                    or source.binding_scope != target_decision.binding_scope
                ):
                    raise MediaBindingError(
                        "media.asset_already_bound.v1", "图片已绑定到其他目标。"
                    )
            try:
                binding = MediaBinding.objects.bind(
                    asset=asset,
                    target_type=target_type,
                    target_id=target_id,
                    slot=item.slot,
                )
            except (IntegrityError, ValidationError):
                raise MediaBindingError(
                    "media.binding_conflict.v1", "图片绑定发生冲突，请重试。"
                ) from None
            current.append(binding)
            by_slot[binding.slot] = binding
            created.append(binding)
    return tuple(created)


def target_binding_snapshot(
    *, target_type: MediaTargetType | str, target_id: str
) -> tuple[TargetBindingSnapshot, ...]:
    try:
        normalized_target = MediaTargetType(target_type)
    except (TypeError, ValueError):
        raise MediaBindingError(
            "media.target_unavailable.v1", "媒体目标不可用。"
        ) from None
    if not isinstance(target_id, str) or not 1 <= len(target_id) <= 128:
        raise MediaBindingError("media.target_unavailable.v1", "媒体目标不可用。")
    return tuple(
        TargetBindingSnapshot(
            binding.asset_id,
            binding.asset.purpose,
            binding.asset.state,
            binding.slot,
        )
        for binding in MediaBinding.objects.select_related("asset")
        .filter(target_type=normalized_target, target_id=target_id)
        .order_by("slot", "asset_id")
    )


def replace_bindings(
    *,
    actor_id: UUID,
    target_type: MediaTargetType | str,
    target_id: str,
    inputs: tuple[BindingInput, ...],
    purpose: MediaPurpose | str | None = None,
    registry: TargetAccessRegistry = default_target_access_registry,
    storage: MediaStorage | None = None,
) -> ReplaceBindingsResult:
    if not isinstance(actor_id, UUID):
        raise MediaBindingError("media.binding_invalid.v1", "媒体绑定信息不合法。")
    normalized_inputs = _normalize_inputs(inputs)
    try:
        normalized_target = MediaTargetType(target_type)
    except (TypeError, ValueError):
        raise MediaBindingError(
            "media.target_unavailable.v1", "媒体目标不可用。"
        ) from None
    with transaction.atomic():
        assets = _locked_assets(normalized_inputs, actor_id) if inputs else {}
        rules = _validate_rules(
            assets=assets, inputs=normalized_inputs, target_type=normalized_target
        )
        purposes = set(rules)
        if purpose is not None:
            try:
                purposes.add(MediaPurpose(purpose))
            except (TypeError, ValueError):
                raise MediaBindingError(
                    "media.binding_purpose_mismatch.v1", "图片用途不匹配。"
                ) from None
        if len(purposes) != 1:
            raise MediaBindingError(
                "media.binding_purpose_mismatch.v1", "每次替换只能处理一种用途。"
            )
        active_purpose = purposes.pop()
        rule = _RULES.get((normalized_target, active_purpose))
        if rule is None:
            raise MediaBindingError(
                "media.binding_purpose_mismatch.v1", "图片用途与目标不匹配。"
            )
        _target_decision(
            registry=registry,
            actor_id=actor_id,
            target_type=normalized_target,
            target_id=target_id,
            purpose=active_purpose,
        )
        current = list(
            MediaBinding.objects.select_for_update()
            .select_related("asset")
            .filter(
                target_type=normalized_target,
                target_id=target_id,
                asset__purpose=active_purpose,
            )
        )
        desired_by_slot = {item.slot: item.asset_id for item in normalized_inputs}
        retained_ids = {
            binding.id
            for binding in current
            if desired_by_slot.get(binding.slot) == binding.asset_id
        }
        removed = [binding for binding in current if binding.id not in retained_ids]
        MediaBinding.objects.filter(id__in=[binding.id for binding in removed]).delete()

        current_slots = {
            binding.slot for binding in current if binding.id in retained_ids
        }
        for item in normalized_inputs:
            if item.slot in current_slots:
                continue
            asset = assets[item.asset_id]
            if asset.bindings.exists():
                raise MediaBindingError(
                    "media.asset_already_bound.v1", "图片已绑定到其他目标。"
                )
            try:
                MediaBinding.objects.bind(
                    asset=asset,
                    target_type=normalized_target,
                    target_id=target_id,
                    slot=item.slot,
                )
            except (IntegrityError, ValidationError):
                raise MediaBindingError(
                    "media.binding_conflict.v1", "图片绑定发生冲突，请重试。"
                ) from None

        pending: list[str] = []
        for binding in removed:
            if not MediaBinding.objects.filter(asset_id=binding.asset_id).exists():
                updated = MediaAsset.objects.filter(
                    id=binding.asset_id, state=MediaState.ACTIVE
                ).update(state=MediaState.DELETE_PENDING)
                if updated:
                    pending.append(binding.asset_id)
        schedule_pending_cleanup(tuple(pending), storage=storage)
    return ReplaceBindingsResult(
        active_asset_ids=tuple(item.asset_id for item in normalized_inputs),
        pending_delete_asset_ids=tuple(pending),
    )
