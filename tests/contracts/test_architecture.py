import ast
from importlib.util import resolve_name
from pathlib import Path

APPS_ROOT = Path(__file__).resolve().parents[2] / "apps"
BUSINESS_APPS = {
    "accounts",
    "administration",
    "analytics",
    "authoring",
    "comments",
    "content",
    "discovery",
    "exchange",
    "media",
    "moderation",
    "navigation",
    "notifications",
    "operations",
}
ALLOWED_APP_DEPENDENCIES = {
    "core": set(),
    "accounts": {"core", "media"},
    "content": {"accounts", "core", "media", "operations"},
    "media": {"core", "operations"},
    "comments": {"content", "core", "operations"},
    "moderation": {"comments", "content", "core", "operations"},
    "notifications": {"core"},
    "navigation": {"core"},
    "operations": {"core"},
    "exchange": {"core", "operations"},
    "analytics": {"accounts", "core", "operations"},
    "discovery": {"comments", "content", "core", "navigation"},
    "authoring": {"comments", "content", "core", "exchange", "media"},
    "administration": {
        "accounts",
        "analytics",
        "content",
        "core",
        "media",
        "moderation",
        "navigation",
        "notifications",
        "operations",
    },
}


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
        if "__pycache__" in path.parts:
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
        "ids.py",
        "management",
        "migrations",
        "models.py",
        "observability",
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
