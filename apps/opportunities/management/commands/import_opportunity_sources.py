import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.opportunities.services.source_manifests import (
    SourceManifestError,
    apply_source_manifest,
    parse_source_manifest,
)

MAX_MANIFEST_BYTES = 1_048_576


def _reject_constant(value: str):
    raise ValueError(f"non-finite JSON constant: {value}")


class Command(BaseCommand):
    help = "Validate or import source-only opportunity configuration"

    def add_arguments(self, parser) -> None:
        parser.add_argument("--input", required=True)
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write validated sources; without this flag the command is a dry run",
        )

    def handle(self, *args, **options) -> None:
        del args
        source = Path(options["input"])
        if source.suffix.casefold() != ".json" or source.is_symlink():
            raise CommandError(
                "Input must be a regular .json file, not a symbolic link"
            )
        source = source.resolve()
        if not source.is_file() or source.stat().st_size > MAX_MANIFEST_BYTES:
            raise CommandError("Input manifest is missing or too large")
        try:
            payload = json.loads(
                source.read_text(encoding="utf-8"), parse_constant=_reject_constant
            )
            rows = parse_source_manifest(payload)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            SourceManifestError,
            ValueError,
        ) as error:
            raise CommandError(
                f"Invalid opportunity source manifest: {error}"
            ) from None
        if not options["apply"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Opportunity source manifest valid sources={len(rows)} dry_run=true"
                )
            )
            return
        try:
            result = apply_source_manifest(rows)
        except SourceManifestError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(
            self.style.SUCCESS(
                "Opportunity source manifest imported "
                f"sources={len(rows)} created={result.created} updated={result.updated}"
            )
        )
