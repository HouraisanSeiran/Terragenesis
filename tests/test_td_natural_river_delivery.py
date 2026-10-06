import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, save_basin_hierarchy
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_natural_channel_geometry import (
    build_natural_channel_geometry, evaluate_natural_channel_window,
    save_natural_channel_geometry, save_natural_channel_window,
)
from terrain_pipeline.td_natural_river_network import (
    build_natural_river_network, save_natural_river_network,
)
from tools.audit_td_natural_river_network import audit_saved_network
from tools.export_td_natural_river_review import export_review
from tools.export_td_natural_river_review_v2 import export_review_v2


def pinned(path, value, saver):
    saver(path, value)
    return {"path": str(path), "expected_sha256": file_sha256(path),
            "expected_identity": value["identity_sha256"]}


class NaturalDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        height = np.fromfunction(lambda row, column: 100 - row - column, (12, 12))
        opened = np.zeros(height.shape, bool)
        opened[-1, -1] = True
        hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=30., open_boundary_mask=opened))
        network = build_natural_river_network(hierarchy, expected_hierarchy_identity=hierarchy["identity_sha256"])
        geometry = build_natural_channel_geometry(network)
        window = evaluate_natural_channel_window(geometry, network, window_origin_m_xz=(180., 240.),
                                                 spacing_m=1., shape_zx=(61, 61))
        self.hierarchy = pinned(self.directory / "hierarchy.npz", hierarchy, save_basin_hierarchy)
        self.network = pinned(self.directory / "network.npz", network, save_natural_river_network)
        self.geometry = pinned(self.directory / "geometry.npz", geometry, save_natural_channel_geometry)
        self.window = pinned(self.directory / "window.npz", window, save_natural_channel_window)

    def tearDown(self):
        self.temporary.cleanup()

    def test_cold_export_and_independent_saved_audit(self):
        with patch("terrain_pipeline.td_natural_river_network.build_natural_river_network", side_effect=AssertionError("rebuild")), \
                patch("terrain_pipeline.td_natural_channel_geometry.build_natural_channel_geometry", side_effect=AssertionError("geometry")), \
                patch("terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy", side_effect=AssertionError("routing")):
            report = audit_saved_network(network_record=self.network, hierarchy_record=self.hierarchy,
                                          geometry_record=self.geometry, window_record=self.window)
            output = self.directory / "review.json"
            exported = export_review(output, network_record=self.network, geometry_record=self.geometry)
        self.assertTrue(all(report["checks"].values()))
        self.assertFalse(report["publishable"])
        review = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(review["grid"]["shape_zx"], [12, 12])
        self.assertFalse(review["capabilities"]["water_surface_3d"])
        self.assertFalse(review["capabilities"]["time_playback"])
        self.assertEqual(exported["sha256"], file_sha256(output))
        self.assertGreater(report["window_material_cut_m3"], 0.)

    def test_export_budget_rejects_before_any_publication(self):
        output = self.directory / "over-budget.json"
        with self.assertRaisesRegex(ValueError, "byte budget"):
            export_review(output, network_record=self.network, geometry_record=self.geometry, max_bytes=1)
        self.assertFalse(output.exists())
        for invalid in (True, 0, -1, 33 * 1024 * 1024):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                export_review(output, network_record=self.network, geometry_record=self.geometry, max_bytes=invalid)

    def test_export_refuses_wrong_external_pin_and_existing_output(self):
        output = self.directory / "review.json"
        wrong = dict(self.network, expected_sha256="0" * 64)
        with self.assertRaises(ValueError):
            export_review(output, network_record=wrong, geometry_record=self.geometry)
        self.assertFalse(output.exists())
        export_review(output, network_record=self.network, geometry_record=self.geometry)
        with self.assertRaises(FileExistsError):
            export_review(output, network_record=self.network, geometry_record=self.geometry)

    def _delivery_index(self):
        review = export_review(self.directory / "review.json", network_record=self.network,
                               geometry_record=self.geometry)
        artifacts = {name: {"path": Path(pin["path"]).name, "sha256": pin["expected_sha256"],
                            "identity_sha256": pin["expected_identity"]} for name, pin in
                     (("network", self.network), ("geometry", self.geometry), ("window", self.window))}
        artifacts["review.json"] = {"path": "review.json", "sha256": review["sha256"]}
        record = {"schema": "td-natural-river-delivery-v1", "artifacts": artifacts,
                  **{flag: False for flag in
                     ("hydraulic_ready", "natural_outlet_verified", "publishable", "solver_advanced")}}
        path = self.directory / "index.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path, record

    def test_v2_cold_review_has_real_fine_bed_and_inspection_priors(self):
        index, unused_record = self._delivery_index()
        with patch("terrain_pipeline.td_natural_river_network.build_natural_river_network", side_effect=AssertionError("rebuild")), \
                patch("terrain_pipeline.td_natural_channel_geometry.evaluate_natural_channel_window", side_effect=AssertionError("resample")), \
                patch("terrain_pipeline.td_natural_channel_geometry.build_natural_channel_geometry", side_effect=AssertionError("geometry")):
            result = export_review_v2(self.directory / "review-v2.json", index_path=index,
                                      index_sha256=file_sha256(index))
        record = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(record["schema"], "td-natural-river-review-v2")
        self.assertEqual(len(record["network"]["edge_q_normal_m3_s"]), len(record["network"]["edge_cell_ids"]))
        self.assertEqual(len(record["network"]["node_supply_duration_fraction"]), len(record["network"]["node_cell_ids"]))
        self.assertGreater(len(record["basin_statistics"]["basin_terminal_cell_ids"]), 0)
        fine = record["fine_bed_window"]["arrays"]
        self.assertGreater(np.sum(fine["actual_cut_m"]), 0.)
        np.testing.assert_allclose(np.array(fine["source_surface_m"]) - fine["actual_cut_m"], fine["bounded_surface_m"])
        self.assertFalse(record["capabilities"]["water_surface_3d"])
        self.assertFalse(record["capabilities"]["time_playback"])
        self.assertEqual(record["status"], "diagnostic_failure")
        self.assertEqual(record["layer_status"]["fine_bed_window"], "diagnostic_failure")
        self.assertFalse(record["quality_gates"]["fine_bed_geometry_ready"])
        self.assertFalse(record["capabilities"]["fine_bed_window_geometry_ready"])
        self.assertTrue(record["capabilities"]["fine_bed_window_3d"])
        self.assertGreater(record["quality_gates"]["fine_window_needs_refinement_nodes"], 0)
        self.assertEqual(len(record["bed_shape_identity_sha256"]), 64)

    def test_v2_rejects_budget_and_changed_saved_review(self):
        index, unused_record = self._delivery_index()
        output = self.directory / "review-v2.json"
        with self.assertRaisesRegex(ValueError, "byte budget"):
            export_review_v2(output, index_path=index, index_sha256=file_sha256(index), max_bytes=1)
        self.assertFalse(output.exists())
        (self.directory / "review.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "SHA"):
            export_review_v2(output, index_path=index, index_sha256=file_sha256(index))
        self.assertFalse(output.exists())

    def test_v2_rejects_artifact_escape_and_foreign_window_pin(self):
        index, record = self._delivery_index()
        output = self.directory / "review-v2.json"
        for field, value in (("path", "../window.npz"), ("expected_identity", "0" * 64)):
            changed = json.loads(json.dumps(record))
            key = "identity_sha256" if field == "expected_identity" else field
            changed["artifacts"]["window"][key] = value
            index.write_text(json.dumps(changed), encoding="utf-8")
            with self.subTest(field=field), self.assertRaises(ValueError):
                export_review_v2(output, index_path=index, index_sha256=file_sha256(index))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
