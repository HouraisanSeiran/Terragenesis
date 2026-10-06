import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.td_basin_breach import load_saddle_breach
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_overflow import OverflowParameters, build_overflow_topology
from terrain_pipeline.td_basin_reception import _sha, build_basin_reception
from terrain_pipeline.td_basin_source import make_td_source
from terrain_pipeline.td_material_field import make_material_field
from terrain_pipeline.td_stable_spill_paths import (
    CASE_NAMES, _digest, build_stable_spill_paths, generate_bounded_candidates, trace_receiver_side,
)
from tools.prepare_td_stable_spill_paths import _json, load_fixed_inputs, prepare, verify_pins


def event_fixture(hierarchy, topology, forward, reverse):
    forward = np.asarray(forward, dtype=float)[:, None]
    reverse = np.asarray(reverse, dtype=float)[:, None]
    steps = len(forward)
    config = OverflowParameters(timestep_s=300., duration_s=300. * steps)
    leaves = len(topology["arrays"]["leaf_ids"])
    if leaves != 2 or len(topology["faces"]) != 1:
        raise ValueError("analytic fixture expects two basins and one physical face")
    supplied = np.tile(topology["arrays"]["leaf_area_m2"] *
                       config.baseflow_mm_per_day / 86_400_000. * 300., (steps, 1))
    net = forward - reverse
    basin_net = np.column_stack((-net[:, 0], net[:, 0]))
    water = np.full((steps + 1, leaves), 1e8)
    for step in range(steps):
        water[step + 1] = water[step] + supplied[step] + basin_net[step]
    residual = supplied + basin_net - np.diff(water, axis=0)
    arrays = {"rain_mm_h": np.zeros(steps), "input_volume_m3": supplied,
              "volume_m3": water, "face_forward_m3": forward, "face_reverse_m3": reverse,
              "face_net_m3": net, "face_volume_m3": forward + reverse,
              "stage_m": np.zeros_like(water), "basin_net_internal_m3": basin_net,
              "basin_gross_internal_m3": np.repeat(forward + reverse, leaves, axis=1),
              "basin_boundary_outflow_m3": np.zeros_like(supplied),
              "basin_balance_residual_m3": residual, "balance_residual_m3": residual.sum(axis=1),
              "spill_onset_step": np.array([0], dtype=np.int64),
              "engineering_boundary_outflow_m3": np.zeros((steps, 0))}
    metadata = {"schema": "td-original-bed-overflow-event-v2",
                "topology_identity_sha256": topology["identity_sha256"],
                "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
                "parameters": vars(config), "steps": steps, "timestep_s": 300., "duration_s": 300. * steps,
                "hydraulic_ready": False, "transient_converged": False,
                "natural_outlet_verified": False, "publishable": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def fixture(height=None, protected=None, forward=None, reverse=None):
    height = np.asarray([[2., 2.01, 1.98, 1.94]] if height is None else height)
    hierarchy = build_basin_hierarchy(make_td_source(height, spacing_m=1., protected_mask=protected))
    topology = build_overflow_topology(hierarchy)
    source_leaf = int(hierarchy["arrays"]["contribution_owner"].ravel()[0])
    forward_source = source_leaf == topology["faces"][0]["leaf_ids"][0]
    event = event_fixture(hierarchy, topology, ([1e6] * 5 if forward_source else [0.] * 5) if forward is None else forward,
                          ([0.] * 5 if forward_source else [1e6] * 5) if reverse is None else reverse)
    reception = build_basin_reception(topology, event, event, hierarchy)
    cases = [{"name": name, "reception": copy.deepcopy(reception),
              "selected_event": event, "reference_event": event} for name in CASE_NAMES]
    return hierarchy, topology, cases


def winding_hierarchy():
    return {"arrays": {"height_m": np.array([[0., 1., 2.], [5., 4., 3.]]),
                       "receiver": np.array([-1, 0, 1, 4, 5, 2]),
                       "contribution_owner": np.zeros((2, 3), dtype=np.int64),
                       "valid_mask": np.ones((2, 3), dtype=bool),
                       "protected_mask": np.zeros((2, 3), dtype=bool)},
            "metadata": {"spacing_m": 30.}}


class StableSpillPathTests(unittest.TestCase):
    def test_actual_saddle_orientation_and_two_receiver_chains(self):
        hierarchy, topology, cases = fixture()
        report = build_stable_spill_paths(hierarchy, topology, cases)
        record = report["paths"][0]
        self.assertEqual(record["path_cell_ids"], [0, 1, 2, 3])
        self.assertEqual(record["directed_face_cell_ids"], [0, 1])
        self.assertEqual(record["side_paths"][0]["cell_ids"], [0])
        self.assertEqual(record["side_paths"][1]["cell_ids"], [1, 2, 3])
        self.assertEqual(record["status"], "bounded_candidate_request")
        self.assertEqual(len(record["bounded_candidate_requests"]), 2)
        request = record["bounded_candidate_requests"][0]
        self.assertEqual(request["routed_volume_m3"], 5e6)
        self.assertEqual(request["wet_duration_s"], 1500.)
        self.assertEqual(request["hydro_face_evidence"]["face_cell_ids"], [0, 1])
        self.assertEqual(request["downstream_anchor_evidence"]["tail_cell_ids"], [3])
        for flag in ("hydraulic_ready", "publishable", "natural_outlet_verified", "continuous_fine_corridor_ready", "geometry_generated"):
            self.assertFalse(report[flag])

    def test_winding_receiver_is_not_replaced_by_straight_line(self):
        traced = trace_receiver_side(winding_hierarchy(), 3, 0)
        self.assertEqual(traced["cell_ids"], [3, 4, 5, 2, 1, 0])
        self.assertEqual(traced["length_m"], 150.)
        self.assertTrue(traced["complete"])

    def test_length_budget_retains_prefix_but_not_false_terminal(self):
        traced = trace_receiver_side(winding_hierarchy(), 3, 0, max_path_cells=3)
        self.assertEqual(traced["cell_ids"], [3, 4, 5])
        self.assertFalse(traced["complete"])
        self.assertIsNone(traced["terminal_cell_id"])
        self.assertIn("receiver_path_length_exceeds_budget", traced["rejection_reasons"])
        hierarchy, topology, cases = fixture()
        record = build_stable_spill_paths(hierarchy, topology, cases, max_path_cells=3)["paths"][0]
        self.assertIn("saddle_path_length_outside_budget", record["rejection_reasons"])
        self.assertFalse(record["bounded_candidate_requests"])

    def test_receiver_protection_unknown_owner_and_d4_rejections(self):
        mutations = [
            ("protected_receiver_path_cell", lambda arrays: arrays["protected_mask"].__setitem__((1, 1), True)),
            ("unknown_receiver_path_cell", lambda arrays: arrays["valid_mask"].__setitem__((1, 1), False)),
            ("receiver_leaves_face_basin", lambda arrays: arrays["contribution_owner"].__setitem__((1, 1), 1)),
            ("receiver_not_d4_adjacent", lambda arrays: arrays["receiver"].__setitem__(3, 1)),
            ("receiver_climbs_original_bed", lambda arrays: arrays["height_m"].__setitem__((1, 1), 6.)),
        ]
        for reason, mutate in mutations:
            with self.subTest(reason=reason):
                hierarchy = winding_hierarchy()
                mutate(hierarchy["arrays"])
                self.assertIn(reason, trace_receiver_side(hierarchy, 3, 0)["rejection_reasons"])

    def test_cycle_rejected_without_unbounded_walk(self):
        hierarchy = winding_hierarchy()
        hierarchy["arrays"]["height_m"][:] = 1.
        hierarchy["arrays"]["receiver"][4] = 3
        self.assertIn("receiver_cycle", trace_receiver_side(hierarchy, 3, 0)["rejection_reasons"])

    def test_protected_low_anchor_retained_as_failed_path(self):
        hierarchy = winding_hierarchy()
        hierarchy["arrays"]["protected_mask"][0, 0] = True
        record = trace_receiver_side(hierarchy, 3, 0)
        self.assertIn("protected_receiver_path_cell", record["rejection_reasons"])
        self.assertTrue(record["complete"])
        self.assertEqual(record["terminal_cell_id"], 0)

    def test_downstream_anchor_must_be_lower(self):
        hierarchy, topology, cases = fixture(height=[[1.94, 2.01, 1.98, 2.]])
        record = build_stable_spill_paths(hierarchy, topology, cases)["paths"][0]
        self.assertIn("downstream_anchor_not_lower_than_source_anchor", record["rejection_reasons"])

    def test_target_fill_is_rejected_without_modifying_baseline(self):
        hierarchy, topology, cases = fixture(height=[[2., 2.01, 1.90, 1.89]])
        baseline = hierarchy["arrays"]["height_m"].copy()
        record = build_stable_spill_paths(hierarchy, topology, cases)["paths"][0]
        self.assertIn("target_requires_unsourced_fill", record["rejection_reasons"])
        np.testing.assert_array_equal(hierarchy["arrays"]["height_m"], baseline)

    def test_ordinary_strong_direction_conflict_and_unstable_events_retained(self):
        hierarchy, topology, cases = fixture()
        original_event = cases[0]["selected_event"]
        reversed_event = event_fixture(hierarchy, topology, original_event["arrays"]["face_reverse_m3"][:, 0],
                                       original_event["arrays"]["face_forward_m3"][:, 0])
        cases[1].update(selected_event=reversed_event, reference_event=reversed_event,
                        reception=build_basin_reception(topology, reversed_event, reversed_event, hierarchy))
        record = build_stable_spill_paths(hierarchy, topology, cases)["paths"][0]
        self.assertIn("ordinary_strong_direction_conflict", record["rejection_reasons"])
        self.assertFalse(record["bounded_candidate_requests"])
        reversal = event_fixture(hierarchy, topology, [1., 1., 0., 0., 0.], [0., 0., 1., 1., 1.])
        cases[1].update(selected_event=reversal, reference_event=reversal,
                        reception=build_basin_reception(topology, reversal, reversal, hierarchy))
        record = build_stable_spill_paths(hierarchy, topology, cases)["paths"][0]
        self.assertIn("strong-6h:not_stable_reception", record["rejection_reasons"])
        self.assertFalse(record["bounded_candidate_requests"])

    def test_rehashed_forged_face_evidence_cannot_bypass_saved_events(self):
        hierarchy, topology, cases = fixture()
        for key, replacement in [("cell_ids", [0, 3]), ("stable_relationship", False), ("source_leaf_id", 99)]:
            with self.subTest(key=key):
                forged = copy.deepcopy(cases)
                reception = forged[0]["reception"]
                reception["faces"][0][key] = replacement
                reception.pop("identity_sha256")
                reception["identity_sha256"] = _sha(reception)
                with self.assertRaisesRegex(ValueError, "actual saved"):
                    build_stable_spill_paths(hierarchy, topology, forged)

    def test_identity_case_coverage_and_budget_rejections(self):
        hierarchy, topology, cases = fixture()
        with self.assertRaisesRegex(ValueError, "exactly once"):
            build_stable_spill_paths(hierarchy, topology, cases[:1])
        for maximum in (True, 2, 65):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                build_stable_spill_paths(hierarchy, topology, cases, max_path_cells=maximum)
        forged = copy.deepcopy(topology)
        forged["identity_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            build_stable_spill_paths(hierarchy, forged, cases)

    def test_real_breach_call_is_independent_and_rejections_preserve_baseline(self):
        hierarchy, topology, cases = fixture()
        report = build_stable_spill_paths(hierarchy, topology, cases)
        baseline = hierarchy["arrays"]["height_m"].copy()
        materials = make_material_field(baseline.shape, origin_m_xz=(0, 0), spacing_m=1.,
            parameters={"erodibility_range": [1., 1.], "weak_path_preference_range": [1., 1.],
                        "erodible_thickness_range_m": [4., 4.]})
        result = generate_bounded_candidates(report, hierarchy, materials)
        self.assertEqual(result["generation_calls"], 2)
        self.assertEqual([attempt["status"] for attempt in result["attempts"]], ["candidate", "candidate"])
        for candidate in result["candidates"]:
            np.testing.assert_array_equal(candidate["arrays"]["original_height_m"], baseline)
            self.assertFalse(candidate["metadata"]["hydrology_coupled_verified"])
        thin = make_material_field(baseline.shape, origin_m_xz=(0, 0), spacing_m=1.,
                                  parameters={"erodible_thickness_range_m": [.001, .001]})
        rejected = generate_bounded_candidates(report, hierarchy, thin)
        self.assertEqual([attempt["status"] for attempt in rejected["attempts"]], ["rejected", "rejected"])
        for candidate in rejected["candidates"]:
            np.testing.assert_array_equal(candidate["arrays"]["height_m"], baseline)
            self.assertIn("insufficient_erodible_thickness", candidate["metadata"]["rejection_reasons"])
        np.testing.assert_array_equal(hierarchy["arrays"]["height_m"], baseline)

    def test_candidate_call_failures_count_toward_budget(self):
        hierarchy, topology, cases = fixture()
        report = build_stable_spill_paths(hierarchy, topology, cases)
        materials = make_material_field((1, 4), origin_m_xz=(0, 0), spacing_m=1.)
        with patch("terrain_pipeline.td_stable_spill_paths.generate_saddle_breach", side_effect=ValueError("failed")) as generate:
            result = generate_bounded_candidates(report, hierarchy, materials, max_candidates=1)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result["generation_calls"], 1)
        self.assertEqual([attempt["status"] for attempt in result["attempts"]], ["failed", "not_attempted"])
        self.assertEqual(result["attempts"][0]["error"], "failed")
        for maximum in (True, -1, 9):
            with self.assertRaises(ValueError):
                generate_bounded_candidates(report, hierarchy, materials, max_candidates=maximum)

    def test_request_tampering_material_protection_and_overwrite_rejected(self):
        hierarchy, topology, cases = fixture()
        report = build_stable_spill_paths(hierarchy, topology, cases)
        materials = make_material_field((1, 4), origin_m_xz=(0, 0), spacing_m=1.)
        report["paths"][0]["bounded_candidate_requests"][0]["routed_volume_m3"] *= 2
        with self.assertRaisesRegex(ValueError, "report identity"):
            generate_bounded_candidates(report, hierarchy, materials)
        report = build_stable_spill_paths(hierarchy, topology, cases)
        different = make_material_field((1, 4), origin_m_xz=(0, 0), spacing_m=1.,
                                        protected_mask=np.array([[True, False, False, False]]))
        with self.assertRaisesRegex(ValueError, "protection"):
            generate_bounded_candidates(report, hierarchy, different)
        with tempfile.TemporaryDirectory() as temporary, patch("tools.prepare_td_stable_spill_paths.load_fixed_inputs") as load:
            with self.assertRaises(FileExistsError):
                prepare(Path(temporary))
            load.assert_not_called()

    def test_material_coordinates_and_rehashed_wrong_request_identity_rejected(self):
        hierarchy, topology, cases = fixture()
        report = build_stable_spill_paths(hierarchy, topology, cases)
        different = make_material_field((1, 4), origin_m_xz=(30, 0), spacing_m=1.)
        with self.assertRaisesRegex(ValueError, "material grid"):
            generate_bounded_candidates(report, hierarchy, different)
        material = make_material_field((1, 4), origin_m_xz=(0, 0), spacing_m=1.)
        request = report["paths"][0]["bounded_candidate_requests"][0]
        request["hydro_identity_sha256"] = "f" * 64
        request["identity_sha256"] = _digest({key: value for key, value in request.items() if key != "identity_sha256"})
        report["identity_sha256"] = _digest({key: value for key, value in report.items() if key != "identity_sha256"})
        with self.assertRaisesRegex(ValueError, "request evidence identity"):
            generate_bounded_candidates(report, hierarchy, material)

    def test_hash_duplicate_key_and_source_change_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.json"
            path.write_text('{"name":1,"name":2}', encoding="utf-8")
            digest = file_sha256(path)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                _json(path, digest)
            with self.assertRaisesRegex(ValueError, "hash"):
                _json(path, "0" * 64)
            path.write_text('{"name":1}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"):
                verify_pins([{"path": str(path), "sha256": digest}])

    def test_runner_saves_new_candidates_and_cold_loads_failed_baseline(self):
        hierarchy, topology, cases = fixture()
        inputs = {"hierarchy": hierarchy, "topology": topology, "cases": cases, "pins": []}
        thin = make_material_field((1, 4), origin_m_xz=(0, 0), spacing_m=1.,
                                  parameters={"erodible_thickness_range_m": [.001, .001]})
        with tempfile.TemporaryDirectory() as temporary, patch("tools.prepare_td_stable_spill_paths.load_fixed_inputs", return_value=inputs), \
             patch("tools.prepare_td_stable_spill_paths.make_material_field", return_value=thin):
            output = Path(temporary) / "new-candidates"
            report = prepare(output)
            requests = json.loads((output / "requests.json").read_text(encoding="utf-8"))
            self.assertEqual(report["bounded_request_count"], 2)
            self.assertEqual(requests["identity_sha256"], report["request_report_identity_sha256"])
            self.assertEqual(report["candidate_status_counts"], {"rejected": 2})
            for attempt in report["candidate_attempts"]:
                pin = attempt["artifact"]
                with patch("terrain_pipeline.td_basin_breach.generate_saddle_breach", side_effect=AssertionError("cold generation forbidden")):
                    saved = load_saddle_breach(output / pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
                self.assertEqual(saved["metadata"]["status"], attempt["status"])
                np.testing.assert_array_equal(saved["arrays"]["original_height_m"], hierarchy["arrays"]["height_m"])
                if attempt["status"] == "rejected":
                    np.testing.assert_array_equal(saved["arrays"]["height_m"], hierarchy["arrays"]["height_m"])
            self.assertTrue((output / "index.json").is_file())

    def test_runner_rejects_new_output_inside_frozen_input_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            inputs = {"pins": [{"path": str(parent / "original.npz")}]}
            with patch("tools.prepare_td_stable_spill_paths.load_fixed_inputs", return_value=inputs):
                with self.assertRaisesRegex(ValueError, "frozen input"):
                    prepare(parent / "forbidden-new-output")
            self.assertFalse((parent / "forbidden-new-output").exists())


class FixedStableSpillColdReadTests(unittest.TestCase):
    def test_actual_pinned_reception_paths_without_solver_or_baseline_mutation(self):
        with patch("terrain_pipeline.td_basin_hierarchy.build_basin_hierarchy", side_effect=AssertionError("cold hierarchy generation forbidden")), \
             patch("terrain_pipeline.td_basin_overflow_radau.simulate_radau_overflow", side_effect=AssertionError("cold solver forbidden")):
            inputs = load_fixed_inputs()
            baseline = inputs["hierarchy"]["arrays"]["height_m"].copy()
            report = build_stable_spill_paths(inputs["hierarchy"], inputs["topology"], inputs["cases"])
        self.assertEqual(len(report["paths"]), 2921)
        self.assertEqual(sum(path["status"] == "bounded_candidate_request" for path in report["paths"]), 503)
        columns = baseline.shape[1]
        for path in report["paths"]:
            for side in path["side_paths"]:
                cells = side["cell_ids"]
                for first, second in zip(cells, cells[1:]):
                    self.assertEqual(int(inputs["hierarchy"]["arrays"]["receiver"][first]), second)
                    self.assertEqual(abs(first // columns - second // columns) + abs(first % columns - second % columns), 1)
            for request in path["bounded_candidate_requests"]:
                self.assertLessEqual(len(request["path_cell_ids"]), 64)
                self.assertTrue(all(face["stable_relationship"] for face in path["event_evidence"].values()))
                self.assertIn(request["hydro_face_evidence"]["face_cell_ids"],
                              [request["path_cell_ids"][index:index + 2] for index in range(len(request["path_cell_ids"]) - 1)])
        np.testing.assert_array_equal(inputs["hierarchy"]["arrays"]["height_m"], baseline)


if __name__ == "__main__":
    unittest.main()
