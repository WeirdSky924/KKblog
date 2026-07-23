from functools import partial

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.media.errors import MediaUploadError
from apps.media.models import MediaPurpose
from apps.media.services.uploads import stage_upload
from apps.media.storage import FilesystemMediaStorage
from apps.media.upload_adapters import default_media_upload_adapters
from apps.operations.public import require_image_creation_capacity


def _render_upload(
    request: HttpRequest, *, purpose: MediaPurpose, input_name: str
) -> HttpResponse:
    if request.method != "POST":
        response = render(
            request,
            "media/partials/upload_result.html",
            {"upload_error": "请选择一张图片后重试。"},
            status=405,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    uploaded = request.FILES.get("file")
    if uploaded is None or len(request.FILES) != 1:
        response = render(
            request,
            "media/partials/upload_result.html",
            {"upload_error": "请选择一张图片后重试。"},
            status=422,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    try:
        asset = stage_upload(
            owner_id=request.account_id,
            purpose=purpose,
            original_name=uploaded.name,
            declared_content_type=uploaded.content_type or "",
            chunks=uploaded.chunks(),
            storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
            capacity_check=partial(
                require_image_creation_capacity, settings.MEDIA_ROOT
            ),
        )
    except MediaUploadError as exc:
        response = render(
            request,
            "media/partials/upload_result.html",
            {
                "upload_error": exc.safe_message,
                "original_name": uploaded.name,
                "input_name": input_name,
            },
            status=422,
        )
    else:
        response = render(
            request,
            "media/partials/upload_result.html",
            {"asset": asset, "input_name": input_name},
            status=201,
        )
    response.headers["Cache-Control"] = "no-store"
    return response


def upload_for_adapter(request: HttpRequest, adapter: str) -> HttpResponse:
    try:
        configured = default_media_upload_adapters.resolve(adapter)
    except ValidationError:
        response = HttpResponse(status=404)
        response.headers["Cache-Control"] = "private, no-store"
        return response
    actor_id = getattr(request, "account_id", None)
    if not configured.access(actor_id):
        response = HttpResponse(status=404)
        response.headers["Cache-Control"] = "private, no-store"
        return response
    return _render_upload(
        request,
        purpose=configured.purpose,
        input_name=configured.input_name,
    )


def upload_avatar(request: HttpRequest) -> HttpResponse:
    if not getattr(request, "account_id", None):
        return redirect(
            f"{reverse('accounts:login')}?next={reverse('media:upload-avatar')}"
        )
    return _render_upload(
        request,
        purpose=MediaPurpose.AVATAR,
        input_name="avatar_asset_id",
    )
