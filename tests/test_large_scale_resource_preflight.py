import unittest

from terrain_pipeline.large_scale_resource_preflight import preflight


class LargeScaleResourcePreflightTests(unittest.TestCase):
    def test_1024_and_2048_fit_default_budget(self):
        self.assertTrue(preflight(1024).runnable)
        self.assertTrue(preflight(2048).runnable)

    def test_4096_is_rejected_by_current_global_state_budget(self):
        result = preflight(4096)
        self.assertFalse(result.runnable)
        self.assertIn("streamed graph state", result.reason)

    def test_invalid_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            preflight(1024, max_mib=0)
