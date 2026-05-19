import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return False

from flask import Flask, send_file
from backend.api.server import register_nexus_routes
from backend.core.env_loader import load_env_file
from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard
from backend.security.secret_manager import initialize_security_foundation
from backend.trading.trading_mode import TradingModeSafetyError, get_trading_mode, require_testnet_credentials

load_dotenv()
load_env_file()
initialize_security_foundation(strict=False)
try:
    trading_mode = get_trading_mode()
    if trading_mode == "binance_testnet":
        missing = require_testnet_credentials()
        if missing:
            print(f"[startup] Binance testnet mode enabled but missing credentials for: {', '.join(missing)}")
except TradingModeSafetyError as exc:
    raise SystemExit(str(exc))

app = Flask(__name__)
register_nexus_routes(app)
_single_instance = None

@app.route("/")
def dashboard():
    return send_file(Path(app.root_path) / "templates" / "nexus_command.html")

if __name__ == "__main__":
    try:
        _single_instance = SingleInstanceGuard("nexus_web").acquire()
    except SingleInstanceError as exc:
        raise SystemExit(str(exc))
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
