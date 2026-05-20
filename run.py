import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return False

from flask import Flask, jsonify, send_file
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


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "nexus-web"})

def _cloud_runtime():
    return bool(
        os.getenv("ZEABUR")
        or os.getenv("ZEABUR_ENVIRONMENT")
        or os.getenv("PORT")
    )


if __name__ == "__main__":
    if not _cloud_runtime():
        try:
            _single_instance = SingleInstanceGuard("nexus_web").acquire()
        except SingleInstanceError as exc:
            raise SystemExit(str(exc))
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)
