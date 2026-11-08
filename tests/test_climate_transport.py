"""Behaviour tests for the limited G4 vapour transport.

These are the **minimum** positive and negative cases the numeric definition calls
for. They test the contract, not a global model:

positive
  C1 single ridge    windward precipitation >= lee precipitation, and precipitation
                     never exceeds the vapour present
  C2 ridge train     run under the controlled steady-chain reading only: the vapour
                     available at the second ridge is not larger than at the first
  C0 flat            with the terrain term off, the terrain-attributed increment is
                     exactly zero (background condensation from the inventory is
                     allowed and is not forced to zero)
  ledger             the five-term identity closes on every case above

negative
  CFL over 1 is refused
  undeclared inflow is refused, never treated as zero
  explicit zero and closed no-flux are legitimate and distinguishable
  unknown boundary yields no certified zero flux
  a diagonal or non-axial wind is refused
  precipitation cannot exceed available vapour even for absurd gains
  ET volume conversion multiplies by density only; depth conversion is the only
  place area appears

No test needs a DEM, a network, a GPU or a compute slot.
"""

import unittest

import numpy as np

from terrain_pipeline.climate_forcing import CELL_AREA_M2, CELL_SPACING_M, CLOSED_NO_FLUX, EXPLICIT_ZERO, UNRESOLVED, WATER_DENSITY_KG_M3, depth_mm, et_volume_to_mass_kg, identity_of, climate_transport_step as transport_step


class BoundaryPropagationTests(unittest.TestCase):
    def test_upstream_pulse_crosses_all_cells_and_exits_in_each_axial_direction(self):
        for direction in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            with self.subTest(direction=direction):
                shape = (1, 5) if direction[0] else (5, 1)
                vapour = np.zeros(shape)
                precipitation = 0.
                exported = 0.
                entered = 0.
                for index in range(6):
                    result = transport_step(vapour, wind_bearing=direction,
                        wind_speed_m_s=1., dt_s=30., uplift_gain=0., gradient=np.zeros(shape),
                        inflow_kg=np.array([7. if index == 0 else 0.]))
                    vapour = result["vapour_kg"]
                    entered += result["ledger"]["inflow_kg"]
                    exported += result["ledger"]["outflow_kg"]
                    precipitation += result["ledger"]["precipitation_kg"]
                    self.assertTrue(result["ledger"]["closure_ok"])
                    self.assertAlmostEqual(entered, vapour.sum() + exported + precipitation)
                    if index < 5:
                        expected = np.zeros(shape)
                        position = index if sum(direction) == 1 else 4 - index
                        expected.ravel()[position] = 7.
                        np.testing.assert_array_equal(vapour, expected)
                self.assertEqual(vapour.sum(), 0.)
                self.assertEqual(exported, 7.)

DT_S = 900.0
SPEED_M_S = 0.033          # CFL = 0.033*900/30 = 0.99, just inside the limit
GAIN = 1.0e-4


def grid(rows=5, columns=6, mass_kg=1.0):
    return np.full((rows, columns), float(mass_kg), np.float64)


def flat_gradient(rows=5, columns=6):
    return np.zeros((rows, columns), np.float64)


def single_ridge(rows=5, columns=6, ridge_column=2, height=0.5):
    """Upslope before the ridge, downslope after it, flat on the far side."""
    slope = np.zeros((rows, columns), np.float64)
    for column in range(columns):
        if column < ridge_column:
            slope[:, column] = height
        elif column == ridge_column:
            slope[:, column] = -height
        else:
            slope[:, column] = 0.
    return slope


class RidgeCaseTests(unittest.TestCase):
    def test_c1_windward_precipitation_exceeds_lee(self):
        slope = single_ridge()
        result = transport_step(
            grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
            uplift_gain=GAIN, gradient=slope, boundary={"west": EXPLICIT_ZERO})
        precipitation = result["precipitation_kg"]
        windward = precipitation[:, :2].sum()
        lee = precipitation[:, 3:].sum()
        self.assertGreater(windward, lee)
        self.assertTrue(result["ledger"]["closure_ok"])

    def test_c1_precipitation_never_exceeds_the_vapour_present(self):
        slope = np.full((5, 6), 1.0e6, np.float64)   # absurd upslope everywhere
        initial = grid(mass_kg=1.0)
        result = transport_step(
            initial, wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
            uplift_gain=1.0e3, gradient=slope, boundary={"west": EXPLICIT_ZERO})
        self.assertTrue(np.all(result["precipitation_kg"] <= initial
                               + result["inflow_kg"] + result["recycle_kg"] + 1e-12))
        self.assertTrue(np.all(result["vapour_kg"] >= -1e-12))

    def test_c0_zero_terrain_gives_exactly_zero_terrain_increment(self):
        result = transport_step(
            grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
            uplift_gain=GAIN, gradient=flat_gradient(),
            boundary={"west": EXPLICIT_ZERO})
        self.assertEqual(float(result["precipitation_kg"].sum()), 0.0)
        self.assertTrue(result["ledger"]["closure_ok"])

    def test_c0_background_condensation_is_allowed_but_comes_from_the_inventory(self):
        """A uniform upslope everywhere is background condensation, not terrain gain."""
        uniform = np.full((5, 6), 0.1, np.float64)
        initial = grid(mass_kg=2.0)
        result = transport_step(
            initial, wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
            uplift_gain=GAIN, gradient=uniform, boundary={"west": EXPLICIT_ZERO})
        precipitated = float(result["precipitation_kg"].sum())
        self.assertGreater(precipitated, 0.0)
        # Drawn from the inventory, never invented.
        self.assertAlmostEqual(
            float(result["vapour_kg"].sum()),
            float(initial.sum()) - precipitated - result["ledger"]["outflow_kg"]
            + result["ledger"]["inflow_kg"] + result["ledger"]["recycle_kg"],
            places=9)

    def test_c2_controlled_chain_second_ridge_gets_no_extra_vapour(self):
        """Steady-chain reading: no inflow and no recycling along the path.

        Only the controlled comparison is asserted — the vapour arriving at the
        second ridge is not larger than what was available at the first. No claim is
        made about the total precipitation of a ridge train versus a single ridge.
        """
        # Two ridges in the same column sequence, duplicated later in the strip.
        columns = 12
        slope = np.zeros((3, columns), np.float64)
        for column in range(columns):
            if column in (1, 6):
                slope[:, column] = 0.5
            elif column in (2, 7):
                slope[:, column] = -0.5
        result = transport_step(
            grid(3, columns), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
            dt_s=DT_S, uplift_gain=GAIN, gradient=slope,
            boundary={"west": EXPLICIT_ZERO})
        vapour = result["vapour_kg"]
        # Available vapour at the second ridge column cannot exceed the first.
        self.assertTrue(np.all(vapour[:, 6] <= vapour[:, 2] + 1e-12))

    def test_multi_step_ledger_closes_every_step(self):
        state = grid()
        slope = single_ridge()
        for _ in range(5):
            result = transport_step(
                state, wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S, dt_s=DT_S,
                uplift_gain=GAIN, gradient=slope, boundary={"west": EXPLICIT_ZERO})
            self.assertTrue(result["ledger"]["closure_ok"],
                            result["ledger"]["closure_residual_kg"])
            state = result["vapour_kg"]


class BoundaryHonestyTests(unittest.TestCase):
    def test_undeclared_inflow_is_refused_not_zeroed(self):
        with self.assertRaises(ValueError) as caught:
            transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                           dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient())
        self.assertIn("never treated as zero", str(caught.exception))

    def test_explicit_zero_and_closed_are_distinguishable(self):
        zero = transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                              dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(),
                              boundary={"west": EXPLICIT_ZERO})
        closed = transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                                dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(),
                                boundary={"west": CLOSED_NO_FLUX})
        self.assertEqual(zero["boundary"]["declaration"], EXPLICIT_ZERO)
        self.assertEqual(closed["boundary"]["declaration"], CLOSED_NO_FLUX)
        self.assertNotEqual(zero["boundary"]["status_per_inflow_cell"],
                            closed["boundary"]["status_per_inflow_cell"])

    def test_unknown_boundary_is_not_certified(self):
        result = transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                                dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(),
                                boundary={"west": UNRESOLVED})
        self.assertFalse(result["boundary"]["certified"])

    def test_declared_inflow_is_booked_as_inflow(self):
        rows, columns = 3, 4
        result = transport_step(
            grid(rows, columns), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
            dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(rows, columns),
            inflow_kg=np.full(rows, 0.25))
        self.assertAlmostEqual(result["ledger"]["inflow_kg"], rows * 0.25, places=12)
        self.assertEqual(result["boundary"]["declaration"], "declared_influx")
        self.assertTrue(result["ledger"]["closure_ok"])

    def test_unsupported_boundary_side_is_rejected(self):
        with self.assertRaises(ValueError):
            transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                           dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(),
                           boundary={"upstream": EXPLICIT_ZERO})


class LimitTests(unittest.TestCase):
    def test_cfl_above_one_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=10.0,
                           dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(),
                           boundary={"west": EXPLICIT_ZERO})
        self.assertIn("CFL", str(caught.exception))

    def test_diagonal_wind_is_refused(self):
        with self.assertRaises(ValueError):
            transport_step(grid(), wind_bearing=(1, 1), wind_speed_m_s=SPEED_M_S,
                           dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(),
                           boundary={"west": EXPLICIT_ZERO})

    def test_negative_state_and_gradient_mismatch_are_refused(self):
        bad = grid()
        bad[0, 0] = -1.
        with self.assertRaises(ValueError):
            transport_step(bad, wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                           dt_s=DT_S, uplift_gain=GAIN, gradient=flat_gradient(),
                           boundary={"west": EXPLICIT_ZERO})
        with self.assertRaises(ValueError):
            transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                           dt_s=DT_S, uplift_gain=GAIN,
                           gradient=np.zeros((2, 2), np.float64),
                           boundary={"west": EXPLICIT_ZERO})


class UnitTests(unittest.TestCase):
    def test_et_volume_converts_by_density_only(self):
        volume = np.array([1.0, 2.0])
        mass = et_volume_to_mass_kg(volume)
        np.testing.assert_allclose(mass, volume * WATER_DENSITY_KG_M3)
        # Dividing by area would have produced kg/m², not kg.
        self.assertFalse(np.allclose(mass, volume * WATER_DENSITY_KG_M3 / CELL_AREA_M2))

    def test_depth_is_the_only_place_area_appears(self):
        mass = np.array([1.0])
        expected_mm = 1.0 / CELL_AREA_M2 / WATER_DENSITY_KG_M3 * 1000.0
        np.testing.assert_allclose(depth_mm(mass), [expected_mm])

    def test_cell_geometry_is_declared(self):
        self.assertEqual(CELL_SPACING_M, 30.0)
        self.assertEqual(CELL_AREA_M2, 900.0)

    def test_one_cell_mass_round_trips_through_depth(self):
        mass = CELL_AREA_M2 * WATER_DENSITY_KG_M3 * 0.001   # 1 mm over one cell
        self.assertAlmostEqual(float(depth_mm(mass).item()), 1.0, places=12)


class IdentityTests(unittest.TestCase):
    def test_identity_changes_with_the_result(self):
        slope = single_ridge()
        low = transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                             dt_s=DT_S, uplift_gain=GAIN, gradient=slope,
                             boundary={"west": EXPLICIT_ZERO})
        high = transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                              dt_s=DT_S, uplift_gain=GAIN * 2., gradient=slope,
                              boundary={"west": EXPLICIT_ZERO})
        self.assertNotEqual(identity_of(low), identity_of(high))

    def test_identity_is_stable_for_the_same_inputs(self):
        slope = single_ridge()
        first = transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                               dt_s=DT_S, uplift_gain=GAIN, gradient=slope,
                               boundary={"west": EXPLICIT_ZERO})
        second = transport_step(grid(), wind_bearing=(1, 0), wind_speed_m_s=SPEED_M_S,
                                dt_s=DT_S, uplift_gain=GAIN, gradient=slope,
                                boundary={"west": EXPLICIT_ZERO})
        self.assertEqual(identity_of(first), identity_of(second))


if __name__ == "__main__":
    unittest.main()
