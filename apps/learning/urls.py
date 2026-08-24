from django.urls import path

from apps.learning.presentation.account import documents
from apps.learning.presentation.quiz import (
    quiz_assess,
    quiz_attempt,
    quiz_index,
    quiz_save_response,
    quiz_submit,
)
from apps.learning.presentation.records import (
    record_detail,
    records,
    records_export,
    wrong_book,
)

app_name = "learning"

urlpatterns = [
    path("", documents, name="documents"),
    path("quiz/", quiz_index, name="quiz-index"),
    path("quiz/wrong/", wrong_book, name="wrong-book"),
    path("quiz/records/", records, name="records"),
    path("quiz/records/export.csv", records_export, name="records-export"),
    path("quiz/records/<uuid:attempt_id>/", record_detail, name="record-detail"),
    path("quiz/attempt/<uuid:attempt_id>/", quiz_attempt, name="quiz-attempt"),
    path(
        "quiz/attempt/<uuid:attempt_id>/submit/",
        quiz_submit,
        name="quiz-submit",
    ),
    path(
        "quiz/response/<uuid:response_id>/save/",
        quiz_save_response,
        name="quiz-save-response",
    ),
    path(
        "quiz/response/<uuid:response_id>/assess/",
        quiz_assess,
        name="quiz-assess",
    ),
]
