import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return False

from flask import Flask, jsonify, request, send_file, send_from_directory
from backend.api.operator_ui_routes import (
    OPERATOR_BUILD_MARKER,
    operator_ui_ready,
    register_operator_ui_routes,
)
from backend.api.market_public_routes import register_market_public_routes
from backend.api.market_scanner_routes import register_market_scanner_routes
from backend.api.market_sector_routes import register_market_sector_routes
from backend.api.market_chart_routes import register_market_chart_routes
from backend.api.market_intelligence_routes import register_market_intelligence_routes
from backend.api.server import register_nexus_routes
from backend.nexus_research.api_routes import register_nexus_research_routes
from backend.nexus_public_decision_cloud.routes import register_public_decision_cloud_routes
from backend.nexus_public_decision_product.routes import register_public_decision_product_routes
from backend.nexus_public_member_intel.routes import register_public_member_intel_routes
from backend.nexus_pub17_market_pulse.routes import register_pub17_market_pulse_routes
from backend.nexus_pub18_live_funnel.routes import register_pub18_live_funnel_routes
from backend.nexus_runtime_snapshot_v18_1.routes import register_runtime_snapshot_routes
from backend.nexus_customer_validation_concierge.routes import (
    register_customer_validation_concierge_routes,
)
from backend.core.env_loader import load_env_file
from backend.runtime.single_instance_guard import SingleInstanceError, SingleInstanceGuard
from backend.security.secret_manager import initialize_security_foundation
from backend.services.console_assets import verify_console_assets
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
register_market_public_routes(app)
register_market_scanner_routes(app)
register_market_sector_routes(app)
register_market_chart_routes(app)
register_market_intelligence_routes(app)
register_public_decision_cloud_routes(app)  # PUB-B: local/staging Decision Cloud (read-only)
register_public_decision_product_routes(app)  # PUB2-A: customer-safe Decision Product E2E (read-only)
register_public_member_intel_routes(app)  # UX-B: Member Web Intelligence Experience (read-only)
register_pub17_market_pulse_routes(app)  # PUB17-B: Market Pulse + Top Opportunities (read-only)
register_pub18_live_funnel_routes(app)  # PUB18-A: Live Funnel + Market Pulse (read-only)
register_runtime_snapshot_routes(app)  # V18.1 Phase B: Runtime Snapshot live binding (read-only)
register_customer_validation_concierge_routes(app)  # PUB2-G: Concierge validation local/staging app
register_nexus_research_routes(app)  # Phase 5 Gate B: AI Review research routes
try:
    from backend.nexus_research.sim_routes import register_gate_c_routes

    register_gate_c_routes(app)  # Phase 5 Gate C: simulator / risk / reflection / replay
except Exception as _gate_c_exc:  # noqa: BLE001
    print(f"[startup] Gate C routes deferred: {_gate_c_exc}")
try:
    from backend.nexus_research.paper_routes import register_paper_routes

    register_paper_routes(app)  # Phase 6 Gate C: paper runtime API
except Exception as _paper_routes_exc:  # noqa: BLE001
    print(f"[startup] Paper routes deferred: {_paper_routes_exc}")
try:
    from backend.api.nexus_market_data_routes import register_nexus_market_data_routes

    register_nexus_market_data_routes(app)  # Phase 6.4: candles / features / intelligence
except Exception as _market_data_exc:  # noqa: BLE001
    print(f"[startup] Nexus market data routes deferred: {_market_data_exc}")
try:
    from backend.api.founder_private_routes import register_founder_private_routes

    register_founder_private_routes(app)  # Phase 6.5: founder private boundary
except Exception as _founder_exc:  # noqa: BLE001
    print(f"[startup] Founder private routes deferred: {_founder_exc}")
# UI-DEPLOY-2: Market Intelligence SPA (static/operator_ui) — register before / catch-alls finish
register_operator_ui_routes(app)

# Product Transformation Phase 1: eager read-only scanner bootstrap (public market data only).
try:
    from backend.market.scanner.scanner_service import get_market_scanner

    get_market_scanner()
    print("[startup] Market scanner started (read-only · BYBIT_MAINNET_LINEAR)")
except Exception as exc:  # noqa: BLE001
    print(f"[startup] Market scanner bootstrap deferred: {exc}")

_asset_check = verify_console_assets(app.root_path)
if _asset_check.get("ok"):
    print(f"[startup] Console artwork OK ({_asset_check.get('present_count')} files)")
else:
    print(f"[startup] WARNING missing console artwork: {_asset_check.get('missing')}")
if operator_ui_ready(app):
    print(f"[startup] Operator UI ready ({OPERATOR_BUILD_MARKER})")
else:
    print("[startup] Operator UI missing — / falls back to legacy nexus_command")


@app.after_request
def _nexus_static_cache_control(response):
    """Avoid stale ES module bundles after deploy (Zeabur CDN/browser 304)."""
    if request.path.startswith("/static/nexus/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    if request.path.startswith("/assets/") or request.path in {"/", "/overview"}:
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    if request.path.startswith("/api/market/") or request.path.startswith("/api/nexus/markets/") \
            or request.path.startswith("/api/nexus/market-intelligence/") \
            or request.path.startswith("/api/nexus/data-providers/") \
            or request.path.startswith("/api/nexus/features/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response
_single_instance = None


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _running_under_gunicorn() -> bool:
    return "gunicorn" in (os.environ.get("SERVER_SOFTWARE", "") or "").lower()


def _gunicorn_worker_count() -> int:
    for key in ("WEB_CONCURRENCY", "GUNICORN_WORKERS"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                pass
    return 1


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

try:
    from backend.nexus_research.bootstrap import bootstrap_research_runtime
    import threading

    def _deferred_research_bootstrap() -> None:
        try:
            # Let HTTP/health bind first; avoid startup contention with scanner bootstrap.
            import time as _time

            _time.sleep(8.0)
            _bootstrap_result = bootstrap_research_runtime()
            print(f"[startup] Research runtime bootstrap: {_bootstrap_result.get('steps', [])}")
        except Exception as _bootstrap_exc:  # noqa: BLE001
            print(f"[startup] Research runtime bootstrap deferred: {_bootstrap_exc}")

    threading.Thread(
        target=_deferred_research_bootstrap,
        name="nexus-research-bootstrap",
        daemon=True,
    ).start()
    print("[startup] Research runtime bootstrap scheduled (deferred)")
except Exception as _bootstrap_exc:  # noqa: BLE001
    print(f"[startup] Research runtime bootstrap wiring deferred: {_bootstrap_exc}")


@app.route("/")
def dashboard():
    # UI-DEPLOY-2: prefer Market Intelligence SPA when present
    ui_dir = Path(app.root_path) / "static" / "operator_ui"
    if (ui_dir / "index.html").is_file():
        return send_from_directory(ui_dir, "index.html")
    return send_file(Path(app.root_path) / "templates" / "nexus_command.html")


@app.route("/health")
def health():
    from backend.runtime.embed_flags import embedded_worker_error, embedded_worker_started
    from config.pure_ai_trading_config import pure_ai_active

    assets = verify_console_assets(app.root_path)
    ready = operator_ui_ready(app)
    return jsonify(
        {
            "status": "ok" if assets.get("ok") else "degraded",
            "service": "nexus-web",
            "embedded_worker": embedded_worker_started,
            "embedded_worker_error": embedded_worker_error,
            "pure_ai_enabled": pure_ai_active(),
            "console_assets": assets,
            "operator_ui_ready": ready,
            "build_marker": OPERATOR_BUILD_MARKER,
            "root_serves": "operator_ui" if ready else "legacy_nexus",
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
