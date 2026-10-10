from pathlib import Path


def test_production_caddy_maintenance_switch_preserves_health_checks():
    development = Path("docker/caddy/Caddyfile.development").read_text(encoding="utf-8")
    production = Path("docker/caddy/Caddyfile.production").read_text(encoding="utf-8")
    config = Path("docker/caddy/maintenance.caddy").read_text(encoding="utf-8")

    assert "import /etc/caddy/maintenance.caddy" in development
    assert "import maintenance" in development
    assert "import /etc/caddy/maintenance.caddy" in production
    assert "import maintenance" in production
    assert "@maintenance {" in config
    assert "try_files /maintenance.enabled" in config
    assert "not path /health/live /health/ready" in config
    assert 'header Cache-Control "no-store"' in config
    assert 'respond "Kajspace 正在进行维护，请稍后重试。" 503' in config
