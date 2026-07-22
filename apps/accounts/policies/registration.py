from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistrationPolicy:
    direct_enabled: bool = False
