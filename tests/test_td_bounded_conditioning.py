import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_basin_breach import saddle_path_face_identity
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_overflow import _face_id
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_bounded_conditioning import (
    build_conditioning_candidates, load_conditioning, save_conditioning, validate_conditioning,
)
from terrain_pipeline.td_material_field import make_material_field
from terrain_pipeline.td_stable_spill_paths import SCHEMA, _digest


def fixture(*, height=None, protected=None, opened=None, thickness=4.0, paths=None):
    height = [[2., 2.01, 1.98, 1.94]] if height is None else height
    source = make_td_source(np.asarray(height), spacing_m=1., protected_mask=protected, open_boundary_mask=opened)
    hierarchy = build_basin_hierarchy(source)
    materials = make_material_field(source["arrays"]["height_m"].shape, origin_m_xz=(0, 0), spacing_m=1.,
        protected_mask=source["arrays"]["protected_mask"],
        parameters={"erodible_thickness_range_m": [thickness, thickness]})
    report = {"schema": SCHEMA, "source_identity_sha256": source["identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "topology_identity_sha256": "a" * 64,
              "event_identity_sha256": {"normal-24h": "b" * 64, "strong-6h": "c" * 64}, "paths": []}
    for path in [[0, 1, 2, 3]] if paths is None else paths:
        face = path[:2]
        face_index = hierarchy["arrays"]["face_cells"].tolist().index(face)
        face_id = _face_id(hierarchy, face_index)
        source_basin, destination = hierarchy["arrays"]["contribution_owner"].ravel()[face].tolist()
        face_identity = saddle_path_face_identity(source["arrays"]["height_m"], path,
            source_identity_sha256=source["identity_sha256"], topology_identity_sha256="a" * 64)
        request = {"case": "normal-24h", "face_id": face_id, "path_cell_ids": path,
            "source_identity_sha256": source["identity_sha256"], "topology_identity_sha256": "a" * 64,
            "hydro_identity_sha256": "b" * 64, "path_face_identity": face_identity,
            "routed_volume_m3": 10.,
            "hydro_face_evidence": {"hydro_identity_sha256": "b" * 64,
                                   "face_cell_ids": face, "outward_volume_m3": 10.},
            "downstream_anchor_evidence": {"topology_identity_sha256": "a" * 64,
                "source_basin_id": source_basin, "destination_basin_id": destination,
                "tail_cell_ids": [path[-1]], "engineering_open_boundary": False}}
        request["identity_sha256"] = _digest(request)
        record = {"status": "bounded_candidate_request", "rejection_reasons": [],
            "source_identity_sha256": source["identity_sha256"],
            "hierarchy_identity_sha256": hierarchy["identity_sha256"], "topology_identity_sha256": "a" * 64,
            "face_id": face_id, "face_cell_ids": face, "directed_face_cell_ids": face,
            "hierarchy_face_index": face_index, "path_cell_ids": path,
            "source_basin_id": source_basin, "destination_basin_id": destination,
            "sill_m": float(source["arrays"]["height_m"].ravel()[face].max()),
            "path_face_identity": face_identity, "bounded_candidate_requests": [request]}
        record["identity_sha256"] = _digest(record)
        report["paths"].append(record)
    report["identity_sha256"] = _digest(report)
    return source, hierarchy, materials, report


class BoundedConditioningTests(unittest.TestCase):
    def test_four_independent_beds_replay_minimal_cut_and_ordinary_only(self):
        inputs = fixture()
        candidates = build_conditioning_candidates(*inputs)
        self.assertEqual(set(candidates), {"baseline", "limited_fill", "limited_breach", "mixed"})
        np.testing.assert_array_equal(candidates["baseline"]["arrays"]["height_m"], inputs[0]["arrays"]["height_m"])
        np.testing.assert_allclose(candidates["limited_breach"]["arrays"]["height_m"], [[2., 1.999999, 1.98, 1.94]], rtol=0, atol=1e-12)
        np.testing.assert_allclose(candidates["limited_fill"]["arrays"]["height_m"], [[2.01, 2.01, 1.98, 1.94]], rtol=0, atol=1e-12)
        for name, bundle in candidates.items():
            self.assertEqual(bundle["identity_sha256"], build_conditioning_candidates(*inputs)[name]["identity_sha256"])
            self.assertTrue(validate_conditioning(bundle))
            for flag in ("natural", "hydraulic", "publishable"):
                self.assertIs(bundle["metadata"][flag], False)
            self.assertFalse(bundle["arrays"]["height_m"].flags.writeable)
        changed = copy.deepcopy(inputs[3])
        changed["event_identity_sha256"]["strong-6h"] = "d" * 64
        changed["identity_sha256"] = _digest({key: value for key, value in changed.items() if key != "identity_sha256"})
        others = build_conditioning_candidates(*inputs[:3], changed)
        for name in candidates:
            np.testing.assert_array_equal(candidates[name]["arrays"]["height_m"], others[name]["arrays"]["height_m"])

    def test_atomic_constraints_and_rejected_paths_never_change_original(self):
        for inputs, parameters, reason in (
            (fixture(thickness=.001), None, "insufficient_erodible_thickness"),
            (fixture(protected=np.array([[False, True, False, False]])), None, "protected_or_unknown_support"),
            (fixture(), {"min_slope": .1}, "downstream_anchor_requires_modification"),
        ):
            with self.subTest(reason=reason):
                bundle = build_conditioning_candidates(*inputs, parameters=parameters)["limited_breach"]
                np.testing.assert_array_equal(bundle["arrays"]["height_m"], inputs[0]["arrays"]["height_m"])
                self.assertEqual(bundle["metadata"]["rejected_treatments"][0]["rejection_reasons"], [reason])
        inputs = fixture()
        for parameters in ({"max_fill_m": .005}, {"max_fill_m3": .005}):
            bundle = build_conditioning_candidates(*inputs, parameters=parameters)["limited_fill"]
            self.assertFalse(bundle["metadata"]["accepted_treatments"])
            np.testing.assert_array_equal(bundle["arrays"]["height_m"], inputs[0]["arrays"]["height_m"])
        opened = fixture(opened=np.array([[True, False, False, True]]))
        alternatives = build_conditioning_candidates(*opened)
        self.assertEqual(alternatives["limited_fill"]["metadata"]["rejected_treatments"][0]["rejection_reasons"],
                         ["open_boundary_geometry_change"])
        for bundle in alternatives.values():
            self.assertTrue(np.all(bundle["arrays"]["delta_m"][bundle["arrays"]["open_boundary_mask"]] == 0))
        report = copy.deepcopy(inputs[3])
        report["paths"][0]["status"] = "rejected"
        record = report["paths"][0]
        record["identity_sha256"] = _digest({key: value for key, value in record.items() if key != "identity_sha256"})
        report["identity_sha256"] = _digest({key: value for key, value in report.items() if key != "identity_sha256"})
        self.assertFalse(build_conditioning_candidates(*inputs[:3], report)["limited_fill"]["metadata"]["accepted_treatments"])

    def test_cumulative_budget_conflicts_and_external_solid_ledger(self):
        inputs = fixture(height=[[2., 2.01, 1.98, 1.94, 10., 2., 2.01, 1.98, 1.94]],
                         paths=[[0, 1, 2, 3], [5, 6, 7, 8]])
        full = build_conditioning_candidates(*inputs)["limited_fill"]
        self.assertEqual(len(full["metadata"]["accepted_treatments"]), 2)
        bounded = build_conditioning_candidates(*inputs, parameters={"max_fill_m3": .015})["limited_fill"]
        self.assertEqual(len(bounded["metadata"]["accepted_treatments"]), 1)
        self.assertEqual(bounded["metadata"]["rejected_treatments"][0]["rejection_reasons"], ["global_geometry_budget_exceeded"])
        ledger = full["metadata"]["geometry_ledger"]
        self.assertAlmostEqual(ledger["fill_geometry_m3"], .02)
        self.assertAlmostEqual(ledger["external_initial_material_input_solid_m3"], .02 * .65)
        self.assertAlmostEqual(ledger["external_initial_material_input_kg"], .02 * .65 * 2650.)
        arrays = {name: values.copy() for name, values in full["arrays"].items()}
        metadata = copy.deepcopy(full["metadata"])
        metadata["accepted_treatments"].append(copy.deepcopy(metadata["accepted_treatments"][0]))
        forged = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
        with self.assertRaisesRegex(ValueError, "support"):
            validate_conditioning(forged)

    def test_standard_cold_io_external_pins_and_rehashed_geometry_forgery(self):
        bundle = build_conditioning_candidates(*fixture())["limited_breach"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "conditioning.npz"
            save_conditioning(path, bundle)
            with patch("terrain_pipeline.td_bounded_conditioning.build_conditioning_candidates", side_effect=AssertionError("cold generation forbidden")):
                loaded = load_conditioning(path, expected_sha256=file_sha256(path), expected_identity=bundle["identity_sha256"])
            self.assertEqual(loaded["identity_sha256"], bundle["identity_sha256"])
            with self.assertRaises(FileExistsError):
                save_conditioning(path, bundle)
            with self.assertRaises(ValueError):
                load_conditioning(path, expected_sha256="0" * 64, expected_identity=bundle["identity_sha256"])
        forged = copy.deepcopy(bundle)
        forged["arrays"]["height_m"][0, 2] -= .1
        forged["arrays"]["delta_m"] = forged["arrays"]["height_m"] - forged["arrays"]["original_height_m"]
        forged["identity_sha256"] = identity(forged["arrays"], forged["metadata"])
        with self.assertRaisesRegex(ValueError, "atomic treatment replay"):
            validate_conditioning(forged)


if __name__ == "__main__":
    unittest.main()
