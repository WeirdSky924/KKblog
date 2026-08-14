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
    request: HttpRequest,
    *,
    purpose: MediaPurpose,
    input_name: str,
    target_id: str | None = None,
) -> HttpResponse:
    is_attachment = purpose == MediaPurpose.ATTACHMENT
    is_hero = purpose == MediaPurpose.HERO
    select_message = (
        "请选择一个附件后重试。"
        if is_attachment
        else (
            "请选择一张图片或一个视频后重试。" if is_hero else "请选择一张图片后重试。"
        )
    )
    if request.method != "POST":
        response = render(
            request,
            "media/partials/upload_result.html",
            {
                "upload_error": select_message,
                "is_attachment": is_attachment,
                "is_hero": is_hero,
            },
            status=405,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    uploaded = request.FILES.get("file")
    if uploaded is None or len(request.FILES) != 1:
        response = render(
            request,
            "media/partials/upload_result.html",
            {
                "upload_error": select_message,
                "is_attachment": is_attachment,
                "is_hero": is_hero,
            },
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
            target_id=target_id,
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
                "is_attachment": is_attachment,
                "is_hero": is_hero,
            },
            status=422,
        )
    else:
        response = render(
            request,
            "media/partials/upload_result.html",
            {
                "asset": asset,
                "input_name": input_name,
                "is_attachment": is_attachment,
                "is_hero": is_hero,
                "is_video": asset.detected_mime.startswith("video/"),
            },
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
    target_id = None
    if configured.target_query_parameter is not None:
        target_id = request.GET.get(configured.target_query_parameter, "")
        assert configured.target_access is not None
        if not target_id or not configured.target_access(actor_id, target_id):
            response = HttpResponse(status=404)
            response.headers["Cache-Control"] = "private, no-store"
            return response
    return _render_upload(
        request,
        purpose=configured.purpose,
        input_name=configured.input_name,
        target_id=target_id,
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
