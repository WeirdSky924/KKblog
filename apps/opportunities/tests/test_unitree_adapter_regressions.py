from apps.opportunities.checks.http import SafeHttpResult
from apps.opportunities.checks.unitree import UNITREE_ADAPTER


class _Client:
    def get(self, url, **limits):
        assert url == "https://www.unitree.com/cn/position"
        assert limits["max_response_bytes"] == 262_144
        return SafeHttpResult(
            status=200,
            final_url=url,
            title="招贤纳士 - 宇树科技",
            body=b"""
                <a href="/cn/position/2060189838933491712" class="link">
                  <p class="title">Robot Data Engineer <span>Hot</span></p>
                  <p class="base-info">Hangzhou | Engineering | R&amp;D</p>
                  <div class="duty"><p>Open role.</p></div>
                </a>
            """,
            truncated=False,
        )


def test_unitree_adapter_collects_server_rendered_positions():
    result = UNITREE_ADAPTER.collect(
        source_url="https://www.unitree.com/cn/position",
        config={"_max_opportunities": 100},
        client=_Client(),
        initial_response=SafeHttpResult(
            200, "https://www.unitree.com/sitemap.xml", "", b"", False
        ),
        heartbeat=lambda: None,
    )

    assert len(result.opportunities) == 1
    item = result.opportunities[0]
    assert item.title == "Robot Data Engineer"
    assert item.target_url.endswith("/2060189838933491712")
    assert item.location_text == "Hangzhou"
    assert item.category_labels == ("Engineering",)
    assert item.city_labels == ("Hangzhou",)
