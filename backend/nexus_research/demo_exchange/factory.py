"""Phase 6.6 — DemoPrivateClientFactory."""
from __future__ import annotations

from typing import Any

from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
from backend.nexus_research.demo_exchange.domain_policy import DemoDomainPolicy
from backend.nexus_research.demo_exchange.signer import DemoRequestSigner
from backend.nexus_research.demo_exchange.transport import DemoReadOnlyTransport


class DemoPrivateClientFactory:
    """Build read-only client; fixtures when credentials missing."""

    def __init__(
        self,
        *,
        policy: DemoDomainPolicy | None = None,
        credential_validator: DemoCredentialPresenceValidator | None = None,
        force_fixtures: bool = False,
    ) -> None:
        self.policy = policy or DemoDomainPolicy()
        self.credentials = credential_validator or DemoCredentialPresenceValidator()
        self.force_fixtures = force_fixtures

    def create(self) -> tuple[DemoReadOnlyTransport, dict[str, Any]]:
        presence = self.credentials.validate(require=False)
        meta: dict[str, Any] = {
            **presence.to_public_dict(),
            "domain_policy": self.policy.summary(),
            "mode": "fixtures" if (self.force_fixtures or not presence.configured) else "live_readonly",
        }
        if self.force_fixtures or not presence.configured:
            transport = DemoReadOnlyTransport(
                policy=self.policy,
                signer=None,
                use_fixtures=True,
            )
            return transport, meta

        key, secret = self.credentials.load_secrets_for_signer()
        signer = DemoRequestSigner(key, secret)
        transport = DemoReadOnlyTransport(
            policy=self.policy,
            signer=signer,
            use_fixtures=False,
        )
        return transport, meta
