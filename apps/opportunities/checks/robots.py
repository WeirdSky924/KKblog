from __future__ import annotations

from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from .http import SafeHttpClient, SafeHttpResult, SafeRequestError

_USER_AGENT = "KajSpace-OpportunityChecker"


class RobotsAwareHttpClient:
    def __init__(self, client: SafeHttpClient, *, respect_robots_txt: bool) -> None:
        if not isinstance(client, SafeHttpClient):
            raise TypeError("client must be a SafeHttpClient")
        self._client = client
        self._respect = respect_robots_txt is not False
        self._policies: dict[str, RobotFileParser | bool] = {}

    def _policy(self, url: str) -> RobotFileParser | bool:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        cached = self._policies.get(hostname)
        if cached is not None:
            return cached
        robots_url = f"https://{hostname}/robots.txt"
        try:
            response = self._client.get(robots_url)
        except SafeRequestError:
            raise SafeRequestError("opportunities.robots_unavailable.v1") from None
        if response.status == 404:
            policy: RobotFileParser | bool = True
        elif response.status in (401, 403):
            policy = False
        elif 200 <= response.status < 300 and not response.truncated:
            parser = RobotFileParser()
            try:
                parser.parse(
                    response.body.decode("utf-8", errors="replace").splitlines()
                )
            except Exception:
                raise SafeRequestError("opportunities.robots_invalid.v1") from None
            policy = parser
        else:
            raise SafeRequestError("opportunities.robots_unavailable.v1")
        self._policies[hostname] = policy
        return policy

    def get(self, url: str, **limits) -> SafeHttpResult:
        return self._request("get", url, limits=limits)

    def post_json(self, url: str, payload, **limits) -> SafeHttpResult:
        return self._request("post_json", url, payload, limits=limits)

    def _request(self, method: str, url: str, *args, limits) -> SafeHttpResult:
        def require_allowed(target_url: str) -> None:
            policy = self._policy(target_url)
            if policy is False or (
                isinstance(policy, RobotFileParser)
                and not policy.can_fetch(_USER_AGENT, target_url)
            ):
                raise SafeRequestError("opportunities.robots_denied.v1")

        if self._respect:
            limits["request_guard"] = require_allowed
        return getattr(self._client, method)(url, *args, **limits)


__all__ = ["RobotsAwareHttpClient"]
