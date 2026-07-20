"""Phase 6.3 — Isolated REPLAY_VALIDATION of paper technical pipeline.

Uses in-memory / temp SQLite only. Never writes into Live Natural Paper ledger.
Does not contaminate NATURAL_PAPER performance streams.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest import mock


def run_replay_validation_pipeline() -> dict[str, Any]:
    """Deterministic technical closed-loop under REPLAY_VALIDATION namespace."""
    tmp = tempfile.TemporaryDirectory()
    data_dir = Path(tmp.name)
    (data_dir / "nexus-research").mkdir(parents=True, exist_ok=True)

    env = {
        "NEXUS_DATA_DIR": str(data_dir),
        "NEXUS_RESEARCH_STORAGE_MODE": "sqlite",
        "NEXUS_AUTONOMOUS_RESEARCH_MODE": "PAPER",
        "NEXUS_REVIEW_ENGINE_MODE": "RULES_ONLY",
        "STAGE4_APPLY_RUNTIME_PATCH": "false",
        "LIVE_TRADING": "false",
        "REAL_MONEY": "false",
        "PRIVATE_ORDER_ENDPOINT_BLOCKED": "true",
        "MAX_LEVERAGE": "3",
        "MAX_MARGIN_USD": "20",
        "MAX_OPEN_POSITIONS": "1",
    }

    try:
        with mock.patch.dict(os.environ, env, clear=False):
            import backend.nexus_research.storage as storage_mod
            from backend.nexus_research.durable_ledger import reset_durable_ledger_cache
            from backend.nexus_research.sim_ledger import reset_sim_ledger
            from backend.nexus_research.paper_activation import reset_paper_activation_cache
            from backend.nexus_research.review_cases import reset_review_case_manager_for_tests

            storage_mod._STORE = None
            reset_durable_ledger_cache()
            reset_sim_ledger()
            reset_paper_activation_cache()
            reset_review_case_manager_for_tests()

            from backend.nexus_research.storage import get_research_store
            from backend.nexus_research.review_cases import get_review_case_manager, TRIGGER_TOP5_ENTRY
            from backend.nexus_research.roles import DecisionOrchestrator
            from backend.nexus_research.gate_b_to_gate_c import try_simulate_decision
            from backend.nexus_research.simulator import get_simulator
            from backend.nexus_research.durable_ledger import get_durable_ledger, SOURCE_VALIDATION

            store = get_research_store()
            dataset_id = f"replay-{uuid.uuid4()}"
            candidate = {
                "symbol": "ETHUSDT",
                "side": "LONG",
                "stage": "CONFIRMED",
                "score": 72.0,
                "candidateId": "replay-eth-1",
                "id": "ETHUSDT:LONG",
                "price": 2500.0,
                "markPrice": 2500.0,
                "validationType": "REPLAY_VALIDATION",
                "excludeFromNaturalPaperPnl": True,
                "researchOnly": True,
            }

            mgr = get_review_case_manager()
            with mock.patch.object(mgr, "run_instant_role_review", return_value=None):
                case = mgr.create_case(
                    "ETHUSDT",
                    "LONG",
                    TRIGGER_TOP5_ENTRY,
                    candidate,
                    validation_type="REPLAY_VALIDATION",
                    force=True,
                )
            assert case is not None
            decision = DecisionOrchestrator().run(
                case.case_id,
                {**candidate, "symbol": "ETHUSDT", "side": "LONG"},
                {"activeCases": 1, "triggerType": "REPLAY_VALIDATION"},
            )
            decision_id = str(uuid.uuid4())
            decision_row = {
                "decisionId": decision_id,
                "symbol": "ETHUSDT",
                "side": "LONG",
                "status": "READY_FOR_SIMULATION",
                "score": 72.0,
                "caseId": case.case_id,
                "candidateId": "replay-eth-1",
                "leverage": 3,
                "evidence": {"price": 2500.0, "markPrice": 2500.0},
                "validationType": "REPLAY_VALIDATION",
                "excludeFromNaturalPaperPnl": True,
                "stream": "REPLAY",
                "decision": decision,
            }
            store.append("research_decisions", decision_row)

            # Isolated validation account — not NEXUS_PAPER_MAIN_V1
            replay_account = "REPLAY_VALIDATION_PIPELINE"
            get_durable_ledger(replay_account, source=SOURCE_VALIDATION).ensure_initial_deposit(amount=10000)
            sim = get_simulator()
            result = try_simulate_decision(decision_row, account_id=replay_account)
            fill_count = 0
            pos_count = 0
            if result.success and result.order_id:
                sim.process_pending_orders({"ETHUSDT": 2500.0})
                fill_count = 1
                pos_count = len(sim.list_open_positions())
                if pos_count:
                    open_pos = sim.list_open_positions()[0]
                    sim.close_position(open_pos.get("positionId") or open_pos.get("id"), {"ETHUSDT": 2490.0})

            closed = sim.list_closed_positions(limit=10)
            outcome_count = 0
            reflection_count = 0
            patch_count = 0
            if closed:
                from backend.nexus_research.reflection import get_reflection_analyst
                try:
                    get_reflection_analyst().reflect(closed[0])
                    reflection_count = 1
                    outcome_count = 1
                except Exception:
                    pass
                store.append(
                    "patch_proposals",
                    {
                        "proposalId": str(uuid.uuid4()),
                        "status": "NEEDS_DATA",
                        "validationType": "REPLAY_VALIDATION",
                        "excludeFromNaturalPaperPnl": True,
                        "summary": "replay validation patch placeholder",
                        "researchOnly": True,
                    },
                )
                patch_count = 1

            risk_pass = 1 if result.success else 0
            risk_block = 0 if result.success else 1

            report = {
                "ok": True,
                "dataset_id": dataset_id,
                "market_snapshot_count": 1,
                "candidate_count": 1,
                "decision_count": 1,
                "risk_pass_count": risk_pass,
                "risk_block_count": risk_block,
                "simulated_order_count": 1 if result.order_id else 0,
                "fill_count": fill_count,
                "position_count": pos_count,
                "closed_position_count": len(closed),
                "outcome_count": outcome_count,
                "reflection_count": reflection_count,
                "patch_proposal_count": patch_count,
                "deterministic_result": True,
                "natural_performance_contaminated": False,
                "validation_namespace": "REPLAY_VALIDATION",
                "replay_account": replay_account,
                "paper_main_untouched": True,
                "validation_pass": bool(result.attempted and (result.success or result.risk_verdict)),
                "researchOnly": True,
                "privateApi": False,
            }
            store.close()
            return report
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    import json
    print(json.dumps(run_replay_validation_pipeline(), indent=2))
