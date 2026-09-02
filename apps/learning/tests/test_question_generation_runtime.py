import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from django.apps import apps
from django.db import transaction
from django.utils import timezone

from apps.agents.contracts import EndpointRuntimeSettings
from apps.agents.models import (
    AgentEndpointCheck,
    AgentInvocation,
    AgentSitePolicy,
    AgentTokenLedger,
)
from apps.agents.public import (
    EndpointDraft,
    ProfileDraft,
    SchemaValidationError,
    create_agent_endpoint,
    create_agent_profile,
    save_agent_prompt_revision,
    set_agent_profile_enabled,
    structured_schema,
)
from apps.core.events.models import OutboxEvent
from apps.core.events.outbox import envelope_from_model
from apps.core.ids import new_ulid
from apps.core.observability.trace import new_trace_code
from apps.learning.public import (
    QUESTION_GENERATION_PROFILE_KEY,
    QUESTION_GENERATION_SCHEMA_KEY,
    GenerationQuestionTypes,
    LearningCommandError,
    LearningModelRunKind,
    QuestionBankCoverageState,
    QuestionBankSeriesState,
    configure_question_generation_limit,
    create_question_bank_generation_request,
    dispatch_pending_question_bank_generations,
    execute_question_bank_generation,
    release_learning_model_run,
    reserve_learning_model_run,
)
from apps.notifications.public import consume_domain_notification
from apps.operations.public import RetryableTaskError, TaskFinalFailed

from .test_account_documents_backend import _administrator, _approved
from .test_documents_lifecycle import _account
from .test_review_runtime import _gateway

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)


def _mark_schema_capability(administrator, endpoint, schema_key):
    return AgentEndpointCheck.objects.create(
        endpoint=endpoint,
        requested_by_id=administrator.id,
        idempotency_key=f"test-capability:{uuid4()}",
        state=AgentEndpointCheck.State.SUCCEEDED,
        endpoint_row_version_snapshot=endpoint.row_version,
        protocol_snapshot=endpoint.protocol,
        base_url_snapshot=endpoint.base_url,
        model_name_snapshot=endpoint.model_name,
        schema_key_snapshot=schema_key,
        capability_strategy="native",
        capability_state="SCHEMA_SUPPORTED",
        authentication_mode_snapshot=endpoint.authentication_mode,
        secret_alias_snapshot=endpoint.secret_alias,
        api_key_ciphertext_snapshot=endpoint.api_key_ciphertext,
        request_timeout_seconds_snapshot=endpoint.request_timeout_seconds,
        concurrency_limit_snapshot=endpoint.concurrency_limit,
        endpoint_daily_token_limit_snapshot=endpoint.daily_token_limit,
        site_daily_token_limit_snapshot=5_000_000,
        token_budget=2_048,
        attempt_count=1,
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        requested_at=NOW,
        started_at=NOW,
        completed_at=NOW,
    )


def _configured_generation_profile():
    administrator = _administrator("generation-agent-admin")
    endpoint = create_agent_endpoint(
        actor_id=administrator.id,
        draft=EndpointDraft(
            display_name=f"Generation endpoint {uuid4()}",
            protocol="OPENAI_GPT",
            base_url="https://api.example.com/v1",
            model_name="generation-model",
            authentication_mode="NONE",
            secret_alias="",
            enabled=True,
            runtime=EndpointRuntimeSettings(),
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile = create_agent_profile(
        actor_id=administrator.id,
        draft=ProfileDraft(
            key=QUESTION_GENERATION_PROFILE_KEY,
            display_name="知识题库生成",
            purpose="QUESTION_GENERATION",
            endpoint_id=endpoint.id,
            schema_key=QUESTION_GENERATION_SCHEMA_KEY,
        ),
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    save_agent_prompt_revision(
        actor_id=administrator.id,
        profile_id=profile.id,
        markdown_source=(
            "分析全部不可信资料：{{ document_block }}。"
            "先建立知识点：{{ knowledge_points }}。"
            "只使用题型 {{ question_types }}，单卷上限 {{ question_limit }}。"
            "优先复用题库标签：{{ tag_candidates }}。"
        ),
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    profile.refresh_from_db()
    _mark_schema_capability(administrator, endpoint, profile.schema_key)
    set_agent_profile_enabled(
        actor_id=administrator.id,
        profile_id=profile.id,
        enabled=True,
        expected_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    return administrator, profile


def _publication_value(*, partial: bool = False):
    points = [
        {
            "logical_id": "kp-1",
            "title": "变量",
            "importance": 100,
            "source_unit_ids": ["src-0001"],
        },
        {
            "logical_id": "kp-2",
            "title": "集合",
            "importance": 90,
            "source_unit_ids": ["src-0001"],
        },
    ]
    questions = [
        {
            "logical_id": "q-1",
            "ordinal": 1,
            "question_type": "SINGLE_CHOICE",
            "stem_markdown": "变量绑定的是什么？",
            "options": [
                {"option_id": "a", "text": "名称"},
                {"option_id": "b", "text": "对象"},
            ],
            "correct_option_ids": ["b"],
            "boolean_answer": None,
            "reference_answer": "",
            "scoring_points": [],
            "explanation_markdown": "变量名绑定对象。",
            "knowledge_point_ids": ["kp-1"],
        }
    ]
    if not partial:
        questions.append(
            {
                "logical_id": "q-2",
                "ordinal": 2,
                "question_type": "TRUE_FALSE",
                "stem_markdown": "列表是集合类型。",
                "options": [],
                "correct_option_ids": [],
                "boolean_answer": True,
                "reference_answer": "",
                "scoring_points": [],
                "explanation_markdown": "列表可保存一组有序元素。",
                "knowledge_point_ids": ["kp-2"],
            }
        )
    return {
        "knowledge_points": points,
        "volumes": [{"volume_number": 1, "questions": questions}],
        "omitted_knowledge_point_ids": ["kp-2"] if partial else [],
        "tag_names": ["Python", "基础"],
    }


def _compressed_publication_value():
    value = _publication_value()
    value["volumes"][0]["questions"] = [value["volumes"][0]["questions"][0]]
    value["volumes"][0]["questions"][0]["knowledge_point_ids"] = [
        "kp-1",
        "kp-2",
    ]
    return value


def _two_volume_publication_value():
    value = _publication_value()
    questions = value["volumes"][0]["questions"]
    questions[1]["ordinal"] = 1
    value["volumes"] = [
        {"volume_number": 1, "questions": [questions[0]]},
        {"volume_number": 2, "questions": [questions[1]]},
    ]
    return value


def _request(root, owner, *, dispatcher=lambda _series_id: None, key=None):
    document, _, storage = _approved(
        root,
        owner,
        key=f"document:{key or uuid4()}",
    )
    result = create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title="Python 基础",
        description="从知识文档生成的题库。",
        question_types=GenerationQuestionTypes(
            single_choice=True,
            true_false=True,
        ),
        idempotency_key=f"generation:{key or uuid4()}",
        dispatcher=dispatcher,
        now=NOW,
    )
    return result, document, storage


def _configure_limit(value: int = 4, *, administrator=None):
    administrator = administrator or _administrator(f"generation-limit-{value}")
    return configure_question_generation_limit(
        actor_id=administrator.id,
        expected_version=1,
        max_questions_per_volume=value,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )


def test_generation_schema_is_fixed_and_rejects_extra_fields() -> None:
    schema = structured_schema(QUESTION_GENERATION_SCHEMA_KEY)
    value = _publication_value()
    assert schema.validate(value) == value
    with pytest.raises(SchemaValidationError):
        schema.validate({**value, "raw_document": "must not leak"})


def test_missing_admin_question_limit_fails_closed_without_counting(
    isolated_media_root,
) -> None:
    owner = _account("generation-limit-missing")
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-limit-missing",
    )
    with pytest.raises(LearningCommandError) as captured:
        create_question_bank_generation_request(
            owner_id=owner.id,
            document_id=document.document_id,
            base_title="未配置上限",
            description="",
            question_types=GenerationQuestionTypes(single_choice=True),
            idempotency_key="generation:limit-missing",
            dispatcher=lambda _series_id: None,
            now=NOW,
        )
    assert captured.value.code == "learning.generation_not_configured.v1"
    assert not apps.get_model("learning", "QuestionBankSeries").objects.exists()
    usage = apps.get_model("learning", "LearningDailyUsage").objects.get(account=owner)
    assert usage.generations_accepted == 0


def test_missing_generation_agent_fails_request_without_counting_or_dispatch(
    isolated_media_root,
) -> None:
    _configure_limit(4)
    owner = _account("generation-agent-missing")
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-agent-missing",
    )
    calls = []

    with pytest.raises(LearningCommandError) as captured:
        create_question_bank_generation_request(
            owner_id=owner.id,
            document_id=document.document_id,
            base_title="缺少生成 AGENT",
            description="",
            question_types=GenerationQuestionTypes(single_choice=True),
            idempotency_key="generation:agent-missing",
            dispatcher=lambda series_id: calls.append(series_id),
            now=NOW,
        )

    assert captured.value.code == "agents.profile_unavailable.v1"
    assert calls == []
    assert not apps.get_model("learning", "QuestionBankSeries").objects.exists()
    usage = apps.get_model("learning", "LearningDailyUsage").objects.get(account=owner)
    assert usage.generations_accepted == 0
    assert not AgentInvocation.objects.filter(
        caller_type="question_generation"
    ).exists()


def test_generation_request_dispatches_after_commit_and_snapshots_admin_limit(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(6, administrator=administrator)
    owner = _account("generation-dispatch")
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-dispatch",
    )
    calls = []
    with transaction.atomic():
        result = create_question_bank_generation_request(
            owner_id=owner.id,
            document_id=document.document_id,
            base_title="Python 基础",
            description="",
            question_types=GenerationQuestionTypes(single_choice=True),
            idempotency_key="generation:dispatch",
            dispatcher=lambda series_id: calls.append(series_id),
            now=NOW,
        )
        assert calls == []
    assert calls == [str(result.series_id)]
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=result.series_id
    )
    assert series.max_questions_per_volume_snapshot == 6
    assert series.dispatch_required is False
    assert series.dispatched_at is not None


def test_generation_dispatch_failure_is_recovered_by_bounded_pending_scan(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-dispatch-recovery")
    document, _, _ = _approved(
        isolated_media_root,
        owner,
        key="document:generation-dispatch-recovery",
    )

    def unavailable(_series_id):
        raise OSError("private broker detail")

    request = create_question_bank_generation_request(
        owner_id=owner.id,
        document_id=document.document_id,
        base_title="待补偿派发",
        description="",
        question_types=GenerationQuestionTypes(single_choice=True),
        idempotency_key="generation:dispatch-recovery",
        dispatcher=unavailable,
        now=NOW,
    )
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert series.dispatch_required is True
    assert series.dispatch_attempted_at == NOW
    calls = []

    dispatched = dispatch_pending_question_bank_generations(
        batch_size=10,
        dispatcher=lambda series_id: calls.append(series_id),
        now=NOW + timedelta(minutes=1),
    )

    series.refresh_from_db()
    assert dispatched == (series.id,)
    assert calls == [str(series.id)]
    assert series.dispatch_required is False
    assert series.dispatched_at == NOW + timedelta(minutes=1)


def test_generation_runtime_publishes_complete_bank_and_snapshots_invocation(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-runtime")
    request, document, storage = _request(
        isolated_media_root,
        owner,
        key="runtime-complete",
    )
    gateway, transport = _gateway(_publication_value())

    result = execute_question_bank_generation(
        series_id=request.series_id,
        task_run_id=new_ulid(),
        gateway=gateway,
        renew_lease=lambda: None,
        storage=storage,
        now=NOW,
    )

    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    invocation = AgentInvocation.objects.get(pk=series.latest_invocation_id)
    assert result.coverage_state == QuestionBankCoverageState.COMPLETE
    assert result.volume_count == 1
    assert series.state == "PUBLISHED"
    assert series.source_document_id == document.document_id
    assert series.input_content_sha256 == series.source_document.content_sha256
    assert invocation.profile_key_snapshot == QUESTION_GENERATION_PROFILE_KEY
    assert invocation.schema_key_snapshot == QUESTION_GENERATION_SCHEMA_KEY
    assert invocation.model_name_snapshot == "generation-model"
    assert transport.call_count == 1
    assert (
        OutboxEvent.objects.filter(
            event_type="learning.generation_completed.v1",
            aggregate_id=str(series.id),
        ).count()
        == 1
    )
    assert (
        not apps.get_model("learning", "LearningModelRunReservation")
        .objects.filter(status="ACTIVE")
        .exists()
    )
    assert json.loads(json.dumps(_publication_value())) == _publication_value()


def test_admin_profile_changes_after_request_do_not_drift_generation_snapshot(
    isolated_media_root,
) -> None:
    administrator, profile = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-snapshot-stable")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="snapshot-stable",
    )
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    snapshot = AgentInvocation.objects.get(pk=series.generation_snapshot_invocation_id)
    assert snapshot.model_name_snapshot == "generation-model"
    assert snapshot.prompt_sequence_snapshot == 1

    endpoint = profile.endpoint
    endpoint.model_name = "changed-after-request"
    endpoint.row_version += 1
    endpoint.save()
    _mark_schema_capability(administrator, endpoint, profile.schema_key)
    profile.refresh_from_db()
    save_agent_prompt_revision(
        actor_id=administrator.id,
        profile_id=profile.id,
        markdown_source=(
            "新的 Prompt {{ document_block }} {{ knowledge_points }} "
            "{{ question_types }} {{ question_limit }} {{ tag_candidates }}"
        ),
        expected_profile_version=profile.row_version,
        trace_code=new_trace_code(),
        client_ip="127.0.0.1",
    )
    gateway, _ = _gateway(_publication_value())

    execute_question_bank_generation(
        series_id=request.series_id,
        task_run_id=new_ulid(),
        gateway=gateway,
        renew_lease=lambda: None,
        storage=storage,
        now=NOW,
    )

    series.refresh_from_db()
    invocation = AgentInvocation.objects.get(pk=series.latest_invocation_id)
    assert invocation.id == snapshot.id
    assert invocation.model_name_snapshot == "generation-model"
    assert invocation.prompt_sequence_snapshot == 1


@pytest.mark.parametrize(
    ("value_factory", "limit", "coverage", "volumes", "event_type"),
    (
        (
            _compressed_publication_value,
            1,
            QuestionBankCoverageState.COMPLETE,
            1,
            "learning.generation_completed.v1",
        ),
        (
            _two_volume_publication_value,
            1,
            QuestionBankCoverageState.COMPLETE,
            2,
            "learning.generation_completed.v1",
        ),
        (
            lambda: _publication_value(partial=True),
            1,
            QuestionBankCoverageState.PARTIAL,
            1,
            "learning.generation_partial.v1",
        ),
    ),
)
def test_generation_capacity_results_are_explicit_and_atomic(
    isolated_media_root,
    value_factory,
    limit,
    coverage,
    volumes,
    event_type,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(limit, administrator=administrator)
    owner = _account(f"generation-capacity-{coverage}-{volumes}")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key=f"capacity-{coverage}-{volumes}",
    )
    gateway, transport = _gateway(value_factory())

    result = execute_question_bank_generation(
        series_id=request.series_id,
        task_run_id=new_ulid(),
        gateway=gateway,
        renew_lease=lambda: None,
        storage=storage,
        now=NOW,
    )

    assert result.coverage_state == coverage
    assert result.volume_count == volumes
    assert transport.call_count == 1
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert series.banks.count() == volumes
    assert series.reserved_bank_slots == volumes
    event = OutboxEvent.objects.get(
        event_type=event_type,
        aggregate_id=str(series.id),
    )
    consume_domain_notification(envelope_from_model(event))
    consume_domain_notification(envelope_from_model(event))
    receipt_model = apps.get_model("notifications", "NotificationReceipt")
    assert receipt_model.objects.filter(recipient=owner).count() == 1


def test_bad_schema_retries_without_publishing_or_capacity_fallback(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(1, administrator=administrator)
    owner = _account("generation-bad-schema")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="bad-schema",
    )
    invalid = {**_publication_value(), "unexpected": "not allowed"}
    gateway, transport = _gateway(invalid)

    with pytest.raises(RetryableTaskError):
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )

    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert series.state == "GENERATING"
    assert series.banks.count() == 0
    assert series.knowledge_points.count() == 0
    assert series.tag_assignments.count() == 0
    assert series.last_error_code
    assert transport.call_count >= 1


def test_generation_rejects_question_type_not_selected_by_owner(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(1, administrator=administrator)
    owner = _account("generation-disabled-type")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="disabled-type",
    )
    invalid = _compressed_publication_value()
    question = invalid["volumes"][0]["questions"][0]
    question.update(
        question_type="SHORT_ANSWER",
        options=[],
        correct_option_ids=[],
        boolean_answer=None,
        reference_answer="变量名绑定对象。",
        scoring_points=["说明名称与对象的关系"],
    )
    gateway, transport = _gateway(invalid)

    with pytest.raises(RetryableTaskError) as captured:
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )

    assert captured.value.error_code == "agents.response_semantics_invalid.v1"
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert series.banks.count() == 0
    assert transport.call_count == 2


def test_business_concurrency_blocks_generation_before_provider_call(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-business-quota")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="business-quota",
    )
    blocker_ref = str(uuid4())
    blocker = reserve_learning_model_run(
        account_id=owner.id,
        kind=LearningModelRunKind.REVIEW,
        owner_ref=blocker_ref,
        idempotency_key=f"generation-blocker:{blocker_ref}",
        lease_expires_at=NOW + timedelta(hours=1),
        now=NOW,
    )
    gateway, transport = _gateway(_publication_value())

    with pytest.raises(RetryableTaskError) as captured:
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )
    assert captured.value.error_code == "learning.concurrent_quota_exhausted.v1"
    assert transport.call_count == 0
    invocations = AgentInvocation.objects.filter(caller_type="question_generation")
    assert invocations.count() == 1
    snapshot = invocations.get()
    assert snapshot.state == "PENDING" and snapshot.task_run_id == ""
    release_learning_model_run(reservation_id=blocker.reservation_id)


def test_revoked_attachment_capability_blocks_generation_before_provider_call(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-capability-revoked")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="capability-revoked",
    )
    owner.attachment_upload_enabled = False
    owner.save(update_fields=("attachment_upload_enabled", "updated_at"))
    gateway, transport = _gateway(_publication_value())

    with pytest.raises(RetryableTaskError) as captured:
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )

    assert captured.value.error_code == "learning.attachment_capability_required.v1"
    assert transport.call_count == 0
    series = apps.get_model("learning", "QuestionBankSeries").objects.get(
        pk=request.series_id
    )
    assert series.state == QuestionBankSeriesState.GENERATION_PENDING
    assert series.attempt_count == 0


def test_agent_token_quota_blocks_generation_before_provider_call(
    isolated_media_root,
) -> None:
    administrator, profile = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    endpoint = profile.endpoint
    endpoint.per_run_token_limit = 10_000
    endpoint.daily_token_limit = 50_000
    endpoint.row_version += 1
    endpoint.save()
    _mark_schema_capability(administrator, endpoint, profile.schema_key)
    policy = AgentSitePolicy.objects.get(pk=1)
    policy.daily_token_limit = 100_000
    policy.row_version += 1
    policy.save()
    ledger_date = timezone.localdate(NOW)
    AgentTokenLedger.objects.create(
        scope="SITE",
        usage_date=ledger_date,
        settled_tokens=50_000,
    )
    AgentTokenLedger.objects.create(
        scope="ENDPOINT",
        endpoint=endpoint,
        usage_date=ledger_date,
        settled_tokens=50_000,
    )
    owner = _account("generation-token-quota")
    request, _, storage = _request(
        isolated_media_root,
        owner,
        key="token-quota",
    )
    gateway, transport = _gateway(_publication_value())

    with pytest.raises(TaskFinalFailed) as captured:
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )
    assert captured.value.error_code == "agents.quota_exhausted.v1"
    assert transport.call_count == 0


def test_same_approved_document_generates_independent_series_without_overwrite(
    isolated_media_root,
) -> None:
    administrator, _ = _configured_generation_profile()
    _configure_limit(4, administrator=administrator)
    owner = _account("generation-same-document")
    document, _, storage = _approved(
        isolated_media_root,
        owner,
        key="document:generation-same-document",
    )
    requests = tuple(
        create_question_bank_generation_request(
            owner_id=owner.id,
            document_id=document.document_id,
            base_title=f"独立题库 {index}",
            description="",
            question_types=GenerationQuestionTypes(
                single_choice=True,
                true_false=True,
            ),
            idempotency_key=f"generation:same-document:{index}",
            dispatcher=lambda _series_id: None,
            now=NOW,
        )
        for index in (1, 2)
    )

    for request in requests:
        gateway, _ = _gateway(_publication_value())
        execute_question_bank_generation(
            series_id=request.series_id,
            task_run_id=new_ulid(),
            gateway=gateway,
            renew_lease=lambda: None,
            storage=storage,
            now=NOW,
        )

    series_model = apps.get_model("learning", "QuestionBankSeries")
    assert (
        series_model.objects.filter(
            source_document_id=document.document_id,
            state=QuestionBankSeriesState.PUBLISHED,
        ).count()
        == 2
    )
    assert (
        apps.get_model("learning", "QuestionBank")
        .objects.filter(series_id__in=[request.series_id for request in requests])
        .count()
        == 2
    )
