import json
import os
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.opportunities.services.source_manifests import (
    SourceManifestError,
    build_source_manifest,
)


class Command(BaseCommand):
    help = "Export opportunity source configuration without crawler or job data"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--output", required=True)
        parser.add_argument("--overwrite", action="store_true")

    def handle(self, *args, **options) -> None:
        del args
        target = Path(options["output"])
        if target.suffix.casefold() != ".json":
            raise CommandError("Output must be a .json file")
        if target.is_symlink():
            raise CommandError("Output must not be a symbolic link")
        parent = target.parent.resolve()
        if not parent.is_dir():
            raise CommandError("Output directory does not exist")
        target = parent / target.name
        if target.exists() and not options["overwrite"]:
            raise CommandError("Output already exists; use --overwrite to replace it")
        try:
            payload = build_source_manifest()
        except SourceManifestError as error:
            raise CommandError(str(error)) from None
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        self.stdout.write(
            self.style.SUCCESS(
                f"Opportunity source manifest exported sources={len(payload['sources'])}"
            )
        )
