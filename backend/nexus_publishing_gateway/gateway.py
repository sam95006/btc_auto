"""Read-only Intelligence Publishing Gateway — main publish path."""
from __future__ import annotations

from typing import Any

from backend.nexus_publishing_gateway.aggregation import apply_public_aggregations
from backend.nexus_publishing_gateway.allowlist import serialize_allowlist
from backend.nexus_publishing_gateway.constants import HARD_BANS, SCHEMA
from backend.nexus_publishing_gateway.deny_traps import assert_no_denied_fields
from backend.nexus_publishing_gateway.environment import assert_local_or_staging
from backend.nexus_publishing_gateway.exceptions import PublishingGatewayError
from backend.nexus_publishing_gateway.redaction import redact_payload
from backend.nexus_publishing_gateway.schema import wrap_public_envelope
from backend.nexus_publishing_gateway.timing import timing_pad


def publish_intelligence(
    private_like_payload: dict[str, Any] | None,
    *,
    environment: str | None = None,
    availability: str = "AVAILABLE",
) -> dict[str, Any]:
    """Sanitize a private-like dict into a public Decision Intelligence envelope.

    Fail-closed order:
      1) environment guard (LOCAL/STAGING)
      2) deny traps on raw input
      3) allow-list serialize
      4) redact residual sensitive shapes
      5) aggregation thresholds / confidence bucketing
      6) schema envelope
      7) timing pad
    """
    with timing_pad() as timing_meta:
        env = assert_local_or_staging(environment)
        raw = dict(private_like_payload or {})
        assert_no_denied_fields(raw, context="pre_allowlist")
        allowed = serialize_allowlist(raw)
        redacted = redact_payload(allowed)
        if not isinstance(redacted, dict):
            raise PublishingGatewayError("allowlist_did_not_return_object")
        aggregated = apply_public_aggregations(redacted)
        assert_no_denied_fields(aggregated, context="post_aggregation")
        envelope = wrap_public_envelope(
            aggregated,
            environment=env,
            availability=availability,
            schema_version=SCHEMA,
        )
        # timing_meta retained only for the pad side-effect; never published.
        _ = timing_meta
        return envelope


def publish_public_dto(payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Alias for publish_intelligence — read-only public DTO factory."""
    return publish_intelligence(payload, **kwargs)


def hard_ban_inventory() -> dict[str, Any]:
    return {
        "hard_bans": list(HARD_BANS),
        "production_deploy": False,
        "live_billing": False,
        "exchange_write": False,
        "PR26_merged": False,
        "PR27_merged": False,
        "read_only": True,
    }
