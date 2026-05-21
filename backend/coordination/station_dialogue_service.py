from __future__ import annotations

import os
import time

from backend.coordination.station_conversation_engine import StationConversationEngine


STATION_CHANNELS = ["HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "RISK"]
PLAYER_SPEAKER = os.getenv("NEXUS_PLAYER_CHAT_NAME", "指揮官")
CHANNEL_CAPTAIN = {
    "HQ": "總部指揮官",
    "BTC": "BTC 艦隊長",
    "ETH": "ETH 艦隊長",
    "SOL": "SOL 艦隊長",
    "PEPE": "PEPE 艦隊長",
    "RADAR": "雷達站站長",
    "NEWS": "新聞站站長",
    "RISK": "風控中心主任",
    "WORLD": "總部指揮官",
}


class StationDialogueService:
    def __init__(self, chat_log, llm_gateway=None):
        self.chat_log = chat_log
        self.llm_gateway = llm_gateway
        self.engine = StationConversationEngine()
        self._last_refresh = {}
        self._last_world = 0.0

    def handle_player_message(self, channel, message, snapshot, player_name=None):
        text = str(message or "").strip()[:500]
        channel_key = str(channel or "WORLD").upper()
        if not text:
            return {"ok": False, "error": "message is required"}

        speaker = str(player_name or PLAYER_SPEAKER).strip() or PLAYER_SPEAKER
        stored = [
            self.chat_log.add(channel_key, speaker, text, source="玩家輸入", importance="INFO"),
        ]

        llm_rows = self._llm_player_reply(channel_key, text, snapshot)
        if llm_rows:
            for row in llm_rows:
                stored.append(
                    self.chat_log.add(
                        channel_key,
                        row["speaker"],
                        row["message"],
                        source=row.get("source", "AI 回覆"),
                        importance=row.get("importance", "INFO"),
                    )
                )
        else:
            for row in self.engine.build_player_reply(channel_key, text, snapshot):
                stored.append(
                    self.chat_log.add(
                        channel_key,
                        row["speaker"],
                        row["message"],
                        source="站內回覆",
                        importance=row.get("importance", "INFO"),
                    )
                )
        return {"ok": True, "channel": channel_key, "messages": stored}

    def _llm_player_reply(self, channel_key, text, snapshot):
        if not self.llm_gateway or not getattr(self.llm_gateway, "enabled", lambda: False)():
            return []

        system = snapshot.get("system", {}) or {}
        capital = snapshot.get("capital", {}) or {}
        news = snapshot.get("news", []) or []
        latest_news = news[0] if news else {}
        payload = {
            "channel": channel_key,
            "player_message": text,
            "alert_level": system.get("alert_level", "NORMAL"),
            "trading_paused": bool(system.get("trading_paused")),
            "capital_total": capital.get("total"),
            "fleet_status": system.get("fleet_status", {}),
            "growth_mode": snapshot.get("growth_mode", {}),
            "latest_news_headline": latest_news.get("summary_zh") or latest_news.get("summary") or "",
        }
        result = self.llm_gateway.run_task("chat", payload, fallback_output={})
        if str(result.get("status", "")).lower() not in {"ok", "success", "fallback"}:
            return []
        if result.get("status") == "fallback" and not (result.get("output") or {}).get("reply"):
            return []

        output = result.get("output") or {}
        reply = str(output.get("reply") or output.get("final_advisory") or "").strip()
        if not reply:
            return []

        importance = str(output.get("importance", "INFO")).upper()
        if importance not in {"INFO", "WARNING", "HIGH"}:
            importance = "INFO"
        captain = CHANNEL_CAPTAIN.get(channel_key, "站長")
        return [{"speaker": captain, "message": reply[:500], "importance": importance, "source": "AI 回覆"}]

    def maybe_refresh_channels(self, snapshot):
        refresh_seconds = max(45, int(os.getenv("NEXUS_STATION_CHAT_REFRESH_SECONDS", "120")))
        now = time.time()
        for channel in STATION_CHANNELS:
            last = float(self._last_refresh.get(channel, 0.0) or 0.0)
            if now - last < refresh_seconds:
                continue
            for row in self.engine.build_channel_thread(channel, snapshot):
                self.chat_log.add(channel, row["speaker"], row["message"], source=row["source"], importance=row["importance"])
            self._last_refresh[channel] = now

        if now - self._last_world >= refresh_seconds:
            for row in self.engine.build_channel_thread("WORLD", snapshot):
                self.chat_log.add("WORLD", row["speaker"], row["message"], source=row["source"], importance=row["importance"])
            self._last_world = now
