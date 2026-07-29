from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True, slots=True)
class RegistrationPolicy:
    direct_enabled: bool = False


RegistrationPolicyProvider = Callable[[], bool]


def _settings_registration_enabled() -> bool:
    return bool(getattr(settings, "DIRECT_REGISTRATION_ENABLED", False))


_registration_policy_provider: RegistrationPolicyProvider = (
    _settings_registration_enabled
)


def configure_registration_policy_provider(
    provider: RegistrationPolicyProvider,
) -> None:
    if not callable(provider):
        raise TypeError("registration policy provider must be callable")
    global _registration_policy_provider
    _registration_policy_provider = provider


def configured_registration_policy() -> RegistrationPolicy:
    value = _registration_policy_provider()
    if not isinstance(value, bool):
        raise TypeError("registration policy provider must return bool")
    return RegistrationPolicy(direct_enabled=value)


__all__ = [
    "RegistrationPolicy",
    "configure_registration_policy_provider",
    "configured_registration_policy",
]
