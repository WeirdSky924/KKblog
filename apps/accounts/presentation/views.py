from urllib.parse import urlencode

from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.audit import record_profile_audit
from apps.accounts.policies.registration import (
    RegistrationPolicy,
    configured_registration_policy,
)
from apps.accounts.presentation.cookies import delete_session_cookie, set_session_cookie
from apps.accounts.presentation.forms import (
    AuthorPreferenceForm,
    ChangeEmailForm,
    ChangePasswordForm,
    CodeLoginForm,
    LoginCodeRequestForm,
    NewEmailCodeForm,
    PasswordLoginForm,
    PasswordResetCodeForm,
    PasswordResetForm,
    ProfileForm,
    RegistrationCodeForm,
    RegistrationForm,
    RevokeAllSessionsForm,
    RevokeSessionForm,
    ThemeForm,
)
from apps.accounts.public import is_active_author
from apps.accounts.queries.profile import public_account_identity
from apps.accounts.queries.sessions import session_list
from apps.accounts.services.authentication import (
    AuthenticationError,
    authenticate_code,
    authenticate_password,
    request_login_code,
)
from apps.accounts.services.author_preferences import (
    AuthorPreferenceError,
    author_preferences,
    change_author_preferences,
)
from apps.accounts.services.credentials import (
    CredentialError,
    change_email,
    change_password,
    request_new_email_code,
    request_password_reset_code,
    reset_password,
)
from apps.accounts.services.profile import ProfileError, change_profile
from apps.accounts.services.registration import (
    RegistrationError,
    register_account,
    request_registration_code,
)
from apps.accounts.services.sessions import (
    SessionError,
    revoke_all_sessions,
    revoke_session,
    summarize_user_agent,
)
from apps.accounts.services.verification import default_verification_store


def _safe_next(request: HttpRequest) -> str:
    value = request.GET.get("next", "") or request.POST.get("next", "")
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return value
    return "/"


def _policy() -> RegistrationPolicy:
    return configured_registration_policy()


def _user_agent_summary(request: HttpRequest) -> str:
    return summarize_user_agent(request.META.get("HTTP_USER_AGENT", ""))


def _client_ip(request: HttpRequest) -> str:
    return getattr(request, "client_ip", request.META.get("REMOTE_ADDR", "127.0.0.1"))


def _render_registration(
    request,
    *,
    registration_form=None,
    code_form=None,
    sent=False,
    status=200,
):
    return render(
        request,
        "accounts/register.html",
        {
            "registration_form": registration_form or RegistrationForm(),
            "code_form": code_form or RegistrationCodeForm(),
            "direct_enabled": _policy().direct_enabled,
            "code_sent": sent,
        },
        status=status,
    )


def register(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _render_registration(request)
    store = default_verification_store()
    trace_code = getattr(request, "trace_code", "")
    client_ip = _client_ip(request)
    if request.POST.get("action") == "send_code":
        form = RegistrationCodeForm(request.POST)
        if not form.is_valid():
            return _render_registration(request, code_form=form, status=422)
        try:
            request_registration_code(
                email=form.cleaned_data["email"],
                invite_code=form.cleaned_data["invite_code"],
                policy=_policy(),
                client_ip=client_ip,
                trace_code=trace_code,
                store=store,
            )
        except RegistrationError as exc:
            form.add_error(None, str(exc))
            return _render_registration(request, code_form=form, status=422)
        initial = {
            "email": form.cleaned_data["email"],
            "invite_code": form.cleaned_data["invite_code"],
        }
        return _render_registration(
            request,
            code_form=form,
            registration_form=RegistrationForm(initial=initial),
            sent=True,
        )
    form = RegistrationForm(request.POST)
    if not form.is_valid():
        return _render_registration(request, registration_form=form, status=422)
    try:
        result = register_account(
            email=form.cleaned_data["email"],
            code=form.cleaned_data["code"],
            password=form.cleaned_data["password"],
            invite_code=form.cleaned_data["invite_code"],
            remember=form.cleaned_data["remember"],
            policy=_policy(),
            client_ip=client_ip,
            trace_code=trace_code,
            store=store,
            user_agent_summary=_user_agent_summary(request),
        )
    except RegistrationError as exc:
        form.add_error(None, str(exc))
        return _render_registration(request, registration_form=form, status=422)
    response = redirect("/")
    set_session_cookie(
        response,
        raw_token=result.raw_session_token,
        remember=form.cleaned_data["remember"],
    )
    return response


def _render_login(
    request,
    *,
    mode="password",
    password_form=None,
    code_request_form=None,
    code_form=None,
    code_sent=False,
    status=200,
):
    return render(
        request,
        "accounts/login.html",
        {
            "mode": mode,
            "password_form": password_form or PasswordLoginForm(),
            "code_request_form": code_request_form or LoginCodeRequestForm(),
            "code_form": code_form or CodeLoginForm(),
            "code_sent": code_sent,
            "next": _safe_next(request),
            "password_reset_completed": request.GET.get("reset") == "1",
            "session_signed_out": request.GET.get("signed_out") in {"1", "all"},
        },
        status=status,
    )


def login(request: HttpRequest) -> HttpResponse:
    if getattr(request, "account_id", None):
        return redirect(_safe_next(request))
    if request.method == "GET":
        mode = "code" if request.GET.get("mode") == "code" else "password"
        return _render_login(request, mode=mode)
    action = request.POST.get("action", "")
    trace_code = getattr(request, "trace_code", "")
    client_ip = _client_ip(request)
    if action == "send_login_code":
        form = LoginCodeRequestForm(request.POST)
        if not form.is_valid():
            return _render_login(
                request, mode="code", code_request_form=form, status=422
            )
        try:
            request_login_code(
                email=form.cleaned_data["email"],
                client_ip=client_ip,
                trace_code=trace_code,
                store=default_verification_store(),
            )
        except AuthenticationError as exc:
            form.add_error(None, str(exc))
            return _render_login(
                request, mode="code", code_request_form=form, status=422
            )
        return _render_login(
            request,
            mode="code",
            code_request_form=form,
            code_form=CodeLoginForm(initial={"email": form.cleaned_data["email"]}),
            code_sent=True,
        )
    form = (
        CodeLoginForm(request.POST)
        if action == "code"
        else PasswordLoginForm(request.POST)
    )
    mode = "code" if action == "code" else "password"
    if not form.is_valid():
        kwargs = {"code_form": form} if mode == "code" else {"password_form": form}
        return _render_login(request, mode=mode, status=422, **kwargs)
    try:
        if mode == "code":
            result = authenticate_code(
                email=form.cleaned_data["email"],
                code=form.cleaned_data["code"],
                remember=form.cleaned_data["remember"],
                client_ip=client_ip,
                trace_code=trace_code,
                store=default_verification_store(),
                user_agent_summary=_user_agent_summary(request),
            )
        else:
            result = authenticate_password(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                remember=form.cleaned_data["remember"],
                client_ip=client_ip,
                trace_code=trace_code,
                user_agent_summary=_user_agent_summary(request),
            )
    except AuthenticationError as exc:
        form.add_error(None, str(exc))
        kwargs = {"code_form": form} if mode == "code" else {"password_form": form}
        return _render_login(request, mode=mode, status=422, **kwargs)
    target = (
        "/accounts/settings/?tab=password"
        if result.account.must_change_password
        else _safe_next(request)
    )
    response = redirect(target)
    set_session_cookie(
        response, raw_token=result.raw_token, remember=form.cleaned_data["remember"]
    )
    return response


def _request_meta(request: HttpRequest) -> tuple[str, str]:
    return (
        _client_ip(request),
        getattr(request, "trace_code", ""),
    )


def _render_reset(request, *, code_form=None, reset_form=None, sent=False, status=200):
    return render(
        request,
        "accounts/password_reset.html",
        {
            "code_form": code_form or PasswordResetCodeForm(),
            "reset_form": reset_form or PasswordResetForm(),
            "code_sent": sent,
        },
        status=status,
    )


def password_reset(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return _render_reset(request)
    client_ip, trace_code = _request_meta(request)
    if request.POST.get("action") == "send_reset_code":
        form = PasswordResetCodeForm(request.POST)
        if not form.is_valid():
            return _render_reset(request, code_form=form, status=422)
        try:
            request_password_reset_code(
                email=form.cleaned_data["email"],
                client_ip=client_ip,
                trace_code=trace_code,
                store=default_verification_store(),
            )
        except CredentialError as exc:
            form.add_error(None, str(exc))
            return _render_reset(request, code_form=form, status=422)
        return _render_reset(
            request,
            code_form=form,
            reset_form=PasswordResetForm(initial={"email": form.cleaned_data["email"]}),
            sent=True,
        )
    form = PasswordResetForm(request.POST)
    if not form.is_valid():
        return _render_reset(request, reset_form=form, status=422)
    try:
        reset_password(
            email=form.cleaned_data["email"],
            code=form.cleaned_data["code"],
            new_password=form.cleaned_data["new_password"],
            client_ip=client_ip,
            trace_code=trace_code,
            store=default_verification_store(),
        )
    except CredentialError as exc:
        form.add_error(exc.field, str(exc))
        return _render_reset(request, reset_form=form, status=422)
    return redirect(f"{reverse('accounts:login')}?reset=1")


def _render_settings(
    request,
    *,
    password_form=None,
    email_code_form=None,
    email_form=None,
    profile_form=None,
    theme_form=None,
    author_preference_form=None,
    code_sent=False,
    active_tab=None,
    status=200,
):
    account = request.account
    selected_tab = active_tab or request.GET.get("tab", "profile")
    is_author = is_active_author(account.id)
    allowed_tabs = {"profile", "credentials", "theme"}
    if is_author:
        allowed_tabs.add("authoring")
    if selected_tab not in allowed_tabs:
        selected_tab = "profile"
    profile_form = profile_form or ProfileForm(
        initial={
            "nickname": account.nickname or "",
            "avatar_asset_id": account.avatar_asset_id or "",
        }
    )
    theme_form = theme_form or ThemeForm(
        initial={"theme": account.theme.casefold().replace("_", "-")}
    )
    author_preference_form = author_preference_form or AuthorPreferenceForm(
        initial={
            "auto_republish_enabled": (
                author_preferences(account_id=account.id).auto_republish_enabled
                if is_author
                else False
            )
        }
    )
    submitted_avatar_id = profile_form["avatar_asset_id"].value() or None
    identity = public_account_identity(account.id)
    return render(
        request,
        "accounts/settings.html",
        {
            "password_form": password_form or ChangePasswordForm(),
            "email_code_form": email_code_form or NewEmailCodeForm(),
            "email_form": email_form or ChangeEmailForm(),
            "profile_form": profile_form,
            "theme_form": theme_form,
            "author_preference_form": author_preference_form,
            "is_author": is_author,
            "code_sent": code_sent,
            "account": account,
            "active_tab": selected_tab,
            "profile_identity": identity,
            "profile_avatar_asset_id": submitted_avatar_id,
            "profile_avatar_preview_url": (
                identity.avatar_url
                if submitted_avatar_id == account.avatar_asset_id
                else None
            ),
            "credentials_saved": request.GET.get("saved") == "1",
            "profile_saved": request.GET.get("profile_saved") == "1",
            "theme_saved": request.GET.get("theme_saved") == "1",
            "author_preference_saved": (
                request.GET.get("author_preference_saved") == "1"
            ),
        },
        status=status,
    )


def _rotated_response(request, result):
    response = redirect(f"{reverse('accounts:settings')}?tab=credentials&saved=1")
    remaining = max(
        1, int((result.session.expires_at - timezone.now()).total_seconds())
    )
    set_session_cookie(
        response,
        raw_token=result.raw_token,
        remember=result.session.kind == "REMEMBER_30D",
        max_age=remaining,
    )
    return response


def settings_view(request: HttpRequest) -> HttpResponse:
    if not getattr(request, "account_id", None):
        settings_url = reverse("accounts:settings")
        return redirect(f"{reverse('accounts:login')}?next={settings_url}")
    if request.method == "GET":
        return _render_settings(request)
    client_ip, trace_code = _request_meta(request)
    action = request.POST.get("action", "")
    if action == "change_profile":
        form = ProfileForm(request.POST)
        if not form.is_valid():
            return _render_settings(
                request, profile_form=form, active_tab="profile", status=422
            )
        try:
            change_profile(
                account_id=request.account_id,
                nickname=form.cleaned_data["nickname"],
                theme=request.account.theme,
                avatar_asset_id=form.cleaned_data["avatar_asset_id"],
                client_ip=client_ip,
                trace_code=trace_code,
                audit_writer=record_profile_audit,
            )
        except ProfileError as exc:
            form.add_error(exc.field, str(exc))
            return _render_settings(
                request, profile_form=form, active_tab="profile", status=422
            )
        return redirect(f"{reverse('accounts:settings')}?tab=profile&profile_saved=1")
    if action == "change_theme":
        form = ThemeForm(request.POST)
        if not form.is_valid():
            return _render_settings(
                request, theme_form=form, active_tab="theme", status=422
            )
        try:
            change_profile(
                account_id=request.account_id,
                nickname=request.account.nickname,
                theme=form.cleaned_data["theme"],
                avatar_asset_id=request.account.avatar_asset_id,
                client_ip=client_ip,
                trace_code=trace_code,
                audit_writer=record_profile_audit,
            )
        except ProfileError as exc:
            form.add_error(exc.field, str(exc))
            return _render_settings(
                request, theme_form=form, active_tab="theme", status=422
            )
        return redirect(f"{reverse('accounts:settings')}?tab=theme&theme_saved=1")
    if action == "change_author_preference":
        form = AuthorPreferenceForm(request.POST)
        if not form.is_valid():
            return _render_settings(
                request,
                author_preference_form=form,
                active_tab="authoring",
                status=422,
            )
        try:
            change_author_preferences(
                account_id=request.account_id,
                auto_republish_enabled=form.cleaned_data["auto_republish_enabled"],
                client_ip=client_ip,
                trace_code=trace_code,
                audit_writer=record_profile_audit,
            )
        except AuthorPreferenceError as exc:
            form.add_error(None, str(exc))
            return _render_settings(
                request,
                author_preference_form=form,
                active_tab="authoring",
                status=422,
            )
        return redirect(
            f"{reverse('accounts:settings')}?tab=authoring&author_preference_saved=1"
        )
    if action == "send_email_code":
        form = NewEmailCodeForm(request.POST)
        if not form.is_valid():
            return _render_settings(
                request,
                email_code_form=form,
                active_tab="credentials",
                status=422,
            )
        try:
            request_new_email_code(
                account_id=request.account_id,
                new_email=form.cleaned_data["new_email"],
                client_ip=client_ip,
                trace_code=trace_code,
                store=default_verification_store(),
            )
        except CredentialError as exc:
            form.add_error(exc.field, str(exc))
            return _render_settings(
                request,
                email_code_form=form,
                active_tab="credentials",
                status=422,
            )
        return _render_settings(
            request,
            email_code_form=form,
            email_form=ChangeEmailForm(
                initial={"new_email": form.cleaned_data["new_email"]}
            ),
            code_sent=True,
            active_tab="credentials",
        )
    if action == "change_email":
        form = ChangeEmailForm(request.POST)
        if not form.is_valid():
            return _render_settings(
                request, email_form=form, active_tab="credentials", status=422
            )
        try:
            result = change_email(
                account_id=request.account_id,
                current_session_id=request.login_session.id,
                new_email=form.cleaned_data["new_email"],
                code=form.cleaned_data["code"],
                client_ip=client_ip,
                trace_code=trace_code,
                store=default_verification_store(),
            )
        except CredentialError as exc:
            form.add_error(exc.field, str(exc))
            return _render_settings(
                request, email_form=form, active_tab="credentials", status=422
            )
        return _rotated_response(request, result)
    form = ChangePasswordForm(request.POST)
    if action != "change_password" or not form.is_valid():
        return _render_settings(
            request, password_form=form, active_tab="credentials", status=422
        )
    try:
        result = change_password(
            account_id=request.account_id,
            current_session_id=request.login_session.id,
            current_password=form.cleaned_data["current_password"],
            new_password=form.cleaned_data["new_password"],
            client_ip=client_ip,
            trace_code=trace_code,
        )
    except CredentialError as exc:
        form.add_error(exc.field, str(exc))
        return _render_settings(
            request, password_form=form, active_tab="credentials", status=422
        )
    return _rotated_response(request, result)


def theme_view(request: HttpRequest) -> HttpResponse:
    return_path = _safe_next(request)
    if not getattr(request, "account_id", None):
        query = urlencode({"next": return_path})
        return redirect(f"{reverse('accounts:login')}?{query}")
    if request.method != "POST":
        return HttpResponseNotAllowed(("POST",))

    form = ThemeForm(request.POST)
    if not form.is_valid():
        return HttpResponse("请选择有效的主题。", status=422)
    client_ip, trace_code = _request_meta(request)
    try:
        change_profile(
            account_id=request.account_id,
            nickname=request.account.nickname,
            theme=form.cleaned_data["theme"],
            avatar_asset_id=request.account.avatar_asset_id,
            client_ip=client_ip,
            trace_code=trace_code,
            audit_writer=record_profile_audit,
        )
    except ProfileError as exc:
        return HttpResponse(str(exc), status=422)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return HttpResponse(status=204)
    return redirect(return_path)


def _render_sessions(
    request: HttpRequest,
    *,
    revoke_form=None,
    all_form=None,
    confirm_all=False,
    status=200,
) -> HttpResponse:
    return render(
        request,
        "accounts/sessions.html",
        {
            "sessions": session_list(
                account_id=request.account_id,
                current_session_id=request.login_session.id,
            ),
            "revoke_form": revoke_form or RevokeSessionForm(),
            "all_form": all_form
            or RevokeAllSessionsForm(initial={"confirm": "all_devices"}),
            "confirm_all": confirm_all,
            "session_revoked": request.GET.get("revoked") == "1",
        },
        status=status,
    )


def sessions_view(request: HttpRequest) -> HttpResponse:
    if not getattr(request, "account_id", None):
        sessions_url = reverse("accounts:sessions")
        return redirect(f"{reverse('accounts:login')}?next={sessions_url}")
    if request.method == "GET":
        return _render_sessions(
            request, confirm_all=request.GET.get("confirm") == "all"
        )

    client_ip, trace_code = _request_meta(request)
    action = request.POST.get("action", "")
    if action == "revoke":
        form = RevokeSessionForm(request.POST)
        if not form.is_valid():
            return _render_sessions(request, revoke_form=form, status=422)
        target_id = form.cleaned_data["session_id"]
        try:
            revoke_session(
                account_id=request.account_id,
                current_session_id=request.login_session.id,
                target_session_id=target_id,
                client_ip=client_ip,
                trace_code=trace_code,
            )
        except SessionError as exc:
            form.add_error(None, str(exc))
            return _render_sessions(request, revoke_form=form, status=422)
        if target_id == request.login_session.id:
            response = redirect(f"{reverse('accounts:login')}?signed_out=1")
            delete_session_cookie(response)
            return response
        return redirect(f"{reverse('accounts:sessions')}?revoked=1")

    form = RevokeAllSessionsForm(request.POST)
    if action != "revoke_all" or not form.is_valid():
        form.add_error(None, "请先确认退出所有设备")
        return _render_sessions(
            request,
            all_form=form,
            confirm_all=True,
            status=422,
        )
    try:
        revoke_all_sessions(
            account_id=request.account_id,
            current_session_id=request.login_session.id,
            client_ip=client_ip,
            trace_code=trace_code,
        )
    except SessionError as exc:
        form.add_error(None, str(exc))
        return _render_sessions(
            request,
            all_form=form,
            confirm_all=True,
            status=422,
        )
    response = redirect(f"{reverse('accounts:login')}?signed_out=all")
    delete_session_cookie(response)
    return response
