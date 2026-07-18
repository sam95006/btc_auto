"""Market Intelligence observability + outcome APIs (Phase 4 Track B).

Read-only · no secrets · no trading coupling.
"""
from __future__ import annotations

from flask import Flask, Response, jsonify, request


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def register_market_intelligence_routes(app: Flask) -> None:
    @app.route("/api/market/intelligence/status")
    def market_intelligence_status():
        from backend.market.intelligence.history_store import get_history_store
        from backend.market.intelligence.outcome_store import get_outcome_store
        from backend.market.intelligence.transition_store import get_transition_store
        from backend.market.scanner.scanner_service import get_market_scanner

        scanner = get_market_scanner()
        st = scanner.status()
        hist = get_history_store().status()
        trans = get_transition_store().status()
        outcomes = get_outcome_store().status()
        sector_last = None
        try:
            from backend.market.sectors.sector_service import get_sector_service

            sec = get_sector_service().status()
            sector_last = {
                "generatedAt": sec.get("generatedAt") or sec.get("lastSnapshotAt"),
                "sectorCount": sec.get("sectorCount"),
                "freshness": sec.get("freshness"),
            }
        except Exception:  # noqa: BLE001
            sector_last = None
        body = {
            "ok": True,
            "read_only": True,
            "researchOnly": True,
            "private_api": False,
            "api_key_used": False,
            "secretsExposed": False,
            "transport": st.get("transport"),
            "breadth": st.get("breadth"),
            "deepSymbolCount": st.get("symbolCount"),
            "wsConnected": st.get("wsConnected"),
            "wsReconnectCount": st.get("wsReconnectCount"),
            "wsSubscribedTopics": st.get("wsSubscribedTopics"),
            "lastMarketUpdateAt": st.get("lastMarketUpdateAt"),
            "lastCandidateRecomputeAt": st.get("lastCandidateRecomputeAt"),
            "candidateCount": (st.get("longCandidates") or 0) + (st.get("shortCandidates") or 0),
            "confirmedCandidates": st.get("confirmedCandidates"),
            "transitionCount": trans.get("count"),
            "outcomePending": outcomes.get("pendingWindows"),
            "outcomeComplete": outcomes.get("completeWindows"),
            "outcomeMissed": outcomes.get("missedWindows"),
            "outcomeStale": outcomes.get("staleWindows"),
            "outcomeTracked": outcomes.get("tracked"),
            "historyMode": hist.get("mode"),
            "historySpanMs": hist.get("historySpanMs"),
            "persistenceHealth": {
                "mode": hist.get("mode"),
                "persistWrites": hist.get("persistWrites"),
                "persistErrors": hist.get("persistErrors"),
                "lastError": hist.get("lastError"),
            },
            "sectorLastSnapshot": sector_last,
            "errorCount": 1 if st.get("lastError") else 0,
            "lastError": st.get("lastError"),
            "wsOutOfOrderBlocked": st.get("wsOutOfOrderBlocked"),
            "wsDuplicateSuppressed": st.get("wsDuplicateSuppressed"),
            "candidateRecomputeEveryTick": False,
            "cache": "no-store",
            "generatedAt": st.get("generatedAt"),
        }
        return _no_store(jsonify(body))

    @app.route("/api/market/intelligence/outcomes")
    def market_intelligence_outcomes():
        from backend.market.intelligence.outcome_store import get_outcome_store

        status = (request.args.get("status") or "").strip() or None
        try:
            limit = int(request.args.get("limit") or 50)
        except ValueError:
            limit = 50
        return _no_store(jsonify(get_outcome_store().list(status=status, limit=limit)))

    @app.route("/api/market/intelligence/outcomes/status")
    def market_intelligence_outcomes_status():
        from backend.market.intelligence.outcome_store import get_outcome_store

        return _no_store(jsonify(get_outcome_store().status()))

    @app.route("/api/market/intelligence/transitions")
    def market_intelligence_transitions():
        from backend.market.intelligence.transition_store import get_transition_store

        try:
            limit = int(request.args.get("limit") or 50)
        except ValueError:
            limit = 50
        rows = get_transition_store().list_recent(limit=limit)
        return _no_store(
            jsonify(
                {
                    "ok": True,
                    "count": len(rows),
                    "transitions": rows,
                    "researchOnly": True,
                    "cache": "no-store",
                }
            )
        )
