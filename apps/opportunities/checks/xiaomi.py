from urllib.parse import parse_qs, urlsplit

from .browser_adapter import BrowserSourceAdapter
from .http import SafeRequestError

_HOST = "xiaomi.jobs.f.mioffice.cn"


def _source(*, value: str, website_path: str, spread: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _HOST
        or parsed.path.rstrip("/") != f"/{website_path}"
        or parse_qs(parsed.query).get("spread") != [spread]
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


class XiaomiAdapter(BrowserSourceAdapter):
    def __init__(
        self,
        *,
        collector_key: str,
        website_path: str,
        recruitment_type: str,
        collector=None,
    ) -> None:
        spread = "J7NS6YR" if website_path == "campus" else "6AA3R7B"
        super().__init__(
            key=collector_key,
            source_validator=lambda value: _source(
                value=value, website_path=website_path, spread=spread
            ),
            allowed_hosts=frozenset({_HOST}),
            collector=collector,
        )
        self.recruitment_type = recruitment_type


XIAOMI_CAMPUS_ADAPTER = XiaomiAdapter(
    collector_key="xiaomi-campus-v1",
    website_path="campus",
    recruitment_type="CAMPUS",
)
XIAOMI_INTERN_ADAPTER = XiaomiAdapter(
    collector_key="xiaomi-intern-v1",
    website_path="internship",
    recruitment_type="INTERNSHIP",
)

__all__ = ["XIAOMI_CAMPUS_ADAPTER", "XIAOMI_INTERN_ADAPTER", "XiaomiAdapter"]
