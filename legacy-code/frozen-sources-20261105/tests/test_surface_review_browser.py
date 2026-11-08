"""Installed Edge browser contract smoke test; no screenshots as assertions."""

from pathlib import Path
import tempfile
import unittest

from tools.verify_surface_review_browser import audit


class SurfaceReviewBrowserTests(unittest.TestCase):
    def test_actual_edge_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            report=audit(Path(directory))
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["pageerrors"])


if __name__=="__main__":
    unittest.main()
