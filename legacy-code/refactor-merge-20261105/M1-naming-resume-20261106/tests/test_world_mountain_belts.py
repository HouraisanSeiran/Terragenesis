"""External contracts for finite coarse ranges; synthetic cases are not visual acceptance."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.tectonic import CrustState, TectonicConfig, evolve
from terrain_pipeline.tectonic import freeze, load_product as load_base
from terrain_pipeline.mountain_forms import WORLD_SEED, WorldMountainConfig, _ridge_height, load_belt_product as load_product, prepare_world_mountain_belts, save_belt_product as save_product


ROOT = Path(__file__).resolve().parents[1]


def background(*, direction=1, thick=False, gap=False):
    config = TectonicConfig(shape=(16, 24), plate_count=2, steps=0,
                            origin_x_m=-120000., origin_z_m=-80000.)
    coverage = np.zeros((2, *config.shape))
    coverage[0, :, :12] = 1
    coverage[1, :, 12:] = 1
    continental = coverage * 35000
    oceanic = np.zeros_like(coverage)
    continental[:, :, :2] = 0
    oceanic[:, :, :2] = coverage[:, :, :2] * 7000
    if thick:
        continental[:, 2:14, 10:14] = coverage[:, 2:14, 10:14] * 52000
    if gap:
        continental[:, 7:9, :] = 0
        oceanic[:, 7:9, :] = coverage[:, 7:9, :] * 7000
    # A genuinely enclosed non-ocean negative depression.
    continental[:, 5, 5] = coverage[:, 5, 5] * 28000
    state = CrustState(coverage, continental, oceanic,
        np.array([[-70000., 0.], [70000., 0.]]),
        np.array([[1000. * direction, 0.], [-1000. * direction, 0.]]))
    return freeze(config, evolve(config, state))


class WorldMountainBeltsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = background()
        cls.product = prepare_world_mountain_belts(cls.base)

    def test_convergent_direction_and_divergent_transform_exclusion(self):
        inventory = self.product.manifest["source_inventory"]
        self.assertEqual(inventory["boundary_counts"]["convergent_faces"], 16)
        self.assertEqual(len(inventory["candidates"]), 1)
        self.assertEqual(inventory["candidates"][0]["kind"], "convergent_boundary")
        self.assertGreater(self.product.arrays["mountain_height_m"].max(), 500)
        for direction in (-1, 0):
            product = prepare_world_mountain_belts(background(direction=direction))
            self.assertEqual(product.manifest["source_inventory"]["ridges"], [])
            self.assertFalse(np.any(product.arrays["mountain_height_m"]))

    def test_disconnected_boundary_is_not_bridged_across_sea(self):
        product = prepare_world_mountain_belts(background(gap=True))
        candidates = product.manifest["source_inventory"]["candidates"]
        self.assertEqual(len(candidates), 2)
        for candidate in candidates:
            points = np.asarray(candidate["vertices_m"])
            self.assertTrue(np.all(points[:, 1] < -10000) or np.all(points[:, 1] > 10000))

    def test_thick_crust_prior_is_recorded_without_inventing_history(self):
        product = prepare_world_mountain_belts(background(direction=0, thick=True))
        candidates = product.manifest["source_inventory"]["candidates"]
        self.assertTrue(candidates)
        self.assertEqual({c["kind"] for c in candidates}, {"thick_crust_morphology_prior"})
        self.assertTrue(all(c["threshold_m"] == 40000 for c in candidates))
        self.assertGreater(product.arrays["mountain_height_m"].max(), 0)

    def test_determinism_and_separate_historical_seed(self):
        other = prepare_world_mountain_belts(self.base)
        self.assertEqual(other.identity, self.product.identity)
        self.assertEqual(other.manifest["world_seed"], WORLD_SEED)
        self.assertEqual(other.manifest["base_world_seed"], 20261020)
        self.assertEqual(other.manifest["base_source"]["identity"], self.base.identity)
        for key in other.arrays:
            np.testing.assert_array_equal(other.arrays[key], self.product.arrays[key])

    def test_same_frozen_geometry_across_grid_spacing(self):
        finer = prepare_world_mountain_belts(self.base, WorldMountainConfig(spacing_m=2000))
        self.assertEqual(finer.manifest["source_inventory"], self.product.manifest["source_inventory"])
        x = np.array([-118001., -100000., -15123., 173., 87654.])
        z = np.array([-77999., -50000., 17000., 34123., 71001.])
        coarse_values = self.product.evaluate_geometry(x, z)
        fine_values = finer.evaluate_geometry(x, z)
        for key in coarse_values:
            np.testing.assert_array_equal(coarse_values[key], fine_values[key])

    def test_no_evolution_no_wrap_and_read_only_query(self):
        with patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError), \
                patch.object(type(self.base), "sample", side_effect=AssertionError):
            product = prepare_world_mountain_belts(self.base)
            first = product.evaluate_geometry(-120000., -75000.)
            source = self.base.arrays["final/elevation_m"][0, 0]
            self.assertEqual(float(first["raw_elevation_m"]), source)
            result = product.query(-120000., -80000.)
            self.assertEqual(float(result["elevation_m"]), product.arrays["elevation_m"][0, 0])
        for values in product.arrays.values():
            with self.assertRaises(ValueError):
                values.setflags(write=True)
        manifest = product.manifest
        manifest["world_seed"] = 9
        self.assertEqual(product.manifest["world_seed"], WORLD_SEED)

    def test_query_centres_reverse_overlap_and_no_cache_growth(self):
        grid = self.product.manifest["grid"]
        x = grid["origin_x_m"] + (np.arange(grid["shape"][1]) + .5) * grid["spacing_m"]
        z = grid["origin_z_m"] + (np.arange(grid["shape"][0]) + .5) * grid["spacing_m"]
        before = set(vars(self.product))
        values = self.product.query(x[None, :], z[:, None])
        reverse = self.product.query(x[::-1][None, :], z[::-1, None])
        overlap = self.product.query(x[10:20][None, :], z[3:15, None])
        for key in values:
            np.testing.assert_array_equal(values[key], self.product.arrays[key])
            np.testing.assert_array_equal(reverse[key][::-1, ::-1], values[key])
            np.testing.assert_array_equal(overlap[key], values[key][3:15, 10:20])
        self.assertEqual(set(vars(self.product)), before)

    def test_bent_ridge_bisector_has_continuous_peak_phase(self):
        inventory = self.product.manifest["source_inventory"]
        inventory["ridges"] = [{"source_id": "bent-test", "role": "main", "style": "folded_ranges",
            "vertices_m": [[-50000., 0.], [0., 0.], [0., 50000.]], "width_m": 30000.,
            "amplitude_m": 2000., "peak_spacing_m": 45000., "phase": .8, "cross_power": 1.5}]
        inventory["basins"] = []
        with patch('terrain_pipeline.mountain_forms._inventory', return_value=inventory):
            product = prepare_world_mountain_belts(self.base)
        differences = []
        # Both arms are equally close at (-20km,+20km), but their projection
        # arclengths are 30km and 70km. Hard nearest-arm phase would jump here.
        for epsilon in (1., .01, .0001):
            values = product.evaluate_geometry(np.array([-20000., -20000.]),
                np.array([20000. - epsilon, 20000. + epsilon]))["mountain_height_m"]
            differences.append(float(abs(values[1] - values[0])))
        self.assertLess(differences[-1], .0001)
        self.assertLess(differences[1], differences[0] * .02)
        self.assertLess(differences[2], differences[1] * .02)

    def test_ocean_inland_negative_and_stage_composition(self):
        arrays = self.product.arrays
        ocean = arrays["ocean_connected"]
        self.assertTrue(np.any(arrays["inland_depression"]))
        self.assertFalse(np.any(ocean & arrays["inland_depression"]))
        np.testing.assert_array_equal(arrays["elevation_m"][ocean], arrays["raw_elevation_m"][ocean])
        self.assertFalse(np.any(arrays["mountain_height_m"][ocean]))
        self.assertFalse(np.any(arrays["basin_depth_m"][ocean]))
        np.testing.assert_allclose(arrays["elevation_m"], arrays["base_elevation_m"]
                                   + arrays["mountain_height_m"] - arrays["basin_depth_m"], atol=.0005)
        inland = arrays["inland_depression"]
        np.testing.assert_array_equal(arrays["elevation_m"][inland], arrays["raw_elevation_m"][inland])
        disabled = prepare_world_mountain_belts(self.base, WorldMountainConfig(flatten_base=False, amplitude_scale=0))
        np.testing.assert_array_equal(disabled.arrays["elevation_m"], disabled.arrays["raw_elevation_m"])

    def test_invalid_coordinates_configuration_and_budgets(self):
        for x, z in ((-120001., 0), (120000., 0), (0, 80000.), (0, -80001.), (np.nan, 0), (0, np.inf)):
            for method in (self.product.query, self.product.evaluate_geometry):
                with self.assertRaises(ValueError):
                    method(x, z)
        for kwargs in ({"spacing_m": 0}, {"spacing_m": np.nan}, {"world_seed": True},
                       {"max_belts": 0}, {"amplitude_scale": -1}):
            with self.assertRaises(ValueError):
                WorldMountainConfig(**kwargs)
        for kwargs in ({"max_cells": 10}, {"max_source_cells": 10},
                       {"max_segments": 1}, {"spacing_m": 7000}):
            with self.assertRaises(ValueError):
                prepare_world_mountain_belts(self.base, WorldMountainConfig(**kwargs))

    def test_save_cold_read_no_overwrite_and_tamper_rejection(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".scratch") as directory:
            path = Path(directory) / "product.npz"
            save_product(self.product, path)
            with patch('terrain_pipeline.mountain_forms.prepare_world_mountain_belts', side_effect=AssertionError):
                loaded = load_product(path, expected_identity=self.product.identity)
                np.testing.assert_array_equal(loaded.evaluate_geometry(0, 0)["elevation_m"],
                                              self.product.evaluate_geometry(0, 0)["elevation_m"])
            with self.assertRaises(FileExistsError):
                save_product(self.product, path)
            with self.assertRaises(ValueError):
                load_product(path, expected_identity="wrong")
            with np.load(path, allow_pickle=False) as archive:
                payload = {k: archive[k].copy() for k in archive.files}
            payload["elevation_m"][4, 4] += 1
            bad = Path(directory) / "tampered.npz"
            np.savez(bad, **payload)
            with self.assertRaises(ValueError):
                load_product(bad)

    def test_real_source_has_curved_main_parallel_branch_peak_saddles(self):
        path = ROOT / ".scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz"
        if not path.exists():
            self.skipTest("local shaped-v4 source unavailable")
        base = load_base(path)
        product = prepare_world_mountain_belts(base)
        inventory = product.manifest["source_inventory"]
        self.assertEqual({r["role"] for r in inventory["ridges"]}, {"main", "parallel", "oblique_branch"})
        self.assertEqual(len({r["style"] for r in inventory["ridges"]}), 3)
        self.assertTrue(inventory["basins"])
        self.assertGreater(product.arrays["basin_depth_m"].max(), 100)
        main = max((r for r in inventory["ridges"] if r["role"] == "main"),
                   key=lambda r: np.linalg.norm(np.diff(r["vertices_m"], axis=0), axis=1).sum())
        points = np.asarray(main["vertices_m"])
        self.assertGreater(np.linalg.norm(np.diff(points, axis=0), axis=1).sum(), np.linalg.norm(points[-1] - points[0]) * 1.01)
        length = np.concatenate(([0.], np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))))
        distance = np.linspace(length[-1] * .1, length[-1] * .9, 200)
        x = np.interp(distance, length, points[:, 0])
        z = np.interp(distance, length, points[:, 1])
        values = product.evaluate_geometry(x, z)["mountain_height_m"]
        extrema = np.diff(np.sign(np.diff(values)))
        self.assertGreater(np.count_nonzero(extrema < 0), 2)
        self.assertGreater(float(np.ptp(values)), 300)

    def test_real_ocean_cell_faces_have_continuous_geometry(self):
        path = ROOT / ".scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz"
        if not path.exists():
            self.skipTest("local shaped-v4 source unavailable")
        base = load_base(path)
        product = prepare_world_mountain_belts(base)
        ocean = base.arrays["final/ocean_connected"]
        config = base.manifest["config"]
        spacing = config["cell_size_m"]
        for axis in (0, 1):
            if axis == 1:
                rows, cols = np.nonzero(ocean[:, :-1] != ocean[:, 1:])
                x = config["origin_x_m"] + (cols + 1) * spacing
                z = config["origin_z_m"] + (rows + .5) * spacing
                left = product.evaluate_geometry(x - .001, z)
                right = product.evaluate_geometry(x + .001, z)
            else:
                rows, cols = np.nonzero(ocean[:-1, :] != ocean[1:, :])
                x = config["origin_x_m"] + (cols + .5) * spacing
                z = config["origin_z_m"] + (rows + 1) * spacing
                left = product.evaluate_geometry(x, z - .001)
                right = product.evaluate_geometry(x, z + .001)
            for field in ("raw_elevation_m", "base_elevation_m", "mountain_height_m", "basin_depth_m", "elevation_m"):
                self.assertLess(float(np.max(abs(left[field] - right[field]))), .1, field)

    def test_styles_change_sections_and_branch_structure(self):
        path = ROOT / ".scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz"
        if not path.exists():
            self.skipTest("local shaped-v4 source unavailable")
        product = prepare_world_mountain_belts(load_base(path))
        ridges = product.manifest["source_inventory"]["ridges"]
        for main in (r for r in ridges if r["role"] == "main"):
            relatives = [r for r in ridges if r["source_id"] == main["source_id"]]
            parallel = [r for r in relatives if r["role"] == "parallel"]
            self.assertEqual(len(parallel), 1 if main["style"] == "block_plateau_margin" else 2)
            if main["style"] == "worn_ranges":
                self.assertTrue(all(r["amplitude_m"] <= main["amplitude_m"] * .33 for r in relatives if r["role"] != "main"))
        # Remove width/height and noise differences: the plateau must still have
        # a distinctly flatter cross-section, then a stronger outer falloff.
        points = np.array([[-100000., 0.], [100000., 0.]])
        section = {"width_m": 20000., "amplitude_m": 2000., "peak_spacing_m": 60000., "phase": .4}
        profiles = {}
        for style, power in (("folded", 1.5), ("block", 3.7), ("worn", 2.3)):
            profiles[style] = _ridge_height({**section, "cross_power": power}, points,
                                           np.zeros(3), np.array([0., 10000., 30000.]))
            profiles[style] /= profiles[style][0]
        self.assertGreater(profiles["block"][1], profiles["folded"][1] + .15)
        self.assertLess(profiles["block"][2], profiles["worn"][2] * .5)


if __name__ == "__main__":
    unittest.main()
