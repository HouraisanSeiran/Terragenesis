import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from terrain_pipeline.lake import LakeRoutingRecipe as LakeRoutingRecipe
from terrain_pipeline.lake import evaluate_lake_routing as evaluate_lake_routing
from terrain_pipeline.lake import lake_routing_hash as lake_routing_hash
from terrain_pipeline.lake import load_lake_routing as load_lake_routing
from terrain_pipeline.lake import save_lake_routing as save_lake_routing


def lake_fixture():
    terrain = np.full((7, 7), 6.)
    terrain[2:5, 2:5] = 1.
    terrain[3, 5] = 3.
    terrain[3, 6] = 2.
    basin = np.zeros(terrain.shape, bool)
    basin[2:5, 2:5] = True
    legal = np.zeros(terrain.shape, bool)
    legal[3, 6] = True
    return dict(height_m=terrain, basin_mask=basin, legal_spill_grid_zx=(3, 5),
                spacing_x_m=1., spacing_z_m=1., source_identity="synthetic-nine-cell-v1",
                downstream_path_grid_zx=[(3, 5), (3, 6)],
                domain_mask=np.ones(terrain.shape, bool),
                protected_mask=np.zeros(terrain.shape, bool), legal_outlet_mask=legal,
                origin_x_m=100., origin_z_m=-50., vertical_datum="synthetic-local-m")


def routing_recipe(**changes):
    recipe = LakeRoutingRecipe(3., 1., (2.,) * 10, (0.,) * 10,
                               (3., 4., 5.), (0., 1., 2.), 5.)
    return replace(recipe, **changes)


def write_unchecked_bundle(result, destination):
    metadata = {name: value for name, value in result.items() if name != "arrays"}
    np.savez_compressed(destination, metadata=np.asarray(json.dumps(metadata)), **result["arrays"])


class LakeRoutingTests(unittest.TestCase):
    def run_lake(self, recipe=None, **changes):
        inputs = lake_fixture()
        inputs.update(changes)
        return evaluate_lake_routing(**inputs, recipe=recipe or routing_recipe())

    def assert_failed(self, result, code):
        self.assertEqual(result["status"], "diagnostic_not_publishable")
        self.assertFalse(result["scenario_feasible"])
        self.assertEqual(result["diagnostic"]["code"], code)

    def assert_ledger(self, result):
        arrays = result["arrays"]
        recipe = result["input"]["recipe"]
        basin = arrays["basin_mask"]
        area = result["summary"]["cell_area_m2"]
        geometry = np.maximum(arrays["stage_m"][:, None] - arrays["height_m"][basin], 0.).sum(axis=1) * area
        np.testing.assert_allclose(geometry, arrays["storage_m3"], rtol=0, atol=1e-12)
        independently_computed = (np.diff(arrays["storage_m3"]) - arrays["step_inflow_volume_m3"] +
                                  arrays["step_loss_volume_m3"] + arrays["step_outflow_volume_m3"])
        np.testing.assert_allclose(independently_computed, arrays["step_residual_m3"], rtol=0, atol=1e-13)
        for index, residual in enumerate(independently_computed):
            scale = max(abs(arrays["storage_m3"][index]), abs(arrays["storage_m3"][index + 1]),
                        arrays["step_inflow_volume_m3"][index], arrays["step_loss_volume_m3"][index],
                        arrays["step_outflow_volume_m3"][index])
            allowed = recipe["volume_abs_tolerance_m3"] + recipe["volume_rel_tolerance"] * scale
            self.assertLessEqual(abs(residual), allowed + 1e-13)
        total = (arrays["storage_m3"][-1] - arrays["storage_m3"][0] -
                 arrays["step_inflow_volume_m3"].sum() + arrays["step_loss_volume_m3"].sum() +
                 arrays["step_outflow_volume_m3"].sum())
        self.assertAlmostEqual(total, independently_computed.sum(), places=12)
        self.assertLessEqual(abs(total), result["summary"]["cumulative_volume_tolerance_m3"] + 1e-13)
        np.testing.assert_array_equal(arrays["wet_mask"], arrays["water_depth_m"] > 0)
        self.assertTrue(np.isnan(arrays["water_surface_m"][~arrays["wet_mask"]]).all())
        self.assertAlmostEqual(arrays["water_depth_m"].sum() * area, arrays["storage_m3"][-1], places=12)
        self.assertFalse(arrays["wet_mask"][3, 5])
        self.assertFalse(arrays["wet_mask"][3, 6])

    def test_analytic_single_step(self):
        result = self.run_lake(routing_recipe(inflow_m3_s=(2.,), loss_m3_s=(0.,)))
        self.assertTrue(result["scenario_feasible"])
        self.assertAlmostEqual(result["arrays"]["stage_m"][-1], 3.2, places=9)
        self.assertAlmostEqual(result["arrays"]["storage_m3"][-1], 19.8, places=8)
        self.assertAlmostEqual(result["arrays"]["step_outflow_m3_s"][0], .2, places=9)
        self.assert_ledger(result)

    def test_analytic_ten_steps_and_determinism(self):
        result = self.run_lake()
        self.assertTrue(result["scenario_feasible"])
        expected_stages = 3. + 2. * (1. - .9 ** np.arange(11))
        np.testing.assert_allclose(result["arrays"]["stage_m"], expected_stages, rtol=0, atol=2e-9)
        self.assertAlmostEqual(result["summary"]["final_storage_m3"], 29.7237880782, places=7)
        self.assertAlmostEqual(result["summary"]["total_outflow_volume_m3"], 8.2762119218, places=7)
        self.assertEqual(result["identity_sha256"], self.run_lake()["identity_sha256"])
        self.assert_ledger(result)

    def test_storage_below_spill_and_full_cell_area(self):
        result = self.run_lake(routing_recipe(initial_stage_m=1., inflow_m3_s=(9.,), loss_m3_s=(0.,)),
                               spacing_x_m=2., spacing_z_m=3.)
        self.assertTrue(result["scenario_feasible"])
        self.assertAlmostEqual(result["arrays"]["storage_m3"][-1], 9., places=7)
        self.assertAlmostEqual(result["arrays"]["stage_m"][-1], 1. + 1. / 6., places=8)
        self.assertEqual(result["arrays"]["step_outflow_m3_s"][0], 0.)
        self.assert_ledger(result)

    def test_variable_inflow_losses_and_monotone_plateau_rating(self):
        inflows = (2., 4., 0., 3.)
        losses = (0., .5, 1., 0.)
        result = self.run_lake(routing_recipe(inflow_m3_s=inflows, loss_m3_s=losses))
        self.assertTrue(result["scenario_feasible"])
        excess_stage = 0.
        for index, (inflow, loss) in enumerate(zip(inflows, losses)):
            excess_stage = .9 * excess_stage + (inflow - loss) / 10.
            self.assertAlmostEqual(result["arrays"]["stage_m"][index + 1], 3. + excess_stage, places=8)
        self.assert_ledger(result)
        plateau = self.run_lake(routing_recipe(rating_outflow_m3_s=(0., 1., 1.)))
        self.assertTrue(plateau["scenario_feasible"])
        self.assert_ledger(plateau)

    def test_empty_initial_at_or_below_bed_and_exact_dry(self):
        for initial in (1., 0.):
            result = self.run_lake(routing_recipe(initial_stage_m=initial, inflow_m3_s=(0.,), loss_m3_s=(0.,)))
            self.assertTrue(result["scenario_feasible"])
            self.assertEqual(result["arrays"]["storage_m3"][-1], 0.)
            self.assertFalse(result["arrays"]["wet_mask"].any())
            self.assert_ledger(result)
        dried = self.run_lake(routing_recipe(initial_stage_m=2., inflow_m3_s=(0.,), loss_m3_s=(9.,)))
        self.assertTrue(dried["scenario_feasible"])
        self.assertEqual(dried["arrays"]["storage_m3"][-1], 0.)

    def test_no_display_threshold_drops_small_depth(self):
        terrain = lake_fixture()["height_m"]
        terrain[2, 2] = 3. - 1e-10
        result = self.run_lake(routing_recipe(inflow_m3_s=(0.,), loss_m3_s=(0.,)), height_m=terrain)
        self.assertTrue(result["scenario_feasible"])
        self.assertTrue(result["arrays"]["wet_mask"][2, 2])
        self.assertGreater(result["arrays"]["water_depth_m"][2, 2], 0.)
        self.assert_ledger(result)

    def test_resource_bounds_grid_steps_and_solver(self):
        for changes in ({"max_grid_cells": 48}, {"max_steps": 9}):
            with self.assertRaises(ValueError):
                self.run_lake(routing_recipe(**changes))
        result = self.run_lake(routing_recipe(max_solver_iterations=1))
        self.assert_failed(result, "solver_resource_limit")
        self.assertEqual(result["diagnostic"]["failed_step"], 0)

    def test_missing_legal_outlet_and_four_neighbor_path(self):
        legal = lake_fixture()["legal_outlet_mask"]
        legal[:] = False
        self.assert_failed(self.run_lake(legal_outlet_mask=legal), "missing_legal_outlet")
        legal[4, 6] = True
        self.assert_failed(self.run_lake(legal_outlet_mask=legal,
                           downstream_path_grid_zx=[(3, 5), (4, 6)]), "invalid_downstream_adjacency")
        terrain = lake_fixture()["height_m"]
        terrain[3, 6] = 4.
        self.assert_failed(self.run_lake(height_m=terrain), "uphill_downstream_path")
        self.assert_failed(self.run_lake(downstream_path_grid_zx=[(3, 5), (3, 6), (3, 5), (3, 6)]),
                           "invalid_downstream_adjacency")

    def test_indices_reject_fractional_boolean_and_out_of_range(self):
        for spill in ((3.1, 5), (3., 5.), (True, 5), (-1, 5), (3, 7), (3,)):
            with self.subTest(spill=spill), self.assertRaises(ValueError):
                self.run_lake(legal_spill_grid_zx=spill)
        for path in ([(3.1, 5), (3, 6)], [(True, 5), (3, 6)], [(3, 5), (3, 7)], [], None):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_lake(downstream_path_grid_zx=path)

    def test_disconnected_basin_and_initial_wet(self):
        basin = lake_fixture()["basin_mask"]
        basin[3, 2:5] = False
        self.assert_failed(self.run_lake(basin_mask=basin), "basin_disconnected")
        terrain = lake_fixture()["height_m"]
        terrain[3, 2:5] = 4.
        self.assert_failed(self.run_lake(height_m=terrain), "wet_pool_disconnected")

    def test_final_wet_split_rejected_with_committed_prefix(self):
        terrain = lake_fixture()["height_m"]
        terrain[3, 2:5] = 2.5
        recipe = routing_recipe(initial_stage_m=3., inflow_m3_s=(0., 0.), loss_m3_s=(0., 8.))
        result = self.run_lake(recipe, height_m=terrain)
        self.assert_failed(result, "wet_pool_disconnected")
        self.assertEqual(result["summary"]["completed_steps"], 1)
        self.assertEqual(result["diagnostic"]["failed_step"], 1)
        self.assertLess(result["diagnostic"]["evidence"]["candidate_stage_m"], 2.5)

    def test_unmodeled_saddle_and_shore_equality(self):
        terrain = lake_fixture()["height_m"]
        terrain[2, 5] = 4.
        self.assert_failed(self.run_lake(height_m=terrain), "unmodeled_low_saddle")
        terrain[2, 5] = 5.
        self.assertTrue(self.run_lake(height_m=terrain)["scenario_feasible"])

    def test_capacity_and_curve_exhaustion_do_not_clamp_success(self):
        recipe = routing_recipe(inflow_m3_s=(100.,), loss_m3_s=(0.,))
        result = self.run_lake(recipe)
        self.assert_failed(result, "spill_capacity_exceeded")
        self.assertEqual(result["arrays"]["stage_m"].tolist(), [3.])
        result = self.run_lake(replace(recipe, rating_stage_m=(3., 4.), rating_outflow_m3_s=(0., 1.)))
        self.assert_failed(result, "rating_range_exceeded")
        result = self.run_lake(routing_recipe(initial_stage_m=5.5, max_stage_m=5.5))
        self.assert_failed(result, "rating_range_exceeded")

    def test_protection_domain_and_grid_boundary_conflicts(self):
        for name, point, code in (("protected_mask", (2, 2), "basin_domain_or_protection"),
                                  ("protected_mask", (3, 6), "path_domain_or_protection"),
                                  ("domain_mask", (2, 2), "basin_domain_or_protection"),
                                  ("domain_mask", (3, 5), "path_domain_or_protection")):
            inputs = lake_fixture()
            inputs[name][point] = name == "protected_mask"
            self.assert_failed(evaluate_lake_routing(**inputs, recipe=routing_recipe()), code)
        basin = lake_fixture()["basin_mask"]
        basin[0:2, 2] = True
        self.assert_failed(self.run_lake(basin_mask=basin), "unmodeled_grid_boundary")

    def test_dry_loss_failure_retains_trace_and_input(self):
        recipe = routing_recipe(initial_stage_m=1., inflow_m3_s=(9., 0.), loss_m3_s=(0., 20.))
        result = self.run_lake(recipe)
        self.assert_failed(result, "dry_loss_exceeds_available_water")
        self.assertEqual(result["summary"]["completed_steps"], 1)
        self.assertEqual(result["diagnostic"]["failed_step"], 1)
        self.assertEqual(result["input"]["recipe"]["loss_m3_s"], (0., 20.))
        self.assertEqual(result["arrays"]["step_inflow_volume_m3"].tolist(), [9.])

    def test_invalid_parameters_rejected_early(self):
        for changes in ({"inflow_m3_s": (-1.,) * 10}, {"loss_m3_s": (-1.,) * 10},
                        {"dt_s": 0.}, {"dt_s": True}, {"dt_s": float("nan")},
                        {"max_steps": 1.5}, {"max_grid_cells": False},
                        {"inflow_m3_s": (1.,)}, {"rating_outflow_m3_s": (1., 2., 3.)},
                        {"rating_outflow_m3_s": (0., 2., 1.)},
                        {"rating_stage_m": (3., 3., 5.)}, {"volume_abs_tolerance_m3": 0.}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                routing_recipe(**changes)
        for changes in ({"spacing_x_m": 0.}, {"origin_x_m": float("inf")},
                        {"vertical_datum": ""}, {"source_identity": ""},
                        {"domain_mask": np.ones((7, 7), int)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.run_lake(**changes)
        terrain = lake_fixture()["height_m"]
        terrain[0, 0] = float("nan")
        with self.assertRaises(ValueError):
            self.run_lake(height_m=terrain)

    def test_arrays_are_detached_and_readonly_even_setflags(self):
        inputs = lake_fixture()
        result = evaluate_lake_routing(**inputs, recipe=routing_recipe())
        inputs["height_m"][:] = -100.
        self.assertEqual(result["arrays"]["height_m"][2, 2], 1.)
        for array in result["arrays"].values():
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.setflags(write=True)

    def test_save_load_success_failure_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, result in (("success", self.run_lake()),
                                 ("failure", self.run_lake(routing_recipe(max_solver_iterations=1)))):
                path = save_lake_routing(result, directory / f"{name}.npz")
                loaded = load_lake_routing(path)
                self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
                self.assertEqual(loaded["scenario_feasible"], result["scenario_feasible"])
                self.assertFalse(loaded["arrays"]["water_depth_m"].flags.writeable)
                original = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    save_lake_routing(result, path)
                self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(list(directory.iterdir())), 2)

    def test_save_race_exactly_one_complete_bundle(self):
        result = self.run_lake()
        barrier = threading.Barrier(2)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "race.npz"

            def save_competing():
                barrier.wait()
                try:
                    save_lake_routing(result, path)
                    return "saved"
                except FileExistsError:
                    return "exists"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(lambda unused: save_competing(), range(2)))
            self.assertEqual(sorted(outcomes), ["exists", "saved"])
            self.assertEqual(load_lake_routing(path)["identity_sha256"], result["identity_sha256"])
            self.assertEqual(list(Path(temporary).iterdir()), [path])

    def test_interrupted_save_leaves_no_partial_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "interrupted.npz"
            with patch('terrain_pipeline.lake._m4_lake_routing_np.savez_compressed', side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    save_lake_routing(self.run_lake(), path)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_rehash_cannot_forge_feasible_storage_or_water(self):
        failed = self.run_lake(routing_recipe(max_solver_iterations=1))
        forged = copy.deepcopy(failed)
        forged["scenario_feasible"] = True
        good = self.run_lake()
        wrong_storage = copy.deepcopy(good)
        wrong_storage["arrays"]["storage_m3"][-1] += 1.
        wrong_water = copy.deepcopy(good)
        wrong_water["arrays"]["water_depth_m"][2, 2] += 1.
        wrong_status = copy.deepcopy(good)
        wrong_status["status"] = "prepared"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "forged.npz"
            for altered in (forged, wrong_storage, wrong_water, wrong_status):
                altered["identity_sha256"] = lake_routing_hash(altered)
                write_unchecked_bundle(altered, path)
                with self.assertRaises(ValueError):
                    load_lake_routing(path)
                with self.assertRaises(ValueError):
                    save_lake_routing(altered, Path(temporary) / "rejected.npz")
            self.assertFalse((Path(temporary) / "rejected.npz").exists())

    def test_hash_mismatch_and_bad_load(self):
        result = copy.deepcopy(self.run_lake())
        result["summary"]["final_storage_m3"] += 1.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.npz"
            write_unchecked_bundle(result, path)
            with self.assertRaises(ValueError):
                load_lake_routing(path)

    def test_hard_resource_ceilings_and_early_rejection_before_copy(self):
        for changes in ({"max_steps": 4097}, {"max_grid_cells": 1000001},
                        {"max_solver_iterations": 129}, {"max_steps": 10 ** 12},
                        {"inflow_m3_s": (0.,) * 4097},
                        {"rating_stage_m": (0.,) * 4097}):
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                routing_recipe(**changes)
        with patch('terrain_pipeline.lake._m4_lake_routing_np.array', side_effect=AssertionError("copy happened")):
            with self.assertRaises(ValueError):
                self.run_lake(routing_recipe(max_grid_cells=48))
            with self.assertRaises(ValueError):
                self.run_lake(routing_recipe(max_steps=9))
            with self.assertRaises(ValueError):
                self.run_lake(height_m=np.empty((1001, 1000)))

    def test_below_bed_max_stage_and_flat_outlet_rejected(self):
        with self.assertRaises(ValueError):
            self.run_lake(routing_recipe(initial_stage_m=0., max_stage_m=.5))
        terrain = lake_fixture()["height_m"]
        terrain[3, 6] = 3.
        self.assert_failed(self.run_lake(height_m=terrain), "outlet_not_below_spill")

    def test_existing_destination_rejected_before_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "existing.npz"
            path.write_bytes(b"preserve")
            with patch('terrain_pipeline.lake._replay', side_effect=AssertionError("replayed")):
                with self.assertRaises(FileExistsError):
                    save_lake_routing({}, path)
            self.assertEqual(path.read_bytes(), b"preserve")

    def test_load_exact_array_set_and_archive_byte_caps_before_numpy(self):
        result = self.run_lake()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bounded.npz"
            save_lake_routing(result, path)
            for name, limit in (("MAX_ARCHIVE_BYTES", 100), ("MAX_METADATA_BYTES", 100)):
                with patch(f'terrain_pipeline.lake.{name}', limit):
                    with patch('terrain_pipeline.lake._m4_lake_routing_np.load', side_effect=AssertionError("decompressed")):
                        with self.assertRaises(ValueError):
                            load_lake_routing(path)
            with zipfile.ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            for wrong_set in (dict(members, **{"extra.npy": members["height_m.npy"]}),
                              {name: data for name, data in members.items() if name != "height_m.npy"}):
                with zipfile.ZipFile(path, "w") as archive:
                    for name, data in wrong_set.items():
                        archive.writestr(name, data)
                with patch('terrain_pipeline.lake._m4_lake_routing_np.load', side_effect=AssertionError("decompressed")):
                    with self.assertRaises(ValueError):
                        load_lake_routing(path)

    def test_npy_bomb_header_rejected_before_numpy_allocation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "header.npz"
            save_lake_routing(self.run_lake(), path)
            with zipfile.ZipFile(path) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            buffer = io.BytesIO()
            np.lib.format.write_array_header_1_0(buffer, {
                "descr": "<f8", "fortran_order": False, "shape": (10 ** 12, 10 ** 12)})
            members["height_m.npy"] = buffer.getvalue()
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in members.items():
                    archive.writestr(name, data)
            with patch('terrain_pipeline.lake._m4_lake_routing_np.load', side_effect=AssertionError("allocated")):
                with self.assertRaises(ValueError):
                    load_lake_routing(path)

    def test_strict_json_duplicate_keys_and_nonfinite_constants(self):
        good = self.run_lake()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "json.npz"
            for text in ('{"status":"failed","status":"prepared"}', '{"value":NaN}',
                         '{"value":Infinity}', '{"value":-Infinity}',
                         '{"nested":{"stage":1,"stage":2}}'):
                np.savez_compressed(path, metadata=np.asarray(text), **good["arrays"])
                with self.subTest(text=text), self.assertRaises(ValueError):
                    load_lake_routing(path)

    def test_save_rejects_unloadable_metadata_without_partial_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "oversized.npz"
            with patch('terrain_pipeline.lake.MAX_METADATA_BYTES', 100):
                with self.assertRaises(ValueError):
                    save_lake_routing(self.run_lake(), path)
            self.assertEqual(list(Path(temporary).iterdir()), [])
            path.write_bytes(b"not an npz")
            with self.assertRaises(ValueError):
                load_lake_routing(path)


if __name__ == "__main__":
    unittest.main()
