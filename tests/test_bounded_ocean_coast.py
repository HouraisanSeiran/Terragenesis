"""Behaviour tests for the bounded basin ocean core.

The four narrow points the review asked for, each with its own case:

1. the transported quantity is a per-step **volume in m³**, not a rate — a caller must
   not multiply by `dt` again;
2. the heat ledger is a **relative heat content** in `m³·°C` at a 0 °C reference, never
   joules; negative temperatures are legitimate and the tolerance uses `Σ|V·T|`;
3. `open` means **leaving the declared grid only**; a land coast is never a drain, and
   a basin separated by land stays closed;
4. the per-step gates hold: no cell goes negative, land stays exactly zero, CFL is
   refused above 1.

No test needs a DEM, a network, a GPU or a compute slot.
"""

import unittest

import numpy as np

from terrain_pipeline.environment_processes import CLOSED, LEDGER_RTOL, OPEN, SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K, ocean_coast_transport_step as transport_step, water_volume_m3

SPACING_M = 30.0
DT_S = 30.0
SPEED_M_S = 1.0          # CFL = 1.0*30/30 = 1.0, exactly at the bound
DEPTH_M = 20.0
TEMPERATURE_C = 10.0


def basin(rows=4, columns=6, depth=DEPTH_M, temperature=TEMPERATURE_C, land=None):
    """A full wet basin, optionally with land cells punched out."""
    wet = np.ones((rows, columns), bool)
    if land is not None:
        for row, column in land:
            wet[row, column] = False
    depth_m = np.where(wet, float(depth), 0.)
    volume = water_volume_m3(depth_m, wet, SPACING_M)
    temperature_c = np.where(wet, float(temperature), 0.)
    return volume, temperature_c, wet


class TransportedVolumeTests(unittest.TestCase):
    def test_reported_quantity_is_a_per_step_volume_not_a_rate(self):
        """The number already contains `dt`; dividing by dt yields a rate, the other way
        round would double-count time."""
        volume, temperature, wet = basin()
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        name = "transported_volume_m3"
        self.assertIn(name, result)
        # A cell's moved volume is speed*dt/dx of what it held: 1.0 of it at CFL 1.
        expected = volume[0, 0] * SPEED_M_S * DT_S / SPACING_M
        self.assertAlmostEqual(float(result[name][0, 0]), float(expected), places=9)
        # A rate would be that divided by dt, which is a different number.
        self.assertNotAlmostEqual(float(result[name][0, 0]),
                                  float(expected) / DT_S, places=3)

    def test_shared_face_moves_water_once(self):
        """One face value, applied with opposite signs: no water is invented."""
        volume, temperature, wet = basin()
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        ledger = result["ledger"]
        self.assertTrue(ledger["water_ok"], ledger["water_residual_m3"])

    def test_current_speed_is_labelled_a_declared_proxy_not_a_solved_stress(self):
        volume, temperature, wet = basin()
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        diagnostics = result["diagnostics"]
        self.assertFalse(diagnostics["wind_stress_solved"])
        self.assertIn("prescribed_current_speed_from_declared_wind_proxy_m_s",
                      diagnostics)


class HeatLedgerTests(unittest.TestCase):
    def test_heat_is_relative_m3_degc_not_joules(self):
        volume, temperature, wet = basin()
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        ledger = result["ledger"]
        for name in ("heat_start_m3_degc", "heat_end_m3_degc", "heat_change_m3_degc"):
            self.assertIn(name, ledger)
        self.assertIn("NOT joules", ledger["heat_reference"])
        # Joules would be the same number times rho*cp, which is a different figure.
        self.assertAlmostEqual(
            ledger["heat_energy_j_if_converted"],
            ledger["heat_end_m3_degc"] * SEAWATER_VOLUMETRIC_HEAT_CAPACITY_J_M3K,
            places=3)

    def test_negative_temperatures_are_legitimate(self):
        volume, _temperature, wet = basin(temperature=-3.0)
        result = transport_step(volume, -3.0 * np.ones_like(volume), wet,
                                wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                                dt_s=DT_S, spacing_m=SPACING_M)
        self.assertTrue(np.isfinite(result["temperature_c"]).all())
        self.assertTrue(result["ledger"]["heat_ok"])

    def test_heat_tolerance_uses_absolute_magnitude_not_signed_sum(self):
        """A basin straddling 0 degC must not get a tiny tolerance from cancellation."""
        rows, columns = 2, 4
        wet = np.ones((rows, columns), bool)
        depth_m = np.full((rows, columns), DEPTH_M)
        volume = water_volume_m3(depth_m, wet, SPACING_M)
        temperature = np.array([[5.0, 5.0, -5.0, -5.0], [5.0, 5.0, -5.0, -5.0]])
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        ledger = result["ledger"]

        # Recompute the expected tolerance independently: rtol * sum|V*T|.
        old_heat = volume * temperature
        magnitude_scale = max(float(np.abs(old_heat).sum()), 1.0)
        expected_tolerance = LEDGER_RTOL * magnitude_scale
        signed_scale = max(abs(float(old_heat.sum())), 1.0)
        signed_tolerance = LEDGER_RTOL * signed_scale

        # The signed total is exactly zero here, so the two schemes differ sharply:
        # the magnitude-based tolerance is the larger one, by the ratio of the scales.
        self.assertAlmostEqual(float(old_heat.sum()), 0.0, places=9)
        self.assertAlmostEqual(ledger["heat_tolerance_m3_degc"], expected_tolerance,
                               places=15)
        self.assertGreater(ledger["heat_tolerance_m3_degc"], signed_tolerance)
        # No absolute magnitude is asserted: the correct figure is whatever the real
        # magnitudes give, and inflating the model tolerance to clear a test is exactly
        # what must not happen.
        self.assertGreater(magnitude_scale, signed_scale)

    def test_heat_closes_with_the_water_account(self):
        volume, temperature, wet = basin(temperature=12.0)
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        ledger = result["ledger"]
        self.assertTrue(ledger["heat_ok"], ledger["heat_residual_m3_degc"])


class ShoreTests(unittest.TestCase):
    def test_land_is_never_an_open_drain(self):
        """A shore cell retains its water; it does not leak into the land cell."""
        rows, columns = 3, 3
        wet = np.ones((rows, columns), bool)
        wet[:, 2] = False                      # land on the east side
        depth_m = np.where(wet, DEPTH_M, 0.)
        volume = water_volume_m3(depth_m, wet, SPACING_M)
        temperature = np.where(wet, TEMPERATURE_C, 0.)
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M, boundary=OPEN)
        # Nothing leaves through the land coast. Column 0's downwind neighbour (column
        # 1) is land *inside* the grid, so it is neither a shared wet face nor an exit;
        # column 1's downwind neighbour (column 2) is land too, same reasoning. Only a
        # cell whose downwind neighbour is off-grid could exit, and there is none here.
        self.assertEqual(float(result["exit_volume_m3"].sum()), 0.0)
        # And the land column stays exactly zero.
        self.assertTrue(np.all(result["volume_m3"][:, 2] == 0.))

    def test_basin_separated_by_land_stays_closed(self):
        """Two wet lobes split by a land column never exchange water."""
        rows, columns = 3, 5
        wet = np.ones((rows, columns), bool)
        wet[:, 2] = False
        depth_m = np.where(wet, DEPTH_M, 0.)
        volume = water_volume_m3(depth_m, wet, SPACING_M)
        temperature = np.where(wet, TEMPERATURE_C, 0.)
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M, boundary=CLOSED)
        # CLOSED: no exits at all, so the western lobe keeps its water entirely.
        self.assertEqual(float(result["exit_volume_m3"].sum()), 0.0)
        west_before = float(volume[:, 0:2].sum())
        west_after = float(result["volume_m3"][:, 0:2].sum())
        self.assertAlmostEqual(west_after, west_before, places=6)

    def test_open_boundary_only_exits_off_grid(self):
        volume, temperature, wet = basin()
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M, boundary=OPEN)
        # With an eastward wind the exit column is the easternmost one.
        self.assertGreater(float(result["exit_volume_m3"][:, -1].sum()), 0.)
        self.assertEqual(float(result["exit_volume_m3"][:, :-1].sum()), 0.0)


class GateTests(unittest.TestCase):
    def test_no_cell_goes_negative(self):
        volume, temperature, wet = basin()
        for _ in range(10):
            result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                    wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                    spacing_m=SPACING_M)
            volume = result["volume_m3"]
            temperature = result["temperature_c"]
            self.assertTrue(np.all(volume >= 0.))

    def test_land_stays_exactly_zero(self):
        volume, temperature, wet = basin(land=[(0, 0), (1, 3)])
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        land = ~wet
        self.assertTrue(np.all(result["volume_m3"][land] == 0.))

    def test_cfl_above_one_is_refused(self):
        volume, temperature, wet = basin()
        with self.assertRaises(ValueError) as caught:
            transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                           wind_speed_m_s=2.0, dt_s=DT_S, spacing_m=SPACING_M)
        self.assertIn("CFL", str(caught.exception))

    def test_diagonal_wind_is_refused(self):
        volume, temperature, wet = basin()
        with self.assertRaises(ValueError):
            transport_step(volume, temperature, wet, wind_bearing=(1, 1),
                           wind_speed_m_s=SPEED_M_S, dt_s=DT_S, spacing_m=SPACING_M)

    def test_land_with_nonzero_volume_is_refused(self):
        volume, temperature, wet = basin(land=[(0, 0)])
        volume[0, 0] = 1.0
        with self.assertRaises(ValueError):
            transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                           wind_speed_m_s=SPEED_M_S, dt_s=DT_S, spacing_m=SPACING_M)


class DeclarationTests(unittest.TestCase):
    def test_salinity_is_declared_not_modelled(self):
        volume, temperature, wet = basin()
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        self.assertEqual(result["diagnostics"]["salinity"], "not_modelled")

    def test_declared_limits_refuse_a_global_ocean_claim(self):
        volume, temperature, wet = basin()
        result = transport_step(volume, temperature, wet, wind_bearing=(1, 0),
                                wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                                spacing_m=SPACING_M)
        joined = " ".join(result["declared_limits"]).lower()
        self.assertIn("not a global ocean", joined)
        self.assertIn("no salinity", joined)
        self.assertIn("diffusion", joined)


if __name__ == "__main__":
    unittest.main()
