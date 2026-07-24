class CommentPostingError(ValueError):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        field: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        self.code = code
        self.safe_message = safe_message
        self.field = field
        self.retry_after = retry_after
        super().__init__(safe_message)
