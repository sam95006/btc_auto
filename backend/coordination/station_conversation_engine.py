from __future__ import annotations

import random
from datetime import datetime


STATION_PARTICIPANTS = {
    "HQ": ["總部指揮官", "總部策略官", "總部風控官", "總部資金官"],
    "BTC": ["BTC 艦隊長", "BTC 交易官", "BTC 風控官"],
    "ETH": ["ETH 艦隊長", "ETH 交易官", "ETH 風控官"],
    "SOL": ["SOL 艦隊長", "SOL 交易官", "SOL 風控官"],
    "PEPE": ["PEPE 艦隊長", "PEPE 交易官", "PEPE 風控官"],
    "RADAR": ["雷達站站長", "巨鯨監控官", "異常掃描官"],
    "NEWS": ["新聞站站長", "宏觀分析官", "加密新聞官"],
    "RISK": ["風控中心主任", "曝險評估官"],
}


class StationConversationEngine:
    def build_channel_thread(self, channel: str, snapshot: dict) -> list[dict]:
        channel_key = str(channel or "HQ").upper()
        if channel_key == "WORLD":
            return self.build_world_thread(snapshot)
        if channel_key not in STATION_PARTICIPANTS:
            return []
        return self._build_internal_thread(channel_key, snapshot)

    def build_world_thread(self, snapshot: dict) -> list[dict]:
        system = snapshot.get("system", {}) or {}
        contexts = snapshot.get("market_context", {}) or {}
        btc_ctx = contexts.get("BTC", {}) or {}
        bias = btc_ctx.get("btc_market_bias", "NEUTRAL")
        alert = system.get("alert_level", "NORMAL")
        fleets = system.get("fleet_status", {}) or {}
        lines = [
            ("新聞站站長", f"各位站長，新聞面目前{'偏風險' if alert != 'NORMAL' else '偏中性'}，先對齊節奏。", "INFO"),
            ("雷達站站長", f"BTC 主方向 {bias}，巨鯨與 funding 我持續盯。", "INFO"),
            ("BTC 艦隊長", f"BTC 訊號 {fleets.get('BTC', {}).get('last_signal', 'HOLD')}，品質不足不硬闖。", "INFO"),
            ("ETH 艦隊長", f"ETH 跟 BTC 連動，目前 {fleets.get('ETH', {}).get('last_signal', 'HOLD')}。", "INFO"),
            ("SOL 艦隊長", f"SOL 波動大，等 BTC 站穩；訊號 {fleets.get('SOL', {}).get('last_signal', 'HOLD')}。", "INFO"),
            ("PEPE 艦隊長", "PEPE 只做順勢小倉，BTC 壓制時不加碼。", "WARNING" if bias == "BEARISH" else "INFO"),
            ("總部指揮官", f"收到。警報 {alert}，風控優先。", "HIGH" if alert != "NORMAL" else "INFO"),
        ]
        return self._pack_lines("WORLD", lines)

    def build_player_reply(self, channel: str, player_message: str, snapshot: dict) -> list[dict]:
        channel_key = str(channel or "WORLD").upper()
        text = str(player_message or "").strip()
        if not text:
            return []
        if channel_key == "WORLD":
            return self._reply_world(text, snapshot)
        return self._reply_station(channel_key, text, snapshot)

    def _build_internal_thread(self, channel: str, snapshot: dict) -> list[dict]:
        roles = STATION_PARTICIPANTS[channel]
        system = snapshot.get("system", {}) or {}
        fleet_state = system.get("fleet_status", {}).get(channel, {}) or {}

        if channel == "HQ":
            capital = snapshot.get("capital", {}) or {}
            lines = [
                (roles[0], f"總資產 {float(capital.get('total', 0) or 0):.2f}U。", "INFO"),
                (roles[1], f"警報 {system.get('alert_level', 'NORMAL')}。", "INFO"),
                (roles[2], "新倉以品質分數與相關性為先。", "INFO"),
            ]
            return self._pack_lines(channel, lines)

        if channel in {"BTC", "ETH", "SOL", "PEPE"}:
            lines = [
                (roles[0], f"艦隊 {fleet_state.get('status', 'MONITORING')}，訊號 {fleet_state.get('last_signal', 'HOLD')}。", "INFO"),
                (roles[1], "等品質過線，不追價。", "INFO"),
                (roles[2], "連續拒單時降倉降槓桿。", "WARNING"),
            ]
            return self._pack_lines(channel, lines)

        if channel == "RADAR":
            whale = snapshot.get("whale", {}) or {}
            return self._pack_lines(channel, [(roles[0], f"巨鯨 {whale.get('severity', 'NORMAL')}：{whale.get('summary', '掃描中')}", "INFO")])

        if channel == "NEWS":
            news = snapshot.get("news", []) or []
            latest = news[0] if news else {}
            headline = latest.get("summary_zh") or latest.get("summary") or "目前無重大新聞"
            return self._pack_lines(channel, [(roles[0], f"新聞：{headline}", "INFO")])

        return self._pack_lines(channel, [(roles[0], "風控中心待命。", "INFO")])

    def _reply_station(self, channel: str, text: str, snapshot: dict) -> list[dict]:
        roles = STATION_PARTICIPANTS.get(channel, ["站長"])
        captain, officer, risk = roles[0], roles[1] if len(roles) > 1 else roles[0], roles[2] if len(roles) > 2 else roles[0]
        signal = (snapshot.get("system", {}) or {}).get("fleet_status", {}).get(channel, {}).get("last_signal", "HOLD")
        if any(w in text for w in ("開倉", "做多", "做空", "買", "賣")):
            lines = [(captain, f"收到。目前訊號 {signal}，先走品質審核。", "INFO"), (risk, "BTC 反向壓力時保守執行。", "WARNING")]
        elif any(w in text for w in ("風險", "暫停")):
            lines = [(risk, "了解，本輪防守模式。", "HIGH"), (captain, "我會同步世界頻道。", "INFO")]
        else:
            lines = [(captain, f"收到：「{text[:80]}」。", "INFO"), (officer, random.choice(["明白，繼續盯盤。", "有變化立刻回報。"]), "INFO")]
        return self._pack_lines(channel, lines[:3])

    def _reply_world(self, text: str, snapshot: dict) -> list[dict]:
        alert = (snapshot.get("system", {}) or {}).get("alert_level", "NORMAL")
        if any(w in text for w in ("全員", "大家", "各站")):
            lines = [("總部指揮官", f"收到全頻指示：「{text[:60]}」。", "HIGH"), ("BTC 艦隊長", "BTC 收到。", "INFO")]
        elif any(w in text for w in ("暫停", "別開")):
            lines = [("總部指揮官", "同步：暫停高風險新倉。", "HIGH"), ("ETH 艦隊長", "ETH 不追高。", "INFO")]
        else:
            lines = [("總部指揮官", f"收到：「{text[:70]}」。", "INFO"), ("新聞站站長", "我會同步各站。", "INFO")]
            if alert != "NORMAL":
                lines.append(("風控中心主任", "仍有警報，各艦隊保守。", "WARNING"))
        return self._pack_lines("WORLD", lines[:4])

    def _pack_lines(self, channel: str, lines: list[tuple]) -> list[dict]:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        source = "世界頻道討論" if channel == "WORLD" else "站內討論"
        return [
            {
                "timestamp": stamp,
                "station": channel,
                "speaker": speaker,
                "message": message,
                "source": source,
                "importance": importance,
            }
            for speaker, message, importance in lines
        ]
