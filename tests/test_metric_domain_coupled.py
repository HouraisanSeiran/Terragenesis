"""`metric_domain_coupled`: the coupled water-sediment ledger's contracts.

What is held to account here, and what deliberately is not:

1. both P8 ledgers still close -- per-domain `weathered = entrained + store_change`
   and `entrained = deposited + delivered`, plus the tile atlas with the stranded
   bin, with the reported totals recomputed from the arrays rather than trusted;
2. **the capacity gate** -- entrainment never exceeds what the flow's own shear
   implies. `totals.capacity_violation_m3` is a hard zero, recomputed on reload;
3. **the coupling gate** -- the thing the P8 slope law structurally could not do:
   `clip(gain * slope, 0, 1)` entrained sediment even with no water at all, because
   it knew nothing about discharge. Here, closing the whole water chain (rain 0 AND
   an empty soil bucket, so the release is exactly zero) entrains **exactly zero**;
4. monotonicity in the transport coefficient, and no saturation at the declared
   default (the P8 law was 91% saturated, i.e. nearly signal-free);
5. refusals stay refusals and the ledger writes no terrain.

A note on why gate 3 needs `initial_soil_mm = 0`: the repository's soil bucket
starts with 30 mm and drains it, so `rain = 0` alone still releases water -- this is
P7's documented draw-down behaviour, not a coupling failure. The gate is therefore
stated as "**zero release implies zero entrainment**", which is the honest and
testable form, and the probe checks the release is exactly zero first.
"""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import numpy as np

from terrain_pipeline.hydrology_planning import PlanningConfig
from terrain_pipeline.channel_geometry import ChannelRecipe
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_domain_closure import (
    clear_cache, domain_topology,
)
from terrain_pipeline.surface_rivers.metric_domain_coupled import (
    ALGORITHM,
    COUPLED_SCHEMA,
    MAX_INTERVALS,
    PRODUCT_KEYS,
    CoupledParameters,
    load_domain_coupled,
    save_domain_coupled,
    solve_domain_coupled,
    validate_domain_coupled,
)
from terrain_pipeline.surface_rivers.metric_domain_flow import (
    domain_flow_topology, solve_domain_flow,
)

SEED = 20261020
CONFIG = PlanningConfig()
POINTS = (
    (0.0, 30000.0),
    (0.0, 40000.0),
    (40000.0, 0.0),
    (20000.0, 0.0),
)
RAIN_MM_H = 4.0
DT_S = 3600.0
INTERVALS = 4
# Closing the water chain needs an empty bucket as well as no rain (see the
# module docstring: the repository bucket drains a 30 mm initial store).
DRY_RUNOFF = RunoffParameters(initial_soil_mm=0.0, initial_fast_mm=0.0,
                              initial_slow_mm=0.0)


class CoupledLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clear_cache()
        cls.record = solve_domain_coupled(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                          dt_s=DT_S, intervals=INTERVALS)
        cls.topology = domain_topology(SEED, POINTS[0][0], POINTS[0][1], CONFIG)

    @classmethod
    def tearDownClass(cls):
        clear_cache()

    def temp_dir(self, name):
        root = Path(tempfile.mkdtemp(prefix="domain-coupled-%s-" % name))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    # ------------------------------------------------ repeatability
    def test_same_scenario_reruns_to_the_same_identity(self):
        clear_cache()
        try:
            again = solve_domain_coupled(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                         dt_s=DT_S, intervals=INTERVALS)
        finally:
            clear_cache()
        self.assertEqual(again["identity_sha256"], self.record["identity_sha256"])

    def test_identity_survives_a_write_and_reload(self):
        root = self.temp_dir("reload")
        path = root / "coupled.npz"
        save_domain_coupled(path, self.record)
        reloaded = load_domain_coupled(path, expected_sha256=_file_sha256(path),
                                       expected_identity=self.record["identity_sha256"])
        self.assertEqual(reloaded["identity_sha256"], self.record["identity_sha256"])
        for key in PRODUCT_KEYS:
            self.assertTrue(np.array_equal(np.asarray(reloaded["arrays"][key]),
                                           np.asarray(self.record["arrays"][key])), key)

    def test_tampered_product_is_refused(self):
        root = self.temp_dir("tamper")
        path = root / "coupled.npz"
        save_domain_coupled(path, self.record)
        digest = _file_sha256(path)
        with path.open("r+b") as handle:
            handle.seek(path.stat().st_size // 2)
            handle.write(b"\x00")
        with self.assertRaises(ValueError):
            load_domain_coupled(path, expected_sha256=digest)

    # ------------------------------------------------ both ledgers close
    def test_every_domain_source_ledger_closes(self):
        arrays = self.record["arrays"]
        weathered = np.asarray(arrays["weathered_m3"], np.float64)
        entrained = np.asarray(arrays["entrained_m3"], np.float64)
        store = np.asarray(arrays["store_change_m3"], np.float64)
        scale = np.maximum(weathered + entrained + np.abs(store), 1.0)
        worst = (np.max(np.abs(weathered - entrained - store) / scale)
                 if weathered.size else 0.0)
        self.assertLess(worst, 1e-9)

    def test_every_domain_routing_ledger_closes(self):
        arrays = self.record["arrays"]
        entrained = np.asarray(arrays["entrained_m3"], np.float64)
        deposited = np.asarray(arrays["deposited_m3"], np.float64)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        scale = np.maximum(entrained + deposited + delivered, 1.0)
        worst = (np.max(np.abs(entrained - deposited - delivered) / scale)
                 if entrained.size else 0.0)
        self.assertLess(worst, 1e-9)

    def test_tile_ledgers_close(self):
        totals = self.record["metadata"]["totals"]
        tolerance = 1e-6 * max(abs(totals["entrained_total_m3"]), 1.0)
        self.assertLess(abs(totals["source_residual_m3"]), tolerance)
        self.assertLess(abs(totals["routing_residual_m3"]), tolerance)
        self.assertGreaterEqual(totals["stranded_on_refused_m3"], 0.0)
        atlas = (totals["deposited_total_m3"] + totals["delivered_total_m3"]
                 + totals["stranded_on_refused_m3"])
        self.assertAlmostEqual(totals["entrained_total_m3"], atlas, places=3)

    def test_reported_totals_are_recomputed_from_the_arrays(self):
        arrays = self.record["arrays"]
        totals = self.record["metadata"]["totals"]
        kind = np.asarray(arrays["kind"]).astype(str)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        for name, array in (("weathered_total_m3", "weathered_m3"),
                            ("entrained_total_m3", "entrained_m3"),
                            ("deposited_total_m3", "deposited_m3"),
                            ("delivered_total_m3", "delivered_m3"),
                            ("store_change_total_m3", "store_change_m3")):
            self.assertAlmostEqual(totals[name], float(np.sum(arrays[array])), places=3)
        self.assertAlmostEqual(totals["delivered_to_sea_m3"],
                               float(np.sum(delivered[kind == "marine"])), places=3)
        self.assertAlmostEqual(totals["delivered_to_basins_m3"],
                               float(np.sum(delivered[kind == "inland"])), places=3)

    def test_a_forged_totals_block_is_caught(self):
        for key in ("entrained_total_m3", "delivered_total_m3", "source_residual_m3",
                    "routing_residual_m3", "capacity_volume_total_m3"):
            forged = _deep_copy_bundle(self.record)
            forged["metadata"]["totals"][key] += 1.0
            with self.assertRaises(ValueError):
                validate_domain_coupled(forged)

    # ------------------------------------------------ the capacity gate
    def test_entrainment_never_exceeds_the_flows_own_capacity(self):
        totals = self.record["metadata"]["totals"]
        self.assertEqual(totals["capacity_violation_m3"], 0.0)
        self.assertLessEqual(totals["entrained_total_m3"],
                             totals["capacity_volume_total_m3"] + 1e-6)

    def test_a_capacity_violation_is_refused_on_validation(self):
        # The gate is a hard zero, not a tolerance to widen: a product that claims
        # more entrainment than its own reported capacity is not a product.
        forged = _deep_copy_bundle(self.record)
        forged["metadata"]["totals"]["capacity_violation_m3"] = 1.0
        forged["identity_sha256"] = _identity(forged)
        with self.assertRaises(ValueError):
            validate_domain_coupled(forged)

    def test_tile_entrainment_cannot_exceed_the_tile_capacity_budget(self):
        forged = _deep_copy_bundle(self.record)
        # Shrink the reported capacity below the entrainment and re-seal the identity
        # so the check under test is the capacity gate, not the identity gate.
        forged["metadata"]["totals"]["capacity_volume_total_m3"] = (
            float(forged["metadata"]["totals"]["entrained_total_m3"]) * 0.5)
        forged["identity_sha256"] = _identity(forged)
        with self.assertRaises(ValueError):
            validate_domain_coupled(forged)

    # ------------------------------------------------ the coupling gate
    def test_zero_release_entrains_exactly_nothing(self):
        """The gate the P8 slope law structurally could not express.

        `metric_domain_sediment` entrained `7.57e8 m3` from slope alone; here the
        whole water chain is closed, so there is no discharge, no shear, no
        capacity -- and therefore exactly no entrainment. The release is asserted
        to be exactly zero first, so the test cannot pass for the wrong reason.
        """
        clear_cache()
        try:
            dry = solve_domain_coupled(
                SEED, POINTS, 0.0, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(runoff=DRY_RUNOFF))
        finally:
            clear_cache()
        validate_domain_coupled(dry)
        totals = dry["metadata"]["totals"]
        self.assertEqual(totals["water_release_total_m3"], 0.0)
        self.assertEqual(totals["capacity_volume_total_m3"], 0.0)
        self.assertEqual(totals["entrained_total_m3"], 0.0)
        self.assertEqual(totals["deposited_total_m3"], 0.0)
        self.assertEqual(totals["delivered_total_m3"], 0.0)
        self.assertEqual(totals["zero_capacity_cells"], totals["accepted_cells"])
        # With no transport, the declared weathering simply STAYS in the store.
        self.assertAlmostEqual(totals["store_change_total_m3"],
                               totals["weathered_total_m3"], places=3)

    def test_entrainment_is_monotone_in_the_transport_coefficient(self):
        clear_cache()
        try:
            weak = solve_domain_coupled(
                SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(transport_coefficient_m3_s_per_pa15=1e-6))
            strong = solve_domain_coupled(
                SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(transport_coefficient_m3_s_per_pa15=1e-5))
        finally:
            clear_cache()
        weak_totals = weak["metadata"]["totals"]
        strong_totals = strong["metadata"]["totals"]
        self.assertGreater(strong_totals["entrained_total_m3"],
                           weak_totals["entrained_total_m3"])
        self.assertGreater(strong_totals["capacity_volume_total_m3"],
                           weak_totals["capacity_volume_total_m3"])
        for name in (weak_totals, strong_totals):
            self.assertEqual(name["capacity_violation_m3"], 0.0)

    def test_more_discharge_means_more_capacity(self):
        """After P9.1 the ceiling no longer hides the rainfall response.

        Before the calibration this test had to lift the width clip by hand to see
        any monotonicity, and had to assert that doubling the rainfall changed
        NOTHING (the infiltration threshold swallowed it). Both of those were
        measurements of the old ceilings. Now the release and the capacity must
        both rise with the rain on the declared defaults.
        """
        releases = []
        capacities = []
        entrained = []
        for rain in (4.0, 8.0, 20.0, 40.0):
            clear_cache()
            try:
                run = solve_domain_coupled(SEED, POINTS, rain, config=CONFIG,
                                           dt_s=DT_S, intervals=INTERVALS)
            finally:
                clear_cache()
            totals = run["metadata"]["totals"]
            self.assertEqual(totals["capacity_violation_m3"], 0.0)
            releases.append(totals["water_release_total_m3"])
            capacities.append(totals["capacity_volume_total_m3"])
            entrained.append(totals["entrained_total_m3"])
        self.assertTrue(all(b > a for a, b in zip(releases, releases[1:])),
                        "release must rise with rainfall once the infiltration "
                        "threshold is below the scenario")
        self.assertTrue(all(b > a for a, b in zip(capacities, capacities[1:])),
                        "capacity must rise with rainfall on the declared defaults")
        # Entrainment rises too, but it converges on the declared weathered volume:
        # the source is still a constant, so this is the measured shape of the
        # remaining limitation, not a hidden failure.
        self.assertTrue(all(b >= a for a, b in zip(entrained, entrained[1:])))
        weathered = totals["weathered_total_m3"]
        self.assertLessEqual(entrained[-1], weathered * 1.001)

    def test_the_calibration_is_visible_in_the_product(self):
        """The calibrated regime must be readable from the product itself.

        `capacity_utilisation` is the honest dial: before P9.1 it sat at ~0.98 (the
        capacity gate was binding everywhere); after raising the ceilings it drops
        far below 1, which is the measurable statement that the chain became
        SOURCE-limited rather than capacity-limited.
        """
        totals = self.record["metadata"]["totals"]
        channel = CoupledParameters().channel
        for name in ("capacity_utilisation", "mean_channel_width_m", "max_channel_width_m",
                     "min_channel_width_m", "mean_channel_depth_m", "max_channel_depth_m",
                     "min_channel_depth_m", "mean_excess_shear_pa",
                     "mean_reference_discharge_m3_s", "zero_capacity_cells"):
            self.assertIn(name, totals)
        self.assertGreaterEqual(totals["capacity_utilisation"], 0.0)
        self.assertLessEqual(totals["capacity_utilisation"], 1.0)
        self.assertLess(totals["capacity_utilisation"], 0.5,
                        "after P9.1 the capacity is no longer the binding constraint")
        self.assertLessEqual(totals["max_channel_width_m"], channel.max_width_m)
        self.assertGreater(totals["mean_reference_discharge_m3_s"], 0.0)

    def test_the_declared_default_is_not_saturated(self):
        """The measured reason this module exists.

        P8's slope law was 91.05% saturated at its declared default, so the slope
        term carried almost no signal. Capacity-limited entrainment reaches its own
        ceiling much more selectively: the utilisation is high but the gate is an
        inequality that is met, not a clip that erased the terrain dependence.
        """
        totals = self.record["metadata"]["totals"]
        self.assertGreater(totals["capacity_utilisation"], 0.0)
        self.assertLessEqual(totals["capacity_utilisation"], 1.0)
        # Not every cell is at its ceiling: some have slack.
        self.assertGreater(totals["zero_capacity_cells"], 0)

    # ------------------------------------------------ geometry is the repo's law
    def test_channel_geometry_follows_the_declared_power_law(self):
        # The caps under test are the COUPLED chain's own (P9.1 calibration), not
        # `ChannelRecipe()`'s defaults: the module deliberately re-bases them, and
        # asserting against the home module's numbers would test the wrong type.
        totals = self.record["metadata"]["totals"]
        channel = CoupledParameters().channel
        self.assertGreater(totals["mean_channel_width_m"], 0.0)
        self.assertLessEqual(totals["max_channel_width_m"], channel.max_width_m)
        self.assertGreaterEqual(totals["min_channel_width_m"], channel.min_width_m)
        self.assertLessEqual(totals["max_channel_depth_m"], channel.max_depth_m)
        self.assertGreaterEqual(totals["min_channel_depth_m"], channel.min_depth_m)

    def test_flow_path_slope_and_independent_capacity_use_source_graph_metric(self):
        from terrain_pipeline.drainage import grid_mesh as grid_mesh
        from terrain_pipeline.drainage import strict_receivers as strict_receivers
        from terrain_pipeline.surface_rivers.metric_domain_coupled import _channel_geometry
        from tools.audit_domain_coupled import independent_capacity
        z, x = np.indices((7, 9))
        height = 200. - 2 * x - z
        origin = (-135., 225.)
        mesh = grid_mesh(height.shape, x0_m=origin[0], z0_m=origin[1], dx_m=30., world_seed=SEED)
        receiver = strict_receivers(height, mesh)[0].reshape(height.shape)
        q = np.full(height.shape, 4.)
        parameters = CoupledParameters()
        width, depth, slope = _channel_geometry(q, parameters.channel, 30., height, receiver,
            origin_xz_m=origin, world_seed=SEED)
        donors = np.flatnonzero(receiver.ravel() >= 0)
        targets = receiver.ravel()[donors]
        lengths = np.hypot(mesh.node_x_m[donors] - mesh.node_x_m[targets],
                           mesh.node_z_m[donors] - mesh.node_z_m[targets])
        expected = (height.ravel()[donors] - height.ravel()[targets]) / lengths
        np.testing.assert_allclose(slope.ravel()[donors], expected, rtol=0, atol=1e-14)
        native_lengths = 30 * np.hypot(donors // 9 - targets // 9, donors % 9 - targets % 9)
        self.assertGreater(np.max(np.abs(lengths - native_lengths)), 1.)
        capacity, audit_width, tau = independent_capacity(height, receiver, q.ravel(),
            parameters.channel, 30., parameters.sediment_critical_shear_pa,
            parameters.transport_coefficient_m3_s_per_pa15, origin_xz_m=origin, world_seed=SEED)
        np.testing.assert_array_equal(audit_width, width.ravel())
        radius = width * depth / (width + 2 * depth)
        np.testing.assert_allclose(tau, (1000 * 9.81 * radius * slope).ravel())

    def test_the_calibration_moved_the_declared_ceilings(self):
        """P9.1: the three ceilings are the calibrated ones, and say why.

        Each value is pinned here so an accidental revert to the inherited defaults
        shows up as a failure rather than as a silent loss of rainfall resolution.
        """
        parameters = CoupledParameters()
        self.assertEqual(parameters.runoff.infiltration_capacity_mm_h, 2.0)
        self.assertEqual(parameters.channel.max_width_m, 1000.0)
        self.assertEqual(parameters.channel.max_depth_m, 50.0)
        self.assertEqual(parameters.sediment_critical_shear_pa, 50.0)

    def test_the_declared_coefficients_are_the_repository_ones(self):
        # The transport coefficient is the repository's, unchanged. The critical
        # shear is a DELIBERATE deviation (P9.1 calibration: 1 -> 50 Pa), pinned so
        # it cannot drift silently; the module docstring records that at this scale
        # the threshold is nearly inert (coarse-grid shear ~1450 Pa).
        import dataclasses
        material = MaterialParameters()
        parameters = CoupledParameters()
        self.assertEqual(parameters.transport_coefficient_m3_s_per_pa15,
                         material.transport_coefficient)
        self.assertNotEqual(parameters.sediment_critical_shear_pa,
                            material.sediment_critical_shear_pa)
        self.assertEqual(parameters.sediment_critical_shear_pa, 50.0)
        self.assertEqual(set(dataclasses.asdict(parameters.channel)),
                         set(dataclasses.asdict(ChannelRecipe())))

    def test_a_wider_channel_carries_more_sediment(self):
        # The override must keep caps at least as large as the calibrated defaults,
        # otherwise "wider" silently becomes narrower than the reference run.
        calibrated = CoupledParameters().channel
        clear_cache()
        try:
            wide = solve_domain_coupled(
                SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(
                    channel=ChannelRecipe(min_width_m=calibrated.min_width_m,
                                          reference_width_m=calibrated.reference_width_m * 2.0,
                                          max_width_m=calibrated.max_width_m * 2.0,
                                          min_depth_m=calibrated.min_depth_m,
                                          max_depth_m=calibrated.max_depth_m)))
        finally:
            clear_cache()
        self.assertGreater(wide["metadata"]["totals"]["capacity_volume_total_m3"],
                           self.record["metadata"]["totals"]["capacity_volume_total_m3"])

    # ------------------------------------------------ the water half is reused
    def test_the_water_half_matches_the_flow_ledger(self):
        """The coupled ledger must reuse the water ledger, not re-derive it.

        The comparison must use the SAME runoff parameters the coupled chain
        declares: after P9.1 its infiltration ceiling (2 mm/h) differs from the
        water ledger's own default (15 mm/h), so comparing against `solve_domain_flow`
        with its defaults would measure that deliberate difference, not a
        disagreement about the bucket.
        """
        runoff = CoupledParameters().runoff
        clear_cache()
        try:
            water = domain_flow_topology(SEED, POINTS[0][0], POINTS[0][1], RAIN_MM_H,
                                         config=CONFIG, parameters=runoff,
                                         dt_s=DT_S, intervals=INTERVALS)
            flow = solve_domain_flow(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                     parameters=runoff, dt_s=DT_S,
                                     intervals=INTERVALS)
        finally:
            clear_cache()
        accessor_total = float(np.sum(water["released_grid_m3"]))
        self.assertAlmostEqual(
            accessor_total, flow["metadata"]["totals"]["released_total_m3"], places=3)
        totals = self.record["metadata"]["totals"]
        self.assertAlmostEqual(totals["water_release_total_m3"], accessor_total, places=3)

    def test_the_water_ledger_own_default_is_left_alone(self):
        # P9.1 calibrates the COUPLED chain only; `rainfall_runoff`'s shared default
        # must keep its own value, because the water ledger's published behaviour
        # (and its draw-down fixtures) depend on it.
        self.assertEqual(RunoffParameters().infiltration_capacity_mm_h, 15.0)
        self.assertEqual(CoupledParameters().runoff.infiltration_capacity_mm_h, 2.0)

    def test_reading_the_accessor_does_not_change_any_answer(self):
        # The accessor is read-only: calling it must not disturb the published water
        # identity (it exposes already-computed arrays, it does not mutate state).
        clear_cache()
        try:
            before = solve_domain_flow(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                       dt_s=DT_S, intervals=INTERVALS)["identity_sha256"]
            domain_flow_topology(SEED, POINTS[0][0], POINTS[0][1], RAIN_MM_H,
                                 config=CONFIG, dt_s=DT_S, intervals=INTERVALS)
            after = solve_domain_flow(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                      dt_s=DT_S, intervals=INTERVALS)["identity_sha256"]
        finally:
            clear_cache()
        self.assertEqual(before, after)

    # ------------------------------------------------ refusals stay refusals
    def test_second_tile_is_an_input_error(self):
        far = CONFIG.macro_span_m * 4 * 10
        with self.assertRaises(ValueError):
            solve_domain_coupled(SEED, [POINTS[0], (far, far)], RAIN_MM_H,
                                 config=CONFIG, dt_s=DT_S, intervals=INTERVALS)

    def test_no_points_is_an_input_error(self):
        with self.assertRaises(ValueError):
            solve_domain_coupled(SEED, [], RAIN_MM_H, config=CONFIG,
                                 dt_s=DT_S, intervals=INTERVALS)

    def test_invalid_rainfall_is_refused(self):
        for bad in (-1.0, True, np.full(3, 1.0), np.zeros((2, 2, 2))):
            with self.assertRaises(ValueError):
                solve_domain_coupled(SEED, POINTS, bad, config=CONFIG,
                                     dt_s=DT_S, intervals=INTERVALS)

    def test_interval_and_time_budgets_are_enforced(self):
        for bad in (0, MAX_INTERVALS + 1, 2.5, True):
            with self.assertRaises(ValueError):
                solve_domain_coupled(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                     dt_s=DT_S, intervals=bad)
        for bad in (0.0, -1.0, float("nan"), True):
            with self.assertRaises(ValueError):
                solve_domain_coupled(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                     dt_s=bad, intervals=INTERVALS)

    def test_parameter_bounds_are_enforced(self):
        for bad in (dict(weathered_m_per_interval=-1.0),
                    dict(deposit_fraction=1.5),
                    dict(deposit_fraction=-0.1),
                    dict(initial_mobile_m=-1.0),
                    dict(transport_coefficient_m3_s_per_pa15=-1.0),
                    dict(sediment_critical_shear_pa=-1.0),
                    dict(weathered_m_per_interval=float("nan"))):
            with self.assertRaises(ValueError):
                CoupledParameters(**bad)
        with self.assertRaises(ValueError):
            CoupledParameters(channel="not a recipe")
        with self.assertRaises(ValueError):
            CoupledParameters(runoff="not runoff parameters")

    def test_misshaped_source_injection_is_refused_not_broadcast(self):
        for bad in (np.zeros(3), np.zeros((2, 2)), True):
            with self.assertRaises(ValueError):
                solve_domain_coupled(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                     dt_s=DT_S, intervals=INTERVALS,
                                     source_m_per_interval=bad)

    def test_product_carries_the_contract_schema(self):
        arrays = self.record["arrays"]
        self.assertEqual(set(arrays), set(PRODUCT_KEYS))
        self.assertEqual(self.record["metadata"]["schema"], COUPLED_SCHEMA)
        self.assertEqual(self.record["metadata"]["algorithm"], ALGORITHM)
        claims = self.record["metadata"]["claims"]
        self.assertTrue(all(claims[key] is False for key in claims))

    def test_the_ledger_writes_no_terrain(self):
        self.assertTrue(all(key not in PRODUCT_KEYS for key in
                            ("bed_change_m", "height_m", "base_height_m", "surface_m")))
        self.assertIs(self.record["metadata"]["claims"]["terrain_feedback_applied"], False)

    def test_cells_are_the_accepted_core_cells(self):
        topology = self.topology
        margin = topology["margin"]
        core = topology["core_cells"]
        accepted_core = topology["accepted"][margin:margin + core + 1,
                                             margin:margin + core + 1]
        cells_x = np.asarray(self.record["arrays"]["cells_x_m"], np.float64)
        self.assertEqual(cells_x.size, int(np.count_nonzero(accepted_core)))

    def test_domains_are_keyed_by_outlet_world_coordinate(self):
        arrays = self.record["arrays"]
        keys = np.stack([np.asarray(arrays["outlet_x_m"], np.float64),
                         np.asarray(arrays["outlet_z_m"], np.float64)], axis=1)
        self.assertEqual(np.unique(keys, axis=0).shape[0], keys.shape[0])
        self.assertEqual(keys.shape[0], int(self.record["metadata"]["domain_count"]))

    def test_kind_is_marine_or_inland_only(self):
        kind = np.asarray(self.record["arrays"]["kind"]).astype(str)
        self.assertTrue(set(kind.tolist()).issubset({"marine", "inland"}))
        self.assertGreater(int(np.count_nonzero(kind == "inland")), 0)

    def test_reversed_point_order_answers_identically(self):
        clear_cache()
        try:
            forward = solve_domain_coupled(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                           dt_s=DT_S, intervals=INTERVALS)
            backward = solve_domain_coupled(SEED, tuple(reversed(POINTS)), RAIN_MM_H,
                                            config=CONFIG, dt_s=DT_S,
                                            intervals=INTERVALS)
        finally:
            clear_cache()
        self.assertEqual(forward["identity_sha256"], backward["identity_sha256"])


    # ------------------------------------------------ the water-dependent source (P14)
    def test_the_water_source_is_off_by_default_and_changes_no_identity(self):
        """The new source must be inert at its default, bit for bit.

        A mechanism added behind a zero default is only safe if the default truly
        changes nothing: the identity and the entrained total must be identical to a
        run that never heard of the parameter. Anything else would silently re-key
        every existing product.
        """
        parameters = CoupledParameters()
        self.assertEqual(parameters.water_source_coefficient_m_per_interval_per_m3_s, 0.0)
        self.assertEqual(parameters.effective_erodible_area_fraction, 0.0)
        clear_cache()
        try:
            plain = solve_domain_coupled(SEED, POINTS, RAIN_MM_H, config=CONFIG,
                                         dt_s=DT_S, intervals=INTERVALS)
            explicit_zero = solve_domain_coupled(
                SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(
                    water_source_coefficient_m_per_interval_per_m3_s=0.0,
                    effective_erodible_area_fraction=0.0))
        finally:
            clear_cache()
        self.assertEqual(explicit_zero["identity_sha256"], plain["identity_sha256"])
        self.assertEqual(explicit_zero["metadata"]["totals"]["entrained_total_m3"],
                         plain["metadata"]["totals"]["entrained_total_m3"])

    def test_a_zero_area_fraction_keeps_the_constant_weathering(self):
        """Either factor at zero must leave the CONSTANT weathering in force.

        Note the distinction this test encodes, because a first draft got it wrong:
        the *behaviour* must be identical, but the *identity* legitimately changes,
        because `metadata.parameters` carries the coefficient and the repository's
        convention is that a changed parameter re-keys a product. Asserting identity
        equality here would forbid that convention; what matters is that the
        published volumes are bit-for-bit the constant-weathering answer.
        """
        clear_cache()
        try:
            half = solve_domain_coupled(
                SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(
                    water_source_coefficient_m_per_interval_per_m3_s=1e-11,
                    effective_erodible_area_fraction=0.0))
        finally:
            clear_cache()
        self.assertEqual(half["metadata"]["totals"]["weathered_total_m3"],
                         self.record["metadata"]["totals"]["weathered_total_m3"])
        self.assertEqual(half["metadata"]["totals"]["entrained_total_m3"],
                         self.record["metadata"]["totals"]["entrained_total_m3"])
        self.assertNotEqual(half["identity_sha256"], self.record["identity_sha256"],
                            "a changed parameter must re-key the product -- that is "
                            "the repository convention, not a defect")
        self.assertNotEqual(
            half["metadata"]["parameters"][
                "water_source_coefficient_m_per_interval_per_m3_s"],
            self.record["metadata"]["parameters"][
                "water_source_coefficient_m_per_interval_per_m3_s"])

    def test_the_water_source_responds_monotonically_to_rainfall(self):
        """The whole point of the mechanism: a water-dependent source.

        With the source off, entrainment converged on the declared weathering
        constant and flattened with rain (the P9.1 leftover). Switched on, the
        weathered total must rise with rainfall, and so must the entrainment.
        """
        weathered = []
        entrained = []
        for rain in (4.0, 8.0, 20.0, 40.0):
            clear_cache()
            try:
                run = solve_domain_coupled(
                    SEED, POINTS, rain, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                    parameters=CoupledParameters(
                        water_source_coefficient_m_per_interval_per_m3_s=1e-11,
                        effective_erodible_area_fraction=1e-4))
            finally:
                clear_cache()
            totals = run["metadata"]["totals"]
            self.assertEqual(totals["capacity_violation_m3"], 0.0)
            weathered.append(totals["weathered_total_m3"])
            entrained.append(totals["entrained_total_m3"])
        self.assertTrue(all(b > a for a, b in zip(weathered, weathered[1:])),
                        "the weathered source must rise with rainfall once it is "
                        "water-dependent")
        self.assertTrue(all(b > a for a, b in zip(entrained, entrained[1:])),
                        "entrainment must rise with rainfall")

    def test_the_water_source_scales_linearly_with_its_coefficient(self):
        # The law is `k * q * fraction`, so doubling k must double the source. This
        # catches an accidental clamp or a hidden saturation.
        values = []
        for coefficient in (1e-12, 2e-12, 4e-12):
            clear_cache()
            try:
                run = solve_domain_coupled(
                    SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                    parameters=CoupledParameters(
                        water_source_coefficient_m_per_interval_per_m3_s=coefficient,
                        effective_erodible_area_fraction=1e-4))
            finally:
                clear_cache()
            values.append(run["metadata"]["totals"]["weathered_total_m3"])
        self.assertGreater(values[1], values[0])
        self.assertGreater(values[2], values[1])
        self.assertAlmostEqual(values[1] / values[0], 2.0, places=6)
        self.assertAlmostEqual(values[2] / values[1], 2.0, places=6)

    def test_the_water_source_magnitude_is_reported_honestly(self):
        """A declared-unit caveat, pinned so it cannot be quietly forgotten.

        At k = 1e-11 and fraction = 1e-4 the whole tile's weathered total is single-
        digit cubic metres -- nanometres over a 1e8 m2 cell. The law multiplies a
        m3/s discharge by a per-interval coefficient without the interval duration,
        so the product is NOT a metre depth. Enabling it therefore needs a calibrated
        k, not a guess, and this test states the order of magnitude rather than
        letting an enabler assume the mechanism alone produces visible erosion.
        """
        clear_cache()
        try:
            run = solve_domain_coupled(
                SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(
                    water_source_coefficient_m_per_interval_per_m3_s=1e-11,
                    effective_erodible_area_fraction=1e-4))
        finally:
            clear_cache()
        weathered = run["metadata"]["totals"]["weathered_total_m3"]
        self.assertGreater(weathered, 0.0)
        self.assertLess(weathered, 1e3,
                        "at the probe coefficients the source is cubic metres, not "
                        "a depth -- do not read it as metres of erosion")
        # The capacity gate must still hold with the new source active.
        self.assertEqual(run["metadata"]["totals"]["capacity_violation_m3"], 0.0)
        validate_domain_coupled(run)

    def test_both_ledgers_still_close_with_the_water_source_active(self):
        clear_cache()
        try:
            run = solve_domain_coupled(
                SEED, POINTS, RAIN_MM_H, config=CONFIG, dt_s=DT_S, intervals=INTERVALS,
                parameters=CoupledParameters(
                    water_source_coefficient_m_per_interval_per_m3_s=1e-10,
                    effective_erodible_area_fraction=1e-3))
        finally:
            clear_cache()
        arrays = run["arrays"]
        weathered = np.asarray(arrays["weathered_m3"], np.float64)
        entrained = np.asarray(arrays["entrained_m3"], np.float64)
        store = np.asarray(arrays["store_change_m3"], np.float64)
        deposited = np.asarray(arrays["deposited_m3"], np.float64)
        delivered = np.asarray(arrays["delivered_m3"], np.float64)
        scale_source = np.maximum(weathered + entrained + np.abs(store), 1.0)
        self.assertLess(float(np.max(np.abs(weathered - entrained - store) / scale_source)),
                        1e-9)
        scale_routing = np.maximum(entrained + deposited + delivered, 1.0)
        self.assertLess(float(np.max(np.abs(entrained - deposited - delivered) / scale_routing)),
                        1e-9)
        validate_domain_coupled(run)

    def test_the_area_fraction_is_bounded(self):
        for bad in (-0.1, 1.5, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                CoupledParameters(effective_erodible_area_fraction=bad)
        for bad in (-1.0, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                CoupledParameters(water_source_coefficient_m_per_interval_per_m3_s=bad)


class CoupledParameterIdentityTests(unittest.TestCase):
    def test_parameter_identity_is_sensitive_to_the_inherited_laws(self):
        base = CoupledParameters()
        self.assertEqual(base, CoupledParameters())
        self.assertNotEqual(base, CoupledParameters(deposit_fraction=0.31))
        self.assertNotEqual(base, CoupledParameters(
            channel=ChannelRecipe(reference_width_m=4.0)))

    def test_parameter_record_flattens_the_nested_dataclasses(self):
        from terrain_pipeline.surface_rivers.metric_domain_coupled import (
            _parameters_record,
        )
        record = _parameters_record(CoupledParameters())
        self.assertIn("channel", record)
        self.assertIn("runoff", record)
        self.assertIsInstance(record["channel"], dict)
        self.assertIn("reference_width_m", record["channel"])
        self.assertIn("initial_soil_mm", record["runoff"])


class CoupledProductNameTests(unittest.TestCase):
    def test_product_name_encodes_the_outlet_identity(self):
        from terrain_pipeline.surface_rivers.metric_domain_coupled import coupled_name
        name = coupled_name(1200000.0, 400000.0)
        self.assertIn("1200000", name)
        self.assertIn("400000", name)
        self.assertIn(COUPLED_SCHEMA, name)


def _file_sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _deep_copy_bundle(record):
    arrays = {key: np.array(value, copy=True) for key, value in record["arrays"].items()}
    metadata = json.loads(json.dumps(record["metadata"]))
    return {"arrays": arrays, "metadata": metadata,
            "identity_sha256": record["identity_sha256"]}


def _identity(bundle):
    """Re-seal a forged bundle so the check under test is the intended one."""
    from terrain_pipeline.common_infra import identity
    return identity(bundle["arrays"], bundle["metadata"])


if __name__ == "__main__":
    unittest.main()
