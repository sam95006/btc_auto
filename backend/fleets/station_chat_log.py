from datetime import datetime


class StationChatLog:
    STATIONS = ["HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "WHALE", "FUNDING", "RISK"]

    def __init__(self, runtime_store):
        self.runtime_store = runtime_store

    def add(self, station, speaker, message, source="SYSTEM", importance="INFO"):
        item = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "station": station,
            "speaker": speaker,
            "message": message,
            "source": source,
            "importance": importance,
        }
        self.runtime_store.append_station_chat(item)
        return item

    def recent_grouped(self, limit=400):
        grouped = self.runtime_store.recent_station_chats(limit=limit)
        for station in self.STATIONS:
            grouped.setdefault(station, [])
        return grouped

