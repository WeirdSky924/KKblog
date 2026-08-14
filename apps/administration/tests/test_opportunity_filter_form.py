from uuid import uuid4

from django.http import QueryDict

from apps.administration.forms.opportunities import OpportunityFilterForm


def test_admin_opportunity_filters_accept_repeated_values() -> None:
    first_source = uuid4()
    second_source = uuid4()
    city = uuid4()
    data = QueryDict(mutable=True)
    data.setlist("verification_status", ("CONFIRMED", "PENDING"))
    data.setlist("publication_state", ("PUBLISHED", "WITHDRAWN"))
    data.setlist("source_id", (str(first_source), str(second_source)))
    data.setlist("recruitment_type", ("CAMPUS", "INTERNSHIP"))
    data.setlist("origin", ("CRAWLER", "MANUAL"))
    data.setlist("city_ids", (str(city),))
    data.setlist("list_missing", ("true", "false"))

    form = OpportunityFilterForm(
        data,
        source_choices=(
            (str(first_source), "来源一"),
            (str(second_source), "来源二"),
        ),
        filter_choices={"city_ids": ((city, "杭州"),)},
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["verification_status"] == ["CONFIRMED", "PENDING"]
    assert form.cleaned_data["publication_state"] == ["PUBLISHED", "WITHDRAWN"]
    assert form.cleaned_data["source_id"] == [str(first_source), str(second_source)]
    assert form.cleaned_data["recruitment_type"] == ["CAMPUS", "INTERNSHIP"]
    assert form.cleaned_data["origin"] == ["CRAWLER", "MANUAL"]
    assert form.cleaned_data["city_ids"] == [str(city)]
    assert form.cleaned_data["list_missing"] == ["true", "false"]
