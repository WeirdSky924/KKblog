from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.ids import is_ulid, new_ulid

from .constants import DetectedFormat, MediaPurpose, MediaState

MAX_IMAGE_BYTES = 2 * 1024 * 1024


def validate_storage_key(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("/")
        or "\\" in value
        or ".." in value.split("/")
        or any(part in {"", "."} for part in value.split("/"))
    ):
        raise ValidationError("媒体存储键不合法")


class MediaAsset(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    owner = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        related_name="media_assets",
        editable=False,
    )
    purpose = models.CharField(max_length=16, choices=MediaPurpose.choices)
    storage_key = models.CharField(max_length=255, unique=True, editable=False)
    original_name = models.CharField(max_length=255)
    detected_mime = models.CharField(max_length=32, choices=DetectedFormat.choices)
    size_bytes = models.PositiveIntegerField(editable=False)
    sha256 = models.CharField(max_length=64, editable=False)
    width = models.PositiveIntegerField(editable=False)
    height = models.PositiveIntegerField(editable=False)
    state = models.CharField(
        max_length=16,
        choices=MediaState.choices,
        default=MediaState.STAGED,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = "media_asset"
        constraints = [
            models.CheckConstraint(
                condition=Q(size_bytes__gte=1, size_bytes__lte=MAX_IMAGE_BYTES),
                name="media_asset_size_range",
            ),
            models.CheckConstraint(
                condition=Q(width__gte=1, height__gte=1),
                name="media_asset_dimensions_positive",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(storage_key__startswith="/")
                    & ~Q(storage_key__contains="\\")
                    & ~Q(storage_key__contains="..")
                ),
                name="media_asset_storage_key_relative",
            ),
            models.CheckConstraint(
                condition=Q(sha256__regex=r"^[0-9a-f]{64}$"),
                name="media_asset_sha256_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state=MediaState.DELETED, deleted_at__isnull=False)
                    | (~Q(state=MediaState.DELETED) & Q(deleted_at__isnull=True))
                ),
                name="media_asset_deleted_at_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(owner__isnull=False)
                    | Q(state__in=(MediaState.DELETE_PENDING, MediaState.DELETED))
                ),
                name="media_asset_owner_lifecycle",
            ),
        ]
        indexes = [
            models.Index(
                fields=("state", "created_at"), name="media_asset_state_created_idx"
            ),
            models.Index(
                fields=("owner", "purpose", "state"), name="media_owner_purpose_idx"
            ),
        ]

    def clean(self) -> None:
        validate_storage_key(self.storage_key)
        if not is_ulid(self.id):
            raise ValidationError({"id": "媒体 ID 必须是 ULID"})
        if self.state == MediaState.DELETED and self.deleted_at is None:
            raise ValidationError({"deleted_at": "已删除媒体必须记录删除时间"})
        if self.state != MediaState.DELETED and self.deleted_at is not None:
            raise ValidationError({"deleted_at": "未删除媒体不能记录删除时间"})

    def mark_deleted(self) -> None:
        self.state = MediaState.DELETED
        self.deleted_at = timezone.now()
