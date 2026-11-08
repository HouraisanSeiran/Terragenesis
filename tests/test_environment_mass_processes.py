from io import BytesIO
import unittest

import numpy as np

from terrain_pipeline import environment_processes as process
from terrain_pipeline.drainage import build_mesh as build_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers


def context(height=None):
    height = np.array([[4., 3., 2., 1., 0.]]) if height is None else np.asarray(height, float)
    mesh = build_mesh(height.shape, origin_native_xz=(10, -4), spacing_m=1., world_seed=20261020)
    ocean = np.zeros(height.shape, bool)
    receiver, _, _ = strict_receivers(height, mesh, outlet_mask=ocean)
    river = np.zeros(height.shape, bool)
    river.ravel()[-2:] = True
    return dict(height_m=height, spacing_m=1., origin_native_xz=(10, -4), world_seed=20261020,
                receiver=receiver.reshape(height.shape), river_mask=river, ocean_mask=ocean,
                valid_mask=np.ones(height.shape, bool), protected_mask=np.zeros(height.shape, bool))


def restored(state):
    with BytesIO() as buffer:
        np.savez(buffer, **state)
        buffer.seek(0)
        with np.load(buffer, allow_pickle=False) as saved:
            return {name: saved[name].copy() for name in saved.files}


def rates(value):
    return {name: {"value": rate, "source": "unit declared engineering scenario"}
            for name, rate in (("k_physical_m_per_s", value),
                               ("k_chemical_m_per_s", 0.), ("k_biological_m_per_s", 0.))}


class MassProcessesTests(unittest.TestCase):
    def test_zero_driver_and_no_input_mutation(self):
        ctx = context()
        state = process.mass_initial_state(ctx)
        saved = restored(state)
        result = process.mass_step(state, {"weathering_parameters": rates(0.)}, ctx, 1.)
        for name in state:
            np.testing.assert_array_equal(state[name], saved[name])
            np.testing.assert_array_equal(result["state"][name], saved[name])
        self.assertEqual(result["ledger"]["solid_residual_m3"], 0.)

    def test_weathering_to_real_hillslope_and_river_inventory_is_finite(self):
        ctx = context()
        state = process.mass_initial_state(ctx, bedrock_thickness_m=.1, bed_hardness=0.)
        forcing = dict(weathering_parameters=rates(1.), transport_fraction_per_s=1., repose_angle_deg=0.)
        first = process.mass_step(state, forcing, ctx, 1.)
        self.assertGreater(first["fluxes"]["river_delivery_solid_m3"].sum(), 0.)
        self.assertGreater(first["state"]["hillslope_deposit_solid_m3"].sum(), 0.)
        np.testing.assert_allclose(first["state"]["bedrock_solid_m3"], 0.)
        self.assertAlmostEqual(first["ledger"]["solid_residual_m3"], 0.)
        current = first["state"]
        for _ in range(8):
            current = process.mass_step(current, forcing, ctx, 1.)["state"]
        self.assertLessEqual(current["river_sediment_solid_m3"].sum(), .5)
        self.assertGreaterEqual(min(value.min() for value in current.values()), 0.)
        np.testing.assert_array_equal(state["bedrock_solid_m3"], np.full((1, 5), .1))

    def test_soil_and_sediment_share_single_weathered_inventory(self):
        ctx = context()
        state = process.mass_initial_state(ctx, bedrock_thickness_m=.1, bed_hardness=0.)
        result = process.mass_step(state, dict(weathering_parameters=rates(1.), soil_request_solid_m3=100.,
                                         transport_fraction_per_s=1., repose_angle_deg=0.), ctx, 1.)
        self.assertGreater(result["state"]["soil_solid_m3"].sum(), 0.)
        self.assertAlmostEqual(result["ledger"]["solid_residual_m3"], 0.)
        self.assertLessEqual(result["state"]["soil_solid_m3"].sum(), .5 * .9 * .5)

    def test_protected_no_weathering_and_resume_matches(self):
        ctx = context()
        ctx["protected_mask"][0, 0] = True
        state = process.mass_initial_state(ctx, bed_hardness=0.)
        forcing = dict(weathering_parameters=rates(.01), transport_fraction_per_s=.2, repose_angle_deg=0.)
        first = process.mass_step(state, forcing, ctx, 10.)["state"]
        self.assertEqual(first["bedrock_solid_m3"][0, 0], state["bedrock_solid_m3"][0, 0])
        direct = process.mass_step(first, forcing, ctx, 10.)
        resumed = process.mass_step(restored(first), forcing, ctx, 10.)
        for name in first:
            np.testing.assert_array_equal(direct["state"][name], resumed["state"][name])
        self.assertAlmostEqual(direct["ledger"]["solid_residual_m3"], 0.)

    def test_invalid_input_rejected(self):
        ctx = context()
        state = process.mass_initial_state(ctx)
        with self.assertRaises(ValueError):
            process.mass_step(state, {"moisture": 2.}, ctx, 1.)
        with self.assertRaises(ValueError):
            process.mass_step(state, {}, ctx, 0.)

    def test_inventory_batches_preserve_full_shape_and_finite_stock(self):
        ctx = context(np.arange(4100., 0., -1.).reshape(1, -1))
        state = process.mass_initial_state(ctx, bedrock_thickness_m=.1, bed_hardness=0.)
        result = process.mass_step(state, {"weathering_parameters": rates(1.)}, ctx, 1.)
        self.assertEqual(result["state"]["regolith_solid_m3"].shape, (1, 4100))
        np.testing.assert_allclose(result["state"]["regolith_solid_m3"], .09)
        self.assertAlmostEqual(result["ledger"]["solid_residual_m3"], 0., places=9)

    def test_existing_bulk_inventory_cannot_change_porosity_silently(self):
        ctx = context()
        first = process.mass_step(process.mass_initial_state(ctx), {"weathering_parameters": rates(.01)}, ctx, 1.)
        parameters = rates(0.)
        parameters["regolith_porosity"] = {"value": .1, "source": "declared different material"}
        with self.assertRaisesRegex(ValueError, "porosity"):
            process.mass_step(first["state"], {"weathering_parameters": parameters}, ctx, 1.)

    def test_root_shear_reduces_actual_mobilized_solid(self):
        ctx = context()
        state = process.mass_initial_state(ctx, bed_hardness=0.)
        forcing = dict(weathering_parameters=rates(.1), transport_fraction_per_s=1., repose_angle_deg=0.)
        bare = process.mass_step(state, forcing, ctx, 1.)
        rooted = process.mass_step(state, {**forcing, "root_cohesion_pa": 100000.}, ctx, 1.)
        self.assertGreater(bare["fluxes"]["mobilized_solid_m3"].sum(), 0.)
        self.assertLess(rooted["fluxes"]["mobilized_solid_m3"].sum(), bare["fluxes"]["mobilized_solid_m3"].sum())
