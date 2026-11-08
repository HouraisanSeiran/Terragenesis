import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import numpy as np

from terrain_pipeline.hydrology_detail import DetailBudget, derive_detail, _steepest_receivers, save_detail, select_key_windows
from terrain_pipeline.channel_geometry import derive_continuous_bed, frozen_window_profiles, select_frozen_window_component, split_frozen_window_component, audit_frozen_window_seams, audit_saved_continuous_bed
from terrain_pipeline.hydrology_detail_conditioning import make_frozen_plan_factory, ResourcePhysicalTerrainDiffusionBackend
from diffusion.physical_config import PhysicalGenerationConfig
from diffusion.geography_physical import make_physical_map_factory
from terrain_pipeline.td_source import CanonicalTDSource, load_canonical_window, _hydrology_td_digest as _digest
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field, stage_fixed_transform


class DetailTests(unittest.TestCase):
    def test_fixed_shared_face_protection_is_distance_bounded_and_identified(self):
        plan = self.fixture()
        raw = plan["height_m"].copy()
        result = derive_detail(plan, raw, origin_xz_m=[0, 0], spacing_m=30.,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                            "archive_sha256": "a" * 64}, shared_boundary_protection_m=60.)
        protected = result["arrays"]["shared_boundary_protected"]
        self.assertTrue(protected[0, 4])
        self.assertTrue(protected[0, 6])
        self.assertFalse(protected[0, 7])
        self.assertFalse(protected[8, 4])
        self.assertEqual(result["metadata"]["shared_boundary_protection"]["width_m"], 60.)
        self.assertNotEqual(result["metadata"]["identity"], self.derive(plan, raw)["metadata"]["identity"])

    def test_owned_d8_support_keeps_complete_core_and_rejects_holes(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        raw = np.ones((9,9))*100
        owned = np.zeros((9,9),bool)
        owned[2:-2,2:-2] = True
        kwargs = {"origin_xz_m":[0,0],"spacing_m":30.,
                  "raw_provenance":{"artifact_kind":"terrain_diffusion_output","td_inference_run":True,"archive_sha256":"a"*64},
                  "window_kind":"ridge"}
        result = derive_detail(plan,raw,d8_owned_mask=owned,**kwargs)
        self.assertIn("actual_d8_has_unplanned_interior_sinks",result["metadata"]["rejection_reasons"])
        np.testing.assert_array_equal(result["arrays"]["d8_owned_mask"],owned)
        self.assertEqual(result["metadata"]["d8_boundary_halo_cells"],2)
        owned[4,4] = False
        with self.assertRaisesRegex(ValueError,"genuine two-cell"):
            derive_detail(plan,raw,d8_owned_mask=owned,**kwargs)

    def fixture(self):
        height = 100.0 - np.indices((9, 9))[1].astype(float)
        owner = np.zeros((9, 9), dtype=np.int32)
        owner[:, 5:] = 1
        return {"seed": 1, "identity_sha256": "b" * 64, "origin_xz_m": [0, 0], "spacing_m": 30.0,
                "height_m": height, "original_height_m": height.copy(),
                "owner_domain_id": owner, "ocean_mask": np.zeros((9, 9), bool),
                "receiver": np.full((9, 9), -1, dtype=np.int64),
                "domains": [{"terminal_indices": [80], "lake_terminal_index": 80}],
                "shared_boundary_edges": np.array([[4, 5]])}

    def derive(self, plan, raw, origin=[0, 0]):
        return derive_detail(plan, raw, origin_xz_m=origin, spacing_m=30.0,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                            "archive_sha256": "a" * 64}, window_kind="ridge")

    def test_actual_steepest_descent_crossing_refused_and_raw_preserved(self):
        plan = self.fixture()
        raw = plan["height_m"].copy()
        result = self.derive(plan, raw)
        self.assertIn("actual_d8_crosses_frozen_domain", result["metadata"]["rejection_reasons"])
        np.testing.assert_array_equal(result["arrays"]["original_td_m"], raw)
        np.testing.assert_array_equal(raw, plan["height_m"])
        self.assertFalse(result["metadata"]["publishable"])

    def test_global_macro_formula_overlap_and_order_independent(self):
        plan = self.fixture()
        plan["height_m"] = plan["height_m"] + np.indices((9, 9))[0] * 0.2
        first = self.derive(plan, plan["original_height_m"][:7, :7])
        second = self.derive(plan, plan["original_height_m"][2:, 2:], [60, 60])
        np.testing.assert_array_equal(first["arrays"]["derived_height_m"][2:, 2:], second["arrays"]["derived_height_m"][:5, :5])

    def test_flats_are_sinks_not_hidden_fill(self):
        self.assertTrue(np.all(_steepest_receivers(np.ones((5, 5)), 30) == -1))
        plan = self.fixture()
        result = self.derive(plan, np.ones((9, 9)) * 100)
        self.assertIn("actual_d8_has_unplanned_interior_sinks", result["metadata"]["rejection_reasons"])

    def test_global_height_map_preserves_sea_stage_and_strict_downhill(self):
        stage = 526.2816108585628
        heights = np.r_[-20.0, 0.0, np.linspace(0.01, stage - 0.01, 1000), stage, 800.0]
        mapped = stage_fixed_transform(heights, stage)
        self.assertTrue(np.all(np.diff(mapped) > 0))
        np.testing.assert_array_equal(mapped[[0, 1, -2, -1]], heights[[0, 1, -2, -1]])
        self.assertLess(np.max(np.diff(mapped) / np.diff(heights)), 7.0)
        # Mapping the continuous height preserves the exact original coastline.
        np.testing.assert_array_equal(stage_fixed_transform(np.array([-0.1, 0, 0.1]), stage) == 0, [False, True, False])

    def test_continuous_fan_shared_faces_and_overlap_independent_of_query(self):
        plan = self.fixture()
        x, z = np.meshgrid(np.linspace(2, 6, 49), np.linspace(2, 6, 49))
        first = continuous_macro_field(plan, x, z)
        second = continuous_macro_field(plan, x[9:37, 12:40], z[9:37, 12:40])
        np.testing.assert_array_equal(second, first[9:37, 12:40])
        # Both owner sides approach one shared crest, including cell corners.
        tangent = np.linspace(2, 6, 49).reshape(7, 7)
        left = continuous_macro_field(plan, np.full((7, 7), 4.5 - 1e-9), tangent)
        right = continuous_macro_field(plan, np.full((7, 7), 4.5 + 1e-9), tangent)
        np.testing.assert_allclose(left, right, atol=1e-7, rtol=0)

    def test_shore_does_not_require_river_but_requires_connected_water_evidence(self):
        plan = self.fixture()
        raw = plan["height_m"].copy()
        result = derive_detail(plan, raw, origin_xz_m=[0, 0], spacing_m=30,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                            "archive_sha256": "a" * 64}, window_kind="lake_shore")
        reasons = result["metadata"]["rejection_reasons"]
        self.assertNotIn("no_explicit_frozen_river_in_window", reasons)
        self.assertNotIn("continuous_fine_bed_not_certified", reasons)
        self.assertIn("continuous_connected_lake_shore_not_certified", reasons)

    def test_canonical_candidate_consumes_actual_fine_bed_without_v4_output(self):
        from tools.prepare_hydrology_domains import prepare_global_fine_beds

        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["frozen_td_lowpass_m"] = plan["height_m"].copy()
        plan["river_mask"] = np.zeros((9, 9), bool)
        plan["river_mask"][4, :-1] = True
        plan["receiver"][4, :-1] = np.arange(37, 45)
        detail = derive_detail(plan, plan["height_m"], origin_xz_m=[0, 0], spacing_m=30,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                            "archive_sha256": "a" * 64}, window_kind="river")
        with TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "river").mkdir()
            save_detail(output / "river" / "river-canonical-projection-v3-detail-v3-assessment-v2.npz", detail)
            reports = prepare_global_fine_beds(plan, output, canonical_projection=True)
            river = next(report for report in reports if report["window_kind"] == "river")
            self.assertTrue(river["independent_geometry_audit"]["accepted"])
            self.assertTrue(river["local_example_compatible"])
            self.assertLess(river["ledger"]["local_max_cut_m"], 4)
            self.assertTrue((output / "river" / "river-canonical-projection-v3-detail-v3-assessment-v2-continuous-fine-bed.npz").exists())
            self.assertFalse(list(output.rglob("*global-residual-v4*")))

    def test_registered_wet_bed_sink_is_allowed_but_not_an_open_river(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["river_mask"] = np.zeros((9, 9), bool)
        plan["river_mask"][4, :-1] = True
        plan["receiver"][4, :-1] = np.arange(37, 45)
        candidate = plan["height_m"].copy()
        candidate[4, 4] = 80
        result = derive_detail(plan, plan["height_m"], origin_xz_m=[0, 0], spacing_m=30,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True, "archive_sha256": "a" * 64},
            window_kind="river", candidate_height_m=candidate,
            candidate_provenance={"artifact_kind": "derived_terrain_diffusion_macro_geometry", "td_inference_run": False,
                                  "parent_archive_sha256": "a" * 64},
            lake_support={"connected_wet_mask": np.ones((9, 9), bool), "level_m": 101,
                          "coarse_basin_mask_sha256": "c" * 64})
        self.assertEqual(result["metadata"]["unplanned_interior_sink_count"], 0)
        self.assertEqual(result["metadata"]["non_downhill_channel_steps"], 0)
        self.assertIn("frozen_river_component_is_submerged_in_verified_lake", result["metadata"]["rejection_reasons"])

    def test_open_river_and_confluence_selection_excludes_highest_stage_wet_lake(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["river_mask"] = np.zeros((9, 9), bool)
        for first, second in ((10, 11), (23, 33), (41, 33), (33, 34), (34, 35)):
            plan["river_mask"].ravel()[first] = True
            plan["receiver"].ravel()[first] = second
        old = select_key_windows(plan)
        self.assertEqual(next(window for window in old if window["kind"] == "confluence")["coarse_cell"], 33)
        corrected = select_key_windows(plan, lake_level_m=95, lake_mask=np.ones((9, 9), bool))
        ordinary = next(window for window in corrected if window["kind"] == "river")
        self.assertEqual(ordinary["selection_edge_cell_ids"], [10, 11])
        self.assertEqual(next(window for window in corrected if window["kind"] == "confluence")["status"], "missing_planned_location")

    def test_budget_refuses_instead_of_clamping_macro(self):
        plan = self.fixture()
        plan["height_m"] += 90
        result = self.derive(plan, plan["original_height_m"])
        self.assertIn("macro_max_abs_m_exceeded", result["metadata"]["rejection_reasons"])
        self.assertEqual(result["arrays"]["macro_delta_m"].max(), 90)
        with self.assertRaises(ValueError):
            DetailBudget(channel_max_cut_m=4.1)

    def test_entire_frozen_path_uses_terrain_following_cut_and_preserves_linear_diagnostic(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["river_mask"] = np.zeros((9, 9), bool)
        plan["river_mask"][4, 0] = True
        plan["receiver"][4, 0] = 44
        candidate = plan["height_m"] + 10
        result = derive_detail(plan, plan["height_m"], origin_xz_m=[0, 0], spacing_m=30,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True, "archive_sha256": "a" * 64},
            candidate_height_m=candidate, candidate_provenance={"artifact_kind": "derived_terrain_diffusion_macro_geometry",
                "td_inference_run": False, "parent_archive_sha256": "a" * 64}, window_kind="river")
        ledger = result["metadata"]["ledger"]
        self.assertAlmostEqual(ledger["linear_coarse_reference_required_cut_m"], 10)
        self.assertAlmostEqual(ledger["required_channel_cut_m"], 0.5)
        self.assertNotIn("required_channel_cut_exceeds_4m", result["metadata"]["rejection_reasons"])
        self.assertIn("continuous_fine_bed_not_certified", result["metadata"]["rejection_reasons"])
        candidate[4, 4] += 8
        profiles = frozen_window_profiles(plan, candidate, [0, 0], 30)
        self.assertGreater(max(np.max(profile["source_m"] - profile["bed_m"]) for profile in profiles), 4)
        rejected = derive_detail(plan, plan["height_m"], origin_xz_m=[0, 0], spacing_m=30,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True, "archive_sha256": "a" * 64},
            candidate_height_m=candidate, candidate_provenance={"artifact_kind": "derived_terrain_diffusion_macro_geometry",
                "td_inference_run": False, "parent_archive_sha256": "a" * 64}, window_kind="river")
        self.assertIn("required_channel_cut_exceeds_4m", rejected["metadata"]["rejection_reasons"])
        self.assertGreater(rejected["metadata"]["continuous_source_non_downhill_channel_steps"], 0)

    def test_full_window_subdivisions_share_one_profile_and_keep_coarse_edge_coverage_honest(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["river_mask"] = np.zeros((9, 9), bool)
        plan["river_mask"][4, 0] = True
        plan["receiver"][4, 0] = 44
        result = self.derive(plan, plan["height_m"])
        window = {"kind": "river", "selection_edge_cell_ids": [36, 44], "origin_xz_m": [30, 90], "shape": [3, 7]}
        spec = select_frozen_window_component(plan, result, window, width_m=4, maximum_segment_length_m=60)
        pieces = split_frozen_window_component(spec)
        self.assertEqual(len(pieces), 3)
        self.assertFalse(spec["coverage"]["entire_coarse_edge_covered"])
        self.assertEqual(spec["coverage"]["represented_length_m"], 180)
        for first, second in zip(pieces[:-1], pieces[1:]):
            self.assertEqual(first["bed_target_m"][-1], second["bed_target_m"][0])
            self.assertEqual(first["centerline_profile"]["bed_m"][-1], second["centerline_profile"]["bed_m"][0])
        self.assertFalse(audit_frozen_window_seams([], spec)["accepted"])
        beds = [derive_continuous_bed(result, piece["points_xz_m"], piece["receiver"], piece["width_m"],
            piece["bed_target_m"], frozen_plan=plan, node_source_edges=piece["node_source_edges"],
            node_edge_fractions=piece["node_edge_fractions"], centerline_profile=piece["centerline_profile"])
            for piece in pieces]
        self.assertTrue(all(bed.get("arrays") for bed in beds), beds)
        seam_audit = audit_frozen_window_seams(beds, spec)
        json.dumps(seam_audit, allow_nan=False)
        self.assertTrue(seam_audit["accepted"], seam_audit)
        self.assertGreater(seam_audit["full_width_seam_samples"], 18)
        self.assertTrue(seam_audit["continuous_affine_trace_verified"])
        beds[1]["arrays"]["bed_elevation_m"] += 0.1
        failed_audit = audit_frozen_window_seams(beds, spec)
        json.dumps(failed_audit, allow_nan=False)
        self.assertFalse(failed_audit["accepted"])

    def test_rounded_native_probe_does_not_reject_a_continuously_descending_frozen_line(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["river_mask"] = np.zeros((9, 9), bool)
        plan["river_mask"][4, 0] = True
        plan["receiver"][4, 0] = 44
        raw = plan["height_m"][:7].copy()
        candidate = raw.copy()
        bump = np.sin(np.linspace(0, np.pi, 9))
        candidate[3] -= 6 * bump
        candidate[4] += 4 * bump
        result = derive_detail(plan, raw, origin_xz_m=[0, 12], spacing_m=30,
            raw_provenance={"artifact_kind": "terrain_diffusion_output", "td_inference_run": True, "archive_sha256": "a" * 64},
            candidate_height_m=candidate, candidate_provenance={"artifact_kind": "derived_terrain_diffusion_macro_geometry",
                "td_inference_run": False, "parent_archive_sha256": "a" * 64}, window_kind="river")
        meta = result["metadata"]
        self.assertGreater(meta["native_raster_non_downhill_channel_steps"], 0)
        self.assertEqual(meta["continuous_source_non_downhill_channel_steps"], 0)
        self.assertEqual(meta["non_downhill_channel_steps"], 0)
        self.assertAlmostEqual(meta["ledger"]["required_channel_cut_m"], 0.5)
        self.assertNotIn("frozen_river_path_not_strictly_downhill", meta["rejection_reasons"])
        self.assertIn("continuous_fine_bed_not_certified", meta["rejection_reasons"])

    def test_full_window_profiles_couple_frozen_confluence_node_beds(self):
        plan = self.fixture()
        plan["river_mask"] = np.zeros((9, 9), bool)
        for first, second in ((36, 40), (31, 40), (40, 44)):
            plan["river_mask"].ravel()[first] = True
            plan["receiver"].ravel()[first] = second
        height = plan["height_m"].copy()
        height[3, 4] = 90
        profiles = frozen_window_profiles(plan, height, [0, 0], 30)
        incoming = [profile["bed_m"][-1] for profile in profiles if profile["source_edge"][1] == 40]
        outgoing = next(profile["bed_m"][0] for profile in profiles if profile["source_edge"][0] == 40)
        np.testing.assert_allclose(incoming, outgoing, atol=0, rtol=0)

    def test_continuous_bed_reuses_finite_width_solver_on_actual_parent(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["receiver"][3, 1] = 29
        plan["river_mask"] = np.zeros((9, 9), bool)
        plan["river_mask"][3, 1] = True
        result = self.derive(plan, plan["original_height_m"])
        points = np.array([[30.0, 90.0], [50.0, 90.0]])
        target = np.array([98.5, 97.8])
        bed = derive_continuous_bed(result, points, np.array([1, -1]), np.array([4.0, 4.0]), target,
            frozen_plan=plan, node_source_edges=np.array([[28, 29], [28, 29]]), node_edge_fractions=np.array([0.0, 2 / 3]))
        self.assertEqual(bed["status"], "local_continuous_geometry_global_unverified")
        self.assertLessEqual(bed["arrays"]["local_cut_m"].max(), 4.0)
        self.assertTrue(bed["closure"]["transverse_bed_coupling"])
        self.assertFalse(bed["publishable"])

    def test_center_lowest_contract_rejects_tilted_old_bottom_and_solves_actual_reconnecting_channel(self):
        plan = self.fixture()
        plan["owner_domain_id"][:] = 0
        plan["height_m"] += np.indices((9, 9))[0] * 0.9
        plan["original_height_m"] = plan["height_m"].copy()
        plan["receiver"][3, 1] = 29
        plan["river_mask"] = np.zeros((9, 9), bool)
        plan["river_mask"][3, 1] = True
        detail = self.derive(plan, plan["original_height_m"])
        points = np.array([[30.0, 90.0], [50.0, 90.0]])
        target = np.array([101.2, 100.5])
        kwargs = {"frozen_plan": plan, "node_source_edges": np.array([[28, 29], [28, 29]]),
                  "node_edge_fractions": np.array([0.0, 2 / 3])}
        old = derive_continuous_bed(detail, points, np.array([1, -1]), np.array([4., 4.]), target, **kwargs)
        self.assertTrue(old.get("arrays"), old.get("reason"))
        cold = audit_saved_continuous_bed(old, detail)
        self.assertFalse(cold["accepted"])
        self.assertGreater(cold["center_minimum_max_residual_m"], 0.01)
        new = derive_continuous_bed(detail, points, np.array([1, -1]), np.array([4., 4.]), target,
                                    center_lowest=True, **kwargs)
        self.assertTrue(new.get("arrays"), new.get("reason"))
        self.assertTrue(new["independent_geometry_audit"]["accepted"])
        self.assertEqual(new["independent_geometry_audit"]["unreconnected_bank_sections"], 0)
        self.assertLessEqual(new["independent_geometry_audit"]["center_minimum_max_residual_m"], 1e-6)
        self.assertLessEqual(new["ledger"]["local_max_cut_m"], 4)
        self.assertEqual(new["algorithm"], "frozen-continuous-bed-v4-center-lowest")
        json.dumps(new["independent_geometry_audit"], allow_nan=False)

    def test_full_window_sidecar_confluence_preserves_branches_and_rejects_sloping_floor_defects(self):
        from dataclasses import asdict
        from tests.test_hydrology_detail_tributaries import fixture
        from terrain_pipeline.hydrology_detail_tributaries import freeze_local_tributary_confluence
        plan = fixture()
        plan["spacing_m"] = 40.0
        parent_receiver, parent_river = plan["receiver"].copy(), plan["river_mask"].copy()
        lake = np.zeros((4, 4), bool)
        sidecar = freeze_local_tributary_confluence(plan, junction_id=5, incoming_ids=[0, 1],
                                                   highest_lake_level_m=4, lake_mask=lake)
        z, x = np.mgrid[:17, :17]
        height = 100 - (x * 10 - 20) * 0.1 - (z * 10 - 20) * 0.1
        detail = {"arrays": {"derived_height_m": height, "original_td_m": height.copy(),
            "owner_domain_id": np.zeros(height.shape, int), "ocean_mask": np.zeros(height.shape, bool),
            "shared_boundary_protected": np.zeros(height.shape, bool)},
            "metadata": {"origin_xz_m": [-20, -20], "spacing_m": 10., "identity": "b" * 64,
                         "plan_identity": plan["identity_sha256"], "budget": asdict(DetailBudget())}}
        window = {"kind": "confluence", "coarse_cell": 5, "origin_xz_m": [0, 0], "shape": [9, 9],
                  "declared_source_edge_cell_ids": [[0, 5], [1, 5], [5, 6]]}
        kwargs = {"tributary_declaration": sidecar, "highest_lake_level_m": 4, "lake_mask": lake}
        spec = select_frozen_window_component(plan, detail, window, width_m=4,
            maximum_segment_length_m=40, junction_length_m=30, **kwargs)
        pieces = split_frozen_window_component(spec)
        central = [piece for piece in pieces if piece["junction_piece"]]
        self.assertEqual(len(central), 1)
        self.assertEqual(sum(node >= 0 for node in central[0]["receiver"]), 3)
        self.assertEqual(set(tuple(record["source_edge"]) for record in spec["coverage"]["source_edges"]),
                         {(0, 5), (1, 5), (5, 6)})
        np.testing.assert_array_equal(parent_receiver, plan["receiver"])
        np.testing.assert_array_equal(parent_river, plan["river_mask"])
        beds = [derive_continuous_bed(detail, piece["points_xz_m"], piece["receiver"], piece["width_m"],
            piece["bed_target_m"], frozen_plan=plan, node_source_edges=piece["node_source_edges"],
            node_edge_fractions=piece["node_edge_fractions"], centerline_profile=piece["centerline_profile"],
            center_lowest=True, **kwargs)
            for piece in pieces]
        rejected = [bed for bed in beds if not bed.get("arrays")]
        self.assertTrue(rejected)
        for bed in rejected:
            self.assertEqual(bed["reason"], "independent_continuous_bed_audit_failed")
            self.assertLessEqual(bed["audit"]["maximum_cut_m"], 4)
            self.assertGreater(bed["audit"]["center_minimum_max_residual_m"], 0.01)
        self.assertGreater(rejected[0]["audit"]["unreconnected_bank_sections"], 0)
        for piece, old in zip(pieces, beds):
            if old.get("arrays") or piece["junction_piece"]:
                continue
            repaired = derive_continuous_bed(detail, piece["points_xz_m"], piece["receiver"], piece["width_m"],
                piece["bed_target_m"], frozen_plan=plan, node_source_edges=piece["node_source_edges"],
                node_edge_fractions=piece["node_edge_fractions"], centerline_profile=piece["centerline_profile"],
                center_lowest=True, continuous_center_lowest=True, **kwargs)
            self.assertTrue(repaired.get("arrays"), repaired)
            self.assertLessEqual(repaired["independent_geometry_audit"]["continuous_center_floor_max_residual_m"], 1e-6)
            self.assertEqual(repaired["algorithm"], "frozen-continuous-bed-v5-continuous-center-floor")
            self.assertTrue(audit_saved_continuous_bed(repaired, detail)["accepted"])
        audit = audit_frozen_window_seams(beds, spec)
        self.assertFalse(audit["accepted"])
        self.assertEqual(audit["reason"], "full_window_mesh_coverage_incomplete")
        json.dumps(audit, allow_nan=False)

    def test_observer_includes_explicit_subthreshold_sidecar_without_changing_parent(self):
        from tests.test_hydrology_detail_tributaries import fixture
        from terrain_pipeline.hydrology_detail_tributaries import freeze_local_tributary_confluence
        plan = fixture()
        plan["original_height_m"] = plan["height_m"].copy()
        plan["shared_boundary_edges"] = np.empty((0, 2), int)
        lake = np.zeros((4, 4), bool)
        sidecar = freeze_local_tributary_confluence(plan, junction_id=5, incoming_ids=[0, 1],
                                                  highest_lake_level_m=4, lake_mask=lake)
        raw = plan["height_m"].copy()
        provenance = {"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                      "archive_sha256": "a" * 64}
        before = derive_detail(plan, raw, origin_xz_m=plan["origin_xz_m"], spacing_m=plan["spacing_m"],
                               raw_provenance=provenance)
        river = plan["river_mask"].copy()
        observed = derive_detail(plan, raw, origin_xz_m=plan["origin_xz_m"], spacing_m=plan["spacing_m"],
            raw_provenance=provenance, tributary_declaration=sidecar, highest_lake_level_m=4, lake_mask=lake)
        old_edges = {tuple(record["source_edge"]) for record in before["metadata"]["represented_frozen_edge_profiles"]}
        new_edges = {tuple(record["source_edge"]) for record in observed["metadata"]["represented_frozen_edge_profiles"]}
        self.assertNotIn((0, 5), old_edges)
        self.assertTrue({(0, 5), (1, 5), (5, 6)} <= new_edges)
        self.assertEqual(observed["metadata"]["local_tributary_sidecar_identity"], sidecar["identity_sha256"])
        np.testing.assert_array_equal(river, plan["river_mask"])

    def test_condition_factory_only_changes_real_elevation_channel(self):
        plan = self.fixture()
        config = PhysicalGenerationConfig()
        plan["spacing_m"] = config.conditioning_spacing_m
        plan["height_m"] += 20.0
        physical = make_physical_map_factory(1, config).sample_raw(1, 1, 4, 4)
        planned = make_frozen_plan_factory(1, config, plan).sample_raw(1, 1, 4, 4)
        np.testing.assert_array_equal(planned[1:], physical[1:])
        np.testing.assert_allclose(planned[0] - physical[0], 20.0, atol=0.001)
        overlap = make_frozen_plan_factory(1, config, plan).sample_raw(2, 2, 4, 4)
        np.testing.assert_array_equal(overlap, planned[:, 1:, 1:])

    def test_schedule_tiers_keep_physical_generation_identity(self):
        config = PhysicalGenerationConfig()
        backends = [ResourcePhysicalTerrainDiffusionBackend(config, tier) for tier in ("light", "balanced", "large")]
        self.assertEqual(len({backend.identity for backend in backends}), 1)
        self.assertEqual([backend.resource_settings["cache_mib"] for backend in backends], [64, 256, 512])
        self.assertTrue(all(backend.pipeline is None for backend in backends))

    def test_genuine_candidate_budget_uses_immutable_original_difference(self):
        plan = self.fixture()
        raw = plan["original_height_m"].copy()
        provenance = {"artifact_kind": "terrain_diffusion_output", "td_inference_run": True,
                      "archive_sha256": "a" * 64}
        result = derive_detail(plan, raw, origin_xz_m=[0, 0], spacing_m=30.0,
            raw_provenance=provenance, window_kind="ridge", candidate_height_m=raw + 90,
            candidate_provenance=dict(provenance, archive_sha256="c" * 64))
        self.assertIn("total_max_abs_m_exceeded", result["metadata"]["rejection_reasons"])
        self.assertEqual(result["metadata"]["ledger"]["total_max_abs_m"], 90)
        np.testing.assert_array_equal(result["arrays"]["original_td_m"], raw)
        np.testing.assert_array_equal(result["arrays"]["total_delta_m"], np.full(raw.shape, 90))
        self.assertNotIn("lowpass", result["metadata"]["macro_baseline"])

    def test_canonical_negative_boundary_overlap_and_cold_component_reconstruction(self):
        class ShapeDependentFixture:
            def __init__(self):
                self.metadata = {"schema": "physical-generation-v1", "fixture_only": True}
                self.identity = _digest(self.metadata)
                self.config = SimpleNamespace(native_resolution_m=30.0)
                self.calls = []

            def generate(self, seed, x, z, size):
                self.calls.append((x, z, size))
                height = (np.arange(x, x + size)[None, :] * 0.5
                          + np.arange(z, z + size)[:, None] * 0.25 + size * 0.01).astype(np.float32)
                climate = np.stack([height + channel for channel in range(5)])
                metadata = dict(self.metadata, identity=self.identity, seed=str(seed), native_origin=[x, z],
                    shape=[size, size], native_resolution_m=30.0, artifact_kind="terrain_diffusion_output")
                return height, climate, metadata

            def close(self):
                pass

        with TemporaryDirectory() as temporary:
            backend = ShapeDependentFixture()
            source = CanonicalTDSource(backend, temporary)
            large_h, large_c, metadata = source.generate(7, -12, -12, 97)
            small_h, small_c, _ = source.generate(7, -4, -4, 17)
            np.testing.assert_array_equal(small_h, large_h[8:25, 8:25])
            np.testing.assert_array_equal(small_c, large_c[:, 8:25, 8:25])
            self.assertEqual(len(backend.calls), 4)
            self.assertTrue(all(call[2] == 257 for call in backend.calls))
            self.assertIn((-256, -256, 257), backend.calls)
            path = Path(temporary) / "assembled.npz"
            np.savez_compressed(path, elevation_m=large_h, climate=large_c,
                                metadata_json=np.array(json.dumps(metadata)))
            cold, _ = load_canonical_window(path, file_sha256(path))
            np.testing.assert_array_equal(cold["arrays"]["height_m"], large_h)
            broken = large_h.copy()
            broken[5, 5] += 1.0
            corrupt = Path(temporary) / "corrupt.npz"
            np.savez_compressed(corrupt, elevation_m=broken, climate=large_c,
                                metadata_json=np.array(json.dumps(metadata)))
            with self.assertRaisesRegex(ValueError, "assembled pixels differ"):
                load_canonical_window(corrupt, file_sha256(corrupt))


if __name__ == "__main__":
    unittest.main()
