"""Domain exceptions. Transient errors are retried, permanent ones fail the deployment."""
from __future__ import annotations


class AppError(Exception):
    """Base error."""


class TransientError(AppError):
    """Temporary failure — the step may be retried."""


class PermanentError(AppError):
    """Unrecoverable failure — the step must not be retried automatically."""


class WaitingError(AppError):
    """Not an error: the step is waiting for an external condition (DNS, certificate)."""

    def __init__(self, message: str, *, state: str = "waiting") -> None:
        super().__init__(message)
        self.state = state


class SSHError(TransientError):
    pass


class SSHCommandError(PermanentError):
    def __init__(self, command: str, exit_code: int, stderr: str) -> None:
        super().__init__(f"command failed (exit {exit_code}): {command}\n{stderr.strip()[:2000]}")
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr


class RemnawaveAPIError(AppError):
    def __init__(self, status: int, body: str, endpoint: str) -> None:
        super().__init__(f"Remnawave {endpoint} -> HTTP {status}: {body[:1000]}")
        self.status = status
        self.body = body
        self.endpoint = endpoint


class RemnawaveUnsupportedOperation(PermanentError):
    """The operation is not present in the documented Remnawave API surface."""


class YandexAPIError(AppError):
    def __init__(self, status: int, body: str, endpoint: str) -> None:
        super().__init__(f"Yandex Cloud {endpoint} -> HTTP {status}: {body[:1000]}")
        self.status = status
        self.body = body
        self.endpoint = endpoint


class PaymentError(AppError):
    pass


class PaymentValidationError(PaymentError):
    """Webhook payload failed validation (signature, amount, order, currency)."""


class DNSNotPropagated(WaitingError):
    pass


class CertificatePending(WaitingError):
    pass
