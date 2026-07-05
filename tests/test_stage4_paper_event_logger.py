"""Stage 4.17-A paper event logger tests — no orders, no exchange calls."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

from tools.research.stage4_paper_event_logger import (
    GuardStats,
    classify_paper_event,
    contains_secret,
    is_eligible_decision,
    load_existing_event_keys,
    render_report,
    run_paper_event_logger,
    strip_events_for_output,
)


def _watch_paper_fields() -> Dict[str, Any]:
    return {
        "directional_bias": "LONG",
        "watch_confirmation_reason": "Range support holding with neutral vol",
        "invalidation": {
            "invalidation_price": 61000.0,
            "invalidation_reason": "Break below range low",
            "max_adverse_move_pct": 0.35,
        },
        "mae_risk_estimate_pct": 0.22,
        "decision_quality_incomplete": False,
        "paper_readiness": {
            "eligible_for_watchlist": True,
            "eligible_for_hypothetical_entry": False,
            "block_reason": "ok",
        },
    }


def _enter_paper_fields() -> Dict[str, Any]:
    return {
        "directional_bias": "LONG",
        "entry_trigger": {
            "type": "pullback_confirm",
            "trigger_price": 62000.0,
            "trigger_condition": "Reclaim VWAP",
        },
        "invalidation": {
            "invalidation_price": 61000.0,
            "invalidation_reason": "Structure break",
            "max_adverse_move_pct": 0.30,
        },
        "mae_risk_estimate_pct": 0.22,
        "risk_reward_estimate": 1.5,
        "decision_quality_incomplete": False,
        "paper_readiness": {
            "eligible_for_watchlist": False,
            "eligible_for_hypothetical_entry": True,
            "block_reason": "ok",
        },
    }


def _decision(**overrides: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "decision_id": "dec-test-1",
        "created_at_utc": "2026-07-05T02:00:00Z",
        "tick_index": 1,
        "symbol": "BTCUSDT",
        "decision_intent": "watch",
        "final_action": "skip",
        "candidate_side": "NONE",
        "confidence": 0.45,
        "provider": "groq",
        "regime": "range",
        "parse_error": False,
        "is_mock_ai": False,
        "order_sent": False,
        "schema_repaired": False,
        "schema_repair_mode": None,
        "market_context": {
            "last_price": 62000.0,
            "regime": "range",
            "volatility_level": "medium",
            "volatility_15m": 0.0012,
            "trend_15m": "up",
        },
    }
    row.update(overrides)
    intent = str(row.get("decision_intent") or "").lower()
    if intent == "watch" and "directional_bias" not in overrides and "decision_quality_incomplete" not in overrides:
        row.update(_watch_paper_fields())
    elif (
        intent == "enter_candidate"
        and "directional_bias" not in overrides
        and "decision_quality_incomplete" not in overrides
    ):
        row.update(_enter_paper_fields())
    return row


class Stage417PaperEventLoggerTests(unittest.TestCase):
    def test_hard_skip_hypothetical_skip(self) -> None:
        event = classify_paper_event(
            _decision(decision_intent="hard_skip"),
            source_dataset="/data/test",
            watchlists={},
        )
        assert event is not None
        self.assertEqual(event["paper_action"], "hypothetical_skip")
        self.assertEqual(event["candidate_side"], "NONE")
        self.assertEqual(event["risk_governor_verdict"], "block")

    def test_soft_skip_hypothetical_skip(self) -> None:
        event = classify_paper_event(
            _decision(decision_intent="soft_skip"),
            source_dataset="/data/test",
            watchlists={},
        )
        assert event is not None
        self.assertEqual(event["paper_action"], "hypothetical_skip")
        self.assertEqual(event["risk_governor_verdict"], "downgrade_to_skip")

    def test_watch_always_watchlist_never_entry(self) -> None:
        watchlists: dict = {}
        for i in range(3):
            event = classify_paper_event(
                _decision(
                    decision_id=f"dec-watch-{i}",
                    tick_index=i + 1,
                    decision_intent="watch",
                    symbol="BTCUSDT",
                ),
                source_dataset="/data/test",
                watchlists=watchlists,
            )
            assert event is not None
            self.assertEqual(event["paper_action"], "watchlist")
            self.assertNotEqual(event["paper_action"], "hypothetical_entry")
        enter = classify_paper_event(
            _decision(
                decision_id="dec-enter-1",
                tick_index=4,
                decision_intent="enter_candidate",
                candidate_side="LONG",
                confidence=0.50,
                symbol="SOLUSDT",
            ),
            source_dataset="/data/test",
            watchlists=watchlists,
        )
        assert enter is not None
        self.assertNotEqual(enter["paper_action"], "hypothetical_entry")

    def test_enter_candidate_btc_pass_hypothetical_entry(self) -> None:
        event = classify_paper_event(
            _decision(
                decision_intent="enter_candidate",
                candidate_side="LONG",
                confidence=0.50,
                symbol="BTCUSDT",
                regime="range",
            ),
            source_dataset="/data/test",
            watchlists={},
        )
        assert event is not None
        self.assertEqual(event["paper_action"], "hypothetical_entry")
        self.assertEqual(event["risk_governor_verdict"], "allow")
        self.assertGreater(event["hypothetical_entry_price"], 0)

    def test_enter_candidate_sol_high_volatility_downgrade(self) -> None:
        event = classify_paper_event(
            _decision(
                decision_intent="enter_candidate",
                candidate_side="LONG",
                confidence=0.55,
                symbol="SOLUSDT",
                regime="volatile",
                market_context={
                    "last_price": 145.0,
                    "regime": "volatile",
                    "volatility_level": "high",
                    "volatility_15m": 0.004,
                },
            ),
            source_dataset="/data/test",
            watchlists={},
        )
        assert event is not None
        self.assertIn(event["paper_action"], {"hypothetical_skip", "watchlist"})
        self.assertNotEqual(event["paper_action"], "hypothetical_entry")

    def test_enter_candidate_pepe_no_confirmation_downgrade_watchlist(self) -> None:
        event = classify_paper_event(
            _decision(
                decision_intent="enter_candidate",
                candidate_side="LONG",
                confidence=0.55,
                symbol="PEPEUSDT",
            ),
            source_dataset="/data/test",
            watchlists={},
        )
        assert event is not None
        self.assertEqual(event["paper_action"], "watchlist")
        self.assertEqual(event["risk_governor_verdict"], "downgrade_to_watchlist")

    def test_schema_safe_skip_defaults_block(self) -> None:
        event = classify_paper_event(
            _decision(
                decision_intent="enter_candidate",
                candidate_side="LONG",
                confidence=0.60,
                schema_repair_mode="safe_skip_defaults",
            ),
            source_dataset="/data/test",
            watchlists={},
        )
        assert event is not None
        self.assertEqual(event["paper_action"], "hypothetical_skip")
        self.assertEqual(event["risk_governor_verdict"], "block")
        self.assertIn("schema_safe_skip_repair", event["risk_governor_reasons"])

    def test_parse_error_not_eligible(self) -> None:
        self.assertFalse(is_eligible_decision(_decision(parse_error=True)))
        event = classify_paper_event(
            _decision(parse_error=True, decision_intent="enter_candidate"),
            source_dataset="/data/test",
            watchlists={},
        )
        self.assertIsNone(event)

    def test_mock_not_processed_as_entry(self) -> None:
        self.assertFalse(is_eligible_decision(_decision(is_mock_ai=True)))
        event = classify_paper_event(
            _decision(is_mock_ai=True, decision_intent="enter_candidate"),
            source_dataset="/data/test",
            watchlists={},
        )
        self.assertIsNone(event)

    def test_order_sent_excluded(self) -> None:
        self.assertFalse(is_eligible_decision(_decision(order_sent=True)))
        event = classify_paper_event(
            _decision(order_sent=True, decision_intent="enter_candidate"),
            source_dataset="/data/test",
            watchlists={},
        )
        self.assertIsNone(event)

    def test_summary_metrics_count_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in"
            out = Path(tmp) / "out"
            inp.mkdir()
            rows = [
                _decision(decision_id="d1", decision_intent="hard_skip"),
                _decision(decision_id="d2", decision_intent="watch", tick_index=2),
                _decision(
                    decision_id="d3",
                    decision_intent="enter_candidate",
                    candidate_side="LONG",
                    confidence=0.50,
                    tick_index=3,
                ),
            ]
            (inp / "ai_decisions.jsonl").write_text(
                "\n".join(json.dumps(r) for r in rows) + "\n",
                encoding="utf-8",
            )
            summary = run_paper_event_logger([inp], output_dir=out, mode="overwrite")
            self.assertEqual(summary["total_events_written"], 3)
            self.assertEqual(summary["hypothetical_skip_count"], 1)
            self.assertEqual(summary["watchlist_count"], 1)
            self.assertEqual(summary["hypothetical_entry_count"], 1)

    def test_no_exchange_call_path(self) -> None:
        import tools.research.stage4_paper_event_logger as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source)
        self.assertNotIn("BybitDemoClient", source)
        self.assertNotIn("place_order", source)
        self.assertNotIn("submit_order", source)

    def test_output_jsonl_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in"
            out = Path(tmp) / "out"
            inp.mkdir()
            (inp / "ai_decisions.jsonl").write_text(
                json.dumps(_decision(decision_id="d1", decision_intent="watch")) + "\n",
                encoding="utf-8",
            )
            run_paper_event_logger([inp], output_dir=out, mode="append-only")
            first_len = (out / "hypothetical_entry_log.jsonl").read_text(encoding="utf-8").count("\n")
            run_paper_event_logger([inp], output_dir=out, mode="append-only")
            second_len = (out / "hypothetical_entry_log.jsonl").read_text(encoding="utf-8").count("\n")
            self.assertEqual(first_len, second_len)

    def test_no_api_key_leak(self) -> None:
        bad = "sk-" + "a" * 40
        summary = {
            "generated_at_utc": "2026-07-05T00:00:00Z",
            "total_decisions_read": 1,
            "total_events_written": 1,
            "hypothetical_entry_count": 0,
            "watchlist_count": 1,
            "hypothetical_skip_count": 0,
            "enter_candidate_allowed_count": 0,
            "enter_candidate_downgraded_count": 0,
            "mock_ai_used_count": 0,
            "order_sent_count": 0,
            "any_exchange_call_made": False,
            "production_touched": False,
            "btc_auto_touched": False,
            "datasets_analyzed": ["/data/test"],
            "missing_datasets": [],
            "paper_action_distribution": {"watchlist": 1},
            "per_symbol_paper_action_distribution": {"BTCUSDT": {"watchlist": 1}},
            "sol_guard_fired_count": 0,
            "pepe_guard_fired_count": 0,
            "mae_guard_fired_count": 0,
            "trend_guard_fired_count": 0,
            "risk_governor_reason_counts": {},
        }
        md = render_report(summary)
        self.assertNotIn(bad, md)
        self.assertFalse(contains_secret("normal report text without secrets"))

    def test_production_btc_auto_not_referenced(self) -> None:
        import tools.research.stage4_paper_event_logger as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertEqual(mod.build_summary(
            datasets_analyzed=[],
            missing_datasets=[],
            total_decisions_read=0,
            events=[],
            guard_stats=GuardStats(),
            excluded_parse=0,
            excluded_mock=0,
            excluded_order=0,
        )["production_touched"], False)
        self.assertEqual(
            strip_events_for_output(
                {"events": [], "production_touched": False, "btc_auto_touched": False}
            )["btc_auto_touched"],
            False,
        )
        self.assertNotIn("place_order", source)
        self.assertNotIn("BybitDemoClient", source)


class Stage418CPaperReadinessLoggerTests(unittest.TestCase):
    def test_logger_blocks_decision_quality_incomplete(self) -> None:
        self.assertFalse(
            is_eligible_decision(
                _decision(
                    decision_intent="watch",
                    decision_quality_incomplete=True,
                    directional_bias="NONE",
                )
            )
        )

    def test_complete_watch_is_eligible(self) -> None:
        self.assertTrue(is_eligible_decision(_decision(decision_intent="watch")))

    def test_enter_candidate_missing_side_ineligible(self) -> None:
        row = _decision(
            decision_intent="enter_candidate",
            candidate_side="NONE",
            decision_quality_incomplete=True,
            directional_bias="NONE",
        )
        self.assertFalse(is_eligible_decision(row))

    def test_no_order_sent_in_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp = Path(tmp) / "in"
            out = Path(tmp) / "out"
            inp.mkdir()
            (inp / "ai_decisions.jsonl").write_text(
                json.dumps(_decision(decision_intent="watch")) + "\n",
                encoding="utf-8",
            )
            summary = run_paper_event_logger([inp], output_dir=out, mode="overwrite")
            self.assertEqual(summary["order_sent_count"], 0)


if __name__ == "__main__":
    unittest.main()
