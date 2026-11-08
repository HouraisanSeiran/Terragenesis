import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from tests.test_td_hour_pages_acceptance_io import write_bundle, write_json
from tools.audit_td_hourly_seams import audit, cut_ledger


class HourlyNativeSeamTests(unittest.TestCase):
    def fixture(self):
        cells = np.arange(20).reshape(4, 5)
        faces = np.concatenate((np.column_stack((cells[:, :-1].ravel(), cells[:, 1:].ravel())),
            np.column_stack((cells[:-1].ravel(), cells[1:].ravel())))).astype(np.int64)
        topology = dict(height_m=np.arange(20.).reshape(4, 5), valid_mask=np.ones((4, 5), bool),
            protected_mask=np.zeros((4, 5), bool), face_cells=faces, receiver=np.full(20, -1, np.int64))
        random = np.random.default_rng(123)
        storage = {key: value.copy() for key, value in topology.items()}
        for name in ("face_forward_m3", "face_reverse_m3", "active_forward_s", "active_reverse_s"):
            storage[name] = random.uniform(0, 10, len(faces))
        net = storage["face_forward_m3"] - storage["face_reverse_m3"]
        storage["internal_net_m3"] = (np.bincount(faces[:, 1], weights=net, minlength=20) -
                                     np.bincount(faces[:, 0], weights=net, minlength=20))[None, :]
        return topology, storage

    def test_complete_two_direction_partition_conserves_each_quadrant(self):
        topology, storage = self.fixture()
        report = cut_ledger(topology, storage, partition_row=2, partition_column=2, duration_s=3600.)
        self.assertEqual(report["unique_shared_face_count"], 9)
        self.assertEqual(len(report["seams"]), 4)
        self.assertLess(max(abs(value) for value in report["quadrant_residual_m3"]), 1e-12)
        self.assertTrue(all(seam["paired_residual_m3"] == 0 for seam in report["seams"]))
        self.assertEqual(sum(seam["both_directions_integrated_face_count"] for seam in report["seams"]), 9)

    def test_endpoint_reversal_preserves_outward_water(self):
        topology, storage = self.fixture()
        before = cut_ledger(topology, storage, partition_row=2, partition_column=2, duration_s=3600.)
        topology["face_cells"] = topology["face_cells"][:, ::-1].copy()
        storage["face_cells"] = topology["face_cells"].copy()
        storage["face_forward_m3"], storage["face_reverse_m3"] = storage["face_reverse_m3"], storage["face_forward_m3"]
        after = cut_ledger(topology, storage, partition_row=2, partition_column=2, duration_s=3600.)
        np.testing.assert_allclose(before["quadrant_outward_m3"], after["quadrant_outward_m3"], atol=1e-12)
        self.assertEqual([seam["canonical_endpoint_sha256"] for seam in before["seams"]],
                         [seam["canonical_endpoint_sha256"] for seam in after["seams"]])

    def test_missing_duplicate_face_and_bad_activity_are_rejected(self):
        for kind in ("missing", "duplicate", "activity"):
            topology, storage = self.fixture()
            if kind == "missing":
                topology["face_cells"] = topology["face_cells"][:-1]
                storage["face_cells"] = topology["face_cells"].copy()
            elif kind == "duplicate":
                topology["face_cells"][0] = topology["face_cells"][1]
                storage["face_cells"] = topology["face_cells"].copy()
            else:
                storage["active_forward_s"][0] = 3601.
            with self.assertRaises(ValueError):
                cut_ledger(topology, storage, partition_row=2, partition_column=2, duration_s=3600.)

    def test_unknown_grid_and_nonfinite_flux_are_rejected(self):
        topology, storage = self.fixture()
        topology["valid_mask"][0, 0] = False
        with self.assertRaises(ValueError):
            cut_ledger(topology, storage, partition_row=2, partition_column=2, duration_s=3600.)
        topology, storage = self.fixture()
        storage["face_forward_m3"][0] = np.nan
        with self.assertRaises(ValueError):
            cut_ledger(topology, storage, partition_row=2, partition_column=2, duration_s=3600.)

    def test_conservative_ledger_redistribution_is_rejected(self):
        topology, storage = self.fixture()
        storage["internal_net_m3"][0, 0] += .1
        storage["internal_net_m3"][0, 1] -= .1
        with self.assertRaisesRegex(ValueError, "original saved internal water ledger"):
            cut_ledger(topology, storage, partition_row=2, partition_column=2, duration_s=3600.)

    def test_complete_accepted_two_rain_saved_hour_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            topology, storage = self.fixture()
            grid = dict(spacing_m=30., origin_m_xz=[0., 0.])
            hierarchy = write_bundle(root / "hierarchy.npz", topology, grid)
            accepted = dict(acceptance_arguments=dict(hierarchy_record=hierarchy), comparison_records={})
            storage["depth_m"] = np.zeros((2, 20))
            for scenario in ("ordinary", "strong"):
                pages = []
                for hour in range(24):
                    metadata = dict(hierarchy_identity_sha256=hierarchy["expected_identity"], spacing_m=30.,
                        chunk_start_s=hour * 3600., chunk_end_s=(hour + 1) * 3600., dt_s=3600.)
                    record = write_bundle(root / scenario / f"hour-{hour:02d}.npz", storage, metadata)
                    pages.append(dict(hour=hour, storage=record))
                accepted["comparison_records"][scenario] = write_json(root / (scenario + "-comparison.json"),
                                                                       dict(pages={"1.25": pages}))
            path = root / "seam-acceptance.json"
            pin = write_json(path, accepted)
            with patch("tools.audit_td_hourly_seams.accepted_inputs", return_value=accepted):
                result = audit(path, pin["expected_sha256"])
            self.assertTrue(result["all_hourly_native_partition_ledgers_passed"])
            self.assertEqual([len(result["cases"][name]) for name in ("ordinary", "strong")], [24, 24])
            self.assertFalse(result["independently_solved_domains"])


if __name__ == "__main__":
    unittest.main()
