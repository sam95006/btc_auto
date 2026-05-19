import os


def _csv_env(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = str(os.getenv(name, "") or "").strip()
    if not raw:
        return default
    values = tuple(item.strip().upper() for item in raw.split(",") if item.strip())
    return values or default


HQ_SPOT_TRUTH_MODE = str(os.getenv("NEXUS_HQ_SPOT_TRUTH_MODE", "stable_only") or "stable_only").strip().lower()

# HQ Spot truth should default to a clean treasury view.
# This prevents noisy Spot testnet faucet assets from polluting the active
# runtime capital view consumed by risk/AI.
HQ_SPOT_TRUTH_STABLE_ASSETS = _csv_env("NEXUS_HQ_SPOT_TRUTH_STABLE_ASSETS", ("USDT", "USDC"))

# Keep a visible inventory scope for HQ reference, but in stable_only mode
# these holdings are not added into the Spot total shown as treasury truth.
HQ_SPOT_VISIBLE_HOLDINGS = _csv_env("NEXUS_HQ_SPOT_VISIBLE_HOLDINGS", ("BTC", "ETH", "SOL", "BNB"))

# Optional HQ treasury scope to avoid mixing unrelated spot-testnet balances into
# the HQ treasury view. This does not fabricate balances; it only limits which
# assets are considered part of the HQ spot truth scope.
HQ_SPOT_ALLOWED_ASSETS = _csv_env(
    "NEXUS_HQ_SPOT_ALLOWED_ASSETS",
    HQ_SPOT_TRUTH_STABLE_ASSETS + HQ_SPOT_VISIBLE_HOLDINGS,
)

# AI truth layer guard controls.
MAX_DEGRADED_CONTEXTS_FOR_FUTURES_AI = 2
REQUIRE_SPOT_STREAM_FOR_AI = False
REQUIRE_FUTURES_STREAM_FOR_AI = False
