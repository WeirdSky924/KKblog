from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from django.apps import apps
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.comments.models import Comment
from apps.comments.services.threads import sync_article_thread
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
)
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str):
    model = apps.get_model("accounts", "Account")
    account = model.objects.create_account(
        email=f"cmt005-http-{uuid4()}@kaj.test",
        password="Valid-password-1",
        nickname=label,
    )
    role_model = apps.get_model("accounts", "RoleAssignment")
    role_model.objects.create(account=account, role="AUTHOR")
    role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _published_article(author) -> str:
    section = create_section(
        actor_id=author.id,
        name=f"游标分区-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title="评论游标文章",
            body="用于验证评论分批加载。",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    now = timezone.now() - timedelta(days=2)
    review = prepare_publication(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=FrozenClock(now),
    )
    publish_article(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=FrozenClock(now),
    )
    return draft.article_id


def _comment(
    thread,
    author,
    *,
    created_at,
    body,
    parent=None,
    root=None,
    depth=0,
    reply_count=0,
    state=Comment.State.VISIBLE,
) -> Comment:
    comment_id = new_ulid()
    deleted = state == Comment.State.DELETED
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=parent,
        root_id=comment_id if root is None else root.id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body="" if deleted else body,
        state=state,
        visible_at=created_at,
        depth=depth,
        reply_count=reply_count,
        client_ip="192.0.2.60",
        deleted_by_kind=Comment.DeletedByKind.OWNER if deleted else None,
        created_at=created_at,
    )


def test_article_thread_renders_fixed_batches_and_htmx_cursor_endpoints() -> None:
    owner = _account("游标作者")
    article_id = _published_article(owner)
    thread, _ = sync_article_thread(actor_id=owner.id, article_id=article_id)
    base = timezone.now() - timedelta(days=1)
    roots = [
        _comment(
            thread,
            owner,
            created_at=base + timedelta(minutes=index),
            body=f"顶层评论 {index:02d}",
            reply_count=11 if index == 0 else 0,
            state=Comment.State.DELETED if index == 5 else Comment.State.VISIBLE,
        )
        for index in range(21)
    ]
    replies = []
    parent = roots[0]
    for index in range(11):
        reply = _comment(
            thread,
            owner,
            created_at=base + timedelta(minutes=30, seconds=index),
            body=f"分批回复 {index:02d}",
            parent=parent,
            root=roots[0],
            depth=index + 1,
        )
        replies.append(reply)
        parent = reply

    client = Client(REMOTE_ADDR="198.51.100.60")
    detail_url = reverse("article:detail", kwargs={"article_id": article_id})
    page_url = reverse("article:comment-page", kwargs={"article_id": article_id})
    reply_url = reverse(
        "article:comment-replies",
        kwargs={"article_id": article_id, "root_id": roots[0].id},
    )
    page = client.get(detail_url)
    assert page.status_code == 200
    html = page.content.decode()
    assert 'data-comment-sort-control="earliest"' in html
    assert 'data-comment-sort-control="latest"' in html
    assert 'data-comment-sort-control="hottest"' in html
    assert 'data-comment-public-list data-sort="earliest"' in html
    assert "顶层评论 00" in html
    assert "顶层评论 19" in html
    assert "顶层评论 20" not in html
    assert "顶层评论 05" not in html
    assert "该评论已删除" in html
    assert "分批回复 09" in html
    assert "分批回复 10" not in html
    assert f'hx-get="{page_url}?' in html
    assert f'hx-get="{reply_url}?' in html

    first_page = page.context["comment_panel"].public_page
    more = client.get(
        page_url,
        {"sort": "earliest", "cursor": first_page.next_cursor},
        HTTP_HX_REQUEST="true",
    )
    assert more.status_code == 200
    more_html = more.content.decode()
    assert "顶层评论 20" in more_html
    assert "顶层评论 19" not in more_html
    assert 'id="comment-public-list"' not in more_html
    assert more.headers["Cache-Control"] == "private, no-store"

    latest = client.get(page_url, {"sort": "latest"}, HTTP_HX_REQUEST="true")
    assert latest.status_code == 200
    latest_html = latest.content.decode()
    assert 'id="comment-public-list"' in latest_html
    assert 'data-sort="latest"' in latest_html
    assert latest_html.index("顶层评论 20") < latest_html.index("顶层评论 19")

    first_replies = first_page.items[0].reply_page
    reply_more = client.get(
        reply_url,
        {"cursor": first_replies.next_cursor},
        HTTP_HX_REQUEST="true",
    )
    assert reply_more.status_code == 200
    reply_more_html = reply_more.content.decode()
    assert "分批回复 10" in reply_more_html
    assert "分批回复 09" not in reply_more_html
    assert "data-comment-reply-focus" in reply_more_html

    invalid = client.get(
        page_url,
        {"sort": "earliest", "cursor": "tampered"},
        HTTP_HX_REQUEST="true",
    )
    assert invalid.status_code == 422
    assert "评论列表未能继续加载" in invalid.content.decode()
    assert invalid.headers["Cache-Control"] == "private, no-store"


def test_comment_sort_preference_is_browser_only() -> None:
    source = Path(__file__).resolve().parents[3] / "static" / "src" / "comments.js"
    content = source.read_text(encoding="utf-8")
    assert '"kaj.comment-sort"' in content
    assert "localStorage" in content
    assert "data-comment-sort-control" in content
