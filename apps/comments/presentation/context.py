from django.conf import settings
from django.urls import reverse

from ..queries import comment_thread_panel
from ..receipts import decode_comment_receipts
from ..targets import GUESTBOOK_TARGET_ID, DiscussionTargetType
from .forms import TopLevelCommentForm


def _comment_context(
    *,
    request,
    target_type: DiscussionTargetType,
    target_id: str,
    noun: str,
    post_url: str,
    page_url: str,
    image_upload_url: str,
    return_url: str,
    return_label: str,
    form: TopLevelCommentForm | None,
    feedback: str,
    receipt_ids: tuple[str, ...] | None,
    sort,
    cursor: str | None,
) -> dict[str, object]:
    active_receipts = (
        receipt_ids
        if receipt_ids is not None
        else decode_comment_receipts(
            request.COOKIES.get(settings.COMMENTS_RECEIPT_COOKIE_NAME)
        )
    )
    return {
        "comment_panel": comment_thread_panel(
            actor_id=getattr(request, "account_id", None),
            target_type=target_type,
            target_id=target_id,
            receipt_ids=active_receipts,
            sort=sort,
            cursor=cursor,
        ),
        "comment_form": form or TopLevelCommentForm(noun=noun),
        "comment_feedback": feedback,
        "comment_post_url": post_url,
        "comment_page_url": page_url,
        "comment_target_type": target_type.value,
        "comment_target_id": target_id,
        "comment_noun": noun,
        "comment_image_upload_url": image_upload_url,
        "comment_return_url": return_url,
        "comment_return_label": return_label,
    }


def article_comment_context(
    *,
    request,
    article_id: str,
    form: TopLevelCommentForm | None = None,
    feedback: str = "",
    receipt_ids: tuple[str, ...] | None = None,
    sort="earliest",
    cursor: str | None = None,
) -> dict[str, object]:
    article_url = reverse("article:detail", kwargs={"article_id": article_id})
    context = _comment_context(
        request=request,
        target_type=DiscussionTargetType.ARTICLE,
        target_id=article_id,
        noun="评论",
        post_url=reverse("article:comment-create", kwargs={"article_id": article_id}),
        page_url=reverse("article:comment-page", kwargs={"article_id": article_id}),
        image_upload_url=reverse(
            "article:comment-image", kwargs={"article_id": article_id}
        ),
        return_url=article_url,
        return_label="返回文章",
        form=form,
        feedback=feedback,
        receipt_ids=receipt_ids,
        sort=sort,
        cursor=cursor,
    )
    context["comment_article_id"] = article_id
    context["comment_article_url"] = article_url
    return context


def guestbook_comment_context(
    *,
    request,
    form: TopLevelCommentForm | None = None,
    feedback: str = "",
    receipt_ids: tuple[str, ...] | None = None,
    sort="earliest",
    cursor: str | None = None,
) -> dict[str, object]:
    return _comment_context(
        request=request,
        target_type=DiscussionTargetType.GUESTBOOK,
        target_id=GUESTBOOK_TARGET_ID,
        noun="留言",
        post_url=reverse("public:guestbook-comment-create"),
        page_url=reverse("public:guestbook-comment-page"),
        image_upload_url=reverse("public:guestbook-comment-image"),
        return_url=reverse("public:guestbook"),
        return_label="返回留言板",
        form=form,
        feedback=feedback,
        receipt_ids=receipt_ids,
        sort=sort,
        cursor=cursor,
    )


def comment_context_for_target(
    *,
    request,
    target_type: str,
    target_id: str,
    **kwargs,
) -> dict[str, object]:
    target = DiscussionTargetType(target_type)
    if target is DiscussionTargetType.ARTICLE:
        return article_comment_context(
            request=request,
            article_id=target_id,
            **kwargs,
        )
    return guestbook_comment_context(request=request, **kwargs)
