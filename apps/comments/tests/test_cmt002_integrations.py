from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from io import BytesIO
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.test import override_settings
from PIL import Image
from redis import Redis

from apps.comments.cooldown import (
    CommentCooldownActive,
    CommentCooldownStore,
    CooldownReservation,
)
from apps.comments.models import Comment
from apps.comments.public import (
    CommentPostingError,
    create_top_level_comment,
    stage_top_level_comment_image,
)
from apps.content.public import (
    ArticleSnapshot,
    ContentFormat,
    create_article,
    create_section,
    prepare_publication,
    publish_article,
)
from apps.core.observability.trace import new_trace_code
from apps.core.time.clock import FrozenClock

pytestmark = pytest.mark.django_db(transaction=True)


def _admin_author(label: str):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    role_model.objects.create(account=account, role="AUTHOR")
    role_model.objects.create(account=account, role="ADMINISTRATOR")
    return account


def _published_article(author, label: str) -> str:
    section = create_section(
        actor_id=author.id,
        name=f"{label}-{uuid4()}",
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    draft = create_article(
        actor_id=author.id,
        snapshot=ArticleSnapshot(
            content_format=ContentFormat.MARKDOWN,
            title=label,
            body="正文",
            section_id=section.section_id,
        ),
        capacity_check=lambda: None,
    )
    now = datetime(2026, 7, 24, 13, 0, tzinfo=UTC)
    clock = FrozenClock(now)
    review = prepare_publication(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        clock=clock,
    )
    publish_article(
        actor_id=author.id,
        article_id=draft.article_id,
        revision_id=draft.revision_id,
        expected_row_version=draft.row_version,
        review_token=review.token,
        trace_code=new_trace_code(),
        clock=clock,
    )
    return draft.article_id


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (12, 8), color).save(output, format="PNG")
    return output.getvalue()


def _redis_store(label: str) -> tuple[CommentCooldownStore, Redis, str]:
    namespace = f"kaj-test-cmt002-{label}-{uuid4()}"
    client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    return CommentCooldownStore(client=client, namespace=namespace), client, namespace


def _clear_namespace(client: Redis, namespace: str) -> None:
    keys = tuple(client.scan_iter(match=f"{namespace}:*"))
    if keys:
        client.delete(*keys)


def test_real_redis_cooldown_is_atomic_digested_and_owner_rollback_only() -> None:
    store, client, namespace = _redis_store("atomic")

    def reserve_once(index: int):
        try:
            return store.reserve(
                subject_kind="IP",
                subject_value="198.51.100.77",
                ttl_seconds=300,
            )
        except CommentCooldownActive as exc:
            return exc.remaining_seconds + index * 0

    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve_once, range(8)))
        reservations = [
            item for item in results if isinstance(item, CooldownReservation)
        ]
        remaining = [item for item in results if isinstance(item, int)]
        assert len(reservations) == 1
        assert len(remaining) == 7
        assert all(1 <= item <= 300 for item in remaining)

        reservation = reservations[0]
        assert "198.51.100.77" not in reservation.key
        assert 1 <= client.ttl(reservation.key) <= 300
        assert (
            store.rollback(
                CooldownReservation(key=reservation.key, token="different-owner")
            )
            is False
        )
        assert client.exists(reservation.key) == 1
        assert store.rollback(reservation) is True
        assert client.exists(reservation.key) == 0
    finally:
        _clear_namespace(client, namespace)


def test_real_anonymous_images_bind_to_comment_and_reject_cross_article_ref(
    tmp_path,
) -> None:
    author = _admin_author("cmt002-media-author")
    first_article = _published_article(author, "第一篇")
    second_article = _published_article(author, "第二篇")
    store, client, namespace = _redis_store("media")
    address = "198.51.100.42"

    try:
        with override_settings(MEDIA_ROOT=tmp_path):
            uploads = tuple(
                stage_top_level_comment_image(
                    target_type="ARTICLE",
                    target_id=first_article,
                    actor_id=None,
                    client_ip=address,
                    original_name=f"comment-{index}.png",
                    declared_content_type="image/png",
                    chunks=(_png_bytes(color),),
                )
                for index, color in enumerate(
                    ((200, 20, 20), (20, 160, 60), (30, 80, 190)),
                    1,
                )
            )
            assert all(address not in upload.image_ref for upload in uploads)
            result = create_top_level_comment(
                target_type="ARTICLE",
                target_id=first_article,
                actor_id=None,
                client_ip=address,
                body="带三张图片的访客评论",
                image_refs=tuple(upload.image_ref for upload in uploads),
                trace_code=new_trace_code(),
                cooldown_store=store,
            )

            binding_model = apps.get_model("media", "MediaBinding")
            asset_model = apps.get_model("media", "MediaAsset")
            bindings = list(
                binding_model.objects.filter(
                    target_type="comment", target_id=result.comment_id
                )
                .select_related("asset")
                .order_by("slot")
            )
            assert [binding.slot for binding in bindings] == [
                "image-1",
                "image-2",
                "image-3",
            ]
            assert {binding.asset.owner_id for binding in bindings} == {author.id}
            assert all(
                f"/articles/{first_article}/comments/" in binding.asset.storage_key
                for binding in bindings
            )
            assert (
                asset_model.objects.filter(
                    id__in=[upload.asset_id for upload in uploads], state="ACTIVE"
                ).count()
                == 3
            )

            cross = stage_top_level_comment_image(
                target_type="ARTICLE",
                target_id=first_article,
                actor_id=None,
                client_ip="198.51.100.99",
                original_name="cross.png",
                declared_content_type="image/png",
                chunks=(_png_bytes((10, 10, 10)),),
            )
            before = Comment.objects.filter(thread__target_id=second_article).count()
            with pytest.raises(CommentPostingError) as rejected:
                create_top_level_comment(
                    target_type="ARTICLE",
                    target_id=second_article,
                    actor_id=None,
                    client_ip="198.51.100.99",
                    body="不能跨文章绑定",
                    image_refs=(cross.image_ref,),
                    trace_code=new_trace_code(),
                    cooldown_store=store,
                )
            assert rejected.value.code == "comments.images_invalid.v1"
            assert (
                Comment.objects.filter(thread__target_id=second_article).count()
                == before
            )

            retry = store.reserve(
                subject_kind="IP",
                subject_value="198.51.100.99",
                ttl_seconds=300,
            )
            assert store.rollback(retry) is True
    finally:
        _clear_namespace(client, namespace)
