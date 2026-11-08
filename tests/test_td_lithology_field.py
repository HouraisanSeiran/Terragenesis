"""岩性属性表与简化噪波分布的单元测试（unittest，无 pytest）。

范围：只测 td_lithology_field 的公开行为——属性表量级、同坐标稳定性、
乱序/分块一致、分布占比覆盖、非法输入拒绝、以及产物重算与篡改拒绝。
不测构造背景（本版没有），也不测其与旧求解器算法的交互。
"""

import unittest

import numpy as np

from terrain_pipeline import geology as lithology


class LithologyAttributeTableTests(unittest.TestCase):
    def test_table_size_and_class_coverage(self):
        self.assertEqual(len(lithology.ROCK_TABLE), 18)
        counts = {class_id: 0 for class_id in lithology.CLASS_IDS}
        for record in lithology.ROCK_TABLE:
            counts[record["class"]] += 1
        for class_id, count in counts.items():
            self.assertGreaterEqual(count, 4, class_id)
            self.assertLessEqual(count, 6, class_id)

    def test_record_fields_and_ranges(self):
        required = {"id", "name_zh", "name_en", "class", "mohs_hardness",
                    "erodibility_index", "bed_hardness", "bank_hardness",
                    "layering", "fracture_density", "solubility", "porosity",
                    "abundance_weight", "units", "value_status"}
        for record in lithology.ROCK_TABLE:
            self.assertLessEqual(required, set(record))
            self.assertEqual(record["value_status"], lithology.PROVENANCE)
            for name in ("erodibility_index", "bed_hardness", "bank_hardness",
                         "layering", "fracture_density", "solubility", "porosity"):
                self.assertGreaterEqual(record[name], 0.0, (record["id"], name))
                self.assertLessEqual(record[name], 1.0, (record["id"], name))
            self.assertGreaterEqual(record["mohs_hardness"], 1.0)
            self.assertLessEqual(record["mohs_hardness"], 7.0)
            self.assertLessEqual(record["porosity"], 1.0)
            self.assertGreater(record["abundance_weight"], 0.0)

    def test_reference_mohs_magnitudes(self):
        expected = {"granite": 6.5, "basalt": 6.0, "limestone": 3.0, "shale": 2.5,
                    "quartzite": 7.0, "marble": 3.5, "slate": 3.0, "dolomite": 3.5,
                    "tuff": 3.5, "sandstone": 4.5, "gneiss": 6.0, "gabbro": 6.5}
        for rock_id, mohs in expected.items():
            self.assertAlmostEqual(lithology.ROCK_BY_ID[rock_id]["mohs_hardness"], mohs, places=9)
        # 花岗岩 6-7、石灰岩 3 的量级（莫氏硬度实数量级而非归一化值）。
        self.assertTrue(6.0 <= lithology.ROCK_BY_ID["granite"]["mohs_hardness"] <= 7.0)
        self.assertTrue(2.5 <= lithology.ROCK_BY_ID["limestone"]["mohs_hardness"] <= 3.5)
        self.assertGreater(lithology.ROCK_BY_ID["quartzite"]["mohs_hardness"],
                           lithology.ROCK_BY_ID["shale"]["mohs_hardness"])

    def test_solubility_order(self):
        table = lithology.ROCK_BY_ID
        self.assertGreater(table["limestone"]["solubility"], 0.5)
        self.assertGreater(table["dolomite"]["solubility"], 0.5)
        self.assertGreater(table["marble"]["solubility"], 0.5)
        self.assertLess(table["granite"]["solubility"], 0.1)
        self.assertLess(table["quartzite"]["solubility"], 0.1)

    def test_hard_rock_resists_and_soft_rock_yields(self):
        order = ["quartzite", "granite", "basalt", "sandstone", "limestone", "shale"]
        values = [lithology.ROCK_BY_ID[rock]["bed_hardness"] for rock in order]
        for first, second in zip(values, values[1:]):
            self.assertGreater(first, second)
        self.assertLess(values[0], 1.0)
        self.assertGreater(values[-1], 0.0)
        # 辉长岩与花岗岩均块状、莫氏均 6.5；本公式下花岗岩孔隙率更低而略硬，
        # 故不假设两者严格次序，只断言两者都硬于砂岩。
        for rock in ("granite", "gabbro"):
            self.assertGreater(lithology.ROCK_BY_ID[rock]["bed_hardness"],
                               lithology.ROCK_BY_ID["sandstone"]["bed_hardness"])

    def test_layered_bank_weaker_than_bed(self):
        for record in lithology.ROCK_TABLE:
            self.assertLessEqual(record["bank_hardness"], record["bed_hardness"])
        # 层状碳酸盐岩岸比床更易崩，同层状碎屑岩也有正面差值。
        self.assertLess(lithology.ROCK_BY_ID["limestone"]["bank_hardness"],
                        lithology.ROCK_BY_ID["limestone"]["bed_hardness"] - 0.15)
        self.assertLess(lithology.ROCK_BY_ID["shale"]["bank_hardness"],
                        lithology.ROCK_BY_ID["shale"]["bed_hardness"] - 0.15)
        # 块状岩石两侧差别很小。
        self.assertLess(lithology.ROCK_BY_ID["granite"]["bed_hardness"]
                        - lithology.ROCK_BY_ID["granite"]["bank_hardness"], 0.05)

    def test_table_identity_is_stable_and_table_is_readonly_copy(self):
        first = lithology.rock_table_identity()
        self.assertEqual(len(first), 64)
        self.assertEqual(first, lithology.rock_table_identity())
        table = lithology.rock_table()
        table[0]["mohs_hardness"] = 1.0
        self.assertNotEqual(lithology.ROCK_TABLE[0]["mohs_hardness"], 1.0)
        self.assertEqual(first, lithology.rock_table_identity())

    def test_unknown_rock_rejected(self):
        with self.assertRaises(KeyError):
            lithology.rock_record("unobtainium")
        with self.assertRaises(ValueError):
            lithology.hardness_lookup("unobtainium")


class LithologySeedTests(unittest.TestCase):
    def test_subseeds_are_distinct_and_fixed(self):
        subseeds = lithology.lithology_subseeds(lithology.DEFAULT_WORLD_SEED)
        self.assertEqual(list(subseeds), list(lithology.SEED_PURPOSES))
        self.assertEqual(len(set(subseeds.values())), len(subseeds))
        for value in subseeds.values():
            self.assertTrue(0 <= value < 2 ** 64)
        # 固定种子的实际值（改动派生规则必须在这里显式更新）。
        self.assertEqual(subseeds["class_primary"], 2857402188508663275)
        self.assertEqual(subseeds["class_secondary"], 3240227529605732832)
        self.assertEqual(subseeds["rock_medium"], 6024362621315249804)
        self.assertEqual(subseeds["patch_high"], 1251164017184175119)

    def test_seed_changes_distribution_and_purpose_separates_sequence(self):
        base = lithology.sample_lithology((32, 32), origin_m_xz=(0., 0.), spacing_m=1000.)
        other = lithology.sample_lithology((32, 32), origin_m_xz=(0., 0.), spacing_m=1000.,
                                          world_seed=20261020 + 1)
        self.assertNotEqual(base["identity_sha256"], other["identity_sha256"])
        self.assertNotEqual(lithology.derive_subseed(20261020, "class_primary"),
                           lithology.derive_subseed(20261020, "rock_medium"))

    def test_invalid_seed_and_purpose_rejected(self):
        for bad in (True, -1, 2 ** 64, 1.5, "20261020"):
            with self.assertRaises(ValueError):
                lithology.lithology_subseeds(bad)
        with self.assertRaises(ValueError):
            lithology.derive_subseed(20261020, "not-a-purpose")


class LithologySamplingStabilityTests(unittest.TestCase):
    def test_repeated_sampling_is_bitwise_identical(self):
        first = lithology.sample_lithology((24, 40), origin_m_xz=(-2000., 5000.), spacing_m=250.)
        second = lithology.sample_lithology((24, 40), origin_m_xz=(-2000., 5000.), spacing_m=250.)
        self.assertEqual(first["identity_sha256"], second["identity_sha256"])
        for name in ("class_index", "rock_index", "bed_hardness", "bank_hardness"):
            self.assertTrue(np.array_equal(first["arrays"][name], second["arrays"][name], equal_nan=False))
            self.assertEqual(first["arrays"][name].tobytes(), second["arrays"][name].tobytes())

    def test_offset_windows_agree_within_overlap(self):
        spacing = 500.0
        big = lithology.sample_lithology((40, 40), origin_m_xz=(0., 0.), spacing_m=spacing)
        small = lithology.sample_lithology((10, 12), origin_m_xz=(12 * spacing, 7 * spacing),
                                          spacing_m=spacing)
        for name in ("class_index", "rock_index", "bed_hardness", "bank_hardness"):
            np.testing.assert_array_equal(big["arrays"][name][7:17, 12:24], small["arrays"][name])

    def test_shuffled_points_match_grid_samples(self):
        spacing = 1000.0
        bundle = lithology.sample_lithology((20, 20), origin_m_xz=(0., 0.), spacing_m=spacing)
        rows = np.repeat(np.arange(20), 20)
        columns = np.tile(np.arange(20), 20)
        order = np.random.default_rng(20261020).permutation(rows.size)
        x = (columns + 0.5) * spacing
        z = (rows + 0.5) * spacing
        points = lithology.sample_lithology_points(x[order], z[order])
        np.testing.assert_array_equal(points["rock_index"],
                                     bundle["arrays"]["rock_index"].ravel()[order].astype(np.int64))
        # 逐点单查询也必须逐位相同。
        single = lithology.sample_lithology_points(x[[0, 137, 399]], z[[0, 137, 399]])
        np.testing.assert_array_equal(single["rock_index"],
                                     bundle["arrays"]["rock_index"].ravel()[[0, 137, 399]])

    def test_sampling_does_not_depend_on_tile_load_order(self):
        tiles = [(0., 0.), (2000., 0.), (0., 2000.), (2000., 2000.)]
        forward = [lithology.sample_lithology((8, 8), origin_m_xz=origin, spacing_m=500.)
                   for origin in tiles]
        backward = [lithology.sample_lithology((8, 8), origin_m_xz=origin, spacing_m=500.)
                    for origin in reversed(tiles)]
        for first, second in zip(forward, reversed(backward)):
            self.assertEqual(first["identity_sha256"], second["identity_sha256"])

    def test_scalar_point_query_matches_grid(self):
        spacing = 1000.0
        bundle = lithology.sample_lithology((8, 8), origin_m_xz=(0., 0.), spacing_m=spacing)
        point = lithology.sample_lithology_points(3.5 * spacing, 5.5 * spacing)
        self.assertEqual(point["rock_index"].shape, ())
        self.assertEqual(int(point["rock_index"]), int(bundle["arrays"]["rock_index"][5, 3]))
        self.assertEqual(float(point["bed_hardness"]), float(bundle["arrays"]["bed_hardness"][5, 3]))

    def test_non_finite_and_misaligned_inputs_rejected(self):
        with self.assertRaises(ValueError):
            lithology.sample_lithology((4, 4), origin_m_xz=(0.5, 0.), spacing_m=1000.)
        with self.assertRaises(ValueError):
            lithology.sample_lithology((4, 4), origin_m_xz=(0., 0.), spacing_m=0.)
        with self.assertRaises(ValueError):
            lithology.sample_lithology((0, 4), origin_m_xz=(0., 0.), spacing_m=1.)
        with self.assertRaises(ValueError):
            lithology.sample_lithology_points(np.array([np.nan]), np.array([0.]))
        with self.assertRaises(ValueError):
            lithology.sample_lithology((4, 4), origin_m_xz=(0., 0.), spacing_m=1.,
                                       parameters={"unknown_knob": 1.0})


class LithologyDistributionTests(unittest.TestCase):
    def fixture(self):
        return lithology.sample_lithology((64, 64), origin_m_xz=(0., 0.), spacing_m=2000.)

    def wide_area_counts(self):
        """Aggregate several far-apart tiles.

        One 256 km window covers about one lattice cell of the 220 km class noise,
        so its class proportions are a *local* realisation and are not expected to
        match the declared weights. Large-area proportions have to be aggregated
        over many class-scale cells, which is what this does.
        """
        origins = [(-4000e3, -4000e3), (-1000e3, 3000e3), (2500e3, -1500e3),
                   (5000e3, 5000e3)]
        class_counts = np.zeros(len(lithology.CLASS_IDS), np.int64)
        rock_counts = np.zeros(len(lithology.ROCK_ORDER), np.int64)
        for origin in origins:
            bundle = lithology.sample_lithology((320, 320), origin_m_xz=origin, spacing_m=4000.)
            class_counts += np.bincount(bundle["arrays"]["class_index"].ravel(),
                                        minlength=len(lithology.CLASS_IDS))
            rock_counts += np.bincount(bundle["arrays"]["rock_index"].ravel(),
                                       minlength=len(lithology.ROCK_ORDER))
        return class_counts, rock_counts, int(class_counts.sum())

    def test_all_three_classes_present_in_an_aggregated_region(self):
        # 单个 128 km 窗口只覆盖 220 km 岩类噪波的约一个格子，可能只有两类；
        # 这里改用横跨多个岩类尺度的固定网格区域断言三类都出现。
        class_counts, rock_counts, total = self.wide_area_counts()
        self.assertEqual(int((class_counts > 0).sum()), 3)
        self.assertEqual(int((rock_counts > 0).sum()), len(lithology.ROCK_ORDER))
        for position, class_id in enumerate(lithology.CLASS_IDS):
            self.assertGreater(class_counts[position] / total, 0.05, class_id)

    def test_local_window_keeps_only_rocks_of_declared_class(self):
        report = lithology.compose_report(self.fixture())
        self.assertGreaterEqual(report["distinct_classes"], 1)
        self.assertGreater(report["distinct_rocks"], 1)
        total = sum(entry["count"] for entry in report["rocks"].values())
        self.assertEqual(total, report["total_cells"])
        seen = {entry["class"] for entry in report["rocks"].values() if entry["count"] > 0}
        self.assertEqual(seen, {class_id for class_id, entry in report["classes"].items()
                                if entry["count"] > 0})

    def test_wide_area_proportions_track_declared_weights(self):
        class_counts, rock_counts, total = self.wide_area_counts()
        self.assertGreater(total, 300000)
        declared = lithology.LITHOLOGY_DEFAULT_PARAMETERS["class_weights"]
        for position, class_id in enumerate(lithology.CLASS_IDS):
            self.assertAlmostEqual(class_counts[position] / total, declared[class_id], delta=0.06)
            self.assertGreater(class_counts[position], 0, class_id)
        self.assertEqual(int((rock_counts > 0).sum()), len(lithology.ROCK_ORDER))
        for class_id in lithology.CLASS_IDS:
            members = lithology.ROCK_ORDER_BY_CLASS[class_id]
            subtotal = sum(int(rock_counts[lithology.ROCK_POSITION[rock]]) for rock in members)
            self.assertGreater(subtotal, 0, class_id)
            for rock in members:
                observed = rock_counts[lithology.ROCK_POSITION[rock]] / subtotal
                self.assertAlmostEqual(
                    observed, lithology.LITHOLOGY_DEFAULT_PARAMETERS["rock_weights"][class_id][rock],
                    delta=0.08, msg=rock)

    def test_local_window_contains_rock_of_its_class_and_table_values(self):
        bundle = self.fixture()
        arrays = bundle["arrays"]
        for position, rock_id in enumerate(lithology.ROCK_ORDER):
            selected = arrays["rock_index"] == position
            if not selected.any():
                continue
            record = lithology.ROCK_BY_ID[rock_id]
            self.assertEqual(int(arrays["class_index"][selected][0]),
                             lithology.CLASS_IDS.index(record["class"]))
            self.assertTrue(np.all(arrays["bed_hardness"][selected] == record["bed_hardness"]))
            self.assertTrue(np.all(arrays["bank_hardness"][selected] == record["bank_hardness"]))
            self.assertTrue(np.all(arrays["erodibility_index"][selected] == record["erodibility_index"]))

    def test_long_frequency_structure_present(self):
        # 岩类必须先由低频决定：同一行内不应逐格跳变。
        bundle = self.fixture()
        row = bundle["arrays"]["class_index"][0]
        changes = int((np.diff(row) != 0).sum())
        self.assertLess(changes, row.size // 4)


class LithologyBundleTests(unittest.TestCase):
    def fixture(self):
        return lithology.sample_lithology((16, 16), origin_m_xz=(1000., -3000.), spacing_m=500.)

    def test_metadata_declares_simplified_unmeasured_status(self):
        bundle = self.fixture()
        metadata = bundle["metadata"]
        self.assertTrue(metadata["synthetic_lithology"])
        self.assertFalse(metadata["measured_lithology"])
        self.assertFalse(metadata["tectonic_context"])
        self.assertEqual(metadata["distribution_model"], "simplified_two_level_value_noise")
        self.assertEqual(metadata["value_status"], lithology.PROVENANCE)
        self.assertEqual(metadata["world_seed"], lithology.DEFAULT_WORLD_SEED)
        self.assertEqual(metadata["subseeds"], lithology.lithology_subseeds())
        self.assertIn(lithology.SEED_DERIVATION, metadata["seed_derivation"])
        self.assertTrue(metadata["coordinate_absolute"])

    def test_validation_rejects_tampering(self):
        bundle = self.fixture()
        litology_ok = lithology.validate_lithology_field(bundle)
        self.assertTrue(litology_ok)

        broken = self.fixture()
        broken["arrays"]["bed_hardness"] = broken["arrays"]["bed_hardness"] + 0.01
        with self.assertRaises(ValueError):
            lithology.validate_lithology_field(broken)

        rehashed = self.fixture()
        arrays = dict(rehashed["arrays"])
        arrays["rock_index"] = np.zeros_like(arrays["rock_index"])
        rehashed["arrays"] = arrays
        rehashed["identity_sha256"] = lithology.identity(arrays, rehashed["metadata"])
        with self.assertRaises(ValueError):
            lithology.validate_lithology_field(rehashed)

        mislabelled = self.fixture()
        mislabelled["metadata"]["measured_lithology"] = True
        with self.assertRaises(ValueError):
            lithology.validate_lithology_field(mislabelled)

        tectonic = self.fixture()
        tectonic["metadata"]["tectonic_context"] = True
        with self.assertRaises(ValueError):
            lithology.validate_lithology_field(tectonic)

    def test_discharge_geometry_inputs_feed_existing_rule(self):
        bundle = self.fixture()
        bed, bank = lithology.discharge_geometry_inputs(bundle)
        self.assertIsInstance(bed, np.ndarray)
        self.assertEqual(bed.dtype, np.float64)
        self.assertEqual(bed.shape, bundle["arrays"]["bed_hardness"].shape)
        self.assertTrue(np.array_equal(bed, bundle["arrays"]["bed_hardness"]))
        self.assertTrue(np.array_equal(bank, bundle["arrays"]["bank_hardness"]))
        self.assertTrue(np.all((bed >= 0.) & (bed <= 1.)))
        self.assertTrue(np.all((bank >= 0.) & (bank <= 1.)))
        # 返回副本：呼叫方修改不得污染已校验的 bundle。
        bed[:] = 0.5
        self.assertFalse(np.all(bundle["arrays"]["bed_hardness"] == 0.5))

    def test_protected_mask_is_preserved(self):
        mask = np.zeros((16, 16), bool)
        mask[3, 4] = True
        bundle = lithology.sample_lithology((16, 16), origin_m_xz=(0., 0.), spacing_m=500.,
                                            protected_mask=mask)
        np.testing.assert_array_equal(bundle["arrays"]["protected_mask"], mask)
        with self.assertRaises(ValueError):
            lithology.sample_lithology((16, 16), origin_m_xz=(0., 0.), spacing_m=500.,
                                       protected_mask=np.zeros((3, 3), bool))


if __name__ == "__main__":
    unittest.main()
