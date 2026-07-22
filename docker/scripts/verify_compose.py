#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VAR_ROOT = (PROJECT_ROOT / "var").resolve()
EXPECTED_SERVICES = {
    "web",
    "postgres",
    "redis",
    "worker",
    "beat",
    "caddy",
    "umami",
    "mailpit",
}
INTERNAL_ONLY_SERVICES = {
    "postgres",
    "redis",
    "worker",
    "beat",
    "umami",
    "mailpit",
}
APP_SERVICES = {"web", "worker", "beat"}


def load_config() -> dict[str, object]:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        print(result.stderr.strip(), file=sys.stderr)
        raise SystemExit(result.returncode)
    return json.loads(result.stdout)


def main() -> int:
    config = load_config()
    services = config.get("services", {})
    networks = config.get("networks", {})
    violations: list[str] = []

    actual_services = set(services)
    if actual_services != EXPECTED_SERVICES:
        violations.append(
            f"services: expected {sorted(EXPECTED_SERVICES)}, got {sorted(actual_services)}"
        )

    backend = networks.get("backend", {})
    if backend.get("internal") is not True:
        violations.append("backend network must be internal")

    caddy_ports = services.get("caddy", {}).get("ports", [])
    if len(caddy_ports) != 1:
        violations.append("caddy must publish exactly one local HTTP port")
    else:
        port = caddy_ports[0]
        expected_port = {
            "host_ip": "127.0.0.1",
            "target": 80,
            "protocol": "tcp",
        }
        for key, value in expected_port.items():
            if port.get(key) != value:
                violations.append(f"caddy port {key} must be {value!r}")

    for name, service in services.items():
        if name in INTERNAL_ONLY_SERVICES and service.get("ports"):
            violations.append(f"{name} must not publish host ports")
        if service.get("privileged"):
            violations.append(f"{name} must not be privileged")
        if service.get("network_mode") == "host":
            violations.append(f"{name} must not use host networking")
        if service.get("restart") != "unless-stopped":
            violations.append(f"{name} must use restart=unless-stopped")
        image = service.get("image", "")
        if image.endswith(":latest") or image.endswith("-latest"):
            violations.append(f"{name} must not use a floating latest image")

        for volume in service.get("volumes", []):
            if volume.get("type") != "bind":
                violations.append(f"{name} volume must be a project bind mount")
                continue
            source = Path(volume.get("source", "")).resolve()
            if not source.is_relative_to(VAR_ROOT):
                violations.append(f"{name} bind source escapes project var: {source}")

    for name in APP_SERVICES:
        service = services.get(name, {})
        if service.get("read_only") is not True:
            violations.append(f"{name} root filesystem must be read-only")
        if "ALL" not in service.get("cap_drop", []):
            violations.append(f"{name} must drop all Linux capabilities")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            violations.append(f"{name} must set no-new-privileges")

    dockerfile = (PROJECT_ROOT / "docker/web/Dockerfile").read_text(encoding="utf-8")
    if "USER 10001:10001" not in dockerfile:
        violations.append("web image must switch to the fixed non-root UID/GID")
    if "COPY . " in dockerfile or "ADD . " in dockerfile:
        violations.append("web image must use explicit COPY sources")

    if violations:
        print("\n".join(sorted(violations)), file=sys.stderr)
        return 1
    print(
        "compose contract: 8 services, local-only HTTP, internal data plane, var binds"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
