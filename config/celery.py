"""Celery application entry point for the Kaj runtime."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("kaj_blog")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.imports = ("config.runtime_tasks",)
app.autodiscover_tasks()

celery_app = app
