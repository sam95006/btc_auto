import os
import signal
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return False

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core.env_loader import load_env_file
from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard
from backend.security.secret_manager import initialize_security_foundation
from backend.services.nexus_runtime import nexus_runtime
from backend.trading.trading_mode import TradingModeSafetyError, get_trading_mode, require_testnet_credentials

load_dotenv()
load_env_file()
initialize_security_foundation(strict=False)
try:
    trading_mode = get_trading_mode()
    if trading_mode == "binance_testnet":
        missing = require_testnet_credentials()
        if missing:
            print(f"[worker] Binance testnet mode enabled but missing credentials for: {', '.join(missing)}")
except TradingModeSafetyError as exc:
    raise SystemExit(str(exc))


_running = True
_single_instance = None


def _stop(*_args):
    global _running
    _running = False


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    nexus_runtime.start()
    while _running:
        time.sleep(1)


def _cloud_runtime():
    return bool(
        os.getenv("ZEABUR")
        or os.getenv("ZEABUR_ENVIRONMENT")
        or os.getenv("KUBERNETES_SERVICE_HOST")
    )


if __name__ == "__main__":
    if not _cloud_runtime():
        try:
            _single_instance = SingleInstanceGuard("nexus_worker").acquire()
        except SingleInstanceError as exc:
            raise SystemExit(str(exc))
    main()

