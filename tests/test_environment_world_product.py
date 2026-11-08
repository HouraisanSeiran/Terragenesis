"""同坐标 30 m 环境联合产品的行为测试。

只断言外部可观察的性质：装配后的字段与状态、四层身份分离、点序无关、只读查询、
拒绝缺源与非法输入、保存/读回一致。不断言内部辅助函数。
"""

import json
import os
import tempfile
import unittest

import numpy as np

from terrain_pipeline.environment_product import FIELD_SPECS, WORLD_SCHEMA as SCHEMA, WorldProduct, world_assemble as assemble, world_describe as describe, world_load as load, world_query as query, world_save as save


SEED = 20261020
SPACING = 30.0


def _grid(size=3, origin=(1266450.0, 1290990.0)):
    x = origin[0] + SPACING * np.arange(size, dtype=np.float64)
    z = origin[1] + SPACING * np.arange(size, dtype=np.float64)
    gx, gz = np.meshgrid(x, z)
    return gx.reshape(-1), gz.reshape(-1)


def _fields(cells, *, with_optional=True):
    fields = {
        "elevation_m": np.linspace(900.0, 950.0, cells),
        "annual_temperature_c": np.linspace(1.0, 6.0, cells),
        "water_state_mm": np.stack([
            np.full(cells, 20.0), np.full(cells, 3.0), np.full(cells, 7.0)]),
    }
    statuses = {name: "computed" for name in fields}
    if with_optional:
        fields["porosity"] = np.full(cells, 0.35)
        fields["monthly_temperature_c"] = np.tile(
            np.linspace(-6.0, 16.0, 12)[:, None], (1, cells))
        fields["water_state_total_mm"] = np.full(cells, 30.0)
        fields["land_cover_index"] = np.arange(cells) % 6
        statuses["porosity"] = "declared"
        statuses["monthly_temperature_c"] = "computed"
        statuses["water_state_total_mm"] = "computed"
        statuses["land_cover_index"] = "declared"
    return fields, statuses


def _assemble(**overrides):
    x, z = _grid()
    cells = int(x.size)
    fields, statuses = _fields(cells)
    arguments = dict(
        city_name="test-3x3", world_seed=SEED, spacing_m=SPACING,
        x_m=x, z_m=z, fields=fields, statuses=statuses,
        source_identities={"g3": "a" * 64, "g5": "b" * 64},
        model_parameters={"land_cover": 0.5}, time_record=None)
    arguments.update(overrides)
    return assemble(**arguments)


class DeclarationTests(unittest.TestCase):
    def test_describe_states_the_separations_and_the_never_list(self):
        declared = describe()
        self.assertEqual(declared["schema"], SCHEMA)
        self.assertEqual(declared["identities"],
                         ["world_identity", "source_identity", "model_identity",
                          "time_identity"])
        self.assertIn("query", declared["separations"])
        never = " | ".join(declared["never"])
        self.assertIn("缺来源的字段当零", never)
        self.assertIn("吸附或移动调用方坐标", never)

    def test_field_specs_declare_units_and_shapes(self):
        for name, (unit, kind) in FIELD_SPECS.items():
            self.assertTrue(unit)
            self.assertIn(kind, ("per_cell", "monthly", "state3"))


class AssembleTests(unittest.TestCase):
    def test_product_carries_every_field_and_its_status(self):
        product = _assemble()
        self.assertIsInstance(product, WorldProduct)
        self.assertEqual(product.cells, 9)
        fields, _statuses = _fields(9)
        self.assertEqual(sorted(product.arrays), sorted(fields))
        self.assertEqual(product.status["porosity"], "declared")
        self.assertEqual(product.status["elevation_m"], "computed")
        self.assertEqual(product.units["elevation_m"], "m")
        self.assertEqual(product.units["water_state_mm"], "mm")

    def test_missing_required_colocated_field_is_refused(self):
        x, z = _grid()
        cells = int(x.size)
        fields, statuses = _fields(cells)
        del fields["water_state_mm"]
        del statuses["water_state_mm"]
        with self.assertRaises(ValueError) as caught:
            assemble(city_name="t", world_seed=SEED, spacing_m=SPACING, x_m=x, z_m=z,
                     fields=fields, statuses=statuses, source_identities={},
                     model_parameters={})
        self.assertIn("water_state_mm", str(caught.exception))

    def test_status_must_be_declared_for_every_field(self):
        x, z = _grid()
        cells = int(x.size)
        fields, statuses = _fields(cells)
        statuses.pop("porosity")
        with self.assertRaises(ValueError):
            assemble(city_name="t", world_seed=SEED, spacing_m=SPACING, x_m=x, z_m=z,
                     fields=fields, statuses=statuses, source_identities={},
                     model_parameters={})

    def test_unknown_field_is_refused(self):
        x, z = _grid()
        cells = int(x.size)
        fields, statuses = _fields(cells)
        fields["made_up"] = np.zeros(cells)
        statuses["made_up"] = "computed"
        with self.assertRaises(ValueError):
            assemble(city_name="t", world_seed=SEED, spacing_m=SPACING, x_m=x, z_m=z,
                     fields=fields, statuses=statuses, source_identities={},
                     model_parameters={})

    def test_length_mismatch_is_refused(self):
        x, z = _grid()
        cells = int(x.size)
        fields, statuses = _fields(cells)
        fields["porosity"] = np.zeros(cells - 1)
        with self.assertRaises(ValueError):
            assemble(city_name="t", world_seed=SEED, spacing_m=SPACING, x_m=x, z_m=z,
                     fields=fields, statuses=statuses, source_identities={},
                     model_parameters={})

    def test_non_finite_or_non_positive_inputs_are_refused(self):
        x, z = _grid()
        cells = int(x.size)
        fields, statuses = _fields(cells)
        for spacing in (0.0, -30.0, float("nan")):
            with self.subTest(spacing=spacing):
                with self.assertRaises(ValueError):
                    assemble(city_name="t", world_seed=SEED, spacing_m=spacing,
                             x_m=x, z_m=z, fields=fields, statuses=statuses,
                             source_identities={}, model_parameters={})
        for seed in (-1, 1.5):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    assemble(city_name="t", world_seed=seed, spacing_m=SPACING,
                             x_m=x, z_m=z, fields=fields, statuses=statuses,
                             source_identities={}, model_parameters={})


class IdentityTests(unittest.TestCase):
    def test_four_identities_are_separate_digests(self):
        product = _assemble()
        values = {product.world_identity, product.source_identity,
                  product.model_identity, product.time_identity}
        self.assertEqual(len(values), 4)
        for value in values:
            self.assertEqual(len(value), 64)

    def test_world_identity_moves_with_seed_and_points(self):
        base = _assemble()
        other_seed = _assemble(world_seed=SEED + 1)
        self.assertNotEqual(base.world_identity, other_seed.world_identity)
        x, z = _grid()
        moved = _assemble(x_m=x + 30.0)
        self.assertNotEqual(base.world_identity, moved.world_identity)

    def test_world_identity_ignores_point_order(self):
        x, z = _grid()
        cells = int(x.size)
        order = np.arange(cells)[::-1]
        fields, statuses = _fields(cells)
        permuted = {name: np.asarray(value)[:, order] if np.asarray(value).ndim == 2
                    else np.asarray(value)[order] for name, value in fields.items()}
        base = _assemble()
        other = assemble(city_name="test-3x3", world_seed=SEED, spacing_m=SPACING,
                         x_m=x[order], z_m=z[order], fields=permuted,
                         statuses=statuses,
                         source_identities={"g3": "a" * 64, "g5": "b" * 64},
                         model_parameters={"land_cover": 0.5}, time_record=None)
        self.assertEqual(base.world_identity, other.world_identity)

    def test_source_and_model_identities_move_independently(self):
        base = _assemble()
        other_source = _assemble(source_identities={"g3": "c" * 64, "g5": "b" * 64})
        self.assertNotEqual(base.source_identity, other_source.source_identity)
        self.assertEqual(base.world_identity, other_source.world_identity)
        self.assertEqual(base.model_identity, other_source.model_identity)
        other_model = _assemble(model_parameters={"land_cover": 0.9})
        self.assertNotEqual(base.model_identity, other_model.model_identity)
        self.assertEqual(base.world_identity, other_model.world_identity)


class QueryTests(unittest.TestCase):
    def test_exact_query_returns_the_cell_values(self):
        product = _assemble()
        x, z = _grid()
        result = query(product, [x[4]], [z[4]])
        self.assertEqual(int(result["cell_index"][0]), 4)
        self.assertEqual(float(result["offset_m"][0]), 0.0)
        self.assertFalse(result["snapped"])
        self.assertAlmostEqual(float(result["elevation_m"][0]),
                               float(product.arrays["elevation_m"][4]), places=12)
        self.assertEqual(result["water_state_mm"].shape, (3, 1))

    def test_off_grid_query_is_refused_without_accept_offset(self):
        product = _assemble()
        x, z = _grid()
        with self.assertRaises(ValueError) as caught:
            query(product, [x[0] + 12.0], [z[0]])
        self.assertIn("不在产品格点上", str(caught.exception))

    def test_accept_offset_admits_a_measured_offset(self):
        product = _assemble()
        x, z = _grid()
        result = query(product, [x[0] + 12.0], [z[0]], accept_offset_m=15.0)
        self.assertEqual(int(result["cell_index"][0]), 0)
        self.assertAlmostEqual(float(result["offset_m"][0]), 12.0, places=9)
        self.assertFalse(result["snapped"])

    def test_accept_offset_below_measured_offset_is_refused(self):
        product = _assemble()
        x, z = _grid()
        with self.assertRaises(ValueError) as caught:
            query(product, [x[0] + 12.0], [z[0]], accept_offset_m=5.0)
        self.assertIn("超过", str(caught.exception))

    def test_query_is_read_only(self):
        product = _assemble()
        before = {name: np.asarray(value).copy() for name, value in product.arrays.items()}
        x, z = _grid()
        query(product, x, z)
        for name, value in before.items():
            np.testing.assert_array_equal(product.arrays[name], value)

    def test_query_reports_status_for_every_field(self):
        product = _assemble()
        x, z = _grid()
        result = query(product, [x[0]], [z[0]])
        self.assertEqual(set(result["status"]), set(product.arrays))
        self.assertEqual(result["status"]["porosity"], "declared")


class SaveLoadTests(unittest.TestCase):
    def test_round_trip_preserves_fields_and_identities(self):
        product = _assemble()
        with tempfile.TemporaryDirectory() as folder:
            arrays = os.path.join(folder, "a.npz")
            record = os.path.join(folder, "a.json")
            save(product, arrays, record)
            cold = load(arrays, record)
        self.assertEqual(cold.world_identity, product.world_identity)
        self.assertEqual(cold.source_identity, product.source_identity)
        self.assertEqual(cold.model_identity, product.model_identity)
        self.assertEqual(cold.status, product.status)
        self.assertEqual(sorted(cold.arrays), sorted(product.arrays))
        np.testing.assert_array_equal(cold.record["x_m"], product.record["x_m"])

    def test_save_refuses_to_overwrite(self):
        product = _assemble()
        with tempfile.TemporaryDirectory() as folder:
            arrays = os.path.join(folder, "a.npz")
            record = os.path.join(folder, "a.json")
            save(product, arrays, record)
            with self.assertRaises(FileExistsError):
                save(product, arrays, record)

    def test_load_refuses_a_different_world_identity(self):
        product = _assemble()
        with tempfile.TemporaryDirectory() as folder:
            arrays = os.path.join(folder, "a.npz")
            record = os.path.join(folder, "a.json")
            save(product, arrays, record)
            with self.assertRaises(ValueError) as caught:
                load(arrays, record, expected_world_identity="0" * 64)
        self.assertIn("world_identity", str(caught.exception))

    def test_record_json_is_readable_and_states_the_coordinate_rule(self):
        product = _assemble()
        with tempfile.TemporaryDirectory() as folder:
            arrays = os.path.join(folder, "a.npz")
            record = os.path.join(folder, "a.json")
            save(product, arrays, record)
            with open(record, "r", encoding="utf-8") as stream:
                meta = json.load(stream)
        self.assertEqual(meta["schema"], SCHEMA)
        self.assertIn("吸附", meta["record"]["coordinate_semantics"])


class PendingTests(unittest.TestCase):
    def test_pending_field_is_reported_not_read_as_zero(self):
        x, z = _grid()
        cells = int(x.size)
        fields, statuses = _fields(cells)
        # A pending field carries NaN so a reader cannot mistake it for a measurement.
        fields["soil_thickness_bulk_m"] = np.full(cells, np.nan)
        statuses["soil_thickness_bulk_m"] = "pending"
        product = assemble(city_name="t", world_seed=SEED, spacing_m=SPACING,
                           x_m=x, z_m=z, fields=fields, statuses=statuses,
                           source_identities={}, model_parameters={})
        self.assertEqual(product.status["soil_thickness_bulk_m"], "pending")
        self.assertTrue(np.all(np.isnan(product.arrays["soil_thickness_bulk_m"])))
        self.assertIn("soil_thickness_bulk_m", product.count_status("pending"))
        result = query(product, [x[0]], [z[0]])
        self.assertTrue(np.isnan(result["soil_thickness_bulk_m"][0]))
        self.assertEqual(result["status"]["soil_thickness_bulk_m"], "pending")


if __name__ == "__main__":
    unittest.main()
