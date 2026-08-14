import json
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.opportunities.models import (
    Opportunity,
    OpportunitySource,
    OpportunitySourceHost,
)


def _source_payload(*, identity=None, company_name="示例企业"):
    return {
        "schema": "kaj.opportunity-source-config.v1",
        "sources": [
            {
                "id": str(identity or uuid4()),
                "company_name": company_name,
                "source_type": "CAMPUS",
                "official_url": "https://jobs.example.com/campus",
                "note": "官方校园招聘",
                "adapter_key": "manual-unsupported-v1",
                "adapter_config": {},
                "enabled": True,
                "respect_robots_txt": True,
                "request_interval_seconds": 2,
                "max_pages": 20,
                "max_opportunities": 1000,
                "max_duration_seconds": 300,
                "allowed_hosts": ["jobs.example.com"],
            }
        ],
    }


@pytest.mark.django_db
def test_export_contains_only_source_configuration(tmp_path):
    source = OpportunitySource.objects.create(
        company_name="示例企业",
        normalized_company_name="示例企业",
        source_type=OpportunitySource.SourceType.CAMPUS,
        official_url="https://jobs.example.com/campus",
        adapter_key="manual-unsupported-v1",
        enabled=True,
        publicly_visible=True,
        check_state=OpportunitySource.CheckState.HEALTHY,
        consecutive_failures=2,
        last_success_at=timezone.now(),
        last_checked_at=timezone.now(),
        row_version=9,
    )
    OpportunitySourceHost.objects.create(source=source, hostname="jobs.example.com")
    output_path = tmp_path / "sources.json"

    call_command("export_opportunity_sources", output=str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    exported = payload["sources"][0]
    assert payload["schema"] == "kaj.opportunity-source-config.v1"
    assert exported["id"] == str(source.id)
    assert exported["allowed_hosts"] == ["jobs.example.com"]
    assert "publicly_visible" not in exported
    assert "check_state" not in exported
    assert "last_success_at" not in exported
    assert "row_version" not in exported
    assert set(payload) == {"schema", "sources"}


@pytest.mark.django_db
def test_import_is_dry_run_by_default_and_resets_runtime_state_on_apply(tmp_path):
    identity = uuid4()
    input_path = tmp_path / "sources.json"
    input_path.write_text(
        json.dumps(_source_payload(identity=identity), ensure_ascii=False),
        encoding="utf-8",
    )
    stdout = StringIO()

    call_command("import_opportunity_sources", input=str(input_path), stdout=stdout)

    assert "dry_run=true" in stdout.getvalue()
    assert not OpportunitySource.objects.exists()

    call_command("import_opportunity_sources", input=str(input_path), apply=True)
    source = OpportunitySource.objects.get(pk=identity)
    assert source.company_name == "示例企业"
    assert source.enabled is True
    assert source.publicly_visible is False
    assert source.check_state == OpportunitySource.CheckState.NEVER
    assert source.consecutive_failures == 0
    assert source.last_success_at is None
    assert source.last_checked_at is None
    assert source.last_error_code == ""
    assert source.row_version == 1
    assert list(source.allowed_hosts.values_list("hostname", flat=True)) == [
        "jobs.example.com"
    ]

    source.publicly_visible = True
    source.check_state = OpportunitySource.CheckState.HEALTHY
    source.consecutive_failures = 3
    source.last_success_at = timezone.now()
    source.row_version = 8
    source.save()
    input_path.write_text(
        json.dumps(
            _source_payload(identity=identity, company_name="更新后的企业"),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    call_command("import_opportunity_sources", input=str(input_path), apply=True)

    source.refresh_from_db()
    assert OpportunitySource.objects.count() == 1
    assert source.company_name == "更新后的企业"
    assert source.publicly_visible is False
    assert source.check_state == OpportunitySource.CheckState.NEVER
    assert source.consecutive_failures == 0
    assert source.last_success_at is None
    assert source.row_version == 1


@pytest.mark.django_db
def test_import_rejects_crawler_fields_unknown_adapters_and_sensitive_config(tmp_path):
    input_path = tmp_path / "sources.json"
    payload = _source_payload()
    payload["sources"][0]["opportunities"] = []
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CommandError, match="source-only schema"):
        call_command("import_opportunity_sources", input=str(input_path))

    payload = _source_payload()
    payload["sources"][0]["adapter_key"] = "missing-adapter-v1"
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CommandError, match="adapter is not registered"):
        call_command("import_opportunity_sources", input=str(input_path))

    payload = _source_payload()
    payload["sources"][0]["adapter_config"] = {"api_token": "not-exportable"}
    input_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CommandError, match="unsafe key"):
        call_command("import_opportunity_sources", input=str(input_path))


@pytest.mark.django_db
def test_versioned_production_manifest_imports_sources_without_job_data():
    manifest = Path("config/opportunity_sources.v1.json")

    call_command("import_opportunity_sources", input=str(manifest), apply=True)

    assert OpportunitySource.objects.count() == 41
    assert OpportunitySourceHost.objects.count() == 48
    assert Opportunity.objects.count() == 0
    assert not OpportunitySource.objects.filter(publicly_visible=True).exists()
    assert not OpportunitySource.objects.exclude(
        check_state=OpportunitySource.CheckState.NEVER,
        consecutive_failures=0,
        last_success_at=None,
        last_checked_at=None,
        last_error_code="",
        row_version=1,
    ).exists()
