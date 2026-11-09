"""Safe, consistent API error envelopes."""


class APIError(RuntimeError):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after

    def payload(self, request_id: str) -> dict:
        result = {
            # Retained for compatibility with the original frontend and clients.
            "error": self.message,
            "code": self.code,
            "message": self.message,
            "request_id": request_id,
            "retryable": self.retryable,
        }
        if self.retry_after is not None:
            result["retry_after_seconds"] = self.retry_after
        return result
