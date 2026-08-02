import os

from config.growth_mode_config import BOLD_TESTNET_ENABLED


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


# Testnet paper-trading: bypass learning cooldown / weak-history blocks (NOT for mainnet).
TESTNET_SANDBOX_ENABLED = _env_bool("NEXUS_TESTNET_SANDBOX", BOLD_TESTNET_ENABLED)
SANDBOX_MIN_CONFIDENCE = float(os.getenv("NEXUS_SANDBOX_MIN_CONFIDENCE", "0.38") or 0.38)
SANDBOX_MIN_APPROVAL_SCORE = float(os.getenv("NEXUS_SANDBOX_MIN_APPROVAL_SCORE", "0.38") or 0.38)
SANDBOX_SKIP_SYMBOL_COOLDOWN = _env_bool("NEXUS_SANDBOX_SKIP_SYMBOL_COOLDOWN", True)
SANDBOX_SKIP_BACKTEST_HISTORY_BLOCKS = _env_bool("NEXUS_SANDBOX_SKIP_BACKTEST_BLOCKS", True)
# Liquidation cooldowns remain enforced even in sandbox unless explicitly opted out.
SANDBOX_SKIP_LIQUIDATION_COOLDOWN = _env_bool("NEXUS_SANDBOX_SKIP_LIQUIDATION_COOLDOWN", False)
SANDBOX_RELAX_GROWTH_BLOCKS = _env_bool("NEXUS_SANDBOX_RELAX_GROWTH", True)
SANDBOX_AUTO_RESET_ON_STARTUP = _env_bool("NEXUS_SANDBOX_AUTO_RESET", True)
SANDBOX_FORCE_LIVE_EXECUTE = _env_bool("NEXUS_SANDBOX_FORCE_LIVE", True)
