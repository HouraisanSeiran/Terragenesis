import copy
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.drainage import resolve_dem_flats as resolve_dem_flats
from terrain_pipeline.underground_rivers import _seal, build_river_geometry, validate_river_geometry


def fixture(height):
    values = np.asarray(height, np.float64)
    candidate = {"arrays": {"height_m": values, "valid_mask": np.isfinite(values), "unknown_mask": ~np.isfinite(values)},
                 "grid": {"origin_x_m": 400000., "origin_z_m": -3200000., "spacing_x_m": 90.,
                          "spacing_z_m": 90., "crs": "EPSG:32651", "units": "metres"}}
    return candidate, resolve_dem_flats(candidate)


class RealDemRiver3DAdapterTests(unittest.TestCase):
    def build(self, candidate, flat, **options):
        return build_river_geometry(candidate, flat, min_contributing_cells=1, **options)

    def test_y_junction_two_tributaries_shared_nodes_banks_and_profiles(self):
        candidate, flat = fixture([[9, 8, 9], [7, 5, 7], [6, 1, 6]])
        result = self.build(candidate, flat)
        receiver = flat["network"].receiver.ravel()
        sources = np.flatnonzero(receiver >= 0)
        np.testing.assert_array_equal(result["edges"], np.column_stack((sources, receiver[sources])))
        np.testing.assert_array_equal(result["edge_ids"], sources)
        donors = np.bincount(receiver[sources], minlength=9)
        np.testing.assert_array_equal(result["donor_count"], donors)
        np.testing.assert_array_equal(result["junctions"], donors > 1)
        np.testing.assert_array_equal(result["heads"], donors == 0)
        np.testing.assert_array_equal(result["terminals"], receiver < 0)
        self.assertGreaterEqual(donors[7], 2)
        self.assertEqual(result["vertices"].shape, (18, 3))
        for edge, faces in zip(result["edges"], result["faces"].reshape(-1, 2, 3)):
            self.assertEqual(set(faces.ravel()), {2 * edge[0], 2 * edge[0] + 1,
                                                2 * edge[1], 2 * edge[1] + 1})
        np.testing.assert_array_equal(result["cross_sections"], np.tile([20., 1., 20.], (9, 1)))
        np.testing.assert_array_equal(result["node_xyz"][:, 1], candidate["arrays"]["height_m"].ravel())
        np.testing.assert_array_equal(result["vertices"][::2, 1], result["node_xyz"][:, 1] - 1.)
        self.assertTrue(validate_river_geometry(candidate, flat, result)["verified"])
        self.assertFalse(result["metadata"]["hydraulic_ready"])
        self.assertFalse(result["metadata"]["continuous_water_body_verified"])

    def test_threshold_downstream_closure_and_empty_selection(self):
        candidate, flat = fixture([[4, 3, 2, 1]])
        result = build_river_geometry(candidate, flat, min_contributing_cells=3)
        self.assertEqual(result["node_ids"].tolist(), [2, 3])
        self.assertEqual(result["edges"].tolist(), [[2, 3]])
        self.assertTrue(validate_river_geometry(candidate, flat, result)["verified"])
        empty = build_river_geometry(candidate, flat, min_contributing_cells=100)
        self.assertEqual(empty["node_xyz"].shape, (0, 3))
        self.assertEqual(empty["faces"].shape, (0, 3))
        self.assertTrue(validate_river_geometry(candidate, flat, empty)["verified"])

    def test_tile_sizes_and_flat_loading_orders_exact_hashes(self):
        candidate, flat = fixture([[4, 4, 3, 2], [4, np.nan, 3, 1]])
        expected = self.build(candidate, flat, tile_size=1)
        for size in (2, 256, 512):
            flat = resolve_dem_flats(candidate, tile_size=size, tile_order="reversed")
            result = self.build(candidate, flat, tile_size=size)
            self.assertEqual(result["content_sha256"], expected["content_sha256"])
            self.assertEqual(result["array_hashes"], expected["array_hashes"])
            self.assertTrue(validate_river_geometry(candidate, flat, result)["verified"])

    def test_coordinates_explicit_grid_and_source_unchanged(self):
        candidate, flat = fixture([[3, 2], [np.nan, 1]])
        before = array_hash(candidate["arrays"]["height_m"])
        result = self.build(candidate, flat, width_m=12., depth_m=2.)
        np.testing.assert_array_equal(result["node_xyz"][:, 0], [400000., 400090., 400090.])
        np.testing.assert_array_equal(result["node_xyz"][:, 2], [-3200000., -3200000., -3199910.])
        self.assertEqual(array_hash(candidate["arrays"]["height_m"]), before)
        records = {item["component_id"]: item for item in flat["components"]}
        np.testing.assert_array_equal(result["touches_unknown"],
            [records[int(component)]["touches_unknown"] for component in result["component_id"]])
        self.assertTrue(result["touches_unknown"].any())
        candidate["grid"]["units"] = "degrees"
        with self.assertRaises(ValueError):
            self.build(candidate, flat)

    def test_rehashed_array_class_edges_profile_mesh_and_claim_tampering_rejected(self):
        candidate, flat = fixture([[3, 2, 1]])
        original = self.build(candidate, flat)
        mutations = [lambda value: value["node_ids"].__setitem__(0, 1),
                     lambda value: value["node_xyz"].__setitem__((0, 1), 100.),
                     lambda value: value["edges"].__setitem__((0, 1), 2),
                     lambda value: value["junctions"].__setitem__(0, True),
                     lambda value: value["touches_unknown"].__setitem__(0, True),
                     lambda value: value["cross_sections"].__setitem__((0, 2), 99.),
                     lambda value: value["vertices"].__setitem__((0, 0), 99.),
                     lambda value: value["faces"].__setitem__((0, 0), 999),
                     lambda value: value["faces"].__setitem__((0, 0), 1),
                     lambda value: value["metadata"].update(hydraulic_ready=True),
                     lambda value: value["metadata"].update(natural_outlet_verified=True)]
        for mutation in mutations:
            result = copy.deepcopy(original)
            mutation(result)
            _seal(result)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_river_geometry(candidate, flat, result)
        altered = copy.deepcopy(flat)
        altered["network"].order[:] = altered["network"].order[::-1]
        with self.assertRaises(ValueError):
            validate_river_geometry(candidate, altered, original)

    def test_invalid_parameters_nonfinite_unknown_and_resource_budget(self):
        candidate, flat = fixture([[3, 2, 1]])
        for options in ({"width_m": True}, {"width_m": 0}, {"width_m": np.inf}, {"depth_m": -1},
                        {"depth_m": np.nan}, {"tile_size": True}, {"tile_size": 1025}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.build(candidate, flat, **options)
        for threshold in (True, 0, -1, np.inf, 500001):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                build_river_geometry(candidate, flat, min_contributing_cells=threshold)
        with self.assertRaises(ValueError):
            fixture([[np.nan]])
        huge = {"arrays": {"height_m": np.zeros((501, 1000)), "valid_mask": np.ones((501, 1000), bool)}}
        with self.assertRaises(ValueError):
            self.build(huge, {})
        candidate["grid"]["origin_x_m"] = np.inf
        with self.assertRaises(ValueError):
            self.build(candidate, flat)

    def test_validator_does_not_replay_builder(self):
        candidate, flat = fixture([[3, 2, 1]])
        result = self.build(candidate, flat)
        with patch('terrain_pipeline.underground_rivers.build_river_geometry', side_effect=AssertionError("no replay")):
            self.assertTrue(validate_river_geometry(candidate, flat, result)["verified"])


if __name__ == "__main__":
    unittest.main()
