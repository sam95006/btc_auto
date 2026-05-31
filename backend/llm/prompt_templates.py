import json


def _json_instruction(schema_hint: str) -> str:
    return (
        "Return valid JSON only. Do not wrap in markdown. "
        f"Schema hint: {schema_hint}"
    )


def build_news_prompt(payload: dict):
    system = (
        "You are NEXUS News HQ. You summarize the latest normalized events into a machine-readable "
        "risk-aware briefing. Never invent prices or account balances. Only reason from the provided snapshot."
    )
    schema = (
        '{"headline_summary": str, "market_regime_guess": str, "risk_flags": [str], '
        '"priority_assets": [str], "action_bias": str, "confidence": float}'
    )
    user = {
        "task": "news_understanding",
        "truth_ready": payload.get("truth_ready"),
        "major_events": payload.get("highest_risk_events", [])[:4],
        "bucket_counts": payload.get("bucket_counts", {}),
        "market_regimes": payload.get("market_regimes", {}),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_radar_prompt(payload: dict):
    system = (
        "You are NEXUS Radar Station. Interpret spread, liquidity, funding, open interest and whale/news conflicts. "
        "Never generate prices on your own."
    )
    schema = (
        '{"market_pressure": str, "liquidity_alerts": [str], "whale_conflict": bool, '
        '"news_conflict": bool, "watch_symbols": [str], "probe_recommendation": str}'
    )
    user = {
        "task": "radar_interpretation",
        "market_context": payload.get("market_context", {}),
        "events": payload.get("normalized_events", [])[:6],
        "truth_layer_status": payload.get("truth_layer_status", {}),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_roundtable_prompt(payload: dict):
    system = (
        "You are the NEXUS HQ round table summarizer. Produce a concise machine-readable meeting conclusion "
        "based only on the provided meeting memory and event context."
    )
    schema = (
        '{"meeting_summary": str, "risk_level": str, "enabled_desks": [str], '
        '"disabled_desks": [str], "reserve_action": str, "next_actions": [str]}'
    )
    user = {
        "task": "round_table_summary",
        "meeting_reference": payload.get("meeting_reference"),
        "machine_summary": payload.get("machine_summary"),
        "risk_level": payload.get("risk_level"),
        "enabled_desks": payload.get("enabled_desks", []),
        "disabled_desks": payload.get("disabled_desks", []),
        "events": payload.get("normalized_events", [])[:5],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_reflection_prompt(payload: dict):
    system = (
        "You are the NEXUS trade reflection analyst. Analyze recent loss patterns and produce a compact recommendation set. "
        "Do not adjust strategy directly. Output recommendations only."
    )
    schema = (
        '{"reflection_summary": str, "top_failure_patterns": [str], "confidence_calibration_bias": str, '
        '"recommended_reviews": [str], "disabled_pattern_candidates": [str]}'
    )
    user = {
        "task": "trade_reflection",
        "loss_count": payload.get("loss_count", 0),
        "failure_pattern_counts": payload.get("failure_pattern_counts", {}),
        "latest_recommendations_by_fleet": payload.get("latest_recommendations_by_fleet", {}),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_chat_prompt(payload: dict):
    system = (
        "You are a NEXUS station officer replying to the commander in Traditional Chinese (繁體中文). "
        "Be concise (2-4 sentences), actionable, and grounded only in the provided snapshot. "
        "Never invent balances, prices, or positions. If data is missing, say what you need."
    )
    schema = '{"reply": str, "importance": "INFO|WARNING|HIGH"}'
    user = {
        "task": "station_chat_reply",
        "channel": payload.get("channel"),
        "player_message": payload.get("player_message"),
        "alert_level": payload.get("alert_level"),
        "trading_paused": payload.get("trading_paused"),
        "capital_total": payload.get("capital_total"),
        "fleet_status": payload.get("fleet_status"),
        "growth_mode": payload.get("growth_mode"),
        "latest_news_headline": payload.get("latest_news_headline"),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_radar_proposal_prompt(payload: dict):
    system = (
        "You are NEXUS Radar Outpost coin selector. ONLY propose altcoin futures trades outside "
        "core fleet symbols (BTC/ETH/SOL/PEPE). Core fleets are handled elsewhere — never propose them. "
        "Pick at most 2 symbols from the provided candidates/board with clear rationale."
    )
    schema = (
        '{"radar_orders": [{"symbol": str, "side": "BUY|SELL", "confidence": float, "rationale": str}], '
        '"skip_reason": str}'
    )
    user = {
        "task": "radar_coin_selection",
        "core_fleet_symbols": payload.get("core_fleet_symbols", []),
        "candidates": payload.get("candidates", []),
        "market_board": payload.get("market_board", [])[:12],
        "truth_layer_status": payload.get("truth_layer_status", {}),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_trade_proposer_prompt(payload: dict):
    system = (
        "You are NEXUS AI trade proposer. Propose at most 2 futures trades from the snapshot. "
        "Respect learning_blocked_symbols (never propose them). Prefer RADAR altcoins over core fleets. "
        "Output advisory proposals only; execution governor will approve or reject."
    )
    schema = (
        '{"trade_proposals": [{"fleet": "RADAR|BTC|ETH|SOL|PEPE", "symbol": str, "side": "BUY|SELL", '
        '"confidence": float, "rationale": str}], "skip_reason": str}'
    )
    user = {
        "task": "ai_trade_proposer",
        "positions": payload.get("positions", [])[:12],
        "market_context": payload.get("market_context", {}),
        "learning_blocked_symbols": payload.get("learning_blocked_symbols", []),
        "news_headlines": payload.get("news_headlines", [])[:6],
        "radar_candidates": payload.get("radar_candidates", [])[:8],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_agent_prompt(payload: dict):
    system = (
        "You are the NEXUS structured discussion orchestrator. Convert multi-agent proposals into a ranked, "
        "conflict-aware plan. You are advisory only and cannot approve trades."
    )
    schema = (
        '{"world_channel_summary": str, "ranked_proposals": [object], "trade_proposals": [object], '
        '"conflicts": [str], "hq_review_required": bool, "final_advisory": str}'
    )
    user = {
        "task": "agent_discussion",
        "world_channel": payload.get("world_channel", []),
        "internal_channels": payload.get("internal_channels", {}),
        "truth_layer_status": payload.get("truth_layer_status", {}),
        "market_context": payload.get("market_context", {}),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"instruction": _json_instruction(schema), "input": user}, ensure_ascii=False)},
    ]


def build_regime_classifier_prompt(payload: dict):
    system = (
        "You are NEXUS market regime classifier. Choose exactly one label for crypto risk-on context. "
        "Labels: CHOP_RNG (range/chop), TREND_BULL (risk-on trend), HIGH_RISK_MACRO (elevated macro/liquidity risk)."
    )
    schema = '{"market_regime": "CHOP_RNG|TREND_BULL|HIGH_RISK_MACRO", "rationale": str}'
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {"instruction": _json_instruction(schema), "input": payload},
                ensure_ascii=False,
            ),
        },
    ]


def build_flex_trade_eval_prompt(payload: dict):
    pure = bool(payload.get("pure_ai_mode"))
    system = (
        "You are NEXUS pure AI futures trader on Binance testnet. "
        + (
            "You are the SOLE decision maker — no rule engine follows you. "
            "Read wallet, deployable_pool, regime, fear/greed, funding/OI, radar candidates, "
            "core signals, open positions, per-symbol context. "
            "Pick 1-2 highest-edge trades. MUST set leverage (10-100) and margin_usd OR margin_pct_deployable "
            "for meaningful notional (target large PnL, not micro scalps). "
            if pure
            else
            "Synthesize wallet capital, deployable_pool, regime, fear/greed, funding/OI stress, "
            "radar candidates, core fleet signals, open positions, and per-symbol market context. "
            "For each proposal you MUST set leverage (integer 2-100) and either "
            "margin_usd (absolute USDT margin) OR margin_pct_deployable (fraction of deployable_pool 0.03-0.20). "
            "Higher confidence + stronger edge → higher leverage and margin within caps. "
        )
        + "Never invent prices. Respect blocked_symbols. Output JSON only."
    )
    schema = (
        '{"trade_proposals": [{"fleet": "RADAR|BTC|ETH|SOL|PEPE", "symbol": str, "side": "BUY|SELL", '
        '"confidence": float, "score": float, "leverage": float, "margin_usd": float, '
        '"margin_pct_deployable": float, "rationale": str, "edge_summary": str, "risk_flags": [str]}], '
        '"market_read": str, "skip_reason": str}'
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {"instruction": _json_instruction(schema), "input": payload},
                ensure_ascii=False,
            ),
        },
    ]


def build_flex_exit_eval_prompt(payload: dict):
    pure = bool(payload.get("pure_ai_mode"))
    if pure:
        system = (
            "You are NEXUS pure AI exit manager on Binance testnet. "
            "You are the SOLE exit decision maker. For EVERY open position output PARTIAL or CLOSE "
            "when profit is meaningful or thesis breaks; HOLD only if strong edge remains. "
            "Do not leave stale positions open without reason. "
            "Use pnl_pct_on_margin, leverage, regime, external intel. Never invent prices."
        )
    else:
        system = (
            "You are NEXUS full-auto exit manager. For each open futures position decide HOLD, PARTIAL, or CLOSE. "
            "Actively take profit when unrealized_pnl reaches profit_targets.take_profit_usd or edge fades. "
            "Cut loss when thesis breaks or pnl below -profit_targets.stop_loss_usd. "
            "Use pnl_pct_on_margin, leverage, regime shift, and external intel. Never invent prices."
        )
    schema = (
        '{"exit_actions": [{"symbol": str, "fleet": str, "decision": "HOLD|PARTIAL|CLOSE", '
        '"fraction": float, "confidence": float, "urgency": "low|medium|high", "reason": str}], '
        '"portfolio_read": str}'
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {"instruction": _json_instruction(schema), "input": payload},
                ensure_ascii=False,
            ),
        },
    ]


def build_post_mortem_prompt(payload: dict):
    system = (
        "You are NEXUS post-trade risk coach. Diagnose losing trades. "
        "Return tactical_loss only when the environment made the trade structurally poor."
    )
    schema = (
        '{"is_tactical_loss": bool, "toxic_features": [str], "action_recommendation": '
        '"BLOCK_STRATEGY|MONITOR", "target_symbol": str, "block_duration_minutes": int, "rationale": str}'
    )
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(
                {"instruction": _json_instruction(schema), "input": payload},
                ensure_ascii=False,
            ),
        },
    ]
