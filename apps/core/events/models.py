from django.db import models
from django.db.models import Q
from django.utils import timezone


class OutboxStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PUBLISHED = "published", "Published"


class ConsumerStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    PROCESSED = "processed", "Processed"


class OutboxEvent(models.Model):
    event_id = models.CharField(primary_key=True, max_length=26, editable=False)
    event_type = models.CharField(max_length=128, editable=False)
    schema_version = models.PositiveSmallIntegerField(editable=False)
    occurred_at = models.DateTimeField(editable=False)
    actor_id = models.UUIDField(null=True, editable=False)
    aggregate_type = models.CharField(max_length=64, editable=False)
    aggregate_id = models.CharField(max_length=128, editable=False)
    trace_code = models.CharField(max_length=30, editable=False)
    payload = models.JSONField(editable=False)
    status = models.CharField(
        max_length=12,
        choices=OutboxStatus,
        default=OutboxStatus.PENDING,
        editable=False,
    )
    attempts = models.PositiveIntegerField(default=0, editable=False)
    available_at = models.DateTimeField(default=timezone.now, editable=False)
    lease_token = models.UUIDField(null=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, editable=False)
    published_at = models.DateTimeField(null=True, editable=False)
    last_error_code = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "core_outbox_event"
        ordering = ("occurred_at", "event_id")
        indexes = [
            models.Index(
                fields=("available_at", "occurred_at"),
                name="core_outbox_ready_idx",
                condition=Q(status=OutboxStatus.PENDING),
            ),
            models.Index(
                fields=("lease_expires_at",),
                name="core_outbox_lease_idx",
                condition=Q(status=OutboxStatus.PENDING),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status=OutboxStatus.PENDING, published_at__isnull=True)
                    | Q(
                        status=OutboxStatus.PUBLISHED,
                        published_at__isnull=False,
                    )
                ),
                name="core_outbox_published_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(lease_token__isnull=True, lease_expires_at__isnull=True)
                    | Q(lease_token__isnull=False, lease_expires_at__isnull=False)
                ),
                name="core_outbox_lease_shape",
            ),
        ]


class EventConsumerRecord(models.Model):
    event_id = models.CharField(max_length=26, editable=False)
    event_type = models.CharField(max_length=128, editable=False)
    consumer_name = models.CharField(max_length=128, editable=False)
    trace_code = models.CharField(max_length=30, editable=False)
    status = models.CharField(
        max_length=12,
        choices=ConsumerStatus,
        default=ConsumerStatus.PENDING,
        editable=False,
    )
    attempts = models.PositiveIntegerField(default=0, editable=False)
    available_at = models.DateTimeField(default=timezone.now, editable=False)
    lease_token = models.UUIDField(null=True, editable=False)
    lease_expires_at = models.DateTimeField(null=True, editable=False)
    processed_at = models.DateTimeField(null=True, editable=False)
    last_error_code = models.CharField(max_length=64, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "core_event_consumer"
        constraints = [
            models.UniqueConstraint(
                fields=("event_id", "consumer_name"),
                name="core_consumer_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=ConsumerStatus.PROCESSED,
                        processed_at__isnull=False,
                        lease_token__isnull=True,
                        lease_expires_at__isnull=True,
                    )
                    | Q(
                        status=ConsumerStatus.PROCESSING,
                        processed_at__isnull=True,
                        lease_token__isnull=False,
                        lease_expires_at__isnull=False,
                    )
                    | Q(
                        status=ConsumerStatus.PENDING,
                        processed_at__isnull=True,
                        lease_token__isnull=True,
                        lease_expires_at__isnull=True,
                    )
                ),
                name="core_consumer_state_shape",
            ),
        ]
        indexes = [
            models.Index(
                fields=("available_at", "lease_expires_at"),
                name="core_consumer_ready_idx",
                condition=~Q(status=ConsumerStatus.PROCESSED),
            )
        ]
