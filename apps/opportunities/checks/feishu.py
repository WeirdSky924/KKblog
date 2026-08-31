from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from .browser import BrowserCollector
from .browser_adapter import BrowserSourceAdapter
from .http import SafeRequestError

# Finite tenant allowlist shared with the browser runner.  A source must be
# added here and in the runner contract before it can use browser collection.
FEISHU_SOURCE_HOSTS = frozenset(
    {
        "boke.jobs.feishu.cn",
        "anker-in.jobs.feishu.cn",
        "dexmal-inc.jobs.feishu.cn",
        "fastbase.jobs.feishu.cn",
        "global-intco.jobs.feishu.cn",
        "hf7l9aiqzx.jobs.feishu.cn",
        "iwhih7is28.jobs.feishu.cn",
        "k11pnjpvz1.jobs.feishu.cn",
        "kwh0jtf778.jobs.feishu.cn",
        "leiniao-ibg.jobs.feishu.cn",
        "learnings.jobs.feishu.cn",
        "leoglobal.jobs.feishu.cn",
        "lilithgames.jobs.feishu.cn",
        "weikezhijia.jobs.feishu.cn",
        "momenta.jobs.feishu.cn",
        "qcraft.jobs.feishu.cn",
        "radrocktech.jobs.feishu.cn",
        "senturytire.jobs.feishu.cn",
        "smartlogictech.jobs.feishu.cn",
        "tarsrobot.jobs.feishu.cn",
        "xiaopeng.jobs.feishu.cn",
    }
)


def _source(source_url: str) -> None:
    parsed = urlsplit(source_url)
    path = parsed.path.rstrip("/") or "/"
    if (
        parsed.scheme != "https"
        or parsed.hostname not in FEISHU_SOURCE_HOSTS
        or len(path) > 160
        or "//" in path
        or not re.fullmatch(
            r"/(?:(?:[A-Za-z0-9_-]+/)?position/list|(?:\d+/)?(?:campus|intern|index(?:/position/list)?))",
            path,
        )
    ):
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")


def _allowed_hosts(source_url: str) -> Iterable[str]:
    host = urlsplit(source_url).hostname
    if host is None:
        raise SafeRequestError("opportunities.adapter_config_invalid.v1")
    return (host,)


class FeishuCareerAdapter(BrowserSourceAdapter):
    def __init__(self, *, collector: BrowserCollector | None = None) -> None:
        super().__init__(
            key="feishu-career-v1",
            source_validator=_source,
            allowed_hosts=_allowed_hosts,
            collector=collector,
        )


FEISHU_ADAPTER = FeishuCareerAdapter()

__all__ = ["FEISHU_ADAPTER", "FEISHU_SOURCE_HOSTS", "FeishuCareerAdapter"]
