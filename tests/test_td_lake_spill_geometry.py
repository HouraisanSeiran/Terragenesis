import copy
import json
import unittest

import numpy as np

from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_overflow import _boundary_faces, _face_id, _physical_faces
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_lake_spill_geometry import trace_engineering_outlet, trace_spill_connection


def fixture():
    bed = np.array([[2.0, 3.0, 6.0, 4.0, 1.0]])
    opened = np.array([[False, False, True, False, False]])
    hierarchy = build_basin_hierarchy(make_td_source(
        bed, spacing_m=2, origin_m_xz=(10, 20), open_boundary_mask=opened))
    owners = hierarchy["arrays"]["contribution_owner"].ravel()
    leaves = np.unique(owners)
    indices = {int(leaf): index for index, leaf in enumerate(leaves)}
    face = _physical_faces(hierarchy, leaves, indices)[0]
    boundary = _boundary_faces(hierarchy, leaves, indices)[0]
    return hierarchy, face, boundary, int(owners[0]), int(owners[-1])


class LakeSpillGeometryTests(unittest.TestCase):
    def test_actual_d4_uphill_lake_and_separate_downhill_support(self):
        hierarchy, face, _, left, right = fixture()
        original = hierarchy["arrays"]["height_m"].copy()
        result = trace_spill_connection(hierarchy, face, left, right, source_stage_m=6)
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["source_sinkcell"], 0)
        self.assertEqual(result["dest_sinkcell"], 4)
        wet = result["source_lake_approach"]
        self.assertEqual(wet["kind"], "sampled_submerged_lake_approach")
        self.assertEqual(wet["cell_ids"], [0, 1, 2])
        self.assertEqual(wet["xyz_m"], [[10, 2, 20], [12, 3, 20], [14, 6, 20]])
        self.assertTrue(wet["all_samples_stage_covered"])
        self.assertFalse(wet["all_samples_submerged"])
        self.assertFalse(wet["is_terrestrial_river"])
        self.assertEqual(result["cross_face"]["cell_ids"], [2, 3])
        self.assertEqual(result["cross_face"]["xyz_m"], [[14, 6, 20], [16, 4, 20]])
        self.assertEqual(result["downhill_terrain_approach"]["cell_ids"], [3, 4])
        reverse = trace_spill_connection(hierarchy, face, right, left, source_stage_m=6)
        self.assertEqual(reverse["status"], "accepted")
        self.assertEqual(reverse["source_lake_approach"]["cell_ids"], [4, 3])
        self.assertEqual(reverse["cross_face"]["cell_ids"], [3, 2])
        np.testing.assert_array_equal(hierarchy["arrays"]["height_m"], original)
        json.dumps(result, allow_nan=False)

    def test_refusals_and_exact_engineering_boundary(self):
        hierarchy, face, boundary, left, right = fixture()
        for case in ("stage", "protected", "invalid", "unknown", "face", "cycle", "owner", "budget"):
            with self.subTest(case=case):
                candidate = copy.deepcopy(hierarchy)
                candidate["arrays"] = {key: value.copy() for key, value in hierarchy["arrays"].items()}
                selected_face = dict(face)
                stage, budget = 6, 2048
                if case == "stage":
                    stage = 5
                elif case == "protected":
                    candidate["arrays"]["protected_mask"].ravel()[0] = True
                elif case == "invalid":
                    candidate["arrays"]["valid_mask"].ravel()[0] = False
                elif case == "unknown":
                    candidate["arrays"]["node_unknown_contact"][left] = True
                elif case == "face":
                    selected_face["face_id"] = _face_id(hierarchy, face["face_index"]) + "wrong"
                elif case == "cycle":
                    candidate["arrays"]["receiver"][0] = 0
                elif case == "owner":
                    candidate["arrays"]["contribution_owner"].ravel()[0] = right
                elif case == "budget":
                    budget = 4
                result = trace_spill_connection(candidate, selected_face, left, right,
                                                source_stage_m=stage, max_path_cells=budget)
                self.assertEqual(result["status"], "rejected")
                self.assertTrue(result["reason"])
                json.dumps(result, allow_nan=False)
        outlet = trace_engineering_outlet(hierarchy, boundary, source_stage_m=6)
        self.assertEqual(outlet["status"], "accepted")
        self.assertEqual(outlet["source_lake_approach"]["cell_ids"], [0, 1, 2])
        self.assertTrue(outlet["is_engineering"])
        self.assertFalse(outlet["is_sea_outlet"])
        for field, value in (("width_m", boundary["width_m"] + 1), ("sill_m", 7), ("cell_id", 3)):
            with self.subTest(boundary_field=field):
                altered = dict(boundary, **{field: value})
                self.assertEqual(trace_engineering_outlet(hierarchy, altered, source_stage_m=6)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
