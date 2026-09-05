from django import forms

from apps.core.ids import normalize_ulid

TAG_STATES = (
    ("", "全部状态"),
    ("PENDING", "待审核"),
    ("ACTIVE", "全站可用"),
    ("REJECTED", "已驳回"),
    ("DELETED", "已删除"),
)

TAG_ACTIONS = (
    ("APPROVE", "通过"),
    ("REJECT", "驳回"),
    ("DELETE", "删除"),
    ("RESTORE", "恢复"),
)


class AdminTagFilterForm(forms.Form):
    state = forms.ChoiceField(label="标签状态", required=False, choices=TAG_STATES)
    page = forms.IntegerField(required=False, min_value=1, initial=1)


class TagCreateForm(forms.Form):
    name = forms.CharField(
        label="标签名称",
        max_length=50,
        widget=forms.TextInput(attrs={"placeholder": "新增全站标签"}),
    )


class TagActionConfirmationForm(forms.Form):
    tag_id = forms.UUIDField(widget=forms.HiddenInput)
    tag_action = forms.ChoiceField(choices=TAG_ACTIONS, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("tag_action", "确认"),),
        widget=forms.HiddenInput,
    )


class SectionCoverForm(forms.Form):
    default_cover_asset_id = forms.CharField(
        label="分区默认封面",
        max_length=26,
        required=False,
        widget=forms.HiddenInput,
    )

    def clean_default_cover_asset_id(self):
        value = self.cleaned_data.get("default_cover_asset_id", "")
        if not value:
            return None
        try:
            return normalize_ulid(value)
        except (TypeError, ValueError):
            raise forms.ValidationError("分区默认封面不合法。") from None


class SectionCreateForm(SectionCoverForm):
    name = forms.CharField(
        label="分区名称",
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "新增文章分区"}),
    )


class SectionPageForm(forms.Form):
    page = forms.IntegerField(required=False, min_value=1, initial=1)


class SectionRenameConfirmationForm(forms.Form):
    section_id = forms.UUIDField(widget=forms.HiddenInput)
    name = forms.CharField(label="新分区名称", max_length=100)
    confirm = forms.ChoiceField(
        choices=(("section_rename", "确认重命名"),),
        widget=forms.HiddenInput,
    )


class SectionUpdateConfirmationForm(SectionCoverForm):
    section_id = forms.UUIDField(widget=forms.HiddenInput)
    name = forms.CharField(label="分区名称", max_length=100)
    confirm = forms.ChoiceField(
        choices=(("section_update", "确认更新"),),
        widget=forms.HiddenInput,
    )


class SectionDeleteConfirmationForm(forms.Form):
    section_id = forms.UUIDField(widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("section_delete", "确认删除"),),
        widget=forms.HiddenInput,
    )


__all__ = [
    "AdminTagFilterForm",
    "SectionCreateForm",
    "SectionDeleteConfirmationForm",
    "SectionRenameConfirmationForm",
    "SectionUpdateConfirmationForm",
    "TagActionConfirmationForm",
    "TagCreateForm",
]
