from config.truth_layer_config import (
    MAX_DEGRADED_CONTEXTS_FOR_FUTURES_AI,
    REQUIRE_FUTURES_STREAM_FOR_AI,
    REQUIRE_SPOT_STREAM_FOR_AI,
)


class TruthLayerGuard:
    def evaluate(self, truth_layer_status, account_sync_status, fleet_symbols=None, spot_symbols=None):
        truth_layer_status = truth_layer_status or {}
        account_sync_status = account_sync_status or {}
        price_freshness = truth_layer_status.get("price_freshness", {}) or {}
        stale_reasons = list(truth_layer_status.get("stale_reasons", []) or [])
        spot_rest = ((account_sync_status.get("rest_snapshot_status") or {}).get("spot") or "idle").lower()
        futures_rest = ((account_sync_status.get("rest_snapshot_status") or {}).get("futures") or "idle").lower()
        spot_stream = ((account_sync_status.get("spot_stream_health") or {}).get("status") or "unknown").lower()
        futures_stream = ((account_sync_status.get("websocket_status") or {}).get("futures") or "unknown").lower()
        fleet_symbols = list(fleet_symbols or [])
        spot_symbols = list(spot_symbols or [])

        def _symbol_price_ok(symbols):
            if not symbols:
                return True
            for symbol in symbols:
                symbol_status = (price_freshness.get(symbol, {}) or {}).get("status")
                if symbol_status == "stale":
                    return False
            return True

        spot_ready = (
            truth_layer_status.get("spot_account_freshness", {}).get("status") != "stale"
            and _symbol_price_ok(spot_symbols)
            and spot_rest == "ok"
        )
        futures_ready = (
            truth_layer_status.get("futures_account_freshness", {}).get("status") != "stale"
            and _symbol_price_ok(fleet_symbols)
            and futures_rest == "ok"
        )

        degraded_contexts = list(truth_layer_status.get("degraded_market_contexts", []) or [])
        if len(degraded_contexts) > MAX_DEGRADED_CONTEXTS_FOR_FUTURES_AI:
            futures_ready = False
            stale_reasons.append("too_many_degraded_market_contexts")

        if REQUIRE_SPOT_STREAM_FOR_AI and spot_stream not in {"connected", "healthy"}:
            spot_ready = False
            stale_reasons.append("spot_stream_not_ready")
        if REQUIRE_FUTURES_STREAM_FOR_AI and futures_stream not in {"connected", "healthy"}:
            futures_ready = False
            stale_reasons.append("futures_stream_not_ready")

        overall_ready = bool(spot_ready or futures_ready)
        return {
            "fresh_for_ai": overall_ready,
            "spot_ready_for_ai": bool(spot_ready),
            "futures_ready_for_ai": bool(futures_ready),
            "stale_reasons": sorted(set(stale_reasons)),
        }

