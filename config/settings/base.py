from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.postgres",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.administration",
    "apps.comments",
    "apps.content",
    "apps.core",
    "apps.discovery",
    "apps.media",
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
CONTENT_SCHEDULE_BATCH_SIZE = 100
CONTENT_PURGE_BATCH_SIZE = 100
ARTICLE_BODY_MAX_BYTES = 2 * 1024 * 1024
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
