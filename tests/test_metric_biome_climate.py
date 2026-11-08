"""Contract tests for the migrated Python biome-selection rules (P5.2).

Acceptance mapping (contract `biome-climate-spec.md`):

- §1.1 four bands, one interior point each -> `test_four_bands_have_an_interior_point`
- §1.1 the three boundary behaviours, at their exact values -> `test_boundary_behaviours_are_exact`
- §1.1 literal equivalence with `Landscape.java:8` on a boundary-dense grid ->
  `test_matches_the_literal_java_expression_on_a_boundary_dense_grid`
- §1.2 landform ordinals, and the Python `dominant_type` correspondence ->
  `test_landform_ordinals_match_the_java_declaration_order`
- §1.3 the 16-name table and `ordinal*4 + variant` -> `test_palette_names_follow_ordinal_times_four_plus_variant`,
  `test_palette_index_returns_int64_on_both_paths`, `test_palette_index_covers_zero_to_fifteen`,
  `test_palette_index_rejects_out_of_range_instead_of_clamping`
- §2.1 the three constants, the clip ends and the physical boundaries ->
  `test_normalization_constants_are_the_frozen_java_numbers`, `test_clip_saturates_at_both_ends`,
  `test_physical_band_boundaries_come_out_of_the_normalization`
- §4 scalar/array single path -> `test_scalar_and_array_paths_agree`
- §4 item 5 the two verbatim declarations -> `test_module_docstring_carries_the_two_required_declarations`

`unittest` only — this repository has no pytest. Run from the repository root:

    .\\runtime\\venv\\Scripts\\python.exe -m unittest discover -s tests -t . -p "test_metric_biome_climate.py"
"""

import unittest

import numpy as np

from terrain_pipeline import climate_forcing as mbc
from terrain_pipeline.climate_forcing import BIOME_PALETTE, INSELBERG, KARST, LANDFORM_COUNT, LANDFORM_NAMES, LANDFORM_ORDINALS, PALETTE_SIZE, PILLARS, PRECIPITATION_SPAN_MM, RAIN_DRY, RAIN_WET, RIFT, TEMPERATURE_LOW, TEMPERATURE_OFFSET_C, TEMPERATURE_SPAN_C, VARIANT_COUNT, VARIANT_NAMES, climate_coordinates, palette_index, variant

# The contract §1.3 table, hard coded here as the expected 16-name order so the
# test would fail if the migration reordered a landform or a climate name.
EXPECTED_PALETTE = [
    ["inselberg_snowy", "inselberg_arid", "inselberg_temperate", "inselberg_humid"],
    ["rift_snowy", "rift_arid", "rift_temperate", "rift_humid"],
    ["karst_snowy", "karst_arid", "karst_temperate", "karst_humid"],
    ["pillars_snowy", "pillars_arid", "pillars_temperate", "pillars_humid"],
]

# A boundary-dense input grid: both sides of every one of the three thresholds,
# each threshold exactly, and the clip endpoints.
GRID_T = (0., .1, .2799999, .28, .2800001, .5, .9, 1., 2.)
GRID_R = (0., .1, .3399999, .34, .3400001, .5, .6399999, .64, .6400001, .9, 1., 2.)


def java_variant_literal(temperature, rain):
    """`Landscape.java:8` written out as a statement-for-statement reference.

    `return temperature<.28?0:rain<.34?1:rain>.64?3:2;` — the same order, the same
    three strict comparisons, evaluated one input at a time. This is a test-only
    oracle: it exists to catch a transcription mistake in the migrated module.
    """
    if temperature < .28:
        return 0
    if rain < .34:
        return 1
    if rain > .64:
        return 3
    return 2


class VariantTests(unittest.TestCase):
    """§1.1 / §4 item 1: the climate band of a normalized (temperature, rain)."""

    def test_four_bands_have_an_interior_point(self):
        self.assertEqual(variant(.1, .5), 0)   # cold: temperature < .28, rain mid
        self.assertEqual(variant(.5, .1), 1)   # dry: rain < .34
        self.assertEqual(variant(.5, .5), 2)   # temperate: .34 <= rain <= .64
        self.assertEqual(variant(.5, .9), 3)   # wet: rain > .64

    def test_boundary_behaviours_are_exact(self):
        """The three §1.1 boundary behaviours, including the temperature veto."""
        # (1) the temperature band vetoes, whatever the rain is: (.1, .9) is 0, not 3.
        self.assertEqual(variant(.1, .9), 0)
        self.assertEqual(variant(.2799999, 1.), 0)
        self.assertEqual(variant(0., 1.), 0)
        # (2) .34 <= rain <= .64 is 2, and both rain comparisons are strict.
        self.assertEqual(variant(.5, RAIN_DRY), 2)
        self.assertEqual(variant(.5, RAIN_WET), 2)
        self.assertEqual(variant(.5, .5), 2)
        self.assertEqual(variant(.5, .3399999), 1)   # strictly below the dry edge
        self.assertEqual(variant(.5, .6400001), 3)   # strictly above the wet edge
        # (3) temperature == .28 is not cold (strict `<`).
        self.assertEqual(variant(TEMPERATURE_LOW, .5), 2)
        self.assertEqual(variant(TEMPERATURE_LOW, .2), 1)
        self.assertEqual(variant(TEMPERATURE_LOW, .9), 3)
        # ... and one ulp below the threshold is cold again.
        self.assertEqual(variant(np.nextafter(TEMPERATURE_LOW, 0.), .9), 0)

    def test_matches_the_literal_java_expression_on_a_boundary_dense_grid(self):
        for t in GRID_T:
            for r in GRID_R:
                with self.subTest(temperature=t, rain=r):
                    self.assertEqual(int(variant(t, r)), java_variant_literal(t, r))

    def test_non_finite_input_follows_the_java_comparisons(self):
        # No finiteness guard on purpose: NaN fails every comparison, exactly as in Java.
        self.assertEqual(variant(np.nan, .5), 2)
        self.assertEqual(variant(np.nan, np.nan), 2)
        self.assertEqual(variant(-np.inf, .5), 0)
        self.assertEqual(variant(np.inf, .5), 2)
        self.assertEqual(variant(.5, np.inf), 3)
        self.assertEqual(variant(.5, -np.inf), 1)


class LandformTests(unittest.TestCase):
    """§1.2: the landform ordinals frozen from `Landform.java:3-9`."""

    def test_landform_ordinals_match_the_java_declaration_order(self):
        self.assertEqual((INSELBERG, RIFT, KARST, PILLARS), (0, 1, 2, 3))
        self.assertEqual(LANDFORM_ORDINALS,
                         {"inselberg": INSELBERG, "rift": RIFT,
                          "karst": KARST, "pillars": PILLARS})
        # The Python side needs no translation table: `dominant_type` from
        # `terrain_pipeline/metric_region.py:140` uses this same plain/hill/plateau/
        # mountain numbering (`docs/metric-minecraft-consumer.md:34`).
        self.assertEqual(tuple(LANDFORM_NAMES), ("inselberg", "rift", "karst", "pillars"))
        self.assertEqual(LANDFORM_COUNT, 4)
        for name, ordinal in LANDFORM_ORDINALS.items():
            self.assertEqual(LANDFORM_NAMES[ordinal], name)

    def test_variant_names_follow_the_resource_naming_order(self):
        # `tools/create_resources.py:19`: climates=['snowy','arid','temperate','humid']
        self.assertEqual(tuple(VARIANT_NAMES), ("snowy", "arid", "temperate", "humid"))
        self.assertEqual(VARIANT_COUNT, 4)


class PaletteTests(unittest.TestCase):
    """§1.3: `index = landform_ordinal * 4 + variant`, `index` in [0, 15]."""

    def test_palette_names_follow_ordinal_times_four_plus_variant(self):
        self.assertEqual(PALETTE_SIZE, 16)
        self.assertEqual(len(BIOME_PALETTE), PALETTE_SIZE)
        expected = []
        for ordinal, landform in enumerate(LANDFORM_NAMES):
            for band, climate in enumerate(VARIANT_NAMES):
                name = landform + "_" + climate
                index = ordinal * VARIANT_COUNT + band
                expected.append(name)
                self.assertEqual(BIOME_PALETTE[index], name)
                self.assertEqual(BIOME_PALETTE[palette_index(ordinal, band)], name)
        self.assertEqual(expected, EXPECTED_PALETTE[0] + EXPECTED_PALETTE[1]
                         + EXPECTED_PALETTE[2] + EXPECTED_PALETTE[3])
        self.assertEqual(tuple(BIOME_PALETTE),
                         tuple(name for row in EXPECTED_PALETTE for name in row))

    def test_palette_index_covers_zero_to_fifteen(self):
        seen = sorted(int(palette_index(o, v))
                      for o in range(LANDFORM_COUNT) for v in range(VARIANT_COUNT))
        self.assertEqual(seen, list(range(16)))
        self.assertEqual(len(set(seen)), PALETTE_SIZE)

    def test_palette_index_returns_int64_on_both_paths(self):
        scalar = palette_index(2, 3)
        self.assertTrue(isinstance(scalar, np.integer))
        self.assertEqual(scalar.dtype, np.dtype(np.int64))
        self.assertEqual(int(scalar), 11)
        array = palette_index(np.array([0, 1, 2, 3], np.int64),
                             np.array([0, 1, 2, 3], np.int64))
        self.assertEqual(array.dtype, np.dtype(np.int64))
        self.assertEqual(array.tolist(), [0, 5, 10, 15])

    def test_palette_index_rejects_out_of_range_instead_of_clamping(self):
        for ordinal, band in ((4, 0), (-1, 0), (0, 4), (0, -1), (16, 16), (-9, -9)):
            with self.subTest(landform_ordinal=ordinal, variant=band):
                with self.assertRaises(ValueError):
                    palette_index(ordinal, band)
        # An array is validated elementwise, so one bad entry raises the whole call.
        with self.assertRaises(ValueError):
            palette_index(np.array([0, 1, 4], np.int64), np.array([0, 1, 1], np.int64))
        with self.assertRaises(ValueError):
            palette_index(np.array([0, 1, 2], np.int64), np.array([0, 1, 4], np.int64))
        # A float index would silently truncate, so the dtype is rejected too.
        with self.assertRaises(ValueError):
            palette_index(1.0, 2.0)


class ClimateCoordinateTests(unittest.TestCase):
    """§2.1: normalized (temperature, rain) from BIO1 / BIO12."""

    def test_normalization_constants_are_the_frozen_java_numbers(self):
        self.assertEqual(TEMPERATURE_OFFSET_C, 12.)
        self.assertEqual(TEMPERATURE_SPAN_C, 45.)
        self.assertEqual(PRECIPITATION_SPAN_MM, 2200.)
        self.assertEqual((TEMPERATURE_LOW, RAIN_DRY, RAIN_WET), (.28, .34, .64))

    def test_clip_saturates_at_both_ends(self):
        # Low end: temperature 0 exactly from BIO1 <= -12 C, rain 0 from BIO12 <= 0 mm.
        self.assertEqual(climate_coordinates(-12., 0.), (0., 0.))
        self.assertEqual(climate_coordinates(-40., -10.), (0., 0.))
        self.assertEqual(climate_coordinates(-1e9, -1e9), (0., 0.))
        # High end: temperature 1 exactly from BIO1 >= 33 C, rain 1 from BIO12 >= 2200 mm.
        self.assertEqual(climate_coordinates(33., 2200.), (1., 1.))
        self.assertEqual(climate_coordinates(80., 5000.), (1., 1.))
        self.assertEqual(climate_coordinates(1e9, 1e9), (1., 1.))
        # Interior point: the two constants act as declared.
        self.assertAlmostEqual(climate_coordinates(0., 1100.)[0], 12. / 45., places=15)
        self.assertAlmostEqual(climate_coordinates(0., 1100.)[1], .5, places=15)
        # §3.3 seam: everything at or above 2200 mm collapses onto rain == 1.
        self.assertEqual(climate_coordinates(20., 2200.)[1], 1.)
        self.assertEqual(climate_coordinates(20., 3200.)[1], 1.)

    def test_physical_band_boundaries_come_out_of_the_normalization(self):
        """§2.4: the four bands in physical units, with safe margins."""
        self.assertEqual(variant(*climate_coordinates(-5., 1100.)), 0)     # BIO1 < 0.60 C
        self.assertEqual(variant(*climate_coordinates(5., 700.)), 1)       # BIO12 < 748 mm
        self.assertEqual(variant(*climate_coordinates(5., 1100.)), 2)
        self.assertEqual(variant(*climate_coordinates(5., 1500.)), 3)      # BIO12 > 1408 mm
        # Above the 2200 mm normalization bound only the wet band is guaranteed.
        self.assertEqual(variant(*climate_coordinates(5., 3200.)), 3)

    def test_scalar_and_array_paths_agree(self):
        temperatures = np.array([-40., -12., 0., 10., 33., 80.], np.float64)
        precipitations = np.array([0., 700., 1100., 1400., 2200., 3200.], np.float64)
        array_t, array_r = climate_coordinates(temperatures, precipitations)
        self.assertEqual(array_t.dtype, np.dtype(np.float64))
        self.assertEqual(array_r.dtype, np.dtype(np.float64))
        for index in range(temperatures.size):
            scalar_t, scalar_r = climate_coordinates(float(temperatures[index]),
                                                     float(precipitations[index]))
            self.assertIsInstance(scalar_t, float)
            self.assertIsInstance(scalar_r, float)
            self.assertEqual(scalar_t, array_t[index])
            self.assertEqual(scalar_r, array_r[index])
        # Broadcasting: a scalar BIO1 against an array BIO12 keeps one code path.
        broadcast_t, broadcast_r = climate_coordinates(0., precipitations)
        self.assertEqual(broadcast_t.shape, precipitations.shape)
        self.assertTrue(np.all(broadcast_t == 12. / 45.))
        self.assertEqual(broadcast_r.tolist(), array_r.tolist())

    def test_variant_scalar_array_and_dtype_paths(self):
        scalar = variant(.1, .9)
        self.assertTrue(isinstance(scalar, np.integer))
        self.assertEqual(scalar.dtype, np.dtype(np.int64))
        self.assertEqual(int(scalar), 0)
        array = variant(np.array([.1, .5, .5, .5], np.float64),
                        np.array([.9, .1, .5, .9], np.float64))
        self.assertEqual(array.dtype, np.dtype(np.int64))
        self.assertEqual(array.tolist(), [0, 1, 2, 3])
        self.assertEqual([int(variant(t, r))
                          for t, r in zip((.1, .5, .5, .5), (.9, .1, .5, .9))],
                         array.tolist())

    def test_module_docstring_carries_the_two_required_declarations(self):
        """§4 item 5: both declarations must appear verbatim in the docstring."""
        docstring = mbc.__doc__
        self.assertIn("**资料出处：无**。三个阈值（`.28` / `.34` / `.64`）全仓只此一处，无 Köppen / "
                      "Holdridge 之类引用 = **纯工程假设**，与 P4 已声明的同类义务一致。",
                      docstring)
        self.assertIn("**\"normalized biome-selection coordinate, not a physical climate quantity\"**",
                      docstring)


if __name__ == "__main__":
    unittest.main()
