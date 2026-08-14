from .adapters import (
    AdapterResult,
    CollectedOpportunity,
    OpportunityAdapter,
    get_adapter,
    register_adapter,
)
from .http import DomainRateLimiter, SafeHttpClient, SafeHttpResult, SafeRequestError
from .robots import RobotsAwareHttpClient

__all__ = [
    "AdapterResult",
    "CollectedOpportunity",
    "DomainRateLimiter",
    "OpportunityAdapter",
    "SafeHttpClient",
    "SafeHttpResult",
    "SafeRequestError",
    "RobotsAwareHttpClient",
    "get_adapter",
    "register_adapter",
]
