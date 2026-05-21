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


def build_agent_prompt(payload: dict):
    system = (
        "You are the NEXUS structured discussion orchestrator. Convert multi-agent proposals into a ranked, "
        "conflict-aware plan. You are advisory only and cannot approve trades."
    )
    schema = (
        '{"world_channel_summary": str, "ranked_proposals": [object], "conflicts": [str], '
        '"hq_review_required": bool, "final_advisory": str}'
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
