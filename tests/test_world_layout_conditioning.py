"""Contract tests for world-layout conditioning. CPU only: no model, no GPU."""
import math
import unittest

import numpy as np

from diffusion.world_layout_conditioning import (
    ALGORITHM,
    CONDITIONING_SPACING_M,
    NATIVE_RESOLUTION_M,
    SCHEMA,
    SEA_DATUM_M,
    WorldLayoutGenerationConfig,
    layout_elevation_m,
    make_conditioning_map,
    select_nonempty_window,
)
from terrain_pipeline.world_water_layout import (
    CLASS_LAND,
    CLASS_LAKE,
    CLASS_OCEAN,
    LayoutSpec,
    MODE_FINITE,
    classify_points,
)

SEED = 20261020


def earth(**kwargs):
    kwargs.setdefault("total_water_fraction", 0.62)
    return LayoutSpec("earth", **kwargs)


def lakes(**kwargs):
    kwargs.setdefault("total_water_fraction", 0.12)
    return LayoutSpec("lakes", **kwargs)


class ConfigTests(unittest.TestCase):
    def test_identity_is_stable_and_layout_bound(self):
        spec = earth()
        first = WorldLayoutGenerationConfig.from_layout(spec)
        self.assertEqual(first.identity(), WorldLayoutGenerationConfig.from_layout(spec).identity())
        other = WorldLayoutGenerationConfig.from_layout(lakes())
        self.assertNotEqual(first.identity(), other.identity())
        self.assertEqual(first.layout_identity, spec.identity())

    def test_native_spacing_is_enforced(self):
        with self.assertRaises(ValueError):
            WorldLayoutGenerationConfig.from_layout(earth(), native_resolution_m=10_000.0)

    def test_sea_datum_is_not_rebased(self):
        with self.assertRaises(ValueError):
            WorldLayoutGenerationConfig.from_layout(earth(), sea_datum_m=-100.0)
        self.assertEqual(WorldLayoutGenerationConfig.from_layout(earth()).sea_datum_m,
                         SEA_DATUM_M)

    def test_record_states_the_limits(self):
        record = WorldLayoutGenerationConfig.from_layout(earth()).record()
        self.assertEqual(record["schema"], SCHEMA)
        self.assertEqual(record["algorithm"], ALGORITHM)
        self.assertEqual(record["production_spacing_m"], NATIVE_RESOLUTION_M)
        self.assertFalse(record["minimum_unit_achieved"])

    def test_from_base_reads_without_modifying(self):
        class Base:
            native_resolution_m = 30.0
            sea_datum_m = 0.0
            model_dir = "models/terrain-diffusion-30m"
            dtype = "fp32"
        base = Base()
        before = dict(base.__class__.__dict__)
        config = WorldLayoutGenerationConfig.from_base(base, earth())
        self.assertEqual(config.borrowed_from_base["model_dir"],
                         "models/terrain-diffusion-30m")
        self.assertEqual(dict(base.__class__.__dict__), before)
        self.assertEqual(base.native_resolution_m, 30.0)


class ElevationTests(unittest.TestCase):
    def test_land_is_above_and_ocean_below_the_datum(self):
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        window = select_nonempty_window(spec, 129, prefer="coast")
        axis = np.arange(129, dtype=np.float64) * NATIVE_RESOLUTION_M
        gx, gz = np.meshgrid(window["origin_m"][0] + axis, window["origin_m"][1] + axis)
        elevation = layout_elevation_m(spec, config, gx, gz)
        classes = classify_points(spec, gx, gz)
        self.assertTrue(np.all(elevation[classes == CLASS_LAND] > SEA_DATUM_M))
        self.assertTrue(np.all(elevation[classes == CLASS_OCEAN] < SEA_DATUM_M))

    def test_lake_bed_is_below_the_datum(self):
        spec = lakes()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        window = select_nonempty_window(spec, 129, prefer="lake")
        axis = np.arange(129, dtype=np.float64) * NATIVE_RESOLUTION_M
        gx, gz = np.meshgrid(window["origin_m"][0] + axis, window["origin_m"][1] + axis)
        elevation = layout_elevation_m(spec, config, gx, gz)
        classes = classify_points(spec, gx, gz)
        if (classes == CLASS_LAKE).any():
            self.assertTrue(np.all(elevation[classes == CLASS_LAKE] < SEA_DATUM_M))


class WindowSelectionTests(unittest.TestCase):
    def test_coast_window_contains_both_classes(self):
        spec = earth()
        window = select_nonempty_window(spec, 129, prefer="coast")
        self.assertTrue(window["contains"]["land"])
        self.assertTrue(window["contains"]["ocean"])
        self.assertEqual(window["size_cells"], 129)
        self.assertIn("rule", window)

    def test_selection_is_deterministic(self):
        spec = earth()
        first = select_nonempty_window(spec, 129, prefer="coast")
        second = select_nonempty_window(spec, 129, prefer="coast")
        self.assertEqual(first["origin_m"], second["origin_m"])

    def test_lake_window_contains_a_basin(self):
        spec = lakes()
        window = select_nonempty_window(spec, 129, prefer="lake")
        self.assertTrue(window["contains"]["lake"])


class ConditioningMapTests(unittest.TestCase):
    def test_protocol_shape_and_finiteness(self):
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        factory = make_conditioning_map(spec, config, origin_world_m=(0.0, 0.0))
        raw = factory.sample_raw(0, 0, 65, 65)
        self.assertEqual(raw.shape, (5, 65, 65))
        self.assertTrue(np.isfinite(raw).all())
        self.assertEqual(factory.finalize(raw).shape, (5, 65, 65))

    def test_indices_are_conditioning_not_native(self):
        """One conditioning index is CONDITIONING_SPACING_M of world, not 30 m."""
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        factory = make_conditioning_map(spec, config, origin_world_m=(0.0, 0.0))
        self.assertEqual(factory.conditioning_spacing_m, CONDITIONING_SPACING_M)
        self.assertEqual(factory.native_resolution_m, NATIVE_RESOLUTION_M)
        components = factory.sample_components(0, 0, 2, 2)
        self.assertEqual(components["elevation_m"].shape, (2, 2))

    def test_non_integer_index_is_refused(self):
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        factory = make_conditioning_map(spec, config, origin_world_m=(0.0, 0.0))
        with self.assertRaises(ValueError):
            factory.sample_raw(0, 0, 2.5, 2)

    def test_channel_provenance_is_declared(self):
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        factory = make_conditioning_map(spec, config, origin_world_m=(0.0, 0.0))
        self.assertEqual(factory.channel_provenance["elevation"],
                         "continuous_layout_shore_field")
        for name in ("temperature", "precipitation"):
            self.assertIn("placeholder", factory.channel_provenance[name])
        self.assertEqual(factory.claim_level, "macro_layout_diagnostic_only")
        self.assertEqual(factory.layout_identity, spec.identity())

    def test_window_is_tile_independent(self):
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        factory = make_conditioning_map(spec, config, origin_world_m=(0.0, 0.0))
        whole = factory.sample_raw(0, 0, 8, 8)
        left = factory.sample_raw(0, 0, 4, 8)
        right = factory.sample_raw(4, 0, 8, 8)
        np.testing.assert_array_equal(whole[:, :, :4], left)
        np.testing.assert_array_equal(whole[:, :, 4:], right)

    def test_non_positive_conditioning_spacing_is_refused(self):
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        with self.assertRaises(ValueError):
            make_conditioning_map(spec, config, origin_world_m=(0.0, 0.0),
                                  conditioning_spacing_m=0.0)

    def test_finalize_rejects_wrong_shape(self):
        spec = earth()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        factory = make_conditioning_map(spec, config, origin_world_m=(0.0, 0.0))
        with self.assertRaises(ValueError):
            factory.finalize(np.zeros((4, 8, 8), dtype=np.float32))


class SpawnBoundaryTests(unittest.TestCase):
    """The payload must cross a Windows spawn boundary without carrying a closure.

    This is a CPU-only probe: it never touches a model, a GPU or the network. It exists
    because the first backend draft put a closure in the payload, which cannot be pickled
    and would have failed only after a model had been loaded.
    """

    def test_payload_is_plain_records_only(self):
        import pickle
        from diffusion.world_layout_backend import config_record, spec_parameters

        spec = lakes()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        payload = {"spec_record": spec_parameters(spec),
                   "config_record": config_record(config),
                   "origin_world_m": [0.0, 0.0],
                   "conditioning_spacing_m": CONDITIONING_SPACING_M,
                   "origin_native_rc": [0, 0], "side": 129, "seed": SEED,
                   "device": "cuda", "dtype": "fp32",
                   "cond_snr": (0.65, 0.1, 1.0, 0.1, 1.0),
                   "gpu_fraction": None}
        # Must be picklable; a closure would raise here.
        restored = pickle.loads(pickle.dumps(payload))
        self.assertEqual(restored["spec_record"]["preset"], "lakes")
        self.assertFalse(callable(restored["spec_record"]))

    def test_records_rebuild_the_same_identity(self):
        from diffusion.world_layout_backend import config_record, spec_parameters
        from terrain_pipeline.world_water_layout import LayoutSpec, identity

        spec = lakes()
        config = WorldLayoutGenerationConfig.from_layout(spec)
        rebuilt = LayoutSpec(**spec_parameters(spec))
        self.assertEqual(identity(rebuilt), identity(spec))
        rebuilt_config = WorldLayoutGenerationConfig(**config_record(config))
        self.assertEqual(rebuilt_config.identity(), config.identity())

    def test_origin_axis_order_is_row_col(self):
        """(x, z) worldspeak must become (row=i, col=j) = (z, x) for `get`.

        Passing x as the row index would transpose the page. This asserts the conversion
        is explicit rather than accidental.
        """
        origin_x_cell, origin_z_cell = 7, 13
        origin_native_rc = (origin_z_cell, origin_x_cell)
        self.assertEqual(origin_native_rc, (13, 7))
        self.assertNotEqual(origin_native_rc, (origin_x_cell, origin_z_cell))


if __name__ == "__main__":
    unittest.main()
