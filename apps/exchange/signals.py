import logging

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete

from apps.exchange.models import ImportJob
from apps.exchange.staging import ImportStaging, ImportStagingError

logger = logging.getLogger(__name__)


def _cleanup_staging(job_id: str) -> None:
    try:
        ImportStaging(settings.EXCHANGE_IMPORT_ROOT).cleanup_job(job_id)
    except (ImportStagingError, OSError):
        logger.error(
            "exchange.import_staging_cleanup_failed.v1 job=%s",
            job_id,
        )


def _import_job_deleted(*, instance: ImportJob, **kwargs) -> None:
    del kwargs
    job_id = instance.id
    transaction.on_commit(lambda: _cleanup_staging(job_id))


def register_exchange_signals() -> None:
    post_delete.connect(
        _import_job_deleted,
        sender=ImportJob,
        dispatch_uid="exchange.import-job-staging-cleanup.v1",
        weak=False,
    )
