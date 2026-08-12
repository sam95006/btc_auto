"""V1.2 preregistration — same 12 mechanisms, new checksums; does not mutate V1.1."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_strategy_engine.cost_semantics import COST_MODEL_VERSION
from backend.nexus_strategy_engine.data_bundle import DATA_BUNDLE_VERSION
from backend.nexus_strategy_engine.executors import get_executor
from backend.nexus_strategy_engine.hypotheses_v1_1 import default_v11_hypothesis_drafts
from backend.nexus_strategy_engine.strategy_spec import freeze_spec, sha_obj


def default_v12_hypothesis_drafts() -> list[dict[str, Any]]:
    drafts = []
    for d in default_v11_hypothesis_drafts():
        nd = deepcopy(d)
        nd["strategy_id"] = d["strategy_id"].replace("V11_", "V12_")
        nd["hypothesis_id"] = nd["strategy_id"]
        nd["strategy_version"] = "dev_v1_2"
        nd["parameter_source"] = "carried_forward_economic_prior_not_v11_pnl_tuned"
        nd["v1_1_preregistration_mutated"] = False
        # Ensure no V1.1 PnL-based retune
        params = dict(nd.get("parameter_values") or {})
        params.pop("execution_engine_checksum", None)
        nd["parameter_values"] = params
        drafts.append(nd)
    return drafts


def preregister_v12_hypotheses(
    *,
    research_universe_snapshot_checksum: str,
    data_bundle_checksum: str,
) -> dict[str, Any]:
    drafts = default_v12_hypothesis_drafts()
    frozen = []
    for d in drafts:
        ex = get_executor(d["component_id"])
        assert ex.implemented
        d = deepcopy(d)
        d["execution_engine_checksum"] = ex.checksum()
        d["component_executor_checksum"] = ex.checksum()
        d["data_bundle_version"] = DATA_BUNDLE_VERSION
        d["cost_model_version"] = COST_MODEL_VERSION
        d["research_universe_snapshot_checksum"] = research_universe_snapshot_checksum
        d["data_bundle_checksum"] = data_bundle_checksum
        params = dict(d.get("parameter_values") or {})
        params.update(
            {
                "execution_engine_checksum": ex.checksum(),
                "research_universe_snapshot_checksum": research_universe_snapshot_checksum,
                "data_bundle_checksum": data_bundle_checksum,
                "cost_model_version": COST_MODEL_VERSION,
            }
        )
        d["parameter_values"] = params
        if isinstance(d.get("eligible_symbol_profile"), dict):
            d["eligible_symbol_profile"] = {**d["eligible_symbol_profile"], "params": params}
        frozen.append(freeze_spec(d))
    families = sorted({h["strategy_family"] for h in frozen})
    return {
        "schema": "ai_hypothesis_preregistration_v1_2",
        "package": "STRATEGY_ENGINE_V1_2",
        "created_before_execution": True,
        "v1_1_mutated": False,
        "v1_mutated": False,
        "generated_hypothesis_count": len(frozen),
        "preregistered_hypothesis_count": len(frozen),
        "strategy_family_count": len(families),
        "strategy_families": families,
        "distinct_component_count": len({h["component_id"] for h in frozen}),
        "research_universe_snapshot_checksum": research_universe_snapshot_checksum,
        "data_bundle_checksum": data_bundle_checksum,
        "hypotheses": frozen,
        "formal_walk_forward_forbidden_in_this_task": True,
        "oos_creation_forbidden": True,
        "demo_forbidden": True,
        "universe_checksum_proof": sha_obj({"universe": research_universe_snapshot_checksum, "bundle": data_bundle_checksum}),
    }
