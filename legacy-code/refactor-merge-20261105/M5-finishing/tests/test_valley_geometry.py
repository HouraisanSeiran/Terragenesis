import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.channel_geometry import ChannelRecipe
from terrain_pipeline.channel_geometry import plan_channel
from terrain_pipeline.channel_geometry import ValleyGeometryRecipe, load_valley_geometry, prepare_valley_geometry, save_valley_geometry, evaluate_fine_valley_ledger
from terrain_pipeline.surface_domain import SurfaceNetworkBudget, prepare_surface_network
from terrain_pipeline.channel_geometry import SectionRecipe
from terrain_pipeline.surface_hydraulics import StageRecipe
from terrain_pipeline.surface_hydraulics import InundationRecipe
from tests.test_channel_stage_inundation import confluence_plan


class ValleyGeometryTests(unittest.TestCase):
    def make_result(self, recipe=None, protected=None):
        plan = confluence_plan()
        shape = plan["arrays"]["source_height_m"].shape
        if protected is None: protected = np.zeros(shape, bool)
        result = prepare_valley_geometry(plan, np.array([[30., 10.], [30., 60.]]),
            np.array([4.7, 3.7]), np.array([30., 30.]), np.ones(shape, bool), protected,
            recipe or ValleyGeometryRecipe(8., 10000., 100000., 100000.),
            ChannelRecipe(reference_discharge_m3_s=.1, reference_width_m=8., min_width_m=8.,
                          max_width_m=8., reference_depth_m=.5, min_depth_m=.5, max_depth_m=.5,
                          max_cut_m=4., min_bed_slope_m_per_m=.00001))
        return plan, result

    def test_independent_valley_and_bed_ledger_round_trip(self):
        plan, result = self.make_result()
        self.assertTrue(result["summary"]["geometry_feasible"])
        self.assertEqual(result["summary"]["geometry_scope"], "coarse_node_diagnostic_only")
        np.testing.assert_array_equal(plan["arrays"]["source_height_m"], result["arrays"]["source_height_m"])
        np.testing.assert_allclose(result["arrays"]["valley_cut_m"] + result["arrays"]["bed_cut_m"],
                                   result["arrays"]["total_cut_m"], rtol=0, atol=1e-9)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "valley.npz"
            save_valley_geometry(result, path)
            loaded = load_valley_geometry(path)
            self.assertEqual(loaded["identity_sha256"], result["identity_sha256"])
            with np.load(path, allow_pickle=False) as archive:
                arrays = {name: archive[name] for name in archive.files if name != "manifest"}
                manifest = archive["manifest"].item()
            arrays["total_cut_m"] = arrays["total_cut_m"].copy(); arrays["total_cut_m"][0, 0] += 1
            np.savez_compressed(path, manifest=manifest, **arrays)
            with self.assertRaises(ValueError): load_valley_geometry(path)

    def test_valley_depth_area_volume_and_protection_fail_independently(self):
        cases = [(ValleyGeometryRecipe(.1, 10000., 100000., 100000.), "valley_depth"),
                 (ValleyGeometryRecipe(8., 100., 100000., 100000.), "valley_area"),
                 (ValleyGeometryRecipe(8., 10000., 10., 100000.), "valley_volume"),
                 (ValleyGeometryRecipe(8., 10000., 100000., 10.), "total_volume")]
        for recipe, key in cases:
            with self.subTest(key=key):
                _, result = self.make_result(recipe)
                self.assertTrue(result["summary"]["failures"][key])
                self.assertFalse(result["summary"]["geometry_feasible"])
        protected = np.zeros((7, 7), bool); protected[3, 3] = True
        _, result = self.make_result(protected=protected)
        self.assertTrue(result["summary"]["failures"]["protection"])

    def test_fine_h0_h1_h2_with_joint_water(self):
        _, valley = self.make_result()
        domain = np.ones((61, 61), bool)
        empty = np.zeros((61, 61), bool)
        legal = empty.copy(); legal[-1, 27:34] = True
        surface = prepare_surface_network(valley["replanned_plan"], 0., 0., 1., 1., (61, 61),
            domain, empty, legal, np.array([5.2]), SectionRecipe(),
            StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 5000., 5000.))
        ledger = evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger["status"], "prepared")
        arrays = ledger["arrays"]
        np.testing.assert_allclose(arrays["valley_cut_m"] + arrays["bed_cut_m"],
                                   arrays["total_cut_m"], rtol=0, atol=1e-8)
        self.assertGreater(ledger["summary"]["valley_cut_volume_m3"], 0)
        self.assertGreater(ledger["summary"]["bed_cut_volume_m3"], 0)

    def test_coarse_protection_failure_survives_fine_joint(self):
        protected = np.zeros((7, 7), bool); protected[3, 3] = True
        _, valley = self.make_result(protected=protected)
        domain = np.ones((61, 61), bool)
        empty = np.zeros((61, 61), bool)
        legal = empty.copy(); legal[-1, 27:34] = True
        surface = prepare_surface_network(valley["replanned_plan"], 0., 0., 1., 1., (61, 61),
            domain, empty, legal, np.array([5.2]), SectionRecipe(),
            StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 5000., 5000.))
        ledger = evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger["status"], "diagnostic_not_publishable")
        self.assertTrue(ledger["summary"]["failures"]["coarse_valley"])

    def test_blocked_bed_becomes_feasible_after_independent_valley(self):
        base = confluence_plan()
        arrays = base["arrays"]
        raised = arrays["source_height_m"].copy()
        raised[3, 3] += 5.
        params = base["identity"]["parameters"]
        recipe = ChannelRecipe(reference_discharge_m3_s=.1, reference_width_m=8.,
            min_width_m=8., max_width_m=8., reference_depth_m=.5,
            min_depth_m=.5, max_depth_m=.5, max_cut_m=4., min_bed_slope_m_per_m=.00001)
        blocked = plan_channel(raised, arrays["receiver"], arrays["order"], arrays["outlet_mask"],
            arrays["discharge_m3_s"], 10., 10., 0., 0., 0., "raised-ridge", recipe)
        self.assertTrue(blocked["arrays"]["over_budget_mask"].any())
        valley = prepare_valley_geometry(blocked, np.array([[30., 10.], [30., 60.]]),
            np.array([4.7, 3.7]), np.array([30., 30.]), np.ones((7, 7), bool),
            np.zeros((7, 7), bool), ValleyGeometryRecipe(8., 10000., 100000., 100000.), recipe)
        self.assertFalse(valley["replanned_plan"]["arrays"]["over_budget_mask"].any())
        self.assertTrue(valley["summary"]["geometry_feasible"])
        self.assertEqual(valley["arrays"]["source_height_m"][3, 3], 10.)
        domain = np.ones((61, 61), bool)
        empty = np.zeros((61, 61), bool)
        legal = empty.copy(); legal[-1, 27:34] = True
        surface = prepare_surface_network(valley["replanned_plan"], 0., 0., 1., 1., (61, 61),
            domain, empty, legal, np.array([5.2]), SectionRecipe(),
            StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 5000., 5000.))
        ledger = evaluate_fine_valley_ledger(valley, surface)
        self.assertEqual(ledger["status"], "prepared")
        self.assertFalse(any(ledger["summary"]["failures"].values()))


if __name__ == "__main__": unittest.main()
