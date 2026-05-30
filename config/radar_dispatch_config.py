import os

RADAR_AUTO_TRADE_ENABLED = os.getenv("NEXUS_RADAR_AUTO_TRADE", "1").strip().lower() in {"1", "true", "yes", "on"}
RADAR_MIN_CANDIDATE_SCORE = float(os.getenv("NEXUS_RADAR_MIN_CANDIDATE_SCORE", "55"))
RADAR_MAX_OPEN_POSITIONS = int(float(os.getenv("NEXUS_RADAR_MAX_OPEN_POSITIONS", "3")))
RADAR_MARGIN_PCT_OF_BUDGET = float(os.getenv("NEXUS_RADAR_MARGIN_PCT_OF_BUDGET", "0.18"))
RADAR_MIN_MARGIN = float(os.getenv("NEXUS_RADAR_MIN_MARGIN", "20"))
RADAR_MAX_LEVERAGE = float(os.getenv("NEXUS_RADAR_MAX_LEVERAGE", "50"))
RADAR_COOLDOWN_SECONDS = int(float(os.getenv("NEXUS_RADAR_COOLDOWN_SECONDS", "120")))

# Re-export from single routing source of truth
from config.fleet_routing_config import CORE_FLEET_SYMBOLS, CORE_FLEETS  # noqa: F401
