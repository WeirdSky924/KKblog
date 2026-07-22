# ruff: noqa: F403,F405
import os
import secrets

from config.environment import (
    load_development_database,
    load_development_mailpit,
    load_development_redis,
    load_trusted_proxy_cidrs,
)

from .base import *

SECRET_KEY = secrets.token_urlsafe(64)
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
SITE_BASE_URL = "http://localhost"
TRUSTED_PROXY_CIDRS = load_trusted_proxy_cidrs(os.environ)

DATABASES = {
    "default": load_development_database(os.environ)
    or {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "var" / "development.sqlite3",
    },
}

REDIS_URL = load_development_redis(os.environ)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

ADMIN_EMAIL = "admin@kaj.test"
ADMINS = [("Kaj admin", ADMIN_EMAIL)]
DEFAULT_FROM_EMAIL = "no-reply@kaj.test"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
_mailpit = load_development_mailpit(os.environ)
EMAIL_HOST = _mailpit.host
EMAIL_PORT = _mailpit.port
EMAIL_USE_TLS = False

del _mailpit
