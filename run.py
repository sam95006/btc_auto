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


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _running_under_gunicorn() -> bool:
    return "gunicorn" in (os.environ.get("SERVER_SOFTWARE", "") or "").lower()


def _looks_like_zeabur_runtime() -> bool:
    """Zeabur injects IDs; users often omit a literal ZEABUR=1 variable."""
    if _truthy_env("ZEABUR"):
        return True
    if (os.getenv("ZEABUR_ENVIRONMENT") or "").strip():
        return True
    return any(
        bool(os.getenv(k))
        for k in (
            "ZEABUR_SERVICE_ID",
            "ZEABUR_PROJECT_ID",
            "ZEABUR_ENVIRONMENT_ID",
        )
    )


def _should_start_embedded_nexus_worker() -> bool:
    """Start trading loop inside web when Zeabur runs a single service (no separate worker)."""
    if _truthy_env("NEXUS_WEB_ONLY"):
        return False
    if _truthy_env("NEXUS_EMBEDDED_WORKER"):
        return True
    if _looks_like_zeabur_runtime():
        # Gunicorn with multiple workers would fork duplicate runtimes; require explicit opt-in.
        if _running_under_gunicorn() and not _truthy_env("NEXUS_EMBEDDED_WORKER"):
            return False
        return True
    return False


def _start_embedded_nexus_worker_if_configured():
    from backend.runtime.embed_flags import set_embedded_worker_status

    if not _should_start_embedded_nexus_worker():
        set_embedded_worker_status(False, None)
        return
    try:
        from backend.services.nexus_runtime import nexus_runtime

        nexus_runtime.start()
        set_embedded_worker_status(True, None)
        print("[startup] NEXUS embedded worker thread started (Binance sync + snapshot updates)")
    except Exception as exc:
        set_embedded_worker_status(False, str(exc))
        print(f"[startup] NEXUS embedded worker failed to start: {exc}")


_start_embedded_nexus_worker_if_configured()


@app.route("/")
def dashboard():
    return send_file(Path(app.root_path) / "templates" / "nexus_command.html")


@app.route("/health")
def health():
    from backend.runtime.embed_flags import embedded_worker_error, embedded_worker_started

    return jsonify(
        {
            "status": "ok",
            "service": "nexus-web",
            "embedded_worker": embedded_worker_started,
            "embedded_worker_error": embedded_worker_error,
        }
    )


@app.route("/", methods=["POST"])
def root_post_noop():
    """Avoid confusing 405 when probes POST the root URL."""
    return (
        jsonify({"ok": False, "error": "POST not supported on /", "hint": "Use /api/nexus/* endpoints."}),
        404,
    )

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
