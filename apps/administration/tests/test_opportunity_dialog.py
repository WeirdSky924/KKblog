from types import SimpleNamespace

from django.template.loader import render_to_string

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
