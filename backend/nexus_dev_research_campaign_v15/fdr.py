"""Multiple-testing helpers for V15-C (Benjamini–Hochberg FDR)."""
from __future__ import annotations

from typing import Any


def benjamini_hochberg(p_values: list[float], *, q: float = 0.10) -> dict[str, Any]:
    n = len(p_values)
    if n == 0:
        return {
            "n_tests": 0,
            "q": q,
            "rejected_indices": [],
            "bh_adjusted_p": [],
            "discoveries": 0,
        }
    order = sorted(range(n), key=lambda i: p_values[i])
    adj = [0.0] * n
    prev = 1.0
    for rank_desc, idx in enumerate(reversed(order), start=1):
        # rank from largest p to smallest for cumulative min
        rank = n - rank_desc + 1
        raw = min(1.0, p_values[idx] * n / rank)
        prev = min(prev, raw)
        adj[idx] = prev
    # recompute standard BH monotonicity from smallest
    adj2 = [0.0] * n
    running = 1.0
    for rank, idx in enumerate(order, start=1):
        val = min(1.0, p_values[idx] * n / rank)
        adj2[idx] = val
    # enforce monotonicity from largest rank downward
    running = 1.0
    for idx in reversed(order):
        running = min(running, adj2[idx])
        adj2[idx] = running
    rejected = [i for i, a in enumerate(adj2) if a <= q]
    return {
        "n_tests": n,
        "q": q,
        "rejected_indices": rejected,
        "bh_adjusted_p": adj2,
        "discoveries": len(rejected),
    }


def two_sided_sign_pvalue(net_series: list[float]) -> float:
    """Simple binomial sign test p-value (development research only)."""
    signs = [1 for x in net_series if x > 0]
    neg = [1 for x in net_series if x < 0]
    n = len(signs) + len(neg)
    if n < 5:
        return 1.0
    k = min(len(signs), len(neg))
    # Exact binomial two-sided via cumulative (small n); normal approx otherwise.
    from math import erf, sqrt

    if n <= 40:
        # cumulative P(X<=k) under p=0.5, two-sided
        def binom_cdf(kk: int, nn: int) -> float:
            total = 0.0
            # compute via recursive ratio
            term = 2.0 ** (-nn)
            s = term
            for i in range(1, kk + 1):
                term *= (nn - i + 1) / i
                s += term
            # s is sum_{i=0..kk} C(n,i)/2^n but term start was for i=0
            # rebuild properly:
            return s

        # rebuild CDF correctly
        term = 1.0
        cdf = 0.0
        for i in range(0, k + 1):
            if i == 0:
                term = 1.0
            else:
                term *= (n - i + 1) / i
            cdf += term
        cdf /= 2.0**n
        p = min(1.0, 2.0 * cdf)
        return max(p, 1e-12)
    # normal approx
    phat = len(signs) / n
    z = abs(phat - 0.5) / (0.5 / sqrt(n))
    # two-sided from erf
    p = max(1e-12, 2.0 * (1.0 - 0.5 * (1.0 + erf(z / sqrt(2.0)))))
    return min(1.0, p)
