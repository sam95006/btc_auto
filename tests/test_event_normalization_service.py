import unittest

from backend.news.event_normalization_service import EventNormalizationService


class EventNormalizationServiceTests(unittest.TestCase):
    def test_normalizes_events_with_quality_and_type(self):
        service = EventNormalizationService()
        rows = service.normalize(
            [
                {
                    "id": "evt1",
                    "summary": "Fed signals possible rate cut for markets",
                    "bucket": "fed",
                    "impact": "HIGH",
                    "sentiment": "POSITIVE",
                    "targets": ["BTC", "ETH"],
                    "source": "Fed",
                    "major": True,
                    "published_ts": "2026-05-14T00:00:00Z",
                }
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "fed_policy")
        self.assertGreater(rows[0]["quality_score"], 0.7)
        self.assertTrue(rows[0]["major"])


if __name__ == "__main__":
    unittest.main()
