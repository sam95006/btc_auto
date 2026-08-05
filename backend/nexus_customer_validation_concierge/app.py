"""Standalone local/staging Concierge app factory."""
from __future__ import annotations

from pathlib import Path

from flask import Flask

from backend.nexus_customer_validation_concierge.routes import (
    register_customer_validation_concierge_routes,
)


def create_app(workspace: Path | str | None = None) -> Flask:
    app = Flask("nexus_customer_validation_concierge")
    register_customer_validation_concierge_routes(app, workspace=workspace)
    return app


def main() -> None:
    import os

    os.environ.setdefault("NEXUS_CONCIERGE_ENV", "local_staging")
    app = create_app()
    port = int(os.environ.get("NEXUS_CONCIERGE_PORT", "8765"))
    # Local only — never bind as a live public deployment claim.
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
