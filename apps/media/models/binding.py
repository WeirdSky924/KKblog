from django.core.exceptions import ValidationError
from django.db import models

from apps.core.ids import new_ulid

from ..targets import validate_binding_target
from .asset import MediaAsset
from .constants import MediaTargetType


class MediaBindingManager(models.Manager):
    def bind(
        self,
        *,
        asset: MediaAsset,
        target_type: MediaTargetType | str,
        target_id: str,
        slot: str,
    ) -> "MediaBinding":
        binding = self.model(
            asset=asset,
            target_type=target_type,
            target_id=target_id,
            slot=slot,
        )
        binding.full_clean(validate_unique=False, validate_constraints=False)
        binding.save(force_insert=True)
        return binding


class MediaBinding(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    asset = models.ForeignKey(
        MediaAsset, on_delete=models.CASCADE, related_name="bindings", editable=False
    )
    target_type = models.CharField(
        max_length=32, choices=MediaTargetType.choices, editable=False
    )
    target_id = models.CharField(max_length=128, editable=False)
    slot = models.CharField(max_length=48, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects = MediaBindingManager()

    class Meta:
        db_table = "media_binding"
        constraints = [
            models.UniqueConstraint(
                fields=("target_type", "target_id", "slot"),
                name="media_binding_target_slot_unique",
            ),
            models.UniqueConstraint(
                fields=("asset", "target_type", "target_id"),
                name="media_binding_asset_target_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(target_type__in=MediaTargetType.values),
                name="media_binding_target_registered",
            ),
        ]
        indexes = [
            models.Index(
                fields=("target_type", "target_id"), name="media_binding_target_idx"
            )
        ]

    def clean(self) -> None:
        validate_binding_target(self.asset.purpose, self.target_type)
        if not self.target_id or len(self.target_id) > 128:
            raise ValidationError({"target_id": "媒体目标 ID 不合法"})
        if (
            not self.slot
            or len(self.slot) > 48
            or not self.slot.replace("-", "").isalnum()
        ):
            raise ValidationError({"slot": "媒体槽位不合法"})
