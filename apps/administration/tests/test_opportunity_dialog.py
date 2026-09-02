import json
from importlib import import_module
from types import SimpleNamespace

from django.http import JsonResponse
from django.template.loader import render_to_string
from django.test import RequestFactory

from apps.administration.forms.opportunities import (
    OpportunityPageForm,
    SourceFilterForm,
    SourceForm,
)


def test_source_dialog_uses_fixed_header_and_shared_switch() -> None:
    body = render_to_string(
        "administration/opportunities.html",
        {
            "active_tab": "sources",
            "dialog_kind": "source-create",
            "dialog_form": SourceForm(adapter_choices=(("test", "测试"),)),
            "source_filter_form": SourceFilterForm(),
            "source_page": SimpleNamespace(items=(), total=0, pages=1),
            "pagination_query": "tab=sources",
        },
    )

    assert 'class="opportunity-admin-dialog__header"' in body
    assert 'class="opportunity-admin-dialog__body"' in body
    assert 'class="switch-control" for="id_respect_robots_txt"' in body
    assert 'class="switch-control__track"' in body
    assert 'class="switch-control__thumb"' in body


def test_run_history_renders_source_rows_and_change_dialog() -> None:
    run_item = SimpleNamespace(
        source_run_id=17,
        run_id="01K2EXAMPLE",
        company_name="示例科技",
        source_type_label="校园招聘",
        official_url="https://jobs.example.com/campus",
        trigger_label="手动单来源",
        run_kind_label="单个来源",
        state="SUCCEEDED",
        state_label="成功",
        created_opportunities=1,
        changed_opportunities=1,
        missing_opportunities=0,
        failed_opportunity_checks=0,
        safe_error_code="",
        started_at=None,
        completed_at=None,
        can_cancel=False,
    )
    change = SimpleNamespace(
        kind="CREATED",
        kind_label="新增",
        opportunity_id="job-1",
        title="后端开发工程师",
        target_url="https://jobs.example.com/campus/jobs/1",
        recruitment_type_label="校园招聘",
        location_text="杭州",
    )
    detail = SimpleNamespace(
        item=run_item,
        changes=(change,),
        change_total=1,
        changes_truncated=False,
        snapshot_observed_at=None,
        detail_note="",
    )

    body = render_to_string(
        "administration/opportunities.html",
        {
            "active_tab": "runs",
            "dialog_kind": "run-detail",
            "run_detail": detail,
            "run_page": SimpleNamespace(items=(run_item,), total=1, pages=1),
            "page_form": OpportunityPageForm(),
            "pagination_query": "tab=runs",
            "run_detail_return_url": "/admin/opportunities/?tab=runs",
        },
    )

    assert 'id="run-detail-17"' in body
    assert 'aria-controls="opportunity-run-detail-dialog"' in body
    assert 'id="opportunity-run-detail-dialog"' in body
    assert '<form method="dialog">' in body
    assert "示例科技" in body
    assert "后端开发工程师" in body


def test_failed_run_history_exposes_source_retry_only_for_failed_row() -> None:
    failed_item = SimpleNamespace(
        source_run_id=18,
        run_id="01K2FAILED",
        source_id="4e4398bb-cfc2-47bb-b7fb-f78ddd2a775b",
        company_name="失败来源",
        source_type_label="校园招聘",
        official_url="https://jobs.example.com/failed",
        trigger_label="定时检查",
        run_kind_label="全部来源",
        state="FAILED",
        state_label="失败",
        created_opportunities=0,
        changed_opportunities=0,
        missing_opportunities=0,
        failed_opportunity_checks=0,
        started_at=None,
        completed_at=None,
        can_cancel=False,
    )
    succeeded_item = SimpleNamespace(
        **{
            **failed_item.__dict__,
            "source_run_id": 19,
            "source_id": "c10e5192-21ac-446f-a719-9b92cd925ee9",
            "company_name": "成功来源",
            "state": "SUCCEEDED",
            "state_label": "成功",
        }
    )

    body = render_to_string(
        "administration/opportunities.html",
        {
            "active_tab": "runs",
            "run_page": SimpleNamespace(
                items=(failed_item, succeeded_item), total=2, pages=1
            ),
            "page_form": OpportunityPageForm(),
            "pagination_query": "tab=runs",
            "list_query": "tab=runs",
        },
    )

    assert body.count('value="retry_source_check"') == 1
    assert 'value="4e4398bb-cfc2-47bb-b7fb-f78ddd2a775b"' in body
    assert 'aria-label="重新检查 失败来源"' in body
    assert 'aria-label="重新检查 成功来源"' not in body


def test_failed_run_retry_reuses_source_check_and_returns_to_history(
    monkeypatch,
) -> None:
    view = import_module("apps.administration.views.opportunities")
    source_id = "4e4398bb-cfc2-47bb-b7fb-f78ddd2a775b"
    captured = {}

    def request_source_check(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(view, "request_source_check", request_source_check)
    monkeypatch.setattr(view, "_throttled", lambda request, action: False)
    request = RequestFactory().post(
        "/admin/opportunities/?tab=runs",
        {"action": "retry_source_check", "source_id": source_id},
    )
    request.account_id = "admin-account"
    request.trace_code = "trace-code"
    request.client_ip = "127.0.0.1"

    response = view._post(request)

    assert str(captured["source_id"]) == source_id
    assert captured["actor_id"] == "admin-account"
    assert callable(captured["dispatcher"])
    assert response.status_code == 302
    assert response.url.endswith("?tab=runs&saved=check")


def test_lazy_opportunity_filter_options_returns_bounded_json(monkeypatch) -> None:
    view = import_module("apps.administration.views.opportunities")
    captured = {}

    def option_page(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            items=(SimpleNamespace(value="option-1", label="后端开发"),),
            page=2,
            pages=4,
            total=120,
            has_previous=True,
            has_next=True,
        )

    monkeypatch.setattr(view, "admin_filter_option_page", option_page)
    request = RequestFactory().get(
        "/admin/opportunities/filter-options/?kind=CATEGORY&q=后端&page=2&selected=option-1"
    )
    request.account_id = "admin-account"

    response = view.opportunity_filter_options(request)

    assert isinstance(response, JsonResponse)
    assert response.status_code == 200
    assert json.loads(response.content) == {
        "items": [{"value": "option-1", "label": "后端开发"}],
        "page": 2,
        "pages": 4,
        "total": 120,
        "has_previous": True,
        "has_next": True,
    }
    assert captured == {
        "actor_id": "admin-account",
        "kind": "CATEGORY",
        "query": "后端",
        "page": 2,
        "page_size": 40,
        "selected_ids": ["option-1"],
    }
