from apps.administration.navigation_registry import resolved_admin_navigation


def administration_shell(request):
    if not getattr(request, "administration_authorized", False):
        return {}
    match = getattr(request, "resolver_match", None)
    return {
        "admin_navigation_groups": resolved_admin_navigation(),
        "admin_current_route": getattr(match, "view_name", ""),
    }
