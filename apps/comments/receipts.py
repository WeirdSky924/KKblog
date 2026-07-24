from django.conf import settings
from django.core import signing

from apps.core.ids import normalize_ulid

_SALT = "comments.receipts.v1"
_MAX_RECEIPTS = 20


def decode_comment_receipts(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    try:
        payload = signing.loads(
            value,
            salt=_SALT,
            max_age=settings.COMMENTS_RECEIPT_MAX_AGE_SECONDS,
        )
    except signing.BadSignature:
        return ()
    if not isinstance(payload, list) or len(payload) > _MAX_RECEIPTS:
        return ()
    receipts = []
    for item in payload:
        try:
            receipts.append(normalize_ulid(item))
        except (TypeError, ValueError):
            return ()
    return tuple(dict.fromkeys(receipts))


def add_comment_receipt(receipts: tuple[str, ...], comment_id: str) -> tuple[str, ...]:
    identity = normalize_ulid(comment_id)
    return tuple(dict.fromkeys((*receipts, identity)))[-_MAX_RECEIPTS:]


def encode_comment_receipts(receipts: tuple[str, ...]) -> str:
    normalized = [normalize_ulid(item) for item in receipts[-_MAX_RECEIPTS:]]
    return signing.dumps(normalized, salt=_SALT, compress=True)


def set_comment_receipt_cookie(response, receipts: tuple[str, ...]) -> None:
    response.set_cookie(
        settings.COMMENTS_RECEIPT_COOKIE_NAME,
        encode_comment_receipts(receipts),
        max_age=settings.COMMENTS_RECEIPT_MAX_AGE_SECONDS,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="Lax",
        path="/",
    )
