# ruff: noqa: F403,F405
import os
import secrets

from config.environment import (
    load_isolated_test_database,
    load_isolated_test_mailpit,
    load_isolated_test_redis,
)

from .base import *

SECRET_KEY = secrets.token_urlsafe(64)
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
SITE_BASE_URL = "http://localhost"

DATABASES = {
    "default": load_isolated_test_database(os.environ)
    or {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

ADMIN_EMAIL = "admin@kaj.test"
ADMINS = [("Kaj admin", ADMIN_EMAIL)]
DEFAULT_FROM_EMAIL = "no-reply@kaj.test"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "localhost"
EMAIL_PORT = 1025
EMAIL_USE_TLS = False

TEST_REDIS_URL = load_isolated_test_redis(os.environ)
if TEST_REDIS_URL is not None:
    REDIS_URL = TEST_REDIS_URL
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": TEST_REDIS_URL,
        }
    }
    CELERY_BROKER_URL = TEST_REDIS_URL
    CELERY_RESULT_BACKEND = TEST_REDIS_URL
_mailpit = load_isolated_test_mailpit(os.environ)
if _mailpit is not None:
    EMAIL_HOST = _mailpit.smtp_host
    EMAIL_PORT = _mailpit.smtp_port
    MAILPIT_API_URL = _mailpit.api_url
del _mailpit

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
