import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEPLOY = PROJECT_ROOT / "docker/scripts/deploy"


def run_deploy(
    *arguments: str, state_root: Path
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
    result = subprocess.run(
        [str(DEPLOY), *arguments, "--state-root", str(state_root)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    events = [json.loads(line) for line in result.stdout.splitlines() if line]
    return result, events


def event_steps(events: list[dict[str, object]]) -> list[str]:
    return [str(event["step"]) for event in events if event["step"] != "deployment"]


def test_dry_run_skips_backup_and_migrate_when_schema_is_current(
    tmp_path: Path,
) -> None:
    result, events = run_deploy(
        "--dry-run",
        "--migration-state",
        "current",
        "--deployment-id",
        "run006-current",
        state_root=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert event_steps(events) == [
        "build_candidate",
        "detect_migrations",
        "enable_maintenance",
        "switch_candidate",
        "check_candidate_health",
        "disable_maintenance",
        "record_success",
    ]
    assert all(event["outcome"] == "planned" for event in events)
    assert list(tmp_path.iterdir()) == []


def test_pending_migration_requires_backup_before_maintenance_and_migrate(
    tmp_path: Path,
) -> None:
    result, events = run_deploy(
        "--simulate",
        "success-pending",
        "--deployment-id",
        "run006-pending",
        state_root=tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert event_steps(events) == [
        "build_candidate",
        "detect_migrations",
        "create_backup",
        "enable_maintenance",
        "apply_migrations",
        "switch_candidate",
        "check_candidate_health",
        "disable_maintenance",
        "record_success",
    ]
    state = json.loads((tmp_path / "run006-pending.json").read_text(encoding="utf-8"))
    assert state["status"] == "succeeded"
    assert state["maintenance_enabled"] is False


def test_same_deployment_id_is_idempotent_after_success(tmp_path: Path) -> None:
    first, _ = run_deploy(
        "--simulate",
        "success-pending",
        "--deployment-id",
        "run006-idempotent",
        state_root=tmp_path,
    )
    second, events = run_deploy(
        "--simulate",
        "success-pending",
        "--deployment-id",
        "run006-idempotent",
        state_root=tmp_path,
    )

    assert first.returncode == 0
    assert second.returncode == 0
    assert event_steps(events) == []
    assert events[-1]["outcome"] == "already_succeeded"


def test_migration_failure_keeps_previous_application_and_exits_30(
    tmp_path: Path,
) -> None:
    result, events = run_deploy(
        "--simulate",
        "migration-failure",
        "--deployment-id",
        "run006-migration-failure",
        state_root=tmp_path,
    )

    assert result.returncode == 30
    steps = event_steps(events)
    assert steps[:5] == [
        "build_candidate",
        "detect_migrations",
        "create_backup",
        "enable_maintenance",
        "apply_migrations",
    ]
    assert "switch_candidate" not in steps
    assert steps[-3:] == [
        "check_previous_health",
        "disable_maintenance",
        "record_failure",
    ]
    state = json.loads(
        (tmp_path / "run006-migration-failure.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "migration_failed"
    assert state["candidate_switched"] is False
    assert state["maintenance_enabled"] is False


def test_health_failure_restores_previous_app_without_database_rollback(
    tmp_path: Path,
) -> None:
    result, events = run_deploy(
        "--simulate",
        "health-failure",
        "--deployment-id",
        "run006-health-failure",
        state_root=tmp_path,
    )

    assert result.returncode == 40
    steps = event_steps(events)
    assert steps[-4:] == [
        "restore_previous",
        "check_previous_health",
        "disable_maintenance",
        "record_failure",
    ]
    assert not any("rollback_migration" in step for step in steps)
    state = json.loads(
        (tmp_path / "run006-health-failure.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "rolled_back"
    assert state["candidate_switched"] is False
    assert state["maintenance_enabled"] is False


def test_unhealthy_previous_app_keeps_maintenance_enabled(tmp_path: Path) -> None:
    result, events = run_deploy(
        "--simulate",
        "rollback-health-failure",
        "--deployment-id",
        "run006-rollback-health-failure",
        state_root=tmp_path,
    )

    assert result.returncode == 50
    assert "disable_maintenance" not in event_steps(events)
    state = json.loads(
        (tmp_path / "run006-rollback-health-failure.json").read_text(encoding="utf-8")
    )
    assert state["status"] == "rollback_unhealthy"
    assert state["maintenance_enabled"] is True


def test_deployment_id_cannot_escape_state_root(tmp_path: Path) -> None:
    result, events = run_deploy(
        "--simulate",
        "success-current",
        "--deployment-id",
        "../escape",
        state_root=tmp_path,
    )

    assert result.returncode == 64
    assert events == []
    assert not (tmp_path.parent / "escape.json").exists()
