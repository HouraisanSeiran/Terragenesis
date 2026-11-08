import tempfile
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.surface_hydraulics import InundationRecipe, evaluate_inundation, load_inundation, save_inundation, slice_inundation
from terrain_pipeline.surface_hydraulics import assess_joint
from terrain_pipeline.surface_hydraulics import StageRecipe, load_stage, save_stage, solve_stage
from terrain_pipeline.channel_geometry import SectionRecipe, evaluate_sections
from terrain_pipeline.channel_geometry import ChannelRecipe, plan_channel
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.surface_rivers.metric_fluvial_water_repair import graph_connection


def confluence_plan(isolated_basin=False):
    height = np.full((7, 7), 10.)
    height[1:6, 2:5] = 5.
    height[0, 3] = 10.
    height[6, 3] = 4.
    if isolated_basin:
        height[4, 1] = 3.
        height[4, 2] = 10.
    receiver = np.full(49, -1, dtype=np.int64)
    outlets = np.ones((7, 7), bool)
    mesh = grid_mesh(height.shape, dx_m=10.)
    for donor, target in ((9, 17), (11, 17), (17, 24), (24, 31), (31, 38), (38, 45)):
        path = graph_connection(donor, target, 7, shape=height.shape, mesh=mesh)
        for first, second in zip(path, path[1:]):
            receiver[first[0] * 7 + first[1]] = second[0] * 7 + second[1]
    outlets[:] = (receiver < 0).reshape(height.shape)
    order = list(np.flatnonzero(outlets))
    position = 0
    while position < len(order):
        order.extend(np.flatnonzero(receiver == order[position]).tolist())
        position += 1
    order = np.asarray(order, np.int64)
    q = np.full((7, 7), .01)
    q.ravel()[(receiver >= 0)] = .1
    q.flat[45] = .1
    plan = plan_channel(height, receiver, order, outlets, q, 10., 10., 0., 0.,
                        0., "synthetic-confluence-basin" if isolated_basin else "synthetic-confluence", ChannelRecipe(
                            reference_discharge_m3_s=.1, reference_width_m=8.,
                            min_width_m=8., max_width_m=8.,
                            reference_depth_m=.5, min_depth_m=.5, max_depth_m=.5,
                            max_cut_m=4., min_bed_slope_m_per_m=.00001))
    return plan


def full_sections(plan):
    return evaluate_sections(plan, 0., 0., 1., 1., (61, 61),
                             np.zeros((61, 61), bool), SectionRecipe())


class StageInundationTests(unittest.TestCase):
    def test_full_confluence_and_lowland_success(self):
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = solve_stage(plan, np.array([5.2]), StageRecipe(max_depth_m=4.,
                                                                 max_lift_above_nominal_m=3.))
        domain = np.ones((61, 61), bool)
        protected = np.zeros((61, 61), bool)
        legal = np.zeros((61, 61), bool)
        legal[-1, 27:34] = True
        flood = evaluate_inundation(plan, sections, stage, domain, protected, legal,
                                    InundationRecipe(max_lateral_reach_m=15.))
        self.assertTrue(stage["summary"]["stage_feasible"])
        self.assertGreater(flood["summary"]["wet_nodes"], 0)
        self.assertGreater(flood["summary"]["overbank_nodes"], 0)
        self.assertTrue(flood["summary"]["legal_outlet_wet"])
        self.assertTrue(assess_joint(plan, sections, stage, flood)["pass"])
        left = slice_inundation(flood, slice(None), slice(0, 31))
        np.testing.assert_array_equal(left["wet_mask"], flood["arrays"]["wet_mask"][:, :31])

    def test_fixed_outlet_and_depth_limit_fail_without_raising_unbounded_water(self):
        plan = confluence_plan()
        stage = solve_stage(plan, np.array([20.]), StageRecipe(max_depth_m=2.))
        self.assertFalse(stage["summary"]["stage_feasible"])
        self.assertGreater(stage["summary"]["invalid_depth_nodes"], 0)
        self.assertEqual(stage["arrays"]["stage_m"][6, 3], 20.)

    def test_protection_and_high_ground_are_not_wet(self):
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = solve_stage(plan, np.array([4.2]), StageRecipe(max_depth_m=3.))
        domain = np.ones((61, 61), bool)
        protected = np.zeros((61, 61), bool)
        protected[30, 30] = True
        legal = np.zeros((61, 61), bool)
        legal[-1, 30] = True
        flood = evaluate_inundation(plan, sections, stage, domain, protected, legal,
                                    InundationRecipe(max_lateral_reach_m=5.))
        self.assertFalse(flood["arrays"]["wet_mask"][30, 30])
        self.assertGreater(flood["summary"]["protected_conflict_nodes"], 0)
        self.assertFalse(flood["arrays"]["wet_mask"][0, 0])
        self.assertFalse(assess_joint(plan, sections, stage, flood)["pass"])

    def test_isolated_low_basin_behind_ridge_stays_dry(self):
        plan = confluence_plan(isolated_basin=True)
        sections = full_sections(plan)
        stage = solve_stage(plan, np.array([5.2]), StageRecipe(max_depth_m=4.,
                                                                 max_lift_above_nominal_m=3.))
        domain = np.ones((61, 61), bool)
        empty = np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        flood = evaluate_inundation(plan, sections, stage, domain, empty, legal,
                                    InundationRecipe(max_lateral_reach_m=30.))
        self.assertLess(sections["arrays"]["bounded_surface_m"][40, 10],
                        stage["arrays"]["stage_m"][4, 3])
        self.assertFalse(flood["arrays"]["wet_mask"][40, 10])
        self.assertTrue(flood["arrays"]["wet_mask"][30, 30])

    def test_save_reload_and_missing_legal_outlet(self):
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = solve_stage(plan, np.array([4.2]), StageRecipe())
        domain = np.ones((61, 61), bool)
        empty = np.zeros((61, 61), bool)
        flood = evaluate_inundation(plan, sections, stage, domain, empty, empty,
                                    InundationRecipe(max_lateral_reach_m=5.))
        self.assertFalse(flood["summary"]["coverage_complete"])
        with tempfile.TemporaryDirectory() as directory:
            stage_path = Path(directory) / "stage.npz"
            flood_path = Path(directory) / "flood.npz"
            save_stage(stage, stage_path)
            save_inundation(flood, flood_path)
            self.assertEqual(load_stage(stage_path)["identity_sha256"], stage["identity_sha256"])
            self.assertEqual(load_inundation(flood_path)["identity_sha256"], flood["identity_sha256"])

    def test_joint_rejects_tampered_section_and_flood_summary(self):
        plan = confluence_plan()
        sections = full_sections(plan)
        stage = solve_stage(plan, np.array([5.2]), StageRecipe(max_depth_m=4.,
                                                                 max_lift_above_nominal_m=3.))
        full = np.ones((61, 61), bool)
        empty = np.zeros((61, 61), bool)
        legal = empty.copy()
        legal[-1, 27:34] = True
        flood = evaluate_inundation(plan, sections, stage, full, empty, legal,
                                    InundationRecipe(max_lateral_reach_m=15.))
        changed = dict(sections)
        changed["arrays"] = dict(sections["arrays"])
        changed["arrays"]["bounded_surface_m"] = sections["arrays"]["bounded_surface_m"].copy()
        changed["arrays"]["bounded_surface_m"][20, 30] -= .1
        with self.assertRaisesRegex(ValueError, "section arrays differ"):
            assess_joint(plan, changed, stage, flood)
        with self.assertRaisesRegex(ValueError, "bounded surface differs"):
            evaluate_inundation(plan, changed, stage, full, empty, legal,
                                InundationRecipe(max_lateral_reach_m=15.))
        changed_flood = dict(flood)
        changed_flood["summary"] = dict(flood["summary"])
        changed_flood["summary"]["coverage_complete"] = False
        with self.assertRaisesRegex(ValueError, "coverage summary mismatch"):
            assess_joint(plan, sections, stage, changed_flood)


if __name__ == "__main__":
    unittest.main()
