import os

REGIME_LABELS = ("CHOP_RNG", "TREND_BULL", "HIGH_RISK_MACRO")
REGIME_REFRESH_SECONDS = int(os.getenv("NEXUS_REGIME_REFRESH_SECONDS", "1800"))
REGIME_LLM_ENABLED = str(os.getenv("NEXUS_REGIME_LLM_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
