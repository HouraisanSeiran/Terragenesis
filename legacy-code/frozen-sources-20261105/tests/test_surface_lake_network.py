from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_reroute import RerouteRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.lake_routing import LakeRoutingRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.network_valley import NetworkValleyRecipe
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from terrain_pipeline.surface_network_recovery import FineGrid, RecoveryRecipe
from terrain_pipeline.surface_lake_network import (
    LakeRiverSeam, SurfaceLakeNetworkRecipe, evaluate_surface_lake_network,
    load_surface_lake_network, save_surface_lake_network, surface_lake_network_hash,
    validate_surface_lake_network,
)
from terrain_pipeline.valley_geometry import ValleyGeometryRecipe


def joint_case(inflows=(2., 4.), initial_stage=10., original_local=.01):
    lake_height = np.full((7, 7), 14.)
    lake_height[2:5, 2:5] = 8.
    lake_height[3, 5] = 10.
    lake_height[3, 6] = 9.
    basin = np.zeros((7, 7), bool)
    basin[2:5, 2:5] = True
    lake_legal = np.zeros((7, 7), bool)
    lake_legal[3, 6] = True
    lake_inputs = dict(height_m=lake_height, basin_mask=basin, legal_spill_grid_zx=(3, 5),
                       spacing_x_m=1., spacing_z_m=1., origin_x_m=-6., origin_z_m=-2.,
                       vertical_datum="synthetic-local-m", source_identity="joint-lake-original-v1",
                       downstream_path_grid_zx=[(3, 5), (3, 6)], domain_mask=np.ones((7, 7), bool),
                       protected_mask=np.zeros((7, 7), bool), legal_outlet_mask=lake_legal,
                       recipe=LakeRoutingRecipe(initial_stage, 1., inflows, (0.,) * len(inflows),
                                                (10., 11., 12.), (0., 1., 2.), 12.))
    height = np.full((7, 7), 14.)
    for row in range(1, 7):
        height[row, 2:5] = 9.1 - row * .1
    receiver = np.full(49, -1, np.int64)
    for row in range(1, 6):
        receiver[row * 7 + 3] = (row + 1) * 7 + 3
    outlets = (receiver == -1).reshape((7, 7))
    order = np.asarray(list(np.flatnonzero(outlets.ravel())) + [38, 31, 24, 17, 10], np.int64)
    discharge = np.zeros((7, 7))
    discharge[1:, 3] = original_local
    channel = ChannelRecipe(start_discharge_m3_s=.05, reference_discharge_m3_s=.2,
        reference_width_m=.8, min_width_m=.4, max_width_m=1.2,
        reference_depth_m=.4, min_depth_m=.2, max_depth_m=.8,
        max_cut_m=2., min_bed_slope_m_per_m=.001)
    plan = plan_channel(height, receiver, order, outlets, discharge,
                        1., 1., -3., 0., 0., "joint-downstream-original-v1", channel)
    fine_domain = np.ones((61, 61), bool)
    fine_protected = np.zeros((61, 61), bool)
    fine_legal = np.zeros((61, 61), bool)
    fine_legal[-1, 20:41] = True
    return dict(lake_inputs=lake_inputs, plan=plan, coarse_domain=np.ones((7, 7), bool),
                coarse_protected=np.zeros((7, 7), bool),
                fine=FineGrid(-3., 0., .1, .1, (61, 61), fine_domain, fine_protected, fine_legal),
                outlet_stage_m=np.full((7, 7), 8.7), section_recipe=SectionRecipe(),
                stage_recipe=StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
                inundation_recipe=InundationRecipe(max_lateral_reach_m=1.5),
                budget=SurfaceNetworkBudget(2., 100., 100.),
                network_recipe=NetworkValleyRecipe(2., .8, 2., .001),
                valley_recipe=ValleyGeometryRecipe(2., 100., 100., 100.),
                reroute_recipe=RerouteRecipe(max_extra_cut_m=2.), recovery_recipe=RecoveryRecipe(max_attempts=4),
                seam=LakeRiverSeam((3, 6), 0., 1., "synthetic-local-m",
                                  "joint-lake-original-v1", "joint-downstream-original-v1"),
                recipe=SurfaceLakeNetworkRecipe())


def high_tailwater_case(zero_lake_outflow=False):
    case = joint_case(inflows=(0.,) if zero_lake_outflow else (2.,),
                      initial_stage=9.01,
                      original_local=.2 if zero_lake_outflow else .01)
    case["lake_inputs"]["height_m"][3, 5] = 9.01
    case["lake_inputs"]["recipe"] = replace(case["lake_inputs"]["recipe"], initial_stage_m=9.01,
        rating_stage_m=(9.01, 10.01, 11.01), max_stage_m=11.01)
    case["outlet_stage_m"][:] = 9.02
    legal = case["fine"].legal_outlet_mask.copy()
    legal[-1, :] = True
    case["fine"] = replace(case["fine"], legal_outlet_mask=legal)
    return case


class SurfaceLakeNetworkTests(unittest.TestCase):
    def assert_failed(self, result, code):
        self.assertFalse(result["transfer_feasible"])
        self.assertEqual(result["diagnostic"]["code"], code)
        self.assertEqual(result["status"], "diagnostic_not_publishable")

    def assert_ledger(self, result):
        for row in result["ledger"]:
            lake_residual = row["lake_storage_change_m3"] - row["dt_s"] * (
                row["lake_inflow_m3_s"] - row["lake_loss_m3_s"] - row["lake_outflow_m3_s"])
            river_residual = row["downstream_outlet_m3_s"] - row["downstream_local_total_m3_s"] - row["lake_outflow_m3_s"]
            combined = row["lake_storage_change_m3"] + row["dt_s"] * row["downstream_outlet_m3_s"] - row["dt_s"] * (
                row["lake_inflow_m3_s"] - row["lake_loss_m3_s"] + row["downstream_local_total_m3_s"])
            self.assertAlmostEqual(lake_residual, row["lake_residual_m3"], places=12)
            self.assertAlmostEqual(river_residual, row["downstream_residual_m3_s"], places=12)
            self.assertAlmostEqual(combined, row["combined_residual_m3"], places=12)
            self.assertLessEqual(abs(combined), row["combined_tolerance_m3"] + 1e-13)
        summary = result["summary"]
        aggregate = (summary["committed_final_lake_storage_m3"] - summary["committed_initial_lake_storage_m3"] +
                     summary["total_downstream_outlet_m3"] - summary["total_lake_inflow_m3"] +
                     summary["total_lake_loss_m3"] - summary["total_downstream_local_m3"])
        self.assertAlmostEqual(aggregate, summary["aggregate_combined_residual_m3"], places=12)
        self.assertLessEqual(abs(aggregate), summary["total_combined_tolerance_m3"] + 1e-12)
        depth = result["committed_lake_arrays"]["water_depth_m"]
        lake_input = result["inputs"]["lake_inputs"]
        self.assertAlmostEqual(float(depth.sum()) * lake_input["spacing_x_m"] * lake_input["spacing_z_m"],
                               summary["committed_final_lake_storage_m3"], places=12)

    def test_two_step_real_recovery(self):
        result = evaluate_surface_lake_network(**joint_case())
        self.assertTrue(result["transfer_feasible"], (result["diagnostic"], result["trace"][0].get("recovery")))
        self.assertEqual(result["summary"]["committed_steps"], 2)
        self.assertEqual(result["status"], "diagnostic_not_publishable")
        for step in result["trace"]:
            self.assertTrue(step["recovery"]["accepted"])
            self.assertLess(step["injection_stage_m"], 10.)
        self.assert_ledger(result)

    def test_changed_flow_recomputes_actual_discharge_and_geometry_from_original(self):
        case = joint_case()
        original_height = case["plan"]["arrays"]["source_height_m"].copy()
        result = evaluate_surface_lake_network(**case)
        first, second = result["trace"]
        self.assertNotEqual(first["lake_outflow_m3_s"], second["lake_outflow_m3_s"])
        for step in result["trace"]:
            local = step["injected_local_inflow_m3_s"].copy().ravel()
            arrays = step["recomputed_plan"]["arrays"]
            for donor in arrays["order"][::-1]:
                target = arrays["receiver"][donor]
                if target >= 0:
                    local[target] += local[donor]
            np.testing.assert_allclose(local.reshape((7, 7)), arrays["discharge_m3_s"], rtol=0, atol=1e-12)
            np.testing.assert_array_equal(arrays["source_height_m"], original_height)
            injection_delta = step["injected_local_inflow_m3_s"] - step["original_local_inflow_m3_s"]
            self.assertEqual(np.count_nonzero(injection_delta), 1)
            self.assertAlmostEqual(injection_delta[1, 3], step["lake_outflow_m3_s"])
            self.assertEqual(arrays["discharge_m3_s"][0, 0], 0.)
        for name in ("bed_cut_m", "wet_mask", "final_surface_m"):
            self.assertFalse(np.array_equal(first["recovery"]["surface"]["arrays"][name],
                                            second["recovery"]["surface"]["arrays"][name]))
        np.testing.assert_array_equal(case["plan"]["arrays"]["source_height_m"], original_height)

    def test_exact_zero_no_flow_without_fabricated_river_geometry(self):
        result = evaluate_surface_lake_network(**joint_case(inflows=(0., 0.), initial_stage=8., original_local=0.))
        self.assertTrue(result["transfer_feasible"])
        self.assertEqual([step["status"] for step in result["trace"]], ["no_flow", "no_flow"])
        self.assertTrue(all(step["recovery"] is None for step in result["trace"]))
        self.assertFalse(result["committed_lake_arrays"]["wet_mask"].any())
        self.assert_ledger(result)

    def test_positive_flow_below_original_threshold_is_not_epsilon_no_flow(self):
        result = evaluate_surface_lake_network(**joint_case(inflows=(.01,), original_local=0.))
        self.assert_failed(result, "positive_outflow_without_active_path")
        self.assertGreater(result["trace"][0]["lake_outflow_m3_s"], 0.)
        self.assertEqual(result["summary"]["committed_steps"], 0)
        self.assertEqual(result["diagnostic"]["evidence"]["original_start_threshold_m3_s"], .05)

    def test_lake_failure_never_runs_downstream(self):
        case = joint_case(inflows=(100.,))
        with patch("terrain_pipeline.surface_lake_network.recover_surface_network", side_effect=AssertionError("called")):
            result = evaluate_surface_lake_network(**case)
        self.assert_failed(result, "lake_scenario_failed")
        self.assertEqual(result["trace"], [])
        self.assertEqual(result["summary"]["committed_steps"], 0)

    def test_seam_domain_and_protection_conflicts(self):
        for name, value in (("coarse_domain", False), ("coarse_protected", True)):
            case = joint_case()
            case[name][1, 3] = value
            self.assert_failed(evaluate_surface_lake_network(**case), "seam_domain_or_protection")

    def test_actual_recovery_protection_and_budget_gates(self):
        case = joint_case()
        case["coarse_protected"][3, 3] = True
        fine = case["fine"]
        protected = fine.protected_mask.copy()
        protected[30, 30] = True
        case["fine"] = replace(fine, protected_mask=protected)
        result = evaluate_surface_lake_network(**case)
        self.assert_failed(result, "downstream_recovery_failed")
        self.assertTrue(result["trace"][0]["recovery"]["attempts"])
        case = joint_case()
        case["budget"] = SurfaceNetworkBudget(2., 0., 0.)
        self.assert_failed(evaluate_surface_lake_network(**case), "downstream_recovery_failed")

    def test_tailwater_submerges_spill_rejects_one_way_assumption(self):
        import terrain_pipeline.surface_lake_network as module
        real = module.recover_surface_network

        def high_tailwater(*args, **kwargs):
            result = deepcopy(real(*args, **kwargs))
            result["surface"]["arrays"]["water_surface_m"][10, 30] = 10.1
            return result

        with patch.object(module, "recover_surface_network", side_effect=high_tailwater):
            result = evaluate_surface_lake_network(**joint_case())
        self.assert_failed(result, "spill_submerged_one_way_invalid")
        self.assertTrue(result["trace"][0]["recovery"]["accepted"])
        self.assertGreaterEqual(result["trace"][0]["injection_stage_m"], 10.)

    def test_overlap_checks_actual_water_footprints(self):
        case = joint_case()
        case["lake_inputs"]["basin_mask"][4, 5] = True
        case["lake_inputs"]["height_m"][4, 5] = 8.
        result = evaluate_surface_lake_network(**case)
        self.assert_failed(result, "lake_river_wet_overlap")
        self.assertGreater(result["trace"][result["diagnostic"]["failed_step"]]["overlap_fine_cells"], 0)

    def test_failed_second_step_commits_only_prefix_geometry(self):
        case = joint_case()
        case["recipe"] = replace(case["recipe"], max_total_attempts=1)
        result = evaluate_surface_lake_network(**case)
        self.assert_failed(result, "joint_recovery_resource_exhausted")
        self.assertEqual(result["summary"]["committed_steps"], 1)
        self.assertEqual(result["diagnostic"]["failed_step"], 1)
        self.assertNotEqual(result["summary"]["committed_final_lake_stage_m"],
                            result["independent_lake_diagnostic"]["summary"]["final_stage_m"])
        self.assertAlmostEqual(result["summary"]["committed_final_lake_stage_m"], 10.2, places=8)
        self.assertEqual(len(result["committed_lake_arrays"]["stage_m"]), 2)
        self.assertEqual([step["committed"] for step in result["trace"]], [True, False])
        self.assert_ledger(result)

    def test_aggregate_fine_work_and_lake_work_exhaustion(self):
        for changes, code in ((dict(max_total_fine_work=3721), "joint_recovery_resource_exhausted"),
                              (dict(max_total_lake_work=150), "joint_lake_work_exhausted")):
            case = joint_case()
            case["recipe"] = replace(case["recipe"], **changes)
            result = evaluate_surface_lake_network(**case)
            self.assert_failed(result, code)
            self.assertEqual(result["summary"]["committed_steps"], 1)
            self.assert_ledger(result)

    def test_early_hard_resource_bounds_and_invalid_recipes(self):
        for changes in (dict(max_steps=65), dict(max_total_attempts=129), dict(max_fine_cells=1000001),
                        dict(max_total_fine_work=8000001), dict(max_steps=True),
                        dict(discharge_abs_tolerance_m3_s=0.)):
            with self.assertRaises(ValueError):
                SurfaceLakeNetworkRecipe(**changes)
        for changes in (dict(max_steps=1), dict(max_coarse_cells=48), dict(max_fine_cells=3720),
                        dict(max_lake_cells=48), dict(max_total_lake_work=50)):
            case = joint_case()
            case["recipe"] = replace(case["recipe"], **changes)
            with patch("terrain_pipeline.surface_lake_network._validated_plan", side_effect=AssertionError("copied")):
                with self.assertRaises(ValueError):
                    evaluate_surface_lake_network(**case)

    def test_coordinate_alignment_and_identity_binding(self):
        for seam_changes in (dict(world_x_m=.01), dict(world_z_m=1.01),
                             dict(lake_path_grid_zx=(3, 5)), dict(lake_path_grid_zx=(2, 6)),
                             dict(downstream_vertical_datum="wrong"), dict(lake_source_identity="wrong"),
                             dict(downstream_source_identity="wrong")):
            case = joint_case()
            case["seam"] = replace(case["seam"], **seam_changes)
            with self.subTest(seam_changes=seam_changes), self.assertRaises(ValueError):
                evaluate_surface_lake_network(**case)
        for node in ((3.1, 6), (True, 6)):
            with self.assertRaises(ValueError):
                replace(joint_case()["seam"], lake_path_grid_zx=node)
        case = joint_case()
        case["lake_inputs"]["height_m"][3, 6] = 8.9
        with self.assertRaisesRegex(ValueError, "elevation"):
            evaluate_surface_lake_network(**case)

    def test_original_q_tampering_and_nonconservative_plan_rejected(self):
        case = joint_case()
        case["plan"] = deepcopy(case["plan"])
        case["plan"]["arrays"]["discharge_m3_s"][2, 3] += 1.
        with self.assertRaises(ValueError):
            evaluate_surface_lake_network(**case)
        case = joint_case()
        original = case["plan"]
        parameters = original["identity"]["parameters"]
        arrays = original["arrays"]
        discharge = arrays["discharge_m3_s"].copy()
        discharge[1, 3] = .03
        channel = ChannelRecipe(**{name: parameters[name] for name in ChannelRecipe.__dataclass_fields__})
        case["plan"] = plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
                                   arrays["outlet_mask"], discharge, 1., 1., -3., 0., 0.,
                                   "joint-downstream-original-v1", channel)
        with self.assertRaisesRegex(ValueError, "conservative"):
            evaluate_surface_lake_network(**case)

    def test_final_recovered_injection_must_be_active_and_wet(self):
        import terrain_pipeline.surface_lake_network as module
        real = module.recover_surface_network

        def inactive_injection(*args, **kwargs):
            result = deepcopy(real(*args, **kwargs))
            result["final_plan"]["arrays"]["channel_mask"][1, 3] = False
            return result

        with patch.object(module, "recover_surface_network", side_effect=inactive_injection):
            result = evaluate_surface_lake_network(**joint_case())
        self.assert_failed(result, "injection_not_wet")

    def test_save_load_success_and_failed_prefix_readonly(self):
        cases = [joint_case(), joint_case()]
        cases[1]["recipe"] = replace(cases[1]["recipe"], max_total_attempts=1)
        with tempfile.TemporaryDirectory() as temporary:
            for index, case in enumerate(cases):
                result = evaluate_surface_lake_network(**case)
                path = save_surface_lake_network(result, Path(temporary) / f"case-{index}.npz")
                loaded = load_surface_lake_network(path)
                self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
                self.assertEqual(loaded["summary"]["committed_steps"], result["summary"]["committed_steps"])
                for array in loaded["committed_lake_arrays"].values():
                    self.assertFalse(array.flags.writeable)
                    with self.assertRaises(ValueError):
                        array.setflags(write=True)
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    save_surface_lake_network(result, path)
                self.assertEqual(before, path.read_bytes())

    def test_rehash_cannot_forge_transfer_or_q(self):
        case = joint_case()
        case["recipe"] = replace(case["recipe"], max_total_attempts=1)
        forged = deepcopy(evaluate_surface_lake_network(**case))
        forged["transfer_feasible"] = True
        forged["identity_sha256"] = surface_lake_network_hash(forged)
        with self.assertRaises(ValueError):
            validate_surface_lake_network(forged)
        forged = deepcopy(evaluate_surface_lake_network(**joint_case()))
        forged["trace"][0]["recomputed_plan"]["arrays"]["discharge_m3_s"][3, 3] += 1.
        forged["identity_sha256"] = surface_lake_network_hash(forged)
        with self.assertRaises(ValueError):
            validate_surface_lake_network(forged)

    def test_atomic_save_race(self):
        result = evaluate_surface_lake_network(**joint_case())
        barrier = threading.Barrier(2)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "race.npz"

            def competing_save(unused):
                barrier.wait()
                try:
                    save_surface_lake_network(result, path)
                    return "saved"
                except FileExistsError:
                    return "exists"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(competing_save, range(2)))
            self.assertEqual(sorted(outcomes), ["exists", "saved"])
            self.assertEqual(load_surface_lake_network(path)["identity_sha256"], result["identity_sha256"])
            self.assertEqual(list(Path(temporary).iterdir()), [path])

    def test_npy_bomb_preflight_and_strict_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.npz"
            save_surface_lake_network(evaluate_surface_lake_network(**joint_case()), path)
            with zipfile.ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            name = next(name for name in members if name != "manifest.npy")
            header = io.BytesIO()
            np.lib.format.write_array_header_1_0(header, dict(descr="<f8", fortran_order=False, shape=(10 ** 12,)))
            members[name] = header.getvalue()
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            with patch("terrain_pipeline.surface_lake_network.np.load", side_effect=AssertionError("allocated")):
                with self.assertRaises(ValueError):
                    load_surface_lake_network(path)

    def test_zero_lake_outflow_with_existing_high_tailwater_rejected(self):
        import terrain_pipeline.surface_lake_network as module
        real = module.recover_surface_network

        def high_existing_tailwater(*args, **kwargs):
            recovered = deepcopy(real(*args, **kwargs))
            self.assertTrue(recovered["accepted"])
            recovered["surface"]["arrays"]["water_surface_m"][10, 30] = 10.1
            recovered["surface"]["arrays"]["wet_mask"][10, 30] = True
            return recovered

        case = joint_case(inflows=(0.,), initial_stage=8., original_local=.2)
        with patch.object(module, "recover_surface_network", side_effect=high_existing_tailwater):
            result = evaluate_surface_lake_network(**case)
        self.assert_failed(result, "spill_submerged_one_way_invalid")
        self.assertEqual(result["trace"][0]["lake_outflow_m3_s"], 0.)
        self.assertEqual(result["summary"]["committed_steps"], 0)

    def test_real_low_spill_high_tailwater_with_zero_and_positive_lake_flow(self):
        for zero_flow in (False, True):
            result = evaluate_surface_lake_network(**high_tailwater_case(zero_flow))
            self.assert_failed(result, "spill_submerged_one_way_invalid")
            self.assertTrue(result["trace"][0]["recovery"]["accepted"])
            self.assertAlmostEqual(result["trace"][0]["injection_stage_m"], 9.02)
            self.assertEqual(result["diagnostic"]["evidence"]["spill_stage_m"], 9.01)
            if zero_flow:
                self.assertEqual(result["trace"][0]["lake_outflow_m3_s"], 0.)

    def test_retained_memory_preflight_before_downstream_recovery(self):
        case = joint_case()
        case["recipe"] = replace(case["recipe"], max_retained_bytes=500000)
        with patch("terrain_pipeline.surface_lake_network.recover_surface_network", side_effect=AssertionError("allocated")):
            result = evaluate_surface_lake_network(**case)
        self.assert_failed(result, "joint_retained_memory_exhausted")
        self.assertEqual(result["summary"]["committed_steps"], 0)
        self.assertEqual(result["trace"], [])
        case["recipe"] = replace(case["recipe"], max_retained_bytes=100)
        with self.assertRaises(ValueError):
            evaluate_surface_lake_network(**case)
        with self.assertRaises(ValueError):
            SurfaceLakeNetworkRecipe(max_retained_bytes=268435457)

    def test_save_payload_size_rejected_before_compression(self):
        result = evaluate_surface_lake_network(**joint_case())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bytes.npz"
            with patch("terrain_pipeline.surface_lake_network.MAX_ARCHIVE_BYTES", 100), patch(
                    "terrain_pipeline.surface_lake_network.np.savez_compressed", side_effect=AssertionError("compressed")):
                with self.assertRaises(ValueError):
                    save_surface_lake_network(result, path)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_load_rehashed_forged_q_and_status_semantically_rejected(self):
        import terrain_pipeline.surface_lake_network as module
        result = evaluate_surface_lake_network(**joint_case())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "rehashed.npz"
            for change in ("q", "status"):
                forged = deepcopy(result)
                if change == "q":
                    forged["trace"][0]["recomputed_plan"]["arrays"]["discharge_m3_s"][3, 3] += 1.
                else:
                    forged["transfer_feasible"] = False
                forged["identity_sha256"] = surface_lake_network_hash(forged)
                arrays = {}
                tree = module._tree(forged, arrays)
                import hashlib
                manifest = dict(format_version=1, tree=tree,
                                tree_sha256=hashlib.sha256(module._json(tree).encode("utf-8")).hexdigest())
                np.savez_compressed(path, manifest=np.asarray(module._json(manifest)), **arrays)
                with self.assertRaisesRegex(ValueError, "replay"):
                    load_surface_lake_network(path)

    def test_interrupted_save_never_leaves_partial_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "interrupted.npz"
            with patch("terrain_pipeline.surface_lake_network.np.savez_compressed", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    save_surface_lake_network(evaluate_surface_lake_network(**joint_case()), path)
            self.assertEqual(list(Path(temporary).iterdir()), [])
            for text in ('{"tree":1,"tree":2}', '{"tree":NaN}', '{"tree":Infinity}'):
                np.savez_compressed(path, manifest=np.asarray(text))
                with self.assertRaises(ValueError):
                    load_surface_lake_network(path)


if __name__ == "__main__":
    unittest.main()
