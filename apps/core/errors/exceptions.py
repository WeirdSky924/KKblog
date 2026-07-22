from .codes import ErrorCode


class DomainError(Exception):
    def __init__(self, code: ErrorCode, *, retry_after: int | None = None) -> None:
        if retry_after is not None and not 1 <= retry_after <= 86_400:
            raise ValueError("retry_after must be between 1 and 86400 seconds")
        self.code = code
        self.retry_after = retry_after
        super().__init__(code.value)
