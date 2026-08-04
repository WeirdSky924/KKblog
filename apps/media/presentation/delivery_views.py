import re

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET, require_http_methods

from apps.media.services.access import MediaAccessError, authorize_asset_read
from apps.media.storage import FilesystemMediaStorage, StorageBoundaryError

_DELIVERY_URI = re.compile(r"/_kaj/media/([0-9A-HJKMNP-TV-Z]{26})")
_PUBLIC_CACHE_CONTROL = "public, max-age=31536000, immutable"
_PRIVATE_CACHE_CONTROL = "private, no-store"


def _privacy_not_found() -> HttpResponse:
    response = HttpResponse(status=404)
    response.headers["Cache-Control"] = _PRIVATE_CACHE_CONTROL
    return response


@require_GET
def internal_authorize(request: HttpRequest) -> HttpResponse:
    if request.headers.get("X-Kaj-Internal-Auth") != "1":
        return _privacy_not_found()

    match = _DELIVERY_URI.fullmatch(request.headers.get("X-Forwarded-Uri", ""))
    if match is None:
        return _privacy_not_found()

    try:
        authorization = authorize_asset_read(
            actor_id=getattr(request, "account_id", None),
            asset_id=match.group(1),
        )
    except MediaAccessError:
        return _privacy_not_found()

    cache_control = (
        _PUBLIC_CACHE_CONTROL
        if authorization.public_immutable
        else _PRIVATE_CACHE_CONTROL
    )
    response = HttpResponse()
    response.headers["X-Kaj-Storage-Key"] = authorization.storage_key
    response.headers["X-Kaj-Cache-Control"] = cache_control
    response.headers["X-Kaj-Public"] = "1" if authorization.public_immutable else "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = _PRIVATE_CACHE_CONTROL
    return response


@require_http_methods(["GET", "HEAD"])
def direct_delivery(request: HttpRequest, asset_id: str) -> HttpResponse:
    if not settings.DIRECT_MEDIA_DELIVERY_ENABLED:
        return _privacy_not_found()
    try:
        authorization = authorize_asset_read(
            actor_id=getattr(request, "account_id", None),
            asset_id=asset_id,
        )
        content = FilesystemMediaStorage(settings.MEDIA_ROOT).read(
            authorization.storage_key
        )
    except (FileNotFoundError, MediaAccessError, StorageBoundaryError):
        return _privacy_not_found()

    response = HttpResponse(content, content_type=authorization.detected_mime)
    response.headers["Cache-Control"] = (
        _PUBLIC_CACHE_CONTROL
        if authorization.public_immutable
        else _PRIVATE_CACHE_CONTROL
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
