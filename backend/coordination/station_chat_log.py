from datetime import datetime


class StationChatLog:
    CHANNELS = ["WORLD", "HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "RISK", "WHALE", "FUNDING"]

    def __init__(self, runtime_store):
        self.runtime_store = runtime_store

    def add(self, channel, speaker, message, source="SYSTEM", importance="INFO"):
        channel_key = str(channel or "HQ").upper()
        item = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "station": channel_key,
            "speaker": str(speaker or "系統").strip() or "系統",
            "message": str(message or "").strip() or "目前沒有新的通訊內容。",
            "source": str(source or "站內通訊").strip() or "站內通訊",
            "importance": str(importance or "INFO").upper(),
        }
        self.runtime_store.append_station_chat(item)
        return item

    def recent_grouped(self, limit=500):
        grouped = self.runtime_store.recent_station_chats(limit=limit)
        for channel in self.CHANNELS:
            grouped.setdefault(channel, [])
        return grouped
