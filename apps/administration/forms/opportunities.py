from django import forms

from apps.opportunities.public import (
    OPPORTUNITY_ORIGIN_CHOICES,
    PUBLICATION_STATE_CHOICES,
    RECRUITMENT_TYPE_CHOICES,
    SOURCE_CHECK_STATE_CHOICES,
    SOURCE_TYPE_CHOICES,
    VERIFICATION_STATUS_CHOICES,
)

PAGE_SIZE_CHOICES = ((10, "10"), (20, "20"), (50, "50"))


class OpportunityPageForm(forms.Form):
    page = forms.IntegerField(required=False, min_value=1, initial=1)
    per_page = forms.TypedChoiceField(
        required=False,
        choices=PAGE_SIZE_CHOICES,
        coerce=int,
        initial=20,
    )


class SourceFilterForm(OpportunityPageForm):
    q = forms.CharField(required=False, max_length=120, label="企业或 URL")
    enabled = forms.ChoiceField(
        required=False,
        label="启用状态",
        choices=(("", "全部"), ("true", "已启用"), ("false", "已停用")),
    )
    source_type = forms.ChoiceField(
        required=False,
        label="来源类型",
        choices=(("", "全部"), *SOURCE_TYPE_CHOICES),
    )
    check_state = forms.ChoiceField(
        required=False,
        label="检查状态",
        choices=(("", "全部"), *SOURCE_CHECK_STATE_CHOICES),
    )


class OpportunityFilterForm(OpportunityPageForm):
    q = forms.CharField(required=False, max_length=120, label="岗位或企业")
    verification_status = forms.MultipleChoiceField(
        required=False,
        label="核实状态",
        choices=VERIFICATION_STATUS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    publication_state = forms.MultipleChoiceField(
        required=False,
        label="上下架",
        choices=PUBLICATION_STATE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    source_id = forms.MultipleChoiceField(
        required=False,
        label="官方来源",
        widget=forms.CheckboxSelectMultiple,
    )
    recruitment_type = forms.MultipleChoiceField(
        required=False,
        label="招聘类型",
        choices=RECRUITMENT_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    origin = forms.MultipleChoiceField(
        required=False,
        label="创建来源",
        choices=OPPORTUNITY_ORIGIN_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    category_ids = forms.MultipleChoiceField(
        required=False,
        label="岗位类别",
        widget=forms.CheckboxSelectMultiple,
    )
    city_ids = forms.MultipleChoiceField(
        required=False,
        label="城市",
        widget=forms.CheckboxSelectMultiple,
    )
    cohort_ids = forms.MultipleChoiceField(
        required=False,
        label="届别",
        widget=forms.CheckboxSelectMultiple,
    )
    list_missing = forms.MultipleChoiceField(
        required=False,
        label="来源列表状态",
        choices=(("true", "列表缺失"), ("false", "当前存在")),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, source_choices=(), filter_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_id"].choices = source_choices
        for name in ("category_ids", "city_ids", "cohort_ids"):
            self.fields[name].choices = tuple(
                (str(identity), label)
                for identity, label in (filter_choices or {}).get(name, ())
            )


class SourceForm(forms.Form):
    source_id = forms.UUIDField(required=False, widget=forms.HiddenInput)
    company_name = forms.CharField(max_length=120, label="企业名称")
    source_type = forms.ChoiceField(choices=SOURCE_TYPE_CHOICES, label="来源类型")
    official_url = forms.URLField(
        max_length=2048, label="官方招聘入口", assume_scheme="https"
    )
    note = forms.CharField(
        required=False,
        max_length=500,
        label="来源备注",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    adapter_key = forms.ChoiceField(label="内置适配器")
    allowed_hosts = forms.CharField(
        label="允许域名",
        help_text="每行一个域名，必须包含官方入口域名。",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    respect_robots_txt = forms.BooleanField(
        required=False, initial=True, label="遵守 robots.txt"
    )
    request_interval_seconds = forms.IntegerField(
        min_value=2, max_value=3600, initial=2, label="同域请求间隔（秒）"
    )
    max_pages = forms.IntegerField(
        min_value=1, max_value=100, initial=50, label="单次最大页数"
    )
    max_opportunities = forms.IntegerField(
        min_value=1, max_value=5000, initial=5000, label="单次最大岗位数"
    )
    max_duration_seconds = forms.IntegerField(
        min_value=1, max_value=600, initial=600, label="单次最长时间（秒）"
    )

    def __init__(self, *args, adapter_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["adapter_key"].choices = adapter_choices

    def clean_allowed_hosts(self):
        return tuple(
            line.strip()
            for line in self.cleaned_data["allowed_hosts"].splitlines()
            if line.strip()
        )


class OpportunityCreateForm(forms.Form):
    source_id = forms.ChoiceField(label="官方来源")
    title = forms.CharField(max_length=200, label="岗位标题")
    target_url = forms.URLField(
        max_length=2048, label="岗位地址", assume_scheme="https"
    )
    recruitment_type = forms.ChoiceField(
        choices=RECRUITMENT_TYPE_CHOICES, label="招聘类型"
    )
    plan = forms.CharField(max_length=200, label="招聘计划")
    location_text = forms.CharField(max_length=300, label="工作地点")
    public_evidence = forms.CharField(
        max_length=1200,
        label="公开证据",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    category_ids = forms.MultipleChoiceField(
        label="岗位类别",
        widget=forms.CheckboxSelectMultiple,
    )
    city_ids = forms.MultipleChoiceField(
        label="城市",
        widget=forms.CheckboxSelectMultiple,
    )
    cohort_ids = forms.MultipleChoiceField(
        label="届别",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, source_choices=(), filter_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_id"].choices = source_choices
        for name in ("category_ids", "city_ids", "cohort_ids"):
            self.fields[name].choices = tuple(
                (str(identity), label)
                for identity, label in (filter_choices or {}).get(name, ())
            )


class OpportunityEditForm(OpportunityCreateForm):
    opportunity_id = forms.UUIDField(widget=forms.HiddenInput)
    source_id = forms.CharField(widget=forms.HiddenInput)
    verification_status = forms.ChoiceField(
        choices=VERIFICATION_STATUS_CHOICES, label="核实状态"
    )
    publication_state = forms.ChoiceField(
        choices=PUBLICATION_STATE_CHOICES, label="上下架状态"
    )


class ReviewDecisionForm(forms.Form):
    review_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    decision = forms.ChoiceField(
        choices=(
            ("ACCEPTED", "接受并确认"),
            ("KEPT_MANUAL", "保留人工值"),
            ("RESOLVED", "标记已处理"),
        ),
        label="处理结果",
    )


class ReviewBatchForm(forms.Form):
    scope = forms.ChoiceField(
        choices=(("PAGE", "当前页"), ("ALL", "全部待审核")),
        widget=forms.HiddenInput,
    )
    page = forms.IntegerField(
        required=False,
        min_value=1,
        initial=1,
        widget=forms.HiddenInput,
    )
    per_page = forms.TypedChoiceField(
        required=False,
        choices=PAGE_SIZE_CHOICES,
        coerce=int,
        initial=20,
        widget=forms.HiddenInput,
    )

    def clean(self):
        cleaned = super().clean()
        review_ids = tuple(self.data.getlist("review_id"))
        if cleaned.get("scope") == "PAGE" and not 1 <= len(review_ids) <= 50:
            raise forms.ValidationError("当前页没有可处理的审核项。")
        cleaned["review_ids"] = review_ids
        return cleaned


class OpportunitySettingsForm(forms.Form):
    default_city_ids = forms.MultipleChoiceField(
        required=False,
        label="城市",
        widget=forms.CheckboxSelectMultiple,
    )
    default_verification_statuses = forms.MultipleChoiceField(
        required=False,
        label="核实状态",
        choices=VERIFICATION_STATUS_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    default_source_ids = forms.MultipleChoiceField(
        required=False,
        label="企业",
        widget=forms.CheckboxSelectMultiple,
    )
    default_recruitment_types = forms.MultipleChoiceField(
        required=False,
        label="招聘类型",
        choices=RECRUITMENT_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
    )
    default_category_ids = forms.MultipleChoiceField(
        required=False,
        label="岗位类别",
        widget=forms.CheckboxSelectMultiple,
    )
    default_cohort_ids = forms.MultipleChoiceField(
        required=False,
        label="届别",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, source_choices=(), filter_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["default_source_ids"].choices = source_choices
        for name in (
            "default_city_ids",
            "default_category_ids",
            "default_cohort_ids",
        ):
            self.fields[name].choices = tuple(
                (str(identity), label)
                for identity, label in (filter_choices or {}).get(name, ())
            )


class CheckActionForm(forms.Form):
    source_id = forms.UUIDField(required=False)
    run_id = forms.CharField(required=False, max_length=26)


__all__ = [
    "CheckActionForm",
    "OpportunityCreateForm",
    "OpportunityEditForm",
    "OpportunityFilterForm",
    "OpportunityPageForm",
    "OpportunitySettingsForm",
    "ReviewBatchForm",
    "ReviewDecisionForm",
    "SourceFilterForm",
    "SourceForm",
]
