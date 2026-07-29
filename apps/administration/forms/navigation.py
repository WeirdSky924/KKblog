from django import forms

NODE_TYPES = (
    ("INTERNAL_PAGE", "站内页"),
    ("SECTION", "文章分区"),
    ("EXTERNAL_LINK", "外链"),
)


class _NodeFields(forms.Form):
    label = forms.CharField(label="导航名称", max_length=80)
    node_type = forms.ChoiceField(label="节点类型", choices=NODE_TYPES)
    target_url = forms.CharField(
        label="目标地址",
        required=False,
        max_length=255,
        help_text="站内页使用公开路径；外链仅允许不含查询参数的 HTTPS 地址。",
    )
    section_id = forms.ChoiceField(label="文章分区", required=False)

    def __init__(self, *args, section_choices=(), **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["section_id"].choices = (("", "请选择分区"), *section_choices)

    def clean(self):
        cleaned = super().clean()
        node_type = cleaned.get("node_type")
        if node_type == "SECTION":
            if not cleaned.get("section_id"):
                self.add_error("section_id", "请选择文章分区。")
            cleaned["target_url"] = ""
        else:
            if not cleaned.get("target_url"):
                self.add_error("target_url", "请输入导航目标地址。")
            cleaned["section_id"] = ""
        return cleaned


class NavigationNodeCreateForm(_NodeFields):
    parent_id = forms.ChoiceField(label="父级节点", required=False)
    position = forms.IntegerField(label="层内位置", min_value=0, max_value=500)
    expected_tree_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, parent_choices=(), **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["parent_id"].choices = (("", "顶层"), *parent_choices)


class NavigationNodeEditConfirmationForm(_NodeFields):
    node_id = forms.UUIDField(widget=forms.HiddenInput)
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    expected_tree_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("navigation_edit", "确认编辑"),),
        widget=forms.HiddenInput,
    )


class NavigationVisibilityConfirmationForm(forms.Form):
    node_id = forms.UUIDField(widget=forms.HiddenInput)
    hidden = forms.TypedChoiceField(
        choices=(("true", "隐藏"), ("false", "显示")),
        coerce=lambda value: value == "true",
        widget=forms.HiddenInput,
    )
    expected_row_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    expected_tree_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("navigation_visibility", "确认显隐"),),
        widget=forms.HiddenInput,
    )


class NavigationDeleteConfirmationForm(forms.Form):
    node_id = forms.UUIDField(widget=forms.HiddenInput)
    expected_versions = forms.CharField(widget=forms.HiddenInput)
    expected_tree_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("navigation_delete", "确认删除"),),
        widget=forms.HiddenInput,
    )


class NavigationMoveForm(forms.Form):
    node_id = forms.UUIDField(widget=forms.HiddenInput)
    new_parent_id = forms.CharField(required=False)
    new_position = forms.IntegerField(min_value=0, max_value=500)
    expected_versions = forms.CharField(widget=forms.HiddenInput)
    expected_tree_version = forms.IntegerField(min_value=1, widget=forms.HiddenInput)


__all__ = [
    "NavigationDeleteConfirmationForm",
    "NavigationMoveForm",
    "NavigationNodeCreateForm",
    "NavigationNodeEditConfirmationForm",
    "NavigationVisibilityConfirmationForm",
]
