from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.administration",
    "apps.core",
    "apps.discovery",
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
        "OPTIONS": {},
    }
]

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [("dist", BASE_DIR / "static" / "dist")]
STATIC_ROOT = BASE_DIR / "var" / "staticfiles"
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
