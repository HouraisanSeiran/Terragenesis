import unittest

import numpy as np

from terrain_pipeline.surface_hydraulics import RerouteRecipe, reroute_channel
from terrain_pipeline.channel_geometry import ChannelRecipe, plan_channel
from terrain_pipeline.surface_domain import SurfaceNetworkBudget, prepare_surface_network, save_surface_network, load_surface_network
import tempfile
from pathlib import Path
from terrain_pipeline.channel_geometry import SectionRecipe
from terrain_pipeline.surface_hydraulics import StageRecipe
from terrain_pipeline.surface_hydraulics import InundationRecipe


def conservative_plan():
    shape = (5, 5)
    height = np.full(shape, 10.)
    receiver = np.full(25, -1, dtype=np.int64)
    for source, target in ((6, 11), (8, 13), (11, 12), (13, 12), (12, 17), (17, 22)):
        receiver[source] = target
    outlets = (receiver == -1).reshape(shape)
    order = []
    seen = set()
    def visit(cell):
        if cell in seen: return
        if receiver[cell] >= 0: visit(int(receiver[cell]))
        seen.add(cell); order.append(cell)
    for cell in range(25): visit(cell)
    q = np.zeros(25)
    q[[6, 8]] = .1
    for cell in order[::-1]:
        if receiver[cell] >= 0: q[receiver[cell]] += q[cell]
    return plan_channel(height, receiver, np.array(order, dtype=np.int64), outlets,
        q.reshape(shape), 1., 1., 0., 0., 0., "conservative-reroute", ChannelRecipe(
            start_discharge_m3_s=.05, reference_discharge_m3_s=.1,
            reference_width_m=2., min_width_m=2., max_width_m=2.,
            reference_depth_m=.5, min_depth_m=.5, max_depth_m=.5, max_cut_m=4.))


class ChannelRerouteTests(unittest.TestCase):
    def test_explicit_reroute_recomputes_graph_and_q(self):
        plan = conservative_plan()
        domain = np.ones((5, 5), bool)
        protected = np.zeros((5, 5), bool)
        protected[1, 2] = True
        result = reroute_channel(plan, (1, 1), (3, 2), domain, protected,
                                 RerouteRecipe(max_path_cells=10))
        path = result["path_grid_zx"]
        self.assertEqual(path[0], [1, 1]); self.assertEqual(path[-1], [3, 2])
        self.assertNotIn([1, 2], path)
        self.assertEqual(result["plan"]["arrays"]["discharge_m3_s"][3, 2], .2)
        self.assertNotEqual(result["plan"]["identity_sha256"], plan["identity_sha256"])

    def test_protected_end_and_no_path_rejected(self):
        plan = conservative_plan()
        domain = np.ones((5, 5), bool)
        protected = np.zeros((5, 5), bool); protected[1, 1] = True
        with self.assertRaises(ValueError):
            reroute_channel(plan, (1, 1), (3, 2), domain, protected)

    def test_rerouted_plan_runs_joint_diagnostic(self):
        plan = conservative_plan()
        domain = np.ones((5, 5), bool)
        protected = np.zeros((5, 5), bool); protected[1, 2] = True
        rerouted = reroute_channel(plan, (1, 1), (3, 2), domain, protected)
        fine_shape = (9, 9)
        fine_domain = np.ones(fine_shape, bool)
        fine_protected = np.zeros(fine_shape, bool)
        fine_protected[2, 4] = True
        legal = np.zeros(fine_shape, bool); legal[-1, 3:6] = True
        result = prepare_surface_network(rerouted["plan"], 0., 0., .5, .5, fine_shape,
            fine_domain, fine_protected, legal, np.array([9.8]), SectionRecipe(),
            StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
            InundationRecipe(max_lateral_reach_m=5.), SurfaceNetworkBudget(4., 100., 100.))
        self.assertIn("joint_blockers", result["summary"])
        self.assertEqual(result["summary"]["inundation"]["channel_seed_nodes"],
                         int(result["arrays"]["channel_seed_mask"].sum()))
        self.assertEqual(result["status"], "prepared")
        self.assertFalse(any(result["summary"]["joint_blockers"].values()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rerouted.npz"
            save_surface_network(result, path)
            self.assertEqual(load_surface_network(path)["identity_sha256"], result["identity_sha256"])
        protected[1, 1] = False
        domain[2, :] = False
        with self.assertRaises(ValueError):
            reroute_channel(plan, (1, 1), (3, 2), domain, protected)


if __name__ == "__main__": unittest.main()
