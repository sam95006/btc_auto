"""Phase 6.2 — Canonical research environment resolver (fail-closed).

Single source of truth for autonomous mode, review engine, storage path,
and execution safety flags. Legacy variables never override canonical mode.
Secrets are never returned — only credential_present booleans.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Canonical modes ───────────────────────────────────────────────────────────
MODE_OFF = "OFF"
MODE_SHADOW = "SHADOW"
MODE_PAPER = "PAPER"
_VALID_AUTONOMOUS = {MODE_OFF, MODE_SHADOW, MODE_PAPER}
_DEFAULT_AUTONOMOUS = MODE_SHADOW

REVIEW_RULES_ONLY = "RULES_ONLY"
REVIEW_LLM_ASSISTED = "LLM_ASSISTED"
REVIEW_DISABLED = "DISABLED"
_VALID_REVIEW = {REVIEW_RULES_ONLY, REVIEW_LLM_ASSISTED, REVIEW_DISABLED}
_DEFAULT_REVIEW = REVIEW_RULES_ONLY

# ── Env names ─────────────────────────────────────────────────────────────────
ENV_AUTONOMOUS = "NEXUS_AUTONOMOUS_RESEARCH_MODE"
ENV_REVIEW = "NEXUS_REVIEW_ENGINE_MODE"
ENV_DATA_DIR = "NEXUS_DATA_DIR"

LEGACY_AUTONOMOUS_ONLY = (
    "PAPER_ONLY",
    "NEXUS_PAPER_ONLY",
    "BYBIT_SHADOW_MODE",
    "NEXUS_BYBIT_SHADOW_MODE",
    "NEXUS_STAGE2_SHADOW_MODE",
    "NEXUS_EMBEDDED_WORKER",
)

GLOBAL_SAFETY_FLAGS = (
    "RESEARCH_ONLY",
    "NEXUS_RESEARCH_ONLY",
    "LIVE_TRADING",
    "NEXUS_LIVE_TRADING",
    "REAL_MONEY",
    "NEXUS_REAL_MONEY",
    "ARM_ALLOWED",
    "NEXUS_ARM_ALLOWED",
    "PRODUCTION_PROMOTION_ALLOWED",
    "NEXUS_PRODUCTION_PROMOTION_ALLOWED",
    "BYBIT_MAINNET_ALLOWED",
    "PRIVATE_ORDER_ENDPOINT_BLOCKED",
    "ORDER_ALLOWED",
    "NEXUS_ORDER_ALLOWED",
    "EXCHANGE_WRITE_ALLOWED",
)

_SECRET_ENV_NAMES = (
    "BYBIT_API_KEY",
    "BYBIT_API_SECRET",
    "BYBIT_DEMO_API_KEY",
    "BYBIT_DEMO_API_SECRET",
    "NEXUS_BYBIT_API_KEY",
    "NEXUS_BYBIT_API_SECRET",
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

_LOCK = threading.RLock()
_CACHE: dict[str, Any] | None = None
_CACHE_TS = 0.0
_CACHE_TTL_SEC = 5.0


def _truthy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in ("1", "true", "yes", "on", "y")


def _falsy(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in ("0", "false", "no", "off", "n")


def _env_present(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _credential_present(names: tuple[str, ...]) -> bool:
    return any(_env_present(n) for n in names)


def _setting(
    *,
    value: Any,
    source: str,
    is_default: bool = False,
    conflict: bool = False,
    fail_closed: bool = False,
) -> dict[str, Any]:
    return {
        "effective": value,
        "source": source,
        "isDefault": is_default,
        "conflict": conflict,
        "failClosed": fail_closed,
    }


def resolve_autonomous_mode() -> dict[str, Any]:
    """Canonical autonomous mode. Legacy vars never override; conflicts fail closed to SHADOW/OFF."""
    conflicts: list[str] = []
    raw = (os.getenv(ENV_AUTONOMOUS) or "").strip().upper()
    if raw in _VALID_AUTONOMOUS:
        mode = raw
        source = ENV_AUTONOMOUS
        is_default = False
    elif raw:
        conflicts.append(f"invalid_{ENV_AUTONOMOUS}={raw}")
        mode = _DEFAULT_AUTONOMOUS
        source = "default_after_invalid"
        is_default = True
    else:
        mode = _DEFAULT_AUTONOMOUS
        source = "default"
        is_default = True

    # Legacy may only tighten safety — never unlock PAPER.
    paper_only = _truthy(os.getenv("PAPER_ONLY")) or _truthy(os.getenv("NEXUS_PAPER_ONLY"))
    if paper_only and mode == MODE_PAPER:
        # PAPER_ONLY historically meant paper, but Phase 6.2 keeps SHADOW until explicit canonical PAPER.
        conflicts.append("legacy_PAPER_ONLY_present_while_canonical_PAPER")
        mode = MODE_SHADOW
        source = "fail_closed_legacy_conflict"
        is_default = False

    live = _truthy(os.getenv("LIVE_TRADING")) or _truthy(os.getenv("NEXUS_LIVE_TRADING"))
    real_money = _truthy(os.getenv("REAL_MONEY")) or _truthy(os.getenv("NEXUS_REAL_MONEY"))
    if (live or real_money) and mode == MODE_PAPER:
        conflicts.append("live_or_real_money_blocks_paper")
        mode = MODE_SHADOW
        source = "fail_closed_execution_flags"
        is_default = False

    return {
        **_setting(
            value=mode,
            source=source,
            is_default=is_default,
            conflict=bool(conflicts),
            fail_closed=bool(conflicts),
        ),
        "conflicts": conflicts,
    }


def resolve_review_engine_mode() -> dict[str, Any]:
    raw = (os.getenv(ENV_REVIEW) or "").strip().upper()
    if raw in _VALID_REVIEW:
        # Compromised credentials policy: do not auto-enable LLM_ASSISTED.
        if raw == REVIEW_LLM_ASSISTED:
            return {
                **_setting(
                    value=REVIEW_RULES_ONLY,
                    source="fail_closed_compromised_credentials_policy",
                    conflict=True,
                    fail_closed=True,
                ),
                "requested": raw,
            }
        return _setting(value=raw, source=ENV_REVIEW)
    if raw:
        return {
            **_setting(
                value=_DEFAULT_REVIEW,
                source="default_after_invalid",
                is_default=True,
                conflict=True,
                fail_closed=True,
            ),
            "requested": raw,
        }
    return _setting(value=_DEFAULT_REVIEW, source="default", is_default=True)


def resolve_research_db_path() -> dict[str, Any]:
    data_dir = (os.getenv(ENV_DATA_DIR) or "").strip() or "/data"
    root = f"{data_dir.rstrip('/')}/nexus-research"
    db = f"{root}/nexus_research.db"
    return {
        **_setting(
            value="nexus-research/nexus_research.db",
            source=ENV_DATA_DIR if (os.getenv(ENV_DATA_DIR) or "").strip() else "default_/data",
            is_default=not bool((os.getenv(ENV_DATA_DIR) or "").strip()),
        ),
        "dataDirConfigured": bool((os.getenv(ENV_DATA_DIR) or "").strip()),
        "pathRedacted": db if data_dir == "/data" else "REDACTED/nexus_research.db",
    }


def resolve_execution_safety() -> dict[str, Any]:
    live = _truthy(os.getenv("LIVE_TRADING")) or _truthy(os.getenv("NEXUS_LIVE_TRADING"))
    real_money = _truthy(os.getenv("REAL_MONEY")) or _truthy(os.getenv("NEXUS_REAL_MONEY"))
    arm = _truthy(os.getenv("ARM_ALLOWED")) or _truthy(os.getenv("NEXUS_ARM_ALLOWED"))
    promo = _truthy(os.getenv("PRODUCTION_PROMOTION_ALLOWED")) or _truthy(
        os.getenv("NEXUS_PRODUCTION_PROMOTION_ALLOWED")
    )
    mainnet = _truthy(os.getenv("BYBIT_MAINNET_ALLOWED"))
    order_allowed = _truthy(os.getenv("ORDER_ALLOWED")) or _truthy(os.getenv("NEXUS_ORDER_ALLOWED"))
    exchange_write = _truthy(os.getenv("EXCHANGE_WRITE_ALLOWED"))
    private_blocked_raw = os.getenv("PRIVATE_ORDER_ENDPOINT_BLOCKED")
    private_blocked = True if private_blocked_raw is None or private_blocked_raw == "" else _truthy(private_blocked_raw)
    if _falsy(private_blocked_raw):
        private_blocked = False

    research_only = True
    if _falsy(os.getenv("RESEARCH_ONLY")) and _falsy(os.getenv("NEXUS_RESEARCH_ONLY")):
        # Missing or false research-only → still force research-only this phase.
        research_only = True

    unsafe = any([live, real_money, arm, promo, mainnet, order_allowed, exchange_write, not private_blocked])
    return {
        "researchOnly": _setting(value=research_only, source="forced_phase62", fail_closed=True),
        "liveTrading": _setting(value=False if live else False, source="fail_closed" if live else "env_or_default", conflict=live, fail_closed=True),
        "liveTradingRequested": live,
        "realMoney": _setting(value=False, source="fail_closed" if real_money else "env_or_default", conflict=real_money, fail_closed=True),
        "realMoneyRequested": real_money,
        "armAllowed": _setting(value=False, source="fail_closed" if arm else "env_or_default", conflict=arm, fail_closed=True),
        "productionPromotion": _setting(value=False, source="fail_closed" if promo else "env_or_default", conflict=promo, fail_closed=True),
        "bybitMainnetAllowed": _setting(value=False, source="fail_closed" if mainnet else "env_or_default", conflict=mainnet, fail_closed=True),
        "exchangeWrite": _setting(value=False, source="fail_closed", conflict=exchange_write or order_allowed, fail_closed=True),
        "privateOrderEndpointBlocked": _setting(
            value=True,
            source="fail_closed" if not private_blocked else "env_or_default",
            conflict=not private_blocked,
            fail_closed=True,
        ),
        "realExecutionEffective": False,
        "privateExchangeUseEffective": False,
        "unsafeFlagsDetected": unsafe,
    }


def resolve_stage4_runtime_patch() -> dict[str, Any]:
    raw = (os.getenv("STAGE4_APPLY_RUNTIME_PATCH") or "").strip().lower()
    effective = raw in ("1", "true", "yes", "on")
    return _setting(
        value=effective,
        source="STAGE4_APPLY_RUNTIME_PATCH" if raw else "default_false",
        is_default=not bool(raw),
        conflict=False,
        fail_closed=effective,  # blocks SAFE_PAPER_PRECHECK when true
    )


def resolve_limits() -> dict[str, Any]:
    def _num(name: str, default: float) -> dict[str, Any]:
        raw = (os.getenv(name) or "").strip()
        if not raw:
            return _setting(value=default, source="default", is_default=True)
        try:
            return _setting(value=float(raw) if "." in raw else int(raw), source=name)
        except ValueError:
            return _setting(value=default, source="default_after_invalid", is_default=True, conflict=True)

    return {
        "maxLeverage": _num("MAX_LEVERAGE", 3),
        "maxMarginUsd": _num("MAX_MARGIN_USD", 20),
        "maxOpenPositions": _num("MAX_OPEN_POSITIONS", 1),
    }


def list_legacy_variables() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in LEGACY_AUTONOMOUS_ONLY + GLOBAL_SAFETY_FLAGS:
        present = _env_present(name)
        out.append({
            "name": name,
            "present": present,
            "classification": (
                "legacy_autonomous"
                if name in LEGACY_AUTONOMOUS_ONLY
                else "global_safety"
            ),
            # Never expose values
            "valueRedacted": True,
        })
    return out


def credential_presence() -> dict[str, bool]:
    return {
        "bybitCredentialPresent": _credential_present(
            ("BYBIT_API_KEY", "BYBIT_DEMO_API_KEY", "NEXUS_BYBIT_API_KEY")
        ),
        "groqCredentialPresent": _credential_present(("GROQ_API_KEY",)),
        "cerebrasCredentialPresent": _credential_present(("CEREBRAS_API_KEY",)),
        "llmCredentialPresent": _credential_present(
            ("GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        ),
    }


def compute_startup_safety_verdict(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return startup safety verdict. Phase 6.2 stays SHADOW; PAPER precheck is advisory only."""
    ctx = context or {}
    conflicts = list(ctx.get("conflicts") or [])
    durable = bool(ctx.get("durableClaim", False))
    restart_proof = bool(ctx.get("restartProof", False))
    owners_ok = all(
        int(ctx.get(k) or 0) == 1
        for k in ("runtimeOwnerCount", "schedulerOwnerCount", "scannerOwnerCount", "ledgerOwnerCount")
    )
    exec_safe = bool(ctx.get("executionSafe", True))
    storage_ok = bool(ctx.get("storageHealthy", durable))
    stage4_patch = bool(ctx.get("stage4RuntimePatchEffective", False))
    capacity_ok = bool(ctx.get("naturalActiveCapacityAvailable", True))
    ledger_ok = bool(ctx.get("ledgerHealthy", True))
    risk_ok = bool(ctx.get("riskEngineHealthy", True))
    capital_ok = bool(ctx.get("capitalAllocatorHealthy", True))
    sim_ok = bool(ctx.get("simulatorHealthy", True))

    if conflicts and not exec_safe:
        verdict = "BLOCKED_CONFIG_CONFLICT"
    elif not storage_ok:
        verdict = "BLOCKED_STORAGE"
    elif not exec_safe:
        verdict = "BLOCKED_EXECUTION_FLAGS"
    elif not owners_ok:
        verdict = "BLOCKED_RUNTIME_OWNERSHIP"
    else:
        paper_ready = all(
            [
                durable,
                restart_proof,
                owners_ok,
                exec_safe,
                not stage4_patch,
                capacity_ok,
                ledger_ok,
                risk_ok,
                capital_ok,
                sim_ok,
                not conflicts,
            ]
        )
        verdict = "SAFE_PAPER_PRECHECK" if paper_ready else "SAFE_SHADOW"

    return {
        "verdict": verdict,
        "safeShadow": verdict in ("SAFE_SHADOW", "SAFE_PAPER_PRECHECK"),
        "paperPrecheckEligible": verdict == "SAFE_PAPER_PRECHECK",
        "stage4RuntimePatchBlocksPaper": stage4_patch,
        "conflicts": conflicts,
        "checks": {
            "durableClaim": durable,
            "restartProof": restart_proof,
            "runtimeOwnership": owners_ok,
            "executionSafe": exec_safe,
            "storageHealthy": storage_ok,
            "stage4RuntimePatchEffective": stage4_patch,
            "naturalActiveCapacityAvailable": capacity_ok,
            "ledgerHealthy": ledger_ok,
            "riskEngineHealthy": risk_ok,
            "capitalAllocatorHealthy": capital_ok,
            "simulatorHealthy": sim_ok,
        },
    }


def get_effective_config(*, refresh: bool = False, runtime_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build redacted effective config snapshot for /api/nexus/config/effective."""
    global _CACHE, _CACHE_TS
    now = time.time()
    with _LOCK:
        if not refresh and _CACHE is not None and (now - _CACHE_TS) < _CACHE_TTL_SEC and runtime_context is None:
            return dict(_CACHE)

    autonomous = resolve_autonomous_mode()
    review = resolve_review_engine_mode()
    storage = resolve_research_db_path()
    execution = resolve_execution_safety()
    stage4 = resolve_stage4_runtime_patch()
    limits = resolve_limits()
    legacy = list_legacy_variables()
    creds = credential_presence()

    conflicts = list(autonomous.get("conflicts") or [])
    if review.get("conflict"):
        conflicts.append("review_engine_mode_conflict")
    if execution.get("unsafeFlagsDetected"):
        conflicts.append("unsafe_execution_flags")

    ctx = {
        "conflicts": conflicts,
        "executionSafe": not execution.get("unsafeFlagsDetected"),
        "stage4RuntimePatchEffective": bool(stage4.get("effective")),
        **(runtime_context or {}),
    }
    # Fill defaults for ownership/storage if not provided
    for k, default in (
        ("durableClaim", True),
        ("restartProof", True),
        ("runtimeOwnerCount", 1),
        ("schedulerOwnerCount", 1),
        ("scannerOwnerCount", 1),
        ("ledgerOwnerCount", 1),
        ("storageHealthy", True),
        ("naturalActiveCapacityAvailable", True),
        ("ledgerHealthy", True),
        ("riskEngineHealthy", True),
        ("capitalAllocatorHealthy", True),
        ("simulatorHealthy", True),
    ):
        ctx.setdefault(k, default)

    verdict = compute_startup_safety_verdict(ctx)

    data = {
        "ok": True,
        "researchOnly": True,
        "privateApi": False,
        "autonomousMode": autonomous,
        "reviewEngineMode": review,
        "storage": storage,
        "storageMode": _setting(
            value="SQLITE_PERSISTENT_VOLUME" if ctx.get("durableClaim") else "UNKNOWN",
            source="runtime",
        ),
        "durableClaim": _setting(value=bool(ctx.get("durableClaim")), source="runtime"),
        "execution": execution,
        "limits": limits,
        "stage4RuntimePatch": stage4,
        "legacyVariables": legacy,
        "credentials": {k: bool(v) for k, v in creds.items()},  # presence only
        "startupSafetyVerdict": verdict,
        "paperModeEnabled": autonomous.get("effective") == MODE_PAPER,
        "realExecutionEffective": False,
        "privateExchangeUseEffective": False,
        "compromisedCredentialsPolicy": "never_use_chat_exposed_keys; rotate_before_llm_or_private_api",
        "generatedAt": int(time.time() * 1000),
    }
    with _LOCK:
        _CACHE = dict(data)
        _CACHE_TS = now
    return data


def read_autonomous_mode() -> str:
    """Convenience for paper_controller / bootstrap."""
    return str(resolve_autonomous_mode()["effective"])
