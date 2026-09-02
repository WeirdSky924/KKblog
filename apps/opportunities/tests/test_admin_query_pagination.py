from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from apps.opportunities.queries import administration


class _LazyReviewRows:
    def __init__(self, rows, *, total):
        self._rows = tuple(rows)
        self._total = total
        self.slices = []

    def order_by(self, *fields):
        assert fields == ("created_at", "id")
        return self

    def filter(self, **conditions):
        assert conditions == {"state": "OPEN"}
        return self

    def count(self):
        return self._total

    def __getitem__(self, key):
        assert isinstance(key, slice)
        self.slices.append(key)
        return self._rows[key]

    def __iter__(self):
        raise AssertionError("review rows must be sliced before iteration")


class _ReviewManager:
    def __init__(self, rows):
        self.rows = rows

    def prefetch_related(self, *relations):
        assert relations == ("opportunity__source",)
        return self.rows


class _OpportunityRows:
    def __init__(self):
        self.filters = []
        self.distinct_called = False

    def prefetch_related(self, *relations):
        return self

    def order_by(self, *fields):
        return self

    def filter(self, **conditions):
        self.filters.append(conditions)
        return self

    def distinct(self):
        self.distinct_called = True
        return self


class _OpportunityManager:
    def __init__(self, rows):
        self.rows = rows

    def select_related(self, *relations):
        return self.rows


def _review_row(position):
    opportunity_id = uuid4()
    return SimpleNamespace(
        id=f"review-{position:04d}",
        opportunity_id=opportunity_id,
        opportunity=SimpleNamespace(
            id=opportunity_id,
            title=f"岗位 {position}",
            source=SimpleNamespace(company_name="示例企业"),
        ),
        kind="NEW",
        state="OPEN",
        field_changes={},
        created_at=datetime(2026, 8, 14, position % 24, tzinfo=UTC),
    )


def test_admin_review_queue_slices_database_rows_before_mapping(monkeypatch) -> None:
    rows = _LazyReviewRows((_review_row(index) for index in range(30)), total=2000)
    model = SimpleNamespace(objects=_ReviewManager(rows))
    monkeypatch.setattr(administration, "OpportunityReviewItem", model)
    monkeypatch.setattr(administration, "_administrator", lambda actor_id: None)

    page = administration.admin_review_queue(
        actor_id=uuid4(),
        page=2,
        page_size=10,
    )

    assert rows.slices == [slice(10, 20)]
    assert page.total == 2000
    assert page.page == 2
    assert page.pages == 200
    assert len(page.items) == 10
    assert page.items[0].review_id == "review-0010"


def test_admin_opportunity_query_uses_in_filters_for_multi_selects(monkeypatch) -> None:
    rows = _OpportunityRows()
    model = SimpleNamespace(objects=_OpportunityManager(rows))
    monkeypatch.setattr(administration, "Opportunity", model)
    monkeypatch.setattr(administration, "_administrator", lambda actor_id: None)
    monkeypatch.setattr(administration, "_page", lambda rows, **kwargs: rows)

    result = administration.admin_opportunities(
        actor_id=uuid4(),
        verification_status=("CONFIRMED", "PENDING"),
        publication_state=("PUBLISHED", "WITHDRAWN"),
        source_id=("source-1", "source-2"),
        recruitment_type=("CAMPUS", "INTERNSHIP"),
        origin=("CRAWLER", "MANUAL"),
        list_missing=("true", "false"),
    )

    assert result is rows
    assert {key for item in rows.filters for key in item} == {
        "verification_status__in",
        "publication_state__in",
        "source_id__in",
        "recruitment_type__in",
        "origin__in",
        "list_missing__in",
    }
    assert rows.distinct_called is False


def test_admin_opportunity_query_distincts_only_for_assignment_filters(
    monkeypatch,
) -> None:
    rows = _OpportunityRows()
    model = SimpleNamespace(objects=_OpportunityManager(rows))
    monkeypatch.setattr(administration, "Opportunity", model)
    monkeypatch.setattr(administration, "_administrator", lambda actor_id: None)
    monkeypatch.setattr(administration, "_page", lambda rows, **kwargs: rows)

    administration.admin_opportunities(
        actor_id=uuid4(),
        category_ids=("category-1",),
    )

    assert rows.distinct_called is True
