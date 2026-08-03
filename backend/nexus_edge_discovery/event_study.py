"""Event Study Engine V1 — predictive value of events before trade geometry."""
from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from backend.nexus_edge_discovery import BOOTSTRAP_BLOCK_BARS, BOOTSTRAP_REPLICATES, FORWARD_HORIZONS, RANDOM_SEED
from backend.nexus_strategy_engine.data_bundle import ResearchDataBundle
from backend.nexus_strategy_engine.executors import ScanContext, get_executor


def _sha(obj: Any) -> str:
    import json

    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


@dataclass
class EventObservation:
    component_id: str
    symbol: str
    side: str
    regime: str
    size_class: str
    entry_index: int
    decision_ts: int
    entry_price: float
    forward: dict[str, float | None]
    mfe: float | None
    mae: float | None
    mfe_before_mae: bool | None
    is_trade: bool = False  # event-study observations are NEVER trades


def _forward_metrics(candles, i: int, side: str, horizons=FORWARD_HORIZONS) -> dict[str, Any]:
    if i < 0 or i >= len(candles):
        return {"forward": {}, "mfe": None, "mae": None, "mfe_before_mae": None}
    px = float(candles[i].close)
    fwd: dict[str, float | None] = {}
    for h in horizons:
        j = i + h
        if j >= len(candles):
            fwd[f"ret_{h}"] = None
            continue
        px2 = float(candles[j].close)
        raw = (px2 - px) / max(px, 1e-12)
        fwd[f"ret_{h}"] = raw if side == "Buy" else -raw
    # MFE/MAE over max horizon available
    max_h = min(max(horizons), len(candles) - i - 1)
    mfe = mae = None
    mfe_before_mae = None
    if max_h >= 1:
        path = []
        for k in range(1, max_h + 1):
            c = candles[i + k]
            if side == "Buy":
                fav = (float(c.high) - px) / px
                adv = (px - float(c.low)) / px
            else:
                fav = (px - float(c.low)) / px
                adv = (float(c.high) - px) / px
            path.append((fav, adv, k))
        mfe = max(p[0] for p in path)
        mae = max(p[1] for p in path)
        first_mfe = next((p[2] for p in path if p[0] >= mfe * 0.999), None)
        first_mae = next((p[2] for p in path if p[1] >= mae * 0.999), None)
        if first_mfe is not None and first_mae is not None:
            mfe_before_mae = first_mfe < first_mae
    return {"forward": fwd, "mfe": mfe, "mae": mae, "mfe_before_mae": mfe_before_mae}


def collect_component_events(
    component_id: str,
    bundles: list[ResearchDataBundle],
    *,
    stride: int = 12,
    cooldown: int = 16,
) -> list[EventObservation]:
    ex = get_executor(component_id)
    if not ex.implemented:
        return []
    out: list[EventObservation] = []
    peers = {}
    for b in bundles:
        c = b.candles_15
        if not c or len(c) < 50:
            continue
        lb = 16
        i = len(c) - 10
        if i > lb:
            peers[b.symbol] = (c[i].close - c[i - lb].close) / max(c[i - lb].close, 1e-9)
    btc_ret = peers.get("BTCUSDT")
    need_deriv = component_id in {"FUNDING_OI_CONTINUATION", "FUNDING_OI_CONTRARIAN", "MARK_INDEX_BASIS_ANOMALY"}
    for b in bundles:
        if not b.candles_15 or len(b.candles_15) < 60:
            continue
        if need_deriv and component_id.startswith("FUNDING") and (not b.funding_points or not b.oi_points):
            continue
        if component_id == "MARK_INDEX_BASIS_ANOMALY" and (not b.mark_15 or not b.index_15):
            continue
        ctx = ScanContext(
            symbol=b.symbol,
            candles_15=b.candles_15,
            candles_60=b.candles_60 or None,
            candles_240=b.candles_240 or None,
            funding_points=b.funding_points or None,
            oi_points=b.oi_points or None,
            mark_candles=b.mark_15 or None,
            index_candles=b.index_15 or None,
            peer_returns_at_ts=peers if component_id in {"RELATIVE_STRENGTH", "CROSS_SECTIONAL_MOMENTUM"} else None,
            btc_return_at_ts=btc_ret,
        )
        try:
            sigs = ex.scan(ctx, stride=stride, cooldown=cooldown)
        except TypeError:
            sigs = ex.scan(ctx)
        for sig in sigs:
            if getattr(sig, "late_entry_rejected", False):
                continue
            i = int(sig.entry_index)
            # Point-in-time: only use candles <= decision bar
            metrics = _forward_metrics(b.candles_15, i, sig.side)
            out.append(
                EventObservation(
                    component_id=component_id,
                    symbol=b.symbol,
                    side=sig.side,
                    regime=str(sig.regime),
                    size_class=getattr(b, "size_class", None) or "UNKNOWN",
                    entry_index=i,
                    decision_ts=int(b.candles_15[i].ts_ms),
                    entry_price=float(sig.entry_price),
                    forward=metrics["forward"],
                    mfe=metrics["mfe"],
                    mae=metrics["mae"],
                    mfe_before_mae=metrics["mfe_before_mae"],
                    is_trade=False,
                )
            )
    return out


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return s[m] if len(s) % 2 else 0.5 * (s[m - 1] + s[m])


def summarize_events(events: list[EventObservation], *, horizon_key: str = "ret_8") -> dict[str, Any]:
    rets = [float(e.forward[horizon_key]) for e in events if e.forward.get(horizon_key) is not None]
    hits = [1.0 if r > 0 else 0.0 for r in rets]
    return {
        "event_count": len(events),
        "observation_is_trade": False,
        "horizon": horizon_key,
        "mean_forward_return": _mean(rets),
        "median_forward_return": _median(rets),
        "directional_hit_rate": _mean(hits),
        "downside_tail_return": _percentile(rets, 5) if rets else None,
        "upside_tail_return": _percentile(rets, 95) if rets else None,
        "mean_mfe": _mean([e.mfe for e in events if e.mfe is not None]),
        "mean_mae": _mean([e.mae for e in events if e.mae is not None]),
    }


def _percentile(xs: list[float], p: float) -> float:
    s = sorted(xs)
    if not s:
        return 0.0
    k = (len(s) - 1) * p / 100.0
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def chronological_folds(events: list[EventObservation], n: int = 5) -> list[list[EventObservation]]:
    ordered = sorted(events, key=lambda e: e.decision_ts)
    if not ordered:
        return [[] for _ in range(n)]
    size = max(1, len(ordered) // n)
    folds = []
    for i in range(n):
        a = i * size
        b = len(ordered) if i == n - 1 else (i + 1) * size
        folds.append(ordered[a:b])
    return folds


def block_bootstrap_ci(
    returns: list[float],
    *,
    block_size: int = BOOTSTRAP_BLOCK_BARS,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = RANDOM_SEED,
    alpha: float = 0.05,
) -> dict[str, Any]:
    rng = random.Random(seed)
    if len(returns) < max(block_size, 2):
        m = _mean(returns)
        return {
            "mean": m,
            "ci_low": m,
            "ci_high": m,
            "bootstrap_method": "chronological_block_bootstrap",
            "bootstrap_block_size": block_size,
            "replicates": 0,
            "random_seed": seed,
            "insufficient": True,
        }
    n = len(returns)
    means = []
    for _ in range(replicates):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.randrange(0, max(1, n - block_size + 1))
            sample.extend(returns[start : start + block_size])
        sample = sample[:n]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(alpha / 2 * len(means))]
    hi = means[int((1 - alpha / 2) * len(means)) - 1]
    return {
        "mean": _mean(returns),
        "ci_low": lo,
        "ci_high": hi,
        "bootstrap_method": "chronological_block_bootstrap",
        "bootstrap_block_size": block_size,
        "replicates": replicates,
        "random_seed": seed,
        "insufficient": False,
    }


def benjamini_hochberg(pvalues: list[tuple[str, float]], *, q: float = 0.10) -> dict[str, Any]:
    """Return FDR-adjusted significance decisions."""
    m = len(pvalues)
    if m == 0:
        return {
            "hypothesis_test_count": 0,
            "raw_significant_count": 0,
            "FDR_adjusted_significant_count": 0,
            "false_discovery_rate": q,
            "tests": [],
        }
    ranked = sorted(pvalues, key=lambda x: x[1])
    thresh = {}
    max_i = 0
    for i, (name, p) in enumerate(ranked, start=1):
        if p <= (i / m) * q:
            max_i = i
        thresh[name] = (i / m) * q
    rejected = {name for name, _ in ranked[:max_i]}
    raw_sig = sum(1 for _, p in pvalues if p < 0.05)
    tests = []
    for name, p in pvalues:
        tests.append(
            {
                "test_id": name,
                "p_value": p,
                "bh_threshold": thresh[name],
                "raw_significant": p < 0.05,
                "fdr_significant": name in rejected,
            }
        )
    return {
        "hypothesis_test_count": m,
        "raw_significant_count": raw_sig,
        "FDR_adjusted_significant_count": len(rejected),
        "false_discovery_rate": q,
        "tests": tests,
    }


def one_sided_mean_pvalue(returns: list[float], *, seed: int = RANDOM_SEED) -> float:
    """Simple bootstrap one-sided p that mean > 0."""
    if len(returns) < 5:
        return 1.0
    rng = random.Random(seed)
    obs = sum(returns) / len(returns)
    if obs <= 0:
        return 1.0
    n = len(returns)
    ge = 0
    centered = [r - obs for r in returns]
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = [centered[rng.randrange(n)] for _ in range(n)]
        if sum(sample) / n >= obs:
            ge += 1
    return (ge + 1) / (BOOTSTRAP_REPLICATES + 1)


def run_event_study(
    bundles: list[ResearchDataBundle],
    component_ids: list[str],
) -> dict[str, Any]:
    registry = []
    summaries = []
    pvals: list[tuple[str, float]] = []
    total_obs = 0
    for cid in component_ids:
        events = collect_component_events(cid, bundles)
        total_obs += len(events)
        # Ensure none are trades
        assert all(not e.is_trade for e in events)
        summ8 = summarize_events(events, horizon_key="ret_8")
        folds = chronological_folds(events, 5)
        pos_folds = 0
        fold_means = []
        for fr in folds:
            sm = summarize_events(fr, horizon_key="ret_8")
            m = sm.get("mean_forward_return")
            fold_means.append(m)
            if m is not None and m > 0:
                pos_folds += 1
        rets = [float(e.forward["ret_8"]) for e in events if e.forward.get("ret_8") is not None]
        boot = block_bootstrap_ci(rets, seed=RANDOM_SEED + abs(hash(cid)) % 10_000)
        p = one_sided_mean_pvalue(rets, seed=RANDOM_SEED + abs(hash(cid)) % 10_000)
        test_id = f"{cid}::ret_8"
        pvals.append((test_id, p))
        # symbol/regime concentration on positive returns
        by_sym: dict[str, float] = defaultdict(float)
        by_reg: dict[str, float] = defaultdict(float)
        pos_sum = 0.0
        for e in events:
            r = e.forward.get("ret_8")
            if r is None or r <= 0:
                continue
            by_sym[e.symbol] += float(r)
            by_reg[e.regime] += float(r)
            pos_sum += float(r)
        largest_sym = (max(by_sym.values()) / pos_sum) if pos_sum > 0 and by_sym else 0.0
        largest_reg = (max(by_reg.values()) / pos_sum) if pos_sum > 0 and by_reg else 0.0
        horizons = {hk: summarize_events(events, horizon_key=hk) for hk in (f"ret_{h}" for h in FORWARD_HORIZONS)}
        entry = {
            "component_id": cid,
            "event_count": len(events),
            "summary_ret_8": summ8,
            "horizons": horizons,
            "fold_count": 5,
            "positive_fold_count": pos_folds,
            "fold_means_ret_8": fold_means,
            "bootstrap": boot,
            "p_value_mean_gt_0": p,
            "largest_symbol_contribution": largest_sym,
            "largest_regime_contribution": largest_reg,
            "effect_size": summ8.get("mean_forward_return"),
            "supported_raw_signal_candidate": bool(
                len(events) >= 30
                and summ8.get("mean_forward_return") is not None
                and float(summ8["mean_forward_return"]) > 0
                and pos_folds >= 3
                and boot.get("ci_low") is not None
                and float(boot["ci_low"]) > 0
            ),
        }
        summaries.append(entry)
        registry.append(
            {
                "component_id": cid,
                "event_study_id": _sha({"c": cid, "n": len(events), "h": "ret_8"}),
                "event_count": len(events),
                "observations_are_trades": False,
            }
        )
    fdr = benjamini_hochberg(pvals, q=0.10)
    supported = [
        s
        for s in summaries
        if s.get("supported_raw_signal_candidate")
        and any(t["test_id"].startswith(s["component_id"]) and t["fdr_significant"] for t in fdr["tests"])
    ]
    return {
        "schema": "event_study_summary_v1",
        "engine": "NEXUS_EVENT_STUDY_ENGINE_V1",
        "event_study_component_count": len(component_ids),
        "event_study_observation_count": total_obs,
        "random_seed": RANDOM_SEED,
        "forward_horizons_bars": list(FORWARD_HORIZONS),
        "registry": registry,
        "components": summaries,
        "statistical_controls": {
            **fdr,
            "bootstrap_method": "chronological_block_bootstrap",
            "bootstrap_block_size": BOOTSTRAP_BLOCK_BARS,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "random_seed": RANDOM_SEED,
            "seeds_frozen_before_execution": True,
        },
        "raw_supported_signal_count": len(supported),
        "supported_signals": supported,
        "multiple_testing_note": "Horizons pre-registered; primary test horizon=ret_8; FDR applied across components",
    }
