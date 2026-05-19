import json
from pathlib import Path
from datetime import datetime


class MeetingMemoryBroadcaster:
    MEMORY_MAP = {
        "HQ": "hq_memory.json",
        "BTC": "btc_memory.json",
        "ETH": "eth_memory.json",
        "SOL": "sol_memory.json",
        "PEPE": "pepe_memory.json",
        "RADAR": "radar_memory.json",
        "NEWS": "news_memory.json",
        "WHALE": "whale_memory.json",
        "FUNDING": "funding_memory.json",
        "RISK": "risk_memory.json",
        "MARKET": "market_memory.json",
        "LEDGER": "ledger_memory.json",
    }

    def __init__(self, base_dir="logs/nexus_memory"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, station):
        name = self.MEMORY_MAP.get(station, f"{station.lower()}_memory.json")
        return self.base_dir / name

    def _default_memory(self, station):
        return {
            "station": station,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "latest_meeting_notes": {},
            "history": [],
        }

    def read_memory(self, station):
        path = self._path_for(station)
        if not path.exists():
            return self._default_memory(station)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return self._default_memory(station)

    def write_memory(self, station, payload):
        path = self._path_for(station)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def broadcast(self, meeting):
        conclusion = meeting.get("conclusion", {})
        latest_notes = {}
        for station in self.MEMORY_MAP:
            memory = self.read_memory(station)
            station_instruction = conclusion.get("station_instructions", {}).get(station, [])
            fleet_instruction = conclusion.get("fleet_instructions", {}).get(station, [])
            note = {
                "meeting_id": meeting.get("meeting_id"),
                "meeting_type": meeting.get("type"),
                "summary": conclusion.get("summary", ""),
                "next_6h_focus": conclusion.get("next_6h_focus", []),
                "station_instructions": station_instruction,
                "fleet_instructions": fleet_instruction,
                "forbidden_actions": conclusion.get("forbidden_actions", {}).get(station, []),
                "watchlist": conclusion.get("watchlist", {}).get(station, []),
                "risk_notes": conclusion.get("risk_notes", {}).get(station, []),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            memory["updated_at"] = note["updated_at"]
            memory["latest_meeting_notes"] = note
            memory["history"] = [note] + list(memory.get("history", []))[:11]
            self.write_memory(station, memory)
            latest_notes[station] = note
        return latest_notes

    def load_all(self):
        return {
            station: self.read_memory(station).get("latest_meeting_notes", {})
            for station in self.MEMORY_MAP
        }

