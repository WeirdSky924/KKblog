from django.db import models


class BootstrapState(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    account_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "account_bootstrap_state"
