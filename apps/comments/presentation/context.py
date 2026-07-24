from django.conf import settings
from django.urls import reverse

from ..queries import article_comment_panel
from ..receipts import decode_comment_receipts
from .forms import TopLevelCommentForm


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
    active_receipts = (
        receipt_ids
        if receipt_ids is not None
        else decode_comment_receipts(
            request.COOKIES.get(settings.COMMENTS_RECEIPT_COOKIE_NAME)
        )
    )
    return {
        "comment_panel": article_comment_panel(
            actor_id=getattr(request, "account_id", None),
            article_id=article_id,
            receipt_ids=active_receipts,
            sort=sort,
            cursor=cursor,
        ),
        "comment_form": form or TopLevelCommentForm(),
        "comment_feedback": feedback,
        "comment_post_url": reverse(
            "article:comment-create", kwargs={"article_id": article_id}
        ),
        "comment_page_url": reverse(
            "article:comment-page", kwargs={"article_id": article_id}
        ),
        "comment_article_id": article_id,
        "comment_image_upload_url": reverse(
            "article:comment-image", kwargs={"article_id": article_id}
        ),
        "comment_article_url": reverse(
            "article:detail", kwargs={"article_id": article_id}
        ),
    }
