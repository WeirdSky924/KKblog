from uuid import uuid4

import pytest
from django.core.management import call_command

from apps.accounts.models import Account, RoleAssignment
from apps.agents.contracts import EndpointRuntimeSettings
from apps.agents.models import AgentEndpoint, AgentProfile, AgentPromptRevision
from apps.agents.public import EndpointDraft, create_agent_endpoint
from apps.core.observability.trace import new_trace_code

pytestmark = pytest.mark.django_db(transaction=True)


def test_seed_default_profiles_creates_prompts_idempotently() -> None:
    admin = Account.objects.create_account(
        email=f"seed-agent-{uuid4()}@kaj.test",
        password="Valid-password-1",
    )
    RoleAssignment.objects.create(
        account=admin,
        role=RoleAssignment.Role.ADMINISTRATOR,
    )
    endpoint = create_agent_endpoint(
        actor_id=admin.id,
        draft=EndpointDraft(
            display_name=f"Seed endpoint {uuid4()}",
            protocol=AgentEndpoint.Protocol.OPENAI_GPT,
            base_url="https://api.example.com/v1",
            model_name="seed-model",
            authentication_mode=AgentEndpoint.AuthenticationMode.NONE,
            enabled=True,
            runtime=EndpointRuntimeSettings(),
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )

    call_command(
        "seed_default_agent_profiles",
        endpoint_id=endpoint.id,
        admin_id=admin.id,
    )

    profiles = tuple(
        AgentProfile.objects.select_related("current_prompt")
        .filter(key__in=("knowledge-review", "question-generation"))
        .order_by("key")
    )
    assert tuple(profile.key for profile in profiles) == (
        "knowledge-review",
        "question-generation",
    )
    assert tuple(profile.schema_key for profile in profiles) == (
        "knowledge-review.v1",
        "question-generation.v1",
    )
    assert all(not profile.enabled for profile in profiles)
    assert all(profile.current_prompt is not None for profile in profiles)
    assert all(profile.current_prompt.sequence == 1 for profile in profiles)
    assert all(
        f"{profile.schema_key} schema" in profile.current_prompt.markdown_source
        for profile in profiles
    )

    call_command(
        "seed_default_agent_profiles",
        endpoint_id=endpoint.id,
        admin_id=admin.id,
    )
    assert (
        AgentProfile.objects.filter(
            key__in=("knowledge-review", "question-generation")
        ).count()
        == 2
    )
    assert (
        AgentPromptRevision.objects.filter(
            profile__key__in=("knowledge-review", "question-generation")
        ).count()
        == 2
    )
