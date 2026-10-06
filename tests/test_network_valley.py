from copy import deepcopy
from dataclasses import asdict, replace
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.network_valley import (
    NetworkValleyRecipe, _array_digest, load_network_valley, prepare_network_valley,
    save_network_valley, validate_network_valley,
)
from terrain_pipeline.surface_network_prepare import (
    SurfaceNetworkBudget, prepare_surface_network, validate_surface_network,
)
from terrain_pipeline.valley_geometry import (
    ValleyGeometryRecipe, _rasterize_valley_edges, evaluate_fine_valley_ledger,
    load_fine_valley_ledger, prepare_valley_geometry, save_fine_valley_ledger,
)
from tests.test_channel_stage_inundation import confluence_plan


class NetworkValleyTests(unittest.TestCase):
    def setUp(self):
        self.base = confluence_plan()
        params = self.base["identity"]["parameters"]
        self.channel = ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
        arrays = self.base["arrays"]
        discharge = arrays["discharge_m3_s"].copy()
        discharge.flat[[17, 24, 31, 38, 45]] = .2
        self.base = self.replan(discharge=discharge)
        self.recipe = NetworkValleyRecipe(3.75, 30., 30., .00001)
        self.budget = ValleyGeometryRecipe(8., 10000., 100000., 100000.)
        self.domain = np.ones((7, 7), bool)
        self.protected = np.zeros((7, 7), bool)

    def replan(self, height=None, discharge=None, channel=None, spacing=(10., 10.)):
        arrays = self.base["arrays"]
        return plan_channel(arrays["source_height_m"] if height is None else height,
            arrays["receiver"], arrays["order"], arrays["outlet_mask"],
            arrays["discharge_m3_s"] if discharge is None else discharge,
            *spacing, 0., 0., 0., "network-test", channel or self.channel)

    def prepare(self, plan=None, recipe=None, budget=None, domain=None, protected=None, channel=None):
        return prepare_network_valley(self.base if plan is None else plan,
            self.domain if domain is None else domain, self.protected if protected is None else protected,
            recipe or self.recipe, budget or self.budget, channel or self.channel)

    def surface(self, valley, budget=None):
        domain = np.ones((61, 61), bool)
        empty = np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        return prepare_surface_network(valley["replanned_plan"], 0., 0., 1., 1., (61, 61),
            domain, empty, legal, np.array([5.2]), SectionRecipe(),
            StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=15.), budget or SurfaceNetworkBudget(4., 5000., 5000.))

    def test_complete_real_edges_shared_floor_width_and_nominal_bed(self):
        discharge = self.base["arrays"]["discharge_m3_s"].copy()
        discharge.flat[[9, 11, 17, 24, 31, 38, 45]] = [.1, .2, .3, .3, .3, .3, .3]
        channel = replace(self.channel, min_depth_m=.2, max_depth_m=3., depth_exponent=.5,
                          min_width_m=1., max_width_m=30., width_exponent=.5)
        plan = self.replan(discharge=discharge, channel=channel, spacing=(6., 10.))
        result = self.prepare(plan=plan, channel=channel, recipe=NetworkValleyRecipe(2., 1., 60., .02))
        network = result["network"]
        edges = network["active_edges"]
        expected = np.array([[9, 17], [11, 17], [17, 24], [24, 31], [31, 38], [38, 45]])
        np.testing.assert_array_equal(edges, expected)
        self.assertEqual(len(edges), np.count_nonzero(plan["arrays"]["channel_mask"].ravel() &
                                                      (plan["arrays"]["receiver"] >= 0)))
        floor = network["floor_elevation_m"].ravel()
        depth = plan["arrays"]["nominal_depth_m"].ravel()
        for (donor, receiver), length in zip(edges, network["edge_length_m"]):
            self.assertLessEqual(floor[receiver], floor[donor] - .02 * length + 1e-12)
            self.assertLessEqual(floor[receiver] - depth[receiver],
                floor[donor] - depth[donor] - channel.min_bed_slope_m_per_m * length + 1e-12)
        self.assertLessEqual(floor[17], min(floor[9], floor[11]) - .02 * math.hypot(6., 10.) + 1e-12)
        np.testing.assert_allclose(network["edge_length_m"][:2], math.hypot(6., 10.))
        np.testing.assert_array_equal(network["width_m"][network["active_mask"]],
            plan["arrays"]["nominal_width_m"][network["active_mask"]] * 2.)
        self.assertTrue(np.all(floor <= plan["arrays"]["source_height_m"].ravel()))

    def test_decreasing_nominal_depth_requires_extra_floor_drop(self):
        discharge = self.base["arrays"]["discharge_m3_s"].copy()
        discharge.flat[[9, 11]] = 1.
        channel = replace(self.channel, min_depth_m=.1, max_depth_m=3., depth_exponent=.5)
        plan = self.replan(discharge=discharge, channel=channel)
        result = self.prepare(plan=plan, channel=channel)
        floor = result["network"]["floor_elevation_m"].ravel()
        depth = plan["arrays"]["nominal_depth_m"].ravel()
        self.assertAlmostEqual(floor[17], 5. - depth[9] + depth[17] -
                               channel.min_bed_slope_m_per_m * math.hypot(10., 10.))

    def test_width_bounds_and_threshold_independence(self):
        recipe = NetworkValleyRecipe(4., 12., 20., .001)
        first = self.prepare(recipe=recipe)
        channel = replace(self.channel, start_discharge_m3_s=.08)
        second = self.prepare(plan=self.replan(channel=channel), recipe=recipe, channel=channel)
        np.testing.assert_array_equal(first["network"]["width_m"], second["network"]["width_m"])
        self.assertTrue(np.all(first["network"]["width_m"][first["network"]["active_mask"]] == 20.))
        lower = self.prepare(recipe=NetworkValleyRecipe(.1, 12., 20., .001))
        self.assertTrue(np.all(lower["network"]["width_m"][lower["network"]["active_mask"]] == 12.))

    def test_bbox_matches_full_union_and_duplicate_edges_do_not_sum(self):
        source = np.arange(99, dtype=float).reshape(9, 11) / 10. + 10.
        params = {"origin_x_m": -20., "origin_z_m": 7., "spacing_x_m": 3., "spacing_z_m": 7.}
        points = np.array([[[-17., 14.], [-14., 21.]], [[-11., 42.], [-11., 49.]]])
        floors = np.array([[9., 8.], [7., 6.]])
        widths = np.array([[14., 19.], [9., 11.]])
        full = _rasterize_valley_edges(source, params, points, floors, widths)
        local = _rasterize_valley_edges(source, params, points, floors, widths, local_bounds=True)
        np.testing.assert_array_equal(local, full)
        repeated = _rasterize_valley_edges(source, params, np.repeat(points, 2, axis=0),
            np.repeat(floors, 2, axis=0), np.repeat(widths, 2, axis=0), local_bounds=True)
        np.testing.assert_array_equal(repeated, full)

    def test_network_union_and_unrelated_tributaries_are_not_joined(self):
        result = self.prepare(recipe=NetworkValleyRecipe(1., 8., 8., .001))
        network = result["network"]
        edges = network["active_edges"]
        points = np.stack(((edges % 7) * 10., (edges // 7) * 10.), axis=2)
        expected = _rasterize_valley_edges(self.base["arrays"]["source_height_m"],
            self.base["identity"]["parameters"], points,
            network["floor_elevation_m"].ravel()[edges], network["width_m"].ravel()[edges])
        np.testing.assert_array_equal(result["arrays"]["valley_cut_m"], expected)
        self.assertEqual(result["arrays"]["valley_cut_m"][1, 3], 0.)

    def test_rasterization_work_is_local_not_edge_times_domain(self):
        source = np.full((487, 487), 10.)
        params = {"origin_x_m": 0., "origin_z_m": 0., "spacing_x_m": 10., "spacing_z_m": 10.}
        points = np.array([[[100., 100.], [110., 110.]]])
        points = np.repeat(points, 2325, axis=0)
        floors = np.full((2325, 2), 8.)
        widths = np.full((2325, 2), 30.)
        meshgrid = np.meshgrid
        sizes = []
        def record_grid(grid_x, grid_z):
            sizes.append(len(grid_x) * len(grid_z))
            return meshgrid(grid_x, grid_z)
        with patch("terrain_pipeline.valley_geometry.np.meshgrid", side_effect=record_grid):
            cut = _rasterize_valley_edges(source, params, points, floors, widths, local_bounds=True)
        self.assertEqual(len(sizes), 2325)
        self.assertLessEqual(max(sizes), 25)
        self.assertEqual(cut[10, 10], 2.)

    def test_budget_failures_are_not_clipped(self):
        height = self.base["arrays"]["source_height_m"].copy()
        height[3, 3] += 5.
        plan = self.replan(height=height)
        generous = self.prepare(plan=plan)
        cases = [(replace(self.budget, max_valley_depth_m=.1), "valley_depth"),
                 (replace(self.budget, max_valley_area_m2=0.), "valley_area"),
                 (replace(self.budget, max_valley_volume_m3=0.), "valley_volume"),
                 (replace(self.budget, max_total_cut_volume_m3=0.), "total_volume"),
                 (replace(self.budget, max_total_cut_area_m2=0.), "total_area")]
        for budget, key in cases:
            with self.subTest(key=key):
                result = self.prepare(plan=plan, budget=budget)
                self.assertFalse(result["summary"]["geometry_feasible"])
                self.assertTrue(result["summary"]["failures"][key])
                np.testing.assert_array_equal(result["arrays"]["valley_cut_m"], generous["arrays"]["valley_cut_m"])
                self.assertEqual(result["status"], "diagnostic_not_publishable")

    def test_domain_and_protection_failure_survive_fine_ledger(self):
        for mask_name, key in (("domain", "active_domain"), ("protected", "active_protection")):
            with self.subTest(mask=mask_name):
                mask = self.domain.copy() if mask_name == "domain" else self.protected.copy()
                mask.flat[9] = mask_name == "protected"
                result = self.prepare(**{mask_name: mask})
                self.assertTrue(result["summary"]["failures"][key])
                surface = self.surface(result)
                ledger = evaluate_fine_valley_ledger(result, surface)
                self.assertTrue(ledger["summary"]["failures"]["coarse_valley"])
                self.assertEqual(ledger["status"], "diagnostic_not_publishable")

    def test_raised_ridge_fine_ledger_and_round_trip(self):
        height = self.base["arrays"]["source_height_m"].copy()
        height[3, 3] += 5.
        plan = self.replan(height=height)
        self.assertTrue(plan["arrays"]["over_budget_mask"].any())
        valley = self.prepare(plan=plan)
        self.assertTrue(valley["summary"]["geometry_feasible"])
        surface = self.surface(valley)
        ledger = evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger["status"], "prepared")
        np.testing.assert_allclose(ledger["arrays"]["valley_cut_m"] + ledger["arrays"]["bed_cut_m"],
            ledger["arrays"]["total_cut_m"], rtol=0, atol=1e-8)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fine.npz"
            save_fine_valley_ledger(ledger, path)
            self.assertEqual(load_fine_valley_ledger(path)["identity_sha256"], ledger["identity_sha256"])
        for value in ledger["arrays"].values():
            with self.assertRaises(ValueError):
                value.flags.writeable = True

    def test_determinism_source_unchanged_and_hard_immutable_outputs(self):
        before = {name: array_hash(value) for name, value in self.base["arrays"].items()}
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        self.assertEqual(before, {name: array_hash(value) for name, value in self.base["arrays"].items()})
        for collection in (first["arrays"], first["network"], first["replanned_plan"]["arrays"]):
            for value in collection.values():
                with self.assertRaises(ValueError):
                    value.flags.writeable = True
        validate_network_valley(first)

    def test_opt_in_identity_and_parent_change_with_parameters_and_masks(self):
        first = self.prepare()
        second = self.prepare(recipe=replace(self.recipe, min_floor_slope_m_per_m=.00002))
        self.assertNotEqual(first["planning_identity_sha256"], second["planning_identity_sha256"])
        self.assertNotEqual(first["identity_sha256"], second["identity_sha256"])
        self.assertEqual(first["replanned_plan"]["identity"]["parameters"]["source_identity"],
                         first["planning_identity_sha256"])
        protected = self.protected.copy()
        protected[0, 0] = True
        third = self.prepare(protected=protected)
        self.assertNotEqual(first["planning_identity_sha256"], third["planning_identity_sha256"])
        self.assertEqual(first["planning_identity"]["algorithm_version"], "network-valley-planning-v1")

    def test_all_source_and_derived_plan_fields_are_validated(self):
        for name in self.base["arrays"]:
            with self.subTest(field=name):
                altered = deepcopy(self.base)
                value = altered["arrays"][name].copy()
                value.flat[0] = not value.flat[0] if value.dtype == bool else value.flat[0] + 1
                altered["arrays"][name] = value
                with self.assertRaises(ValueError):
                    self.prepare(plan=altered)

    def test_invalid_topology_even_with_rehashed_sources(self):
        for field in ("receiver", "order"):
            altered = deepcopy(self.base)
            value = altered["arrays"][field].copy()
            if field == "receiver":
                value[9] = 45
            else:
                value[[0, -1]] = value[[-1, 0]]
            altered["arrays"][field] = value
            params = altered["identity"]["parameters"]
            params["source_route_sha256" if field == "receiver" else "source_order_sha256"] = array_hash(value)
            altered["identity_sha256"] = ArtifactIdentity(**altered["identity"]).sha256
            with self.assertRaises(ValueError):
                self.prepare(plan=altered)

    def test_recipe_mismatch_empty_network_and_invalid_masks(self):
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.prepare(channel=replace(self.channel, start_discharge_m3_s=.08))
        discharge = np.full((7, 7), .01)
        discharge.flat[45] = .1
        with self.assertRaisesRegex(ValueError, "active D8 edge"):
            self.prepare(plan=self.replan(discharge=discharge))
        for mask in (np.ones((7, 7), float), np.ones((2, 2), bool)):
            with self.assertRaises(ValueError):
                self.prepare(domain=mask)
        for field in asdict(self.recipe):
            for value in (True, 0., -1., float("inf"), float("nan")):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        replace(self.recipe, **{field: value})
        with self.assertRaises(ValueError):
            replace(self.recipe, min_width_m=31.)

    def test_output_tampering_rejected_before_fine_ledger(self):
        valley = self.prepare()
        surface = self.surface(valley)
        for collection in ("network", "arrays"):
            for name in valley[collection]:
                with self.subTest(collection=collection, field=name):
                    changed = deepcopy(valley)
                    value = changed[collection][name].copy()
                    value.flat[0] = not value.flat[0] if value.dtype == bool else value.flat[0] + 1
                    changed[collection][name] = value
                    with self.assertRaises(ValueError):
                        evaluate_fine_valley_ledger(changed, surface)
        changed = deepcopy(valley)
        changed["summary"]["geometry_feasible"] = False
        with self.assertRaises(ValueError):
            evaluate_fine_valley_ledger(changed, surface)
        changed = deepcopy(valley)
        changed["replanned_plan"]["arrays"]["nominal_depth_m"] = np.ones((7, 7))
        with self.assertRaises(ValueError):
            evaluate_fine_valley_ledger(changed, surface)
        changed = deepcopy(surface)
        changed["arrays"]["final_surface_m"] = changed["arrays"]["final_surface_m"].copy()
        changed["arrays"]["final_surface_m"][0, 0] += 1.
        with self.assertRaises(ValueError):
            evaluate_fine_valley_ledger(valley, changed)

    def test_rehashed_failed_valley_cannot_be_promoted_to_feasible(self):
        failed = self.prepare(budget=ValleyGeometryRecipe(0., 0., 0., 0., 0.))
        self.assertFalse(failed["summary"]["geometry_feasible"])
        for erase_failures in (False, True):
            changed = deepcopy(failed)
            changed["summary"]["geometry_feasible"] = True
            if erase_failures:
                changed["summary"]["failures"] = dict.fromkeys(changed["summary"]["failures"], False)
            changed["identity"]["parameters"]["summary_sha256"] = digest(changed["summary"])
            changed["identity_sha256"] = ArtifactIdentity(**changed["identity"]).sha256
            with self.assertRaisesRegex(ValueError, "semantics mismatch"):
                validate_network_valley(changed)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "forged.npz"
                with self.assertRaises(ValueError):
                    save_network_valley(changed, path)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_rehashed_failed_surface_cannot_make_fine_ledger_prepared(self):
        valley = self.prepare()
        failed = self.surface(valley, budget=SurfaceNetworkBudget(4., 0., 0.))
        self.assertEqual(failed["status"], "diagnostic_not_publishable")
        honest = evaluate_fine_valley_ledger(valley, failed)
        self.assertEqual(honest["status"], "diagnostic_not_publishable")
        for erase_failures in (False, True):
            changed = deepcopy(failed)
            changed["status"] = "prepared"
            changed["summary"]["publishable"] = True
            if erase_failures:
                changed["summary"]["budget_failures"] = dict.fromkeys(changed["summary"]["budget_failures"], False)
                changed["summary"]["joint_blockers"] = dict.fromkeys(changed["summary"]["joint_blockers"], False)
            changed["identity"]["parameters"]["summary_sha256"] = digest(changed["summary"])
            changed["identity_sha256"] = ArtifactIdentity(**changed["identity"]).sha256
            with self.assertRaises(ValueError):
                validate_surface_network(changed, allow_diagnostic=True)
            with self.assertRaises(ValueError):
                evaluate_fine_valley_ledger(valley, changed)

    def test_diagnostic_bundle_round_trip_immutable_and_no_overwrite(self):
        for budget in (self.budget, ValleyGeometryRecipe(0., 0., 0., 0.)):
            with self.subTest(budget=budget), tempfile.TemporaryDirectory() as directory:
                valley = self.prepare(budget=budget)
                path = Path(directory) / "network.npz"
                self.assertEqual(save_network_valley(valley, path), path)
                loaded = load_network_valley(path)
                self.assertEqual(loaded["identity_sha256"], valley["identity_sha256"])
                self.assertEqual(loaded["planning_identity"], valley["planning_identity"])
                self.assertEqual(loaded["summary"], valley["summary"])
                for actual, original in ((loaded["arrays"], valley["arrays"]),
                        (loaded["network"], valley["network"]),
                        (loaded["replanned_plan"]["arrays"], valley["replanned_plan"]["arrays"])):
                    self.assertEqual(set(actual), set(original))
                    for name in actual:
                        np.testing.assert_array_equal(actual[name], original[name])
                        with self.assertRaises(ValueError):
                            actual[name].flags.writeable = True
                before = path.read_bytes()
                with self.assertRaises(FileExistsError):
                    save_network_valley(valley, path)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_diagnostic_archive_tampering_and_field_set_rejected(self):
        valley = self.prepare()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valid.npz"
            save_network_valley(valley, path)
            with np.load(path, allow_pickle=False) as archive:
                manifest = str(archive["manifest"].item())
                payload = {name: archive[name].copy() for name in archive.files if name != "manifest"}
            for action in ("mutate", "extra", "missing"):
                changed = {name: value.copy() for name, value in payload.items()}
                if action == "mutate":
                    changed["network__width_m"].flat[17] += 1.
                elif action == "extra":
                    changed["network__unexpected"] = np.zeros(1)
                else:
                    del changed["replanned__target_bed_m"]
                import json
                record = json.loads(manifest)
                record["payload_sha256"] = _array_digest(changed)
                damaged = Path(directory) / f"{action}.npz"
                np.savez_compressed(damaged, manifest=json.dumps(record), **changed)
                with self.assertRaises(ValueError):
                    load_network_valley(damaged)

    def test_atomic_diagnostic_save_cleans_temporary_on_link_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "network.npz"
            with patch("terrain_pipeline.network_valley.os.link", side_effect=FileExistsError("race")):
                with self.assertRaises(FileExistsError):
                    save_network_valley(self.prepare(), path)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_rehashed_source_h0_and_parent_mismatch_rejected(self):
        valley = self.prepare()
        changed = deepcopy(valley)
        changed["arrays"]["source_height_m"] = changed["arrays"]["source_height_m"].copy()
        changed["arrays"]["source_height_m"][0, 0] += 1.
        changed["identity"]["parameters"]["arrays_sha256"] = _array_digest(changed["arrays"])
        changed["identity_sha256"] = ArtifactIdentity(**changed["identity"]).sha256
        with self.assertRaises(ValueError):
            validate_network_valley(changed)
        changed = deepcopy(valley)
        changed["planning_identity"]["parameters"]["source_plan_sha256"] = "wrong-parent"
        changed["planning_identity_sha256"] = ArtifactIdentity(**changed["planning_identity"]).sha256
        with self.assertRaises(ValueError):
            validate_network_valley(changed)
        changed = deepcopy(valley)
        changed["identity"]["parameters"]["replanned_sha256"] = self.base["identity_sha256"]
        changed["identity_sha256"] = ArtifactIdentity(**changed["identity"]).sha256
        with self.assertRaises(ValueError):
            validate_network_valley(changed)

    def test_synthetic_fixture_discharge_conserves_at_confluence(self):
        arrays = self.base["arrays"]
        discharge = arrays["discharge_m3_s"]
        runoff = discharge.ravel().copy()
        for donor in np.flatnonzero(arrays["receiver"] >= 0):
            runoff[arrays["receiver"][donor]] -= discharge.flat[donor]
        self.assertTrue(np.all(runoff >= 0.))
        self.assertAlmostEqual(float(runoff.sum()), float(discharge[arrays["outlet_mask"]].sum()))
        self.assertEqual(discharge.flat[9] + discharge.flat[11], discharge.flat[17])

    def test_original_explicit_api_geometry_and_identity(self):
        points = np.array([[30., 10.], [30., 60.]])
        floors = np.array([4.7, 3.7])
        widths = np.array([30., 30.])
        result = prepare_valley_geometry(self.base, points, floors, widths, self.domain, self.protected,
                                        self.budget, self.channel)
        grid_x, grid_z = np.meshgrid(np.arange(7) * 10., np.arange(7) * 10.)
        fraction = np.clip((grid_z - 10.) / 50., 0., 1.)
        distance = np.hypot(grid_x - 30., grid_z - (10. + fraction * 50.))
        floor = (1 - fraction) * 4.7 + fraction * 3.7
        cut = np.zeros((7, 7))
        inside = distance < 15.
        cut[inside] = np.maximum(0., self.base["arrays"]["source_height_m"][inside] - floor[inside]) * (
            .5 * (1 + np.cos(np.pi * distance[inside] / 15.)))
        np.testing.assert_array_equal(result["arrays"]["valley_cut_m"], cut)
        identity = ArtifactIdentity("Terragenesis", "valley-geometry", "valley-geometry-v1", 0,
            {**asdict(self.budget), "source_plan_sha256": self.base["identity_sha256"],
             "replanned_sha256": result["replanned_plan"]["identity_sha256"],
             "centerline_sha256": array_hash(points), "floor_sha256": array_hash(floors),
             "width_sha256": array_hash(widths), "domain_sha256": array_hash(self.domain),
             "protected_sha256": array_hash(self.protected),
             "arrays_sha256": digest({name: array_hash(value) for name, value in result["arrays"].items()}),
             "summary_sha256": digest(result["summary"])})
        self.assertEqual(result["identity_sha256"], identity.sha256)
        self.assertEqual(result["replanned_plan"]["identity"]["parameters"]["source_identity"],
                         self.base["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
