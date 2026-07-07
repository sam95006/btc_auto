"""Stage 4.18 watchlist follow-up simulator tests — offline only, no orders."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

from tools.research.stage4_paper_event_logger import run_paper_event_logger
from tools.research.stage4_watchlist_followup_simulator import (
    MAE_CALIBRATION_MODES,
    contains_secret,
    render_418b_report,
    render_report,
    recommend_calibration_mode_for_419,
    run_major_mae_calibration_replay,
    run_simulator,
    simulate_major_mae_calibration_mode,
    simulate_mode,
)
from tools.research.stage4_paper_guard_inputs import MAE_SOURCE_LLM, get_paper_mae_pct


def _watch_paper_fields() -> Dict[str, Any]:
    return {
        "directional_bias": "LONG",
        "watch_confirmation_reason": "Pullback held support",
        "entry_trigger": {
            "type": "pullback_confirm",
            "trigger_price": 62000.0,
            "trigger_condition": "Reclaim VWAP",
        },
        "invalidation": {
            "invalidation_price": 61000.0,
            "invalidation_reason": "Break below support",
            "max_adverse_move_pct": 0.35,
        },
        "mae_risk_estimate_pct": 0.20,
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
        "mae_risk_estimate_pct": 0.20,
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


class Stage418BMaeCalibrationTests(unittest.TestCase):
    def _major_rows(self, **overrides: Any) -> list[tuple[str, Dict[str, Any]]]:
        base = _decision(
            symbol="BTCUSDT",
            market_context={
                "last_price": 62000.0,
                "regime": "range",
                "volatility_level": "low",
                "volatility_15m": 0.0005,
                "trend_15m": "up",
            },
            **overrides,
        )
        return [("/data/test", base)]

    def test_major_mae_75_only_btc_eth(self) -> None:
        rows = self._major_rows(decision_intent="enter_candidate", confidence=0.50, candidate_side="LONG")
        acc = simulate_major_mae_calibration_mode("major_mae_75", rows)
        self.assertIn("BTCUSDT", acc.per_symbol_graduations or acc.per_symbol_graduations.keys() or {"BTCUSDT": 0})
        sol = simulate_major_mae_calibration_mode(
            "major_mae_75",
            [("/data/test", _decision(symbol="SOLUSDT", decision_intent="enter_candidate", confidence=0.55))],
        )
        self.assertEqual(sol.hypothetical_graduation_count, 0)
        self.assertGreater(sol.sol_pepe_blocked_count, 0)

    def test_major_mae_90_graduation_possible(self) -> None:
        rows = self._major_rows(decision_intent="enter_candidate", confidence=0.50, candidate_side="LONG")
        acc = simulate_major_mae_calibration_mode("major_mae_90", rows)
        self.assertGreaterEqual(acc.hypothetical_graduation_count, 0)

    def test_major_mae_100_graduation_possible(self) -> None:
        rows = self._major_rows(decision_intent="enter_candidate", confidence=0.50, candidate_side="LONG")
        acc = simulate_major_mae_calibration_mode("major_mae_100", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 1)

    def test_sol_pepe_always_blocked(self) -> None:
        for mode in MAE_CALIBRATION_MODES:
            acc = simulate_major_mae_calibration_mode(
                mode,
                [("/data/test", _decision(symbol="PEPEUSDT", decision_intent="watch"))],
            )
            self.assertEqual(acc.hypothetical_graduation_count, 0)
            self.assertGreater(acc.sol_pepe_blocked_count, 0)

    def test_side_memory_uses_recent_side(self) -> None:
        rows = [
            (
                "/data/test",
                _decision(
                    decision_id="d0",
                    tick_index=1,
                    decision_intent="skip",
                    candidate_side="LONG",
                    confidence=0.44,
                ),
            ),
            (
                "/data/test",
                _decision(
                    decision_id="d1",
                    tick_index=2,
                    decision_intent="watch",
                    candidate_side="NONE",
                    confidence=0.45,
                    market_context={"last_price": 62000, "regime": "range", "volatility_level": "low", "volatility_15m": 0.0005},
                ),
            ),
            (
                "/data/test",
                _decision(
                    decision_id="d2",
                    tick_index=3,
                    decision_intent="watch",
                    candidate_side="NONE",
                    confidence=0.46,
                    market_context={"last_price": 62000, "regime": "range", "volatility_level": "low", "volatility_15m": 0.0005},
                ),
            ),
        ]
        acc = simulate_major_mae_calibration_mode("major_mae_100_side_memory", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)
        from tools.research.stage4_paper_event_logger import is_eligible_decision

        self.assertFalse(is_eligible_decision(rows[1][1]))

    def test_side_memory_records_side_source(self) -> None:
        rows = self._major_rows(decision_intent="enter_candidate", candidate_side="LONG", confidence=0.50)
        acc = simulate_major_mae_calibration_mode("major_mae_100_side_memory", rows)
        if acc.graduations:
            self.assertIn(acc.graduations[0].get("side_source"), {"decision_candidate_side", "recent_confirmed_side"})

    def test_confidence_floor_enforced(self) -> None:
        rows = self._major_rows(decision_intent="enter_candidate", candidate_side="LONG", confidence=0.30)
        acc = simulate_major_mae_calibration_mode("major_mae_100_side_memory_conf_floor", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)
        self.assertTrue(any("confidence_below" in k for k in acc.block_reason_counts))

    def test_graduation_count_in_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp = root / "in"
            paper = root / "paper"
            out = root / "out"
            inp.mkdir()
            paper.mkdir()
            decisions = [
                _decision(
                    decision_id="d1",
                    decision_intent="enter_candidate",
                    candidate_side="LONG",
                    confidence=0.50,
                    market_context={"last_price": 62000, "regime": "range", "volatility_level": "low", "volatility_15m": 0.0005},
                ),
            ]
            (inp / "ai_decisions.jsonl").write_text(json.dumps(decisions[0]) + "\n", encoding="utf-8")
            run_paper_event_logger([inp], output_dir=paper, mode="overwrite")
            summary = run_major_mae_calibration_replay(
                decision_dirs=[inp], paper_events_dir=paper, output_dir=out
            )
            self.assertIn("mode_results", summary)
            self.assertTrue((out / "stage4_18b_block_reason_matrix.json").is_file())

    def test_block_reason_matrix_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inp, paper, out = root / "in", root / "paper", root / "out"
            inp.mkdir()
            paper.mkdir()
            (inp / "ai_decisions.jsonl").write_text(
                json.dumps(_decision(decision_intent="watch")) + "\n",
                encoding="utf-8",
            )
            run_paper_event_logger([inp], output_dir=paper, mode="overwrite")
            run_major_mae_calibration_replay(decision_dirs=[inp], paper_events_dir=paper, output_dir=out)
            matrix = json.loads((out / "stage4_18b_block_reason_matrix.json").read_text(encoding="utf-8"))
            self.assertIn("major_mae_75", matrix)

    def test_calibration_no_order_sent(self) -> None:
        summary = run_major_mae_calibration_replay(
            decision_dirs=[],
            paper_events_dir=tempfile.mkdtemp(),
            output_dir=tempfile.mkdtemp(),
        )
        self.assertEqual(summary["order_sent_count"], 0)

    def test_calibration_no_exchange_path(self) -> None:
        import tools.research.stage4_watchlist_followup_simulator as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("urlopen", source)

    def test_calibration_production_not_touched(self) -> None:
        summary = run_major_mae_calibration_replay(
            decision_dirs=[],
            paper_events_dir=tempfile.mkdtemp(),
            output_dir=tempfile.mkdtemp(),
        )
        self.assertFalse(summary["production_touched"])
        self.assertFalse(summary["btc_auto_touched"])

    def test_input_dir_alias_for_decision_dir(self) -> None:
        import argparse
        from tools.research import stage4_watchlist_followup_simulator as mod

        parser = argparse.ArgumentParser()
        parser.add_argument("--decision-dir", "--input-dir", action="append", dest="decision_dirs", default=[])
        args = parser.parse_args(["--input-dir", "/data/test"])
        self.assertEqual(args.decision_dirs, ["/data/test"])
        self.assertIn("--input-dir", Path(mod.__file__).read_text(encoding="utf-8"))


class Stage418ELlmMaeCalibrationTests(unittest.TestCase):
    def test_llm_mae_calibration_graduation_with_high_legacy_vol(self) -> None:
        rows = [
            (
                "/data/test",
                _decision(
                    decision_id="d1",
                    tick_index=1,
                    decision_intent="watch",
                    candidate_side="LONG",
                    confidence=0.45,
                    mae_risk_estimate_pct=0.22,
                    market_context={
                        "last_price": 62000.0,
                        "regime": "range",
                        "volatility_level": "high",
                        "volatility_15m": 0.004,
                    },
                ),
            ),
            (
                "/data/test",
                _decision(
                    decision_id="d2",
                    tick_index=2,
                    decision_intent="watch",
                    candidate_side="LONG",
                    confidence=0.46,
                    mae_risk_estimate_pct=0.22,
                    market_context={
                        "last_price": 62000.0,
                        "regime": "range",
                        "volatility_level": "high",
                        "volatility_15m": 0.004,
                    },
                ),
            ),
        ]
        acc = simulate_major_mae_calibration_mode("major_mae_100_llm_mae", rows)
        self.assertGreater(acc.watchlist_confirmed, 0)
        self.assertGreater(acc.hypothetical_graduation_count, 0)

    def test_legacy_mode_blocks_same_rows_without_llm_mae(self) -> None:
        rows = [
            (
                "/data/test",
                _decision(
                    decision_id="d1",
                    tick_index=1,
                    decision_intent="watch",
                    candidate_side="LONG",
                    confidence=0.45,
                    market_context={
                        "last_price": 62000.0,
                        "regime": "range",
                        "volatility_level": "high",
                        "volatility_15m": 0.004,
                    },
                ),
            ),
        ]
        row = rows[0][1]
        row.pop("mae_risk_estimate_pct", None)
        acc = simulate_major_mae_calibration_mode("major_mae_100", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)

    def test_sol_pepe_blocked_in_llm_mae_modes(self) -> None:
        for mode in (
            "major_mae_100_llm_mae",
            "major_mae_100_llm_mae_side_memory",
            "major_mae_100_llm_mae_conf_floor",
        ):
            acc = simulate_major_mae_calibration_mode(
                mode,
                [("/data/test", _decision(symbol="SOLUSDT", decision_intent="watch", mae_risk_estimate_pct=0.10))],
            )
            self.assertEqual(acc.hypothetical_graduation_count, 0)
            self.assertGreater(acc.sol_pepe_blocked_count, 0)

    def test_llm_mae_mode_preferred_for_419_recommendation(self) -> None:
        mode_results = {
            "major_mae_100": {"hypothetical_graduation_count": 1},
            "major_mae_100_llm_mae": {"hypothetical_graduation_count": 2},
        }
        self.assertEqual(
            recommend_calibration_mode_for_419(mode_results),
            "major_mae_100_llm_mae",
        )

    def test_simulator_uses_llm_mae_in_llm_modes(self) -> None:
        row = _decision(mae_risk_estimate_pct=0.22, market_context={"volatility_level": "high"})
        mae, src = get_paper_mae_pct(row)
        self.assertEqual(src, MAE_SOURCE_LLM)


class Stage418CPaperReadinessSimulatorTests(unittest.TestCase):
    def test_simulator_blocks_decision_quality_incomplete(self) -> None:
        from tools.research.stage4_paper_event_logger import is_eligible_decision

        row = _decision(decision_intent="watch", decision_quality_incomplete=True, directional_bias="NONE")
        self.assertFalse(is_eligible_decision(row))

    def test_simulator_allows_paper_ready_watch(self) -> None:
        from tools.research.stage4_paper_event_logger import is_eligible_decision

        self.assertTrue(is_eligible_decision(_decision(decision_intent="watch")))

    def test_simulator_does_not_graduate_incomplete_watch(self) -> None:
        rows = [
            (
                "/data/test",
                _decision(
                    decision_id="d1",
                    tick_index=1,
                    decision_intent="watch",
                    symbol="BTCUSDT",
                    directional_bias="LONG",
                    watch_confirmation_reason="Support",
                    mae_risk_estimate_pct=0.40,
                    invalidation={
                        "invalidation_price": 61000.0,
                        "invalidation_reason": "SL",
                        "max_adverse_move_pct": 0.40,
                    },
                    paper_readiness={
                        "eligible_for_watchlist": True,
                        "eligible_for_hypothetical_entry": False,
                        "block_reason": "ok",
                    },
                ),
            ),
            (
                "/data/test",
                _decision(
                    decision_id="d2",
                    tick_index=2,
                    decision_intent="watch",
                    symbol="BTCUSDT",
                    directional_bias="LONG",
                    watch_confirmation_reason="Support",
                    mae_risk_estimate_pct=0.40,
                    invalidation={
                        "invalidation_price": 61000.0,
                        "invalidation_reason": "SL",
                        "max_adverse_move_pct": 0.40,
                    },
                    paper_readiness={
                        "eligible_for_watchlist": True,
                        "eligible_for_hypothetical_entry": False,
                        "block_reason": "ok",
                    },
                ),
            ),
        ]
        acc = simulate_major_mae_calibration_mode("major_mae_100_llm_mae", rows)
        self.assertEqual(acc.hypothetical_graduation_count, 0)


class Stage418HWatchlistRuntimeTests(unittest.TestCase):
    def test_runtime_version_check_importable(self) -> None:
        from tools.research.check_stage4_runtime_version import check_runtime_version

        root = Path(__file__).resolve().parents[1]
        summary = check_runtime_version(app_root=root)
        self.assertIn("runtime_version_check_passed", summary)

    def test_calibration_no_orders_sent(self) -> None:
        import tools.research.stage4_watchlist_followup_simulator as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("btc-auto", source)


class Stage418ICompareIntegrationTests(unittest.TestCase):
    def test_compare_tool_importable_from_simulator_context(self) -> None:
        from tools.research.stage4_mae_regression_compare import compare_mae_regressions

        self.assertTrue(callable(compare_mae_regressions))

    def test_no_production_btc_auto_in_compare(self) -> None:
        import tools.research.stage4_mae_regression_compare as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("btc-auto", source)
        self.assertNotIn("place_order", source)


class Stage418JSimulatorEnforcementTests(unittest.TestCase):
    def test_simulator_blocks_graduation_directional_bias_without_side(self) -> None:
        from tools.research.stage4_paper_event_logger import (
            _quality_blocked_skip_reason,
            is_eligible_decision,
        )

        watch_fields = {
            k: v
            for k, v in _watch_paper_fields().items()
            if k not in {"directional_bias", "mae_risk_estimate_pct"}
        }
        row = _decision(
            **watch_fields,
            decision_id="d1",
            tick_index=1,
            symbol="BTCUSDT",
            decision_intent="watch",
            candidate_side="NONE",
            directional_bias="LONG",
            confidence=0.5,
            mae_risk_estimate_pct=0.25,
        )
        row["directional_bias_without_candidate_side"] = True
        self.assertFalse(is_eligible_decision(row))
        self.assertEqual(
            _quality_blocked_skip_reason(row),
            "directional_bias_without_candidate_side",
        )
        acc = simulate_major_mae_calibration_mode(
            "major_mae_100_llm_mae",
            [("/data/test", row)],
        )
        self.assertEqual(acc.hypothetical_graduation_count, 0)


class Stage418MSimulatorStructuredOutputTests(unittest.TestCase):
    def test_simulator_blocks_mae_scale_drift_candidate(self) -> None:
        from tools.research.stage4_paper_readiness import apply_schema_level_enforcement

        proposal = apply_schema_level_enforcement(
            {
                "decision_intent": "watch",
                "symbol": "ETHUSDT",
                "candidate_side": "BUY",
                "directional_bias": "LONG",
                "watch_confirmation_reason": "x",
                "entry_trigger": {"type": "pullback_confirm", "trigger_price": 0, "trigger_condition": "x"},
                "invalidation": {"invalidation_price": 2991, "invalidation_reason": "x", "max_adverse_move_pct": 0.30},
                "mae_risk_estimate_pct": 2.0,
            }
        )
        self.assertTrue(proposal.get("mae_scale_drift_suspected"))
        self.assertFalse((proposal.get("paper_readiness") or {}).get("eligible_for_watchlist"))

    def test_simulator_no_exchange_call_path(self) -> None:
        import tools.research.stage4_watchlist_followup_simulator as mod

        source = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("place_order", source)
        self.assertNotIn("btc-auto", source)


if __name__ == "__main__":
    unittest.main()
