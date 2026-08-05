"""Deterministic cost model with exact-decimal accounting — CANONICAL AUTHORITY.

Canonical module (exactly one for Private Core Session / strategy / replay /
execution / reporting cost formulas):

  ``backend.nexus_execution.cost_model``

Every cost component is computed as a :class:`decimal.Decimal` so the cost
bridge equation

    gross_pnl - entry_fee - exit_fee - spread_cost - slippage_cost
              - funding_cost - partial_fill_cost - cancel_replace_cost
    == net_pnl

holds exactly, not within a floating-point tolerance.

Cost components:
  * ``entry_fee``            fee for opening leg (maker or taker)
  * ``exit_fee``             fee for closing leg (maker or taker)
  * ``spread_cost``          notional * spread_bps
  * ``slippage_cost``        notional * slippage_bps for taker legs only
  * ``funding_cost``         signed; positive = debit, negative = credit
  * ``partial_fill_cost``    fixed penalty per additional fill event
  * ``cancel_replace_cost``  fixed penalty per cancel/replace cycle

Compat shims (strategy cost_semantics, demo geometry, autonomy V1.1 sim) MUST
delegate formula work here. They may label evidence sources or add explicitly
named non-bridge policy buffers, but MUST NOT invent parallel fee/spread/
slippage/funding/net-PnL equations.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any, Iterable, Mapping

from backend.nexus_execution.contracts import CostBridge, InstrumentSpec

BPS = Decimal("10000")

# Founder-conservative defaults (linear scale, no exchange-specific tiering).
DEFAULT_MAKER_FEE = Decimal("0.0002")
DEFAULT_TAKER_FEE = Decimal("0.00055")
DEFAULT_SPREAD_BPS = Decimal("1.0")
DEFAULT_SLIPPAGE_BPS = Decimal("2.0")
DEFAULT_PARTIAL_FILL_PENALTY = Decimal("0.005")   # USDT per extra fill event
DEFAULT_CANCEL_REPLACE_PENALTY = Decimal("0.01")  # USDT per cancel/replace cycle
# Conservative funding debit proxy when PIT funding is unavailable (per hold window).
DEFAULT_FUNDING_UNAVAILABLE_BUFFER_RATE = Decimal("0.0001")
# Explicit non-bridge policy buffer (demo/pretrade gates only; not part of CostBridge).
DEFAULT_COST_UNCERTAINTY_BUFFER_RATE = Decimal("0.0002")

COST_MODEL_VERSION = "founder-conservative-v1-1-2026-08-05"
COST_MODEL_SCHEMA = "nexus_cost_model_contract_v1"
CANONICAL_COST_AUTHORITY = "backend.nexus_execution.cost_model"
CANONICAL_COST_AUTHORITY_COUNT = 1

# Legacy / research-proxy labels that must migrate onto COST_MODEL_VERSION.
LEGACY_COST_MODEL_VERSIONS: frozenset[str] = frozenset(
    {
        "NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1",
        "founder-conservative-v1-2026-07-31",
        "founder-conservative-v1",
        "replay-only",
    }
)

COMPATIBLE_COST_MODEL_VERSIONS: frozenset[str] = frozenset(
    {COST_MODEL_VERSION} | set(LEGACY_COST_MODEL_VERSIONS)
)

COST_BRIDGE_COMPONENT_KEYS: tuple[str, ...] = (
    "gross_pnl",
    "entry_fee",
    "exit_fee",
    "spread_cost",
    "slippage_cost",
    "funding_cost",
    "partial_fill_cost",
    "cancel_replace_cost",
    "net_pnl",
)


class CostModelVersionError(ValueError):
    """Raised when a cost-model version is incompatible or unknown."""


class CostBridgeFailure(ValueError):
    """Raised when a cost bridge fails exact-decimal reconciliation."""


@dataclass(frozen=True, slots=True)
class CostModelContract:
    """Versioned authority contract for Session / strategy / replay cost math."""

    version: str = COST_MODEL_VERSION
    schema: str = COST_MODEL_SCHEMA
    authority: str = CANONICAL_COST_AUTHORITY
    maker_fee: Decimal = DEFAULT_MAKER_FEE
    taker_fee: Decimal = DEFAULT_TAKER_FEE
    spread_bps: Decimal = DEFAULT_SPREAD_BPS
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS
    partial_fill_penalty: Decimal = DEFAULT_PARTIAL_FILL_PENALTY
    cancel_replace_penalty: Decimal = DEFAULT_CANCEL_REPLACE_PENALTY
    funding_unavailable_buffer_rate: Decimal = DEFAULT_FUNDING_UNAVAILABLE_BUFFER_RATE
    cost_uncertainty_buffer_rate: Decimal = DEFAULT_COST_UNCERTAINTY_BUFFER_RATE

    def validate(self) -> None:
        validate_cost_model_version(self.version, allow_legacy=False)
        if self.authority != CANONICAL_COST_AUTHORITY:
            raise CostModelVersionError(
                f"authority_mismatch expected={CANONICAL_COST_AUTHORITY} got={self.authority}"
            )
        if self.schema != COST_MODEL_SCHEMA:
            raise CostModelVersionError(
                f"schema_mismatch expected={COST_MODEL_SCHEMA} got={self.schema}"
            )
        for name in (
            "maker_fee",
            "taker_fee",
            "spread_bps",
            "slippage_bps",
            "partial_fill_penalty",
            "cancel_replace_penalty",
            "funding_unavailable_buffer_rate",
            "cost_uncertainty_buffer_rate",
        ):
            val = getattr(self, name)
            if not isinstance(val, Decimal):
                raise CostModelVersionError(f"{name}_must_be_Decimal")
            if val < 0:
                raise CostModelVersionError(f"{name}_must_be_non_negative")

    def to_dict(self) -> dict[str, str]:
        return {
            "version": self.version,
            "schema": self.schema,
            "authority": self.authority,
            "maker_fee": format(self.maker_fee, "f"),
            "taker_fee": format(self.taker_fee, "f"),
            "spread_bps": format(self.spread_bps, "f"),
            "slippage_bps": format(self.slippage_bps, "f"),
            "partial_fill_penalty": format(self.partial_fill_penalty, "f"),
            "cancel_replace_penalty": format(self.cancel_replace_penalty, "f"),
            "funding_unavailable_buffer_rate": format(self.funding_unavailable_buffer_rate, "f"),
            "cost_uncertainty_buffer_rate": format(self.cost_uncertainty_buffer_rate, "f"),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CostModelContract":
        required = {f.name for f in fields(cls)}
        missing = required - set(payload.keys())
        if missing:
            raise CostModelVersionError(f"serialization_missing_keys={sorted(missing)}")
        version = migrate_cost_model_version(str(payload["version"]))
        return cls(
            version=version,
            schema=str(payload["schema"]),
            authority=str(payload["authority"]),
            maker_fee=Decimal(str(payload["maker_fee"])),
            taker_fee=Decimal(str(payload["taker_fee"])),
            spread_bps=Decimal(str(payload["spread_bps"])),
            slippage_bps=Decimal(str(payload["slippage_bps"])),
            partial_fill_penalty=Decimal(str(payload["partial_fill_penalty"])),
            cancel_replace_penalty=Decimal(str(payload["cancel_replace_penalty"])),
            funding_unavailable_buffer_rate=Decimal(
                str(payload["funding_unavailable_buffer_rate"])
            ),
            cost_uncertainty_buffer_rate=Decimal(str(payload["cost_uncertainty_buffer_rate"])),
        )


DEFAULT_COST_MODEL_CONTRACT = CostModelContract()


def get_cost_model_contract() -> CostModelContract:
    """Return the live canonical contract (singleton defaults)."""
    DEFAULT_COST_MODEL_CONTRACT.validate()
    return DEFAULT_COST_MODEL_CONTRACT


def validate_cost_model_version(version: str | None, *, allow_legacy: bool = True) -> str:
    """Validate and normalize a cost-model version string.

    When ``allow_legacy`` is True, known legacy labels are accepted but must be
    migrated before use as Session authority evidence.
    """
    if version is None or str(version).strip() == "":
        raise CostModelVersionError("cost_model_version_missing")
    raw = str(version).strip()
    if raw == COST_MODEL_VERSION:
        return raw
    if allow_legacy and raw in LEGACY_COST_MODEL_VERSIONS:
        return raw
    if raw in COMPATIBLE_COST_MODEL_VERSIONS:
        return raw
    raise CostModelVersionError(f"incompatible_cost_model_version={raw!r}")


def migrate_cost_model_version(version: str | None) -> str:
    """Map legacy / proxy labels onto the canonical COST_MODEL_VERSION."""
    raw = validate_cost_model_version(version, allow_legacy=True)
    if raw == COST_MODEL_VERSION:
        return raw
    if raw in LEGACY_COST_MODEL_VERSIONS:
        return COST_MODEL_VERSION
    raise CostModelVersionError(f"unmigratable_cost_model_version={raw!r}")


def versions_compatible(a: str | None, b: str | None) -> bool:
    """True iff both versions migrate to the same canonical version."""
    try:
        return migrate_cost_model_version(a) == migrate_cost_model_version(b)
    except CostModelVersionError:
        return False


def serialize_cost_bridge(bridge: CostBridge) -> dict[str, str]:
    """Serialize a CostBridge under the canonical schema."""
    if not bridge.verify():
        raise CostBridgeFailure("cost_bridge_verify_failed_before_serialize")
    payload = bridge.as_dict()
    payload["cost_model_version"] = COST_MODEL_VERSION
    payload["schema"] = COST_MODEL_SCHEMA
    payload["authority"] = CANONICAL_COST_AUTHORITY
    return payload


def deserialize_cost_bridge(payload: Mapping[str, Any]) -> CostBridge:
    """Deserialize and verify a CostBridge; migrate legacy version labels."""
    missing = [k for k in COST_BRIDGE_COMPONENT_KEYS if k not in payload]
    if missing:
        raise CostBridgeFailure(f"cost_bridge_missing_keys={missing}")
    version = payload.get("cost_model_version")
    if version is not None:
        migrate_cost_model_version(str(version))
    bridge = CostBridge(
        gross_pnl=Decimal(str(payload["gross_pnl"])),
        entry_fee=Decimal(str(payload["entry_fee"])),
        exit_fee=Decimal(str(payload["exit_fee"])),
        spread_cost=Decimal(str(payload["spread_cost"])),
        slippage_cost=Decimal(str(payload["slippage_cost"])),
        funding_cost=Decimal(str(payload["funding_cost"])),
        partial_fill_cost=Decimal(str(payload["partial_fill_cost"])),
        cancel_replace_cost=Decimal(str(payload["cancel_replace_cost"])),
        net_pnl=Decimal(str(payload["net_pnl"])),
    )
    if not bridge.verify():
        raise CostBridgeFailure("cost_bridge_verify_failed_after_deserialize")
    return bridge


def _bps_cost(notional: Decimal, bps: Decimal) -> Decimal:
    return (notional * bps / BPS)


def _as_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def entry_leg_cost(
    spec: InstrumentSpec,
    *,
    price: Decimal,
    qty: Decimal,
    is_taker: bool,
    spread_bps: Decimal = DEFAULT_SPREAD_BPS,
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(fee, spread, slippage)`` for the opening leg."""
    notional = price * qty
    fee_rate = spec.taker_fee if is_taker else spec.maker_fee
    fee = notional * fee_rate
    spread = _bps_cost(notional, spread_bps)
    slippage = _bps_cost(notional, slippage_bps) if is_taker else Decimal(0)
    return (fee, spread, slippage)


def exit_leg_cost(
    spec: InstrumentSpec,
    *,
    price: Decimal,
    qty: Decimal,
    is_taker: bool,
    spread_bps: Decimal = DEFAULT_SPREAD_BPS,
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(fee, spread, slippage)`` for the closing leg (same shape)."""
    return entry_leg_cost(
        spec,
        price=price,
        qty=qty,
        is_taker=is_taker,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
    )


def funding_component(
    *,
    notional: Decimal,
    funding_rate: Decimal,
    intervals: int,
) -> Decimal:
    """Signed funding: positive means the position owes funding (debit)."""
    if intervals <= 0 or funding_rate == 0:
        return Decimal(0)
    return notional * funding_rate * Decimal(intervals)


def funding_unavailable_buffer(*, notional: Decimal) -> Decimal:
    """Conservative positive debit when PIT funding is unavailable."""
    return abs(notional) * DEFAULT_FUNDING_UNAVAILABLE_BUFFER_RATE


def cost_uncertainty_buffer(*, notional: Decimal) -> Decimal:
    """Non-bridge demo/pretrade uncertainty buffer (explicitly labeled)."""
    return abs(notional) * DEFAULT_COST_UNCERTAINTY_BUFFER_RATE


def partial_fill_component(*, extra_fills: int) -> Decimal:
    """Penalty for splitting the notional across multiple fills."""
    if extra_fills <= 0:
        return Decimal(0)
    return DEFAULT_PARTIAL_FILL_PENALTY * Decimal(extra_fills)


def cancel_replace_component(*, cycles: int) -> Decimal:
    if cycles <= 0:
        return Decimal(0)
    return DEFAULT_CANCEL_REPLACE_PENALTY * Decimal(cycles)


def compose_cost_bridge(
    *,
    side: str,  # LONG | SHORT
    qty: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
    entry_fee: Decimal,
    exit_fee: Decimal,
    entry_spread: Decimal,
    exit_spread: Decimal,
    entry_slippage: Decimal,
    exit_slippage: Decimal,
    funding: Decimal,
    partial_fill: Decimal,
    cancel_replace: Decimal,
) -> CostBridge:
    """Assemble an :class:`~contracts.CostBridge` from atomic legs.

    ``side`` uses LONG/SHORT (position semantics), not BUY/SELL.
    """
    sign = Decimal(1) if side.upper() == "LONG" else Decimal(-1)
    gross_pnl = (exit_price - entry_price) * qty * sign
    spread_cost = entry_spread + exit_spread
    slippage_cost = entry_slippage + exit_slippage
    net_pnl = (
        gross_pnl
        - entry_fee
        - exit_fee
        - spread_cost
        - slippage_cost
        - funding
        - partial_fill
        - cancel_replace
    )
    bridge = CostBridge(
        gross_pnl=gross_pnl,
        entry_fee=entry_fee,
        exit_fee=exit_fee,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        funding_cost=funding,
        partial_fill_cost=partial_fill,
        cancel_replace_cost=cancel_replace,
        net_pnl=net_pnl,
    )
    if not bridge.verify():
        raise CostBridgeFailure("compose_cost_bridge_invariant_broken")
    return bridge


def net_pnl_from_components(
    *,
    gross_pnl: Decimal,
    entry_fee: Decimal,
    exit_fee: Decimal,
    spread_cost: Decimal,
    slippage_cost: Decimal,
    funding_cost: Decimal,
    partial_fill_cost: Decimal = Decimal(0),
    cancel_replace_cost: Decimal = Decimal(0),
) -> Decimal:
    """Canonical net-PnL formula — sole authority for this identity."""
    return (
        gross_pnl
        - entry_fee
        - exit_fee
        - spread_cost
        - slippage_cost
        - funding_cost
        - partial_fill_cost
        - cancel_replace_cost
    )


def leg_costs_for_notional(
    *,
    notional: Decimal,
    is_taker: bool,
    fee_rate: Decimal | None = None,
    spread_bps: Decimal = DEFAULT_SPREAD_BPS,
    slippage_bps: Decimal = DEFAULT_SLIPPAGE_BPS,
) -> dict[str, Decimal]:
    """Single-leg fee/spread/slippage from notional (compat float bridges use this)."""
    rate = fee_rate if fee_rate is not None else (
        DEFAULT_TAKER_FEE if is_taker else DEFAULT_MAKER_FEE
    )
    fee = notional * rate
    spread = _bps_cost(notional, spread_bps)
    slippage = _bps_cost(notional, slippage_bps) if is_taker else Decimal(0)
    return {
        "fee": fee,
        "entry_fee": fee,
        "spread_cost": spread,
        "slippage_cost": slippage,
        "fee_rate": rate,
    }


def estimate_round_trip_costs(
    *,
    notional: Decimal | float,
    fee_rate: Decimal | float,
    spread_bps: Decimal | float,
    slippage_bps: Decimal | float,
    funding_rate: Decimal | float | None,
    include_uncertainty_buffer: bool = False,
) -> dict[str, Decimal]:
    """Canonical pretrade / geometry round-trip cost estimate (exact Decimal).

    When ``funding_rate`` is None, applies ``funding_unavailable_buffer``.
    Uncertainty buffer is optional and labeled — not part of CostBridge.
    """
    n = abs(_as_decimal(notional))
    fr = _as_decimal(fee_rate)
    entry = leg_costs_for_notional(
        notional=n,
        is_taker=True,
        fee_rate=fr,
        spread_bps=_as_decimal(spread_bps),
        slippage_bps=_as_decimal(slippage_bps),
    )
    exit_ = leg_costs_for_notional(
        notional=n,
        is_taker=True,
        fee_rate=fr,
        spread_bps=_as_decimal(spread_bps),
        slippage_bps=_as_decimal(slippage_bps),
    )
    if funding_rate is None:
        funding = funding_unavailable_buffer(notional=n)
    else:
        funding = abs(n * _as_decimal(funding_rate))
    spread_cost = entry["spread_cost"] + exit_["spread_cost"]
    slippage_cost = entry["slippage_cost"] + exit_["slippage_cost"]
    # Demo geometry historically folded spread+slip into one "slippage" bucket.
    combined_market = spread_cost + slippage_cost
    uncertainty = cost_uncertainty_buffer(notional=n) if include_uncertainty_buffer else Decimal(0)
    total = entry["fee"] + exit_["fee"] + combined_market + funding + uncertainty
    return {
        "entry_fee": entry["fee"],
        "exit_fee": exit_["fee"],
        "spread_cost": spread_cost,
        "slippage_cost": slippage_cost,
        "slippage": combined_market,  # legacy demo key
        "funding": funding,
        "uncertainty": uncertainty,
        "total_cost": total,
    }


def estimate_round_trip_costs_float(
    *,
    notional: float,
    fee_rate: float,
    spread_bps: float,
    slippage_bps: float,
    funding_rate: float | None,
    include_uncertainty_buffer: bool = True,
) -> dict[str, float]:
    """Float façade for demo / research callers — math still from Decimal path."""
    raw = estimate_round_trip_costs(
        notional=notional,
        fee_rate=fee_rate,
        spread_bps=spread_bps,
        slippage_bps=slippage_bps,
        funding_rate=funding_rate,
        include_uncertainty_buffer=include_uncertainty_buffer,
    )
    return {
        "entry_fee": float(raw["entry_fee"]),
        "exit_fee": float(raw["exit_fee"]),
        "spread_cost": float(raw["spread_cost"]),
        "slippage_cost": float(raw["slippage_cost"]),
        "slippage": float(raw["slippage"]),
        "funding": float(raw["funding"]),
        "uncertainty": float(raw["uncertainty"]),
        "total_cost": float(raw["total_cost"]),
        "cost_model_version": COST_MODEL_VERSION,
    }


def apply_leg_costs_float(
    *,
    notional: float,
    is_taker: bool,
    fee_rate: float | None = None,
    spread_bps: float | None = None,
    slippage_bps: float | None = None,
) -> dict[str, float]:
    """Compat single-leg costs for autonomy V1.1 shim."""
    costs = leg_costs_for_notional(
        notional=_as_decimal(notional),
        is_taker=is_taker,
        fee_rate=_as_decimal(fee_rate) if fee_rate is not None else None,
        spread_bps=_as_decimal(spread_bps) if spread_bps is not None else DEFAULT_SPREAD_BPS,
        slippage_bps=(
            _as_decimal(slippage_bps) if slippage_bps is not None else DEFAULT_SLIPPAGE_BPS
        ),
    )
    return {
        "entry_fee": float(costs["entry_fee"]),
        "fee": float(costs["fee"]),
        "spread_cost": float(costs["spread_cost"]),
        "slippage_cost": float(costs["slippage_cost"]),
        "fee_rate": float(costs["fee_rate"]),
        "cost_model_version": COST_MODEL_VERSION,
    }


def net_pnl_float(
    *,
    gross_pnl: float,
    entry_fee: float,
    exit_fee: float,
    spread_cost: float,
    slippage_cost: float,
    funding_cost: float,
    partial_fill_cost: float = 0.0,
    cancel_replace_cost: float = 0.0,
) -> float:
    """Float façade for net PnL — delegates to canonical Decimal formula."""
    return float(
        net_pnl_from_components(
            gross_pnl=_as_decimal(gross_pnl),
            entry_fee=_as_decimal(entry_fee),
            exit_fee=_as_decimal(exit_fee),
            spread_cost=_as_decimal(spread_cost),
            slippage_cost=_as_decimal(slippage_cost),
            funding_cost=_as_decimal(funding_cost),
            partial_fill_cost=_as_decimal(partial_fill_cost),
            cancel_replace_cost=_as_decimal(cancel_replace_cost),
        )
    )


def sum_decimals(values: Iterable[Decimal]) -> Decimal:
    total = Decimal(0)
    for v in values:
        total = total + v
    return total


def detect_cost_formula_divergence(
    *,
    competitor_versions: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Detect version / authority divergence vs the canonical contract.

    ``competitor_versions`` maps module → declared COST_MODEL_VERSION.
    """
    findings: list[dict[str, Any]] = []
    competitors = dict(competitor_versions or {})
    for mod, ver in competitors.items():
        if ver is None:
            findings.append(
                {
                    "code": "COST_VERSION_MISSING",
                    "module": mod,
                    "severity": "high",
                }
            )
            continue
        if not versions_compatible(ver, COST_MODEL_VERSION):
            findings.append(
                {
                    "code": "COST_MODEL_VERSION_DIVERGENCE",
                    "module": mod,
                    "canonical": COST_MODEL_VERSION,
                    "competitor_version": ver,
                    "severity": "critical",
                }
            )
        elif ver != COST_MODEL_VERSION:
            # Legacy label still present — migration required for Session authority.
            findings.append(
                {
                    "code": "COST_MODEL_VERSION_LEGACY_LABEL",
                    "module": mod,
                    "canonical": COST_MODEL_VERSION,
                    "competitor_version": ver,
                    "severity": "medium",
                    "recommendation": "Re-export COST_MODEL_VERSION from cost_model",
                }
            )
    version_div = sum(
        1 for f in findings if f["code"] == "COST_MODEL_VERSION_DIVERGENCE"
    )
    return {
        "schema": "nexus_cost_formula_divergence_v1",
        "canonical_cost_authority": CANONICAL_COST_AUTHORITY,
        "canonical_cost_authority_count": CANONICAL_COST_AUTHORITY_COUNT,
        "cost_formula_divergence_count": version_div,  # version-formula coupling
        "cost_version_divergence_count": version_div,
        "findings": findings,
        "passed": version_div == 0 and CANONICAL_COST_AUTHORITY_COUNT == 1,
    }


def authority_metrics(
    *,
    bridge_failures: int = 0,
    formula_divergence_count: int = 0,
    version_divergence_count: int = 0,
) -> dict[str, Any]:
    """Required readiness metrics for V11.1 cost-model authority consolidation."""
    return {
        "canonical_cost_authority": CANONICAL_COST_AUTHORITY,
        "canonical_cost_authority_count": CANONICAL_COST_AUTHORITY_COUNT,
        "cost_model_version": COST_MODEL_VERSION,
        "cost_model_schema": COST_MODEL_SCHEMA,
        "cost_formula_divergence_count": int(formula_divergence_count),
        "cost_version_divergence_count": int(version_divergence_count),
        "cost_bridge_failure_count": int(bridge_failures),
        "passed": (
            CANONICAL_COST_AUTHORITY_COUNT == 1
            and int(formula_divergence_count) == 0
            and int(version_divergence_count) == 0
            and int(bridge_failures) == 0
        ),
    }


# Float aliases for legacy constant imports (must stay identical to Decimal defaults).
TAKER_FEE = float(DEFAULT_TAKER_FEE)
MAKER_FEE = float(DEFAULT_MAKER_FEE)
DEFAULT_SPREAD_BPS_FLOAT = float(DEFAULT_SPREAD_BPS)
DEFAULT_SLIPPAGE_BPS_FLOAT = float(DEFAULT_SLIPPAGE_BPS)
