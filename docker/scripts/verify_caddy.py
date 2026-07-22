#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_FILE = PROJECT_ROOT / "docker/caddy/compose.production.yaml"
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
    "KAJ_UMAMI_DATABASE_URL": "postgresql://kaj:contract@postgres:5432/umami",
    "KAJ_UMAMI_APP_SECRET": "contract-only-umami-secret",
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

    for missing in sorted(REQUIRED):
        values = REQUIRED.copy()
        values.pop(missing)
        os.environ.pop(missing, None)
        result = compose_config(values)
        if result.returncode == 0:
            failures.append(f"production compose accepted missing {missing}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        "caddy contract: local HTTP, production gates, public 80/443, secret isolation"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
