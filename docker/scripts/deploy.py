#!/usr/bin/env python3
"""Fail-closed deployment workflow planner and simulator.

This module deliberately has no production command adapter. It makes the deployment
ordering and failure semantics executable without touching services or data.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

USAGE_ERROR = 64
SOFTWARE_ERROR = 70
STATE_IO_ERROR = 74
MIGRATION_FAILURE = 30
CANDIDATE_HEALTH_FAILURE = 40
ROLLBACK_HEALTH_FAILURE = 50
STATE_VERSION = 1
DEPLOYMENT_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


class UsageError(Exception):
    """Raised before any workflow event or state file is created."""


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


@dataclass(frozen=True)
class Scenario:
    migration_state: str
    migration_succeeds: bool = True
    candidate_healthy: bool = True
    previous_healthy: bool = True


SCENARIOS = {
    "success-current": Scenario(migration_state="current"),
    "success-pending": Scenario(migration_state="pending"),
    "migration-failure": Scenario(migration_state="pending", migration_succeeds=False),
    "health-failure": Scenario(migration_state="pending", candidate_healthy=False),
    "rollback-health-failure": Scenario(
        migration_state="pending",
        candidate_healthy=False,
        previous_healthy=False,
    ),
}


@dataclass
class Journal:
    path: Path
    deployment_id: str
    scenario_name: str
    scenario: Scenario
    state: dict[str, object] = field(init=False)

    def __post_init__(self) -> None:
        self.state = {
            "version": STATE_VERSION,
            "deployment_id": self.deployment_id,
            "mode": "simulation",
            "scenario": self.scenario_name,
            "migration_state": self.scenario.migration_state,
            "status": "running",
            "maintenance_enabled": False,
            "candidate_switched": False,
            "database_migrated": False,
            "database_rollback_attempted": False,
            "events": [],
        }

    def record(
        self,
        step: str,
        *,
        outcome: str = "completed",
        exit_code: int = 0,
        updates: dict[str, object] | None = None,
    ) -> None:
        if updates:
            self.state.update(updates)
        event = event_for(
            self.deployment_id,
            step,
            outcome=outcome,
            exit_code=exit_code,
        )
        events = self.state["events"]
        if not isinstance(events, list):
            raise RuntimeError("invalid in-memory deployment journal")
        events.append(event)
        write_atomic_json(self.path, self.state)
        emit(event)


def event_for(
    deployment_id: str,
    step: str,
    *,
    outcome: str,
    exit_code: int,
) -> dict[str, object]:
    return {
        "version": STATE_VERSION,
        "deployment_id": deployment_id,
        "step": step,
        "outcome": outcome,
        "exit_code": exit_code,
    }


def emit(event: dict[str, object]) -> None:
    print(json.dumps(event, ensure_ascii=True, separators=(",", ":")), flush=True)


def write_atomic_json(path: Path, state: dict[str, object]) -> None:
    payload = json.dumps(
        state,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = ArgumentParser(
        description="Plan or simulate the Kaj deployment state machine.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned workflow without creating state or side effects.",
    )
    mode.add_argument(
        "--simulate",
        choices=sorted(SCENARIOS),
        metavar="SCENARIO",
        help="Run a deterministic local simulation and persist its journal.",
    )
    parser.add_argument(
        "--migration-state",
        choices=("current", "pending"),
        help="Required for --dry-run; simulation scenarios define their own state.",
    )
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--state-root", required=True, type=Path)
    parsed = parser.parse_args(arguments)

    if parsed.dry_run and parsed.migration_state is None:
        raise UsageError("--dry-run requires --migration-state")
    if parsed.simulate and parsed.migration_state is not None:
        raise UsageError("--migration-state cannot be combined with --simulate")
    if not DEPLOYMENT_ID_PATTERN.fullmatch(parsed.deployment_id):
        raise UsageError(
            "deployment ID must start with an ASCII letter or digit and contain "
            "only letters, digits, dot, underscore, or hyphen"
        )
    return parsed


def planned_steps(migration_state: str) -> list[str]:
    steps = ["build_candidate", "detect_migrations"]
    if migration_state == "pending":
        steps.append("create_backup")
    steps.append("enable_maintenance")
    if migration_state == "pending":
        steps.append("apply_migrations")
    return [
        *steps,
        "switch_candidate",
        "check_candidate_health",
        "disable_maintenance",
        "record_success",
    ]


def run_dry_run(deployment_id: str, migration_state: str) -> int:
    for step in planned_steps(migration_state):
        emit(
            event_for(
                deployment_id,
                step,
                outcome="planned",
                exit_code=0,
            )
        )
    emit(
        event_for(
            deployment_id,
            "deployment",
            outcome="planned",
            exit_code=0,
        )
    )
    return 0


def checked_state_path(state_root: Path, deployment_id: str) -> Path:
    try:
        state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root = state_root.resolve(strict=True)
    except OSError as error:
        raise UsageError("state root is unavailable") from error
    if not root.is_dir():
        raise UsageError("state root must be a directory")
    path = root / f"{deployment_id}.json"
    try:
        exists = path.exists() or path.is_symlink()
        metadata = path.lstat() if exists else None
    except OSError as error:
        raise UsageError("deployment journal metadata is unavailable") from error
    if metadata is not None:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise UsageError("existing deployment journal must be a regular file")
    return path


def read_terminal_state(path: Path, deployment_id: str) -> tuple[str, int] | None:
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise UsageError("existing deployment journal is unreadable") from error
    if not isinstance(state, dict) or state.get("deployment_id") != deployment_id:
        raise UsageError("existing deployment journal has an invalid identity")

    status = state.get("status")
    terminal_codes = {
        "succeeded": 0,
        "migration_failed": MIGRATION_FAILURE,
        "rolled_back": CANDIDATE_HEALTH_FAILURE,
        "rollback_unhealthy": ROLLBACK_HEALTH_FAILURE,
    }
    if not isinstance(status, str) or status not in terminal_codes:
        raise UsageError("incomplete deployment journal requires manual recovery")
    outcome = "already_succeeded" if status == "succeeded" else "already_failed"
    return outcome, terminal_codes[status]


def finish_failure(
    journal: Journal,
    *,
    status: str,
    exit_code: int,
    previous_healthy: bool,
) -> int:
    health_exit_code = 0 if previous_healthy else ROLLBACK_HEALTH_FAILURE
    journal.record(
        "check_previous_health",
        outcome="completed" if previous_healthy else "failed",
        exit_code=health_exit_code,
    )
    if previous_healthy:
        journal.record(
            "disable_maintenance",
            updates={"maintenance_enabled": False},
        )
    final_status = status if previous_healthy else "rollback_unhealthy"
    final_exit_code = exit_code if previous_healthy else ROLLBACK_HEALTH_FAILURE
    journal.record(
        "record_failure",
        outcome="failed",
        exit_code=final_exit_code,
        updates={"status": final_status},
    )
    emit(
        event_for(
            journal.deployment_id,
            "deployment",
            outcome="failed",
            exit_code=final_exit_code,
        )
    )
    return final_exit_code


def run_simulation(
    state_root: Path,
    deployment_id: str,
    scenario_name: str,
) -> int:
    scenario = SCENARIOS[scenario_name]
    state_path = checked_state_path(state_root, deployment_id)
    previous = read_terminal_state(state_path, deployment_id)
    if previous is not None:
        outcome, exit_code = previous
        emit(
            event_for(
                deployment_id,
                "deployment",
                outcome=outcome,
                exit_code=exit_code,
            )
        )
        return exit_code

    journal = Journal(state_path, deployment_id, scenario_name, scenario)
    journal.record("build_candidate")
    journal.record("detect_migrations")
    if scenario.migration_state == "pending":
        journal.record("create_backup")
    journal.record(
        "enable_maintenance",
        updates={"maintenance_enabled": True},
    )

    if scenario.migration_state == "pending":
        if not scenario.migration_succeeds:
            journal.record(
                "apply_migrations",
                outcome="failed",
                exit_code=MIGRATION_FAILURE,
            )
            return finish_failure(
                journal,
                status="migration_failed",
                exit_code=MIGRATION_FAILURE,
                previous_healthy=scenario.previous_healthy,
            )
        journal.record(
            "apply_migrations",
            updates={"database_migrated": True},
        )

    journal.record(
        "switch_candidate",
        updates={"candidate_switched": True},
    )
    if not scenario.candidate_healthy:
        journal.record(
            "check_candidate_health",
            outcome="failed",
            exit_code=CANDIDATE_HEALTH_FAILURE,
        )
        journal.record(
            "restore_previous",
            updates={"candidate_switched": False},
        )
        return finish_failure(
            journal,
            status="rolled_back",
            exit_code=CANDIDATE_HEALTH_FAILURE,
            previous_healthy=scenario.previous_healthy,
        )

    journal.record("check_candidate_health")
    journal.record(
        "disable_maintenance",
        updates={"maintenance_enabled": False},
    )
    journal.record("record_success", updates={"status": "succeeded"})
    emit(
        event_for(
            deployment_id,
            "deployment",
            outcome="succeeded",
            exit_code=0,
        )
    )
    return 0


def main(arguments: list[str] | None = None) -> int:
    try:
        parsed = parse_arguments(sys.argv[1:] if arguments is None else arguments)
        if parsed.dry_run:
            return run_dry_run(parsed.deployment_id, parsed.migration_state)
        return run_simulation(
            parsed.state_root,
            parsed.deployment_id,
            parsed.simulate,
        )
    except UsageError as error:
        print(f"deploy: {error}", file=sys.stderr)
        return USAGE_ERROR
    except OSError:
        print("deploy: deployment journal I/O failed", file=sys.stderr)
        return STATE_IO_ERROR
    except Exception:
        print("deploy: internal simulation error", file=sys.stderr)
        return SOFTWARE_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
