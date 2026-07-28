from django import forms

ARTICLE_STATES = (
    ("", "全部状态"),
    ("DRAFT", "草稿"),
    ("SCHEDULED", "定时"),
    ("PUBLISHED", "已发布"),
    ("DELETED", "删除冷静期"),
)

REPORT_STATES = (
    ("", "全部状态"),
    ("PENDING", "待初审"),
    ("UPHELD", "初审成立"),
    ("REJECTED", "初审驳回"),
    ("APPEAL_PENDING", "申诉待复审"),
    ("FINAL_UPHELD", "终局成立"),
    ("FINAL_REJECTED", "终局驳回"),
    ("CLOSED", "已关闭"),
)


class AdminArticleFilterForm(forms.Form):
    q = forms.CharField(
        label="标题、作者邮箱或昵称",
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "输入关键词"}),
    )
    state = forms.ChoiceField(label="文章状态", required=False, choices=ARTICLE_STATES)


class ArticleActionConfirmationForm(forms.Form):
    article_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    moderation_action = forms.ChoiceField(
        choices=(("HIDE", "隐藏"), ("DELETE", "删除")),
        widget=forms.HiddenInput,
    )
    reason = forms.CharField(
        label="操作原因（可选）",
        required=False,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    confirm = forms.ChoiceField(
        choices=(("article_action", "确认"),),
        widget=forms.HiddenInput,
    )


class ArticleRestoreConfirmationForm(forms.Form):
    case_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    confirm = forms.ChoiceField(
        choices=(("article_restore", "确认恢复"),),
        widget=forms.HiddenInput,
    )


class ArticleAppealReviewConfirmationForm(forms.Form):
    case_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    appeal_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    outcome = forms.ChoiceField(
        choices=(("GRANTED", "准许"), ("REJECTED", "驳回")),
        widget=forms.HiddenInput,
    )
    decision_reason = forms.CharField(
        label="复审说明（可选）",
        required=False,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    confirm = forms.ChoiceField(
        choices=(("article_appeal_review", "确认复审"),),
        widget=forms.HiddenInput,
    )


class CommentDeletionConfirmationForm(forms.Form):
    comment_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    reason = forms.CharField(
        label="删除原因（可选）",
        required=False,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    confirm = forms.ChoiceField(
        choices=(("comment_delete", "确认删除"),),
        widget=forms.HiddenInput,
    )


class AdminReportFilterForm(forms.Form):
    state = forms.ChoiceField(label="案件状态", required=False, choices=REPORT_STATES)


class ReportReviewConfirmationForm(forms.Form):
    report_id = forms.CharField(max_length=26, widget=forms.HiddenInput)
    outcome = forms.ChoiceField(
        choices=(("UPHELD", "成立"), ("REJECTED", "驳回")),
        widget=forms.HiddenInput,
    )
    decision_reason = forms.CharField(
        label="裁决说明（可选）",
        required=False,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    confirm = forms.ChoiceField(
        choices=(("report_review", "确认初审"),),
        widget=forms.HiddenInput,
    )


class ReportFinalReviewConfirmationForm(ReportReviewConfirmationForm):
    confirm = forms.ChoiceField(
        choices=(("report_final_review", "确认终局复审"),),
        widget=forms.HiddenInput,
    )


__all__ = [
    "AdminArticleFilterForm",
    "AdminReportFilterForm",
    "ArticleActionConfirmationForm",
    "ArticleAppealReviewConfirmationForm",
    "ArticleRestoreConfirmationForm",
    "CommentDeletionConfirmationForm",
    "ReportFinalReviewConfirmationForm",
    "ReportReviewConfirmationForm",
]
