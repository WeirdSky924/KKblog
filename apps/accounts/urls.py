from django.urls import path

from apps.accounts.presentation.admin_password_reset import admin_password_reset_link
from apps.accounts.presentation.views import (
    login,
    password_reset,
    register,
    sessions_view,
    settings_view,
    theme_view,
)

app_name = "accounts"

urlpatterns = [
    path("login/", login, name="login"),
    path("password-reset/", password_reset, name="password-reset"),
    path(
        "password-reset/link/",
        admin_password_reset_link,
        name="admin-password-reset",
    ),
    path("register/", register, name="register"),
    path("sessions/", sessions_view, name="sessions"),
    path("settings/", settings_view, name="settings"),
    path("theme/", theme_view, name="theme"),
]
