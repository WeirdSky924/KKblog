from urllib.parse import urlsplit

from .browser_adapter import BrowserSourceAdapter
from .http import SafeRequestError

_HOST = "jobs.bytedance.com"


def _source(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _HOST
        or parsed.path.rstrip("/") != "/campus/position"
        or parsed.query
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


class ByteDanceCampusAdapter(BrowserSourceAdapter):
    def __init__(self, *, collector=None) -> None:
        super().__init__(
            key="bytedance-campus-v1",
            source_validator=_source,
            allowed_hosts=frozenset({_HOST}),
            collector=collector,
        )


BYTEDANCE_CAMPUS_ADAPTER = ByteDanceCampusAdapter()

__all__ = ["BYTEDANCE_CAMPUS_ADAPTER", "ByteDanceCampusAdapter"]
