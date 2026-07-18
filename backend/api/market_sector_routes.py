"""Sector read-only APIs (Phase 3)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.market.sectors.sector_service import get_sector_service


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp


def register_market_sector_routes(app: Flask) -> None:
    @app.route("/api/market/sectors/status")
    def market_sectors_status():
        return _no_store(jsonify(get_sector_service().status()))

    @app.route("/api/market/sectors")
    def market_sectors_list():
        sort = (request.args.get("sort") or "performance").strip()
        state = (request.args.get("state") or "").strip() or None
        return _no_store(jsonify(get_sector_service().list_sectors(sort=sort, state=state)))

    @app.route("/api/market/sectors/rankings")
    def market_sectors_rankings():
        sort = (request.args.get("sort") or "performance").strip()
        return _no_store(jsonify(get_sector_service().rankings(sort=sort)))

    @app.route("/api/market/sectors/<sector_id>")
    def market_sector_detail(sector_id: str):
        body = get_sector_service().sector_detail(sector_id)
        code = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), code

    @app.route("/api/market/sectors/<sector_id>/symbols")
    def market_sector_symbols(sector_id: str):
        try:
            limit = int(request.args.get("limit") or 80)
        except ValueError:
            limit = 80
        body = get_sector_service().sector_symbols(sector_id, limit=limit)
        code = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), code

    @app.route("/api/market/sectors/<sector_id>/candidates")
    def market_sector_candidates(sector_id: str):
        body = get_sector_service().sector_candidates(sector_id)
        code = 200 if body.get("ok") else 404
        return _no_store(jsonify(body)), code

    @app.route("/api/market/sectors/<sector_id>/events")
    def market_sector_events(sector_id: str):
        # Bounded: filter scanner events by sector membership (best-effort)
        from backend.market.scanner.scanner_service import get_market_scanner
        from backend.market.sectors import taxonomy as tax

        meta = tax.get_sector(sector_id)
        if not meta:
            return _no_store(jsonify({"ok": False, "error": "sector_not_found"})), 404
        members = set(tax.symbols_for_sector(meta["id"]))
        bases = {s.replace("USDT", "") for s in members}
        ev = get_market_scanner().events(limit=40)
        filtered = []
        for e in ev.get("events") or []:
            sym = str(e.get("symbol") or "")
            base = sym.replace("USDT", "").replace("1000", "")
            if sym in members or base in bases:
                filtered.append(e)
        return _no_store(
            jsonify(
                {
                    "ok": True,
                    "count": len(filtered),
                    "events": filtered[:30],
                    "cache": "no-store",
                    "researchOnly": True,
                }
            )
        )
