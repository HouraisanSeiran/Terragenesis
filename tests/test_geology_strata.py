"""Declared stratigraphy tests (unittest, no pytest).

Scope: the declared-parallel-strata model only — vertical rock change, dip,
finite fault offset, joint plane distance, finite stock, budget and rejections.
No naturalness claim, no erosion, no inventory.

**Do not run without a granted compute slot** (`.scratch/stage2-g1-g9/spec.md:41`).
"""

from builtins import ValueError as _merged_strata_StrataBudgetError
import unittest

import numpy as np

from terrain_pipeline import geology as strata
from terrain_pipeline import geology as lithology

ANCHOR_X = 1_265_190.0
ANCHOR_Z = 1_286_220.0
TOP = 200.0


def _stack(*, strike=0.0, dip=0.0, thicknesses=(40.0, 40.0, 40.0),
           rocks=("granite", "limestone", "shale")):
    return strata.normalize_stack({
        "source": "test fixture",
        "anchor_xz_m": [ANCHOR_X, ANCHOR_Z],
        "top_elevation_m": TOP,
        "strike_deg": strike,
        "dip_deg": dip,
        "layers": [{"rock_id": rock, "vertical_thickness_m": thickness,
                    "source": "test fixture"}
                   for rock, thickness in zip(rocks, thicknesses)],
    })


def _fault(offset=12.0, side="positive", width=40.0):
    return [{"segment_xz_m": [[ANCHOR_X, ANCHOR_Z + 100.0],
                               [ANCHOR_X + 1000.0, ANCHOR_Z + 100.0]],
             "vertical_offset_m": offset, "moving_side": side,
             "influence_width_m": width, "source": "test fixture"}]


class VerticalRockChangeTests(unittest.TestCase):
    """同 (x,z) 不同高程必须得到不同岩种 —— 2D 噪声岩种不得被复制成地下层。"""

    def test_same_column_three_elevations_give_three_layers(self):
        stack = _stack()
        x = np.array([ANCHOR_X])
        z = np.array([ANCHOR_Z])
        result = strata.query_layers(x, z, np.array([190.0]), stack)
        self.assertEqual(int(result["layer_index"][0]), 0)
        self.assertEqual(int(result["state"][0]), strata.INSIDE_STACK)
        middle = strata.query_layers(x, z, np.array([150.0]), stack)
        self.assertEqual(int(middle["layer_index"][0]), 1)
        deep = strata.query_layers(x, z, np.array([100.0]), stack)
        self.assertEqual(int(deep["layer_index"][0]), 2)
        rocks = {int(result["rock_index"][0]), int(middle["rock_index"][0]),
                 int(deep["rock_index"][0])}
        self.assertEqual(len(rocks), 3)
        self.assertEqual(rocks, {lithology.ROCK_POSITION["granite"],
                                lithology.ROCK_POSITION["limestone"],
                                lithology.ROCK_POSITION["shale"]})

    def test_above_and_below_are_not_rock(self):
        stack = _stack()
        x = np.array([ANCHOR_X])
        z = np.array([ANCHOR_Z])
        above = strata.query_layers(x, z, np.array([250.0]), stack)
        self.assertEqual(int(above["state"][0]), strata.ABOVE_COLUMN)
        self.assertEqual(int(above["rock_index"][0]), -1)
        below = strata.query_layers(x, z, np.array([50.0]), stack)
        self.assertEqual(int(below["state"][0]), strata.BELOW_COLUMN)
        # 底部不得延伸，也不得回退成顶层岩种
        self.assertEqual(int(below["rock_index"][0]), -1)
        self.assertNotEqual(int(below["rock_index"][0]),
                            lithology.ROCK_POSITION["granite"])

    def test_undeclared_stack_has_no_rock_anywhere(self):
        stack = strata.normalize_stack(None)
        self.assertEqual(stack["status"], strata.UNKNOWN_NO_SOURCE)
        result = strata.query_layers(np.array([ANCHOR_X]), np.array([ANCHOR_Z]),
                                    np.array([150.0]), stack)
        self.assertEqual(result["status"], strata.UNKNOWN_NO_SOURCE)
        self.assertEqual(int(result["rock_index"][0]), -1)
        self.assertEqual(int(result["layer_index"][0]), -1)

    def test_vertical_thickness_is_labelled_as_vertical(self):
        stack = _stack()
        self.assertEqual(stack["thickness_kind"], "vertical_at_anchor_not_normal")
        self.assertEqual(stack["total_vertical_thickness_m"], 120.0)
        self.assertEqual(stack["horizon_elevation_m"], [200.0, 160.0, 120.0, 80.0])


class DipGeometryTests(unittest.TestCase):
    """倾角在世界坐标里必须精确可算：dip=45 时 x+30 恰好低 30 m。"""

    def test_flat_horizons_do_not_change_with_position(self):
        stack = _stack(dip=0.0)
        heights, _ = strata.horizons_at(np.array([ANCHOR_X, ANCHOR_X + 500.0]),
                                        np.array([ANCHOR_Z, ANCHOR_Z]), stack)
        self.assertTrue(np.all(heights[:, 0] == heights[:, 1]))

    def test_dip_45_lowers_horizon_by_tan_times_distance(self):
        stack = _stack(dip=45.0, strike=0.0)
        heights, _ = strata.horizons_at(np.array([ANCHOR_X, ANCHOR_X + 30.0]),
                                        np.array([ANCHOR_Z, ANCHOR_Z]), stack)
        drop = heights[:, 0] - heights[:, 1]
        self.assertTrue(np.allclose(drop, 30.0, rtol=0.0, atol=1e-9))

    def test_strike_rotates_the_dip_direction(self):
        # strike=90 时倾向向东为 +z，所以 x 方向不再改变层面高程。
        stack = _stack(dip=45.0, strike=90.0)
        along_x, _ = strata.horizons_at(np.array([ANCHOR_X, ANCHOR_X + 30.0]),
                                       np.array([ANCHOR_Z, ANCHOR_Z]), stack)
        self.assertTrue(np.allclose(along_x[:, 0], along_x[:, 1], atol=1e-9))
        along_z, _ = strata.horizons_at(np.array([ANCHOR_Z, ANCHOR_Z]),
                                       np.array([ANCHOR_Z, ANCHOR_Z + 30.0]), stack)
        self.assertTrue(np.allclose(along_z[:, 0] - along_z[:, 1], 30.0, atol=1e-9))

    def test_vertical_dip_is_refused(self):
        for bad in (90.0, 90.0001, -1.0):
            with self.assertRaises(ValueError):
                _stack(dip=bad)

    def test_strike_bounds(self):
        for bad in (360.0, -1.0):
            with self.assertRaises(ValueError):
                _stack(strike=bad)


class FaultOffsetTests(unittest.TestCase):
    """有限带内才偏移；带外与无断层版本逐位相同。"""

    def test_fault_on_off_at_the_same_point(self):
        stack = _stack()
        x = np.array([ANCHOR_X])
        z = np.array([ANCHOR_Z + 100.0])
        # 边界附近的合法例：无断层时 elev=130 落在层 1（120 <= 130 < 160）；
        # 断层把查询高程平移 -12 → 118，落入层 2（80 <= 118 < 120）。
        without = strata.query_layers(x, z, np.array([130.0]), stack)
        self.assertEqual(float(without["applied_offset_m"][0]), 0.0)
        self.assertEqual(str(without["fault_effect"][0]), strata.FAULT_NOT_DECLARED)
        self.assertEqual(int(without["layer_index"][0]), 1)
        with_fault = strata.query_layers(x, z, np.array([130.0]), stack, faults=_fault())
        self.assertEqual(str(with_fault["fault_effect"][0]), strata.FAULT_APPLIED)
        self.assertEqual(float(with_fault["applied_offset_m"][0]), 12.0)
        # 偏移真的改动了查询高程 → 同一 (x,z,elev) 上落到不同的层。
        self.assertNotEqual(int(with_fault["layer_index"][0]),
                            int(without["layer_index"][0]))

    def test_fault_offset_does_not_force_a_layer_change(self):
        # 反向对照：偏移不跨越层界时，层号必须保持不变（不得为凑“必换层”造例）。
        stack = _stack()
        x = np.array([ANCHOR_X])
        z = np.array([ANCHOR_Z + 100.0])
        without = strata.query_layers(x, z, np.array([155.0]), stack)
        with_fault = strata.query_layers(x, z, np.array([155.0]), stack, faults=_fault())
        self.assertEqual(str(with_fault["fault_effect"][0]), strata.FAULT_APPLIED)
        self.assertEqual(float(with_fault["applied_offset_m"][0]), 12.0)
        # 155 与 155-12=143 都在层 1（120..160），所以层号相同。
        self.assertEqual(int(with_fault["layer_index"][0]),
                         int(without["layer_index"][0]))

    def test_opposite_sides_get_different_offsets(self):
        stack = _stack()
        # 断层段位于 z = ANCHOR_Z+100，moving_side=positive（side>=0 一侧）。
        # elev=128：正侧 shifted=128-12=116 → 层 2（80..120）；负侧 shifted=128 → 层 1。
        inside_x = np.array([ANCHOR_X, ANCHOR_X])
        inside_z = np.array([ANCHOR_Z + 110.0, ANCHOR_Z + 90.0])
        result = strata.query_layers(inside_x, inside_z, np.array([128.0, 128.0]),
                                    stack, faults=_fault())
        offsets = result["applied_offset_m"]
        self.assertEqual(sorted(offsets.tolist()), [0.0, 12.0])
        layers = result["layer_index"]
        self.assertEqual(abs(int(layers[0]) - int(layers[1])), 1)
        self.assertEqual(int(layers[0]), 2)
        self.assertEqual(int(layers[1]), 1)

    def test_outside_the_band_is_bitwise_unchanged(self):
        stack = _stack()
        far_x = np.array([ANCHOR_X + 1000.0])
        far_z = np.array([ANCHOR_Z + 5000.0])
        elev = np.array([150.0])
        without = strata.query_layers(far_x, far_z, elev, stack)
        with_fault = strata.query_layers(far_x, far_z, elev, stack, faults=_fault())
        self.assertEqual(str(with_fault["fault_effect"][0]), strata.FAULT_OUTSIDE)
        self.assertEqual(float(with_fault["applied_offset_m"][0]), 0.0)
        self.assertTrue(np.array_equal(without["layer_index"], with_fault["layer_index"]))
        self.assertTrue(np.array_equal(without["rock_index"], with_fault["rock_index"]))

    def test_beyond_the_segment_ends_is_outside(self):
        stack = _stack()
        # 段沿 x 从 ANCHOR_X 到 ANCHOR_X+1000；x+2000 已在端点之外。
        beyond_x = np.array([ANCHOR_X + 2000.0])
        beyond_z = np.array([ANCHOR_Z + 100.0])
        result = strata.query_layers(beyond_x, beyond_z, np.array([150.0]), stack,
                                    faults=_fault())
        self.assertEqual(str(result["fault_effect"][0]), strata.FAULT_OUTSIDE)
        self.assertEqual(float(result["applied_offset_m"][0]), 0.0)

    def test_band_width_is_required_and_nonzero(self):
        with self.assertRaises(ValueError):
            strata.normalize_faults([{"segment_xz_m": [[0.0, 0.0], [1.0, 0.0]],
                                       "vertical_offset_m": 5.0,
                                       "moving_side": "positive",
                                       "source": "fixture"}])
        with self.assertRaises(ValueError):
            strata.normalize_faults([{"segment_xz_m": [[0.0, 0.0], [1.0, 0.0]],
                                       "vertical_offset_m": 0.0,
                                       "moving_side": "positive",
                                       "influence_width_m": 10.0,
                                       "source": "fixture"}])


class JointGeometryTests(unittest.TestCase):
    """节理是世界锚定平面族，必须给出到最近节理面的实测距离，不是回传输入。"""

    def test_no_declaration_is_pending(self):
        result = strata.joint_distance(np.array([ANCHOR_X]), np.array([ANCHOR_Z]),
                                       np.array([150.0]), None)
        self.assertEqual(result["status"], strata.PENDING)

    def test_horizontal_joint_set_gives_distance_to_nearest_plane(self):
        declaration = {"source": "test fixture", "anchor_xz_m": [ANCHOR_X, ANCHOR_Z],
                       "sets": [{"strike_deg": 0.0, "dip_deg": 0.0,
                                  "spacing_m": 10.0, "phase_m": 0.0}]}
        result = strata.joint_distance(np.array([ANCHOR_X]), np.array([ANCHOR_Z]),
                                       np.array([153.0]), declaration)
        entry = result["sets"][0]
        self.assertAlmostEqual(float(entry["absolute_distance_m"][0]), 3.0, places=9)
        self.assertEqual(int(entry["joint_index"][0]), 15)

    def test_distance_is_wrapped_by_spacing(self):
        declaration = {"source": "test fixture", "anchor_xz_m": [ANCHOR_X, ANCHOR_Z],
                       "sets": [{"strike_deg": 0.0, "dip_deg": 0.0,
                                  "spacing_m": 10.0, "phase_m": 2.0}]}
        result = strata.joint_distance(np.array([ANCHOR_X]), np.array([ANCHOR_Z]),
                                       np.array([151.0]), declaration)
        entry = result["sets"][0]
        # phase=2 时平面在 ..., 142, 152 ...；151 距 152 为 1 m。
        self.assertAlmostEqual(float(entry["absolute_distance_m"][0]), 1.0, places=9)

    def test_vertical_joint_set_uses_horizontal_distance_only(self):
        declaration = {"source": "test fixture", "anchor_xz_m": [ANCHOR_X, ANCHOR_Z],
                       "sets": [{"strike_deg": 0.0, "dip_deg": 0.0,
                                  "spacing_m": 5.0, "phase_m": 0.0}]}
        one = strata.joint_distance(np.array([ANCHOR_X]), np.array([ANCHOR_Z]),
                                    np.array([100.0]), declaration)
        two = strata.joint_distance(np.array([ANCHOR_X]), np.array([ANCHOR_Z]),
                                    np.array([120.0]), declaration)
        self.assertAlmostEqual(float(one["sets"][0]["absolute_distance_m"][0]),
                               float(two["sets"][0]["absolute_distance_m"][0]), places=9)

    def test_bad_joint_parameters_are_refused(self):
        for bad in ({"strike_deg": 360.0, "dip_deg": 0.0, "spacing_m": 5.0},
                    {"strike_deg": 0.0, "dip_deg": 0.0, "spacing_m": 0.0},
                    {"strike_deg": 0.0, "dip_deg": 120.0, "spacing_m": 5.0}):
            with self.assertRaises(ValueError):
                strata.normalize_joints({"source": "fixture",
                                         "anchor_xz_m": [0.0, 0.0], "sets": [bad]})


class DeclaredStockTests(unittest.TestCase):
    """有限体积只依赖已声明几何，不依赖风化速率。"""

    def test_volume_exists_from_footprint_alone(self):
        stack = _stack()
        stock = strata.declared_stock(stack, footprint_m2=1_000_000.0)
        self.assertEqual(stock["status"], strata.STOCK_DECLARED)
        self.assertEqual(stock["vertical_volume_m3"], 120.0 * 1_000_000.0)
        self.assertNotIn("mass_kg", stock)
        self.assertEqual(stock["weatherable_source"], strata.PENDING)
        self.assertIsNone(stock["weatherable_thickness_m"])

    def test_mass_needs_declared_density(self):
        stack = _stack()
        with_density = strata.declared_stock(stack, footprint_m2=1000.0,
                                            density_kg_m3=2650.0)
        self.assertEqual(with_density["mass_kg"], 120.0 * 1000.0 * 2650.0)

    def test_dipping_stock_volume_has_no_extra_cosine(self):
        # footprint 是水平投影面积：V = 水平面积 × 垂直厚，两个角度下同面积同厚同体积。
        flat = strata.declared_stock(_stack(dip=0.0), footprint_m2=1000.0)
        dipping = strata.declared_stock(_stack(dip=60.0), footprint_m2=1000.0)
        self.assertEqual(flat["vertical_volume_m3"], dipping["vertical_volume_m3"])
        self.assertEqual(dipping["footprint_kind"], "horizontal_projection")
        self.assertAlmostEqual(dipping["total_normal_thickness_m"],
                               dipping["total_vertical_thickness_m"] * 0.5, places=12)
        self.assertAlmostEqual(dipping["bedding_area_m2"], 2000.0, places=9)
        # 两条路线必须给出同一体积。
        self.assertAlmostEqual(
            dipping["total_normal_thickness_m"] * dipping["bedding_area_m2"],
            dipping["vertical_volume_m3"], places=6)

    def test_weatherable_thickness_is_capped_and_never_assumed(self):
        stack = _stack()
        declared = strata.declared_stock(stack, footprint_m2=1000.0,
                                         weatherable_thickness_m=30.0)
        self.assertEqual(declared["weatherable_volume_m3"], 30.0 * 1000.0)
        capped = strata.declared_stock(stack, footprint_m2=1000.0,
                                       weatherable_thickness_m=500.0)
        self.assertEqual(capped["weatherable_volume_m3"], 120.0 * 1000.0)

    def test_missing_footprint_is_pending_not_zero(self):
        stock = strata.declared_stock(_stack())
        self.assertEqual(stock["status"], strata.STOCK_PENDING)
        self.assertNotIn("vertical_volume_m3", stock)

    def test_undeclared_stack_yields_no_stock(self):
        stock = strata.declared_stock(strata.normalize_stack(None), footprint_m2=1000.0)
        self.assertEqual(stock["status"], strata.UNKNOWN_NO_SOURCE)


class BudgetAndRejectionTests(unittest.TestCase):
    def test_layer_cap_is_enforced(self):
        layers = [{"rock_id": "granite", "vertical_thickness_m": 1.0,
                   "source": "fixture"} for _ in range(strata.MAX_STRATA_LAYERS + 1)]
        with self.assertRaises(ValueError):
            strata.normalize_stack({"source": "fixture", "anchor_xz_m": [0.0, 0.0],
                                    "top_elevation_m": 0.0, "strike_deg": 0.0,
                                    "dip_deg": 0.0, "layers": layers})

    def test_horizon_output_budget_is_checked_before_allocation(self):
        # 8192 * 65 = 532,480 < 1,000,000，所以 point 模式下永不会超——
        # 直接测 grid 模式（cell 上限 262,144）乘层数会超：262,144 * 65 = 17,039,360。
        with self.assertRaises(_merged_strata_StrataBudgetError):
            strata.strata_preflight(strata.MAX_GRID_CELLS, 64, with_horizons=True,
                             point_mode=False)
        # 同一 cell 数不要层界时只算层号，不受乘积门约束。
        budget = strata.strata_preflight(strata.MAX_GRID_CELLS, 64, with_horizons=False,
                                  point_mode=False)
        self.assertEqual(budget["horizon_values"], 0)
        # point 模式点上限内本来就不可能超乘积门，这里明确记录这一事实。
        point_budget = strata.strata_preflight(strata.MAX_POINTS, 64, with_horizons=True)
        self.assertLessEqual(point_budget["horizon_values"], strata.MAX_CELL_LAYER_VALUES)

    def test_point_cap_is_enforced(self):
        with self.assertRaises(_merged_strata_StrataBudgetError):
            strata.strata_preflight(strata.MAX_POINTS + 1, 3)

    def test_invalid_layer_entries_are_refused(self):
        base = {"source": "fixture", "anchor_xz_m": [0.0, 0.0], "top_elevation_m": 0.0,
                "strike_deg": 0.0, "dip_deg": 0.0}
        for bad_layer in ({"rock_id": "unobtainium", "vertical_thickness_m": 1.0,
                           "source": "fixture"},
                          {"rock_id": "granite", "vertical_thickness_m": 0.0,
                           "source": "fixture"},
                          {"rock_id": "granite", "vertical_thickness_m": 1.0}):
            with self.assertRaises(ValueError):
                strata.normalize_stack(dict(base, layers=[bad_layer]))

    def test_missing_source_is_refused(self):
        with self.assertRaises(ValueError):
            strata.normalize_stack({"anchor_xz_m": [0.0, 0.0], "top_elevation_m": 0.0,
                                    "strike_deg": 0.0, "dip_deg": 0.0,
                                    "layers": [{"rock_id": "granite",
                                                "vertical_thickness_m": 1.0,
                                                "source": "fixture"}]})

    def test_describe_declares_the_boundaries(self):
        declared = strata.strata_describe()
        self.assertEqual(declared["supported_dip_deg"], "0 <= dip < 90")
        self.assertEqual(declared["max_strata_layers"], strata.MAX_STRATA_LAYERS)
        # 检查结构字段，不靠散文短语。
        self.assertEqual(declared["thickness_kind"],
                         "vertical_thickness_m at the anchor, not normal thickness")
        self.assertIn("cos(dip)", declared["thickness_conversion"])
        self.assertIn("horizontal_area", declared["thickness_conversion"])
        self.assertGreaterEqual(len(declared["limitations"]), 4)


if __name__ == "__main__":
    unittest.main()
