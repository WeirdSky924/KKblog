#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_FILE = PROJECT_ROOT / "docker/caddy/compose.production.yaml"
CADDY_IMAGE = os.environ.get("KAJ_CADDY_IMAGE", "kaj-blog-caddy:local")
REQUIRED = {
    "DJANGO_SECRET_KEY": "Kj8!xN2@vP5#rT9$wY4%aC7&dF1*gH6!mQ3@zX8#sV2$kL9%pR5",
    "KAJ_PUBLIC_URL": "https://blog.example.com",
    "KAJ_PUBLIC_HOST": "blog.example.com",
    "KAJ_ADMIN_EMAIL": "admin@example.com",
    "RESEND_FROM_EMAIL": "no-reply@example.com",
    "RESEND_API_KEY": "re_contract_only_1234567890",
    "DATABASE_URL": "postgresql://kaj:contract@postgres:5432/kaj",
    "REDIS_URL": "redis://redis:6379/0",
    "KAJ_MEDIA_ROOT": "/app/var/media",
    "KAJ_INITIAL_ADMIN_PASSWORD": "Contract9!OnlyValue",
    "KAJ_TRUSTED_PROXY_CIDRS": "172.16.0.0/12",
    "KAJ_UMAMI_DATABASE_URL": "postgresql://kaj:contract@postgres:5432/umami",
    "KAJ_UMAMI_APP_SECRET": "contract-only-umami-secret-value",
    "KAJ_UMAMI_WEBSITE_ID": "8b52c6fc-8d26-48b4-8ec8-5f2a67587044",
}


def compose_config(values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(values)
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(PROJECT_ROOT / "compose.yaml"),
            "-f",
            str(PRODUCTION_FILE),
            "config",
            "--format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )


def adapt_caddy(filename: str, *, production: bool) -> subprocess.CompletedProcess[str]:
    environment = [
        "-e",
        "KAJ_CADDY_UPSTREAM=web:8000",
        "-e",
        "KAJ_UMAMI_UPSTREAM=umami:3000",
    ]
    if production:
        environment.extend(["-e", "KAJ_PUBLIC_HOST=blog.example.com"])
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--entrypoint",
            "caddy",
            "-v",
            f"{PROJECT_ROOT / 'docker/caddy'}:/etc/caddy:ro",
            *environment,
            CADDY_IMAGE,
            "adapt",
            "--config",
            f"/etc/caddy/{filename}",
            "--adapter",
            "caddyfile",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def analytics_proxy_violations(config: dict[str, object]) -> list[str]:
    violations: list[str] = []
    nodes = list(walk_json(config))
    matches = [
        match
        for node in nodes
        for match in node.get("match", [])
        if isinstance(match, dict)
    ]
    expected_public = {
        "/analytics/script.js": ["GET", "HEAD"],
        "/analytics/collect": ["POST", "OPTIONS"],
    }
    for path, methods in expected_public.items():
        actual = [match for match in matches if match.get("path") == [path]]
        if len(actual) != 1 or actual[0].get("method") != methods:
            violations.append(f"Caddy must match only {methods} on {path}")

    adapted_paths = {
        path
        for match in matches
        for path in match.get("path", [])
        if isinstance(path, str)
    }
    if any("+" in path or "\\n" in path for path in adapted_paths):
        violations.append("Caddy analytics paths contain malformed matcher text")

    reverse_proxies = [node for node in nodes if node.get("handler") == "reverse_proxy"]
    umami_proxies = [
        proxy
        for proxy in reverse_proxies
        if any(
            upstream.get("dial") == "umami:3000"
            for upstream in proxy.get("upstreams", [])
            if isinstance(upstream, dict)
        )
    ]
    if len(umami_proxies) != 3:
        violations.append("Caddy must define exactly three Umami proxy routes")
    for proxy in umami_proxies:
        deleted = proxy.get("headers", {}).get("request", {}).get("delete", [])
        if "Cookie" not in deleted:
            violations.append("Every Umami proxy route must remove browser cookies")

    auth_proxies = [
        proxy
        for proxy in reverse_proxies
        if proxy.get("rewrite", {}).get("uri") == "/internal/analytics/authorize"
    ]
    if len(auth_proxies) != 1:
        violations.append("Caddy must define one analytics authorization subrequest")
    else:
        request_headers = auth_proxies[0].get("headers", {}).get("request", {})
        if "Authorization" not in request_headers.get("delete", []):
            violations.append("Analytics authorization must not receive Umami tokens")
        if request_headers.get("set", {}).get("X-Kaj-Internal-Auth") != ["1"]:
            violations.append("Analytics authorization must set the internal marker")

        prefix_rewrites = [
            node
            for node in nodes
            if node.get("strip_path_prefix") == "/admin/analytics/umami"
        ]
        if len(prefix_rewrites) != 1:
            violations.append("Caddy must strip the analytics dashboard prefix once")
        elif not (
            nodes.index(auth_proxies[0])
            < nodes.index(prefix_rewrites[0])
            < nodes.index(umami_proxies[-1])
        ):
            violations.append(
                "Caddy must authorize the original dashboard path before rewriting"
            )
    return violations


def main() -> int:
    failures: list[str] = []
    configured = compose_config(REQUIRED)
    if configured.returncode:
        print(
            "production compose did not render with contract-only values",
            file=sys.stderr,
        )
        return 1

    config = json.loads(configured.stdout)
    services = config["services"]
    ports = services["caddy"].get("ports", [])
    actual_ports = {
        (port["host_ip"], port["published"], port["target"]) for port in ports
    }
    if actual_ports != {("0.0.0.0", "80", 80), ("0.0.0.0", "443", 443)}:
        failures.append("production Caddy must publish only public 80 and 443")

    caddy_environment = services["caddy"]["environment"]
    forbidden = {
        "DJANGO_SECRET_KEY",
        "DATABASE_URL",
        "REDIS_URL",
        "RESEND_API_KEY",
        "KAJ_INITIAL_ADMIN_PASSWORD",
        "KAJ_UMAMI_APP_SECRET",
    }
    leaked = forbidden.intersection(caddy_environment)
    if leaked:
        failures.append(
            "Caddy received unrelated secrets: " + ", ".join(sorted(leaked))
        )

    for name in ("web", "worker", "beat"):
        environment = services[name]["environment"]
        if environment.get("DJANGO_SETTINGS_MODULE") != "config.settings.production":
            failures.append(f"{name} must use production settings")
        if "KAJ_UMAMI_APP_SECRET" in environment:
            failures.append(f"{name} received the Umami application secret")

    for missing in sorted(REQUIRED):
        values = REQUIRED.copy()
        values.pop(missing)
        os.environ.pop(missing, None)
        result = compose_config(values)
        if result.returncode == 0:
            failures.append(f"production compose accepted missing {missing}")

    for filename, production in (
        ("Caddyfile.development", False),
        ("Caddyfile.production", True),
    ):
        adapted = adapt_caddy(filename, production=production)
        if adapted.returncode:
            failures.append(f"Caddy could not adapt {filename}")
            continue
        failures.extend(analytics_proxy_violations(json.loads(adapted.stdout)))

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        "caddy contract: ports, production gates, secret isolation, exact analytics routes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
