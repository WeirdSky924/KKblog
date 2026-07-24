from django.urls import path

from .views import confirm_report, create_comment_report, upload_report_evidence

app_name = "moderation"

urlpatterns = [
    path(
        "comments/<str:comment_id>/report/confirm/",
        confirm_report,
        name="report-confirm",
    ),
    path(
        "comments/<str:comment_id>/report/",
        create_comment_report,
        name="report-create",
    ),
    path(
        "comments/<str:comment_id>/report/evidence/",
        upload_report_evidence,
        name="report-evidence-upload",
    ),
]
