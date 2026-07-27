from django.apps import AppConfig


class ExchangeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.exchange"

    def ready(self) -> None:
        from apps.exchange import signals

        signals.register_exchange_signals()
