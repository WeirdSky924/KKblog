from django.urls import path

from apps.accounts.presentation.views import (
    login,
    password_reset,
    register,
    sessions_view,
    settings_view,
)

app_name = "accounts"

urlpatterns = [
    path("login/", login, name="login"),
    path("password-reset/", password_reset, name="password-reset"),
    path("register/", register, name="register"),
    path("sessions/", sessions_view, name="sessions"),
    path("settings/", settings_view, name="settings"),
]
