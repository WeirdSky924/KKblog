from apps.core.http import is_htmx_fragment_request


def is_htmx(request) -> bool:
    return is_htmx_fragment_request(request)


def posting_status(code: str) -> int:
    if code in {
        "comments.body_invalid.v1",
        "comments.guestbook_body_invalid.v1",
        "comments.images_invalid.v1",
        "comments.reply_images_forbidden.v1",
    }:
        return 422
    if code == "comments.cooldown_active.v1":
        return 429
    if code in {
        "comments.guestbook_daily_limit.v1",
        "comments.guestbook_account_daily_limit.v1",
    }:
        return 429
    if code in {
        "comments.login_required.v1",
        "comments.account_unavailable.v1",
        "comments.network_restricted.v1",
    }:
        return 403
    if code == "comments.closed.v1":
        return 409
    return 404
