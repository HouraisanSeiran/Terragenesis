from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.geology import bedrock_porosity, material_mass_inputs, prepare_material_source, validate_material_source, query_material_source
from terrain_pipeline.environment_processes import mass_initial_state as initial_state, mass_step as step
from terrain_pipeline.geology import properties_at
from terrain_pipeline.geology import sample_lithology_points


def context(shape=(33, 33)):
    rows, cols = np.indices(shape)
    return {"height_m": np.full(shape, 1050.), "origin_native_xz": [43700, 42100],
            "spacing_m": 30., "world_seed": 20261020,
            "node_x_m": (43700 + cols) * 30. + 4., "node_z_m": (42100 + rows) * 30. - 3.,
            "valid_mask": np.ones(shape, bool), "ocean_mask": np.zeros(shape, bool),
            "river_mask": np.zeros(shape, bool), "protected_mask": np.zeros(shape, bool),
            "receiver": np.full(shape, -1, np.int64)}


class MaterialSourceTests(unittest.TestCase):
    def test_same_seed_native_anchor_and_existing_g2_identity(self):
        ctx = context()
        source = prepare_material_source(ctx)
        rows, cols = np.indices((33, 33))
        x, z = (43700 + cols) * 30., (42100 + rows) * 30.
        expected = properties_at(x, z, world_seed=20261020)
        self.assertEqual(source["identity_sha256"], expected["identity_sha256"])
        previous = sample_lithology_points(x, z, world_seed=20261020)
        np.testing.assert_array_equal(source["arrays"]["bed_hardness"], previous["bed_hardness"])
        np.testing.assert_array_equal(source["arrays"]["x_m"], x)
        self.assertFalse(np.array_equal(source["arrays"]["x_m"], ctx["node_x_m"]))
        self.assertTrue(source["metadata"]["synthetic_lithology"])
        self.assertFalse(source["metadata"]["measured_lithology"])

    def test_actual_material_drives_existing_mass_solubility_without_changing_regolith(self):
        ctx = context((3, 3))
        source = prepare_material_source(ctx)
        inputs = material_mass_inputs(source, ctx)
        state = initial_state(ctx, **inputs)
        np.testing.assert_array_equal(state["solubility"], .03)
        np.testing.assert_array_equal(state["bed_hardness"], inputs["bed_hardness"])
        np.testing.assert_array_equal(bedrock_porosity(source), .06)
        np.testing.assert_array_equal(state["regolith_porosity"], .35)
        self.assertNotIn("regolith_porosity", inputs)
        for values in (*inputs.values(), bedrock_porosity(source)):
            with self.assertRaises(ValueError):
                values.setflags(write=True)

    def test_cold_validation_does_not_resample_and_unknowns_remain_absent(self):
        source = prepare_material_source(context())
        with patch('terrain_pipeline.geology.properties_at', side_effect=AssertionError("sample")):
            with patch('terrain_pipeline.geology.sample_lithology_points', side_effect=AssertionError("sample")):
                self.assertTrue(validate_material_source(source, context()))
                material_mass_inputs(source)
        for name in ("intrinsic_permeability_m2", "bedrock_thickness_m", "cover_thickness_m"):
            self.assertNotIn(name, source["arrays"])
        self.assertEqual(source["metadata"]["fields_status"]["intrinsic_permeability_m2"], "pending")
        self.assertEqual(source["metadata"]["fields_status"]["bedrock_thickness_m"], "unknown_no_source")

    def test_context_inputs_are_not_mutated(self):
        ctx = context()
        before = deepcopy(ctx)
        prepare_material_source(ctx)
        for name, value in ctx.items():
            if isinstance(value, np.ndarray):
                np.testing.assert_array_equal(value, before[name])
            else:
                self.assertEqual(value, before[name])

    def test_real_g9_consumer_changes_with_sampled_solubility_at_identical_forcing(self):
        ctx = context((3, 3))
        source = prepare_material_source(ctx)
        inputs = material_mass_inputs(source, ctx)
        sampled = initial_state(ctx, **inputs)
        declared = initial_state(ctx, bed_hardness=inputs["bed_hardness"], solubility=.2)
        forcing = {"temperature_c": 20., "moisture": .5}
        actual = step(sampled, forcing, ctx, 3600.)["state"]
        baseline = step(declared, forcing, ctx, 3600.)["state"]
        self.assertTrue(np.all(actual["bedrock_solid_m3"] > baseline["bedrock_solid_m3"]))
        self.assertTrue(np.all(actual["regolith_solid_m3"] < baseline["regolith_solid_m3"]))
        self.assertTrue(np.all(actual["dissolved_solid_m3"] < baseline["dissolved_solid_m3"]))
        np.testing.assert_array_equal(actual["regolith_porosity"], baseline["regolith_porosity"])

    def test_query_preserves_actual_values_units_and_pending_properties(self):
        source = prepare_material_source(context())
        result = query_material_source(source, 2, 3)
        self.assertEqual(result["solubility"], .03)
        self.assertEqual(result["bedrock_porosity"], .06)
        self.assertEqual(result["x_m"], 43703 * 30.)
        self.assertEqual(result["z_m"], 42102 * 30.)
        self.assertEqual(result["status"]["intrinsic_permeability_m2"], "pending")
        self.assertNotIn("intrinsic_permeability_m2", result)
        self.assertEqual(result["source"]["identity_sha256"], source["identity_sha256"])
        with self.assertRaises(ValueError):
            query_material_source(source, -1, 0)

    def test_cross_context_and_bad_resource_or_coordinate_rejected(self):
        source = prepare_material_source(context())
        wrong = context()
        wrong["origin_native_xz"][0] += 1
        with self.assertRaisesRegex(ValueError, "anchors"):
            validate_material_source(source, wrong)
        for key, value in (("world_seed", 20261021), ("spacing_m", 15.), ("origin_native_xz", [0.5, 0])):
            wrong = context()
            wrong[key] = value
            with self.assertRaises(ValueError):
                prepare_material_source(wrong)
        with self.assertRaises(ValueError):
            prepare_material_source(context((65, 65)))


if __name__ == "__main__":
    unittest.main()
