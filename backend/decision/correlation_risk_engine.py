class CorrelationRiskEngine:
    def evaluate(self, decision, open_positions, prices, market_context, tick_orders, meeting_notes=None):
        fleet = decision["fleet"]
        side = decision["side"]
        margin = float(decision.get("margin", 0.0) or 0.0)
        quality_score = float(decision.get("quality_score", 0.0) or 0.0)
        btc_fast = float(market_context.get("btc_change_fast", 0.0) or 0.0)
        btc_slow = float(market_context.get("btc_change_slow", 0.0) or 0.0)
        meeting_notes = meeting_notes or {}
        forbidden_text = " ".join(meeting_notes.get("forbidden_actions", []))

        if fleet in forbidden_text and ((side == "BUY" and "?šå?" in forbidden_text) or (side == "SELL" and "?šç©º" in forbidden_text)):
            return False, "meeting_forbidden_action"

        if fleet == "PEPE" and side == "BUY" and (btc_fast < -0.006 or btc_slow < -0.012):
            return False, "btc_downtrend_blocks_pepe_long"
        if fleet == "PEPE" and side == "SELL" and btc_fast > 0.006 and margin > 30.0:
            return False, "btc_strong_up_blocks_pepe_heavy_short"

        if fleet == "PEPE":
            btc_margins = [float(item.get("margin", 30.0)) for item in tick_orders if item.get("fleet") == "BTC"]
            btc_reference_margin = max(btc_margins or [100.0])
            if margin > btc_reference_margin * 0.3:
                return False, "pepe_margin_above_btc_cap"

        if fleet in ("SOL", "PEPE"):
            peer = "PEPE" if fleet == "SOL" else "SOL"
            peer_same_side = [item for item in tick_orders if item.get("fleet") == peer and item.get("side") == side]
            if peer_same_side:
                peer_quality = max(float(item.get("quality_score", 0.0)) for item in peer_same_side)
                if quality_score < peer_quality:
                    return False, "lower_quality_alt_correlation_block"

        if fleet == "PEPE" and side == "BUY":
            other_alt_longs = [item for item in tick_orders if item.get("fleet") in ("ETH", "SOL") and item.get("side") == "BUY"]
            if other_alt_longs and quality_score < 0.85:
                return False, "pepe_deprioritized_vs_eth_sol"

        notional = float(decision.get("margin", 0.0)) * float(decision.get("leverage", 1.0))
        if fleet in ("BTC", "ETH") and side in ("BUY", "SELL"):
            same_side_exposure = sum(
                float(item.get("margin", 0.0)) * float(item.get("leverage", 1.0))
                for item in open_positions
                if item.get("fleet") in ("BTC", "ETH") and item.get("side") == side
            )
            same_side_exposure += sum(
                float(item.get("margin", 0.0)) * float(item.get("leverage", 1.0))
                for item in tick_orders
                if item.get("fleet") in ("BTC", "ETH") and item.get("side") == side
            )
            if same_side_exposure + notional > 1700.0 * 0.6:
                return False, "btc_eth_total_exposure_cap"

        return True, ""
