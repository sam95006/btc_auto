"""NEXUS-EXPERIENCE-1B.1 — Home data-truth guards (source-level).

There is no TS test runner in this repo, so these assert, at the source level, the
critical data-truth rule: the answer-first Home must NEVER describe missing
volatility/risk data as a calm market, must distinguish loading/error/unavailable/
stale, and the trial banner must never fabricate a countdown.
"""
from __future__ import annotations

from pathlib import Path

FE = Path("frontend") / "src" / "member_platform_v1"
HOME = FE / "pages" / "home" / "HomePage.tsx"
TRIAL = FE / "components" / "TrialBanner.tsx"


def _read(p: Path) -> str:
    assert p.exists(), f"missing {p}"
    return p.read_text(encoding="utf-8")


def test_home_gates_calm_on_real_data_availability():
    src = _read(HOME)
    # A calm / no-attention conclusion (t("no_attention")) must be gated by a real
    # data-availability check, and there must be an explicit insufficient-data path.
    assert "attentionDataAvailable" in src
    assert 't("attn_insufficient")' in src
    # The calm message must be rendered only in the branch guarded by
    # attentionDataAvailable, immediately before the insufficient-data fallback.
    calm = src.index('t("no_attention")')
    insufficient = src.index('t("attn_insufficient")')
    guard = src.index("attentionDataAvailable ? (")
    assert guard < calm < insufficient, "calm must sit inside the attentionDataAvailable branch"


def test_home_distinguishes_every_data_state():
    src = _read(HOME)
    # LOADING / ERROR / UNAVAILABLE / STALE / AVAILABLE must be distinct — a network
    # error must not collapse into a market-unavailable conclusion.
    for token in ('"loading"', '"error"', '"unavailable"', '"stale"', '"available"'):
        assert token in src, token
    assert 't("error")' in src           # error surfaced honestly
    assert 'dataStatus === "stale"' in src


def test_trial_banner_never_fabricates():
    src = _read(TRIAL)
    assert "getPersonalSubscription" in src           # backend-driven
    assert '"UNAVAILABLE"' in src                       # honest unavailable path
    assert 'trial.trial_active === true' in src         # only a real active trial shows a countdown
    # No hard-coded day counts / fake countdowns.
    assert "days_remaining" in src                      # uses the real backend value
    for fake in ("30 days left", "剩餘 30", "days remaining"):
        assert fake not in src, fake
