"""Independent runoff/surface/total water ledgers and cold strict-schema IO."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, identity
from terrain_pipeline.rainfall_runoff import RunoffParameters, simulate_rainfall_runoff
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy
from terrain_pipeline.td_basin_overflow import OverflowParameters, build_overflow_topology
from terrain_pipeline.td_basin_runoff_exchange import (
    _RunoffExchange, RunoffExchangeParameters, load_runoff_exchange,
    save_runoff_exchange, simulate_runoff_exchange, validate_runoff_exchange,
)
from terrain_pipeline.td_basin_source import make_td_source


class RunoffExchangeTests(unittest.TestCase):
    def topology(self, *, opened=False, single=False):
        height = np.array([[0.]]) if single else np.array([[0., 1., 0.]])
        boundary = np.zeros(height.shape, bool)
        if opened:
            boundary[0, -1] = True
        return build_overflow_topology(build_basin_hierarchy(make_td_source(
            height, spacing_m=1., open_boundary_mask=boundary)))

    def simulate(self, topology=None, rain=None, **kwargs):
        topology = self.topology() if topology is None else topology
        count = len(topology["arrays"]["leaf_ids"])
        rain = np.full((4, count), 30.) if rain is None else rain
        parameters = kwargs.pop("parameters", RunoffExchangeParameters(timestep_s=300., duration_s=300. * len(rain)))
        return simulate_runoff_exchange(topology, rain, parameters=parameters, **kwargs)

    def writable(self, event):
        return {"arrays": {key: value.copy() for key, value in event["arrays"].items()},
                "metadata": copy.deepcopy(event["metadata"]), "identity_sha256": event["identity_sha256"]}

    def repin(self, event):
        event["identity_sha256"] = identity(event["arrays"], event["metadata"])
        return event

    def assert_balances(self, event):
        arrays = event["arrays"]
        for key in ("balance_residual_m3", "surface_balance_residual_m3", "total_balance_residual_m3"):
            self.assertLess(float(np.max(np.abs(arrays[key]))), 1e-7)
        total_change = arrays["total_water_m3"][-1].sum() - arrays["total_water_m3"][0].sum()
        self.assertAlmostEqual(total_change, arrays["rain_volume_m3"].sum() - arrays["et_volume_m3"].sum() - arrays["engineering_boundary_outflow_m3"].sum(), places=7)
        for key in ("soil_volume_m3", "fast_volume_m3", "slow_volume_m3", "surface_volume_m3",
                    "face_forward_m3", "face_reverse_m3", "engineering_boundary_outflow_m3"):
            self.assertTrue(np.all(arrays[key] >= 0))

    def test_single_closed_leaf_conserves_four_separate_inventories(self):
        topology = self.topology(single=True)
        rain = np.array([[30.], [120.], [0.], [0.]])
        event = self.simulate(topology, rain)
        arrays = event["arrays"]
        self.assert_balances(event)
        np.testing.assert_allclose(np.diff(arrays["surface_volume_m3"], axis=0), arrays["outflow_volume_m3"], atol=1e-10)
        self.assertGreater(float(arrays["outflow_volume_m3"][-1].sum()), 0.)
        for flag in ("hydraulic_ready", "transient_converged", "natural_outlet_verified", "publishable"):
            self.assertIs(event["metadata"][flag], False)

    def test_spatial_rain_reuses_exact_runoff_without_duplicate_supply(self):
        topology = self.topology()
        rain = np.array([[20., 120.], [0., 30.], [80., 0.], [0., 0.]])
        untouched_rain = rain.copy()
        runoff_parameters = RunoffParameters(initial_soil_mm=10., initial_fast_mm=2., initial_slow_mm=3.)
        event = self.simulate(topology, rain, runoff_parameters=runoff_parameters, initial_surface_volume_m3=[2., 1.])
        expected = simulate_rainfall_runoff(rain, topology["arrays"]["leaf_area_m2"], dt_s=300.,
                                            source_id="lumped-basin-rainfall", parameters=runoff_parameters)
        for key in ("rain_volume_m3", "et_volume_m3", "soil_mm", "fast_mm", "slow_mm", "outflow_volume_m3"):
            np.testing.assert_array_equal(event["arrays"][key], expected[key])
        np.testing.assert_array_equal(event["arrays"]["surface_input_volume_m3"], expected["outflow_volume_m3"])
        np.testing.assert_array_equal(rain, untouched_rain)
        self.assert_balances(event)

    def test_dry_zero_initial_storage_never_gets_legacy_baseflow(self):
        runoff = RunoffParameters(initial_soil_mm=0., potential_et_mm_h=0., percolation_mm_h=0.)
        event = self.simulate(rain=np.zeros((4, 2)), runoff_parameters=runoff)
        self.assertTrue(np.all(event["arrays"]["total_water_m3"] == 0.))
        self.assertTrue(np.all(event["arrays"]["surface_input_volume_m3"] == 0.))
        with self.assertRaises(ValueError):
            self.simulate(parameters=OverflowParameters(timestep_s=300., duration_s=1200.))

    def test_one_way_engineering_boundary_and_real_face_reversal(self):
        topology = self.topology(opened=True)
        rain = np.array([[0., 0.], [120000., 0.], [0., 0.], [0., 0.]])
        runoff = RunoffParameters(infiltration_capacity_mm_h=0., initial_soil_mm=0.,
                                  potential_et_mm_h=0., percolation_mm_h=0., fast_tau_s=30.)
        event = self.simulate(topology, rain, runoff_parameters=runoff, initial_surface_volume_m3=[0., 10.],
                              parameters=RunoffExchangeParameters(timestep_s=300., duration_s=1200., boundary_conductance_m_s=.00001))
        self.assert_balances(event)
        self.assertGreater(float(event["arrays"]["face_forward_m3"].sum()), 0.)
        self.assertGreater(float(event["arrays"]["face_reverse_m3"].sum()), 0.)
        self.assertGreater(float(event["arrays"]["engineering_boundary_outflow_m3"].sum()), 0.)
        self.assertIn("one-way", event["metadata"]["boundary_semantics"])

    def test_inherited_sparse_jacobian_and_positive_stage_quadrature(self):
        exchange = _RunoffExchange(self.topology(opened=True), RunoffExchangeParameters())
        exchange.set_runoff_volume(np.array([1., 2.]), 300.)
        values = np.concatenate(([10., 5.], np.zeros(exchange.size - exchange.count)))
        analytic = exchange.jacobian(0., values).toarray()
        for column in range(exchange.size):
            perturbation = np.zeros(exchange.size)
            perturbation[column] = 1e-6
            numerical = (exchange.rhs(0., values + perturbation) - exchange.rhs(0., values - perturbation)) / 2e-6
            np.testing.assert_allclose(analytic[:, column], numerical, atol=1e-8)
        actual_conservative_step = _RunoffExchange.conservative_step
        with patch.object(_RunoffExchange, "conservative_step", autospec=True, side_effect=actual_conservative_step) as conservative:
            self.simulate(initial_surface_volume_m3=[10., 5.])
            self.assertGreater(conservative.call_count, 0)

    def test_surface_step_refinement_keeps_the_same_300_second_runoff_forcing(self):
        topology = self.topology()
        rain = np.array([[30., 120.], [0., 20.], [0., 0.], [0., 0.]])
        coarse = self.simulate(topology, rain, initial_surface_volume_m3=[10., 5.], max_step_s=300.)
        fine = self.simulate(topology, rain, initial_surface_volume_m3=[10., 5.], max_step_s=150., rtol=5e-8)
        for key in ("soil_mm", "fast_mm", "slow_mm", "outflow_volume_m3"):
            np.testing.assert_array_equal(coarse["arrays"][key], fine["arrays"][key])
        np.testing.assert_allclose(coarse["arrays"]["surface_volume_m3"], fine["arrays"]["surface_volume_m3"], rtol=1e-7, atol=1e-7)
        self.assertEqual(fine["metadata"]["runoff_metadata"]["dt_s"], 300.)
        self.assert_balances(fine)

    def test_static_validation_rejects_rehashed_bad_ledgers_shapes_and_flags(self):
        topology = self.topology()
        original = self.simulate(topology, initial_surface_volume_m3=[10., 5.])
        mutations = [lambda event: event["arrays"].pop("soil_mm"),
                     lambda event: event["arrays"].update(unknown=np.zeros(1)),
                     lambda event: event["metadata"].update(schema="old-four-store-schema"),
                     lambda event: event["metadata"].update(publishable=True),
                     lambda event: event["metadata"].update(baseflow_mm_per_day=.15),
                     lambda event: event["metadata"]["parameters"].update(runoff_coefficient=.35),
                     lambda event: event["metadata"]["work"].update(accepted_steps=True),
                     lambda event: event["arrays"].update(surface_volume_m3=np.zeros((1, 2))),
                     lambda event: event["arrays"].update(stage_m=event["arrays"]["stage_m"].astype(np.float32)),
                     lambda event: event["arrays"]["surface_input_volume_m3"].__setitem__((0, 0), 100.),
                     lambda event: event["arrays"]["surface_volume_m3"].__setitem__((1, 0), -1.),
                     lambda event: event["arrays"]["face_forward_m3"].__setitem__((0, 0), -1.),
                     lambda event: event["arrays"]["soil_volume_m3"].__setitem__((0, 0), 10.),
                     lambda event: event["arrays"]["total_water_m3"].__setitem__((1, 0), 100.),
                     lambda event: event["arrays"]["surface_balance_residual_m3"].__setitem__((0, 0), .1),
                     lambda event: event["arrays"]["stage_m"].__setitem__((1, 0), float("nan"))]
        for index, mutation in enumerate(mutations):
            corrupted = self.writable(original)
            mutation(corrupted)
            if any(not np.isfinite(value).all() for value in corrupted["arrays"].values()):
                corrupted["identity_sha256"] = "0" * 64
            else:
                self.repin(corrupted)
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_runoff_exchange(corrupted, topology)

    def test_rehashed_zero_residual_does_not_hide_added_surface_water(self):
        topology = self.topology(single=True)
        event = self.writable(self.simulate(topology))
        arrays = event["arrays"]
        arrays["surface_volume_m3"][1:] += 1.
        arrays["total_water_m3"][1:] += 1.
        arrays["surface_balance_residual_m3"][:] = 0.
        arrays["total_balance_residual_m3"][:] = 0.
        with self.assertRaises(ValueError):
            validate_runoff_exchange(self.repin(event), topology)

    def test_illegal_forcing_parameters_initial_and_topology_rejected(self):
        for rain in (np.zeros(4), np.zeros((4, 3)), np.full((4, 2), True), np.full((4, 2), -1.),
                     np.full((4, 2), float("inf"))):
            with self.subTest(shape=rain.shape), self.assertRaises(ValueError):
                self.simulate(rain=rain)
        for kwargs in ({"rtol": True}, {"max_step_s": 0.}, {"initial_surface_volume_m3": [True, False]},
                       {"initial_surface_volume_m3": [-1., 0.]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.simulate(**kwargs)
        for values in ({"timestep_s": True}, {"duration_s": 301.}, {"face_conductance_m_s": -1.}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                RunoffExchangeParameters(**values)
        topology = self.topology()
        topology["identity_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.simulate(topology)
        with patch("terrain_pipeline.td_basin_runoff_exchange.MAX_ARRAY_BYTES", 1), self.assertRaises(ValueError):
            self.simulate()

    def test_saved_cold_io_is_solver_free_pinned_readonly_and_no_overwrite(self):
        topology = self.topology()
        event = self.simulate(topology)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "exchange.npz"
            save_runoff_exchange(event, path, topology)
            pin = file_sha256(path)
            with patch("terrain_pipeline.td_basin_runoff_exchange.Radau", side_effect=AssertionError("cold solver forbidden")), patch("terrain_pipeline.td_basin_runoff_exchange.simulate_rainfall_runoff", side_effect=AssertionError("cold runoff forbidden")):
                saved = load_runoff_exchange(path, expected_sha256=pin, expected_identity=event["identity_sha256"], topology=topology)
            for key, value in saved["arrays"].items():
                np.testing.assert_array_equal(value, event["arrays"][key])
                self.assertFalse(value.flags.writeable)
            with self.assertRaises(FileExistsError):
                save_runoff_exchange(event, path, topology)
            for hash_value, identity_value in (("0" * 64, event["identity_sha256"]), (pin, "0" * 64)):
                with self.assertRaises(ValueError):
                    load_runoff_exchange(path, expected_sha256=hash_value, expected_identity=identity_value, topology=topology)
            damaged = self.writable(event)
            damaged["arrays"]["unknown"] = np.zeros(1)
            self.repin(damaged)
            bad_path = Path(directory) / "unknown.npz"
            from terrain_pipeline.mountain_source_adapter import save_bundle
            save_bundle(bad_path, damaged, validator=lambda _: True)
            with self.assertRaisesRegex(ValueError, "archive fields"):
                load_runoff_exchange(bad_path, expected_sha256=file_sha256(bad_path), expected_identity=damaged["identity_sha256"], topology=topology)


if __name__ == "__main__":
    unittest.main()
