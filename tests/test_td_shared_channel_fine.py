from collections import defaultdict
from copy import deepcopy
import unittest

import numpy as np

from terrain_pipeline.common_infra import identity
from terrain_pipeline import channel_geometry as source
from terrain_pipeline.td_shared_channel_fine import (
    SPACING_M, TILE_CELLS, BudgetExceeded, _center_cut, build_tile, compact_node_fans,
    plan_tiles, seal, verify_integral_conservation)
from tools.prepare_td_shared_channel_fine import load_channel


def fixture():
    spacing = SPACING_M
    vertices = [[spacing * .6, spacing * .6], [spacing * 1.4, spacing * .6], [spacing * .6, spacing * 1.4]]
    fan = {"fan_id": "tiny:fan:0", "vertices_xz_m": vertices, "depth_at_vertices_m": [.2, .4, .6],
        "depth_origin_xz_m": vertices[0], "depth_coefficients_m_1xz": [.2, .2 / (.8 * spacing), .4 / (.8 * spacing)],
        "boundary_segment_id": "edge:0"}
    function = seal({"triangle_id": "tiny:face:0", "status": "candidate", "rejection_reasons": [], "fans": [fan]})
    record = seal({"node_id": "tiny", "status": "candidate", "rejection_reasons": [], "source_functions": [function]})
    rows, columns = np.indices((3, 3))
    arrays = {"height_m": 10. + rows + columns + .3 * rows * columns,
        "valid_mask": np.ones((3, 3), bool), "protected_mask": np.zeros((3, 3), bool),
        "open_boundary_mask": np.zeros((3, 3), bool), "cell_owner": np.zeros((3, 3), np.int64),
        "contribution_owner": np.zeros((3, 3), np.int64), "node_unknown_contact": np.zeros(1, bool)}
    metadata = {"origin_m_xz": [0., 0.], "spacing_m": 1., "source_identity_sha256": "a" * 64}
    hierarchy = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    context = source._i46__context(hierarchy, [0], {"covered_native_cell_ids": [], "stage_by_leaf": []})
    return record, {"origin_m_xz": [0., 0.], "spacing_m": SPACING_M, "tile_cells": TILE_CELLS}, context


class SharedChannelFineTests(unittest.TestCase):
    def test_partial_cell_exact_affine_integral_outside_centers_and_unique_sparse_keys(self):
        record, grid, context = fixture()
        fans = compact_node_fans(record)
        plan = plan_tiles(fans, grid)
        self.assertEqual(plan["unique_cell_count"], 3)
        accumulated = defaultdict(lambda: [[], []])
        tiles = []
        for tile_key in sorted(plan["tile_masks"]):
            tile = build_tile(fans, plan, tile_key, grid, context, fan_parent_identity="a" * 64)
            tiles.append(tile)
            for integral in tile["fan_integrals"]:
                accumulated[integral["fan_key"]][0].append(integral["coverage_area_m2"])
                accumulated[integral["fan_key"]][1].append(integral["integrated_cut_m3"])
        integrals = verify_integral_conservation(fans, accumulated)
        expected = .32 * SPACING_M**2 * .4
        self.assertAlmostEqual(sum(tile["material_ledger"]["cut_rock_m3"] for tile in tiles), expected, places=14)
        self.assertAlmostEqual(integrals[0]["coverage_area_m2"], .32 * SPACING_M**2, places=14)
        self.assertEqual(sum(tile["center_sample_cut_volume_m3"] for tile in tiles), 0.)
        cells = [cell for tile in tiles for cell in tile["cells"]]
        self.assertEqual(len({(cell["global_row"], cell["global_col"]) for cell in cells}), 3)
        self.assertTrue(all(not cell["center_inside"] and cell["derived_bed_m"] == cell["source_height_m"] for cell in cells))
        self.assertTrue(all(cell["integrated_cut_m3"] > 0. for cell in cells))
        self.assertAlmostEqual(tiles[0]["material_ledger"]["exported_excavated_rock_m3"], expected, places=14)
        self.assertEqual(tiles[0]["material_ledger"]["solid_fill_m3"], 0.)
        self.assertEqual(_center_cut(fans[0], np.asarray(fans[0]["vertices_xz_m"][0])), .2)

    def test_whole_package_budget_illegal_depth_and_unpassed_parent_are_rejected(self):
        record, grid, context = fixture()
        fans = compact_node_fans(record)
        with self.assertRaises(BudgetExceeded):
            plan_tiles(fans, grid, max_cells=1)
        with self.assertRaisesRegex(ValueError, "duplicate saved fan"):
            plan_tiles(fans + fans, grid)
        for depth in (-1e-16, 4.000000000000001):
            changed = deepcopy(record)
            function = changed["source_functions"][0]
            function["fans"][0]["depth_at_vertices_m"][0] = depth
            seal(function)
            with self.assertRaisesRegex(ValueError, "strict saved fan"):
                compact_node_fans(changed)
        with self.assertRaisesRegex(ValueError, "fixed actual passed"):
            load_channel({"path": "unused", "sha256": "0" * 64}, {"path": "unused", "sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
