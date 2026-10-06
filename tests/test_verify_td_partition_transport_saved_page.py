"""Saved-page transport diagnostic rejects changed pins and false certification."""

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import tempfile

import numpy as np

from tools import verify_td_partition_transport_saved_page as diagnostic


class SavedPageDiagnosticTests(unittest.TestCase):
    def test_independent_stage_matches_simple_zero_case(self):
        bed = np.zeros((2, 2), dtype=np.float64)
        depth = np.zeros((2, 2), dtype=np.float64)
        valid = np.ones((2, 2), dtype=bool)
        opened = np.zeros((2, 2), dtype=bool)
        faces = np.array([[0, 1], [0, 2], [1, 3], [2, 3]], dtype=np.int64)
        final, forward, reverse, boundaries, external = diagnostic._reference(bed, depth, valid, opened, faces)
        np.testing.assert_array_equal(final, depth.ravel())
        self.assertEqual(float(forward.sum() + reverse.sum() + external.sum()), 0.)
        self.assertEqual(len(boundaries), 0)

    def test_rejects_changed_primary_sha_before_loading(self):
        with patch.object(diagnostic, "file_sha256", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "source SHA"):
                diagnostic.diagnose()

    def test_real_report_contract_if_present(self):
        path = diagnostic.ROOT / "verification/td-basin-generation/independent-partition-saved-page-20261003-v3/report.json"
        if not path.is_file():
            self.skipTest("actual cold diagnostic not yet run")
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["shape_zx"], [256, 256])
        self.assertEqual(report["tile_count"], 1)
        self.assertFalse(report["real_cross_tile_validated"])
        self.assertFalse(report["rain_forcing_applied"])
        self.assertFalse(report["baseline_continuation"])
        self.assertFalse(report["full_water_or_full_day_accepted"])
        self.assertFalse(report["hydraulic_ready"])
        self.assertFalse(report["natural_outlet_verified"])
        self.assertFalse(report["publishable"])
        self.assertEqual(report["primary_source_sha256_before"], report["primary_source_sha256_after"])

    def test_atomic_publish_does_not_replace_existing_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "report.json"
            target.write_bytes(b"existing")
            with patch.object(sys, "argv", ["verify", "--output", str(target)]), patch.object(
                    diagnostic, "diagnose", return_value={"schema": "test"}):
                with self.assertRaises(FileExistsError):
                    diagnostic.main()
            self.assertEqual(target.read_bytes(), b"existing")

    def test_fresh_import_has_no_solver_or_numba(self):
        code = ("import tools.verify_td_partition_transport_saved_page; import sys; "
                "assert 'numba' not in sys.modules; "
                "assert 'terrain_pipeline.td_basin_transport_v6' not in sys.modules; "
                "assert 'terrain_pipeline.td_basin_storage_v10' not in sys.modules")
        subprocess.run([sys.executable, "-c", code], check=True)


if __name__ == "__main__":
    unittest.main()
