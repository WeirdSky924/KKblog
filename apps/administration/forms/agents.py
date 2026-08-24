import json

from django import forms

from apps.agents.contracts import (
    MAX_CONCURRENCY_LIMIT,
    MAX_CONTEXT_WINDOW_TOKENS,
    MAX_ENDPOINT_DAILY_TOKEN_LIMIT,
    MAX_MAX_OUTPUT_TOKENS,
    MAX_PER_RUN_TOKEN_LIMIT,
    MAX_REQUEST_TIMEOUT_SECONDS,
    MAX_SITE_DAILY_TOKEN_LIMIT,
    MAX_THINKING_BUDGET_TOKENS,
    MIN_CONCURRENCY_LIMIT,
    MIN_CONTEXT_WINDOW_TOKENS,
    MIN_ENDPOINT_DAILY_TOKEN_LIMIT,
    MIN_MAX_OUTPUT_TOKENS,
    MIN_PER_RUN_TOKEN_LIMIT,
    MIN_REQUEST_TIMEOUT_SECONDS,
    MIN_SITE_DAILY_TOKEN_LIMIT,
    MIN_THINKING_BUDGET_TOKENS,
    AgentCommandError,
    EndpointRuntimeSettings,
    default_endpoint_base_url,
)
from apps.agents.providers.capabilities import (
    reasoning_effort_choices,
    resolve_reasoning_capability,
)
from apps.agents.public import (
    AgentAuthenticationMode,
    AgentEndpointProtocol,
    AgentProfilePurpose,
    EndpointDraft,
    ProfileDraft,
)


def _number(minimum: int, maximum: int):
    return forms.NumberInput(
        attrs={"min": minimum, "max": maximum, "step": 1, "inputmode": "numeric"}
    )


class AgentEndpointForm(forms.Form):
    endpoint_id = forms.UUIDField(required=False, widget=forms.HiddenInput())
    expected_version = forms.IntegerField(required=False, widget=forms.HiddenInput())
    display_name = forms.CharField(
        label="显示名称",
        max_length=80,
        help_text="仅用于后台识别，不参与请求、配额或费用计算。",
    )
    protocol = forms.ChoiceField(
        label="Provider",
        choices=(
            (AgentEndpointProtocol.OPENAI_GPT, "OpenAI / GPT"),
            (AgentEndpointProtocol.OPENAI_DEEPSEEK, "DeepSeek"),
            (AgentEndpointProtocol.ANTHROPIC, "Anthropic / Claude"),
        ),
        help_text="决定 LangChain 客户端、认证头和结构化输出通道；修改后需要重新进行连接与 schema 检查。",
    )
    base_url = forms.CharField(
        label="接口地址（可选）",
        max_length=500,
        required=False,
        help_text="实际请求的根地址；OpenAI/DeepSeek 根地址会自动补 /v1。修改只影响后续新任务，已创建的 Invocation 快照不变。",
    )
    model_name = forms.CharField(
        label="Model",
        max_length=160,
        help_text="发送给 Provider 的模型标识。修改只影响后续新任务，已有 Invocation 不会漂移。",
    )
    authentication_mode = forms.ChoiceField(
        label="认证方式",
        choices=(
            (AgentAuthenticationMode.SECRET_ALIAS, "服务器 API 密钥"),
            (AgentAuthenticationMode.CUSTOM_API_KEY, "自定义 API Key"),
            (AgentAuthenticationMode.NONE, "无需认证（自建服务）"),
        ),
        help_text="决定 API Key 的来源；切换认证方式会影响后续外呼，密钥正文不会显示在页面或日志中。",
    )
    secret_alias = forms.ChoiceField(
        label="服务器密钥",
        required=False,
        help_text="服务器环境中已注册的密钥别名，只保存引用；更换后需要重新检查 Endpoint。",
    )
    api_key = forms.CharField(
        label="API Key",
        required=False,
        strip=False,
        widget=forms.PasswordInput(
            attrs={"autocomplete": "new-password", "spellcheck": "false"}
        ),
        help_text="仅自定义认证填写；编辑时留空表示保持已有密钥。保存后只保留加密值，不回显原文。",
    )
    clear_api_key = forms.BooleanField(
        label="清除已保存的自定义 API Key",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
        help_text="清除后 Endpoint 将不再携带自定义密钥；不会删除已创建 Invocation 的认证快照。",
    )
    enabled = forms.BooleanField(
        label="启用 Endpoint",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
        help_text="停用后阻止新的 AGENT 检查和 Invocation；已经创建并固化快照的运行不受当前配置漂移影响。",
    )
    context_window_tokens = forms.IntegerField(
        label="上下文窗口",
        min_value=MIN_CONTEXT_WINDOW_TOKENS,
        max_value=MAX_CONTEXT_WINDOW_TOKENS,
        widget=_number(MIN_CONTEXT_WINDOW_TOKENS, MAX_CONTEXT_WINDOW_TOKENS),
        help_text="一次请求允许的输入与输出总 token 空间。过小会在外呼前拒绝长文档；修改后只影响新任务，并需要重新检查 AGENT schema。",
    )
    max_output_tokens = forms.IntegerField(
        label="单次输出上限",
        min_value=MIN_MAX_OUTPUT_TOKENS,
        max_value=MAX_MAX_OUTPUT_TOKENS,
        widget=_number(MIN_MAX_OUTPUT_TOKENS, MAX_MAX_OUTPUT_TOKENS),
        help_text="单次最多生成的 token 数，影响答案完整度、费用和截断概率；必须小于上下文窗口。",
    )
    reasoning_effort = forms.ChoiceField(
        label="推理强度",
        required=False,
        choices=(("", "不设置（使用上游默认值）"),),
        help_text="按当前 Provider 和 Model 显示上游支持的推理强度；未知模型不会发送该参数。",
    )
    thinking_budget_tokens = forms.IntegerField(
        label="旧版思考 token 预算",
        required=False,
        min_value=MIN_THINKING_BUDGET_TOKENS,
        max_value=MAX_THINKING_BUDGET_TOKENS,
        widget=_number(MIN_THINKING_BUDGET_TOKENS, MAX_THINKING_BUDGET_TOKENS),
        help_text="仅旧版 Claude extended thinking 使用；与推理强度不能同时填写，且必须小于单次输出上限。",
    )
    per_run_token_limit = forms.IntegerField(
        label="单业务运行上限",
        min_value=MIN_PER_RUN_TOKEN_LIMIT,
        max_value=MAX_PER_RUN_TOKEN_LIMIT,
        widget=_number(MIN_PER_RUN_TOKEN_LIMIT, MAX_PER_RUN_TOKEN_LIMIT),
        help_text="一次业务运行所有尝试合计可消耗的上限，包含 retry 和 repair；过小会减少重试次数或在外呼前拒绝任务。",
    )
    request_timeout_seconds = forms.IntegerField(
        label="请求超时（秒）",
        min_value=MIN_REQUEST_TIMEOUT_SECONDS,
        max_value=MAX_REQUEST_TIMEOUT_SECONDS,
        widget=_number(MIN_REQUEST_TIMEOUT_SECONDS, MAX_REQUEST_TIMEOUT_SECONDS),
        help_text="单次 Provider 请求的总截止时间。复杂生成可能需要更长时间；超时会进入失败/重试状态，不会发布半成品。",
    )
    concurrency_limit = forms.IntegerField(
        label="并发上限",
        min_value=MIN_CONCURRENCY_LIMIT,
        max_value=MAX_CONCURRENCY_LIMIT,
        widget=_number(MIN_CONCURRENCY_LIMIT, MAX_CONCURRENCY_LIMIT),
        help_text="同一 Endpoint 同时允许的模型任务数。降低会让任务排队，高于 1 可能增加并发费用；不改变单个结果。",
    )
    endpoint_daily_token_limit = forms.IntegerField(
        label="Endpoint 每日上限",
        min_value=MIN_ENDPOINT_DAILY_TOKEN_LIMIT,
        max_value=MAX_ENDPOINT_DAILY_TOKEN_LIMIT,
        widget=_number(MIN_ENDPOINT_DAILY_TOKEN_LIMIT, MAX_ENDPOINT_DAILY_TOKEN_LIMIT),
        help_text="该 Endpoint 每个自然日的硬 token 上限；达到后新的外呼会被拒绝，已有运行不被强行中断。",
    )
    input_price_per_million_tokens = forms.DecimalField(
        label="每百万输入 token 价格",
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=6,
        help_text="仅用于后台费用估算和统计，不改变 token 配额或 Provider 请求。",
    )
    output_price_per_million_tokens = forms.DecimalField(
        label="每百万输出 token 价格",
        required=False,
        min_value=0,
        max_digits=14,
        decimal_places=6,
        help_text="仅用于后台费用估算和统计，不改变 token 配额或 Provider 请求。",
    )

    def __init__(self, *args, site_daily_limit: int, secret_aliases=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.site_daily_limit = site_daily_limit
        protocol = (
            self.data.get("protocol")
            if self.is_bound
            else self.initial.get("protocol", "")
        )
        model_name = (
            self.data.get("model_name")
            if self.is_bound
            else self.initial.get("model_name", "")
        )
        self.fields["reasoning_effort"].choices = reasoning_effort_choices(
            protocol, model_name
        )
        self.fields[
            "thinking_budget_tokens"
        ].disabled = not resolve_reasoning_capability(
            protocol, model_name
        ).supports_thinking_budget
        if not self.is_bound:
            defaults = EndpointRuntimeSettings()
            endpoint_daily_limit = min(
                defaults.endpoint_daily_token_limit,
                site_daily_limit,
            )
            self.initial.setdefault("protocol", AgentEndpointProtocol.OPENAI_GPT)
            self.initial.setdefault(
                "context_window_tokens", defaults.context_window_tokens
            )
            self.initial.setdefault("max_output_tokens", defaults.max_output_tokens)
            self.initial.setdefault(
                "per_run_token_limit",
                min(defaults.per_run_token_limit, endpoint_daily_limit),
            )
            self.initial.setdefault(
                "request_timeout_seconds", defaults.request_timeout_seconds
            )
            self.initial.setdefault("concurrency_limit", defaults.concurrency_limit)
            self.initial.setdefault("endpoint_daily_token_limit", endpoint_daily_limit)
        self.fields["secret_alias"].choices = [("", "不使用密钥")] + [
            (alias, alias) for alias in secret_aliases
        ]
        if not self.is_bound and not self.initial.get("authentication_mode"):
            self.initial["authentication_mode"] = (
                AgentAuthenticationMode.SECRET_ALIAS
                if secret_aliases
                else AgentAuthenticationMode.NONE
            )

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        if not cleaned.get("base_url"):
            cleaned["base_url"] = default_endpoint_base_url(cleaned["protocol"])
        if cleaned["authentication_mode"] == AgentAuthenticationMode.NONE:
            if cleaned.get("api_key") or cleaned.get("clear_api_key"):
                self.add_error("api_key", "无需认证模式不能填写或清除 API Key。")
                return cleaned
            cleaned["secret_alias"] = ""
        elif cleaned["authentication_mode"] == AgentAuthenticationMode.SECRET_ALIAS:
            if cleaned.get("api_key") or cleaned.get("clear_api_key"):
                self.add_error(
                    "api_key", "服务器密钥模式不能填写或清除自定义 API Key。"
                )
                return cleaned
            if not cleaned["secret_alias"]:
                self.add_error("secret_alias", "请选择服务器已注册的密钥别名。")
                return cleaned
        elif cleaned["authentication_mode"] == AgentAuthenticationMode.CUSTOM_API_KEY:
            cleaned["secret_alias"] = ""
            if cleaned.get("api_key") and cleaned.get("clear_api_key"):
                self.add_error("api_key", "不能同时更新和清除自定义 API Key。")
                return cleaned
            if cleaned.get("clear_api_key"):
                cleaned["authentication_mode"] = AgentAuthenticationMode.NONE
        elif not cleaned["secret_alias"]:
            self.add_error("secret_alias", "请选择服务器已注册的密钥别名。")
            return cleaned
        try:
            self.runtime_settings(cleaned).validate(
                site_daily_token_limit=self.site_daily_limit
            )
        except AgentCommandError as error:
            raise forms.ValidationError(str(error)) from None
        return cleaned

    @staticmethod
    def runtime_settings(cleaned) -> EndpointRuntimeSettings:
        return EndpointRuntimeSettings(
            context_window_tokens=cleaned["context_window_tokens"],
            max_output_tokens=cleaned["max_output_tokens"],
            reasoning_effort=cleaned.get("reasoning_effort", ""),
            thinking_budget_tokens=cleaned.get("thinking_budget_tokens"),
            per_run_token_limit=cleaned["per_run_token_limit"],
            request_timeout_seconds=cleaned["request_timeout_seconds"],
            concurrency_limit=cleaned["concurrency_limit"],
            endpoint_daily_token_limit=cleaned["endpoint_daily_token_limit"],
        )

    def draft(self) -> EndpointDraft:
        cleaned = self.cleaned_data
        return EndpointDraft(
            display_name=cleaned["display_name"],
            protocol=cleaned["protocol"],
            base_url=cleaned["base_url"],
            model_name=cleaned["model_name"],
            authentication_mode=cleaned["authentication_mode"],
            secret_alias=cleaned["secret_alias"],
            api_key=cleaned["api_key"],
            clear_api_key=cleaned["clear_api_key"],
            enabled=cleaned["enabled"],
            runtime=self.runtime_settings(cleaned),
            input_price_per_million_tokens=cleaned["input_price_per_million_tokens"],
            output_price_per_million_tokens=cleaned["output_price_per_million_tokens"],
        )


class AgentSiteTokenLimitForm(forms.Form):
    daily_token_limit = forms.IntegerField(
        label="全站每日 token 上限",
        min_value=MIN_SITE_DAILY_TOKEN_LIMIT,
        max_value=MAX_SITE_DAILY_TOKEN_LIMIT,
        widget=_number(MIN_SITE_DAILY_TOKEN_LIMIT, MAX_SITE_DAILY_TOKEN_LIMIT),
        help_text="全站所有 Endpoint 共用的每日硬上限；达到后所有新的模型外呼都会被拒绝，已有运行不受影响。",
    )
    expected_version = forms.IntegerField(widget=forms.HiddenInput())


class AgentProfileForm(forms.Form):
    profile_id = forms.UUIDField(required=False, widget=forms.HiddenInput())
    expected_version = forms.IntegerField(required=False, widget=forms.HiddenInput())
    key = forms.RegexField(
        label="稳定标识",
        regex=r"[a-z][a-z0-9-]{2,63}\Z",
        max_length=64,
        help_text="业务代码使用的唯一标识。创建后不可修改；它决定调用方找到哪个 AGENT。",
    )
    display_name = forms.CharField(
        label="AGENT 名称",
        max_length=80,
        help_text="后台展示名称，不改变业务行为。",
    )
    purpose = forms.ChoiceField(
        label="用途",
        choices=AgentProfilePurpose.choices,
        help_text="决定哪个业务模块调用它以及对应的输出语义；修改后必须确认 schema 和 Prompt 仍匹配。",
    )
    endpoint_id = forms.ChoiceField(
        label="Endpoint",
        help_text="指定新任务发送到哪个模型连接。切换只影响后续任务，已有 Invocation 保留原 Endpoint 快照。",
    )
    schema_key = forms.RegexField(
        label="输出 schema",
        regex=r"[a-z][a-z0-9_.-]{2,95}\Z",
        max_length=96,
        help_text="本地确定性校验契约。修改后必须重新通过该 schema 的 capability probe，输出不符合时不会进入业务表。",
    )
    enabled = forms.BooleanField(
        label="启用 AGENT",
        required=False,
        widget=forms.CheckboxInput(attrs={"role": "switch"}),
        help_text="启用前必须有 Prompt、启用的 Endpoint 和成功的当前 schema 检查；停用只阻止新任务。",
    )

    def __init__(self, *args, endpoints=(), key_readonly=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["endpoint_id"].choices = [
            (str(endpoint.endpoint_id), endpoint.display_name) for endpoint in endpoints
        ]
        if key_readonly:
            self.fields["key"].disabled = True

    def draft(self) -> ProfileDraft:
        cleaned = self.cleaned_data
        return ProfileDraft(
            key=cleaned["key"],
            display_name=cleaned["display_name"],
            purpose=cleaned["purpose"],
            endpoint_id=cleaned["endpoint_id"],
            schema_key=cleaned["schema_key"],
            enabled=cleaned["enabled"],
        )


class AgentPromptForm(forms.Form):
    profile_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(widget=forms.HiddenInput())
    markdown_source = forms.CharField(
        label="Markdown Prompt",
        widget=forms.Textarea(attrs={"rows": 18, "spellcheck": "false"}),
        help_text="只填写业务目标和输出要求。文档内容始终是不可信材料，安全边界、schema、重试和权限由 Harness 强制处理；保存会创建新版本，只影响后续任务。",
    )


class AgentEndpointCheckForm(forms.Form):
    endpoint_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(widget=forms.HiddenInput())
    request_id = forms.CharField(max_length=128, widget=forms.HiddenInput())
    confirm = forms.CharField(widget=forms.HiddenInput())
    profile_key = forms.ChoiceField(
        label="结构化能力（可选）",
        required=False,
        help_text="不选择只检查 LangChain 网络、认证和基础响应；选择 AGENT 会额外发送该 profile 的真实 schema，成功后才允许启用或继续使用该 AGENT。两种检查都可能产生 Provider 费用。",
    )

    def __init__(self, *args, capability_options=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["profile_key"].choices = [("", "仅检查网络与基础 JSON")] + [
            (
                option.profile_key,
                f"{option.display_name} · {option.schema_key}"
                + (" · 已启用" if option.enabled else " · 待启用"),
            )
            for option in capability_options
        ]

    def clean_confirm(self):
        if self.cleaned_data["confirm"] != "endpoint_check":
            raise forms.ValidationError("请重新确认连接检查。")
        return "endpoint_check"


class AgentTokenResetForm(forms.Form):
    scope = forms.ChoiceField(
        choices=(("SITE", "全站"), ("ENDPOINT", "Endpoint")),
        widget=forms.HiddenInput(),
    )
    endpoint_id = forms.UUIDField(required=False, widget=forms.HiddenInput())
    expected_ledger_version = forms.IntegerField(
        min_value=0, widget=forms.HiddenInput()
    )
    reason = forms.CharField(
        label="重置原因",
        max_length=255,
        help_text="仅写入审计记录。重置通过 adjustment 将今日有效用量归零，不删除历史 ledger，也不释放活跃预留。",
    )
    operation_id = forms.CharField(max_length=128, widget=forms.HiddenInput())
    confirm = forms.CharField(widget=forms.HiddenInput())

    def clean_confirm(self):
        if self.cleaned_data["confirm"] != "token_reset":
            raise forms.ValidationError("请重新确认用量重置。")
        return "token_reset"


class AgentRestoreDefaultsForm(forms.Form):
    expected_site_version = forms.IntegerField(widget=forms.HiddenInput())
    endpoint_versions = forms.CharField(widget=forms.HiddenInput())
    confirm = forms.CharField(widget=forms.HiddenInput())

    def clean_confirm(self):
        if self.cleaned_data["confirm"] != "restore_defaults":
            raise forms.ValidationError("请重新确认恢复默认上限。")
        return "restore_defaults"

    def clean_endpoint_versions(self):
        try:
            value = json.loads(self.cleaned_data["endpoint_versions"])
        except (TypeError, ValueError):
            raise forms.ValidationError("Endpoint 版本集合不合法。") from None
        if not isinstance(value, dict) or any(
            not isinstance(key, str)
            or isinstance(version, bool)
            or not isinstance(version, int)
            or version < 1
            for key, version in value.items()
        ):
            raise forms.ValidationError("Endpoint 版本集合不合法。")
        return value


class AgentPromptSwitchForm(forms.Form):
    profile_id = forms.UUIDField(widget=forms.HiddenInput())
    revision_id = forms.UUIDField(widget=forms.HiddenInput())
    expected_version = forms.IntegerField(widget=forms.HiddenInput())
    confirm = forms.CharField(widget=forms.HiddenInput())

    def clean_confirm(self):
        if self.cleaned_data["confirm"] != "prompt_switch":
            raise forms.ValidationError("请重新确认 Prompt 版本切换。")
        return "prompt_switch"
