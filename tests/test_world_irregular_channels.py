import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from terrain_pipeline.channel_geometry import DischargeGeometryConfig
from terrain_pipeline.world_irregular_channels import build_irregular_channel_geometry, query_reach_indices


class IrregularChannelTest(unittest.TestCase):
    def fixture(self, shape=(8, 10), spacing=1.):
        row, col = np.indices(shape)
        mesh = SimpleNamespace(node_x_m=(col + .2).ravel(), node_z_m=(row + .3).ravel(),
            origin_native_xz=(0, 0), spacing_m=spacing)
        bed = np.full(shape, 10.)
        receiver = np.full(bed.size, -1, np.int64)
        channel = np.zeros(shape, bool)
        return bed, mesh, receiver, channel

    def build(self, bed, mesh, receiver, channel, **kwargs):
        return build_irregular_channel_geometry(bed, np.ones(bed.shape), channel, mesh, receiver, **kwargs)

    def test_non_eight_direction_segment_has_analytic_cross_section(self):
        bed, mesh, receiver, channel = self.fixture()
        a, b = 11, 46
        receiver[a] = b
        channel.ravel()[a] = True
        result = self.build(bed, mesh, receiver, channel)
        graph, arrays = result["graph"], result["arrays"]
        self.assertEqual(graph["reach_source"].tolist(), [a])
        self.assertEqual(graph["reach_target"].tolist(), [b])
        self.assertNotEqual(abs(mesh.node_x_m[b] - mesh.node_x_m[a]), abs(mesh.node_z_m[b] - mesh.node_z_m[a]))
        self.assertTrue(arrays["cut_depth_m"].any())
        row, col = np.indices(bed.shape)
        dx, dz = mesh.node_x_m[b] - mesh.node_x_m[a], mesh.node_z_m[b] - mesh.node_z_m[a]
        t = np.clip(((col - mesh.node_x_m[a]) * dx + (row - mesh.node_z_m[a]) * dz) / (dx * dx + dz * dz), 0., 1.)
        distance = np.hypot(col - mesh.node_x_m[a] - t * dx, row - mesh.node_z_m[a] - t * dz)
        width, depth = graph["node_width_m"][a], graph["node_design_incision_depth_m"][a]
        expected = depth * np.clip((width / 2. - distance) / (width * .2), 0., 1.)
        np.testing.assert_allclose(arrays["cut_depth_m"], expected)
        np.testing.assert_array_equal(bed, 10.)

    def test_shared_confluence_uses_one_node_identity_and_section(self):
        bed, mesh, receiver, channel = self.fixture()
        receiver[[11, 15, 34]] = [34, 34, 66]
        channel.ravel()[[11, 15, 34]] = True
        result = self.build(bed, mesh, receiver, channel)
        graph = result["graph"]
        self.assertEqual(graph["reach_target"].tolist(), [34, 34, 66])
        self.assertEqual(graph["node_x_m"].size, bed.size)
        self.assertEqual(graph["node_width_m"][34], graph["node_width_m"][11])
        self.assertTrue(np.isfinite(result["arrays"]["final_bed_m"]).all())

    def test_subgrid_width_does_not_cut_every_touched_cell(self):
        bed, mesh, receiver, channel = self.fixture()
        receiver[11] = 17
        channel.ravel()[11] = True
        config = DischargeGeometryConfig(width_at_unit_q_m=.01)
        result = self.build(bed, mesh, receiver, channel, config=config)
        self.assertGreater(result["graph"]["node_width_m"][11], 0.)
        self.assertEqual(result["arrays"]["cut_depth_m"].sum(), 0.)

    def test_lake_ocean_unknown_terminal_anchors_do_not_cut(self):
        for mask_name, terminal_kind in (("lake_mask", 3), ("ocean_mask", 4), ("complete_mask", 2)):
            with self.subTest(mask=mask_name):
                bed, mesh, receiver, channel = self.fixture()
                receiver[11] = 13
                channel.ravel()[11] = True
                mask = np.zeros(bed.shape, bool)
                mask.ravel()[13] = True
                passed = ~mask if mask_name == "complete_mask" else mask
                result = self.build(bed, mesh, receiver, channel, **{mask_name: passed})
                self.assertEqual(result["graph"]["node_terminal_kind"][13], terminal_kind)
                self.assertEqual(result["graph"]["reach_target"].tolist(), [13])
                self.assertEqual(result["arrays"]["cut_depth_m"].ravel()[13], 0.)

    def test_unknown_or_protected_interior_blocks_cutting_shortcut(self):
        for mask_name in ("protected_mask", "complete_mask"):
            bed, mesh, receiver, channel = self.fixture()
            receiver[11] = 17
            channel.ravel()[11] = True
            mask = np.zeros(bed.shape, bool)
            mask.ravel()[14] = True
            passed = ~mask if mask_name == "complete_mask" else mask
            result = self.build(bed, mesh, receiver, channel, **{mask_name: passed})
            self.assertTrue(result["graph"]["reach_projection_blocked"][0])
            self.assertEqual(result["arrays"]["cut_depth_m"].sum(), 0.)

    def test_relief_is_bounded_and_excavation_is_unplaced(self):
        bed, mesh, receiver, channel = self.fixture()
        receiver[11] = 17
        channel.ravel()[11] = True
        bed[1, 14 % bed.shape[1]] = 100.
        result = self.build(bed, mesh, receiver, channel)
        self.assertLessEqual(result["arrays"]["cut_depth_m"].max(), 4.)
        self.assertTrue(result["graph"]["reach_max_cut_limited"][0])
        budget = result["metadata"]["material_budget"]
        self.assertEqual(budget["unplaced_excavated_bulk_m3"], result["arrays"]["cut_depth_m"].sum())
        self.assertFalse(budget["sediment_export_solved"])

    def test_material_response_and_npz_replay_bounds_query(self):
        bed, mesh, receiver, channel = self.fixture()
        receiver[11] = 46
        channel.ravel()[11] = True
        soft = self.build(bed, mesh, receiver, channel, bed_hardness=0.)
        hard = self.build(bed, mesh, receiver, channel, bed_hardness=1.)
        self.assertGreater(hard["graph"]["node_width_m"][11], soft["graph"]["node_width_m"][11])
        self.assertLess(hard["graph"]["node_design_incision_depth_m"][11], soft["graph"]["node_design_incision_depth_m"][11])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "graph.npz"
            np.savez(path, **soft["graph"])
            with np.load(path, allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved["node_x_m"], mesh.node_x_m)
                self.assertEqual(query_reach_indices(saved, 1., 1., 2., 2.).tolist(), [0])
                self.assertEqual(query_reach_indices(saved, 100., 100., 101., 101.).size, 0)

    def test_invalid_fields_rejected(self):
        bed, mesh, receiver, channel = self.fixture()
        for kwargs in ({"bed_hardness": -1.}, {"bank_hardness": np.nan}, {"protected_mask": np.zeros(bed.shape)}):
            with self.assertRaises(ValueError):
                self.build(bed, mesh, receiver, channel, **kwargs)


if __name__ == "__main__":
    unittest.main()
