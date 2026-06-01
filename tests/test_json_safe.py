import unittest

from backend.core.json_safe import sanitize_for_json


class JsonSafeTests(unittest.TestCase):
    def test_strips_control_chars(self):
        raw = {"msg": "hello\x00world\x1f", "items": ["a\x0bb"]}
        clean = sanitize_for_json(raw)
        self.assertEqual(clean["msg"], "helloworld")
        self.assertEqual(clean["items"][0], "ab")

    def test_roundtrip_json(self):
        import json

        payload = sanitize_for_json({"x": "line\nok"})
        json.dumps(payload, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
