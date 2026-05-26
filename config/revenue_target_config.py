import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return float(default)


# third_of_futures_capital | fixed | third_of_legacy_10k
MONTHLY_REVENUE_TARGET_MODE = str(
    os.getenv("NEXUS_MONTHLY_REVENUE_TARGET_MODE", "third_of_futures_capital") or "third_of_futures_capital"
).strip().lower()
MONTHLY_REVENUE_TARGET_USD = _env_float("NEXUS_MONTHLY_REVENUE_TARGET_USD", 3333.0)
MONTHLY_REVENUE_CAPITAL_FRACTION = _env_float("NEXUS_MONTHLY_REVENUE_CAPITAL_FRACTION", 1.0 / 3.0)
REVENUE_GROWTH_MODE = _env_bool("NEXUS_REVENUE_GROWTH_MODE", True)
FUTURES_ONLY_TRADING = _env_bool("NEXUS_FUTURES_ONLY_TRADING", True)
FUTURES_DEPLOY_FRACTION = _env_float("NEXUS_FUTURES_DEPLOY_FRACTION", 0.92)
# Looser gates while building the first live samples (monthly revenue track).
EXPLORATION_MIN_QUALITY = _env_float("NEXUS_EXPLORATION_MIN_QUALITY", 0.50)
EXPLORATION_MIN_APPROVAL_SCORE = _env_float("NEXUS_EXPLORATION_MIN_APPROVAL_SCORE", 0.44)
EXPLORATION_AI_PROPOSALS_PER_TICK = int(_env_float("NEXUS_EXPLORATION_AI_PROPOSALS_PER_TICK", 8))
