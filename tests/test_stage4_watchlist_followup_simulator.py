"""Stage 4.18 watchlist follow-up simulator tests — offline only, no orders."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from tools.research.stage4_paper_event_logger import run_paper_event_logger
from tools.research.stage4_watchlist_followup_simulator import (
    contains_secret,
    render_report,
    run_simulator,
    simulate_mode,
)


def _decision(**overrides: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "decision_id": "dec-1",
        "created_at_utc": "2026-07-05T02:00:00Z",
        "tick_index": 1,
        "symbol": "BTCUSDT",
        "decision_intent": "watch",
        "final_action": "skip",
        "candidate_side": "LONG",
        "confidence": 0.45,
        "provider": "groq",
        "regime": "range",
        "parse_error": False,
        "is_mock_ai": False,
        "order_sent": False,
        "schema_repair_mode": None,
        "market_context": {
            "last_price": 62000.0,
            "regime": "range",
            "volatility_level": "low",
            "volatility_15m": 0.0008,
            "trend_15m": "up",
        },
    }
    row.update(overrides)
    return row


class Stage418WatchlistSimulatorTests(unittest.TestCase):
    def _setup_dirs(self, tmp: str, decisions: list[Dict[str, Any]]) -> tuple[Path, Path, Path]:
        root = Path(tmp)
        inp = root / "in"
        paper = root / "paper"
        out = root / "out"
        inp.mkdir()
        paper.mkdir()
        (inp / "ai_decisions.jsonl").write_text(
            "\n".join(json.dumps(d) for d in decisions) + "\n",
            encoding="utf-8",
        )
        run_paper_event_logger([inp], output_dir=paper, mode="overwrite")
        return inp, paper, out

    def test_simulator_loads_paper_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp, paper, out = self._setup_dirs(tmp, [_decision()])
            summary = run_simulator(decision_dirs=[inp], paper_events_dir=paper, output_dir=out)
            self.assertEqual(summary["paper_events_input_count"], 1)

    def test_watchlist_pending_to_confirmed(self) -> None:
        decisions = [
            _decision(decision_id="d1", tick_index=1, decision_intent="watch", confidence=0.45),
            _decision(decision_id="d2", tick_index=2, decision_intent="watch", confidence=0.46),
            _decision(decision_id="d3", tick_index=3, decision_intent="enter_candidate", confidence=0.47),
        ]
        rows = [("/data/test", d) for d in decisions]
        acc = simulate_mode("confirmed_watchlist_only", rows)
        self.assertGreaterEqual(acc.watchlist_confirmed, 1)

    def test_watchlist_expiration(self) -> None:
        decisions = [
            _decision(decision_id="d1", tick_index=1, decision_intent="watch"),
            _decision(decision_id="d2", tick_index=10, decision_intent="watch"),
        ]
        rows = [("/data/test", d) for d in decisions]
        acc = simulate_mode("confirmed_watchlist_only", rows)
        self.assertGreaterEqual(acc.watchlist_expired, 1)

    def test_strict_current_no_direct_watch_entry(self) -> None:
        rows = [("/data/test", _decision(decision_intent="watch"))]
        acc = simulate_mode("strict_current", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)

    def test_confirmed_watchlist_requires_two_confirmations(self) -> None:
        rows = [("/data/test", _decision(decision_id="d1", tick_index=1, decision_intent="watch"))]
        acc = simulate_mode("confirmed_watchlist_only", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)

    def test_major_only_blocks_sol_pepe_graduation(self) -> None:
        decisions = [
            _decision(
                decision_id="d1",
                symbol="SOLUSDT",
                tick_index=1,
                decision_intent="watch",
                confidence=0.55,
            ),
            _decision(
                decision_id="d2",
                symbol="SOLUSDT",
                tick_index=2,
                decision_intent="watch",
                confidence=0.56,
            ),
            _decision(
                decision_id="d3",
                symbol="SOLUSDT",
                tick_index=3,
                decision_intent="enter_candidate",
                candidate_side="LONG",
                confidence=0.57,
            ),
        ]
        rows = [("/data/test", d) for d in decisions]
        acc = simulate_mode("major_only_calibrated", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)

    def test_pepe_never_direct_entry(self) -> None:
        rows = [
            (
                "/data/test",
                _decision(
                    symbol="PEPEUSDT",
                    decision_intent="enter_candidate",
                    candidate_side="LONG",
                    confidence=0.55,
                    market_context={
                        "last_price": 0.00001,
                        "regime": "range",
                        "volatility_level": "low",
                        "volatility_15m": 0.0005,
                    },
                ),
            )
        ]
        acc = simulate_mode("confirmed_watchlist_only", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)

    def test_parse_error_blocks_graduation(self) -> None:
        rows = [("/data/test", _decision(parse_error=True, decision_intent="enter_candidate"))]
        acc = simulate_mode("major_only_calibrated", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)

    def test_safe_skip_defaults_blocks_graduation(self) -> None:
        rows = [
            (
                "/data/test",
                _decision(
                    decision_intent="enter_candidate",
                    schema_repair_mode="safe_skip_defaults",
                    confidence=0.55,
                ),
            )
        ]
        acc = simulate_mode("major_only_calibrated", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)

    def test_enter_candidate_downgrade_reasons_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            decisions = [
                _decision(decision_id="d1", decision_intent="enter_candidate", confidence=0.55),
            ]
            inp, paper, out = self._setup_dirs(tmp, decisions)
            summary = run_simulator(decision_dirs=[inp], paper_events_dir=paper, output_dir=out)
            self.assertIn("enter_candidate_downgrade_reasons", summary)

    def test_summary_metrics_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inp, paper, out = self._setup_dirs(tmp, [_decision()])
            run_simulator(decision_dirs=[inp], paper_events_dir=paper, output_dir=out)
            self.assertTrue((out / "stage4_18_watchlist_followup_summary.json").is_file())
            self.assertTrue((out / "stage4_18_watchlist_transitions.jsonl").is_file())

    def test_no_exchange_call_path(self) -> None:
        import tools.research.stage4_watchlist_followup_simulator as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source)
        self.assertNotIn("BybitDemoClient", source)

    def test_no_order_sent(self) -> None:
        summary = run_simulator(
            decision_dirs=[],
            paper_events_dir=tempfile.mkdtemp(),
            output_dir=tempfile.mkdtemp(),
        )
        self.assertEqual(summary["order_sent_count"], 0)

    def test_no_api_key_leak(self) -> None:
        bad = "sk-" + "a" * 40
        md = render_report({"generated_at_utc": "t", "mode_results": {}, "analysis": {}})
        self.assertNotIn(bad, md)
        self.assertFalse(contains_secret("clean report"))

    def test_production_btc_auto_not_referenced(self) -> None:
        import tools.research.stage4_watchlist_followup_simulator as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertFalse(mod.run_simulator(
            decision_dirs=[],
            paper_events_dir=tempfile.mkdtemp(),
            output_dir=tempfile.mkdtemp(),
        )["production_touched"])
        self.assertNotIn("place_order", source)


if __name__ == "__main__":
    unittest.main()
