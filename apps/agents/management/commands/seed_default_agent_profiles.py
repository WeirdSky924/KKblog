from django.core.management.base import BaseCommand, CommandError

from apps.agents.defaults import DEFAULT_AGENT_PROMPTS, default_agent_purpose
from apps.agents.models import AgentEndpoint, AgentProfile
from apps.agents.services import (
    ProfileDraft,
    create_agent_profile,
    save_agent_prompt_revision,
)
from apps.core.observability.trace import new_trace_code


class Command(BaseCommand):
    help = "Create the built-in knowledge review, question generation, and article explanation AGENT profiles for an endpoint."

    def add_arguments(self, parser):
        parser.add_argument("--endpoint-id", required=True)
        parser.add_argument("--admin-id", required=True)

    def handle(self, *args, **options):
        endpoint_id = options["endpoint_id"]
        admin_id = options["admin_id"]
        try:
            endpoint = AgentEndpoint.objects.get(pk=endpoint_id)
        except (AgentEndpoint.DoesNotExist, TypeError, ValueError):
            raise CommandError("Endpoint does not exist") from None
        created = []
        repaired = []
        for key, prompt in DEFAULT_AGENT_PROMPTS.items():
            purpose = default_agent_purpose(key)
            schema_key = f"{key}.v1"
            profile = AgentProfile.objects.filter(key=key).first()
            if profile is None:
                profile = create_agent_profile(
                    actor_id=admin_id,
                    draft=ProfileDraft(
                        key=key,
                        display_name=(
                            "知识文档审核"
                            if key == "knowledge-review"
                            else "题库生成"
                            if key == "question-generation"
                            else "文章划词解释"
                        ),
                        purpose=purpose,
                        endpoint_id=endpoint.id,
                        schema_key=schema_key,
                    ),
                    trace_code=new_trace_code(),
                    client_ip="127.0.0.1",
                )
                created.append(key)
            elif (
                profile.endpoint_id != endpoint.id
                or profile.purpose != purpose
                or profile.schema_key != schema_key
            ):
                raise CommandError(f"Existing {key} profile conflicts with defaults")
            if profile.current_prompt_id is not None:
                continue
            save_agent_prompt_revision(
                actor_id=admin_id,
                profile_id=profile.id,
                markdown_source=prompt,
                expected_profile_version=profile.row_version,
                trace_code=new_trace_code(),
                client_ip="127.0.0.1",
            )
            if key not in created:
                repaired.append(key)
        self.stdout.write(
            self.style.SUCCESS(
                f"created={','.join(created) or 'none'} "
                f"repaired={','.join(repaired) or 'none'}"
            )
        )
