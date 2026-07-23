from apps.accounts.models import Account


def account_theme(request):
    account = getattr(request, "account", None)
    if account is None or account.status != Account.Status.ACTIVE:
        return {"initial_theme": "light", "theme_source": "visitor"}
    return {
        "initial_theme": account.theme.casefold().replace("_", "-"),
        "theme_source": "account",
    }
