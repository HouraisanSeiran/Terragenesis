"""A1 同坐标环境联合查询的验收测试（外部行为）。

只测外部行为：同点逐字段对现独立公开核、乱序/分窗无关、身份随来源变、
缺来源拒、DEM halo 不足真 pending / require 拒、显式粗来源可识别、
soil 30 m 明确且同 arid 不告警、cache 不跳身份、超点/字节门早拒。

不测内部实现，**不**测任何“区分度阈值”。
"""
import hashlib
import json
import os
import unittest

import numpy as np

from terrain_pipeline.climate_forcing import climate_coordinates, variant
from terrain_pipeline.climate_forcing import RefinedClimateParameters, sample_climate_v2
from terrain_pipeline.environment_query import AVAILABLE_WATER_SEMANTICS, GRID_SPACING_M, MAX_POINTS, NOT_AVAILABLE, describe, preflight, sample_environment
from builtins import ValueError as EnvironmentBudgetError
from terrain_pipeline.soil_water import SoilParameters
from terrain_pipeline.geology import sample_lithology_points
from terrain_pipeline.geology import make_material_field

SEED = 20261020
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRODUCT = os.path.join(ROOT, "artifacts", "finite-river-sample-v1")
#: 不依赖任何产物数据的兜底窗口（绝对世界坐标，30 m 格参考点）
BASE_X = 1_265_190.0
BASE_Z = 1_286_220.0


def _grid(rows, cols, base_x=BASE_X, base_z=BASE_Z):
    xs = base_x + np.arange(cols) * GRID_SPACING_M
    zs = base_z + np.arange(rows) * GRID_SPACING_M
    return np.meshgrid(xs, zs)


def _load_dem():
    """若 M1-M4 样本产物在场，返回其 DEM sampler + 声明；否则 None。"""
    product_path = os.path.join(PRODUCT, "product.json")
    elev_path = os.path.join(PRODUCT, "domain", "elevation_m.npy")
    if not (os.path.exists(product_path) and os.path.exists(elev_path)):
        return None
    with open(product_path, "r", encoding="utf-8") as handle:
        domain = json.load(handle)["domain"]
    origin_x, origin_z = domain["origin_m_xz"]
    elev = np.load(elev_path)

    def sampler(x_m, z_m):
        ax = np.asarray(x_m, np.float64)
        az = np.asarray(z_m, np.float64)
        col = np.rint((ax - origin_x) / GRID_SPACING_M).astype(np.int64)
        row = np.rint((az - origin_z) / GRID_SPACING_M).astype(np.int64)
        ok = ((col >= 0) & (col < elev.shape[1]) & (row >= 0) & (row < elev.shape[0]))
        out = np.full(ax.shape, np.nan, np.float64)
        out[ok] = elev[row[ok], col[ok]]
        return out

    dem = {"identity_sha256": hashlib.sha256(
        np.ascontiguousarray(elev).tobytes()).hexdigest(),
        "origin_m_xz": [origin_x, origin_z], "spacing_m": GRID_SPACING_M,
        "shape_zx": list(elev.shape), "source_path": "artifacts/finite-river-sample-v1/domain/elevation_m.npy"}
    return sampler, dem, origin_x, origin_z, elev


class DeclarationTests(unittest.TestCase):
    def test_describe_states_the_boundaries(self):
        declared = describe()
        self.assertEqual(declared["grid_spacing_m"], GRID_SPACING_M)
        self.assertEqual(declared["available_water_semantics"],
                         "relative_proxy_not_dynamic_et")
        self.assertIn("potential_et", declared["not_available_fields"])
        self.assertIn("actual_et", declared["not_available_fields"])
        joined = " ".join(declared["never"])
        self.assertIn("10 km", joined)


class FieldEquivalenceTests(unittest.TestCase):
    """同点逐字段必须等于现有独立公开核。"""

    def setUp(self):
        self.x, self.z = _grid(4, 5)
        flat_x = self.x.ravel()
        flat_z = self.z.ravel()
        self.result = sample_environment(SEED, flat_x, flat_z, source_identities={})

    def test_climate_matches_sample_climate_v2(self):
        flat_x = self.x.ravel()
        flat_z = self.z.ravel()
        reference = sample_climate_v2(SEED, flat_x, flat_z,
                                     elevation_m=self.result["elevation_m"].ravel())
        self.assertTrue(np.array_equal(
            np.asarray(reference["annual_precipitation_mm"]).ravel(),
            self.result["BIO12_mm"].ravel()))
        self.assertTrue(np.array_equal(
            np.asarray(reference["BIO1_4_12_15"][0]).ravel(),
            self.result["BIO1_c"].ravel()))
        self.assertTrue(np.array_equal(
            np.asarray(reference["monthly_temperature_c"]),
            self.result["monthly_temperature_c"]))

    def test_material_matches_make_material_field(self):
        flat_x = self.x.ravel()
        flat_z = self.z.ravel()
        origin_x = float(flat_x.min())
        origin_z = float(flat_z.min())
        cols = int(round((float(flat_x.max()) - origin_x) / GRID_SPACING_M)) + 1
        rows = int(round((float(flat_z.max()) - origin_z) / GRID_SPACING_M)) + 1
        seed = self.result["identity"]["sub_seeds"]["material"]
        field = make_material_field((rows, cols), origin_m_xz=[origin_x, origin_z],
                                   spacing_m=GRID_SPACING_M, seed=seed)
        row_i = np.rint((flat_z - origin_z) / GRID_SPACING_M).astype(np.int64)
        col_i = np.rint((flat_x - origin_x) / GRID_SPACING_M).astype(np.int64)
        expected = np.asarray(field["arrays"]["erodible_thickness_m"])[row_i, col_i]
        self.assertTrue(np.array_equal(expected, self.result["material_erodible_thickness_m"].ravel()))

    def test_lithology_matches_sample_lithology_points(self):
        reference = sample_lithology_points(self.x.ravel(), self.z.ravel(), world_seed=SEED)
        self.assertTrue(np.array_equal(
            np.asarray(reference["rock_index"]).ravel(),
            self.result["lithology_rock_index"].ravel()))

    def test_biome_band_matches_variant(self):
        temperature, rain = climate_coordinates(self.result["BIO1_c"].ravel(),
                                               self.result["BIO12_mm"].ravel())
        expected = np.asarray(variant(temperature, rain), np.int64)
        self.assertTrue(np.array_equal(expected, self.result["biome_climate_band"].ravel()))

    def test_available_water_carries_proxy_semantics(self):
        self.assertEqual(self.result["available_water_semantics"], AVAILABLE_WATER_SEMANTICS)
        self.assertEqual(self.result["sources"]["available_water"]["semantics"],
                         AVAILABLE_WATER_SEMANTICS)
        self.assertEqual(self.result["sources"]["potential_et"]["status"], NOT_AVAILABLE)
        self.assertEqual(self.result["sources"]["actual_et"]["status"], NOT_AVAILABLE)
        self.assertEqual(self.result["sources"]["land_cover"]["status"], NOT_AVAILABLE)


class DeterminismTests(unittest.TestCase):
    def test_shuffled_points_give_identical_values(self):
        x, z = _grid(5, 6)
        flat_x, flat_z = x.ravel(), z.ravel()
        straight = sample_environment(SEED, flat_x, flat_z, source_identities={})
        permutation = np.random.default_rng(SEED).permutation(flat_x.size)
        shuffled = sample_environment(SEED, flat_x[permutation], flat_z[permutation],
                                     source_identities={})
        for key in ("BIO12_mm", "BIO1_c", "material_erodible_thickness_m",
                    "lithology_rock_index", "soil_depth_m"):
            restored = np.empty_like(np.asarray(straight[key]).ravel())
            restored[permutation] = np.asarray(shuffled[key]).ravel()
            self.assertTrue(np.array_equal(restored, np.asarray(straight[key]).ravel()),
                            "%s depends on query order" % key)

    def test_window_split_is_irrelevant(self):
        x, z = _grid(6, 6)
        whole = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        whole_bio12 = np.asarray(whole["BIO12_mm"]).reshape(x.shape)
        whole_rock = np.asarray(whole["lithology_rock_index"]).reshape(x.shape)
        block = sample_environment(SEED, x[2:4, 1:4].ravel(), z[2:4, 1:4].ravel(),
                                  source_identities={})
        self.assertTrue(np.array_equal(
            np.asarray(block["BIO12_mm"]).reshape((2, 3)), whole_bio12[2:4, 1:4]))
        self.assertTrue(np.array_equal(
            np.asarray(block["lithology_rock_index"]).reshape((2, 3)), whole_rock[2:4, 1:4]))

    def test_points_digest_ignores_order(self):
        x, z = _grid(3, 4)
        flat_x, flat_z = x.ravel(), z.ravel()
        first = sample_environment(SEED, flat_x, flat_z, source_identities={})
        permutation = np.random.default_rng(7).permutation(flat_x.size)
        second = sample_environment(SEED, flat_x[permutation], flat_z[permutation],
                                    source_identities={})
        self.assertEqual(first["identity"]["points_digest"],
                         second["identity"]["points_digest"])
        self.assertEqual(first["identity"]["combined_identity_sha256"],
                         second["identity"]["combined_identity_sha256"])


class IdentityTests(unittest.TestCase):
    def test_material_seed_change_changes_identity(self):
        x, z = _grid(2, 2)
        default = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        other_seed = (default["identity"]["sub_seeds"]["material"] + 1) % (2 ** 64)
        changed = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={},
                                    material_seed=other_seed)
        self.assertNotEqual(default["identity"]["combined_identity_sha256"],
                            changed["identity"]["combined_identity_sha256"])

    def test_soil_parameter_change_changes_identity(self):
        x, z = _grid(2, 2)
        default = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        tweaked = sample_environment(
            SEED, x.ravel(), z.ravel(), source_identities={},
            soil_parameters=SoilParameters(slope_spacing_m=GRID_SPACING_M,
                                           available_water_span_mm=1000.0))
        self.assertNotEqual(default["identity"]["combined_identity_sha256"],
                            tweaked["identity"]["combined_identity_sha256"])

    def test_sub_seeds_are_recorded_with_derivation(self):
        x, z = _grid(1, 2)
        result = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        record = result["identity"]["record"]
        self.assertIn("seed_derivation", record["material"])
        self.assertIn("sha256", record["material"]["seed_derivation"])
        self.assertIn("seed_derivation", record["soil"])
        self.assertEqual(record["world_seed"], SEED)


class RejectionTests(unittest.TestCase):
    def test_missing_dem_identity_is_refused(self):
        x, z = _grid(1, 2)

        def sampler(x_m, z_m):
            return np.zeros(np.shape(x_m), np.float64)

        with self.assertRaises(ValueError):
            sample_environment(SEED, x.ravel(), z.ravel(),
                              elevation_sampler=sampler, source_identities={})

    def test_dem_identity_without_sampler_is_refused(self):
        x, z = _grid(1, 2)
        dem = {"identity_sha256": "0" * 64, "origin_m_xz": [BASE_X, BASE_Z],
               "spacing_m": GRID_SPACING_M, "shape_zx": [2, 2]}
        with self.assertRaises(ValueError):
            sample_environment(SEED, x.ravel(), z.ravel(), source_identities={"dem": dem})

    def test_non_grid_points_are_refused_not_snapped(self):
        with self.assertRaises(ValueError):
            sample_environment(SEED, np.array([BASE_X + 1.0]), np.array([BASE_Z]),
                              source_identities={})

    def test_ten_kilometre_soil_default_is_refused(self):
        x, z = _grid(1, 2)
        with self.assertRaises(ValueError):
            sample_environment(SEED, x.ravel(), z.ravel(), source_identities={},
                              soil_parameters=SoilParameters())

    def test_bad_seed_and_policy_are_refused(self):
        x, z = _grid(1, 2)
        with self.assertRaises(ValueError):
            sample_environment(True, x.ravel(), z.ravel(), source_identities={})
        with self.assertRaises(ValueError):
            sample_environment(SEED, x.ravel(), z.ravel(), source_identities={},
                              orographic_policy="whatever")

    def test_too_many_points_are_refused_before_allocation(self):
        with self.assertRaises(EnvironmentBudgetError):
            preflight(MAX_POINTS + 1, 10)

    def test_oversized_material_bbox_is_refused(self):
        with self.assertRaises(EnvironmentBudgetError):
            preflight(10, 10 ** 9)

    def test_scattered_points_with_huge_bbox_are_refused(self):
        """2000 x 2000 格包围盒 = 4,000,000 cells > 262,144 上限，分配前就拒。"""
        xs = np.array([BASE_X, BASE_X + 1999 * GRID_SPACING_M])
        zs = np.array([BASE_Z, BASE_Z + 1999 * GRID_SPACING_M])
        with self.assertRaises(EnvironmentBudgetError):
            sample_environment(SEED, xs, zs, source_identities={})


class PolicyDispatchTests(unittest.TestCase):
    """policy 优先：显式选粗不得被自动改成 DEM；无 DEM 时 require_dem 必须拒。"""

    def test_require_dem_without_any_dem_is_refused(self):
        x, z = _grid(2, 2)
        with self.assertRaises(ValueError) as caught:
            sample_environment(SEED, x.ravel(), z.ravel(), source_identities={},
                              orographic_policy="require_dem")
        self.assertIn("require_dem", str(caught.exception))

    def _one_point(self):
        loaded = _load_dem()
        if loaded is None:
            self.skipTest("finite-river-sample-v1 DEM not present")
        sampler, dem, origin_x, origin_z, elev = loaded
        xs = np.array([origin_x + 128 * GRID_SPACING_M])
        zs = np.array([origin_z + 158 * GRID_SPACING_M])
        return sampler, dem, xs, zs

    def test_coarse_policy_is_not_upgraded_even_when_dem_covers(self):
        sampler, dem, xs, zs = self._one_point()
        result = sample_environment(SEED, xs, zs, elevation_sampler=sampler,
                                    source_identities={"dem": dem},
                                    orographic_policy="coarse_condition")
        self.assertEqual(result["orographic"]["orographic_elevation_source"],
                         "coarse_condition_field")
        self.assertEqual(result["orographic"]["status"],
                         "declared_background_estimate_coarse")
        self.assertEqual(result["sources"]["monthly_precipitation_mm"]["status"],
                         "declared_background_estimate")

    def test_pending_never_claims_dem_without_coverage(self):
        sampler, dem, xs, zs = self._one_point()
        result = sample_environment(SEED, xs, zs, elevation_sampler=sampler,
                                    source_identities={"dem": dem})
        orographic = result["orographic"]
        if orographic["status"] == "pending_dem_halo_insufficient":
            self.assertEqual(orographic["orographic_elevation_source"],
                             "coarse_condition_field")
            self.assertNotEqual(orographic["precipitation_status"], "dem_verified")
        else:
            self.assertEqual(orographic["status"], "dem_verified")
            self.assertEqual(orographic["orographic_elevation_source"], "caller_dem")


class OffGridSamplerTests(unittest.TestCase):
    """off-grid 的 sampler 请求必须被判为不可用，而不是被 rint 成格心。"""

    def test_half_cell_offset_request_is_not_treated_as_aligned(self):
        from terrain_pipeline.environment_query import _dem_lookup

        dem = {"identity_sha256": "0" * 64, "origin_m_xz": [BASE_X, BASE_Z],
               "spacing_m": GRID_SPACING_M, "shape_zx": [10, 10]}
        _h, inside, _r, _c = _dem_lookup(dem, np.array([BASE_X + 15.0]),
                                        np.array([BASE_Z + 15.0]))
        self.assertFalse(bool(inside[0]), "half-cell offset must be off-grid")
        _h, inside, row_i, col_i = _dem_lookup(dem, np.array([BASE_X + 3 * GRID_SPACING_M]),
                                              np.array([BASE_Z + 4 * GRID_SPACING_M]))
        self.assertTrue(bool(inside[0]))
        self.assertEqual((int(row_i[0]), int(col_i[0])), (4, 3))

    def test_off_grid_sampler_marks_soil_not_available(self):
        """soil 模板越出 DEM 时必须标 not_available，不得用粗地形徽幸。"""
        def sampler(x_m, z_m):
            return np.zeros(np.shape(x_m), np.float64)

        dem = {"identity_sha256": "1" * 64, "origin_m_xz": [BASE_X, BASE_Z],
               "spacing_m": GRID_SPACING_M, "shape_zx": [2, 2]}
        result = sample_environment(SEED, np.array([BASE_X]), np.array([BASE_Z]),
                                    elevation_sampler=sampler,
                                    source_identities={"dem": dem})
        self.assertEqual(str(result["soil_status"].ravel()[0]), NOT_AVAILABLE)
        self.assertEqual(str(result["elevation_source_per_point"].ravel()[0]), "caller_dem")


class OrographicPolicyTests(unittest.TestCase):
    """DEM halo 不足必须真实 pending / require 拒，不能静默或伪称 DEM 已接。"""

    def setUp(self):
        loaded = _load_dem()
        if loaded is None:
            self.skipTest("finite-river-sample-v1 DEM not present")
        self.sampler, self.dem, self.origin_x, self.origin_z, self.elev = loaded

    def _block(self, row0=150, col0=100, rows=3, cols=3):
        xs = self.origin_x + np.arange(col0, col0 + cols) * GRID_SPACING_M
        zs = self.origin_z + np.arange(row0, row0 + rows) * GRID_SPACING_M
        return np.meshgrid(xs, zs)

    def test_pending_reports_real_envelope_and_missing_coverage(self):
        x, z = self._block()
        result = sample_environment(SEED, x.ravel(), z.ravel(),
                                    elevation_sampler=self.sampler,
                                    source_identities={"dem": self.dem})
        orographic = result["orographic"]
        self.assertEqual(orographic["status"], "pending_dem_halo_insufficient")
        self.assertEqual(orographic["orographic_elevation_source"], "coarse_condition_field")
        self.assertEqual(orographic["precipitation_status"], "declared_background_estimate")
        envelope = orographic["requested_envelope"]
        self.assertFalse(envelope["dem_covered_all"])
        self.assertGreater(envelope["requested_coordinates_missing"], 0)
        self.assertGreater(envelope["requested_coordinates_total"], 0)
        # 实测包络必须真的超出 DEM 范围（不是写死的 halo 常量）
        self.assertGreater(envelope["requested_envelope_m"]["x_min"],
                           0.0)
        self.assertTrue(envelope["requested_envelope_m"]["x_max"] > envelope["dem_extent_m"]["x_max"]
                        or envelope["requested_envelope_m"]["x_min"] < envelope["dem_extent_m"]["x_min"]
                        or envelope["requested_envelope_m"]["z_max"] > envelope["dem_extent_m"]["z_max"]
                        or envelope["requested_envelope_m"]["z_min"] < envelope["dem_extent_m"]["z_min"])

    def test_pending_keeps_temperature_and_other_fields(self):
        x, z = self._block()
        result = sample_environment(SEED, x.ravel(), z.ravel(),
                                    elevation_sampler=self.sampler,
                                    source_identities={"dem": self.dem})
        self.assertTrue(np.isfinite(result["BIO1_c"]).all())
        self.assertTrue(np.isfinite(result["BIO12_mm"]).all())
        self.assertTrue(np.isfinite(result["material_erodible_thickness_m"]).all())
        self.assertTrue((result["elevation_source_per_point"] == "caller_dem").all())

    def test_require_dem_refuses_instead_of_falling_back(self):
        x, z = self._block()
        with self.assertRaises(ValueError) as caught:
            sample_environment(SEED, x.ravel(), z.ravel(),
                              elevation_sampler=self.sampler,
                              source_identities={"dem": self.dem},
                              orographic_policy="require_dem")
        self.assertIn("require_dem", str(caught.exception))

    def test_explicit_coarse_policy_is_labelled(self):
        x, z = self._block()
        result = sample_environment(SEED, x.ravel(), z.ravel(),
                                    elevation_sampler=self.sampler,
                                    source_identities={"dem": self.dem},
                                    orographic_policy="coarse_condition")
        orographic = result["orographic"]
        self.assertEqual(orographic["orographic_elevation_source"], "coarse_condition_field")
        self.assertEqual(orographic["precipitation_status"], "declared_background_estimate")
        self.assertEqual(result["sources"]["monthly_precipitation_mm"]["status"],
                         "declared_background_estimate")

    def test_climate_runs_in_one_batch_and_reuses_result(self):
        x, z = self._block()
        result = sample_environment(SEED, x.ravel(), z.ravel(),
                                    elevation_sampler=self.sampler,
                                    source_identities={"dem": self.dem})
        self.assertEqual(result["cost"]["cache"]["climate_batch_passes"], 1)
        self.assertEqual(result["cost"]["source_call_counts"]["sample_climate_v2"], 1)
        self.assertEqual(result["cost"]["cache"]["bio12_exact_lookup_misses"], 0)
        self.assertEqual(result["cost"]["cache"]["thickness_exact_lookup_misses"], 0)

    def test_coarse_estimate_matches_plain_v2(self):
        x, z = self._block()
        result = sample_environment(SEED, x.ravel(), z.ravel(),
                                    elevation_sampler=self.sampler,
                                    source_identities={"dem": self.dem})
        reference = sample_climate_v2(SEED, result["x_m"].ravel(), result["z_m"].ravel(),
                                     elevation_m=result["elevation_m"].ravel())
        self.assertTrue(np.array_equal(
            np.asarray(reference["annual_precipitation_mm"]).ravel(),
            result["BIO12_mm"].ravel()))


class SoilPathTests(unittest.TestCase):
    def test_soil_uses_thirty_metre_slope_spacing(self):
        x, z = _grid(2, 2)
        result = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        self.assertEqual(result["identity"]["record"]["soil"]["parameters"]["slope_spacing_m"],
                         GRID_SPACING_M)
        self.assertEqual(result["budget"]["max_points"], MAX_POINTS)

    def test_uniform_arid_domain_raises_no_warning(self):
        """全 arid / 同 soil 输出是合法观测，不得报错或告警。"""
        import warnings
        x, z = _grid(4, 4)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        self.assertEqual(len(caught), 0)
        bands = set(int(v) for v in np.asarray(result["biome_climate_band"]).ravel())
        self.assertEqual(len(bands), 1, "this small arid block is expected to be uniform")
        self.assertTrue(np.isfinite(result["soil_depth_m"]).all())

    def test_palette_needs_landform_ordinal(self):
        x, z = _grid(1, 2)
        without = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        self.assertIsNone(without["biome_palette_index"])
        self.assertEqual(without["biome_palette_status"], NOT_AVAILABLE)
        with_ordinal = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={},
                                         landform_ordinal=0)
        self.assertEqual(with_ordinal["biome_palette_status"], "computed")
        self.assertTrue((np.asarray(with_ordinal["biome_palette_index"]) < 16).all())


class OrdinalBindingTests(unittest.TestCase):
    """ordinal 必须绑到坐标：同点不同 ordinal ⇒ ID 与输出双变；permuted ⇒ ID 不变。"""

    def test_different_ordinal_changes_identity_and_output(self):
        x, z = _grid(3, 3)
        flat_x, flat_z = x.ravel(), z.ravel()
        zeros = sample_environment(SEED, flat_x, flat_z, source_identities={},
                                   landform_ordinal=0)
        threes = sample_environment(SEED, flat_x, flat_z, source_identities={},
                                    landform_ordinal=3)
        self.assertNotEqual(zeros["identity"]["combined_identity_sha256"],
                            threes["identity"]["combined_identity_sha256"])
        self.assertFalse(np.array_equal(np.asarray(zeros["biome_palette_index"]),
                                       np.asarray(threes["biome_palette_index"])))
        self.assertTrue(zeros["identity"]["record"]["biome"]["landform_ordinal"]
                        ["supplied"])

    def test_permuted_ordinal_keeps_same_identity(self):
        x, z = _grid(2, 3)
        flat_x, flat_z = x.ravel(), z.ravel()
        ordinal_by_point = (np.arange(flat_x.size) % 4).astype(np.int64)
        first = sample_environment(SEED, flat_x, flat_z, source_identities={},
                                   landform_ordinal=ordinal_by_point)
        permutation = np.random.default_rng(11).permutation(flat_x.size)
        second = sample_environment(SEED, flat_x[permutation], flat_z[permutation],
                                    source_identities={},
                                    landform_ordinal=ordinal_by_point[permutation])
        self.assertEqual(first["identity"]["combined_identity_sha256"],
                         second["identity"]["combined_identity_sha256"])
        restored = np.empty_like(np.asarray(second["biome_palette_index"]).ravel())
        restored[permutation] = np.asarray(second["biome_palette_index"]).ravel()
        self.assertTrue(np.array_equal(restored, np.asarray(
            first["biome_palette_index"]).ravel()))

    def test_absent_ordinal_records_supplied_false(self):
        x, z = _grid(1, 2)
        result = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        self.assertFalse(result["identity"]["record"]["biome"]["landform_ordinal"]["supplied"])


class SourceKeyBindingTests(unittest.TestCase):
    """未知 source 键不得静默忽略；代码身份必须进组合记录。"""

    def test_unknown_source_key_is_refused(self):
        x, z = _grid(1, 2)
        with self.assertRaises(ValueError) as caught:
            sample_environment(SEED, x.ravel(), z.ravel(),
                              source_identities={"soil": {"identity_sha256": "0" * 64}})
        self.assertIn("unsupported source_identities", str(caught.exception))

    def test_code_identities_are_bound(self):
        x, z = _grid(1, 2)
        result = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        code = result["identity"]["record"]["code_identities"]
        for name in ('terrain_pipeline.climate_forcing',
                     'terrain_pipeline.climate_forcing',
                     'terrain_pipeline.soil_water',
                     'terrain_pipeline.climate_forcing',
                     'terrain_pipeline.geology',
                     'terrain_pipeline.geology',
                     "terrain_pipeline.hydrology_planning"):
            self.assertIn(name, code)
            self.assertEqual(len(code[name]["source_sha256"]), 64)


class CacheIdentityTests(unittest.TestCase):
    def test_material_seed_change_does_not_reuse_values(self):
        x, z = _grid(3, 3)
        first = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={})
        other = (first["identity"]["sub_seeds"]["material"] + 1) % (2 ** 64)
        second = sample_environment(SEED, x.ravel(), z.ravel(), source_identities={},
                                   material_seed=other)
        self.assertFalse(np.array_equal(
            np.asarray(first["material_erodible_thickness_m"]),
            np.asarray(second["material_erodible_thickness_m"])))
        self.assertNotEqual(first["identity"]["record"]["material"]["identity_sha256"],
                            second["identity"]["record"]["material"]["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
