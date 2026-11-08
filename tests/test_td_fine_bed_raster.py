from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline.td_fine_bed_raster import (
    build_fine_bed_raster, load_fine_bed_raster, sample_native_dem,
    save_fine_bed_raster, validate_fine_bed_raster)


def fixture():
    rows, columns = np.indices((5, 5))
    arrays = {"height_m": 10. + columns + rows * 2.,
              "valid_mask": np.ones((5, 5), bool),
              "protected_mask": np.zeros((5, 5), bool),
              "open_boundary_mask": np.zeros((5, 5), bool),
              "cell_owner": np.zeros((5, 5), np.int64),
              "contribution_owner": np.zeros((5, 5), np.int64),
              "node_unknown_contact": np.zeros(1, bool)}
    metadata = {"origin_m_xz": [0., 0.], "spacing_m": 1.,
                "source_identity_sha256": "a" * 64}
    hierarchy = {"arrays": arrays, "metadata": metadata,
                 "identity_sha256": identity(arrays, metadata)}
    sections = {"schema": "td-watershed-sections-v1", "identity_sha256": "b" * 64,
                "selected_leaf_ids": [0],
                "source_identity_sha256": "a" * 64,
                "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                "node_sections": [{"node_id": "first", "width_m": 2.},
                                  {"node_id": "second", "width_m": 2.}],
                "edge_sections": [{"arc_id": "receiver:1:2", "node_ids": ["first", "second"],
                                   "triangle_indices": [0, 1]}],
                "mesh": {"vertices_xyz_m": [[.5, 10.5, .5], [1.5, 11.5, .5],
                                            [1.5, 13.5, 1.5], [.5, 12.5, 1.5]],
                         "triangles": [[0, 1, 2], [0, 2, 3]],
                         "triangle_arc_ids": ["receiver:1:2", "receiver:1:2"]}}
    return hierarchy, sections


class FineBedRasterTests(unittest.TestCase):
    def test_bilinear_native_and_zero_weight_corner(self):
        hierarchy, _ = fixture()
        arrays = hierarchy["arrays"]
        arrays["valid_mask"][1, 1] = False
        arrays["protected_mask"][1, 1] = True
        hierarchy["identity_sha256"] = identity(arrays, hierarchy["metadata"])
        exact = sample_native_dem(hierarchy, 0., 0.)
        self.assertEqual(exact["height_m"], 10.)
        self.assertEqual(exact["native_cell_ids"], [0])
        self.assertEqual(exact["rejection_reasons"], [])
        interior = sample_native_dem(hierarchy, .25, .25)
        self.assertIn("unknown_native_corner", interior["rejection_reasons"])
        self.assertIn("protected_native_corner", interior["rejection_reasons"])
        self.assertIsNone(interior["height_m"])
        self.assertIn("outside_native_dem", sample_native_dem(hierarchy, -1., 0.)["rejection_reasons"])

    def test_triangle_only_sparse_grid_ledger_and_roundtrip(self):
        hierarchy, sections = fixture()
        arrays_before = {key: value.copy() for key, value in hierarchy["arrays"].items()}
        record = build_fine_bed_raster(hierarchy, sections, fine_spacing_m=1., tile_cells=1)
        self.assertEqual(record["grid"]["spacing_m"], .5)
        self.assertEqual(record["summary"]["candidate_cells"], 4)
        self.assertEqual(record["summary"]["window_count"], 4)
        self.assertAlmostEqual(record["material_ledger"]["cut_rock_m3"], 1.)
        self.assertEqual(record["material_ledger"]["exported_excavated_rock_m3"], 1.)
        self.assertEqual(record["material_ledger"]["sediment_pore_m3"], 0.)
        for window in record["windows"]:
            for cell in window["cells"]:
                self.assertAlmostEqual(cell["source_sample"]["height_m"] - cell["derived_bed_m"], 1.)
        for key, value in arrays_before.items():
            np.testing.assert_array_equal(hierarchy["arrays"][key], value)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raster.json"
            save_fine_bed_raster(record, path)
            loaded = load_fine_bed_raster(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                         expected_identity=record["identity_sha256"], hierarchy=hierarchy,
                                         sections=sections)
            self.assertEqual(record, loaded)
            with self.assertRaises(FileExistsError):
                save_fine_bed_raster(record, path)
        broken = deepcopy(record)
        broken["windows"][0]["cells"][0]["derived_bed_m"] -= .1
        with self.assertRaises(ValueError):
            validate_fine_bed_raster(broken)

    def test_conflicts_protection_fill_cut_unknown_and_budget(self):
        hierarchy, sections = fixture()
        transitions = {"identity_sha256": "c" * 64, "entries": [{"status": "candidate",
            "accepted_port_arc_id": "receiver:1:2", "width_m": 2.,
            "vertices_xyz_m": [[.5, 9.5, .5], [1.5, 10.5, .5], [1.5, 12.5, 1.5]],
            "triangles": [[0, 1, 2]]}]}
        conflict = build_fine_bed_raster(hierarchy, sections, transitions)
        cells = [cell for window in conflict["windows"] for cell in window["cells"]]
        self.assertTrue(any("conflicting_triangle_overlap" in cell["rejection_reasons"] for cell in cells))
        self.assertFalse(conflict["hydraulic_ready"])
        local = build_fine_bed_raster(hierarchy, sections, transitions, scope="lake-entry-neighborhood")
        self.assertEqual(local["selection"]["selected_06_triangle_indices"], [0, 1])
        overlay = build_fine_bed_raster(hierarchy, sections, transitions, scope="transitions-only")
        self.assertEqual(overlay["selection"]["selected_06_triangle_indices"], [])
        self.assertEqual(len(overlay["triangles"]), 1)
        for reason, mutate in (
            ("protected_native_corner", lambda data: data["protected_mask"].fill(True)),
            ("open_boundary_native_corner", lambda data: data["open_boundary_mask"].fill(True)),
            ("unknown_native_owner", lambda data: data["node_unknown_contact"].fill(True))):
            source = deepcopy(hierarchy)
            mutate(source["arrays"])
            source["identity_sha256"] = identity(source["arrays"], source["metadata"])
            geometry = deepcopy(sections)
            geometry["hierarchy_identity_sha256"] = source["identity_sha256"]
            result = build_fine_bed_raster(source, geometry)
            self.assertEqual(result["summary"]["candidate_cells"], 0)
            self.assertTrue(all(reason in cell["rejection_reasons"]
                for window in result["windows"] for cell in window["cells"]))
            self.assertEqual(result["material_ledger"]["cut_rock_m3"], 0.)
        source = deepcopy(hierarchy)
        source["arrays"]["contribution_owner"].fill(1)
        source["arrays"]["node_unknown_contact"] = np.zeros(2, bool)
        source["identity_sha256"] = identity(source["arrays"], source["metadata"])
        geometry = deepcopy(sections)
        geometry["hierarchy_identity_sha256"] = source["identity_sha256"]
        outside = build_fine_bed_raster(source, geometry)
        self.assertEqual(outside["summary"]["candidate_cells"], 0)
        self.assertTrue(all("outside_selected_component" in cell["rejection_reasons"]
            for window in outside["windows"] for cell in window["cells"]))
        for delta, reason in ((2., "fill_without_material"), (-5., "cut_depth_exceeded")):
            geometry = deepcopy(sections)
            for point in geometry["mesh"]["vertices_xyz_m"]:
                point[1] += delta
            result = build_fine_bed_raster(hierarchy, geometry)
            self.assertEqual(result["summary"]["candidate_cells"], 0)
            self.assertTrue(all(reason in cell["rejection_reasons"]
                for window in result["windows"] for cell in window["cells"]))
        bounded = build_fine_bed_raster(hierarchy, sections, max_cells=1)
        self.assertEqual(bounded["summary"]["candidate_cells"], 0)
        self.assertEqual(bounded["summary"]["refused_triangles"], 2)
        for protection in (
            {"covered_native_cell_ids": [6], "stage_by_leaf": []},
            {"covered_native_cell_ids": [], "stage_by_leaf": [{"leaf_id": 0, "stage_m": 100.}]}):
            wet = build_fine_bed_raster(hierarchy, sections, wet_protection=protection)
            cells = [cell for window in wet["windows"] for cell in window["cells"]]
            self.assertTrue(all(cell["source_sample"]["wet_source_support"] for cell in cells))
            self.assertTrue(all("lake_wet_bed_cut_refused" in cell["rejection_reasons"] for cell in cells))
            self.assertTrue(all(cell["derived_bed_m"] == cell["source_sample"]["height_m"] for cell in cells))
            self.assertEqual(wet["material_ledger"]["cut_rock_m3"], 0.)
            validate_fine_bed_raster(wet, hierarchy, sections, wet_protection=protection)
        zero_cut = deepcopy(sections)
        for point in zero_cut["mesh"]["vertices_xyz_m"]:
            point[1] += 1.
        unchanged = build_fine_bed_raster(hierarchy, zero_cut, wet_protection=protection)
        self.assertEqual(unchanged["summary"]["candidate_cells"], 4)
        self.assertEqual(unchanged["material_ledger"]["cut_rock_m3"], 0.)


if __name__ == "__main__":
    unittest.main()
