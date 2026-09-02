import pytest

from config.environment import ConfigurationError, load_agent_provider_environment


def test_agent_provider_environment_loads_only_dedicated_secret_names() -> None:
    environment = load_agent_provider_environment(
        {
            "KAJ_AGENT_SECRET_PRIMARY_GPT": "secret-value-123",
            "KAJ_AGENT_SECRET_CLAUDE_1": "another-secret-456",
            "KAJ_AGENT_INTERNAL_ENDPOINT_ALLOWLIST": (
                "localhost:11434,10.0.0.8:8000,[::1]:9000"
            ),
            "UNRELATED_SECRET": "must-not-load",
        }
    )
    assert set(environment.secrets) == {"PRIMARY_GPT", "CLAUDE_1"}
    assert environment.internal_allowlist == (
        "localhost:11434",
        "10.0.0.8:8000",
        "[::1]:9000",
    )
    rendered = repr(environment)
    assert "secret-value-123" not in rendered
    assert "another-secret-456" not in rendered
    assert "UNRELATED_SECRET" not in environment.secrets


@pytest.mark.parametrize(
    "values",
    (
        {"KAJ_AGENT_SECRET_bad": "secret-value-123"},
        {"KAJ_AGENT_SECRET_PRIMARY": "short"},
        {"KAJ_AGENT_SECRET_PRIMARY": "contains space"},
        {"KAJ_AGENT_INTERNAL_ENDPOINT_ALLOWLIST": "localhost"},
        {"KAJ_AGENT_INTERNAL_ENDPOINT_ALLOWLIST": "*.internal:8000"},
        {"KAJ_AGENT_INTERNAL_ENDPOINT_ALLOWLIST": "localhost:11434/path"},
    ),
)
def test_agent_provider_environment_rejects_unsafe_configuration(values) -> None:
    with pytest.raises(ConfigurationError) as rejected:
        load_agent_provider_environment(values)
    assert "secret-value-123" not in str(rejected.value)
    assert "contains space" not in str(rejected.value)
