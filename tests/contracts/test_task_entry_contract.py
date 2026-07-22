import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _is_celery_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (
        isinstance(target, ast.Name)
        and target.id == "shared_task"
        or isinstance(target, ast.Attribute)
        and target.attr == "task"
    )


def _calls_task_run_owner(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "execute_celery_entry"
        for node in ast.walk(function)
    )


def test_every_celery_entry_uses_operations_task_run_owner() -> None:
    entries = []
    violations = []
    roots = (PROJECT_ROOT / "apps", PROJECT_ROOT / "config")
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not any(_is_celery_decorator(item) for item in node.decorator_list):
                    continue
                label = f"{path.relative_to(PROJECT_ROOT)}:{node.name}"
                entries.append(label)
                if not _calls_task_run_owner(node):
                    violations.append(label)

    assert "config/runtime_tasks.py:smoke" in entries
    assert not violations, "Celery entries bypass TaskRun owner:\n" + "\n".join(
        violations
    )
