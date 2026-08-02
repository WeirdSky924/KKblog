import re
import unicodedata
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser

import nh3
from django.conf import settings
from django.utils.module_loading import import_string

MAX_VERIFICATION_EMAIL_TEMPLATE_BYTES = 48 * 1024

DEFAULT_VERIFICATION_EMAIL_TEMPLATE = """<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background-color:#f7f7f8;font-family:Microsoft YaHei,PingFang SC,Arial,sans-serif;color:#202124">
  <tr>
    <td align="center" style="padding:36px 16px">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background-color:#ffffff;border:1px solid #d9d9dc;border-top:4px solid #7e2637;border-radius:6px">
        <tr>
          <td style="padding:36px 40px 18px">
            <p style="margin:0 0 24px;color:#7e2637;font-size:15px;font-weight:700;line-height:1.5">{{ site_name }}</p>
            <h1 style="margin:0 0 14px;color:#202124;font-size:28px;font-weight:700;line-height:1.35">邮箱验证码</h1>
            <p style="margin:0;color:#65676b;font-size:16px;line-height:1.75">你正在进行{{ purpose }}，请使用下方验证码完成验证。</p>
          </td>
        </tr>
        <tr>
          <td style="padding:8px 40px 24px">
            <p style="margin:0;padding:20px 24px;background-color:#f1f1f2;border-left:4px solid #7e2637;color:#202124;font-size:34px;font-weight:700;line-height:1.25;text-align:center;letter-spacing:0">{{ code }}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 40px 36px">
            <p style="margin:0 0 10px;color:#65676b;font-size:14px;line-height:1.7">验证码将在 {{ minutes }} 分钟后失效，请勿转发或告知他人。</p>
            <p style="margin:0;color:#65676b;font-size:14px;line-height:1.7">若不是你本人操作，可以忽略这封邮件。</p>
          </td>
        </tr>
      </table>
      <p style="margin:18px 0 0;color:#65676b;font-size:12px;line-height:1.6">此邮件由 {{ site_name }} 自动发送，请勿直接回复。</p>
    </td>
  </tr>
</table>
"""

_ALLOWED_VARIABLES = frozenset({"site_name", "code", "minutes", "purpose"})
_VARIABLE = re.compile(r"{{\s*([a-z_][a-z0-9_]*)\s*}}")
_ALLOWED_TAGS = frozenset(
    {
        "br",
        "div",
        "h1",
        "h2",
        "p",
        "small",
        "span",
        "strong",
        "table",
        "tbody",
        "td",
        "tr",
    }
)
_ALLOWED_ATTRIBUTES = {
    "table": {"cellpadding", "cellspacing", "role", "style", "width"},
    "td": {"align", "style", "valign", "width"},
    "div": {"style"},
    "h1": {"style"},
    "h2": {"style"},
    "p": {"style"},
    "small": {"style"},
    "span": {"style"},
    "strong": {"style"},
}
_STYLE_PROPERTIES = frozenset(
    {
        "background-color",
        "border",
        "border-bottom",
        "border-left",
        "border-radius",
        "border-right",
        "border-top",
        "color",
        "font-family",
        "font-size",
        "font-weight",
        "letter-spacing",
        "line-height",
        "margin",
        "margin-bottom",
        "margin-left",
        "margin-right",
        "margin-top",
        "max-width",
        "padding",
        "padding-bottom",
        "padding-left",
        "padding-right",
        "padding-top",
        "text-align",
        "vertical-align",
        "width",
    }
)
_SAFE_STYLE_VALUE = re.compile(r"[a-zA-Z0-9#.,% ()/-]+\Z")


class EmailTemplateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerificationEmailConfiguration:
    site_name: str
    template_source: str


class _TemplateStructureValidator(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self._validate_tag(tag)
        allowed = _ALLOWED_ATTRIBUTES.get(tag, set())
        for name, value in attrs:
            if name not in allowed:
                raise EmailTemplateError("邮件模板包含不支持的 HTML 属性。")
            if name == "style":
                _validate_style(value or "")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        self._validate_tag(tag)

    @staticmethod
    def _validate_tag(tag):
        if tag not in _ALLOWED_TAGS:
            raise EmailTemplateError("邮件模板包含不支持的 HTML 标签。")


def _validate_style(value: str) -> None:
    for declaration in value.split(";"):
        declaration = declaration.strip()
        if not declaration:
            continue
        if ":" not in declaration:
            raise EmailTemplateError("邮件模板包含不合法的样式。")
        name, raw_value = (part.strip() for part in declaration.split(":", 1))
        if name.lower() not in _STYLE_PROPERTIES:
            raise EmailTemplateError("邮件模板包含不支持的样式属性。")
        lowered = raw_value.lower()
        if not raw_value or not _SAFE_STYLE_VALUE.fullmatch(raw_value):
            raise EmailTemplateError("邮件模板包含不安全的样式值。")
        if any(
            token in lowered for token in ("url", "expression", "javascript", "@import")
        ):
            raise EmailTemplateError("邮件模板不能加载外部资源。")
        if name.lower() == "letter-spacing" and raw_value not in {"0", "0px"}:
            raise EmailTemplateError("邮件模板的字符间距必须为 0。")


def validate_verification_email_template(source: str) -> str:
    if not isinstance(source, str):
        raise EmailTemplateError("邮件模板必须是 UTF-8 HTML 文本。")
    normalized = unicodedata.normalize("NFC", source).strip()
    if not normalized:
        raise EmailTemplateError("邮件模板不能为空。")
    if len(normalized.encode("utf-8")) > MAX_VERIFICATION_EMAIL_TEMPLATE_BYTES:
        raise EmailTemplateError("邮件模板不能超过 48 KiB。")
    variables = set(_VARIABLE.findall(normalized))
    if "code" not in variables:
        raise EmailTemplateError("邮件模板必须包含 {{ code }} 验证码变量。")
    if variables - _ALLOWED_VARIABLES or "{{" in _VARIABLE.sub("", normalized):
        raise EmailTemplateError("邮件模板包含不支持的变量。")
    validator = _TemplateStructureValidator(convert_charrefs=True)
    try:
        validator.feed(normalized)
        validator.close()
    except (EmailTemplateError, ValueError):
        raise
    sanitized = nh3.clean(
        normalized,
        tags=set(_ALLOWED_TAGS),
        attributes=_ALLOWED_ATTRIBUTES,
        clean_content_tags={"form", "iframe", "script", "style", "svg", "template"},
        strip_comments=True,
        link_rel=None,
    )
    return sanitized.strip()


def render_verification_email_html(
    source: str,
    *,
    site_name: str,
    code: str,
    minutes: int,
    purpose: str,
) -> str:
    template = validate_verification_email_template(source)
    values = {
        "site_name": site_name,
        "code": code,
        "minutes": str(minutes),
        "purpose": purpose,
    }
    return _VARIABLE.sub(lambda match: escape(values[match.group(1)]), template)


def verification_email_subject(site_name: str) -> str:
    return f"{verification_email_sender_name(site_name)} · 邮箱验证码"


def verification_email_sender_name(site_name: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", str(site_name)).split())
    return normalized or "Kaj的小房间"


def configured_verification_email() -> VerificationEmailConfiguration:
    provider = import_string(settings.ACCOUNT_VERIFICATION_EMAIL_CONFIGURATION_PROVIDER)
    configuration = provider()
    if not isinstance(configuration, VerificationEmailConfiguration):
        raise TypeError("Verification email provider returned an invalid value")
    return configuration


__all__ = [
    "DEFAULT_VERIFICATION_EMAIL_TEMPLATE",
    "EmailTemplateError",
    "MAX_VERIFICATION_EMAIL_TEMPLATE_BYTES",
    "VerificationEmailConfiguration",
    "configured_verification_email",
    "render_verification_email_html",
    "validate_verification_email_template",
    "verification_email_sender_name",
    "verification_email_subject",
]
