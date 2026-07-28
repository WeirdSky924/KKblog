from django.shortcuts import redirect

from apps.administration.navigation_registry import default_admin_route_name


def index(request):
    del request
    return redirect(default_admin_route_name())
