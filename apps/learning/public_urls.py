from django.urls import path

from apps.learning.presentation.public_banks import (
    question_bank_detail,
    question_bank_list,
)

app_name = "question_banks"

urlpatterns = [
    path("", question_bank_list, name="index"),
    path("<uuid:bank_id>/", question_bank_detail, name="detail"),
]
