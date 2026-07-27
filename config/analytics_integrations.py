from django.conf import settings

from apps.analytics.services.retention import (
    PostgresUmamiRetentionStore,
    UmamiRetentionCounts,
    UmamiRetentionResult,
    expire_umami_data,
)
from apps.core.time.clock import Clock, SystemClock


def expire_configured_umami_data(*, clock: Clock | None = None) -> UmamiRetentionResult:
    active_clock = clock or SystemClock()
    if not getattr(settings, "ANALYTICS_ENABLED", False):
        result = expire_umami_data(
            store=_DisabledRetentionStore(),
            clock=active_clock,
        )
        return result
    database_url = getattr(settings, "ANALYTICS_DATABASE_URL", "")
    store = PostgresUmamiRetentionStore(database_url)
    return expire_umami_data(store=store, clock=active_clock)


class _DisabledRetentionStore:
    def delete_before(self, _cutoff):
        return UmamiRetentionCounts()
