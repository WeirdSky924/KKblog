from django.db import models

from apps.core.ids import new_ulid


class SecurityEvent(models.Model):
    id = models.CharField(
        primary_key=True, max_length=26, default=new_ulid, editable=False
    )
    event_type = models.CharField(max_length=64, editable=False)
    account = models.ForeignKey(
        "accounts.Account",
        related_name="security_events",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    subject_digest = models.CharField(max_length=64, blank=True, editable=False)
    client_ip = models.GenericIPAddressField(
        protocol="both", unpack_ipv4=True, editable=False
    )
    trace_code = models.CharField(max_length=30, editable=False)
    safe_summary = models.JSONField(default=dict, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        db_table = "account_security_event"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=("event_type", "created_at"), name="security_event_type_idx"
            ),
            models.Index(
                fields=("account", "created_at"), name="security_event_account_idx"
            ),
        ]
