from dataclasses import dataclass
from uuid import UUID

DEFAULT_VERIFICATION_STATUSES = ("CONFIRMED", "PENDING")


@dataclass(frozen=True, slots=True)
class OpportunityDefaultFilters:
    city_ids: tuple[UUID, ...]
    verification_statuses: tuple[str, ...]
    source_ids: tuple[UUID, ...]
    recruitment_types: tuple[str, ...]
    category_ids: tuple[UUID, ...]
    cohort_ids: tuple[UUID, ...]


def project_default_filters(
    selections, *, settings_exists: bool
) -> OpportunityDefaultFilters:
    buckets = {
        "CITY": [],
        "STATUS": [],
        "COMPANY": [],
        "RECRUITMENT_TYPE": [],
        "CATEGORY": [],
        "COHORT": [],
    }
    for selection in selections:
        if selection.kind in {"CITY", "CATEGORY", "COHORT"}:
            buckets[selection.kind].append(selection.option_id)
        elif selection.kind == "COMPANY":
            buckets[selection.kind].append(selection.source_id)
        elif selection.kind in {"STATUS", "RECRUITMENT_TYPE"}:
            buckets[selection.kind].append(selection.value)
    statuses = tuple(buckets["STATUS"])
    if not settings_exists:
        statuses = DEFAULT_VERIFICATION_STATUSES
    return OpportunityDefaultFilters(
        tuple(buckets["CITY"]),
        statuses,
        tuple(buckets["COMPANY"]),
        tuple(buckets["RECRUITMENT_TYPE"]),
        tuple(buckets["CATEGORY"]),
        tuple(buckets["COHORT"]),
    )


__all__ = [
    "DEFAULT_VERIFICATION_STATUSES",
    "OpportunityDefaultFilters",
    "project_default_filters",
]
