import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from terrain_pipeline.td_surface_river_edges import build_td_surface_river_edges, write_report
from terrain_pipeline.basin_storage import make_td_source as make_td_source
from terrain_pipeline.basin_topology import build_basin_hierarchy as build_basin_hierarchy
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import simulate_threshold_storage as simulate_basin_storage
from terrain_pipeline.common_infra import identity


def hierarchy_fixture():
    height = np.array([[3., 2.], [4., 1.]])
    valid = np.ones((2, 2), dtype=bool)
    return build_basin_hierarchy(make_td_source(height, spacing_m=1, valid_mask=valid))


class SurfaceRiverEdgesTests(unittest.TestCase):
    def test_requires_frozen_d4_faces_and_marks_missing_flux_diagnostic(self):
        hierarchy = hierarchy_fixture()
        result = build_td_surface_river_edges(hierarchy)
        self.assertTrue(result["diagnostic"]["d4_only"])
        self.assertTrue(result["diagnostic"]["diagnostic_only"])
        self.assertTrue(result["records"][0]["edge_id"].endswith("cell:0:0|" + result["records"][0]["endpoint_ids"][1]))
        self.assertEqual(result["records"][0]["cell_ids"], [0, 1])

    def test_protected_endpoint_rejected(self):
        height = np.array([[3., 2.], [4., 1.]])
        protected = np.array([[True, False], [False, False]])
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=1, protected_mask=protected))
        with self.assertRaisesRegex(ValueError, "protected"):
            build_td_surface_river_edges(hierarchy)

    def test_no_triangle_or_natural_boundary_inference(self):
        height = np.array([[3., 2.], [4., 1.]])
        opened = np.array([[False, False], [False, True]])
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=1, open_boundary_mask=opened))
        result = build_td_surface_river_edges(hierarchy)
        boundaries = [record for record in result["records"] if record["kind"] == "d4_boundary_face"]
        self.assertTrue(boundaries)
        self.assertTrue(all(record["boundary_kind"] == "engineered_boundary" for record in boundaries))
        self.assertTrue(all(record["natural_outlet"] is False for record in boundaries))
        self.assertTrue(all(record["boundary_face_flux_available"] is False for record in boundaries))

    def test_unknown_barrier_retains_hole_without_bridging(self):
        source = make_td_source(np.array([[2., 1.], [3., 0.]]), spacing_m=1,
                                valid_mask=np.array([[True, False], [True, True]]))
        result = build_td_surface_river_edges(build_basin_hierarchy(source))
        self.assertEqual(result["diagnostic"]["unknown_cells"], 1)
        self.assertTrue(all(1 not in record["cell_ids"] for record in result["records"]))
        self.assertFalse(result["diagnostic"]["hydraulic_ready"])

    def test_directional_flux_identity_and_time_rejected(self):
        hierarchy = hierarchy_fixture()
        storage = simulate_basin_storage(hierarchy, np.array([10.]), dt_s=10)
        result = build_td_surface_river_edges(hierarchy, storage=storage)
        for record in result["records"]:
            self.assertEqual(record["net_volume_m3"], record["forward_volume_m3"] - record["reverse_volume_m3"])
            self.assertEqual(record["gross_volume_m3"], record["forward_volume_m3"] + record["reverse_volume_m3"])
        self.assertFalse(result["diagnostic"]["hydraulic_ready"])
        bad = {**storage, "identity_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "identity"):
            build_td_surface_river_edges(hierarchy, storage=bad)
        bad = {**storage, "metadata": {**storage["metadata"], "dt_s": -10.}}
        bad["identity_sha256"] = identity(bad["arrays"], bad["metadata"])
        with self.assertRaises(ValueError):
            build_td_surface_river_edges(hierarchy, storage=bad)

    def test_missing_receiver_evidence_and_atomic_no_overwrite(self):
        result = build_td_surface_river_edges(hierarchy_fixture(), include_receiver=False)
        self.assertFalse(result["diagnostic"]["receiver_complete"])
        self.assertTrue(all(record["upstream_cell"] is None for record in result["records"]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            write_report(result, path)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_report(result, path)
            self.assertEqual(before, path.read_bytes())

    def test_frozen_real_hierarchy_cold_read_no_build_or_solver(self):
        root = Path(__file__).resolve().parents[1]
        with patch('terrain_pipeline.basin_topology.build_basin_hierarchy', side_effect=AssertionError("no build")), patch(
                'terrain_pipeline.basin_storage.simulate_threshold_storage', side_effect=AssertionError("no solve")):
            hierarchy = load_basin_hierarchy(root / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz",
                expected_sha256="36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422",
                expected_identity="cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998")
            result = build_td_surface_river_edges(hierarchy)
        self.assertEqual(sum(record["kind"] == "d4_internal_face" for record in result["records"]), 130560)
        self.assertFalse(result["diagnostic"]["hydraulic_ready"])


if __name__ == "__main__":
    unittest.main()
