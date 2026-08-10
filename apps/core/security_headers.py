from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest, HttpResponseBase

_CONTENT_SECURITY_POLICY = "frame-src 'self' https://player.bilibili.com"


class ContentSecurityPolicyMiddleware:
    def __init__(
        self,
        get_response: Callable[[HttpRequest], HttpResponseBase],
    ) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = _CONTENT_SECURITY_POLICY
        return response
