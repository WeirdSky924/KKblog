from django import forms
from django.http import QueryDict
from django.template.loader import render_to_string


class _PickerForm(forms.Form):
    cities = forms.MultipleChoiceField(
        required=False,
        choices=(("hangzhou", "杭州"), ("shanghai", "上海")),
        widget=forms.CheckboxSelectMultiple,
    )


def test_filter_picker_renders_searchable_checkbox_dialog() -> None:
    data = QueryDict(mutable=True)
    data.setlist("cities", ("hangzhou", "shanghai"))
    field = _PickerForm(data)["cities"]

    body = render_to_string(
        "components/forms/opportunity_filter_picker.html",
        {
            "field": field,
            "title": "城市",
            "picker_id": "test-cities",
            "auto_submit": True,
        },
    )

    assert "data-opportunity-filter-picker" in body
    assert "data-opportunity-filter-search" in body
    assert "data-opportunity-filter-option" in body
    assert 'name="cities"' in body
    assert body.count('type="checkbox"') == 2
    assert body.count("checked") == 2
    assert "搜索城市" in body
