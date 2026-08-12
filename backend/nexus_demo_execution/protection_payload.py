"""Protection payload validation — entry→fill→position→SL→TP→verified chain."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_demo_execution import FIXED_LEVERAGE


class ProtectionStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PROTECTION_NOT_VERIFIED = "PROTECTION_NOT_VERIFIED"


PROTECTION_CHAIN_STAGES = (
    "entry",
    "fill",
    "position",
    "stop_loss",
    "take_profit",
    "verified",
)

KNOWN_PROTECTION_FIELDS = frozenset(
    {
        "entry",
        "fill",
        "position",
        "stop_loss",
        "take_profit",
        "verified",
        "symbol",
        "side",
        "leverage",
        "tradeMode",
        "stopLoss",
        "takeProfit",
        "slTriggerBy",
        "tpTriggerBy",
        "positionIdx",
        "dry_run_only",
    })


@dataclass
class ProtectionPayloadValidation:
    status: ProtectionStatus
    chain: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    unknown_fields: list[str] = field(default_factory=list)

    @property
    def verified(self) -> bool:
        return self.status == ProtectionStatus.VERIFIED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "verified": self.verified,
            "errors": list(self.errors),
            "unknown_fields": list(self.unknown_fields),
            "chain_stages": list(PROTECTION_CHAIN_STAGES),
            "chain": _redact_chain(self.chain),
        }


def build_protection_payload(
    *,
    symbol: str,
    side: str,
    entry_price: float,
    qty: float,
    stop_loss: float,
    take_profit: float,
    leverage: int = FIXED_LEVERAGE,
) -> dict[str, Any]:
    """Build protection chain payload for dry-run validation."""
    return {
        "entry": {"symbol": symbol, "side": side, "price": entry_price, "qty": qty},
        "fill": {"filled_qty": qty, "avg_price": entry_price},
        "position": {
            "symbol": symbol,
            "side": side,
            "size": qty,
            "leverage": leverage,
            "tradeMode": "Isolated",
            "positionIdx": 0,
        },
        "stop_loss": {"stopLoss": str(stop_loss), "slTriggerBy": "LastPrice"},
        "take_profit": {"takeProfit": str(take_profit), "tpTriggerBy": "LastPrice"},
        "verified": {"protection_attached": True, "dry_run_only": True},
        "symbol": symbol,
        "side": side,
        "leverage": leverage,
        "tradeMode": "Isolated",
        "stopLoss": str(stop_loss),
        "takeProfit": str(take_profit),
        "dry_run_only": True,
    }


def validate_protection_payload(payload: dict[str, Any] | None) -> ProtectionPayloadValidation:
    """Validate protection chain; unknown fields → PROTECTION_NOT_VERIFIED."""
    if payload is None:
        return ProtectionPayloadValidation(
            status=ProtectionStatus.PROTECTION_NOT_VERIFIED,
            errors=["payload_missing"],
        )

    errors: list[str] = []
    unknown_fields: list[str] = []

    for key in payload:
        if key not in KNOWN_PROTECTION_FIELDS:
            unknown_fields.append(key)

    if unknown_fields:
        return ProtectionPayloadValidation(
            status=ProtectionStatus.PROTECTION_NOT_VERIFIED,
            chain=dict(payload),
            errors=["unknown_fields_present"],
            unknown_fields=unknown_fields,
        )

    for stage in PROTECTION_CHAIN_STAGES:
        if stage not in payload:
            errors.append(f"missing_chain_stage:{stage}")
        elif not payload[stage]:
            errors.append(f"empty_chain_stage:{stage}")

    if payload.get("tradeMode") != "Isolated":
        errors.append(f"trade_mode_must_be_isolated:{payload.get('tradeMode')}")

    try:
        lev = int(payload.get("leverage", 0))
        if lev != FIXED_LEVERAGE:
            errors.append(f"leverage_must_be_{FIXED_LEVERAGE}:{lev}")
    except (TypeError, ValueError):
        errors.append(f"invalid_leverage:{payload.get('leverage')}")

    sl = payload.get("stopLoss")
    tp = payload.get("takeProfit")
    if not sl:
        errors.append("stop_loss_missing")
    if not tp:
        errors.append("take_profit_missing")

    verified_block = payload.get("verified") or {}
    if not verified_block.get("protection_attached"):
        errors.append("protection_not_attached")
    if verified_block.get("dry_run_only") is not True:
        errors.append("dry_run_only_required")

    status = (
        ProtectionStatus.VERIFIED
        if not errors
        else ProtectionStatus.PROTECTION_NOT_VERIFIED
    )
    return ProtectionPayloadValidation(
        status=status,
        chain=dict(payload),
        errors=errors,
        unknown_fields=unknown_fields,
    )


def _redact_chain(chain: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in chain.items():
        if isinstance(value, dict):
            redacted[key] = {
                k: "[REDACTED]" if "secret" in k.lower() else v
                for k, v in value.items()
            }
        else:
            redacted[key] = value
    return redacted
