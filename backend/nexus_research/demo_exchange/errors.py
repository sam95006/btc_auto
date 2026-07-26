"""Phase 6.6 — Demo exchange errors (never embed secrets)."""
from __future__ import annotations


class DemoExchangeError(Exception):
    """Base error; message must never contain API key/secret."""


class DomainRejectedError(DemoExchangeError):
    pass


class MethodNotAllowedError(DemoExchangeError):
    pass


class WriteForbiddenError(DemoExchangeError):
    """Raised when any write/mutation API is attempted."""


class CredentialMissingError(DemoExchangeError):
    pass


class SignatureInvalidError(DemoExchangeError):
    pass


class PermissionDeniedError(DemoExchangeError):
    pass


class RateLimitError(DemoExchangeError):
    pass


class TimeoutError_(DemoExchangeError):
    """HTTP timeout (named to avoid shadowing builtin)."""


class MalformedResponseError(DemoExchangeError):
    pass


class StaleDataError(DemoExchangeError):
    pass


class AccountIdentityMismatchError(DemoExchangeError):
    pass


class SchemaValidationError(DemoExchangeError):
    pass
