from apps.opportunities.checks.adapters import AdapterResult
from apps.opportunities.checks.deepseek import DeepSeekAdapter
from apps.opportunities.checks.http import SafeHttpResult


class _Delegate:
    def __init__(self):
        self.calls = []

    def collect(self, **kwargs):
        self.calls.append(("collect", kwargs))
        return AdapterResult(complete=True)

    def check_opportunity(self, **kwargs):
        self.calls.append(("check", kwargs))
        return SafeHttpResult(200, kwargs["target_url"], "", b"", False)


def test_deepseek_adapter_delegates_collection_to_verified_moka_site():
    delegate = _Delegate()
    adapter = DeepSeekAdapter(delegate=delegate)
    source_url = "https://talent.deepseek.com/"
    initial = SafeHttpResult(200, source_url, "DeepSeek 招聘", b"", False)

    result = adapter.collect(
        source_url=source_url,
        config={"_max_pages": 50},
        client=object(),
        initial_response=initial,
        heartbeat=lambda: None,
    )

    assert result.complete is True
    _, call = delegate.calls[0]
    assert call["source_url"] == (
        "https://app.mokahr.com/social-recruitment/high-flyer/140576#/jobs"
    )
    assert call["config"]["page_size"] == 3
    assert call["initial_response"] is initial


def test_deepseek_adapter_delegates_detail_validation_to_moka():
    delegate = _Delegate()
    adapter = DeepSeekAdapter(delegate=delegate)
    target_url = (
        "https://app.mokahr.com/social-recruitment/high-flyer/140576"
        "#/job/bae809fb-1978-4401-b209-34067b26569d"
    )

    response = adapter.check_opportunity(
        source_url="https://talent.deepseek.com/",
        target_url=target_url,
        config={},
        client=object(),
    )

    assert response.status == 200
    _, call = delegate.calls[0]
    assert call["source_url"].endswith("high-flyer/140576#/jobs")
    assert call["target_url"] == target_url
