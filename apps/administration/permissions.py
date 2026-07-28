from functools import wraps

from django.core.exceptions import PermissionDenied
from django.utils.cache import patch_vary_headers

from apps.accounts.public import is_administrator


def administrator_required(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not is_administrator(getattr(request, "account_id", None)):
            raise PermissionDenied
        request.administration_authorized = True
        response = view(request, *args, **kwargs)
        response.headers["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ("Cookie",))
        return response

    return guarded


__all__ = ["administrator_required"]
