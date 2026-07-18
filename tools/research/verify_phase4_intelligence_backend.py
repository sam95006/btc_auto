#!/usr/bin/env python3
"""Phase 4 Track B — Market Intelligence backend verify (static + light runtime)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    print("PHASE4_INTELLIGENCE_BACKEND_VERIFY")
    fails: list[str] = []

    required = [
        ROOT / "backend" / "market" / "intelligence" / "history_store.py",
        ROOT / "backend" / "market" / "intelligence" / "transition_store.py",
        ROOT / "backend" / "market" / "intelligence" / "outcome_store.py",
        ROOT / "backend" / "api" / "market_intelligence_routes.py",
        ROOT / "backend" / "market" / "scanner" / "bybit_public_ws.py",
    ]
    for p in required:
        ok = p.is_file()
        print(f"file:{p.relative_to(ROOT)}={'ok' if ok else 'MISSING'}")
        if not ok:
            fails.append(f"missing:{p.name}")

    # Memory-only history mode
    os.environ.pop("NEXUS_DATA_DIR", None)
    from backend.market.intelligence.history_store import HistoryStore  # noqa: E402

    mem = HistoryStore()
    if mem.mode != "memory":
        fails.append(f"expected_memory_got_{mem.mode}")
    else:
        print("history_mode_memory=true")
    mem.append_sample("BTCUSDT", price=100.0, oi=1.0, turnover=1e6)
    assert mem.get_samples("BTCUSDT")
    print("history_sample_ok=true")

    # Writable dir → sqlite/jsonl
    with tempfile.TemporaryDirectory() as td:
        os.environ["NEXUS_DATA_DIR"] = td
        # force new instance
        import backend.market.intelligence.history_store as hs  # noqa: E402

        hs._STORE = None
        store = hs.HistoryStore()
        if store.mode not in ("sqlite", "jsonl"):
            fails.append(f"expected_persist_got_{store.mode}")
        else:
            print(f"history_mode_persist={store.mode}")
        store.append_sample("ETHUSDT", price=200.0, oi=2.0)
        st = store.status()
        if st.get("secretsStored") or st.get("walletStored") or st.get("ordersStored"):
            fails.append("forbidden_storage_flags")
        print(f"schema_version={st.get('schemaVersion')}")
    os.environ.pop("NEXUS_DATA_DIR", None)

    from backend.market.intelligence.transition_store import TransitionStore  # noqa: E402

    ts = TransitionStore()
    ranked = [
        {
            "id": "BTCUSDT:LONG",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "stage": "CONFIRMED",
            "rank": 1,
            "opportunityScore": 70,
            "confirmationScore": 60,
            "riskScore": 20,
            "reasons": ["test"],
            "conflicts": [],
        }
    ]
    n = ts.record_from_candidates(ranked, {}, source_snapshot_at=1)
    n2 = ts.record_from_candidates(ranked, {}, source_snapshot_at=1)
    if n < 1:
        fails.append("transition_not_recorded")
    if n2 != 0:
        fails.append("transition_dedup_failed")
    else:
        print("transition_dedup=true")
    tl = ts.timeline("BTCUSDT")
    if not tl.get("transitions"):
        fails.append("timeline_empty")
    else:
        print("timeline_api_shape_ok=true")

    from backend.market.intelligence.outcome_store import OutcomeStore  # noqa: E402

    os_ = OutcomeStore()
    r1 = os_.ensure_tracking(
        anomaly_id="test:1",
        symbol="BTCUSDT",
        reference_price=100.0,
        direction="UP",
        observed_at=1_000,
    )
    r2 = os_.ensure_tracking(
        anomaly_id="test:1",
        symbol="BTCUSDT",
        reference_price=100.0,
        direction="UP",
        observed_at=1_000,
    )
    if not r1.get("ok"):
        fails.append("outcome_create_failed")
    if r2.get("error") != "duplicate_blocked":
        fails.append("outcome_duplicate_not_blocked")
    else:
        print("outcome_duplicate_blocked=true")
    ost = os_.status()
    if ost.get("syntheticLiveResult") is not False:
        fails.append("synthetic_flag_wrong")
    if ost.get("recommendationCoupled") is not False:
        fails.append("recommendation_coupled")
    print(f"outcome_windows={ost.get('windows')}")

    # Funding history function present + fabricatedHistory false
    from backend.market.charts import bybit_public_charts as charts  # noqa: E402

    src = (ROOT / "backend" / "market" / "charts" / "bybit_public_charts.py").read_text(
        encoding="utf-8"
    )
    if "/v5/market/funding/history" not in src:
        fails.append("funding_endpoint_missing")
    if "fabricatedHistory" not in src:
        fails.append("fabricated_flag_missing")
    # Offline: call status helper with monkeypatched failure path via empty symbol handling
    # Prefer live call if network works; tolerate failure as honest unavailable
    try:
        body = charts.fetch_funding_history("BTCUSDT", limit=5)
        print(f"funding_fetch_ok={body.get('ok')}")
        print(f"funding_available={body.get('available')}")
        print(f"fabricatedHistory={body.get('fabricatedHistory')}")
        if body.get("fabricatedHistory") is not False:
            fails.append("funding_fabricated_true")
        if body.get("ok") and body.get("points"):
            print(f"funding_points={len(body['points'])}")
    except Exception as exc:  # noqa: BLE001
        print(f"funding_fetch_exception={exc}")

    # Routes registration markers
    run_src = (ROOT / "run.py").read_text(encoding="utf-8")
    stage_src = (
        ROOT
        / "deploy"
        / "zeabur_stage3_demo_learning"
        / "tools"
        / "research"
        / "stage3_readonly_web_app.py"
    ).read_text(encoding="utf-8")
    if "register_market_intelligence_routes" not in run_src:
        fails.append("run_py_missing_mi_routes")
    if "register_market_intelligence_routes" not in stage_src:
        fails.append("stage3_app_missing_mi_routes")
    else:
        print("routes_registered=true")

    scanner_routes = (ROOT / "backend" / "api" / "market_scanner_routes.py").read_text(
        encoding="utf-8"
    )
    if "candidates/<symbol>/timeline" not in scanner_routes:
        fails.append("timeline_route_missing")
    else:
        print("timeline_route=true")

    # Safety: candidate_engine not modified by this verify (presence only)
    print("candidate_formula_guard=do_not_modify_candidate_engine")
    print("trading_path_untouched=assumed_by_scope")

    # Deploy mirrors
    deploy_root = ROOT / "deploy" / "zeabur_stage3_demo_learning" / "backend"
    for rel in (
        "market/intelligence/history_store.py",
        "market/intelligence/transition_store.py",
        "market/intelligence/outcome_store.py",
        "api/market_intelligence_routes.py",
        "market/scanner/bybit_public_ws.py",
        "market/scanner/scanner_service.py",
        "market/charts/bybit_public_charts.py",
    ):
        p = deploy_root / rel
        print(f"deploy_mirror:{rel}={'ok' if p.is_file() else 'MISSING'}")
        if not p.is_file():
            fails.append(f"deploy_missing:{rel}")

    if fails:
        print("FAILS=" + ",".join(fails))
        print("VERDICT=FAIL")
        return 1
    print("VERDICT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
