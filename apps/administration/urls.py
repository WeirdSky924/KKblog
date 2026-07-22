from django.urls import path

from apps.administration.views.audit import audit_log
from apps.administration.views.invites import invites
from apps.administration.views.ip_blocks import ip_blocks

app_name = "admin"

urlpatterns = [
    path("audit/", audit_log, name="audit"),
    path("invites/", invites, name="invites"),
    path("ip-blocks/", ip_blocks, name="ip-blocks"),
]
