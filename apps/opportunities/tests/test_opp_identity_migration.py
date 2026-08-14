from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from apps.opportunities.models import Opportunity

pytestmark = pytest.mark.django_db(transaction=True)

OLD_SCHEMA = ("opportunities", "0002_opportunity_check_runtime")
NEW_SCHEMA = ("opportunities", "0003_opportunity_composite_identity")


def test_composite_identity_migration_backfills_normalized_title() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate([OLD_SCHEMA])
    old_apps = executor.loader.project_state([OLD_SCHEMA]).apps
    old_source = old_apps.get_model("opportunities", "OpportunitySource")
    old_opportunity = old_apps.get_model("opportunities", "Opportunity")
    source = old_source.objects.create(
        company_name="迁移示例科技",
        normalized_company_name="迁移示例科技",
        source_type="CAMPUS",
        official_url=f"https://jobs.example.com/{uuid4()}",
        adapter_key="example-v1",
    )
    opportunity_id = uuid4()
    old_opportunity.objects.create(
        id=opportunity_id,
        source=source,
        title="  ＡI   实习生  ",
        target_url="https://jobs.example.com/campus/jobs",
        normalized_target_url="https://jobs.example.com/campus/jobs",
        recruitment_type="INTERNSHIP",
        plan="2027 届实习招聘",
        location_text="杭州",
        public_evidence="来自企业公开招聘列表。",
        verification_status="PENDING",
        publication_state="PUBLISHED",
        origin="IMPORT",
    )

    try:
        MigrationExecutor(connection).migrate([NEW_SCHEMA])
        row = Opportunity.objects.get(pk=opportunity_id)
        assert row.normalized_identity_title == "ai 实习生"
    finally:
        MigrationExecutor(connection).migrate([NEW_SCHEMA])
