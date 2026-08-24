from uuid import UUID

from django import forms

from apps.learning.contracts import (
    LEARNING_ADMIN_REASON_CHOICES,
    MAX_API_DAILY_LIMIT,
    MAX_API_MINUTE_LIMIT,
    MAX_QUESTIONS_PER_VOLUME,
    MIN_API_DAILY_LIMIT,
    MIN_API_MINUTE_LIMIT,
    MIN_QUESTIONS_PER_VOLUME,
    AdminLearningAction,
    KnowledgeDocumentState,
    LearningAdminTargetType,
    LearningAppealDecision,
    LearningCommandError,
    LearningQuotaLimits,
    LearningQuotaOverride,
    QuestionBankApiCorsMode,
    QuestionBankVisibility,
)
from apps.learning.public import normalize_cors_origins
from apps.learning.services.administration import AdminLearningTarget


class LearningDocumentFilterForm(forms.Form):
    q = forms.CharField(label="搜索", required=False, max_length=100)
    state = forms.ChoiceField(
        label="状态",
        required=False,
        choices=(
            ("", "全部状态"),
            *KnowledgeDocumentState.choices,
        ),
    )
    page = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput())


class LearningQuestionBankFilterForm(forms.Form):
    q = forms.CharField(label="搜索", required=False, max_length=100)
    state = forms.ChoiceField(
        label="运行状态",
        required=False,
        choices=(
            ("", "全部运行状态"),
            ("GENERATION_PENDING", "等待生成"),
            ("GENERATING", "生成中"),
            ("PUBLISHED", "已发布"),
            ("GENERATION_FAILED", "生成失败"),
        ),
    )
    visibility = forms.ChoiceField(
        label="可见性",
        required=False,
        choices=(("", "全部可见性"), *QuestionBankVisibility.choices),
    )
    page = forms.IntegerField(required=False, min_value=1, widget=forms.HiddenInput())


class LearningBatchForm(forms.Form):
    target_type = forms.ChoiceField(
        choices=tuple((item.value, item.value) for item in LearningAdminTargetType)
    )
    action = forms.ChoiceField(
        choices=tuple((item.value, item.value) for item in AdminLearningAction)
    )
    targets = forms.MultipleChoiceField(
        required=True,
        widget=forms.MultipleHiddenInput(),
    )
    reason_code = forms.ChoiceField(
        required=False,
        label="管理原因",
        choices=(("", "请选择管理原因"), *LEARNING_ADMIN_REASON_CHOICES),
        help_text="用于审计和通知；隐藏或删除时必须选择一个原因。",
    )
    confirm = forms.BooleanField(
        required=True,
        label="我确认按以上对象执行批量处置",
        widget=forms.CheckboxInput(attrs={"class": "learning-admin__confirm-checkbox"}),
    )

    def __init__(self, *args, target_values=(), require_reason=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.require_reason = require_reason
        action = self.data.get("action") if self.is_bound else ""
        if action in {"HIDE", "DELETE"}:
            if self.is_bound and not self.data.get("reason_code"):
                self.data = self.data.copy()
                self.data["reason_code"] = "policy_review"
            self.initial["reason_code"] = "policy_review"
        self.fields["targets"].choices = tuple(
            (value, value) for value in target_values
        )

    def clean_reason_code(self):
        value = self.cleaned_data.get("reason_code", "").strip()
        if self.require_reason and not value:
            value = "policy_review"
        return value

    def clean_confirm(self):
        value = self.cleaned_data["confirm"]
        raw = self.data.get("confirm")
        if value is not True or raw not in {
            "on",
            "true",
            "True",
            "1",
            "learning_batch",
        }:
            raise forms.ValidationError("确认信息无效。")
        return "learning_batch"

    def clean_targets(self):
        values = self.cleaned_data["targets"]
        if not 1 <= len(values) <= 50:
            raise forms.ValidationError("一次最多处置 50 个明确勾选对象。")
        targets = []
        for value in values:
            try:
                target_id, raw_version = value.split(":", 1)
                targets.append(AdminLearningTarget(UUID(target_id), int(raw_version)))
            except (TypeError, ValueError):
                raise forms.ValidationError("批量对象版本信息无效。") from None
        return tuple(targets)


class LearningAppealDecisionForm(forms.Form):
    appeal_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)
    decision = forms.ChoiceField(
        choices=tuple((item.value, item.value) for item in LearningAppealDecision)
    )
    decision_markdown = forms.CharField(
        label="决定说明",
        min_length=1,
        max_length=4_000,
        widget=forms.Textarea(attrs={"rows": 8}),
    )
    confirm = forms.CharField(widget=forms.HiddenInput(), initial="learning_appeal")

    def clean_confirm(self):
        value = self.cleaned_data["confirm"]
        if value != "learning_appeal":
            raise forms.ValidationError("确认信息无效。")
        return value


class LearningQuotaForm(forms.Form):
    daily_uploads = forms.IntegerField(
        min_value=1,
        max_value=100,
        label="每日上传",
        help_text="每个账户每天最多新提交的知识文档数；只影响后续提交，不取消已上传文档。",
    )
    pending_reviews = forms.IntegerField(
        min_value=1,
        max_value=20,
        label="同时待处理",
        help_text="每个账户同时处于待审核/审核中的文档数；达到上限会阻止新提交，现有审核继续运行。",
    )
    daily_generations = forms.IntegerField(
        min_value=1,
        max_value=50,
        label="每日生成",
        help_text="每个账户每天最多接受的题库生成请求数；只影响新请求。",
    )
    concurrent_model_runs = forms.IntegerField(
        min_value=1,
        max_value=3,
        label="同时运行",
        help_text="每个账户同时运行的审核/生成模型任务数；超过后新任务排队或重试，不中断现有任务。",
    )
    unpurged_banks = forms.IntegerField(
        min_value=1,
        max_value=2_000,
        label="未清理题库",
        help_text="每个账户允许保留的未清理题库数量；达到上限会阻止新题库生成，删除或清理后恢复空间。",
    )
    max_questions_per_volume = forms.IntegerField(
        min_value=MIN_QUESTIONS_PER_VOLUME,
        max_value=MAX_QUESTIONS_PER_VOLUME,
        required=False,
        label="单卷题数上限",
        help_text="后续生成任务每一卷最多生成的题目数量；模型可能因知识点不足生成更少，最多生成两卷。留空保持当前值。",
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)

    def limits(self) -> LearningQuotaLimits:
        return LearningQuotaLimits(
            daily_uploads=self.cleaned_data["daily_uploads"],
            pending_reviews=self.cleaned_data["pending_reviews"],
            daily_generations=self.cleaned_data["daily_generations"],
            concurrent_model_runs=self.cleaned_data["concurrent_model_runs"],
            unpurged_banks=self.cleaned_data["unpurged_banks"],
        )


class LearningGenerationResetForm(forms.Form):
    confirm = forms.CharField(
        widget=forms.HiddenInput(), initial="learning_generation_reset"
    )

    def clean_confirm(self):
        value = self.cleaned_data["confirm"]
        if value != "learning_generation_reset":
            raise forms.ValidationError("请重新确认每日生成计数重置。")
        return value


class LearningQuestionBankApiForm(forms.Form):
    enabled = forms.BooleanField(
        label="开放匿名题库 API",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
        help_text="控制未登录客户端是否可以读取公开题库；只读，不开放上传、生成或管理能力。",
    )
    cors_mode = forms.ChoiceField(
        label="来源策略",
        choices=QuestionBankApiCorsMode.choices,
        help_text="决定浏览器跨域请求是否放行；不影响服务端或同源请求。",
    )
    cors_origins = forms.CharField(
        label="允许的 HTTPS Origin（每行一个）",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "spellcheck": "false"}),
        help_text="仅在白名单模式生效；每行一个 HTTPS Origin。修改会影响后续浏览器请求。",
    )
    minute_limit = forms.IntegerField(
        label="每 IP 每分钟",
        min_value=MIN_API_MINUTE_LIMIT,
        max_value=MAX_API_MINUTE_LIMIT,
        help_text="单个 IP 在任意一分钟内可访问 API 的次数；超出返回限流，不影响题库数据。",
    )
    daily_limit = forms.IntegerField(
        label="每 IP 每日",
        min_value=MIN_API_DAILY_LIMIT,
        max_value=MAX_API_DAILY_LIMIT,
        help_text="单个 IP 每个自然日可访问 API 的次数；必须不小于每分钟上限。",
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput(), min_value=1)

    def clean_cors_origins(self):
        value = self.cleaned_data.get("cors_origins", "")
        try:
            return normalize_cors_origins(
                tuple(line.strip() for line in value.splitlines() if line.strip())
            )
        except LearningCommandError as error:
            raise forms.ValidationError(str(error)) from None

    def clean(self):
        cleaned = super().clean()
        minute = cleaned.get("minute_limit")
        daily = cleaned.get("daily_limit")
        if minute is not None and daily is not None and daily < minute:
            self.add_error("daily_limit", "每日限额不能小于每分钟限额。")
        return cleaned


class LearningAccountQuotaForm(forms.Form):
    account_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(widget=forms.HiddenInput(), min_value=0)
    daily_uploads = forms.IntegerField(
        min_value=1,
        max_value=100,
        required=False,
        label="每日上传",
        help_text="留空继承全站配置；填写后只覆盖这个账户的后续提交。",
    )
    pending_reviews = forms.IntegerField(
        min_value=1,
        max_value=20,
        required=False,
        label="同时待处理",
        help_text="留空继承全站配置；控制这个账户同时待审核/审核中文档数量。",
    )
    daily_generations = forms.IntegerField(
        min_value=1,
        max_value=50,
        required=False,
        label="每日生成",
        help_text="留空继承全站配置；控制这个账户每天可创建的题库生成请求数。",
    )
    concurrent_model_runs = forms.IntegerField(
        min_value=1,
        max_value=3,
        required=False,
        label="同时运行",
        help_text="留空继承全站配置；控制这个账户同时占用的审核/生成模型任务数。",
    )
    unpurged_banks = forms.IntegerField(
        min_value=1,
        max_value=2_000,
        required=False,
        label="未清理题库",
        help_text="留空继承全站配置；控制这个账户可保留的未清理题库数量。",
    )

    def limits(self) -> LearningQuotaOverride:
        return LearningQuotaOverride(
            daily_uploads=self.cleaned_data.get("daily_uploads"),
            pending_reviews=self.cleaned_data.get("pending_reviews"),
            daily_generations=self.cleaned_data.get("daily_generations"),
            concurrent_model_runs=self.cleaned_data.get("concurrent_model_runs"),
            unpurged_banks=self.cleaned_data.get("unpurged_banks"),
        )


__all__ = [
    "LearningAccountQuotaForm",
    "LearningAppealDecisionForm",
    "LearningBatchForm",
    "LearningDocumentFilterForm",
    "LearningGenerationResetForm",
    "LearningQuotaForm",
    "LearningQuestionBankFilterForm",
    "LearningQuestionBankApiForm",
]
