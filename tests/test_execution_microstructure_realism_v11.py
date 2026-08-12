"""V11 Execution Microstructure Realism — unit + smoke harness tests.

Defaults use smoke-scale env overrides so pytest stays CI-fast. Full targets
(250k × 2 passes) are exercised by
``tools/research/run_execution_microstructure_realism_v11.py``.
"""
from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from pathlib import Path

import pytest

os.environ.setdefault("NEXUS_V11_MICRO_SMOKE", "1")
os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_execution.book_model_v11 import (  # noqa: E402
    FILL_ACCURACY_CLAIM,
    STALE_BOOK_AGE_MS,
    generate_synthetic_book,
    liquidation_distance,
    market_impact,
    queue_position_approx,
    top_of_book_spread,
    validate_book,
)
from backend.nexus_execution.microstructure_realism_v11 import (  # noqa: E402
    ADAPTER_ID,
    CANONICAL_EXECUTION_ENGINE,
    CANONICAL_EXECUTION_ENGINE_COUNT,
    DEFAULT_SCENARIOS,
    PASS_STATUS,
    MicrostructureExecutionAdapterV11,
    load_micro_config,
    run_microstructure_campaign,
    write_microstructure_artifacts,
)
from backend.nexus_execution.microstructure_realism_v11.scenarios import (  # noqa: E402
    SCENARIO_KINDS,
)
from backend.nexus_execution.execution_simulator_v1_1 import (  # noqa: E402
    AutonomousExecutionSimulatorV11,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNED_FILES = (
    REPO_ROOT / "backend/nexus_execution/book_model_v11.py",
    REPO_ROOT / "tools/research/run_execution_microstructure_realism_v11.py",
    REPO_ROOT / "tests/test_execution_microstructure_realism_v11.py",
)
OWNED_DIRS = (REPO_ROOT / "backend/nexus_execution/microstructure_realism_v11",)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def test_canonical_engine_single_authority() -> None:
    assert CANONICAL_EXECUTION_ENGINE_COUNT == 1
    assert (
        CANONICAL_EXECUTION_ENGINE
        == "backend.nexus_execution.execution_simulator_v1_1.AutonomousExecutionSimulatorV11"
    )
    assert ADAPTER_ID == "NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1"
    adapter = MicrostructureExecutionAdapterV11()
    assert isinstance(adapter.canonical_engine, AutonomousExecutionSimulatorV11)


def test_micro_config_smoke_defaults() -> None:
    cfg = load_micro_config()
    assert cfg.smoke is True
    assert cfg.scenarios < DEFAULT_SCENARIOS
    assert cfg.scenarios >= 1


def test_book_validate_stale_and_missing() -> None:
    assert validate_book(None) is not None
    assert validate_book(None).reason == "MISSING_BOOK"
    book = generate_synthetic_book(
        symbol="BTCUSDT",
        mid=Decimal("100"),
        tick=Decimal("0.1"),
        seed=1,
        age_ms=STALE_BOOK_AGE_MS + 1,
    )
    reject = validate_book(book)
    assert reject is not None
    assert reject.reason == "STALE_BOOK"


def test_top_of_book_and_impact() -> None:
    book = generate_synthetic_book(
        symbol="BTCUSDT", mid=Decimal("100"), tick=Decimal("0.1"), seed=7, levels=5
    )
    assert top_of_book_spread(book) > 0
    impact = market_impact(book, side="BUY", qty=Decimal("0.5"))
    assert impact["ok"] is True
    q = queue_position_approx(
        book, side="BUY", limit_price=book.best_bid.price, order_qty=Decimal("0.1")
    )
    assert q["ok"] is True
    assert FILL_ACCURACY_CLAIM in impact["fill_accuracy_claim"]


def test_liquidation_distance_degrades_with_leverage() -> None:
    book = generate_synthetic_book(
        symbol="BTCUSDT",
        mid=Decimal("100"),
        tick=Decimal("0.1"),
        seed=3,
        mark_price=Decimal("100"),
        index_price=Decimal("99"),
    )
    mild = liquidation_distance(book, side="LONG", entry_price=Decimal("100"), leverage=5)
    harsh = liquidation_distance(book, side="LONG", entry_price=Decimal("100"), leverage=25)
    assert Decimal(harsh["degraded_distance"]) <= Decimal(mild["degraded_distance"])


def test_adapter_fail_closed_on_stale_book() -> None:
    adapter = MicrostructureExecutionAdapterV11()
    created = adapter.create_order(
        {
            "idempotency_key": "T-STALE",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": Decimal("0.1"),
        },
        mark_price=Decimal("100"),
    )
    assert created["status"] == "ACCEPTED"
    book = generate_synthetic_book(
        symbol="BTCUSDT",
        mid=Decimal("100"),
        tick=Decimal("0.1"),
        seed=9,
        age_ms=STALE_BOOK_AGE_MS + 50,
    )
    fill = adapter.try_fill_with_book(created["order_id"], book)
    assert fill["status"] == "REJECTED"
    assert fill["reason"] == "STALE_BOOK"
    order = adapter.canonical_engine.orders[created["order_id"]]
    assert order.fills == []


def test_no_candle_touch_equals_fill() -> None:
    adapter = MicrostructureExecutionAdapterV11()
    book = generate_synthetic_book(
        symbol="BTCUSDT", mid=Decimal("100"), tick=Decimal("0.1"), seed=11
    )
    limit = book.best_bid.price
    created = adapter.create_order(
        {
            "idempotency_key": "T-TOUCH",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": Decimal("0.1"),
            "price": limit,
        },
        mark_price=Decimal("100"),
    )
    assert created["status"] == "ACCEPTED"
    fill = adapter.try_fill_with_book(
        created["order_id"],
        book,
        tick=Decimal("0.1"),
        high=limit + Decimal("1"),
        low=limit,  # touch only — trade-through needs low <= limit - tick
    )
    assert fill["status"] != "FILLED"


def test_scenario_kinds_cover_contracts() -> None:
    required = {
        "stale_book_reject",
        "missing_book_reject",
        "top_of_book_spread_market",
        "depth_ladder_walk",
        "queue_position_limit",
        "market_impact_partial",
        "latency_distribution_sample",
        "partial_fill_progression",
        "cancel_replace_latency",
        "mark_index_divergence",
        "funding_timestamp_debit",
        "liquidation_distance_degrade",
        "no_candle_touch_fill",
        "same_bar_ambiguous_blocked",
        "duplicate_intent_no_exposure",
        "reduce_only_cannot_increase",
        "cost_bridge_round_trip",
    }
    assert required.issubset(set(SCENARIO_KINDS))


def test_microstructure_campaign_smoke_pass() -> None:
    cfg = load_micro_config()
    report = run_microstructure_campaign(config=cfg)
    assert report["generated_execution_scenario_count"] == cfg.scenarios
    assert report["pass"] is True
    assert report["exchange_write_attempt_count"] == 0
    assert report["demo_order_count"] == 0
    assert report["mainnet"] is False
    assert report["real_money"] is False
    assert report["invariants"]["scenarios_with_violations"] == 0
    assert report["canonical_execution_engine"] == CANONICAL_EXECUTION_ENGINE
    assert report["fill_accuracy_claim"] == FILL_ACCURACY_CLAIM


def test_write_artifacts_and_secret_scan(tmp_path: Path) -> None:
    cfg = load_micro_config()
    campaign = run_microstructure_campaign(config=cfg)

    hits: list[str] = []
    files: list[Path] = list(OWNED_FILES)
    for d in OWNED_DIRS:
        files.extend(sorted(p for p in d.rglob("*.py") if p.is_file()))
    for fp in files:
        text = fp.read_text(encoding="utf-8", errors="ignore")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                hits.append(str(fp))
                break
    secret_scan = {
        "schema": "v11_execution_microstructure_realism_secret_scan",
        "secret_leak_count": len(hits),
        "hits": hits,
        "files_scanned": len(files),
    }
    assert secret_scan["secret_leak_count"] == 0

    out = tmp_path / "artifacts"
    paths = write_microstructure_artifacts(
        out, campaign=campaign, secret_scan=secret_scan, pass_number=1
    )
    status = json.loads(paths["microstructure_status.json"].read_text(encoding="utf-8"))
    assert status["status"] == PASS_STATUS
    assert status["fuzz_pass"] is True
    readiness = json.loads(paths["readiness_report.json"].read_text(encoding="utf-8"))
    assert readiness["recommendation"] == PASS_STATUS
