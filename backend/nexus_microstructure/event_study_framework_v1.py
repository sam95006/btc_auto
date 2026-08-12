"""Microstructure Event Study Engine Framework V1 — engine only, no real study execution."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: str) -> str:
    return hashlib.sha256(obj.encode()).hexdigest()


@dataclass
class SyntheticEvent:
    event_id: str
    symbol: str
    exchange_ts_ms: int
    corrected_ts_ms: int
    family: str
    payload: dict[str, Any]
    source_partition_id: str
    source_checksum: str


class EventStudyEngineFrameworkV1:
    """Deterministic framework for future microstructure event studies.

    Does not select thresholds using future outcomes.
    Does not claim predictive edge.
    """

    def __init__(self) -> None:
        self.event_study_real_execution = False
        self.new_strategy_generated_count = 0
        self.profitability_claim_count = 0

    def load_point_in_time(self, events: Iterable[SyntheticEvent], *, as_of_ms: int) -> list[SyntheticEvent]:
        return [e for e in events if e.corrected_ts_ms <= as_of_ms]

    def clock_corrected_order(self, events: list[SyntheticEvent]) -> list[SyntheticEvent]:
        return sorted(events, key=lambda e: (e.corrected_ts_ms, e.symbol, e.event_id))

    def cluster_events(self, events: list[SyntheticEvent], *, window_ms: int) -> list[list[SyntheticEvent]]:
        if not events:
            return []
        ordered = self.clock_corrected_order(events)
        clusters: list[list[SyntheticEvent]] = [[ordered[0]]]
        for ev in ordered[1:]:
            if ev.corrected_ts_ms - clusters[-1][-1].corrected_ts_ms <= window_ms and ev.symbol == clusters[-1][-1].symbol:
                clusters[-1].append(ev)
            else:
                clusters.append([ev])
        return clusters

    def forward_labels(
        self,
        *,
        entry_price: float,
        path: list[float],
        horizons: list[int],
    ) -> dict[str, Any]:
        """Label MFE/MAE and adverse-first ambiguity on a synthetic price path."""
        out = {}
        for h in horizons:
            segment = path[: max(1, min(len(path), h))]
            rets = [(p - entry_price) / entry_price for p in segment]
            mfe = max(rets) if rets else 0.0
            mae = min(rets) if rets else 0.0
            # Adverse-first: did MAE threshold precede MFE within same bar window?
            adverse_first = False
            for r in rets:
                if r <= mae and mae < 0:
                    adverse_first = True
                    break
                if r >= mfe and mfe > 0:
                    break
            out[str(h)] = {
                "forward_return": rets[-1] if rets else 0.0,
                "MFE": mfe,
                "MAE": mae,
                "adverse_first_ambiguity": adverse_first,
            }
        return out

    def chronological_folds(self, n: int, *, folds: int = 5) -> list[dict[str, Any]]:
        if n <= 0:
            return []
        size = max(1, n // folds)
        result = []
        for i in range(folds):
            start = i * size
            end = n if i == folds - 1 else min(n, (i + 1) * size)
            result.append({"fold": i, "train_end": start, "test_start": start, "test_end": end})
        return result

    def block_bootstrap_indices(self, n: int, *, block: int, samples: int, seed: int = 7) -> list[list[int]]:
        # Deterministic LCG
        state = seed
        out = []
        for _ in range(samples):
            idxs = []
            while len(idxs) < n:
                state = (1103515245 * state + 12345) % (2**31)
                start = state % max(1, n - block + 1)
                idxs.extend(list(range(start, min(n, start + block))))
            out.append(idxs[:n])
        return out

    def fdr_bh(self, p_values: list[float], *, q: float = 0.05) -> list[bool]:
        m = len(p_values)
        if m == 0:
            return []
        order = sorted(range(m), key=lambda i: p_values[i])
        rejected = [False] * m
        max_i = -1
        for rank, idx in enumerate(order, start=1):
            if p_values[idx] <= (rank / m) * q:
                max_i = rank
        for rank, idx in enumerate(order, start=1):
            if rank <= max_i:
                rejected[idx] = True
        return rejected

    def cost_bridge(self, gross: float, *, fee_bps: float, slip_bps: float) -> dict[str, float]:
        cost = (fee_bps + slip_bps) / 10000.0
        return {"gross": gross, "net": gross - cost, "cost": cost}

    def lineage(self, events: list[SyntheticEvent]) -> dict[str, Any]:
        parts = sorted({(e.source_partition_id, e.source_checksum) for e in events})
        material = "|".join(f"{a}:{b}" for a, b in parts)
        return {
            "source_partition_count": len(parts),
            "lineage_checksum": _sha(material),
            "partitions": [{"partition_id": a, "checksum": b} for a, b in parts],
        }

    def preregistration_schema(self) -> dict[str, Any]:
        return {
            "schema": "event_study_preregistration_v1",
            "required_fields": [
                "research_question_id",
                "economic_mechanism",
                "required_data",
                "event_definition_version",
                "decision_timestamp_definition",
                "forward_horizons",
                "segmentation_plan",
                "multiple_testing_plan",
                "cost_dependency",
                "failure_conditions",
                "minimum_data_depth",
                "minimum_event_count",
                "checksum",
                "registered_at",
            ],
            "hold_conditions": {
                "calendar_days": 14,
                "complete_UTC_day_coverage": True,
                "symbol_diversity": 25,
                "liquidation_event_count": 500,
                "integrity_status": "PASS",
                "Founder_authorization": True,
            },
            "event_study_readiness_status": "NOT_READY",
            "event_study_real_execution": False,
            "created_at": _utc(),
        }


def run_framework_self_test() -> dict[str, Any]:
    eng = EventStudyEngineFrameworkV1()
    events = [
        SyntheticEvent("e1", "BTCUSDT", 1000, 1005, "AGGRESSIVE_TRADE_FLOW", {"side": "Buy"}, "p1", "c1"),
        SyntheticEvent("e2", "BTCUSDT", 1010, 1012, "AGGRESSIVE_TRADE_FLOW", {"side": "Buy"}, "p1", "c1"),
        SyntheticEvent("e3", "ETHUSDT", 1020, 1025, "LIQUIDATION_EVENTS", {"side": "Sell"}, "p2", "c2"),
    ]
    loaded = eng.load_point_in_time(events, as_of_ms=1020)
    clusters = eng.cluster_events(loaded, window_ms=20)
    labels = eng.forward_labels(entry_price=100.0, path=[99.0, 98.5, 101.0], horizons=[1, 3])
    folds = eng.chronological_folds(10, folds=5)
    boot = eng.block_bootstrap_indices(10, block=2, samples=3, seed=1)
    fdr = eng.fdr_bh([0.001, 0.02, 0.5], q=0.05)
    cost = eng.cost_bridge(0.01, fee_bps=5.5, slip_bps=2.0)
    lin = eng.lineage(events)
    pre = eng.preregistration_schema()
    ok = (
        len(loaded) == 2
        and len(clusters) >= 1
        and "MFE" in labels["3"]
        and len(folds) == 5
        and len(boot) == 3
        and isinstance(fdr, list)
        and cost["net"] < cost["gross"]
        and lin["source_partition_count"] == 2
        and pre["event_study_readiness_status"] == "NOT_READY"
        and eng.event_study_real_execution is False
    )
    return {
        "schema": "microstructure_event_study_framework_v1",
        "event_study_framework_status": "PASS" if ok else "FAIL",
        "event_study_real_execution": False,
        "event_study_readiness_status": "NOT_READY",
        "new_strategy_generated_count": 0,
        "profitability_claim_count": 0,
        "self_test": {
            "loaded": len(loaded),
            "clusters": len(clusters),
            "labels": labels,
            "folds": len(folds),
            "bootstrap_samples": len(boot),
            "fdr": fdr,
            "cost": cost,
            "lineage": lin,
        },
        "preregistration": pre,
        "created_at": _utc(),
    }
