"""G2 地质物性组合层的验收测试（unittest，无 pytest）。

只测外部行为：非空层序与非零填充、逐位复用既有核、扩展表身份、
30 m 格心/参考点映射、乱序与分窗一致、真实宽度消费者因果对照、
诚实边界、非法输入早拒、预算预检。

**本文件当前不得运行**：计算槽未授（`.scratch/stage2-g1-g9/spec.md:41`）。
不测内部实现，不测“自然度”，不假定“花岗岩一定宽于页岩”（宽度同时依赖
bed 与 bank 两个硬度，方向由公式与实际输入决定，不由岩名强设）。
"""

from builtins import ValueError as _merged_geology_GeologyBudgetError
import inspect
import unittest

import numpy as np

from terrain_pipeline import geology
from terrain_pipeline import geology as lithology
from terrain_pipeline import geology as material
from terrain_pipeline.surface_rivers.world_channel_graph import derive_noise_seed

SEED = 20261020
BASE_X = 1_265_190.0
BASE_Z = 1_286_220.0
SHAPE = (4, 5)
SPACING = geology.GRID_SPACING_M
MATERIAL_PURPOSE = "geography-stage2-material"


def _origin():
    return [BASE_X, BASE_Z]


def _column(**kwargs):
    options = {"shape": SHAPE, "origin_m_xz": _origin(), "spacing_m": SPACING,
               "world_seed": SEED,
               "material_seed": derive_noise_seed(SEED, MATERIAL_PURPOSE)}
    options.update(kwargs)
    return geology.geology_column(**options)


def _strength(value, source="test fixture", scale="intact rock mass"):
    return {"status": geology.DECLARED, "units": geology.EXTENDED_FIELDS[
        "uniaxial_strength_mpa"], "value": value, "source": source,
            "rock_mass_scale": scale}


def _partial_strength_table(rock_id="granite", value=200.0):
    return {rock_id: {"uniaxial_strength_mpa": _strength(value)}}


class LayerColumnTests(unittest.TestCase):
    """非空层序；没有来源时如实 unknown，绝不写 0 也不写半无限。"""

    def test_layer_definitions_are_not_empty_and_ordered(self):
        definitions = geology.layer_definitions()
        self.assertGreaterEqual(len(definitions), 2)
        self.assertEqual([layer["name"] for layer in definitions], ["cover", "bedrock"])
        self.assertEqual([layer["order"] for layer in definitions], [0, 1])

    def test_grid_column_default_bedrock_thickness_is_unknown_not_zero(self):
        bundle = _column()
        status = bundle["metadata"]["fields_status"]
        self.assertEqual(status["bedrock_thickness_m"], geology.UNKNOWN_NO_SOURCE)
        self.assertNotIn("bedrock_thickness_m", bundle["arrays"])
        self.assertTrue(geology.validate_geology_properties(bundle))

    def test_point_form_has_no_cover_thickness(self):
        x_m, z_m = geology.cell_centres(SHAPE, origin_m_xz=_origin(), spacing_m=SPACING)
        bundle = geology.properties_at(x_m, z_m, world_seed=SEED)
        self.assertEqual(bundle["metadata"]["fields_status"]["cover_thickness_m"],
                         geology.NOT_SAMPLED_NO_GRID_WINDOW)
        self.assertNotIn("cover_thickness_m", bundle["arrays"])
        self.assertTrue(geology.validate_geology_properties(bundle))

    def test_declared_zero_bedrock_thickness_is_legal_but_undeclared_is_unknown(self):
        # 0 m 是「有来源的有限值」，因此允许；但无声明的情况必须仍是 unknown，不是 0。
        declared = {"source": "test fixture", "bedrock_thickness_m": 0.0}
        bundle = _column(strata_declaration=declared)
        self.assertEqual(bundle["metadata"]["fields_status"]["bedrock_thickness_m"],
                         geology.DECLARED)
        self.assertTrue(np.all(bundle["arrays"]["bedrock_thickness_m"] == 0.0))
        unknown = _column()
        self.assertNotIn("bedrock_thickness_m", unknown["arrays"])

    def test_strata_declaration_requires_a_source(self):
        with self.assertRaises(ValueError):
            _column(strata_declaration={"bedrock_thickness_m": 12.0})

    def test_declared_strata_are_finite_and_nonnegative(self):
        with self.assertRaises(ValueError):
            _column(strata_declaration={"source": "fixture", "bedrock_thickness_m": -1.0})
        with self.assertRaises(ValueError):
            _column(strata_declaration={"source": "fixture",
                                        "bedrock_thickness_m": float("nan")})


class ReuseOfExistingCoresTests(unittest.TestCase):
    """每个物理量都必须逐位复用既有核，不重算。"""

    def test_rock_fields_match_lithology_at_the_same_cell_centres(self):
        bundle = _column()
        x_m, z_m = geology.cell_centres(SHAPE, origin_m_xz=_origin(), spacing_m=SPACING)
        reference = lithology.sample_lithology_points(x_m, z_m, world_seed=SEED)
        arrays = bundle["arrays"]
        for name in ("rock_index", "class_index", "bed_hardness", "bank_hardness",
                     "erodibility_index"):
            self.assertTrue(np.array_equal(arrays[name],
                                           np.asarray(reference[name])), name)

    def test_cover_thickness_matches_material_field(self):
        bundle = _column()
        reference = material.make_material_field(
            SHAPE, origin_m_xz=_origin(), spacing_m=SPACING,
            seed=derive_noise_seed(SEED, MATERIAL_PURPOSE))
        self.assertTrue(np.array_equal(
            bundle["arrays"]["cover_thickness_m"],
            np.asarray(reference["arrays"]["erodible_thickness_m"])))

    def test_cover_thickness_is_declared_as_not_soil(self):
        bundle = _column()
        self.assertIn("not soil depth", bundle["metadata"]["limitations"][0])

    def test_rock_table_lookup_fields_come_from_the_table(self):
        bundle = _column()
        arrays = bundle["arrays"]
        for name in ("mohs_hardness", "solubility", "porosity"):
            for position, rock_id in enumerate(lithology.ROCK_ORDER):
                record = lithology.rock_record(rock_id)
                expected = record[name]
                selected = arrays["rock_index"] == position
                if selected.any():
                    self.assertTrue(np.all(arrays[name][selected] == expected), name)

    def test_bank_hardness_never_exceeds_bed_hardness(self):
        arrays = _column()["arrays"]
        self.assertFalse(np.any(arrays["bank_hardness"] > arrays["bed_hardness"]))


class CoordinateSemanticsTests(unittest.TestCase):
    """30 m 参考点不等于格心；不静默吸附。"""

    def test_cell_centres_are_half_a_cell_from_reference_nodes(self):
        x_m, z_m = geology.cell_centres((2, 2), origin_m_xz=[0.0, 0.0], spacing_m=SPACING)
        self.assertEqual(float(x_m[0, 0]), SPACING / 2.0)
        self.assertEqual(float(z_m[0, 0]), SPACING / 2.0)
        self.assertEqual(float(x_m[0, 1]), 1.5 * SPACING)
        self.assertEqual(geology.HALF_CELL_M, SPACING / 2.0)

    def test_reference_points_are_refused_without_explicit_offset(self):
        # 30 m 整数参考节点 ≠ 格心：默认必须拒，而不是静默吸附到所在格。
        nodes_x = np.array([BASE_X, BASE_X + SPACING])
        nodes_z = np.array([BASE_Z, BASE_Z + SPACING])
        with self.assertRaises(ValueError):
            geology.reference_points_to_cells(nodes_x, nodes_z, origin_m_xz=_origin(),
                                              spacing_m=SPACING)

    def test_cell_centres_are_accepted_because_they_are_the_sampled_points(self):
        x_m, z_m = geology.cell_centres(SHAPE, origin_m_xz=_origin(), spacing_m=SPACING)
        mapped = geology.reference_points_to_cells(x_m, z_m, origin_m_xz=_origin(),
                                                  spacing_m=SPACING)
        self.assertTrue(np.allclose(mapped["offset_m"], 0.0, rtol=0.0, atol=1e-9))
        self.assertFalse(mapped["snapped"])

    def test_reference_nodes_report_the_half_cell_offset(self):
        nodes_x = np.array([BASE_X, BASE_X + SPACING])
        nodes_z = np.array([BASE_Z, BASE_Z])
        mapped = geology.reference_points_to_cells(
            nodes_x, nodes_z, origin_m_xz=_origin(), spacing_m=SPACING,
            accept_offset_m=geology.HALF_CELL_M * np.sqrt(2.0))
        # 节点→格心是 (±15 m, ±15 m) 的两轴偏移，欧氏距离 = 15*sqrt(2)。
        self.assertTrue(np.allclose(mapped["offset_m"], geology.HALF_CELL_M * np.sqrt(2.0)))
        self.assertFalse(mapped["snapped"])
        self.assertEqual(mapped["row_index"].tolist(), [0, 0])
        self.assertEqual(mapped["column_index"].tolist(), [0, 1])

    def test_accepting_a_wrong_offset_is_refused(self):
        with self.assertRaises(ValueError):
            geology.reference_points_to_cells(
                np.array([BASE_X]), np.array([BASE_Z]), origin_m_xz=_origin(),
                spacing_m=SPACING, accept_offset_m=0.0)

    def test_unanchored_origin_is_refused_not_snapped(self):
        with self.assertRaises(ValueError):
            geology.cell_centres((2, 2), origin_m_xz=[1.0, 0.0], spacing_m=SPACING)

    def test_non_30m_spacing_is_refused(self):
        for spacing in (10_000.0, 1.0, 29.999):
            with self.assertRaises(ValueError):
                geology.cell_centres((2, 2), origin_m_xz=[0.0, 0.0], spacing_m=spacing)


class OrderAndWindowIndependenceTests(unittest.TestCase):
    """同一点逐位一致：单点、乱序、分窗都不得改变结果。"""

    def test_shuffled_points_match_sorted_points(self):
        x_m, z_m = geology.cell_centres(SHAPE, origin_m_xz=_origin(), spacing_m=SPACING)
        flat_x = x_m.reshape(-1)
        flat_z = z_m.reshape(-1)
        order = np.array([4, 0, 17, 3, 1, 19, 2, 8, 15, 6, 11, 9, 13, 5, 18, 7, 16, 10,
                          12, 14])
        straight = geology.properties_at(flat_x, flat_z, world_seed=SEED)
        shuffled = geology.properties_at(flat_x[order], flat_z[order], world_seed=SEED)
        for name in ("rock_index", "class_index", "bed_hardness", "bank_hardness"):
            self.assertTrue(np.array_equal(straight["arrays"][name][order],
                                           shuffled["arrays"][name]), name)
        self.assertEqual(straight["metadata"]["points_digest"],
                         shuffled["metadata"]["points_digest"])

    def test_point_form_matches_the_same_cells_in_a_window(self):
        column = _column()
        x_m, z_m = geology.cell_centres(SHAPE, origin_m_xz=_origin(), spacing_m=SPACING)
        points = geology.properties_at(x_m, z_m, world_seed=SEED)
        for name in ("rock_index", "bed_hardness", "bank_hardness", "erodibility_index"):
            self.assertTrue(np.array_equal(column["arrays"][name],
                                           points["arrays"][name]), name)

    def test_offset_window_is_seamless(self):
        x_m, z_m = geology.cell_centres(SHAPE, origin_m_xz=_origin(), spacing_m=SPACING)
        probe_x = float(x_m[2, 3])
        probe_z = float(z_m[2, 3])
        single = geology.properties_at(np.array([probe_x]), np.array([probe_z]),
                                      world_seed=SEED)
        # 起点平移后的一个小窗，其 [0,0] 格心正好落在上面那个探测点上。
        shifted_origin = [BASE_X + 3 * SPACING, BASE_Z + 2 * SPACING]
        shifted = geology.geology_column(
            (2, 3), origin_m_xz=shifted_origin, spacing_m=SPACING, world_seed=SEED,
            material_seed=derive_noise_seed(SEED, MATERIAL_PURPOSE))
        shifted_x, shifted_z = geology.cell_centres(
            (2, 3), origin_m_xz=shifted_origin, spacing_m=SPACING)
        self.assertEqual(float(shifted_x[0, 0]), probe_x)
        self.assertEqual(float(shifted_z[0, 0]), probe_z)
        self.assertEqual(int(single["arrays"]["rock_index"][0]),
                         int(shifted["arrays"]["rock_index"][0, 0]))
        self.assertEqual(float(single["arrays"]["bed_hardness"][0]),
                         float(shifted["arrays"]["bed_hardness"][0, 0]))


class ExtendedPropertyTests(unittest.TestCase):
    """扩展物性：默认全 pending，不编造常量；声明则必须带来源与等级。"""

    def test_default_table_is_all_pending_and_emits_no_numbers(self):
        table = geology.default_extended_properties()
        self.assertEqual(sorted(table), sorted(lithology.ROCK_ORDER))
        for rock_id in lithology.ROCK_ORDER:
            for field in geology.EXTENDED_FIELDS:
                self.assertEqual(table[rock_id][field]["status"], geology.PENDING)
        bundle = _column()
        for field in geology.EXTENDED_FIELDS:
            self.assertNotIn(field, bundle["arrays"])
            self.assertNotIn(field + "_available", bundle["arrays"])
            self.assertEqual(bundle["metadata"]["fields_status"][field], geology.PENDING)

    def test_partial_declaration_carries_an_availability_mask(self):
        # 固定点上到底出现哪些岩种由该窗口实际采样决定，不预设。先采一次拿真实 rock_id。
        observed = _column()
        first_rock = lithology.ROCK_ORDER[int(observed["arrays"]["rock_index"][0, 0])]
        bundle = _column(extended_properties=_partial_strength_table(rock_id=first_rock,
                                                                    value=200.0))
        arrays = bundle["arrays"]
        mask = arrays["uniaxial_strength_mpa_available"]
        self.assertEqual(mask.dtype, np.dtype(bool))
        # 该岩种确实出现在 [0,0]，所以掩码在那里必然为真（不是“为凑非空而造点”）。
        self.assertTrue(bool(mask[0, 0]))
        self.assertTrue(np.all(arrays["uniaxial_strength_mpa"][~mask] == 0.0))
        pending = bundle["metadata"]["extended_pending_rock_ids"]["uniaxial_strength_mpa"]
        self.assertNotIn(first_rock, pending)
        self.assertEqual(len(pending), len(lithology.ROCK_ORDER) - 1)
        self.assertEqual(bundle["metadata"]["fields_status"]["uniaxial_strength_mpa"],
                         geology.PARTIALLY_DECLARED)
        self.assertTrue(geology.validate_geology_properties(bundle))

    def test_mask_matches_the_declared_rock_exactly(self):
        # 掩码不是「随便非空」，而是恰好等于「该格 rock_id == 已声明岩种」。
        observed = _column()
        target = lithology.ROCK_ORDER[int(observed["arrays"]["rock_index"][-1, -1])]
        bundle = _column(extended_properties=_partial_strength_table(rock_id=target))
        arrays = bundle["arrays"]
        rock_index = arrays["rock_index"]
        declared_position = lithology.ROCK_POSITION[target]
        expected_mask = rock_index == declared_position
        self.assertTrue(np.array_equal(arrays["uniaxial_strength_mpa_available"],
                                       expected_mask))
        # 已声明处 = 200 MPa；未声明处 = 0 且无意义（必须读掩码）。
        self.assertTrue(np.all(arrays["uniaxial_strength_mpa"][expected_mask] == 200.0))
        self.assertTrue(np.all(arrays["uniaxial_strength_mpa"][~expected_mask] == 0.0))
        pending = bundle["metadata"]["extended_pending_rock_ids"]["uniaxial_strength_mpa"]
        self.assertNotIn(target, pending)
        self.assertEqual(len(pending), len(lithology.ROCK_ORDER) - 1)
        self.assertEqual(bundle["metadata"]["fields_status"]["uniaxial_strength_mpa"],
                         geology.PARTIALLY_DECLARED)
        self.assertTrue(geology.validate_geology_properties(bundle))

    def test_declared_value_without_source_is_refused(self):
        bad = {"granite": {"uniaxial_strength_mpa": {
            "status": geology.DECLARED, "units": "MPa", "value": 200.0,
            "rock_mass_scale": "intact"}}}
        with self.assertRaises(ValueError):
            _column(extended_properties=bad)

    def test_unknown_rock_id_and_unknown_field_are_refused(self):
        with self.assertRaises(ValueError):
            _column(extended_properties={"unobtainium": {}})
        with self.assertRaises(ValueError):
            _column(extended_properties={"granite": {"tensile_strength_mpa": _strength(1.0)}})

    def test_wrong_units_are_refused(self):
        wrong = {"granite": {"intrinsic_permeability_m2": {
            "status": geology.DECLARED, "units": "m/s", "value": 1e-15,
            "source": "fixture", "rock_mass_scale": "intact"}}}
        with self.assertRaises(ValueError):
            _column(extended_properties=wrong)

    def test_extended_identity_changes_with_the_table(self):
        plain = geology.normalize_extended_properties()
        declared = geology.normalize_extended_properties(
            _partial_strength_table(value=180.0))
        self.assertNotEqual(geology.extended_properties_identity(plain),
                            geology.extended_properties_identity(declared))
        first = _column()
        second = _column()
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        changed = _column(extended_properties=_partial_strength_table())
        self.assertNotEqual(first["identity_sha256"], changed["identity_sha256"])

    def test_identity_binds_the_rock_table_and_the_core_versions(self):
        bundle = _column()
        metadata = bundle["metadata"]
        self.assertEqual(metadata["rock_table_identity_sha256"],
                         lithology.rock_table_identity())
        self.assertEqual(metadata["lithology_subseeds"],
                         lithology.lithology_subseeds(SEED))
        self.assertEqual(metadata["material"]["seed"],
                         derive_noise_seed(SEED, MATERIAL_PURPOSE))
        self.assertEqual(metadata["material"]["identity_sha256"],
                         material.make_material_field(
                             SHAPE, origin_m_xz=_origin(), spacing_m=SPACING,
                             seed=derive_noise_seed(SEED, MATERIAL_PURPOSE))["identity_sha256"])


class JointAndFaultDeclarationTests(unittest.TestCase):
    """节理/断层只作声明；角度与间距各自校验；错层永远未验证。"""

    def test_no_joint_declaration_is_pending(self):
        bundle = _column()
        self.assertEqual(bundle["metadata"]["joint_declaration"]["status"],
                         geology.PENDING)

    def test_declared_joints_are_kept_with_units(self):
        declaration = {"source": "fixture", "sets": [
            {"strike_deg": 350.0, "dip_deg": 90.0, "spacing_m": 6.0}]}
        bundle = _column(joint_declaration=declaration)
        joints = bundle["metadata"]["joint_declaration"]
        self.assertEqual(joints["status"], geology.DECLARED)
        self.assertEqual(joints["sets"][0]["strike_deg"], 350.0)

    def test_joint_angles_and_spacing_are_validated_independently(self):
        for bad in ({"strike_deg": 360.0, "dip_deg": 90.0, "spacing_m": 6.0},
                    {"strike_deg": 10.0, "dip_deg": 91.0, "spacing_m": 6.0},
                    {"strike_deg": 10.0, "dip_deg": 45.0, "spacing_m": 0.0}):
            with self.assertRaises(ValueError):
                _column(joint_declaration={"source": "fixture", "sets": [bad]})

    def test_fault_declaration_stays_unverified(self):
        declaration = {"source": "fixture", "plane_origin_xz_m": [BASE_X, BASE_Z],
                       "strike_degrees": 20.0, "slip_m": 40.0,
                       "moving_side": "positive", "transition_width_m": 90.0}
        bundle = _column(fault_declaration=declaration)
        fault = bundle["metadata"]["fault_context"]
        self.assertEqual(fault["status"], geology.DECLARED_GEOMETRY_NOT_LITHOLOGY_OFFSET)
        self.assertEqual(fault["strata_offset_status"], geology.UNVERIFIED)

    def test_no_fault_declaration_is_pending(self):
        bundle = _column()
        self.assertEqual(bundle["metadata"]["fault_context"]["status"], geology.PENDING)
        self.assertEqual(bundle["metadata"]["fault_context"]["strata_offset_status"],
                         geology.PENDING)

    def test_negative_slip_is_refused(self):
        with self.assertRaises(ValueError):
            geology.fault_context({"source": "fixture", "plane_origin_xz_m": [0.0, 0.0],
                                   "strike_degrees": 0.0, "slip_m": -1.0,
                                   "moving_side": "positive", "transition_width_m": 10.0})


class RealConsumerTests(unittest.TestCase):
    """一个真实公开消费者：既有宽度律。方向由公式与输入决定，不由岩名强设。"""

    def setUp(self):
        self.bundle = _column()
        self.area = np.full(SHAPE, 25_000_000.0, np.float64)
        self.options = {"reference_discharge_m3_s": 100.0, "reference_width_m": 40.0,
                        "min_width_m": 1.0, "max_width_m": 5000.0}

    def test_width_comes_from_the_existing_law(self):
        from terrain_pipeline.lake import channel_width_from_lithology_m as channel_width_from_lithology_m
        result = geology.channel_width_m(self.bundle, self.area, **self.options)
        reference, reference_q = channel_width_from_lithology_m(
            self.area.reshape(-1),
            self.bundle["arrays"]["bed_hardness"].reshape(-1),
            self.bundle["arrays"]["bank_hardness"].reshape(-1),
            reference_discharge_m3_s=self.options["reference_discharge_m3_s"],
            reference_width_m=self.options["reference_width_m"],
            min_width_m=self.options["min_width_m"],
            max_width_m=self.options["max_width_m"])
        self.assertTrue(np.array_equal(result["width_m"], reference.reshape(SHAPE)))
        self.assertTrue(np.allclose(result["design_q_m3_s"], reference_q.reshape(SHAPE)))
        self.assertEqual(result["overrides_used"], [])
        self.assertEqual(result["consumer"],
                         "surface_rivers.world_reach_lake.channel_width_from_lithology_m")
        self.assertEqual(sorted(result["consumed_fields"]),
                         ["bank_hardness", "bed_hardness"])

    def test_causal_control_bed_hardness_changes_width(self):
        base = geology.channel_width_m(self.bundle, self.area, **self.options)["width_m"]
        harder_bed = np.clip(self.bundle["arrays"]["bed_hardness"] + 0.3, 0.0, 1.0)
        harder_bank = np.minimum(self.bundle["arrays"]["bank_hardness"], harder_bed)
        changed = geology.channel_width_m(
            self.bundle, self.area, bed_hardness=harder_bed, bank_hardness=harder_bank,
            **self.options)
        self.assertEqual(changed["overrides_used"], ["bed_hardness", "bank_hardness"])
        self.assertFalse(np.allclose(base, changed["width_m"]))
        # 床更硬 → 侧向做功更多 → 同 Q 下不会变窄（既有律的方向，不是岩名假设）
        self.assertTrue(np.all(changed["width_m"] >= base - 1e-12))

    def test_causal_control_bank_hardness_changes_width(self):
        base = geology.channel_width_m(self.bundle, self.area, **self.options)["width_m"]
        softer_bank = np.clip(self.bundle["arrays"]["bank_hardness"] - 0.3, 0.0, 1.0)
        changed = geology.channel_width_m(
            self.bundle, self.area, bank_hardness=softer_bank, **self.options)
        self.assertEqual(changed["overrides_used"], ["bank_hardness"])
        self.assertFalse(np.allclose(base, changed["width_m"]))
        # 岸更软 → 抵抗展宽更小 → 不会变窄
        self.assertTrue(np.all(changed["width_m"] >= base - 1e-12))

    def test_override_must_be_in_range_and_shaped(self):
        with self.assertRaises(ValueError):
            geology.channel_width_m(self.bundle, self.area,
                                    bed_hardness=np.full(SHAPE, 1.5), **self.options)
        with self.assertRaises(ValueError):
            geology.channel_width_m(self.bundle, self.area,
                                    bed_hardness=np.full((2, 2), 0.5), **self.options)

    def test_consumer_rejects_mismatched_area_count(self):
        with self.assertRaises(ValueError):
            geology.channel_width_m(self.bundle, np.full(3, 1e7), **self.options)

    def test_module_is_not_wired_into_a_default_path(self):
        declared = geology.properties_describe()
        self.assertIn("channel_width_m", declared["explicit_consumers"])
        joined = " ".join(declared["never"])
        self.assertIn("importing the A1 environment query", joined)


class HonestBoundaryTests(unittest.TestCase):
    """未接线的字段必须如实 pending，不能写成已接线。"""

    def test_no_consumer_for_permeability_or_solubility(self):
        declared = geology.properties_describe()
        self.assertIn("intrinsic_permeability_m2", declared["fields_without_consumer"])
        self.assertIn("solubility", declared["fields_without_consumer"])

    def test_never_list_binds_the_declared_boundaries(self):
        joined = " ".join(geology.properties_describe()["never"])
        for text in ("a second rock table", "inverting porosity into permeability",
                     "treating compressive strength as tensile strength",
                     "a regolith or soil inventory", "any temperature input",
                     "10 km compatibility"):
            self.assertIn(text, joined)

    def test_no_temperature_field_is_returned(self):
        # 检查实际结构与签名，不靠字符串搜索禁令文本。
        bundle = _column()
        names = set(bundle["arrays"]) | set(bundle["metadata"])
        self.assertFalse([name for name in names if "temperature" in str(name).lower()])
        for function in (geology.properties_at, geology.geology_column,
                         geology.channel_width_m):
            parameters = inspect.signature(function).parameters
            self.assertFalse([name for name in parameters
                              if "temperature" in name.lower() or name in ("temp_c", "kelvin")],
                             function.__name__)
        point = geology.properties_at(np.array([BASE_X]), np.array([BASE_Z]), world_seed=SEED)
        self.assertFalse([name for name in point["arrays"] if "temperature" in name.lower()])
        # 诚实禁令仍然保留（不能被当成错误改掉）。
        self.assertIn("any temperature input", " ".join(geology.properties_describe()["never"]))

    def test_material_thickness_is_not_called_soil_or_stock(self):
        metadata = _column()["metadata"]
        joined = " ".join(metadata["limitations"])
        self.assertIn("not soil depth", joined)
        self.assertIn("not regolith stock", joined)
        self.assertEqual(metadata["material"]["semantics"],
                         "erodible thickness, not soil depth and not a stock")


class RejectionAndBudgetTests(unittest.TestCase):
    """非法输入早拒；预算在任何容器分配之前预检。"""

    def test_bad_world_seed_is_refused(self):
        for seed in (-1, 2 ** 64, True, 1.5):
            with self.assertRaises(ValueError):
                geology.properties_at(np.array([0.0]), np.array([0.0]), world_seed=seed)

    def test_non_finite_coordinates_are_refused(self):
        with self.assertRaises(ValueError):
            geology.properties_at(np.array([np.nan]), np.array([0.0]))

    def test_grid_limits_are_checked_before_material_allocation(self):
        with self.assertRaises(_merged_geology_GeologyBudgetError):
            geology.properties_preflight(geology.MAX_GRID_CELLS + 1, point_mode=False)
        with self.assertRaises(_merged_geology_GeologyBudgetError):
            geology.properties_preflight(geology.MAX_POINTS + 1, point_mode=True)

    def test_point_limit_is_enforced(self):
        with self.assertRaises(_merged_geology_GeologyBudgetError):
            geology.properties_at(np.zeros(geology.MAX_POINTS + 1),
                                  np.zeros(geology.MAX_POINTS + 1))

    def test_preflight_reports_the_declared_budget(self):
        budget = geology.properties_preflight(100, point_mode=True)
        self.assertEqual(budget["max_points"], geology.MAX_POINTS)
        self.assertEqual(budget["max_grid_cells"], geology.MAX_GRID_CELLS)
        self.assertEqual(budget["max_output_bytes"], geology.MAX_OUTPUT_BYTES)
        self.assertLessEqual(budget["estimated_logical_payload_bytes"],
                             geology.MAX_OUTPUT_BYTES)
        with self.assertRaises(_merged_geology_GeologyBudgetError):
            geology.properties_preflight(0)

    def test_tampered_identity_is_refused(self):
        bundle = _column()
        bundle["identity_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            geology.validate_geology_properties(bundle)

    def test_tampered_array_is_refused(self):
        bundle = _column()
        bundle["arrays"]["bed_hardness"] = np.clip(
            bundle["arrays"]["bed_hardness"] + 0.01, 0.0, 1.0)
        with self.assertRaises(ValueError):
            geology.validate_geology_properties(bundle)

    def test_rock_table_mismatch_is_refused(self):
        bundle = _column()
        bundle["metadata"]["rock_order"] = list(reversed(lithology.ROCK_ORDER))
        with self.assertRaises(ValueError):
            geology.validate_geology_properties(bundle)


if __name__ == "__main__":
    unittest.main()
