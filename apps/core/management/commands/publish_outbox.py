from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string

from apps.core.events.publisher import publish_batch


def _load_transport():
    dotted_path = getattr(settings, "OUTBOX_TRANSPORT", "")
    if not isinstance(dotted_path, str) or not dotted_path:
        raise CommandError("OUTBOX_TRANSPORT is required; no event was published")
    try:
        factory = import_string(dotted_path)
        transport = factory()
    except Exception:
        raise CommandError(
            "OUTBOX_TRANSPORT is invalid; no event was published"
        ) from None
    if not callable(getattr(transport, "publish", None)):
        raise CommandError("OUTBOX_TRANSPORT is invalid; no event was published")
    return transport


class Command(BaseCommand):
    help = "Publish one leased batch from the transactional outbox"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--batch-size",
            type=int,
            default=settings.OUTBOX_BATCH_SIZE,
        )
        parser.add_argument(
            "--lease-seconds",
            type=int,
            default=settings.OUTBOX_LEASE_SECONDS,
        )
        parser.add_argument(
            "--retry-delay-seconds",
            type=int,
            default=settings.OUTBOX_RETRY_DELAY_SECONDS,
        )

    def handle(self, *args, **options) -> None:
        del args
        transport = _load_transport()
        try:
            result = publish_batch(
                transport,
                batch_size=options["batch_size"],
                lease_seconds=options["lease_seconds"],
                retry_delay_seconds=options["retry_delay_seconds"],
            )
        except ValueError:
            raise CommandError("Invalid outbox publisher bounds") from None
        self.stdout.write(
            self.style.SUCCESS(
                "Outbox batch complete "
                f"claimed={result.claimed} "
                f"published={result.published} "
                f"failed={result.failed}"
            )
        )
