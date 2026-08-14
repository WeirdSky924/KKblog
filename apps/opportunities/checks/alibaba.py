from urllib.parse import parse_qs, urlsplit

from .browser_adapter import BrowserSourceAdapter
from .http import SafeRequestError

_HOST = "campus-talent.alibaba.com"
_BATCH_ID = "100000760001"


def _source(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _HOST
        or parsed.path.rstrip("/") != "/campus/position"
        or parse_qs(parsed.query).get("batchId") != [_BATCH_ID]
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


class AlibabaCampusAdapter(BrowserSourceAdapter):
    def __init__(self, *, collector=None) -> None:
        super().__init__(
            key="alibaba-campus-v1",
            source_validator=_source,
            allowed_hosts=frozenset({_HOST}),
            collector=collector,
        )


ALIBABA_CAMPUS_ADAPTER = AlibabaCampusAdapter()

__all__ = ["ALIBABA_CAMPUS_ADAPTER", "AlibabaCampusAdapter"]
