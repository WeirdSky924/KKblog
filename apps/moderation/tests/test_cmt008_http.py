from datetime import timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from django.apps import apps
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.comments.services import sync_guestbook_thread
from apps.core.ids import new_ulid
from apps.moderation.models import Report, ReportReason

pytestmark = pytest.mark.django_db(transaction=True)


def _account(label: str, *, roles: tuple[str, ...] = ()):
    account_model = apps.get_model("accounts", "Account")
    role_model = apps.get_model("accounts", "RoleAssignment")
    account = account_model.objects.create_account(
        email=f"{label}-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    for role in roles:
        role_model.objects.create(account=account, role=role)
    return account


def _client(account, address: str) -> Client:
    token, _ = apps.get_model("accounts", "LoginSession").issue(
        account=account,
        remember=False,
    )
    client = Client(REMOTE_ADDR=address)
    client.cookies[settings.ACCOUNT_SESSION_COOKIE_NAME] = token
    return client


def _comment(thread, author):
    comment_model = apps.get_model("comments", "Comment")
    identity = new_ulid()
    now = timezone.now() - timedelta(minutes=20)
    return comment_model.objects.create(
        id=identity,
        thread=thread,
        parent=None,
        root_id=identity,
        author=author,
        author_kind=comment_model.AuthorKind.ACCOUNT,
        body="等待真实举报的留言",
        state=comment_model.State.VISIBLE,
        visible_at=now,
        depth=0,
        reply_count=0,
        client_ip="192.0.2.81",
        created_at=now,
    )


def _png() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (12, 10), (32, 91, 122)).save(stream, format="PNG")
    return stream.getvalue()


def _authorize(client: Client, asset_id: str):
    return client.get(
        reverse("media:internal-authorize"),
        HTTP_X_FORWARDED_URI=f"/_kaj/media/{asset_id}",
        HTTP_X_KAJ_INTERNAL_AUTH="1",
    )


def test_report_dialog_validation_success_duplicate_and_privacy(tmp_path) -> None:
    administrator = _account("cmt008-http-admin", roles=("ADMINISTRATOR",))
    reporter = _account("cmt008-http-reporter")
    target_author = _account("cmt008-http-target")
    other = _account("cmt008-http-other")
    thread = sync_guestbook_thread()
    comment = _comment(thread, target_author)
    page_url = reverse("public:guestbook")
    confirm_url = reverse(
        "moderation:report-confirm",
        kwargs={"comment_id": comment.id},
    )
    report_url = reverse(
        "moderation:report-create",
        kwargs={"comment_id": comment.id},
    )
    upload_url = reverse(
        "moderation:report-evidence-upload",
        kwargs={"comment_id": comment.id},
    )
    visitor = Client(REMOTE_ADDR="198.51.100.81")
    reporter_client = _client(reporter, "198.51.100.82")
    target_client = _client(target_author, "198.51.100.83")
    admin_client = _client(administrator, "198.51.100.84")
    other_client = _client(other, "198.51.100.85")

    with override_settings(MEDIA_ROOT=tmp_path):
        visitor_html = visitor.get(page_url).content.decode()
        reporter_html = reporter_client.get(page_url).content.decode()
        assert f'hx-get="{confirm_url}"' not in visitor_html
        assert f'hx-get="{confirm_url}"' in reporter_html
        assert visitor.get(confirm_url, HTTP_HX_REQUEST="true").status_code == 403
        assert (
            visitor.post(
                report_url,
                {"reason": ReportReason.SPAM},
                HTTP_HX_REQUEST="true",
            ).status_code
            == 403
        )

        dialog = reporter_client.get(confirm_url, HTTP_HX_REQUEST="true")
        assert dialog.status_code == 200
        dialog_html = dialog.content.decode()
        assert "举报这条留言" in dialog_html
        assert f'hx-post="{report_url}"' in dialog_html
        assert f'data-media-upload-url="{upload_url}"' in dialog_html
        assert dialog_html.count('data-media-picker="report-evidence"') == 3
        assert all(value in dialog_html for value in ReportReason.values)
        assert str(reporter.id) not in dialog_html
        assert reporter.email not in dialog_html

        invalid = reporter_client.post(
            report_url,
            {"reason": "", "description": "说" * 201},
            HTTP_HX_REQUEST="true",
        )
        assert invalid.status_code == 422
        invalid_html = invalid.content.decode()
        assert "请选择举报理由" in invalid_html
        assert "补充说明不能超过 200 字" in invalid_html
        assert "说" * 201 in invalid_html
        assert 'data-error-focus tabindex="-1"' in invalid_html

        upload = reporter_client.post(
            upload_url,
            {
                "file": SimpleUploadedFile(
                    "evidence.png",
                    _png(),
                    content_type="image/png",
                )
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        assert upload.status_code == 201
        evidence_ref = upload.context["upload"].evidence_ref
        asset_id = upload.context["upload"].asset_id

        created = reporter_client.post(
            report_url,
            {
                "reason": ReportReason.PRIVACY,
                "description": "评论公开了私人联系方式",
                "evidence_ref_1": evidence_ref,
            },
            HTTP_HX_REQUEST="true",
        )
        assert created.status_code == 201
        created_html = created.content.decode()
        assert "举报已提交" in created_html
        assert str(reporter.id) not in created_html
        assert reporter.email not in created_html
        report = Report.objects.get()
        assert report.reporter_id == reporter.id
        assert report.reported_author_id == target_author.id
        assert report.reason == ReportReason.PRIVACY
        binding = apps.get_model("media", "MediaBinding").objects.get(
            target_type="report",
            target_id=report.id,
            asset_id=asset_id,
        )
        assert binding.slot == "evidence-1"
        assert binding.asset.purpose == "EVIDENCE"
        assert binding.asset.owner_id == reporter.id

        assert _authorize(reporter_client, asset_id).status_code == 200
        assert _authorize(admin_client, asset_id).status_code == 200
        assert _authorize(target_client, asset_id).status_code == 404
        assert _authorize(other_client, asset_id).status_code == 404

        duplicate = reporter_client.post(
            report_url,
            {"reason": ReportReason.OTHER, "description": "再次提交"},
            HTTP_HX_REQUEST="true",
        )
        assert duplicate.status_code == 409
        assert "已经举报过" in duplicate.content.decode()
        assert Report.objects.count() == 1

        target_page = target_client.get(page_url).content.decode()
        assert str(reporter.id) not in target_page
        assert reporter.email not in target_page
        assert "评论公开了私人联系方式" not in target_page
        assert apps.get_model("core", "OutboxEvent").objects.count() == 0
        assert apps.get_model("operations", "AuditEntry").objects.count() == 0
