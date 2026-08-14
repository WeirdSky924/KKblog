from urllib.parse import parse_qs, urlsplit

from .browser_adapter import BrowserSourceAdapter
from .http import SafeRequestError

_HOST = "campushr.hikvision.com"


def _source(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _HOST
        or parsed.path != "/school"
        or parse_qs(parsed.query).get("schoolType") != ["nozxf"]
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


class HikvisionAdapter(BrowserSourceAdapter):
    def __init__(self, *, collector=None) -> None:
        super().__init__(
            key="hikvision-v1",
            source_validator=_source,
            allowed_hosts=frozenset({_HOST}),
            collector=collector,
        )


HIKVISION_ADAPTER = HikvisionAdapter()

__all__ = ["HIKVISION_ADAPTER", "HikvisionAdapter"]
