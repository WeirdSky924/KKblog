from django import forms


class HomePageForm(forms.Form):
    page = forms.IntegerField(
        required=False,
        min_value=1,
        error_messages={"invalid": "请输入有效页码。", "min_value": "页码不能小于 1。"},
    )
    per_page = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=20,
        choices=((10, "10"), (20, "20"), (50, "50")),
        error_messages={"invalid_choice": "每页数量只能选择 10、20 或 50。"},
    )

    def clean_page(self) -> int:
        return self.cleaned_data.get("page") or 1
