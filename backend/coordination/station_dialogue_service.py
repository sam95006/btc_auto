from __future__ import annotations

import os
import time

from backend.coordination.station_conversation_engine import StationConversationEngine


STATION_CHANNELS = ["HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "RISK"]
PLAYER_SPEAKER = os.getenv("NEXUS_PLAYER_CHAT_NAME", "指揮官")


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
