from __future__ import annotations

from backend.nexus_research_ai_autonomy.lifecycle_purpose import LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
from backend.nexus_research_ai_autonomy.win_rate_rolling_v29 import compute_research_rolling_stats


def _make_lifecycle(i: int, net: float, side: str = "LONG") -> dict:
    return {
        "lifecycle_purpose": LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
        "side": side,
        "wallet_reconciliation": {"WALLET_RECONCILIATION_PASS": True},
        "exact_pnl_accounting": {
            "accounting_complete": True,
            "calculated_net_pnl": net,
        },
        "path_excursion": {"mfe_capture_ratio": 0.5 + (i % 3) * 0.1},
    }


def test_last_10_and_last_30_windows_metrics_roll_forward_in_order():
    nets = []
    lifecycles = []
    for i in range(35):
        # alternate win/loss to avoid edge cases
        net = 1.0 if i % 2 == 0 else -0.5
        nets.append(net)
        lifecycles.append(_make_lifecycle(i, net=net))

    out = compute_research_rolling_stats(lifecycles)
    last_10_nets = nets[-10:]
    last_30_nets = nets[-30:]

    assert out["last_10"]["n"] == 10
    assert out["last_30"]["n"] == 30
    assert out["last_10"]["net_pnl"] == sum(last_10_nets)
    assert out["last_30"]["net_pnl"] == sum(last_30_nets)

