import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_source import make_td_source, validate_td_source
from terrain_pipeline.td_basin_hierarchy import (
    basin_volume_at_level, build_basin_hierarchy, load_basin_hierarchy, save_basin_hierarchy,
)


class BasinHierarchyTests(unittest.TestCase):
    def build(self, height, **kwargs):
        return build_basin_hierarchy(make_td_source(np.array(height, dtype=float), spacing_m=1, **kwargs))

    def test_single_bowl_exact_capacity_and_unchanged_bed(self):
        result = self.build([[3, 3, 3], [3, 0, 3], [3, 3, 3]])
        arrays = result["arrays"]
        self.assertEqual(arrays["node_parent"].tolist(), [-1])
        self.assertEqual(basin_volume_at_level(result, 0, 2), 2)
        self.assertEqual(basin_volume_at_level(result, 0, 4), 12)
        self.assertEqual(arrays["height_m"][1, 1], 0)
        self.assertFalse(arrays["height_m"].flags.writeable)

    def test_nested_exact_stage_volumes_without_duplicate_children(self):
        result = self.build([[0, 2, 1, 4, 0]])
        arrays = result["arrays"]
        self.assertEqual(arrays["node_parent"].tolist(), [3, 4, 3, 4, -1])
        self.assertEqual(arrays["node_birth_m"].tolist(), [0, 0, 1, 2, 4])
        self.assertEqual(arrays["stage_capacity_m3"][:4].tolist(), [2, 4, 1, 6])
        self.assertEqual(basin_volume_at_level(result, 3, 2), 3)
        self.assertEqual(basin_volume_at_level(result, 3, 4), 9)
        self.assertEqual(basin_volume_at_level(result, 4, 4), 13)
        self.assertEqual(sum(arrays["stage_capacity_m3"][:4]), 13)
        self.assertEqual(arrays["cell_owner"].tolist(), [[0, 3, 2, 4, 1]])
        self.assertEqual(arrays["contribution_owner"].tolist(), [[0, 0, 2, 1, 1]])

    def test_equal_height_multiple_saddles_single_multifurcation(self):
        result = self.build([[0, 2, 0], [2, 3, 2], [0, 2, 0]])
        arrays = result["arrays"]
        self.assertEqual(arrays["node_parent"].tolist(), [4, 4, 4, 4, -1])
        saddle = (arrays["face_level_m"] == 2) & (arrays["face_merge_node"] == 4)
        self.assertEqual(int(saddle.sum()), 8)
        self.assertEqual(basin_volume_at_level(result, 4, 2), 8)
        self.assertEqual(basin_volume_at_level(result, 4, 3), 16)

    def test_unknown_barrier_and_diagonal_contact_do_not_merge(self):
        valid = np.array([[True, False], [False, True]])
        result = self.build([[0, 9], [9, 0]], valid_mask=valid)
        arrays = result["arrays"]
        self.assertEqual(arrays["node_parent"].tolist(), [-1, -1])
        self.assertEqual(arrays["face_cells"].shape, (0, 2))
        self.assertTrue(arrays["node_unknown_contact"].all())
        self.assertFalse(arrays["node_open_boundary"].any())
        self.assertEqual(arrays["cell_owner"].tolist(), [[0, -1], [-1, 1]])

    def test_closed_and_engineering_open_are_distinct(self):
        closed = self.build([[2, 0, 2]])
        opened = self.build([[2, 0, 2]], open_boundary_mask=np.array([[True, False, False]]))
        self.assertFalse(closed["arrays"]["node_open_boundary"].any())
        self.assertEqual(opened["arrays"]["node_open_level_m"].tolist(), [2])
        self.assertFalse(opened["metadata"]["natural_outlet_verified"])

    def test_flat_receiver_is_d4_nonascending_acyclic(self):
        result = self.build([[2, 2, 2, 1], [2, 2, 2, 0], [2, 2, 2, 1]])
        arrays = result["arrays"]
        bed = arrays["height_m"].ravel()
        for start in range(bed.size):
            seen = set()
            cell = start
            while arrays["receiver"][cell] >= 0:
                self.assertNotIn(cell, seen)
                seen.add(cell)
                downstream = int(arrays["receiver"][cell])
                row, column = divmod(cell, 4)
                next_row, next_column = divmod(downstream, 4)
                self.assertEqual(abs(row - next_row) + abs(column - next_column), 1)
                self.assertLessEqual(bed[downstream], bed[cell])
                cell = downstream
        self.assertGreater(int((bed[arrays["receiver"]] == bed).sum()), 0)

    def test_deterministic_fortran_order_and_rebuild_new_bed(self):
        height = np.array([[0., 2., 1., 4., 0.]])
        first = self.build(height)
        second = self.build(np.asfortranarray(height))
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        height[0, 1] = 0
        changed = self.build(height)
        self.assertNotEqual(first["identity_sha256"], changed["identity_sha256"])
        self.assertEqual(len(changed["arrays"]["node_parent"]), 3)

    def test_cold_read_external_pins_and_reject_mutation(self):
        result = self.build([[0, 2, 1]])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hierarchy.npz"
            save_basin_hierarchy(path, result)
            sha = file_sha256(path)
            with patch("terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy", side_effect=AssertionError("cold generation forbidden")):
                loaded = load_basin_hierarchy(path, expected_sha256=sha, expected_identity=result["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            with self.assertRaises(ValueError):
                load_basin_hierarchy(path, expected_sha256="0" * 64, expected_identity=result["identity_sha256"])
            with self.assertRaises(FileExistsError):
                save_basin_hierarchy(path, result)
            corrupted = dict(result, arrays=dict(result["arrays"]))
            corrupted["arrays"]["node_parent"] = np.array([-1, -1, -1])
            with self.assertRaises(ValueError):
                save_basin_hierarchy(Path(directory) / "bad.npz", corrupted)
            self.assertFalse((Path(directory) / "bad.npz").exists())

    def test_illegal_inputs_and_source_identity(self):
        for spacing in (0, -1, float("nan")):
            with self.assertRaises(ValueError):
                make_td_source([[1]], spacing_m=spacing)
        with self.assertRaises(ValueError):
            self.build([[float("nan")]])
        with self.assertRaises(ValueError):
            self.build(np.ones((3, 3)), open_boundary_mask=np.ones((3, 3), bool))
        source = make_td_source([[0]], spacing_m=1)
        source["identity_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            validate_td_source(source)

    def test_curves_match_independent_subtree_integral(self):
        result = self.build([[0, 2, 1, 4, 0], [5, 3, 6, 7, 8]])
        arrays = result["arrays"]
        parent = arrays["node_parent"]
        for node in range(len(parent)):
            selected = np.zeros(arrays["height_m"].shape, bool)
            for index in np.ndindex(selected.shape):
                owner = int(arrays["cell_owner"][index])
                while owner >= 0 and owner != node:
                    owner = int(parent[owner])
                selected[index] = owner == node
            lower = arrays["node_birth_m"][node]
            upper = arrays["node_upper_m"][node]
            if not np.isfinite(upper):
                upper = float(arrays["height_m"].max() + 2)
            for level in np.linspace(lower, upper, 7):
                expected = np.maximum(0, level - arrays["height_m"][selected]).sum()
                self.assertAlmostEqual(basin_volume_at_level(result, node, float(level)), expected)


if __name__ == "__main__":
    unittest.main()
