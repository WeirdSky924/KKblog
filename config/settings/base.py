from pathlib import Path

from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.postgres",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.administration",
    "apps.analytics",
    "apps.comments",
    "apps.content",
    "apps.core",
    "apps.discovery",
    "apps.exchange",
    "apps.media",
    "apps.moderation",
    "apps.navigation",
    "apps.notifications",
    "apps.operations",
]

MIDDLEWARE = [
    "apps.core.observability.trace.TraceMiddleware",
    "apps.core.errors.handlers.ErrorResponseMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "apps.accounts.middleware.NetworkPolicyMiddleware",
    "apps.accounts.middleware.AccountSessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "apps.accounts.presentation.context.account_theme",
                "apps.analytics.presentation.context.analytics_tracking",
                "apps.navigation.presentation.context.site_shell",
            ]
        },
    }
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [("dist", BASE_DIR / "static" / "dist")]
STATIC_ROOT = BASE_DIR / "var" / "staticfiles"
MEDIA_ROOT = BASE_DIR / "var" / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_TIMEOUT = 10
DIRECT_REGISTRATION_ENABLED = False
ACCOUNT_SESSION_COOKIE_NAME = "kaj_session"
TRUSTED_PROXY_CIDRS = ()
NETWORK_PUBLIC_NAMESPACES = ("public", "article")
NETWORK_POLICY_EXEMPT_VIEW_NAMES = ("operations:live", "operations:ready")

OUTBOX_BATCH_SIZE = 100
OUTBOX_LEASE_SECONDS = 60
OUTBOX_RETRY_DELAY_SECONDS = 60

CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ENABLE_UTC = True
CELERY_TIMEZONE = "UTC"
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_RESULT_EXPIRES = 300
CELERY_TASK_IGNORE_RESULT = True
CELERY_BEAT_SCHEDULE = {
    "core-publish-outbox": {
        "task": "config.runtime_tasks.publish_outbox",
        "schedule": 5.0,
    },
    "operations-send-alert-emails": {
        "task": "config.runtime_tasks.send_operational_alert_emails",
        "schedule": 60.0,
    },
    "operations-check-capacity": {
        "task": "apps.operations.check_capacity",
        "schedule": 300.0,
    },
    "operations-check-service-health": {
        "task": "apps.operations.check_service_health",
        "schedule": 60.0,
    },
    "comments-publish-due": {
        "task": "apps.comments.dispatch_due_comments",
        "schedule": 60.0,
    },
    "content-purge-deleted": {
        "task": "apps.content.dispatch_deleted_articles",
        "schedule": 3600.0,
    },
    "content-publish-scheduled": {
        "task": "apps.content.dispatch_scheduled_articles",
        "schedule": 60.0,
    },
    "media-delete-pending": {
        "task": "apps.media.dispatch_pending_media",
        "schedule": 60.0,
    },
    "media-cleanup-staged": {
        "task": "apps.media.dispatch_staged_media",
        "schedule": 3_600.0,
    },
    "exchange-expire-exports": {
        "task": "apps.exchange.dispatch_expired_exports",
        "schedule": 3_600.0,
    },
    "operations-weekly-backup": {
        "task": "apps.operations.weekly_backup",
        # CELERY_TIMEZONE is UTC; Sunday 19:00 UTC is Monday 03:00 Shanghai.
        "schedule": crontab(minute=0, hour=19, day_of_week=0),
    },
    "operations-expire-backups": {
        "task": "apps.operations.dispatch_expired_backups",
        "schedule": crontab(minute=30, hour=19),
    },
    "analytics-expire-umami-data": {
        "task": "apps.analytics.expire_umami_data",
        # 19:45 UTC is 03:45 in Asia/Shanghai.
        "schedule": crontab(minute=45, hour=19),
    },
}

MEDIA_STAGED_EXPIRY_SECONDS = 86_400
MEDIA_CLEANUP_BATCH_SIZE = 100
DISCOVERY_TITLE_SEARCH_THRESHOLD = 0.2
DISCOVERY_CACHE_NAMESPACE = "kaj"
DISCOVERY_ARTICLE_CACHE_TTL_SECONDS = 3_600
DISCOVERY_LIST_CACHE_TTL_SECONDS = 60
COMMENTS_COOLDOWN_NAMESPACE = "kaj"
COMMENTS_ACCOUNT_POLICY_PROVIDER = "config.comment_integrations.comment_account_policy"
COMMENTS_MEDIA_GATEWAY_PROVIDER = "config.comment_integrations.comment_media_gateway"
COMMENTS_RECEIPT_COOKIE_NAME = "kaj_comment_receipts"
COMMENTS_RECEIPT_MAX_AGE_SECONDS = 90 * 24 * 60 * 60
COMMENTS_PUBLICATION_BATCH_SIZE = 100
MODERATION_ACCOUNT_POLICY_PROVIDER = (
    "config.moderation_integrations.moderation_account_policy"
)
MODERATION_EVIDENCE_GATEWAY_PROVIDER = (
    "config.moderation_integrations.report_evidence_gateway"
)
MODERATION_APPEAL_EVIDENCE_GATEWAY_PROVIDER = (
    "config.moderation_integrations.report_appeal_evidence_gateway"
)
MODERATION_ARTICLE_APPEAL_EVIDENCE_GATEWAY_PROVIDER = (
    "config.moderation_integrations.article_appeal_evidence_gateway"
)
CONTENT_SCHEDULE_BATCH_SIZE = 100
CONTENT_PURGE_BATCH_SIZE = 100
ARTICLE_BODY_MAX_BYTES = 2 * 1024 * 1024
EXCHANGE_IMPORT_ROOT = BASE_DIR / "var" / "exchange" / "imports"
EXCHANGE_IMPORT_COMPRESSED_MAX_BYTES = 64 * 1024 * 1024
EXCHANGE_IMPORT_EXPANDED_MAX_BYTES = 256 * 1024 * 1024
EXCHANGE_IMPORT_ITEM_MAX_COUNT = 1000
EXCHANGE_IMPORT_PATH_MAX_DEPTH = 8
EXCHANGE_IMPORT_COMPRESSION_MAX_RATIO = 100
EXCHANGE_EXPORT_ROOT = BASE_DIR / "var" / "exchange" / "exports"
EXCHANGE_EXPORT_EXPIRY_BATCH_SIZE = 100
BACKUP_ROOT = BASE_DIR / "var" / "backups"
BACKUP_DESTINATION = "local"
BACKUP_TIMEZONE = "Asia/Shanghai"
BACKUP_CRON = "0 3 * * 1"
BACKUP_PG_DUMP_BINARY = "/usr/lib/postgresql/16/bin/pg_dump"
BACKUP_HEARTBEAT_INTERVAL_SECONDS = 30
BACKUP_EXPIRY_BATCH_SIZE = 100
ANALYTICS_ENABLED = False
ANALYTICS_DATABASE_URL = ""
ANALYTICS_WEBSITE_ID = ""
NAVIGATION_SITE_PRESENTATION_PROVIDER = (
    "apps.navigation.public.default_site_presentation"
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact": {"()": "apps.core.errors.redaction.RedactingFilter"},
    },
    "formatters": {
        "safe": {
            "format": "{levelname} {name} trace={trace_code} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["redact"],
            "formatter": "safe",
        }
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.server": {"handlers": [], "level": "WARNING", "propagate": False},
        "kaj": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
