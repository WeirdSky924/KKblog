import ast
from importlib.util import resolve_name
from pathlib import Path

APPS_ROOT = Path(__file__).resolve().parents[2] / "apps"
ARCHITECTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "architecture"
BUSINESS_APPS = {
    "accounts",
    "administration",
    "agents",
    "analytics",
    "authoring",
    "comments",
    "content",
    "discovery",
    "exchange",
    "learning",
    "media",
    "moderation",
    "navigation",
    "notifications",
    "operations",
    "opportunities",
}
ALLOWED_APP_DEPENDENCIES = {
    "core": set(),
    "accounts": {"core", "media"},
    "agents": {"accounts", "core", "operations"},
    "content": {"accounts", "core", "media", "operations"},
    "media": {"core", "operations"},
    "comments": {"content", "core", "operations"},
    "moderation": {"comments", "content", "core", "operations"},
    "notifications": {"core"},
    "navigation": {"accounts", "content", "core", "operations"},
    "operations": {"core"},
    "opportunities": {"accounts", "core", "operations"},
    "exchange": {"core", "operations"},
    "learning": {"accounts", "agents", "core", "media", "operations"},
    "analytics": {"accounts", "core", "operations"},
    "discovery": {"comments", "content", "core", "media", "navigation"},
    "authoring": {"accounts", "comments", "content", "core", "exchange", "media"},
    "administration": {
        "accounts",
        "agents",
        "analytics",
        "comments",
        "content",
        "core",
        "exchange",
        "learning",
        "media",
        "moderation",
        "navigation",
        "notifications",
        "operations",
        "opportunities",
    },
}


def test_agent_learning_architecture_contracts_are_registered() -> None:
    required_markers = {
        "README.md": ("apps/agents", "apps/learning"),
        "01-system-directory.md": ("apps/agents", "apps/learning"),
        "adr/ADR-007-server-rendered-with-question-bank-api.md": (
            "/api/v1/question-banks",
            "rate_limiter_unavailable",
        ),
        "modules/12-agents-runtime.md": ("apps/agents", "Provider 与威胁边界"),
        "modules/13-learning-question-banks.md": (
            "apps/learning",
            "公开查询和 API",
        ),
        "contracts/01-application-services.md": (
            "## agents 公开服务",
            "## learning 公开服务",
        ),
        "contracts/02-authorization-matrix.md": (
            "## AGENT 与知识学习",
            "外部题库 API",
        ),
        "contracts/03-frontend-contract-map.md": (
            "question-banks:index",
            "admin:agent-endpoints",
        ),
        "contracts/04-events-errors.md": (
            "knowledge.review_completed.v1",
            "question_bank.generation_completed.v1",
        ),
        "contracts/05-background-tasks.md": (
            "review_knowledge_document",
            "generate_question_bank",
        ),
        "data/01-er-model.md": ("AgentEndpoint", "KnowledgeDocument"),
        "data/04-indexes-constraints.md": (
            "agent_endpoint",
            "knowledge_document",
        ),
        "data/05-storage-lifecycle.md": (
            "知识文档",
            "题库",
        ),
        "delivery/02-module-verification-matrix.md": (
            "AGENT 运行时",
            "知识学习",
        ),
        "reference/03-requirements-traceability.md": (
            "AKQ-Q001",
            "AKQ-Q039",
        ),
    }
    missing = []
    for relative_path, markers in required_markers.items():
        content = (ARCHITECTURE_ROOT / relative_path).read_text(encoding="utf-8")
        for marker in markers:
            if marker not in content:
                missing.append(f"{relative_path}: {marker}")
    assert not missing, "\n".join(missing)


def test_agents_and_learning_dependency_direction_is_one_way() -> None:
    assert ALLOWED_APP_DEPENDENCIES["agents"] == {
        "accounts",
        "core",
        "operations",
    }
    assert ALLOWED_APP_DEPENDENCIES["learning"] == {
        "accounts",
        "agents",
        "core",
        "media",
        "operations",
    }
    dependents = {
        owner
        for owner, dependencies in ALLOWED_APP_DEPENDENCIES.items()
        if "learning" in dependencies
    }
    assert dependents == {"administration"}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    relative_module = path.relative_to(APPS_ROOT.parent).with_suffix("")
    module_name = ".".join(relative_module.parts)
    package_name = (
        module_name if path.name == "__init__.py" else module_name.rsplit(".", 1)[0]
    )
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                imported = resolve_name(
                    "." * node.level + (node.module or ""),
                    package_name,
                )
            else:
                imported = node.module
            if imported:
                imports.append(imported)
    return imports


def test_app_imports_follow_documented_dependency_direction() -> None:
    violations = []
    for path in sorted(APPS_ROOT.rglob("*.py")):
        if {"__pycache__", "migrations", "tests"} & set(path.parts):
            continue
        relative_path = path.relative_to(APPS_ROOT)
        if len(relative_path.parts) < 2:
            continue
        owner = relative_path.parts[0]
        allowed = ALLOWED_APP_DEPENDENCIES.get(owner)
        if allowed is None:
            violations.append(f"{path}: unknown owner app {owner}")
            continue
        for imported in _imports(path):
            parts = imported.split(".")
            if len(parts) < 2 or parts[0] != "apps":
                continue
            dependency = parts[1]
            if dependency == owner:
                continue
            if dependency not in allowed:
                violations.append(f"{path}: {owner} -> {imported}")
            if len(parts) >= 3 and parts[2] == "models":
                violations.append(f"{path}: cross-app private model import {imported}")
    assert not sorted(set(violations)), "\n".join(sorted(set(violations)))


def test_core_contains_only_approved_cross_cutting_capabilities() -> None:
    allowed_entries = {
        "__init__.py",
        "apps.py",
        "errors",
        "events",
        "http.py",
        "ids.py",
        "management",
        "migrations",
        "models.py",
        "observability",
        "pagination.py",
        "security_headers.py",
        "time",
    }
    actual = {
        path.name
        for path in (APPS_ROOT / "core").iterdir()
        if path.name != "__pycache__"
    }
    assert actual <= allowed_entries


def test_no_empty_business_app_is_scaffolded_early() -> None:
    present = {path.name for path in APPS_ROOT.iterdir() if path.is_dir()}
    empty = []
    for name in present & BUSINESS_APPS:
        implementation_files = [
            path
            for path in (APPS_ROOT / name).rglob("*.py")
            if path.name not in {"__init__.py", "apps.py"} and "tests" not in path.parts
        ]
        if not implementation_files:
            empty.append(name)
    assert not empty
