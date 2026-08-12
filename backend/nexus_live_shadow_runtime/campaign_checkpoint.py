"""V18.2 Phase C — compact hourly campaign checkpoint (NOT git, NOT huge reports)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CHECKPOINT_SCHEMA = "v18_2_shadow_24h_checkpoint_v1"
CHECKPOINT_FIELDS: tuple[str, ...] = (
    "campaign_id",
    "campaign_state",
    "started_at",
    "elapsed",
    "heartbeat_age",
    "cycles_completed",
    "cycles_failed",
    "source_health",
    "data_lag",
    "contracts_seen",
    "eligible",
    "observe_only",
    "blocked",
    "candidates",
    "LONG",
    "SHORT",
    "WAIT",
    "ABSTAIN",
    "BLOCK",
    "shadow_opened",
    "shadow_closed",
    "AI_success",
    "AI_failure",
    "fallback",
    "runtime_restart_count",
    "safety_counters",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_compact_checkpoint(
    *,
    campaign_id: str,
    campaign_state: str,
    started_at: str,
    elapsed_sec: float,
    heartbeat_age_sec: float | None,
    metrics: dict[str, Any],
    source_health: str,
    data_lag_ms: int | None,
    safety_counters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the Founder-required compact hourly checkpoint payload."""
    m = metrics or {}
    ai_fail = int(m.get("AI_timeout") or 0) + int(m.get("AI_invalid_json") or 0)
    safety = safety_counters or {
        "actual_ordered_count": int(m.get("actual_ordered_count") or 0),
        "actual_filled_count": int(m.get("actual_filled_count") or 0),
        "busy_loop_count": int(m.get("busy_loop_count") or 0),
        "exchange_write_attempt_count": int(m.get("exchange_write_attempt_count") or 0),
        "mainnet_client_count": int(m.get("mainnet_client_count") or 0),
        "demo_order_count": int(m.get("demo_order_count") or 0),
        "real_money": bool(m.get("real_money") or False),
    }
    return {
        "schema": CHECKPOINT_SCHEMA,
        "written_at": utc_now(),
        "campaign_id": campaign_id,
        "campaign_state": campaign_state,
        "started_at": started_at,
        "elapsed": round(float(elapsed_sec), 3),
        "heartbeat_age": None if heartbeat_age_sec is None else round(float(heartbeat_age_sec), 3),
        "cycles_completed": int(m.get("runtime_cycles_completed") or 0),
        "cycles_failed": int(m.get("runtime_cycles_failed") or 0),
        "source_health": source_health,
        "data_lag": data_lag_ms,
        "contracts_seen": int(m.get("total_contracts_seen") or 0),
        "eligible": int(m.get("eligible_contracts_latest") or 0),
        "observe_only": int(m.get("observe_only_contracts_latest") or 0),
        "blocked": int(m.get("blocked_contracts_latest") or 0),
        "candidates": int(m.get("candidates_generated") or 0),
        "LONG": int(m.get("LONG_count") or 0),
        "SHORT": int(m.get("SHORT_count") or 0),
        "WAIT": int(m.get("WAIT_count") or 0),
        "ABSTAIN": int(m.get("ABSTAIN_count") or 0),
        "BLOCK": int(m.get("BLOCK_count") or 0),
        "shadow_opened": int(m.get("shadow_opened_count") or 0),
        "shadow_closed": int(m.get("shadow_closed_count") or 0),
        "AI_success": int(m.get("AI_success") or 0),
        "AI_failure": ai_fail,
        "fallback": int(m.get("deterministic_fallback_count") or 0),
        "runtime_restart_count": int(m.get("runtime_restart_count") or 0),
        "safety_counters": safety,
    }


def validate_checkpoint_schema(payload: dict[str, Any]) -> list[str]:
    """Return list of missing required fields (empty = ok)."""
    missing: list[str] = []
    for key in CHECKPOINT_FIELDS:
        if key not in payload:
            missing.append(key)
    return missing


class CompactCheckpointWriter:
    """Hourly compact JSON checkpoints under campaign checkpoint_dir."""

    def __init__(self, checkpoint_dir: Path) -> None:
        self.dir = Path(checkpoint_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.latest_path = self.dir / "checkpoint_latest.json"
        self.index_path = self.dir / "checkpoint_index.jsonl"
        self.count = 0

    def write(self, payload: dict[str, Any]) -> Path:
        missing = validate_checkpoint_schema(payload)
        if missing:
            raise ValueError(f"checkpoint_missing_fields:{missing}")
        self.count += 1
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        hourly = self.dir / f"checkpoint_{stamp}_{self.count:04d}.json"
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        hourly.write_text(text, encoding="utf-8")
        self.latest_path.write_text(text, encoding="utf-8")
        with self.index_path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "n": self.count,
                        "path": hourly.name,
                        "written_at": payload.get("written_at"),
                        "campaign_state": payload.get("campaign_state"),
                        "cycles_completed": payload.get("cycles_completed"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return hourly
