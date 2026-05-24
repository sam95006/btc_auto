import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

from backend.services.nexus_runtime import FIXED_MEETING_SLOTS, NexusRuntime


class RoundtableScheduleTests(unittest.TestCase):
    def _taipei(self, year, month, day, hour, minute=0):
        if ZoneInfo is None:
            return datetime(year, month, day, hour, minute, 0)
        return datetime(year, month, day, hour, minute, 0, tzinfo=ZoneInfo("Asia/Taipei"))

    @patch("backend.services.nexus_runtime.runtime_store")
    def test_ensure_refreshes_today_passed_slots(self, mock_store):
        mock_store.recent_meetings.return_value = [
            {
                "meeting_id": "scheduled_2026-05-20_18-00",
                "slot": "18:00",
                "time": "2026-05-20 18:00:00",
                "type": "SCHEDULED_ROUND_TABLE",
                "conclusion": {"summary": "18:00 固定圓桌會議完成，舊資料。"},
            }
        ]
        runtime = NexusRuntime.__new__(NexusRuntime)
        runtime.meetings = []
        runtime.latest_news = [{"summary_zh": "測試新聞摘要"}]
        runtime.portfolio_status = {"fleet_restrictions": {}, "capital_adjustments": {}, "reserve_action": "hold"}
        runtime.station_learning_exchange = {}
        runtime.state_manager = MagicMock()
        runtime.state_manager.snapshot.return_value = {"fleet_status": {"ETH": "TRADING"}}
        runtime.alerts = []
        runtime._normalize_meeting_record = NexusRuntime._normalize_meeting_record.__get__(runtime, NexusRuntime)
        runtime._save_round_table_memory = MagicMock()
        runtime._append_meeting_alert = MagicMock()

        with patch("backend.services.nexus_runtime.nexus_now", return_value=self._taipei(2026, 5, 24, 19, 30)):
            runtime._ensure_fixed_roundtables()

        today_ids = {item.get("meeting_id") for item in runtime.meetings}
        self.assertIn("scheduled_2026-05-24_00-00", today_ids)
        self.assertIn("scheduled_2026-05-24_06-00", today_ids)
        self.assertIn("scheduled_2026-05-24_12-00", today_ids)
        self.assertIn("scheduled_2026-05-24_18-00", today_ids)
        self.assertNotIn("scheduled_2026-05-20_18-00", today_ids)

        latest_18 = next(item for item in runtime.meetings if item.get("meeting_id") == "scheduled_2026-05-24_18-00")
        summary = latest_18.get("conclusion", {}).get("summary", "")
        self.assertIn("2026-05-24", summary)
        self.assertIn("測試新聞摘要", summary)
        self.assertGreaterEqual(mock_store.append_meeting.call_count, len(FIXED_MEETING_SLOTS))

    @patch("backend.services.nexus_runtime.runtime_store")
    def test_enrich_today_meetings_with_llm(self, mock_store):
        runtime = NexusRuntime.__new__(NexusRuntime)
        runtime.meetings = [
            {
                "meeting_id": "scheduled_2026-05-24_12-00",
                "slot": "12:00",
                "time": "2026-05-24 12:00:00",
                "type": "SCHEDULED_ROUND_TABLE",
                "conclusion": {"summary": "12:00 固定圓桌會議完成（更新 2026-05-24 12:05 Taipei）。重點摘要：測試"},
            }
        ]
        runtime.portfolio_status = {}
        runtime.station_learning_exchange = {}
        runtime._normalize_meeting_record = NexusRuntime._normalize_meeting_record.__get__(runtime, NexusRuntime)

        payload = {"machine_summary": "風險中性", "risk_level": "NORMAL", "fleet_restrictions": {"BTC": ["pause"]}}
        llm = {"output": {"meeting_summary": "維持觀察 BTC 方向"}}

        with patch("backend.services.nexus_runtime.nexus_now", return_value=self._taipei(2026, 5, 24, 13, 0)):
            runtime._enrich_today_scheduled_meetings(payload, llm)

        summary = runtime.meetings[0]["conclusion"]["summary"]
        self.assertIn("｜AI：", summary)
        self.assertIn("風險中性", summary)
        self.assertIn("維持觀察 BTC 方向", summary)
        mock_store.append_meeting.assert_called()


if __name__ == "__main__":
    unittest.main()
