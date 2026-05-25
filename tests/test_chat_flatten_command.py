import unittest
from unittest.mock import MagicMock, patch

from backend.coordination.chat_command_handler import detect_chat_command, format_flatten_reply
from backend.coordination.station_dialogue_service import StationDialogueService


class ChatFlattenCommandTests(unittest.TestCase):
    def test_detect_flatten_phrases(self):
        self.assertEqual(detect_chat_command("整體平倉"), "flatten_all")
        self.assertEqual(detect_chat_command("  全部平倉  "), "flatten_all")
        self.assertEqual(detect_chat_command("請幫我整體平倉"), "flatten_all")
        self.assertEqual(detect_chat_command("close all"), "flatten_all")
        self.assertEqual(detect_chat_command("flatten all positions now"), "flatten_all")
        self.assertIsNone(detect_chat_command("今天行情如何？"))

    def test_format_flatten_reply(self):
        text = format_flatten_reply(
            {
                "closed": [{"symbol": "BTCUSDT", "side": "BUY", "pnl": 12.5}],
                "failed": [],
                "skipped": [],
            }
        )
        self.assertIn("BTCUSDT", text)
        self.assertIn("成功 1 筆", text)

    def test_handle_player_message_routes_flatten(self):
        chat_log = MagicMock()
        chat_log.add.side_effect = lambda *args, **kwargs: {
            "channel": args[0],
            "speaker": args[1],
            "message": args[2],
            "source": kwargs.get("source"),
        }
        service = StationDialogueService(chat_log, llm_gateway=None)
        flat_result = {"ok": True, "closed": [], "failed": [], "skipped": []}

        with patch(
            "backend.services.nexus_runtime.nexus_runtime.flatten_all_positions",
            return_value=flat_result,
        ) as flatten_mock:
            with patch(
                "backend.services.nexus_runtime.nexus_runtime.refresh_live_exchange_state",
            ):
                result = service.handle_player_message("WORLD", "整體平倉", snapshot={})

        self.assertTrue(result.get("ok"))
        self.assertEqual(result.get("command"), "flatten_all")
        flatten_mock.assert_called_once()
        self.assertGreaterEqual(chat_log.add.call_count, 2)


if __name__ == "__main__":
    unittest.main()
