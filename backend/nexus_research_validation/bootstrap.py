"""Bootstrap and block-bootstrap stability measures (development / synthetic only)."""
from __future__ import annotations

import math
import random
from typing import Any, Sequence

from backend.nexus_research_validation.constants import (
    BLOCK_BOOTSTRAP_BLOCK_SIZE,
    BOOTSTRAP_CI_LEVEL,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_STABILITY_CI_FLOOR,
)


def _mean(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _percentile(sorted_xs: Sequence[float], pct: float) -> float:
    if not sorted_xs:
        return 0.0
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    k = (len(sorted_xs) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_xs[int(k)]
    return sorted_xs[f] * (c - k) + sorted_xs[c] * (k - f)


def iid_bootstrap_means(
    series: Sequence[float],
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = 0,
) -> list[float]:
    rng = random.Random(seed)
    n = len(series)
    if n == 0:
        return [0.0] * replicates
    out: list[float] = []
    for _ in range(replicates):
        sample = [series[rng.randrange(n)] for _ in range(n)]
        out.append(_mean(sample))
    return out


def block_bootstrap_means(
    series: Sequence[float],
    *,
    block_size: int = BLOCK_BOOTSTRAP_BLOCK_SIZE,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = 0,
) -> list[float]:
    """Moving block bootstrap preserving short-range dependence."""
    rng = random.Random(seed)
    n = len(series)
    if n == 0:
        return [0.0] * replicates
    bs = max(1, min(block_size, n))
    starts = list(range(0, n - bs + 1)) or [0]
    out: list[float] = []
    for _ in range(replicates):
        sample: list[float] = []
        while len(sample) < n:
            st = starts[rng.randrange(len(starts))]
            sample.extend(series[st : st + bs])
        sample = sample[:n]
        out.append(_mean(sample))
    return out


def bootstrap_stability_report(
    series: Sequence[float],
    *,
    seed: int = 0,
    replicates: int = BOOTSTRAP_REPLICATES,
    block_size: int = BLOCK_BOOTSTRAP_BLOCK_SIZE,
    ci_level: float = BOOTSTRAP_CI_LEVEL,
) -> dict[str, Any]:
    """CI and sign-stability for net-return series. Not a qualification claim."""
    observed = _mean(series)
    iid = iid_bootstrap_means(series, replicates=replicates, seed=seed)
    block = block_bootstrap_means(
        series, block_size=block_size, replicates=replicates, seed=seed + 17
    )
    alpha = 1.0 - ci_level
    lo_q, hi_q = alpha / 2.0, 1.0 - alpha / 2.0

    def _ci(vals: list[float]) -> dict[str, float]:
        s = sorted(vals)
        return {
            "lo": _percentile(s, lo_q),
            "hi": _percentile(s, hi_q),
            "mean": _mean(vals),
        }

    iid_ci = _ci(iid)
    block_ci = _ci(block)
    iid_sign_agree = sum(1 for v in iid if (v > 0) == (observed > 0)) / max(1, len(iid))
    block_sign_agree = sum(1 for v in block if (v > 0) == (observed > 0)) / max(
        1, len(block)
    )

    stable = (
        observed > BOOTSTRAP_STABILITY_CI_FLOOR
        and iid_ci["lo"] > BOOTSTRAP_STABILITY_CI_FLOOR
        and block_ci["lo"] > BOOTSTRAP_STABILITY_CI_FLOOR
        and iid_sign_agree >= 0.80
        and block_sign_agree >= 0.75
    )

    return {
        "observed_mean": observed,
        "n_observations": len(series),
        "replicates": replicates,
        "block_size": block_size,
        "ci_level": ci_level,
        "iid_bootstrap": {**iid_ci, "sign_agreement": iid_sign_agree},
        "block_bootstrap": {**block_ci, "sign_agreement": block_sign_agree},
        "bootstrap_stable": stable,
        "development_only": True,
        "formal_walk_forward": False,
        "not_oos_claim": True,
    }
