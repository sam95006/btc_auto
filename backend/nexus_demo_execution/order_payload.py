"""Demo order payload validation — structure only, never POST."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.nexus_demo_execution import FIXED_LEVERAGE
from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL, DemoDomainPolicy


class OrderPayloadStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    DOMAIN_REJECTED = "DOMAIN_REJECTED"


REQUIRED_ORDER_FIELDS = frozenset(
    {
        "category",
        "symbol",
        "side",
        "orderType",
        "qty",
        "positionIdx",
        "tradeMode",
        "leverage",
    }
)

ALLOWED_CATEGORIES = frozenset({"linear"})
ALLOWED_SIDES = frozenset({"Buy", "Sell"})
ALLOWED_ORDER_TYPES = frozenset({"Market", "Limit"})
REQUIRED_TRADE_MODE = "Isolated"


@dataclass
class OrderPayloadValidation:
    status: OrderPayloadStatus
    payload: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    domain: str = DEMO_REST_BASE_URL

    @property
    def valid(self) -> bool:
        return self.status == OrderPayloadStatus.VALID

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "valid": self.valid,
            "errors": list(self.errors),
            "domain": self.domain,
            "payload": _redact_payload(self.payload),
        }


def build_demo_order_payload(
    *,
    symbol: str,
    side: str,
    qty: float,
    margin_usdt: float,
    leverage: int = FIXED_LEVERAGE,
    order_type: str = "Market",
) -> dict[str, Any]:
    """Build a demo order payload for validation — never sent to exchange."""
    return {
        "category": "linear",
        "symbol": symbol,
        "side": side,
        "orderType": order_type,
        "qty": str(qty),
        "positionIdx": 0,
        "tradeMode": REQUIRED_TRADE_MODE,
        "leverage": str(leverage),
        "margin_usdt": margin_usdt,
        "domain": DEMO_REST_BASE_URL,
        "dry_run_only": True,
    }


def validate_demo_order_payload(payload: dict[str, Any] | None) -> OrderPayloadValidation:
    """Validate demo order payload structure without POST."""
    if payload is None:
        return OrderPayloadValidation(
            status=OrderPayloadStatus.INVALID,
            errors=["payload_missing"],
        )

    errors: list[str] = []
    domain = str(payload.get("domain") or DEMO_REST_BASE_URL)

    try:
        DemoDomainPolicy.validate_base_url(domain)
    except Exception as exc:
        return OrderPayloadValidation(
            status=OrderPayloadStatus.DOMAIN_REJECTED,
            payload=dict(payload),
            errors=[f"domain_rejected:{exc}"],
            domain=domain,
        )

    for field_name in REQUIRED_ORDER_FIELDS:
        if field_name not in payload:
            errors.append(f"missing_field:{field_name}")

    category = payload.get("category")
    if category and category not in ALLOWED_CATEGORIES:
        errors.append(f"invalid_category:{category}")

    side = payload.get("side")
    if side and side not in ALLOWED_SIDES:
        errors.append(f"invalid_side:{side}")

    order_type = payload.get("orderType")
    if order_type and order_type not in ALLOWED_ORDER_TYPES:
        errors.append(f"invalid_order_type:{order_type}")

    trade_mode = payload.get("tradeMode")
    if trade_mode != REQUIRED_TRADE_MODE:
        errors.append(f"trade_mode_must_be_isolated:{trade_mode}")

    leverage = payload.get("leverage")
    try:
        lev_int = int(str(leverage))
        if lev_int != FIXED_LEVERAGE:
            errors.append(f"leverage_must_be_{FIXED_LEVERAGE}:{lev_int}")
    except (TypeError, ValueError):
        errors.append(f"invalid_leverage:{leverage}")

    qty = payload.get("qty")
    try:
        if float(str(qty)) <= 0:
            errors.append("qty_must_be_positive")
    except (TypeError, ValueError):
        errors.append(f"invalid_qty:{qty}")

    if payload.get("dry_run_only") is not True:
        errors.append("dry_run_only_required")

    status = OrderPayloadStatus.VALID if not errors else OrderPayloadStatus.INVALID
    return OrderPayloadValidation(
        status=status,
        payload=dict(payload),
        errors=errors,
        domain=domain,
    )


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(payload)
    for key in list(redacted):
        key_l = key.lower()
        if any(marker in key_l for marker in ("secret", "api_key", "password", "token")):
            redacted[key] = "[REDACTED]"
    return redacted
