"""Independent audit regressions for narrow bed reversals and material ledgers."""

import copy
import unittest

import numpy as np

from terrain_pipeline.channel_geometry import build_channel_geometry
from terrain_pipeline.surface_rivers.metric_sediment import solve_sediment, SedimentConfig
from tools.verify_td_river_geometry import fixture
from tools.verify_td_river_sediment import benchmark
from tools.audit_td_river_geometry_sediment import (
    independent_continuous_bed, independent_sediment, independent_source_and_cut,
)


class IndependentReviewTests(unittest.TestCase):
    def test_continuous_audit_detects_single_fine_vertex_reverse_slope(self):
        terrain, ids, receiver, args = fixture("single")
        good = build_channel_geometry(terrain, ids, receiver, **args)
        independent_continuous_bed(good)
        forged = {"arrays": {key: value.copy() for key, value in good["arrays"].items()},
                  "metadata": copy.deepcopy(good["metadata"]), "identity_sha256": good["identity_sha256"]}
        coordinates = forged["arrays"]["vertices_xz_m"]
        midpoint = forged["arrays"]["node_xz_m"][1:3].mean(axis=0)
        index = int(np.argmin(np.linalg.norm(coordinates - midpoint, axis=1)))
        forged["arrays"]["bed_elevation_m"][index] -= 2.
        with self.assertRaisesRegex(AssertionError, "uphill"):
            independent_continuous_bed(forged)

    def test_independent_source_and_cut_detects_restored_wet_cell_cut(self):
        terrain, ids, receiver, args = fixture("lake")
        good = build_channel_geometry(terrain, ids, receiver, **args)
        independent_source_and_cut(good)
        forged = {"arrays": {key: value.copy() for key, value in good["arrays"].items()},
                  "metadata": copy.deepcopy(good["metadata"]), "identity_sha256": good["identity_sha256"]}
        vertices = forged["arrays"]["vertices_xz_m"]
        index = int(np.argmin(np.linalg.norm(vertices - [45., 40.], axis=1)))
        forged["arrays"]["cut_depth_m"][index] = .001
        forged["arrays"]["bed_elevation_m"][index] -= .001
        with self.assertRaises(AssertionError):
            independent_source_and_cut(forged)

    def test_independent_material_audit_rejects_same_total_wrong_donor(self):
        domain, forcing, material, mobile = benchmark("y")
        good = solve_sediment(domain, forcing, material, mobile, SedimentConfig(max_dt_seconds=.5))
        independent_sediment(good)
        forged = {"arrays": {key: value.copy() for key, value in good["arrays"].items()},
                  "metadata": copy.deepcopy(good["metadata"]), "identity_sha256": good["identity_sha256"]}
        # A wrong recipient can conserve the global sum while breaking the actual junction.
        incoming = forged["arrays"]["step_incoming_solid_m3"]
        amount = incoming[0, 2]
        self.assertGreater(amount, 0.)
        incoming[0, 2] -= amount
        incoming[0, 3] += amount
        with self.assertRaises(AssertionError):
            independent_sediment(forged)


if __name__ == "__main__":
    unittest.main()
