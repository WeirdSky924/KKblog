from apps.accounts.models import Account, RoleAssignment
from apps.accounts.queries.profile import public_account_identity


def account_theme(request):
    account = getattr(request, "account", None)
    if account is None or account.status != Account.Status.ACTIVE:
        return {
            "initial_theme": "light",
            "theme_source": "visitor",
            "shell_account": None,
            "shell_is_administrator": False,
            "shell_return_path": request.get_full_path(),
            "shell_session_id": None,
        }
    return {
        "initial_theme": account.theme.casefold().replace("_", "-"),
        "theme_source": "account",
        "shell_account": public_account_identity(account.id),
        "shell_is_administrator": account.roles.filter(
            role=RoleAssignment.Role.ADMINISTRATOR
        ).exists(),
        "shell_return_path": request.get_full_path(),
        "shell_session_id": request.login_session.id,
    }
