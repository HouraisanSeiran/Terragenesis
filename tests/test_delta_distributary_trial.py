import unittest

import numpy as np

from tools.run_delta_distributary_trial import (
    microrelief, initial_product, candidate_anchors, diagnose_bar, stage_report, _widest, _graph,
)


class DistributaryTrialTests(unittest.TestCase):
    def test_corner_export_capacity_sums_both_marine_faces(self):
        original, _ = initial_product(False)
        product = {"arrays": {k: v.copy() for k, v in original["arrays"].items()},
                   "metadata": dict(original["metadata"])}
        product["metadata"]["last_coupling_interval_s"] = 10.
        faces = np.flatnonzero(product["arrays"]["boundary_cell"] == 0)
        self.assertEqual(len(faces), 2)
        product["arrays"]["boundary_last_water_transfer_m3"][faces] = [30., 40.]
        self.assertEqual(_graph(product)[2][0], 7.)

    def test_widest_sea_route_includes_export_face_capacity(self):
        graph = [[(1, 10.), (2, 5.)], [], []]
        path, capacity = _widest(graph, 0, {1: .01, 2: 3.}, np.ones(3, bool))
        self.assertEqual(path, [0, 2])
        self.assertEqual(capacity, 3.)

    def test_microrelief_is_absolute_coordinate_and_order_invariant(self):
        x = np.array([1374000., 1374030., 1374060.])
        z = np.array([1242000., 1242030., 1242060.])
        values = microrelief(x, z)
        np.testing.assert_array_equal(values[::-1], microrelief(x[::-1], z[::-1]))
        self.assertEqual(values[1], microrelief(x[1], z[1]))
        self.assertTrue(np.all(abs(values) <= .025))

    def test_cover_stock_is_finite_and_noise_is_not_deposition(self):
        flat, flat_excavation = initial_product(False)
        noise, noise_excavation = initial_product(True)
        self.assertEqual(flat_excavation, noise_excavation)
        self.assertAlmostEqual(flat["metadata"]["initial_bed_solid_m3"], noise["metadata"]["initial_bed_solid_m3"])
        self.assertGreater(flat["metadata"]["initial_bed_solid_m3"], 0.)
        self.assertEqual(candidate_anchors(noise), [])
        self.assertFalse(stage_report(noise, 100.)["local_material_distributary_passed"])
        self.assertEqual(stage_report(noise, 100.)["solid_budget_residual_m3"], 0.)

    def test_flat_inactive_bed_cannot_certify_distributaries(self):
        product, _ = initial_product(False)
        result = diagnose_bar(product, (16, 28), 100.)
        self.assertFalse(result["passed"])
        for section in result["sections"]:
            self.assertEqual(section["north"]["bed_below_bar_m"], 0.)
            self.assertEqual(section["south"]["westward_q_m3_s"], 0.)

    def test_local_channel_witness_requires_three_material_gates(self):
        original, _ = initial_product(False)
        product = {"arrays": {k: v.copy() for k, v in original["arrays"].items()},
                   "metadata": dict(original["metadata"])}
        a = product["arrays"]
        product["metadata"]["last_coupling_interval_s"] = 10.
        a["depth_m"][:] = 1.
        a["bed_m"][16, 26:31] = -.2
        a["bed_m"][[13, 19], :36] = -.7
        paths = []
        for row in (13, 19):
            cells = [16*48+c for c in range(46, 34, -1)]
            step = -1 if row < 16 else 1
            cells += [r*48+35 for r in range(16+step, row+step, step)]
            cells += [row*48+c for c in range(34, -1, -1)]
            paths.append(cells)
            for first, second in zip(cells, cells[1:]):
                face = ((a["face_left"] == first) & (a["face_right"] == second))
                reverse = ((a["face_left"] == second) & (a["face_right"] == first))
                a["internal_last_water_transfer_m3"][face] += 50.
                a["internal_last_water_transfer_m3"][reverse] -= 50.
            boundary = a["boundary_cell"] == row*48
            a["boundary_last_water_transfer_m3"][boundary] = 50.
        result = diagnose_bar(product, (16, 28), 10.)
        self.assertTrue(result["passed"])
        gate = (a["face_left"] == 13*48+28) & (a["face_right"] == 13*48+29)
        a["internal_last_water_transfer_m3"][gate] = -.01
        self.assertFalse(diagnose_bar(product, (16, 28), 10.)["passed"])


if __name__ == "__main__":
    unittest.main()
