"""Resolved formation contracts; fixed seeds, macro-only (not TD acceptance)."""
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import unittest

import numpy as np

from terrain_pipeline.tectonic import TectonicConfig, initialize, evolve
from terrain_pipeline.tectonic import components, geometry_metrics, voronoi_complexity
from terrain_pipeline.tectonic import freeze, load_product, plan

ROOT = Path(__file__).resolve().parents[1]


class FormationTests(unittest.TestCase):
    def test_mixed_reference_preserves_cores_and_determinism(self):
        config = TectonicConfig(shape=(128, 160), steps=0,
                                origin_x_m=-800000., origin_z_m=-640000.)
        state = initialize(config)
        geometry = state.formation
        self.assertGreater(geometry["continuous_boundary_segments"], 24)
        self.assertEqual({p["family"] for p in geometry["growth_shapes"]}, {"circle", "ellipse", "triangle"})
        self.assertEqual(geometry["periodic_components_per_plate"], [1] * 8)
        ids = state.plate_coverage.argmax(0)
        for plate, anchor in enumerate(state.plate_seeds_m):
            x, z = np.floor((anchor - [config.origin_x_m, config.origin_z_m]) /
                            config.cell_size_m).astype(int)
            self.assertEqual(ids[z, x], plate)
        other = initialize(config)
        np.testing.assert_array_equal(other.plate_coverage, state.plate_coverage)
        self.assertEqual(other.formation, geometry)

    def test_v2_cold_read_does_not_call_formation_or_evolution(self):
        from unittest.mock import patch
        path = ROOT / ".scratch/plate-formation-coast-20261101/formation-run-v2/product.npz"
        if not path.exists():
            self.skipTest("local immutable v2 product unavailable")
        with patch('terrain_pipeline.tectonic.initialize', side_effect=AssertionError), \
                patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError), \
                patch('terrain_pipeline.tectonic.form_plates', side_effect=AssertionError):
            product = load_product(path)
        self.assertEqual(product.manifest["algorithm"], "kinematic-crust-2")

    def test_v3_cold_read_preserves_saved_product(self):
        from unittest.mock import patch
        path = ROOT / ".scratch/plate-formation-coast-20261101/compact-run-v3-final/product.npz"
        if not path.exists():
            self.skipTest("local immutable v3 product unavailable")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with patch('terrain_pipeline.tectonic.initialize', side_effect=AssertionError), \
                patch('terrain_pipeline.tectonic.evolve', side_effect=AssertionError), \
                patch('terrain_pipeline.tectonic.form_plates', side_effect=AssertionError):
            product = load_product(path)
        self.assertEqual(product.manifest["algorithm"], "kinematic-crust-3")
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_full_coverage_connected_and_unequal_with_true_concave_geometry(self):
        config = TectonicConfig(steps=0)
        state = initialize(config)
        geometry = state.formation
        ids = state.plate_coverage.argmax(0)
        np.testing.assert_array_equal(state.plate_coverage.sum(0), 1)
        self.assertEqual(geometry["periodic_components_per_plate"], [1] * config.plate_count)
        self.assertGreaterEqual(min(geometry["plate_area_cells"]), config.min_plate_cells)
        self.assertGreater(max(geometry["plate_area_cells"]), min(geometry["plate_area_cells"]))
        self.assertGreater(geometry["continuous_boundary_segments"], config.plate_count * 6)
        self.assertGreater(sum(geometry["continuous_concave_vertices_per_plate"]), config.plate_count)
        nodes = np.asarray(geometry["microfragment_id_zx"])
        owners = np.asarray(geometry["microfragment_plate"])
        np.testing.assert_array_equal(owners[nodes], ids)
        self.assertEqual(int(np.bincount(nodes.ravel()).sum()), np.prod(config.shape))
        product = freeze(config, evolve(config, state))
        self.assertEqual(product.manifest["core_metadata"]["formation"], geometry)

    def test_periodic_microfragments_are_split_and_never_dropped(self):
        labels = np.array([[0, 1, 1, 0], [1, 0, 1, 1], [1, 1, 1, 1]])
        fragments, sources = components(labels)
        self.assertEqual(fragments[0, 0], fragments[0, -1])
        self.assertNotEqual(fragments[0, 0], fragments[1, 1])
        np.testing.assert_array_equal(np.asarray(sources)[fragments], labels)
        self.assertEqual(sources.count(0), 2)

    def test_infeasible_minimum_fails_without_reseeding(self):
        for config in (TectonicConfig(shape=(4, 4), plate_count=5),
                       TectonicConfig(min_plate_cells=0),
                       TectonicConfig(microcells_per_plate=1)):
            with self.subTest(config=config), self.assertRaises(ValueError):
                initialize(config)
        # Exact count is either met or rejected explicitly, never silently reduced.
        state = initialize(TectonicConfig(shape=(8, 8), plate_count=8, min_plate_cells=1))
        self.assertEqual(len(np.unique(state.plate_coverage.argmax(0))), 8)

    def test_resolution_and_budget_include_microcells(self):
        config = TectonicConfig(shape=(128, 128), steps=0)
        sparse = plan(replace(config, microcells_per_plate=8))
        dense = plan(config)
        self.assertGreater(dense["formation_distance_cell_visits"], sparse["formation_distance_cell_visits"])
        self.assertGreater(dense["estimated_peak_memory_bytes"], sparse["estimated_peak_memory_bytes"])
        self.assertFalse(plan(config, max_cell_plate_steps=sparse["cell_plate_steps"])["allowed"])

    def test_geometry_supports_noninteger_metric_spacing(self):
        config = TectonicConfig(shape=(8, 12), plate_count=3, steps=0,
                                cell_size_m=.1, max_speed_m_per_step=0)
        product = freeze(config, evolve(config))
        self.assertEqual(product.manifest["core_metadata"]["formation"]["minimum_resolved_plate_area_m2"],
                         4 * .1**2)

    def test_unchanged_embryo_velocity_and_old_product_cold_read(self):
        path = ROOT / ".scratch/plate-formation-coast-20261101/baseline/tectonic_evolution_v1.py"
        if not path.exists():
            self.skipTest("local immutable baseline unavailable")
        spec = importlib.util.spec_from_file_location("formation_baseline", path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        config = TectonicConfig(shape=(32, 48), plate_count=5, steps=0)
        before = old.initialize(old.TectonicConfig(shape=config.shape, plate_count=5, steps=0))
        after = initialize(config)
        np.testing.assert_array_equal(before.continental_m.sum(0), after.continental_m.sum(0))
        np.testing.assert_array_equal(before.oceanic_m.sum(0), after.oceanic_m.sum(0))
        np.testing.assert_array_equal(before.velocities_m_per_step, after.velocities_m_per_step)
        frozen = ROOT / ".scratch/world-generation-sequence-20261101/macro-run-v2/product.npz"
        if frozen.exists():
            digest = hashlib.sha256(frozen.read_bytes()).hexdigest()
            product = load_product(frozen)
            self.assertEqual(product.manifest["schema"], "tectonic-frozen-product-v1")
            self.assertEqual(digest, hashlib.sha256(frozen.read_bytes()).hexdigest())

    def test_geometry_corruption_is_rejected_even_with_new_identity(self):
        from terrain_pipeline.tectonic import FrozenTectonicProduct, _digest, _json
        config = TectonicConfig(shape=(16, 24), plate_count=4, steps=0)
        product = freeze(config, evolve(config))
        manifest = product.manifest
        manifest["core_metadata"]["formation"]["microfragment_plate"][0] = 99
        manifest.pop("identity")
        manifest["identity"] = _digest(_json(manifest).encode())
        with self.assertRaisesRegex(ValueError, "geometry"):
            FrozenTectonicProduct(manifest, dict(product.arrays))

    def test_core_cost_and_algorithm_corruption_are_rejected(self):
        from terrain_pipeline.tectonic import FrozenTectonicProduct, _digest, _json
        config = TectonicConfig(shape=(16, 24), plate_count=4, steps=0)
        product = freeze(config, evolve(config))
        for corruption in ("cost", "core", "algorithm", "type", "shape", "shape_seed"):
            with self.subTest(corruption=corruption):
                manifest = product.manifest
                if corruption == "cost":
                    manifest["core_metadata"]["formation"]["growth_cost"]["path_weight"] = .8
                elif corruption == "shape":
                    manifest["core_metadata"]["formation"]["growth_shapes"][0]["angle_rad"] += .1
                elif corruption == "shape_seed":
                    manifest["core_metadata"]["formation"]["shape_purpose_seed"] += 1
                elif corruption == "core":
                    manifest["core_metadata"]["formation"]["core_microfragment_per_plate"].reverse()
                elif corruption == "algorithm":
                    manifest["algorithm"] = "kinematic-crust-2"
                    manifest["core_metadata"]["algorithm_version"] = "kinematic-crust-2"
                else:
                    manifest["core_metadata"]["formation"] = "invalid"
                manifest.pop("identity")
                manifest["identity"] = _digest(_json(manifest).encode())
                with self.assertRaises(ValueError):
                    FrozenTectonicProduct(manifest, dict(product.arrays))


if __name__ == "__main__":
    unittest.main()
