"""Domain errors raised by services. The API layer maps them to the envelope."""


class DomainError(Exception):
    """A failure with an HTTP status. Services raise this; routes do not catch it themselves."""
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        """Keep the client-facing message and the status the envelope should use."""
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class PermanentIngestError(DomainError):
    """A document that will not succeed if the task is retried."""

    def __init__(self, message: str) -> None:
        """A permanent ingest failure is a 400 and is not retried."""
        super().__init__(message, status_code=400)


class TransientIngestError(Exception):
    """A failure Celery may retry with backoff."""

    def __init__(self, message: str) -> None:
        """Keep the reason. The worker retries this and then stores it as a failed job."""
        super().__init__(message)
        self.message = message
