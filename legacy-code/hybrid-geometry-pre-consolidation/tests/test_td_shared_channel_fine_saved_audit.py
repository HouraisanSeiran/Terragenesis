"""Tiny independent sampling/integration and sparse ownership regressions."""

from copy import deepcopy
import unittest

import numpy as np

from tools.td_shared_channel_fine_saved_audit import (
    LEDGER_KEYS, Fan, GlobalGrid, NativeSource, audit_tile,
    cell_intersection, expected_tile_intersections)


def fixture():
    source = NativeSource({"height_m": np.array([[10., 12.], [13., 17.]]),
        "valid_mask": np.ones((2, 2), bool), "protected_mask": np.zeros((2, 2), bool),
        "open_boundary_mask": np.zeros((2, 2), bool), "cell_owner": np.zeros((2, 2), int),
        "contribution_owner": np.zeros((2, 2), int), "node_unknown_contact": np.zeros(1, bool)},
        {"origin_m_xz": [0., 0.], "spacing_m": 1.}, {0},
        {"covered_native_cell_ids": [], "stage_by_leaf": []})
    fan = Fan({"fan_key": "saved-fan", "fan_id": "saved-fan",
        "vertices_xz_m": [[0., 0.], [1., 0.], [0., 1.]], "depth_at_vertices_m": [1., 2., 3.],
        "depth_origin_xz_m": [0., 0.], "depth_coefficients_m_1xz": [1., 1., 2.],
        "projected_area_m2": .5, "expected_integrated_cut_m3": 1.})
    grid = {"origin_m_xz": [.25, .25], "spacing_m": 1., "tile_cells": 2}
    return source, fan, grid


def tiny_tile(source, fan, grid):
    polygon, area, volume = cell_intersection(fan, 0, 0, grid)
    sample = source.sample([.75, .75])
    contribution = {"fan_key": fan.key, "fan_id": fan.key, "global_row": 0, "global_col": 0,
        "local_index": 0, "polygon_cell_local_uv_cut_m": polygon,
        "polygon_xz_m": [[.25+point[0], .25+point[1]] for point in polygon],
        "coverage_area_m2": area, "integrated_cut_m3": volume}
    cell = {"global_row": 0, "global_col": 0, "local_index": 0, "center_xz_m": [.75, .75],
        "source_sample": sample, "source_height_m": sample["height_m"], "derived_bed_m": sample["height_m"],
        "cut_depth_m": 0., "center_inside": False, "center_fan_keys": [], "valid": True,
        "coverage_area_m2": area, "integrated_cut_m3": volume, "contribution_indices": [0]}
    return {"grid": grid, "tile_row_column": [0, 0], "global_origin_row_column": [0, 0],
        "cells": [cell], "contributions": [contribution],
        "fan_integrals": [{"fan_key": fan.key, "fan_id": fan.key, "coverage_area_m2": area, "integrated_cut_m3": volume}],
        "material_ledger": {key: volume if key in ("cut_rock_m3", "exported_excavated_rock_m3") else 0. for key in LEDGER_KEYS},
        "center_sample_cut_volume_m3": 0.}


class SavedFineAuditTests(unittest.TestCase):
    def test_native_affine_partial_cell_and_strict_supports(self):
        source, fan, grid = fixture()
        self.assertEqual(source.sample([.75, .75])["height_m"], 14.875)
        polygon, area, volume = cell_intersection(fan, 0, 0, grid)
        self.assertEqual(area, .125)
        self.assertEqual(volume, .28125)
        self.assertIsNone(fan.center_cut([.75, .75]))
        self.assertEqual(fan.center_cut([0., 1.]), 3.)
        for field, value in (("depth_at_vertices_m", [-1e-16, 2., 3.]),
                             ("depth_at_vertices_m", [1., 2., 4.0000000001]),
                             ("depth_coefficients_m_1xz", [1., 1., 20.])):
            forged = deepcopy(fan.saved)
            forged[field] = value
            with self.assertRaises(ValueError):
                Fan(forged)
        expected = {0: {fan.key: (polygon, area, volume)}}
        result = audit_tile(tiny_tile(source, fan, grid), {fan.key: fan}, expected, source, GlobalGrid(grid))
        self.assertEqual(result["integrated_cut_m3"], .28125)
        self.assertEqual(result["center_sample_cut_volume_m3"], 0.)
        self.assertEqual(result["outside_fan_centers"], 1)

    def test_unique_grid_and_missing_or_forged_geometry_rejected(self):
        source, fan, grid = fixture()
        owner = GlobalGrid(grid)
        owner.begin_tile([0, 0])
        cell = {"global_row": 0, "global_col": 0, "local_index": 0}
        owner.accept_cell(cell)
        with self.assertRaises(ValueError):
            owner.accept_cell(cell)
        with self.assertRaises(ValueError):
            owner.begin_tile([0, 0])
        with self.assertRaises(ValueError):
            owner.accept_cell({"global_row": 0, "global_col": 2, "local_index": 0})
        tile = tiny_tile(source, fan, grid)
        polygon, area, volume = cell_intersection(fan, 0, 0, grid)
        expected = {0: {fan.key: (polygon, area, volume)}}
        all_expected = expected_tile_intersections({fan.key: fan}, [fan.key], (0, 0), grid)
        self.assertEqual(all_expected[0], expected[0])
        for mutation in ("integral", "polygon", "reference", "omission", "outside_bed"):
            forged = deepcopy(tile)
            if mutation == "integral":
                forged["contributions"][0]["integrated_cut_m3"] += .01
            elif mutation == "polygon":
                forged["contributions"][0]["polygon_cell_local_uv_cut_m"][0][2] += .01
            elif mutation == "reference":
                forged["cells"][0]["contribution_indices"] = []
            elif mutation == "omission":
                forged["contributions"] = []
            else:
                forged["cells"][0]["derived_bed_m"] -= .01
            with self.assertRaises(ValueError):
                audit_tile(forged, {fan.key: fan}, expected, source, GlobalGrid(grid))


if __name__ == "__main__":
    unittest.main()
