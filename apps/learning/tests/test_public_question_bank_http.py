import pytest
from django.apps import apps
from django.urls import reverse

from apps.learning.public import set_question_bank_visibility

from .test_account_documents_http import _authenticate
from .test_public_question_bank_queries import _fixture_banks

pytestmark = pytest.mark.django_db(transaction=True)


def test_public_list_is_identical_for_visitor_and_logged_in_user(
    client,
    isolated_media_root,
) -> None:
    first, second, third = _fixture_banks(isolated_media_root)
    url = reverse("question_banks:index")

    visitor = client.get(url)
    visitor_html = visitor.content.decode("utf-8")
    assert visitor.status_code == 200
    assert "知识题库" in visitor_html
    assert "Python 后端基础" in visitor_html
    assert "前端交互实践" in visitor_html
    assert "Python 工程进阶" in visitor_html
    assert "Python作者" in visitor_html

    _authenticate(client, first.series.owner)
    logged_in = client.get(url)
    logged_in_html = logged_in.content.decode("utf-8")
    for bank in (first, second, third):
        assert str(bank.id) in visitor_html
        assert str(bank.id) in logged_in_html


def test_public_html_filters_and_fuzzy_search_use_shared_query(
    client,
    isolated_media_root,
) -> None:
    first, second, third = _fixture_banks(isolated_media_root)
    tag_model = apps.get_model("learning", "QuestionBankTag")
    python_tag = tag_model.objects.get(normalized_name="python")
    url = reverse("question_banks:index")

    filtered = client.get(
        url,
        {
            "tags": [str(python_tag.id)],
            "question_types": ["TRUE_FALSE"],
            "min_questions": "2",
            "sort": "question_count_desc",
        },
    )
    filtered_html = filtered.content.decode("utf-8")
    assert filtered.status_code == 200
    assert "Python 工程进阶" in filtered_html
    assert "Python 后端基础" not in filtered_html
    assert "前端交互实践" not in filtered_html

    fuzzy = client.get(url, {"q": "Pythn", "sort": "latest"})
    fuzzy_html = fuzzy.content.decode("utf-8")
    assert fuzzy.status_code == 200
    assert "Python 后端基础" in fuzzy_html
    assert "Python 工程进阶" in fuzzy_html
    assert "前端交互实践" not in fuzzy_html
    assert str(first.id) in fuzzy_html and str(third.id) in fuzzy_html
    assert str(second.id) not in fuzzy_html


def test_public_detail_shows_answers_and_hidden_bank_returns_404(
    client,
    isolated_media_root,
) -> None:
    first, _, third = _fixture_banks(isolated_media_root)
    detail_url = reverse("question_banks:detail", kwargs={"bank_id": first.id})

    detail = client.get(detail_url)
    html = detail.content.decode("utf-8")
    assert detail.status_code == 200
    assert "Python 后端基础" in html
    assert "答案 A" in html and "正确答案" in html
    assert "单选解析" in html
    assert "source_document" not in html
    assert "Prompt" not in html and "Endpoint" not in html

    set_question_bank_visibility(
        actor_id=third.series.owner_id,
        bank_id=third.id,
        expected_version=third.row_version,
        target="OWNER_HIDDEN",
    )
    hidden_url = reverse("question_banks:detail", kwargs={"bank_id": third.id})
    assert client.get(hidden_url).status_code == 404


def test_invalid_public_filter_returns_actionable_422(
    client,
    isolated_media_root,
) -> None:
    _fixture_banks(isolated_media_root)
    response = client.get(
        reverse("question_banks:index"),
        {"min_questions": "10", "max_questions": "2", "sort": "latest"},
    )
    html = response.content.decode("utf-8")
    assert response.status_code == 422
    assert "最多题数不能小于最少题数" in html
    assert "题库列表" in html
    invalid_page = client.get(
        reverse("question_banks:index"),
        {"page": "invalid", "sort": "latest"},
    )
    assert invalid_page.status_code == 422
