from pathlib import Path


def test_production_caddy_maintenance_switch_preserves_health_checks():
    config = Path("docker/caddy/Caddyfile.production").read_text(encoding="utf-8")

    assert "@maintenance {" in config
    assert "try_files /maintenance.enabled" in config
    assert "not path /health/live /health/ready" in config
    assert 'header Cache-Control "no-store"' in config
    assert 'respond "Kajspace 正在进行维护，请稍后重试。" 503' in config
