"""V15-C campaign orchestrator — two-pass, development-only, never qualification labels."""
from __future__ import annotations

import hashlib
import inspect
from pathlib import Path
from typing import Any

from backend.nexus_dev_research_campaign_v15 import data as data_mod
from backend.nexus_dev_research_campaign_v15 import features as features_mod
from backend.nexus_dev_research_campaign_v15 import simulate as simulate_mod
from backend.nexus_dev_research_campaign_v15.constants import (
    ALLOWED_LABELS,
    ARTIFACT_DIRNAME,
    BASE_COMMIT,
    BRANCH,
    CAMPAIGN_ID,
    FDR_Q_LEVEL,
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    PACKAGE,
    RANDOM_SEED,
    SCHEMA,
)
from backend.nexus_dev_research_campaign_v15.data import DevelopmentPanel, load_development_panel, panel_digest
from backend.nexus_dev_research_campaign_v15.fdr import benjamini_hochberg
from backend.nexus_dev_research_campaign_v15.hard_bans import env_hard_ban_guard
from backend.nexus_dev_research_campaign_v15.labeling import assign_label, label_histogram
from backend.nexus_dev_research_campaign_v15.simulate import (
    evaluate_all_mechanisms,
    mechanism_family_count,
)


def _code_checksum() -> str:
    blobs = [
        inspect.getsource(data_mod),
        inspect.getsource(features_mod),
        inspect.getsource(simulate_mod),
    ]
    return hashlib.sha256("\n".join(blobs).encode()).hexdigest()


def _label_evaluation(ev: dict[str, Any], *, mt_rejected: bool) -> dict[str, Any]:
    promising = False
    rejected = False
    if not ev.get("data_blocked") and not ev.get("sample_blocked"):
        net = float(ev.get("net_pnl") or 0.0)
        gross = float(ev.get("gross_pnl") or 0.0)
        # Development promising: net>0, not cost-destroyed, not regime-fragile, survives MT
        if (
            net > 0
            and not ev.get("cost_destroyed")
            and not ev.get("regime_fragile")
            and not mt_rejected
        ):
            promising = True
        elif gross <= 0 and net <= 0:
            rejected = True
        elif net <= 0 and not ev.get("cost_destroyed"):
            rejected = True

    info = assign_label(
        data_blocked=bool(ev.get("data_blocked")),
        sample_blocked=bool(ev.get("sample_blocked")),
        multiple_testing_rejected=bool(mt_rejected) and not bool(ev.get("data_blocked")) and not bool(ev.get("sample_blocked")),
        cost_destroyed=bool(ev.get("cost_destroyed")) and not bool(ev.get("data_blocked")) and not bool(ev.get("sample_blocked")),
        regime_fragile=bool(ev.get("regime_fragile"))
        and not bool(ev.get("data_blocked"))
        and not bool(ev.get("sample_blocked"))
        and not bool(ev.get("cost_destroyed")),
        development_promising=promising,
        rejected=rejected,
    )
    return {
        **ev,
        "label": info["label"],
        "result_label": info["label"],
        "label_info": info,
    }


def run_campaign(
    *,
    root: Path,
    panel: DevelopmentPanel | None = None,
    seed: int = RANDOM_SEED,
    use_network: bool = True,
    allow_fixture_fallback: bool = True,
    pass_id: int = 1,
) -> dict[str, Any]:
    env = env_hard_ban_guard()
    if not env["ok"]:
        raise RuntimeError(f"hard ban env violations: {env['violations']}")

    if panel is None:
        panel = load_development_panel(
            root=root,
            use_network=use_network,
            allow_fixture_fallback=allow_fixture_fallback,
        )

    raw = evaluate_all_mechanisms(panel)

    # Multiple testing only over candidates that are not data/sample blocked.
    testable_idx = [
        i
        for i, r in enumerate(raw)
        if not r.get("data_blocked") and not r.get("sample_blocked")
    ]
    p_values = [float(raw[i]["p_value"]) for i in testable_idx]
    bh = benjamini_hochberg(p_values, q=FDR_Q_LEVEL)
    mt_reject_by_idx: dict[int, bool] = {}
    for local_i, global_i in enumerate(testable_idx):
        # Rejected by MT means NOT a BH discovery (fail closed for promising path)
        # OR raw p fails Bonferroni.
        adj = bh["bh_adjusted_p"][local_i]
        discoveries = set(bh["rejected_indices"])
        # For labeling MULTIPLE_TESTING_REJECTED: candidate had weak evidence under FDR
        # when gross suggests a "hit" that doesn't survive multiplicity.
        gross = float(raw[global_i].get("gross_pnl") or 0.0)
        net = float(raw[global_i].get("net_pnl") or 0.0)
        looks_positive = net > 0 or gross > 0
        survived = local_i in discoveries
        mt_reject_by_idx[global_i] = bool(looks_positive and not survived and adj > FDR_Q_LEVEL)

    labeled = [
        _label_evaluation(r, mt_rejected=mt_reject_by_idx.get(i, False)) for i, r in enumerate(raw)
    ]
    hist = label_histogram(labeled)
    labels_used = {e["label"] for e in labeled}
    assert labels_used <= ALLOWED_LABELS

    # Universe / regime / symbol partition summaries
    symbol_partition = {}
    for e in labeled:
        for sym, net in (e.get("symbol_net") or {}).items():
            symbol_partition.setdefault(sym, {"mechanism_count": 0, "net_sum": 0.0})
            symbol_partition[sym]["mechanism_count"] += 1
            symbol_partition[sym]["net_sum"] += float(net)

    regime_partition: dict[str, int] = {}
    for e in labeled:
        for reg, cnt in (e.get("regime_breakdown") or {}).items():
            regime_partition[reg] = regime_partition.get(reg, 0) + int(cnt)

    digest = panel_digest(panel)
    report = {
        "schema": SCHEMA,
        "package": PACKAGE,
        "campaign_id": CAMPAIGN_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "pass_id": pass_id,
        "seed": seed,
        "hard_bans": sorted(HARD_BANS),
        "non_claims": list(NON_CLAIMS),
        "env_guard": env,
        "code_checksum": _code_checksum(),
        "panel_digest": digest,
        "data_lineage": panel.classification,
        "fixture_used": panel.fixture_used,
        "fixture_never_called_real": True,
        "development_interval_id": panel.development_interval_id,
        "data_provenance": panel.provenance,
        "mechanism_count": len(labeled),
        "mechanism_family_count": mechanism_family_count(labeled),
        "evaluations": labeled,
        "label_histogram": hist,
        "multiple_testing": {
            "q": FDR_Q_LEVEL,
            "testable_count": len(testable_idx),
            "bh": bh,
            "mt_rejected_count": sum(1 for v in mt_reject_by_idx.values() if v),
        },
        "dynamic_universe": {
            "symbols": panel.symbols,
            "interval": panel.interval,
            "symbol_partition": symbol_partition,
        },
        "regime_partition": regime_partition,
        "cost_model_authority": "backend.nexus_execution.cost_model",
        "execution_sensitivity": {
            "spread_model": "hl_range_proxy_noted",
            "impact_bps_default": 2.0,
            "funding_asof": True,
        },
        "experiment_registry_hooks": {
            "campaign_id": CAMPAIGN_ID,
            "artifact_dirname": ARTIFACT_DIRNAME,
            "panel_digest": digest,
            "registered": True,
        },
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "qualification_ready_count": 0,
        "qualified_claimed": False,
        "profitability_claimed": False,
        "profitability_claim_count": 0,
        "edge_claimed": False,
        "edge_claim_count": 0,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_touch_count": 0,
        "auto_integrate": False,
        "pr27_merge_attempted": False,
        "development_only": True,
        "status_json_emitted": False,
    }
    return report
