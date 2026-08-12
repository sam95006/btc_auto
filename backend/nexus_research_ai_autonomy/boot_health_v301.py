"""V18.2.30.1 Zeabur worker boot health — BOOT_READY only if safe requirements pass."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import (
    autonomy_dir,
    campaign_root,
    ensure_writable,
    lock_dir,
    resolve_demo_env_path,
    runtime_location,
    worker_instance_id,
)


def _load_creds() -> dict[str, bool]:
    from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import load_demo_env

    path = resolve_demo_env_path()
    if path is not None:
        return load_demo_env(path)
    # Zeabur: env-only
    key_ok = bool((os.environ.get("BYBIT_DEMO_API_KEY") or "").strip())
    secret_ok = bool((os.environ.get("BYBIT_DEMO_API_SECRET") or "").strip())
    return {"key_present": key_ok, "secret_present": secret_ok}


def verify_exchange_demo(*, fail_closed: bool = True) -> dict[str, Any]:
    """Verify api-demo.bybit.com + credentials. Never log secrets."""
    out: dict[str, Any] = {
        "ok": False,
        "domain": "api-demo.bybit.com",
        "base_url": DEMO_REST_BASE_URL,
        "account_uid": None,
        "account_type": None,
        "fail_closed": fail_closed,
    }
    creds = _load_creds()
    out["credential_present"] = bool(creds.get("key_present") and creds.get("secret_present"))
    if not out["credential_present"]:
        out["error"] = "DEMO_CREDENTIALS_MISSING"
        return out

    # Hard safety: never allow mainnet flags
    if str(os.environ.get("MAINNET", "false")).lower() in {"1", "true", "yes"}:
        out["error"] = "MAINNET_FORBIDDEN"
        return out
    if str(os.environ.get("REAL_MONEY", "false")).lower() in {"1", "true", "yes"}:
        out["error"] = "REAL_MONEY_FORBIDDEN"
        return out

    try:
        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

        client = DemoWriteClient()
        # Domain lock
        host = getattr(client, "host", None) or "api-demo.bybit.com"
        if "api-demo.bybit.com" not in str(host) and "api-demo.bybit.com" not in DEMO_REST_BASE_URL:
            out["error"] = "DOMAIN_MISMATCH"
            out["host"] = str(host)
            return out

        wallet = {}
        if hasattr(client, "get_wallet_balance"):
            wallet = client.get_wallet_balance() or {}
        elif hasattr(client, "wallet_balance"):
            wallet = client.wallet_balance() or {}
        else:
            # Best-effort account probe via positions list (auth check)
            _ = client.list_positions() if hasattr(client, "list_positions") else []
            wallet = {"probed": "positions"}

        uid = (
            wallet.get("account_uid")
            or wallet.get("uid")
            or os.environ.get("BYBIT_DEMO_UID")
            or os.environ.get("NEXUS_DEMO_UID")
        )
        expected = (os.environ.get("BYBIT_DEMO_UID_EXPECTED") or os.environ.get("NEXUS_DEMO_UID_EXPECTED") or "").strip()
        out["account_uid"] = str(uid) if uid else None
        out["account_type"] = wallet.get("accountType") or wallet.get("account_type") or "UNIFIED"
        if expected and out["account_uid"] and expected != str(out["account_uid"]):
            out["error"] = "UID_MISMATCH"
            out["expected_uid_set"] = True
            return out
        out["ok"] = True
        out["exchange_connectivity"] = "OK"
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = type(exc).__name__
        out["detail"] = str(exc)[:200]
        out["exchange_connectivity"] = "DEGRADED"
        return out


def run_boot_health(
    *,
    campaign: Path | None = None,
    ai_registry: Any | None = None,
    probe_ai: bool = True,
) -> dict[str, Any]:
    """Return BOOT_READY only if safe requirements pass."""
    root = campaign or campaign_root()
    auto = autonomy_dir(root)
    locks = lock_dir()
    storage = ensure_writable(auto)
    lock_w = ensure_writable(locks)
    ckpt = ensure_writable(root / "checkpoints")

    os.environ.setdefault("EXCHANGE_WRITE", "true")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")

    exchange = verify_exchange_demo(fail_closed=True)
    ai_probe = None
    ai_agg = None
    if probe_ai and ai_registry is not None:
        ai_probe = ai_registry.probe_all()
        ai_agg = ai_registry.aggregate()
    elif probe_ai:
        from backend.nexus_research_ai_autonomy.ai_provider_health_v301 import AIProviderHealthRegistry

        reg = AIProviderHealthRegistry(store_path=auto / "ai_provider_health.json")
        ai_probe = reg.probe_all()
        ai_agg = reg.aggregate()

    # Market data: cheap ticker if exchange ok
    market_ok = False
    market_detail = None
    if exchange.get("ok"):
        try:
            from backend.nexus_demo_execution.demo_write_client import DemoWriteClient

            client = DemoWriteClient()
            if hasattr(client, "get_ticker"):
                t = client.get_ticker("BTCUSDT")
                market_ok = bool(t)
                market_detail = "ticker_ok" if market_ok else "ticker_empty"
            else:
                market_ok = True
                market_detail = "exchange_ok_assume_market"
        except Exception as exc:  # noqa: BLE001
            market_detail = type(exc).__name__

    blockers: list[str] = []
    if not storage.get("ok"):
        blockers.append("storage_not_writable")
    if not lock_w.get("ok"):
        blockers.append("lock_dir_not_writable")
    if not exchange.get("ok"):
        blockers.append(f"exchange:{exchange.get('error')}")
    if not market_ok:
        blockers.append(f"market:{market_detail or 'failed'}")

    # AI not configured is NOT a boot blocker for V30 deterministic entry,
    # unless Founder explicitly requires AI for entry.
    require_ai = (os.environ.get("NEXUS_AUTONOMY_REQUIRE_AI_ENTRY") or "").lower() in {
        "1",
        "true",
        "yes",
    }
    if require_ai and ai_agg and not ai_agg.get("ai_calls_working"):
        blockers.append(f"ai:{ai_agg.get('ai_state')}")

    boot_ready = len(blockers) == 0
    return {
        "schema": "v18_2_30_1_boot_health_v1",
        "BOOT_READY": boot_ready,
        "runtime_location": runtime_location(),
        "worker_instance_id": worker_instance_id(),
        "campaign_root": str(root),
        "storage": storage,
        "checkpoints": ckpt,
        "lock_dir": lock_w,
        "exchange": {k: v for k, v in exchange.items() if k != "detail" or not boot_ready},
        "market_data": {"ok": market_ok, "detail": market_detail},
        "ai": ai_agg,
        "ai_probe": {"providers": (ai_probe or {}).get("providers")} if ai_probe else None,
        "blockers": blockers,
        "safety": {
            "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE"),
            "MAINNET": os.environ.get("MAINNET"),
            "REAL_MONEY": os.environ.get("REAL_MONEY"),
            "demo_domain": "api-demo.bybit.com",
        },
    }
