from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from django.apps import apps
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from apps.comments.models import Comment, DiscussionThread
from apps.comments.services.deletion import delete_own_comment
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from config.comment_integrations import comment_account_policy, comment_media_gateway

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str):
    model = apps.get_model("accounts", "Account")
    return model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (16, 12), (120, 30, 70)).save(stream, format="PNG")
    return stream.getvalue()


def _buffered_comment(thread, author, label: str) -> Comment:
    comment_id = new_ulid()
    now = timezone.now()
    return Comment.objects.create(
        id=comment_id,
        thread=thread,
        parent=None,
        root_id=comment_id,
        author=author,
        author_kind=Comment.AuthorKind.ACCOUNT,
        body=label,
        state=Comment.State.BUFFERED,
        visible_at=now + timedelta(minutes=10),
        depth=0,
        reply_count=0,
        client_ip="192.0.2.96",
        created_at=now,
    )


def _bind_image(gateway, *, thread, comment, actor, label: str):
    staged = gateway.stage_image(
        actor_id=actor.id,
        thread_owner_id=thread.owner_id,
        target_type="GUESTBOOK",
        target_id="site",
        client_ip="198.51.100.96",
        original_name=f"{label}.png",
        declared_content_type="image/png",
        chunks=(_png(),),
    )
    gateway.bind_images(
        actor_id=actor.id,
        thread_owner_id=thread.owner_id,
        target_type="GUESTBOOK",
        target_id="site",
        comment_id=comment.id,
        client_ip="198.51.100.96",
        image_refs=(staged.image_ref,),
    )
    return apps.get_model("media", "MediaAsset").objects.get(pk=staged.asset_id)


def test_delete_releases_binding_and_deletes_present_or_missing_file(tmp_path) -> None:
    owner = _account("cmt006-media-owner")
    member = _account("cmt006-media-member")
    thread = DiscussionThread.objects.create(
        target_type="GUESTBOOK",
        target_id="site",
        owner=owner,
    )
    policy = comment_account_policy()

    with override_settings(MEDIA_ROOT=tmp_path):
        gateway = comment_media_gateway()
        present_comment = _buffered_comment(thread, member, "删除现有文件")
        present_asset = _bind_image(
            gateway,
            thread=thread,
            comment=present_comment,
            actor=member,
            label="present",
        )
        present_path = tmp_path / present_asset.storage_key
        assert present_path.is_file()

        result = delete_own_comment(
            comment_id=present_comment.id,
            actor_id=member.id,
            client_ip="198.51.100.96",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=gateway,
        )
        present_asset.refresh_from_db()
        present_comment.refresh_from_db()
        assert result.asset_ids == (present_asset.id,)
        assert present_comment.state == Comment.State.DELETED
        assert present_asset.state == "DELETED"
        assert not present_path.exists()
        assert (
            not apps.get_model("media", "MediaBinding")
            .objects.filter(target_id=present_comment.id)
            .exists()
        )

        missing_comment = _buffered_comment(thread, member, "删除缺失文件")
        missing_asset = _bind_image(
            gateway,
            thread=thread,
            comment=missing_comment,
            actor=member,
            label="missing",
        )
        missing_path = tmp_path / missing_asset.storage_key
        missing_path.unlink()
        delete_own_comment(
            comment_id=missing_comment.id,
            actor_id=member.id,
            client_ip="198.51.100.97",
            trace_code=new_trace_code(),
            account_policy=policy,
            media_gateway=gateway,
        )
        missing_asset.refresh_from_db()
        assert missing_asset.state == "DELETED"
        assert not missing_path.exists()
