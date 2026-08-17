"""Minimal, disarmed health endpoint for the Bybit Demo validation container."""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SERVICE_NAME = "nexus-bybit-demo-learning-validation"


def _false(name: str) -> bool:
    """Report unsafe/missing values as false; entrypoint enforces these values."""
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


class ValidationHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - standard-library handler contract
        if self.path != "/health":
            self.send_error(404)
            return
        payload = {
            "ok": True,
            "service": SERVICE_NAME,
            "mode": "BYBIT_DEMO_VALIDATION",
            "mainnet": _false("MAINNET"),
            "real_money": _false("REAL_MONEY"),
            "demo_autonomous_enabled": _false("DEMO_AUTONOMOUS_ENABLED"),
            "exchange_write": _false("EXCHANGE_WRITE"),
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format: str, *_args: object) -> None:
        """Avoid request logs that could accidentally contain query strings."""


def main() -> None:
    port_raw = (os.environ.get("PORT") or "8080").strip()
    port = int(port_raw) if port_raw.isdigit() else 8080
    server = ThreadingHTTPServer(("0.0.0.0", port), ValidationHealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
