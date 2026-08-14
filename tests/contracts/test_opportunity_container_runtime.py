from pathlib import Path


def test_web_image_contains_media_runtime_without_browser_privilege_expansion():
    dockerfile = Path("docker/web/Dockerfile").read_text(encoding="utf-8")

    assert "libmediainfo0v5" in dockerfile
    assert "DEBIAN_MIRROR" in dockerfile
    assert "DEBIAN_SECURITY_MIRROR" in dockerfile
    assert "chromium" not in dockerfile
    assert "node_modules/playwright" not in dockerfile


def test_browser_runtime_is_isolated_in_a_non_privileged_host_service():
    unit = Path("deploy/systemd/kaj-opportunity-browser.service").read_text(
        encoding="utf-8"
    )

    assert "User=blog-browser" in unit
    assert "NoNewPrivileges=true" in unit
    assert "CapabilityBoundingSet=\n" in unit
    assert "ProtectSystem=strict" in unit
    assert "apps/opportunities/checks/browser_service.py" in unit
    assert "--peer-uid 10001" in unit
    assert "--chrome /opt/google/chrome/chrome" in unit
    assert "SYS_ADMIN" not in unit
    assert "--no-sandbox" not in unit
