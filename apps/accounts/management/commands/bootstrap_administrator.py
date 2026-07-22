from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services.bootstrap import BootstrapError, bootstrap_administrator


class Command(BaseCommand):
    help = "Consume the configured one-time secret and create the sole administrator"

    def handle(self, *args, **options):
        password = getattr(settings, "INITIAL_ADMIN_PASSWORD", "")
        if not password:
            raise CommandError("INITIAL_ADMIN_PASSWORD is not configured")
        try:
            account = bootstrap_administrator(
                email=settings.ADMIN_EMAIL,
                initial_password=password,
                production=not settings.DEBUG,
            )
        except BootstrapError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(f"Administrator initialized: {account.id}")
