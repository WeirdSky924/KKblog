from django.conf import settings
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render

from apps.authoring.queries import article_body_media_workspace
from apps.content.public import ArticleNotFound
from apps.media.public import (
    CleanupOutcome,
    MediaCleanupRetryable,
    MediaPurpose,
    OwnedMediaDeleteError,
    delete_owned_unbound_asset,
)
from apps.media.storage import FilesystemMediaStorage

from .access import author_id_or_response, private_response


def _workspace(request, *, actor_id, upload_scope: str):
    try:
        return article_body_media_workspace(
            actor_id=actor_id,
            upload_scope=upload_scope,
            article_id=request.GET.get("article", ""),
        )
    except (ArticleNotFound, ValueError):
        raise Http404 from None


def body_media_library(request, upload_scope: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "GET":
        return private_response(HttpResponseNotAllowed(("GET",)))
    workspace = _workspace(
        request,
        actor_id=actor_id,
        upload_scope=upload_scope,
    )
    return private_response(
        render(
            request,
            "authoring/partials/body_media_library.html",
            {"body_media_workspace": workspace},
        )
    )


def delete_body_media(request, upload_scope: str, asset_id: str):
    actor_id, response = author_id_or_response(request)
    if response is not None:
        return response
    if request.method != "POST":
        return private_response(HttpResponseNotAllowed(("POST",)))
    workspace = _workspace(
        request,
        actor_id=actor_id,
        upload_scope=upload_scope,
    )
    item = next(
        (candidate for candidate in workspace.items if candidate.asset_id == asset_id),
        None,
    )
    if item is None:
        raise Http404
    if not item.deletable:
        return private_response(
            JsonResponse(
                {"ok": False, "message": "图片已被文章版本使用，不能删除。"},
                status=409,
            )
        )
    try:
        result = delete_owned_unbound_asset(
            owner_id=actor_id,
            asset_id=asset_id,
            purpose=MediaPurpose.BODY,
            storage=FilesystemMediaStorage(settings.MEDIA_ROOT),
        )
    except OwnedMediaDeleteError as exc:
        status = 409 if exc.code == "media.asset_in_use.v1" else 404
        return private_response(
            JsonResponse({"ok": False, "message": exc.safe_message}, status=status)
        )
    except MediaCleanupRetryable:
        return private_response(
            JsonResponse(
                {
                    "ok": True,
                    "pending": True,
                    "message": "图片已从列表移除，服务器正在重试文件删除。",
                },
                status=202,
            )
        )
    pending = result.outcome == CleanupOutcome.SCHEDULED
    return private_response(
        JsonResponse(
            {
                "ok": True,
                "pending": pending,
                "message": (
                    "图片已从列表移除，服务器正在完成文件删除。"
                    if pending
                    else "图片及服务器文件已删除。"
                ),
            },
            status=202 if pending else 200,
        )
    )
