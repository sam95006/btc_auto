"""V14-B Event Study Engine — block bootstrap confidence intervals."""
from __future__ import annotations

import math
from typing import Any, Callable, Sequence

from backend.nexus_event_study.constants import (
    DEFAULT_BOOTSTRAP_BLOCK,
    DEFAULT_BOOTSTRAP_REPLICATES,
    DEFAULT_BOOTSTRAP_SEED,
)
from backend.nexus_event_study.types import BootstrapCI


def _lcg(state: int) -> int:
    return (1103515245 * state + 12345) % (2**31)


def block_bootstrap_indices(
    n: int,
    *,
    block: int = DEFAULT_BOOTSTRAP_BLOCK,
    replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> list[list[int]]:
    if n <= 0:
        return [[] for _ in range(replicates)]
    block = max(1, min(block, n))
    state = seed
    out: list[list[int]] = []
    for _ in range(replicates):
        idxs: list[int] = []
        while len(idxs) < n:
            state = _lcg(state)
            start = state % max(1, n - block + 1)
            idxs.extend(range(start, min(n, start + block)))
        out.append(idxs[:n])
    return out


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


def bootstrap_mean_ci(
    values: Sequence[float],
    *,
    block: int = DEFAULT_BOOTSTRAP_BLOCK,
    replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> BootstrapCI:
    xs = [float(v) for v in values]
    if not xs:
        return BootstrapCI(
            statistic="mean",
            point=None,
            ci_low=None,
            ci_high=None,
            replicates=replicates,
            block=block,
            seed=seed,
        )
    point = sum(xs) / len(xs)
    samples = block_bootstrap_indices(len(xs), block=block, replicates=replicates, seed=seed)
    boots: list[float] = []
    for idxs in samples:
        boots.append(sum(xs[i] for i in idxs) / len(idxs))
    lo = _percentile(boots, 100.0 * (alpha / 2.0))
    hi = _percentile(boots, 100.0 * (1.0 - alpha / 2.0))
    return BootstrapCI(
        statistic="mean",
        point=point,
        ci_low=lo,
        ci_high=hi,
        replicates=replicates,
        block=block,
        seed=seed,
    )


def bootstrap_statistic_ci(
    values: Sequence[float],
    statistic: Callable[[Sequence[float]], float],
    *,
    name: str = "custom",
    block: int = DEFAULT_BOOTSTRAP_BLOCK,
    replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    alpha: float = 0.05,
) -> BootstrapCI:
    xs = [float(v) for v in values]
    if not xs:
        return BootstrapCI(name, None, None, None, replicates, block, seed)
    point = float(statistic(xs))
    samples = block_bootstrap_indices(len(xs), block=block, replicates=replicates, seed=seed)
    boots = [float(statistic([xs[i] for i in idxs])) for idxs in samples]
    return BootstrapCI(
        statistic=name,
        point=point,
        ci_low=_percentile(boots, 100.0 * (alpha / 2.0)),
        ci_high=_percentile(boots, 100.0 * (1.0 - alpha / 2.0)),
        replicates=replicates,
        block=block,
        seed=seed,
    )


def bootstrap_report(values: Sequence[float], **kwargs: Any) -> dict[str, Any]:
    ci = bootstrap_mean_ci(values, **kwargs)
    d = ci.to_dict()
    d["schema"] = "v14_b_bootstrap_ci"
    d["profitability_claimed"] = False
    d["inference_is_descriptive_only"] = True
    return d
