from django.urls import path

from apps.learning.presentation.api import question_bank_detail, question_bank_list

app_name = "question_banks_api"

urlpatterns = [
    path("", question_bank_list, name="index"),
    path("<uuid:bank_id>/", question_bank_detail, name="detail"),
]
