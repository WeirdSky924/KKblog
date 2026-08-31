from uuid import UUID

from django import forms

from .public import (
    PAGE_SIZES,
    RECRUITMENT_TYPE_CHOICES,
    SOURCE_TYPE_CHOICES,
    VERIFICATION_STATUS_CHOICES,
)


class OpportunityPageForm(forms.Form):
    view = forms.ChoiceField(
        required=False,
        choices=(("jobs", "岗位"), ("sources", "官方来源"), ("bookmarks", "我的收藏")),
    )
    job_q = forms.CharField(required=False, max_length=100, strip=True)
    source_q = forms.CharField(required=False, max_length=100, strip=True)
    job_page = forms.IntegerField(required=False, min_value=1)
    source_page = forms.IntegerField(required=False, min_value=1)
    per_page = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=20,
        choices=tuple((value, str(value)) for value in PAGE_SIZES),
    )
    cities = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple
    )
    statuses = forms.MultipleChoiceField(
        required=False,
        choices=VERIFICATION_STATUS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    companies = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple
    )
    recruitment_types = forms.MultipleChoiceField(
        required=False,
        choices=RECRUITMENT_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    categories = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple
    )
    cohorts = forms.MultipleChoiceField(
        required=False, widget=forms.CheckboxSelectMultiple
    )
    bookmarked = forms.BooleanField(required=False)
    source_types = forms.MultipleChoiceField(
        required=False,
        choices=SOURCE_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, filters, authenticated=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.authenticated = authenticated
        for name, options in (
            ("cities", filters.cities),
            ("categories", filters.categories),
            ("cohorts", filters.cohorts),
        ):
            self.fields[name].choices = tuple(
                (str(item.option_id), item.label) for item in options
            )
        self.fields["companies"].choices = tuple(
            (str(item.source_id), item.label) for item in filters.sources
        )

    def clean_view(self):
        return self.cleaned_data.get("view") or "jobs"

    def clean_job_page(self):
        return self.cleaned_data.get("job_page") or 1

    def clean_source_page(self):
        return self.cleaned_data.get("source_page") or 1

    def clean_bookmarked(self):
        return (
            bool(self.cleaned_data.get("bookmarked")) if self.authenticated else False
        )

    def _uuids(self, name):
        return tuple(
            UUID(value) for value in dict.fromkeys(self.cleaned_data.get(name) or ())
        )

    def clean_cities(self):
        return self._uuids("cities")

    def clean_categories(self):
        return self._uuids("categories")

    def clean_cohorts(self):
        return self._uuids("cohorts")

    def clean_companies(self):
        return self._uuids("companies")


class OpportunityBookmarkForm(forms.Form):
    opportunity_id = forms.UUIDField()
    selected = forms.ChoiceField(choices=(("true", "收藏"), ("false", "取消收藏")))
    return_query = forms.CharField(required=False, max_length=2000)

    def clean_selected(self):
        return self.cleaned_data["selected"] == "true"


__all__ = ["OpportunityBookmarkForm", "OpportunityPageForm"]
