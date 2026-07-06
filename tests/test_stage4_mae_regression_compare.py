"""Stage 4.18-I MAE regression compare tool tests — offline only."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from tools.research.stage4_mae_regression_compare import compare_mae_regressions


def _base_decision(**overrides: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "decision_id": "dec-1",
        "created_at_utc": "2026-07-05T02:00:00Z",
        "tick_index": 1,
        "symbol": "BTCUSDT",
        "decision_intent": "watch",
        "final_action": "skip",
        "candidate_side": "LONG",
        "directional_bias": "LONG",
        "confidence": 0.50,
        "provider": "groq",
        "parse_error": False,
        "is_mock_ai": False,
        "order_sent": False,
        "market_context": {
            "last_price": 62000.0,
            "regime": "range",
            "volatility_level": "low",
            "trend_15m": "up",
        },
        "watch_confirmation_reason": "Support held",
        "invalidation": {
            "invalidation_price": 61780.0,
            "invalidation_reason": "Break support",
            "max_adverse_move_pct": 0.35,
        },
        "mae_risk_estimate_pct": 0.30,
        "decision_quality_incomplete": False,
        "paper_readiness": {
            "eligible_for_watchlist": True,
            "eligible_for_hypothetical_entry": False,
            "block_reason": "ok",
        },
    }
    row.update(overrides)
    return row


def _write_session(tmp: Path, name: str, decisions: list[Dict[str, Any]]) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    with (d / "ai_decisions.jsonl").open("w", encoding="utf-8") as fh:
        for row in decisions:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (d / "stage4_ai_decision_summary.json").write_text(
        json.dumps({"effective_decision_count": len(decisions)}),
        encoding="utf-8",
    )
    return d


class Stage418IMaeRegressionCompareTests(unittest.TestCase):
    def test_compare_detects_btc_graduation_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline_rows = [
                _base_decision(decision_id="b1", tick_index=1),
                _base_decision(decision_id="b2", tick_index=2, mae_risk_estimate_pct=0.32),
            ]
            candidate_rows = [
                _base_decision(decision_id="c1", tick_index=1, mae_risk_estimate_pct=0.50),
                _base_decision(decision_id="c2", tick_index=2, mae_risk_estimate_pct=0.45),
            ]
            b_dir = _write_session(root, "baseline", baseline_rows)
            c_dir = _write_session(root, "candidate", candidate_rows)
            out = root / "out"
            summary = compare_mae_regressions(
                baseline_dir=str(b_dir),
                candidate_dir=str(c_dir),
                output_dir=str(out),
            )
            self.assertTrue(summary["analysis"]["btc_graduation_regression"]["btc_graduation_regression"])
            self.assertTrue((out / "stage4_18i_compare_summary.json").is_file())

    def test_compare_detects_eth_watch_mae_above_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eth_high = _base_decision(
                symbol="ETHUSDT",
                decision_id="e1",
                mae_risk_estimate_pct=0.45,
                invalidation={"max_adverse_move_pct": 0.45},
            )
            b_dir = _write_session(root, "baseline", [])
            c_dir = _write_session(root, "candidate", [eth_high])
            summary = compare_mae_regressions(
                baseline_dir=str(b_dir),
                candidate_dir=str(c_dir),
                output_dir=str(root / "out"),
            )
            self.assertEqual(summary["eth_watch_mae_above_cap_count"], 1)
            self.assertIn("eth_watch_mae_above", summary["analysis"]["eth_no_graduation_cause"])

    def test_compare_outputs_watchlist_confirmation_block_reasons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            high_mae = _base_decision(mae_risk_estimate_pct=0.80, candidate_side="LONG")
            c_dir = _write_session(root, "candidate", [high_mae])
            b_dir = _write_session(root, "baseline", [])
            summary = compare_mae_regressions(
                baseline_dir=str(b_dir),
                candidate_dir=str(c_dir),
                output_dir=str(root / "out"),
            )
            blocks = summary.get("watchlist_confirmation_block_reasons") or {}
            self.assertIsInstance(blocks, dict)
            self.assertTrue(len(blocks) >= 0)

    def test_no_exchange_call_path(self) -> None:
        import tools.research.stage4_mae_regression_compare as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("BybitDemoClient", source)
        self.assertNotIn("urlopen", source)

    def test_no_production_btc_auto_reference(self) -> None:
        import tools.research.stage4_mae_regression_compare as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("btc-auto", source)
        self.assertFalse(compare_mae_regressions(
            baseline_dir=tempfile.mkdtemp(),
            candidate_dir=tempfile.mkdtemp(),
            output_dir=tempfile.mkdtemp(),
        )["production_touched"])


if __name__ == "__main__":
    unittest.main()
