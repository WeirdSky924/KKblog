from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

from .adapters import AdapterResult, FetchClient
from .http import SafeHttpResult, SafeRequestError
from .moka import MOKA_ADAPTER

_MOKA_SOURCE = "https://app.mokahr.com/social-recruitment/high-flyer/140576#/jobs"


def _validate_source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "talent.deepseek.com"
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


class DeepSeekAdapter:
    key = "deepseek-moka-v1"
    browser_required = False
    authoritative_listing = True

    def __init__(self, *, delegate=MOKA_ADAPTER) -> None:
        self._delegate = delegate

    def check_opportunity(
        self,
        *,
        source_url: str,
        target_url: str,
        config: Mapping[str, object],
        client: FetchClient,
    ) -> SafeHttpResult:
        _validate_source(source_url)
        return self._delegate.check_opportunity(
            source_url=_MOKA_SOURCE,
            target_url=target_url,
            config=config,
            client=client,
        )

    def collect(
        self,
        *,
        source_url: str,
        config: Mapping[str, object],
        client: FetchClient,
        initial_response: SafeHttpResult,
        heartbeat,
    ) -> AdapterResult:
        _validate_source(source_url)
        delegated_config = {**config, "page_size": 3}
        return self._delegate.collect(
            source_url=_MOKA_SOURCE,
            config=delegated_config,
            client=client,
            initial_response=initial_response,
            heartbeat=heartbeat,
        )


DEEPSEEK_ADAPTER = DeepSeekAdapter()

__all__ = ["DEEPSEEK_ADAPTER", "DeepSeekAdapter"]
