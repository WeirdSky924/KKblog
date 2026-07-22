from django.conf import settings


def set_session_cookie(
    response, *, raw_token: str, remember: bool, max_age: int | None = None
) -> None:
    if max_age is None:
        max_age = 30 * 24 * 60 * 60 if remember else 12 * 60 * 60
    response.set_cookie(
        settings.ACCOUNT_SESSION_COOKIE_NAME,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path="/",
    )


def delete_session_cookie(response) -> None:
    response.delete_cookie(
        settings.ACCOUNT_SESSION_COOKIE_NAME,
        path="/",
        samesite="Lax",
    )
