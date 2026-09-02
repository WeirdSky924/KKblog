import pytest

from apps.agents.providers.http import (
    ProviderHttpRequest,
    ProviderHttpResponse,
    ProviderNetworkPolicy,
    ProviderTransportError,
    SafeProviderHttpClient,
)

PUBLIC_ADDRESS = "93.184.216.34"


def _resolver(address=PUBLIC_ADDRESS):
    return lambda _hostname, _port: (address,)


def _response(body=b"{}", *, status=200, headers=None):
    return ProviderHttpResponse(status=status, headers=headers or {}, body=body)


@pytest.mark.parametrize(
    "url",
    (
        "https://user:password@api.example.com/v1",
        "https://api.example.com/v1?token=unsafe",
        "https://api.example.com/v1#fragment",
        "ftp://api.example.com/v1",
        "https://api.example.com:0/v1",
    ),
)
def test_provider_url_rejects_credentials_and_invalid_shapes(url: str) -> None:
    policy = ProviderNetworkPolicy()
    with pytest.raises(ProviderTransportError) as rejected:
        policy.resolve(url, resolver=_resolver())
    assert rejected.value.code == "agents.endpoint_rejected.v1"


def test_public_https_is_allowed_but_public_http_is_denied() -> None:
    policy = ProviderNetworkPolicy()
    target = policy.resolve(
        "https://api.example.com/v1", resolver=_resolver(PUBLIC_ADDRESS)
    )
    assert target.hostname == "api.example.com"
    assert target.address == PUBLIC_ADDRESS
    assert target.port == 443

    with pytest.raises(ProviderTransportError) as rejected:
        policy.resolve("http://api.example.com/v1", resolver=_resolver(PUBLIC_ADDRESS))
    assert rejected.value.code == "agents.endpoint_https_required.v1"


def test_private_http_requires_exact_server_allowlist() -> None:
    denied = ProviderNetworkPolicy()
    with pytest.raises(ProviderTransportError) as rejected:
        denied.resolve("http://localhost:11434/v1", resolver=_resolver("127.0.0.1"))
    assert rejected.value.code == "agents.endpoint_address_denied.v1"

    allowed = ProviderNetworkPolicy(internal_allowlist=("localhost:11434",))
    target = allowed.resolve(
        "http://localhost:11434/v1", resolver=_resolver("127.0.0.1")
    )
    assert target.address == "127.0.0.1"
    assert target.authority == "localhost:11434"


@pytest.mark.parametrize("address", ("169.254.169.254", "100.100.100.200"))
def test_metadata_addresses_are_always_denied_even_when_allowlisted(
    address: str,
) -> None:
    policy = ProviderNetworkPolicy(internal_allowlist=(f"{address}:80",))
    with pytest.raises(ProviderTransportError) as rejected:
        policy.resolve(f"http://{address}:80/v1", resolver=_resolver(address))
    assert rejected.value.code == "agents.endpoint_address_denied.v1"


def test_dns_rebinding_is_rechecked_before_following_redirect() -> None:
    calls = 0

    def resolver(_hostname, _port):
        nonlocal calls
        calls += 1
        return (PUBLIC_ADDRESS,) if calls == 1 else ("127.0.0.1",)

    transport_calls = []

    def transport(request):
        transport_calls.append(request)
        return _response(status=307, headers={"location": "/v1/retry"})

    client = SafeProviderHttpClient(
        policy=ProviderNetworkPolicy(), resolver=resolver, transport=transport
    )
    with pytest.raises(ProviderTransportError) as rejected:
        client.post_json(
            "https://api.example.com/v1/messages",
            {"value": 1},
            timeout_seconds=10,
            max_response_bytes=1024,
            max_redirects=1,
        )
    assert rejected.value.code == "agents.endpoint_address_denied.v1"
    assert len(transport_calls) == 1


def test_redirect_cannot_move_authorization_to_another_authority() -> None:
    def transport(_request):
        return _response(
            status=302, headers={"location": "https://other.example.com/v1"}
        )

    client = SafeProviderHttpClient(
        policy=ProviderNetworkPolicy(),
        resolver=_resolver(),
        transport=transport,
    )
    with pytest.raises(ProviderTransportError) as rejected:
        client.post_json(
            "https://api.example.com/v1/chat/completions",
            {"value": 1},
            headers={"Authorization": "Bearer should-not-leak"},
            timeout_seconds=10,
            max_response_bytes=1024,
            max_redirects=1,
        )
    assert rejected.value.code == "agents.redirect_authority_denied.v1"


def test_slow_and_oversized_responses_fail_closed() -> None:
    clock = [0.0]

    def monotonic():
        return clock[0]

    def slow_transport(_request):
        clock[0] = 6.0
        return _response()

    slow_client = SafeProviderHttpClient(
        policy=ProviderNetworkPolicy(),
        resolver=_resolver(),
        transport=slow_transport,
        monotonic=monotonic,
    )
    with pytest.raises(ProviderTransportError) as timed_out:
        slow_client.post_json(
            "https://api.example.com/v1/messages",
            {},
            timeout_seconds=5,
            max_response_bytes=1024,
        )
    assert timed_out.value.code == "agents.request_timeout.v1"

    large_client = SafeProviderHttpClient(
        policy=ProviderNetworkPolicy(),
        resolver=_resolver(),
        transport=lambda _request: _response(b"x" * 1025),
    )
    with pytest.raises(ProviderTransportError) as too_large:
        large_client.post_json(
            "https://api.example.com/v1/messages",
            {},
            timeout_seconds=5,
            max_response_bytes=1024,
        )
    assert too_large.value.code == "agents.response_too_large.v1"


def test_provider_read_timeout_honors_endpoint_budget_above_thirty_seconds() -> None:
    requests = []

    def transport(request):
        requests.append(request)
        return _response()

    client = SafeProviderHttpClient(
        policy=ProviderNetworkPolicy(),
        resolver=_resolver(),
        transport=transport,
    )
    client.post_json(
        "https://api.example.com/v1/chat/completions",
        {},
        timeout_seconds=120,
        max_response_bytes=1024,
    )
    assert requests[0].read_timeout_seconds == 120


def test_transport_request_repr_redacts_headers_and_body() -> None:
    request = ProviderHttpRequest(
        url="https://api.example.com/v1",
        hostname="api.example.com",
        address=PUBLIC_ADDRESS,
        port=443,
        target="/v1",
        connect_timeout_seconds=5,
        read_timeout_seconds=10,
        max_response_bytes=1024,
        headers={"Authorization": "Bearer top-secret"},
        body=b'{"private":"content"}',
    )
    rendered = repr(request)
    assert "top-secret" not in rendered
    assert "private" not in rendered
