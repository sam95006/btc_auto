"""Security boundary exceptions — fail closed, never soft-allow writes."""
from __future__ import annotations


class ExchangeWriteForbidden(RuntimeError):
    """Raised when any exchange write / mutation method is invoked under traps."""

    code = "EXCHANGE_WRITE_FORBIDDEN"

    def __init__(self, method: str = "", detail: str = "") -> None:
        self.method = method
        self.detail = detail
        msg = self.code if not method else f"{self.code}:{method}"
        if detail:
            msg = f"{msg}:{detail}"
        super().__init__(msg)


class CredentialBoundaryError(RuntimeError):
    code = "CREDENTIAL_BOUNDARY_FAILED"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}:{reason}")


class PublicPrivateBoundaryError(RuntimeError):
    code = "PUBLIC_PRIVATE_BOUNDARY_FAILED"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}:{reason}")


class PersistenceSecurityError(RuntimeError):
    code = "PERSISTENCE_SECURITY_FAILED"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}:{reason}")


class NetworkEgressForbidden(RuntimeError):
    code = "NETWORK_EGRESS_FORBIDDEN"

    def __init__(self, url: str = "", detail: str = "") -> None:
        self.url = url
        self.detail = detail
        super().__init__(f"{self.code}:{url}:{detail}" if detail else f"{self.code}:{url}")
