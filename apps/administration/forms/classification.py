from django import forms

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


class SectionCreateForm(forms.Form):
    name = forms.CharField(
        label="分区名称",
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "新增文章分区"}),
    )


class SectionRenameConfirmationForm(forms.Form):
    section_id = forms.UUIDField(widget=forms.HiddenInput)
    name = forms.CharField(label="新分区名称", max_length=100)
    confirm = forms.ChoiceField(
        choices=(("section_rename", "确认重命名"),),
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
    "TagActionConfirmationForm",
    "TagCreateForm",
]
