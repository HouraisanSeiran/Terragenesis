import unittest

import numpy as np

from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import masked_mesh as masked_mesh
from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
from terrain_pipeline.drainage import strict_receivers as strict_receivers
from terrain_pipeline.surface_rivers.native_30m_source import build_strict_topology
from terrain_pipeline.surface_rivers.native_30m_hydrology_ledger import window_terminal_kind
from terrain_pipeline.surface_rivers.metric_depression_gate import unfilled_catchment_flow
from terrain_pipeline.surface_rivers.natural_outlet_status import derived_unknown_mask


class MetricIrregularStrictTests(unittest.TestCase):
    def test_fractional_metric_frame_anisotropic_lengths_and_raw_slope(self):
        mesh = grid_mesh((9, 11), x0_m=-17.25, z0_m=102.5, dx_m=7., dz_m=19.)
        bed = (mesh.node_x_m * .3 + mesh.node_z_m * .8).reshape(mesh.shape)
        before = bed.copy()
        receiver, length, slope = strict_receivers(bed, mesh)
        self.assertTrue(receiver_edges_valid(receiver, mesh))
        for node in np.flatnonzero(receiver >= 0):
            edges = slice(mesh.indptr[node], mesh.indptr[node + 1])
            targets = mesh.indices[edges]
            slopes = (bed.flat[node] - bed.ravel()[targets]) / mesh.edge_length_m[edges]
            self.assertAlmostEqual(slope[node], float(slopes.max()))
            self.assertAlmostEqual(length[node], np.hypot(
                mesh.node_x_m[node] - mesh.node_x_m[receiver[node]],
                mesh.node_z_m[node] - mesh.node_z_m[receiver[node]]))
        np.testing.assert_array_equal(bed, before)

    def test_masked_graph_cannot_cross_unknown_corner_or_barrier(self):
        mesh = grid_mesh((7, 9))
        valid = np.ones(mesh.shape, bool)
        valid[:, 4] = False
        masked = masked_mesh(mesh, valid)
        for node in range(valid.size):
            for target in masked.indices[masked.indptr[node]:masked.indptr[node + 1]]:
                self.assertTrue(valid.flat[node] and valid.flat[target])
                self.assertEqual(node % 9 < 4, target % 9 < 4)
        corner = np.array([[True, False], [False, True]])
        tiny = masked_mesh(grid_mesh(corner.shape), corner)
        self.assertEqual(tiny.indices.size, 0)

    def test_native_overlap_preserves_absolute_positions_and_interior_receivers(self):
        z, x = np.indices((19, 21))
        bed = 100. + x * .3 + z * .7
        full = build_strict_topology(bed, np.ones(bed.shape, bool), origin_native_xz=(-8, 11))
        sub_bed = bed[3:16, 4:18]
        sub = build_strict_topology(sub_bed, np.ones(sub_bed.shape, bool), origin_native_xz=(-4, 14))
        for name in ("node_x_m", "node_z_m"):
            np.testing.assert_array_equal(full[name][3:16, 4:18], sub[name])
        for row in range(4, 9):
            for col in range(4, 10):
                target = int(sub["receiver"][row, col])
                target_row, target_col = divmod(target, sub_bed.shape[1])
                self.assertEqual(full["receiver"][row + 3, col + 4],
                                 (target_row + 3) * bed.shape[1] + target_col + 4)

    def test_native_terminal_account_uses_same_graph_support_rule(self):
        bed = np.ones((15, 17))
        valid = np.ones(bed.shape, bool)
        valid[5, 6] = False
        topology = build_strict_topology(bed, valid, origin_native_xz=(-10, 8))
        declaration = window_terminal_kind(topology["receiver"], valid, origin_native_xz=(-10, 8))
        np.testing.assert_array_equal(declaration["terminal_kind"], topology["terminal_kind"])
        np.testing.assert_array_equal(derived_unknown_mask(valid, origin_native_xz=(-10, 8)),
                                      topology["upstream_unknown_mask"])
        self.assertFalse(np.any(topology["upstream_unknown_mask"][~valid]))

    def test_raw_catchment_counts_conserve_and_flats_remain_sinks(self):
        mesh = grid_mesh((8, 9), x0_m=-33., z0_m=82., dx_m=12., dz_m=7.)
        bed = (mesh.node_x_m + mesh.node_z_m).reshape(mesh.shape)
        count, receiver, sinks = unfilled_catchment_flow(bed, mesh=mesh)
        self.assertEqual(float(count[sinks].sum()), float(bed.size))
        self.assertTrue(receiver_edges_valid(receiver, mesh))
        count, receiver, sinks = unfilled_catchment_flow(np.zeros(mesh.shape), mesh=mesh)
        self.assertTrue(sinks.all())
        self.assertTrue(np.all(receiver == -1))
        np.testing.assert_array_equal(count, np.ones(bed.size))


if __name__ == "__main__":
    unittest.main()
