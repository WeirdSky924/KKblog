from pathlib import Path


def test_incremental_image_requires_a_revision_and_only_copies_runtime_sources():
    dockerfile = Path("docker/web/Dockerfile.incremental").read_text(encoding="utf-8")
    ignore = Path("docker/web/Dockerfile.incremental.dockerignore").read_text(
        encoding="utf-8"
    )

    assert (
        "ARG BASE_IMAGE=registry.invalid/kajspace/base-image:required-build-arg"
        in dockerfile
    )
    assert "ARG SOURCE_REVISION" in dockerfile
    assert "org.opencontainers.image.revision=${SOURCE_REVISION}" in dockerfile
    assert "COPY --chown=10001:10001 apps/ /app/apps/" in dockerfile
    assert "COPY --chown=10001:10001 templates/ /app/templates/" in dockerfile
    assert "COPY --chown=10001:10001 static/dist/ /app/static/dist/" in dockerfile
    assert ".env" in ignore
    assert "var" in ignore
    assert "static/dist" not in ignore
