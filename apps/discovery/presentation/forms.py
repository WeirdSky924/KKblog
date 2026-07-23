from uuid import UUID

from django import forms


class PaginationForm(forms.Form):
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


class HomePageForm(PaginationForm):
    tags = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"invalid_choice": "所选标签已不可用。"},
    )

    def __init__(self, *args, tag_choices=(), **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["tags"].choices = tuple(tag_choices)

    def clean_tags(self) -> tuple[UUID, ...]:
        values = self.cleaned_data.get("tags") or ()
        return tuple(dict.fromkeys(UUID(value) for value in values))

    def clean(self):
        cleaned_data = super().clean()
        raw_tags = self.data.getlist("tags") if hasattr(self.data, "getlist") else ()
        if len(set(raw_tags)) > 5:
            self.add_error("tags", "最多选择 5 个标签。")
        return cleaned_data


class SearchPageForm(PaginationForm):
    q = forms.CharField(
        required=True,
        max_length=100,
        strip=True,
        error_messages={
            "required": "请输入文章标题。",
            "max_length": "搜索内容不能超过 100 个字符。",
        },
        widget=forms.SearchInput(
            attrs={"autocomplete": "off", "placeholder": "搜索文章标题"}
        ),
    )


class BookmarkStateForm(forms.Form):
    class TargetState:
        SAVED = "saved"
        REMOVED = "removed"

    class Source:
        ARTICLE = "article"
        BOOKMARKS = "bookmarks"

    target_state = forms.ChoiceField(
        choices=(
            (TargetState.SAVED, "收藏"),
            (TargetState.REMOVED, "移除收藏"),
        ),
        widget=forms.HiddenInput,
        error_messages={
            "required": "请选择收藏状态。",
            "invalid_choice": "收藏状态无效。",
        },
    )
    source = forms.ChoiceField(
        choices=(
            (Source.ARTICLE, "文章"),
            (Source.BOOKMARKS, "收藏列表"),
        ),
        widget=forms.HiddenInput,
        error_messages={
            "required": "收藏来源无效。",
            "invalid_choice": "收藏来源无效。",
        },
    )
