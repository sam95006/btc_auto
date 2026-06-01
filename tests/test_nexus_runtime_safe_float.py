import unittest

from backend.services import nexus_runtime as nr


class NexusRuntimeSafeFloatTests(unittest.TestCase):
    def test_safe_float_accepts_default(self):
        self.assertEqual(nr._safe_float(None, 5.0), 5.0)
        self.assertEqual(nr._safe_float("12.5"), 12.5)

    def test_ensure_min_trade_size_does_not_raise(self):
        runtime = object.__new__(nr.NexusRuntime)
        out = nr.NexusRuntime._ensure_min_trade_size(
            runtime,
            {"leverage": None, "margin": 90.0},
        )
        self.assertGreater(float(out["margin"]), 0.0)


if __name__ == "__main__":
    unittest.main()
