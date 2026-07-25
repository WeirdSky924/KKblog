# ruff: noqa: F403,F405
import os

from config.environment import load_production_environment

from .base import *

_environment = load_production_environment(os.environ)

SECRET_KEY = _environment.secret_key
DEBUG = False
ALLOWED_HOSTS = [_environment.public_host]
SITE_BASE_URL = _environment.public_url
CSRF_TRUSTED_ORIGINS = [_environment.public_url]

DATABASES = {"default": _environment.database}
REDIS_URL = _environment.redis_url
MEDIA_ROOT = _environment.media_root
INITIAL_ADMIN_PASSWORD = _environment.initial_admin_password
TRUSTED_PROXY_CIDRS = _environment.trusted_proxy_cidrs

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
OUTBOX_TRANSPORT = "config.outbox_transport.build_application_event_transport"

ADMIN_EMAIL = _environment.admin_email
ADMINS = [("Kaj admin", ADMIN_EMAIL)]
DEFAULT_FROM_EMAIL = _environment.resend_from_email
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.resend.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = "resend"
EMAIL_HOST_PASSWORD = _environment.resend_api_key
EMAIL_USE_TLS = True
OPERATIONAL_EMAIL_PROVIDER = "resend"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

del _environment
