from pathlib import Path

from django.conf import settings
from django.test import override_settings

from apps.exchange.staging import ImportStaging


def test_import_staging_defaults_to_writable_media_volume(tmp_path) -> None:
    configured = Path(settings.EXCHANGE_IMPORT_ROOT)
    assert configured == Path(settings.MEDIA_ROOT) / ".exchange" / "imports"

    expected = tmp_path / ".exchange" / "imports"
    with override_settings(
        MEDIA_ROOT=tmp_path,
        EXCHANGE_IMPORT_ROOT=expected,
    ):
        staging = ImportStaging(settings.EXCHANGE_IMPORT_ROOT)

    assert staging.root == expected.resolve()
    assert staging.root.is_dir()
    assert staging.root.is_relative_to(Path(tmp_path).resolve())
