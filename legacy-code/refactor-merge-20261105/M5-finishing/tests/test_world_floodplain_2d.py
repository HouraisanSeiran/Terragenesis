"""Behaviour tests for the two-dimensional floodplain adapter.

The tests are external-behaviour tests: water budget closure, non-negative depth,
no over-capacity residual after the flood recedes, and boundary handling. None of
them re-implements the frozen local-inertial solver; they drive it through the
adapter and check the guarantees the adapter claims.
"""
import unittest

import numpy as np

from terrain_pipeline.surface_hydraulics import SurfaceBudget
from terrain_pipeline.surface_hydraulics import CARVED_EPSILON_M, FloodplainWindow, aggregate_fine_field, boundary_cell_coordinates, boundary_cells, boundary_certificate, build_domain, cell_centres, crossing_edges, domain_ledger, extent_statistics, hydrograph, interval_forcing, residual_wetland, rim_outlet_cells, run_domain, source_locations, source_matrix, window_extent

FAST = SurfaceBudget(max_depth_m=40., max_snapshots=40, max_wall_s=120., max_dt_s=30.)


def tilted_page(rows=24, columns=24, spacing=60.):
    """A bowl with one low rim cell, so spilling is deterministic and inspectable."""
    ys, xs = np.mgrid[0:rows, 0:columns]
    height = 100. + .4 * (ys - rows / 2.) ** 2 * spacing / 60. \
        + .4 * (xs - columns / 2.) ** 2 * spacing / 60.
    return height.astype(np.float64)


def channel_mask(rows=24, columns=24, half=1):
    mask = np.zeros((rows, columns), bool)
    mask[:, columns // 2 - half:columns // 2 + half + 1] = True
    return mask


class AggregationTests(unittest.TestCase):
    def test_block_mean_reproduces_the_fine_page_when_block_is_one(self):
        page = np.arange(64., dtype=np.float64).reshape(8, 8)
        np.testing.assert_array_equal(aggregate_fine_field(page, 1), page)

    def test_block_mean_is_the_arithmetic_mean_not_the_minimum(self):
        page = np.array([[0., 2., 0., 0.],
                         [4., 6., 0., 0.],
                         [8., 10., 0., 0.],
                         [12., 14., 0., 0.]])
        out = aggregate_fine_field(page, 2)
        self.assertEqual(out.shape, (2, 2))
        np.testing.assert_allclose(out[:, 0], [(0. + 2. + 4. + 6.) / 4.,
                                              (8. + 10. + 12. + 14.) / 4.])
        # the block minimum would have been 0 and 8
        self.assertGreater(out[0, 0], 0.)

    def test_trailing_partial_block_is_dropped_not_padded(self):
        page = np.zeros((5, 7), np.float64)
        out = aggregate_fine_field(page, 2)
        self.assertEqual(out.shape, (2, 3))

    def test_non_finite_fine_field_is_refused(self):
        page = np.zeros((4, 4), np.float64)
        page[1, 1] = np.nan
        with self.assertRaises(ValueError):
            aggregate_fine_field(page, 2)

    def test_zero_block_is_refused(self):
        with self.assertRaises(ValueError):
            aggregate_fine_field(np.zeros((4, 4), np.float64), 0)


class WindowTests(unittest.TestCase):
    def test_cell_centres_sit_half_a_cell_inside_the_origin(self):
        window = FloodplainWindow((1000., 2000.), 30., 3)
        xs, zs = cell_centres(window, (2, 2))
        np.testing.assert_allclose(xs, [1000. + 45., 1000. + 135.])
        np.testing.assert_allclose(zs, [2000. + 45., 2000. + 135.])

    def test_extent_is_the_outer_edge_not_the_centre(self):
        window = FloodplainWindow((1000., 2000.), 30., 3)
        self.assertEqual(window_extent(window, (2, 3)),
                         (1000., 1000. + 3 * 90., 2000., 2000. + 2 * 90.))

    def test_bad_window_parameters_are_refused(self):
        with self.assertRaises(ValueError):
            FloodplainWindow((0., 0.), -1., 1).validate()
        with self.assertRaises(ValueError):
            FloodplainWindow((0., 0.), 30., 0).validate()


class CrossingTests(unittest.TestCase):
    def test_edge_leaving_the_window_is_found_at_the_boundary_plane(self):
        window = FloodplainWindow((0., 0.), 10., 1)
        shape = (10, 10)                                   # x and z both span 0..100 m
        nodes = np.array([[150., 50.], [50., 50.]])        # outside -> inside: still `inflow`
        found = crossing_edges(window, shape, nodes, np.array([1, -1]))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["donor"], 0)
        self.assertTrue(found[0]["inflow"])
        self.assertAlmostEqual(found[0]["point_m_xz"][0], 100.)

    def test_direction_of_travel_decides_the_inflow_flag(self):
        window = FloodplainWindow((0., 0.), 10., 1)
        shape = (10, 10)
        inward = crossing_edges(window, shape,
                                np.array([[150., 50.], [50., 50.]]), np.array([1, -1]))
        outward = crossing_edges(window, shape,
                                 np.array([[50., 50.], [150., 50.]]), np.array([1, -1]))
        self.assertTrue(inward[0]["inflow"])
        self.assertFalse(outward[0]["inflow"])

    def test_edges_wholly_inside_or_wholly_outside_do_not_cross(self):
        window = FloodplainWindow((0., 0.), 10., 1)
        shape = (10, 10)                                   # 0..100 m each way
        inside = np.array([[20., 20.], [80., 80.]])
        self.assertEqual(crossing_edges(window, shape, inside, np.array([1, -1])), [])
        outside = np.array([[300., 300.], [400., 400.]])
        self.assertEqual(crossing_edges(window, shape, outside, np.array([1, -1])), [])

    def test_terminal_node_without_receiver_is_ignored(self):
        window = FloodplainWindow((0., 0.), 10., 1)
        nodes = np.array([[50., 50.]])
        self.assertEqual(crossing_edges(window, (10, 10), nodes, np.array([-1])), [])


class SourceTests(unittest.TestCase):
    def window(self):
        return FloodplainWindow((0., 0.), 10., 1)

    def test_width_controls_how_many_boundary_cells_receive_water(self):
        crossing = {"donor": 0, "receiver": 1, "inflow": True, "axis": "x",
                    "side": "min", "point_m_xz": (0., 50.)}
        narrow = source_locations(self.window(), (10, 10), [crossing], np.array([20., 1.]))
        wide = source_locations(self.window(), (10, 10), [crossing], np.array([80., 1.]))
        self.assertLess(len(narrow[0]["cells"]), len(wide[0]["cells"]))
        for location in (narrow[0], wide[0]):
            self.assertAlmostEqual(float(location["weights"].sum()), 1.)

    def test_every_source_cell_is_on_the_declared_boundary(self):
        crossing = {"donor": 0, "receiver": 1, "inflow": True, "axis": "z",
                    "side": "max", "point_m_xz": (50., 100.)}
        location = source_locations(self.window(), (10, 10), [crossing], np.array([60., 1.]))[0]
        rows = [cell[0] for cell in location["cells"]]
        self.assertTrue(all(row == 9 for row in rows), rows)

    def test_source_matrix_is_row_stochastic_and_lands_each_volume_once(self):
        crossings = [
            {"donor": 0, "receiver": 1, "inflow": True, "axis": "x", "side": "min",
             "point_m_xz": (0., 30.)},
            {"donor": 1, "receiver": 2, "inflow": True, "axis": "z", "side": "max",
             "point_m_xz": (70., 100.)},
        ]
        locations = source_locations(self.window(), (10, 10), crossings,
                                     np.array([40., 40.]))
        matrix = source_matrix((10, 10), locations)
        np.testing.assert_allclose(matrix.sum(axis=1), np.ones(2))
        forcing = interval_forcing((10, 10), matrix, np.array([100., 300.]))
        self.assertAlmostEqual(float(forcing.sum()), 400.)

    def test_negative_discharge_is_refused_downstream(self):
        matrix = np.zeros((1, 4))
        matrix[0, 0] = 1.
        forcing = interval_forcing((2, 2), matrix, np.array([-1.]))
        self.assertLess(float(forcing.sum()), 0.)   # the adapter does not hide it
        with self.assertRaises(ValueError):
            hydrograph(np.array([[-1.]]), 3600.)


class BoundaryTests(unittest.TestCase):
    def test_rim_is_the_lowest_boundary_cell(self):
        height = tilted_page()
        height[-1, 5] = 90.                       # carve one low rim cell
        cells, rim, shares = rim_outlet_cells(height.shape, height, margin_cells=0)
        self.assertAlmostEqual(rim, 90.)
        self.assertIn((height.shape[0] - 1, 5), cells)
        self.assertEqual(shares, [])

    def test_rim_never_lands_on_an_injection_receptor(self):
        height = tilted_page()
        height[-1, 5] = 90.
        cells, rim, _ = rim_outlet_cells(height.shape, height, margin_cells=1,
                                         exclude={(height.shape[0] - 1, 5)})
        self.assertNotIn((height.shape[0] - 1, 5), cells)
        self.assertGreater(rim, 90.)

    def test_everything_else_is_closed_and_crests_are_the_ground(self):
        height = tilted_page()
        kinds, crests, exterior = boundary_certificate(height.shape, height,
                                                       outlet_cells=[(0, 0)])
        self.assertEqual(int((kinds == 0).sum()), exterior.size - 1)
        self.assertEqual(int((kinds == 1).sum()), 1)
        np.testing.assert_allclose(crests, height.ravel()[exterior])

    def test_outlet_off_the_boundary_is_refused(self):
        height = tilted_page()
        with self.assertRaises(ValueError):
            boundary_certificate(height.shape, height, outlet_cells=[(3, 3)])

    def test_boundary_coordinates_match_the_solver_ordering(self):
        shape = (4, 5)
        grid = np.arange(20).reshape(shape)
        self.assertTrue(np.array_equal(boundary_cells(shape),
                                       np.r_[grid[:, 0], grid[:, -1], grid[0], grid[-1]]))
        coordinates = boundary_cell_coordinates(shape)
        self.assertEqual(len(coordinates), boundary_cells(shape).size)
        for cell, flat in zip(coordinates, boundary_cells(shape)):
            self.assertEqual(cell[0] * shape[1] + cell[1], int(flat))


class DomainRunTests(unittest.TestCase):
    """End-to-end behaviour of the frozen solver driven through the adapter."""

    def build(self):
        height = tilted_page(rows=16, columns=16, spacing=60.)
        height[0, 0] = height.min() - 3.          # forced low rim so outflow is possible
        window = FloodplainWindow((0., 0.), 60., 1)
        domain = build_domain(window, height, source_identity="test", margin_cells=0)
        crossings = [{"donor": 0, "receiver": 1, "inflow": True, "axis": "x",
                      "side": "min", "point_m_xz": (0., 8 * 60. + 30.)}]
        locations = source_locations(window, height.shape, crossings, np.array([180.]))
        domain["source_matrix"] = source_matrix(height.shape, locations)
        return window, domain, height, crossings, locations

    def test_water_budget_closes_and_depth_stays_non_negative(self):
        window, domain, height, _, _ = self.build()
        rates = np.full((4, domain["source_matrix"].shape[0]), 25.)
        result = run_domain(domain, initial_depth_m=np.zeros(height.shape), interval_s=900.,
                            intervals=4, discharge_per_interval=rates,
                            source_identity="test", forcing_identity="f", budget=FAST,
                            snapshot_interval_s=900.)
        self.assertEqual(result["metadata"]["status"], "completed")
        depth = np.asarray(result["arrays"]["depth_m"], np.float64)
        self.assertGreaterEqual(float(depth.min()), 0.)
        ledger = domain_ledger(result, spacing_m=60., declared_injection_m3=float(rates.sum() * 900.))
        self.assertLess(abs(ledger["residual_m3"]), 1e-6 * max(ledger["initial_storage_m3"], 1.))
        self.assertTrue(ledger["injection_matches_source"])

    def test_no_boundary_face_draws_water_in(self):
        window, domain, height, _, _ = self.build()
        rates = np.full((4, domain["source_matrix"].shape[0]), 25.)
        result = run_domain(domain, initial_depth_m=np.zeros(height.shape), interval_s=900.,
                            intervals=4, discharge_per_interval=rates,
                            source_identity="test", forcing_identity="f", budget=FAST,
                            snapshot_interval_s=900.)
        self.assertEqual(float(result["metadata"]["boundary_input_m3"]), 0.)

    def test_residual_after_recession_cannot_exceed_what_was_supplied(self):
        window, domain, height, _, _ = self.build()
        rates = np.full((6, domain["source_matrix"].shape[0]), 20.)
        result = run_domain(domain, initial_depth_m=np.zeros(height.shape), interval_s=900.,
                            intervals=6, discharge_per_interval=rates,
                            source_identity="test", forcing_identity="f", budget=FAST,
                            snapshot_interval_s=900.)
        depth = np.asarray(result["arrays"]["depth_m"], np.float64)
        supplied = float(result["metadata"]["supplied_m3"])
        final_volume = float(depth[-1].sum() * 60. ** 2)
        self.assertLessEqual(final_volume, supplied * (1. + 1e-9))
        carved = channel_mask(*height.shape, half=0).astype(np.float64)
        residual = residual_wetland(depth[-1], spacing_m=60., carved_depth_m=carved)
        self.assertLessEqual(residual["residual_volume_m3"], supplied * (1. + 1e-9))

    def test_interval_count_mismatch_is_refused(self):
        window, domain, height, _, _ = self.build()
        rates = np.zeros((3, domain["source_matrix"].shape[0]))
        with self.assertRaises(ValueError):
            run_domain(domain, initial_depth_m=np.zeros(height.shape), interval_s=900.,
                       intervals=5, discharge_per_interval=rates, source_identity="test",
                       forcing_identity="f", budget=FAST)


class StatisticsTests(unittest.TestCase):
    def test_wet_area_uses_the_threshold_and_the_cell_area(self):
        depth = np.zeros((4, 4), np.float64)
        depth[0, 0] = .5
        depth[0, 1] = .005                    # below the default 2 cm threshold
        stats = extent_statistics(depth, spacing_m=10., carved_depth_m=np.zeros((4, 4)))
        self.assertEqual(stats["wet_cells"], 1)
        self.assertAlmostEqual(stats["wet_area_m2"], 100.)
        self.assertAlmostEqual(stats["max_depth_m"], .5)

    def test_overbank_area_excludes_the_carved_cross_section(self):
        depth = np.full((4, 4), 1., np.float64)
        carved = np.zeros((4, 4))
        carved[:, 1] = .4
        stats = extent_statistics(depth, spacing_m=10., carved_depth_m=carved)
        self.assertAlmostEqual(stats["channel_wet_area_m2"], 4 * 100.)
        self.assertAlmostEqual(stats["overbank_wet_area_m2"], 12 * 100.)

    def test_negative_depth_is_refused(self):
        depth = np.zeros((2, 2))
        depth[0, 0] = -1.
        with self.assertRaises(ValueError):
            extent_statistics(depth, spacing_m=10., carved_depth_m=np.zeros((2, 2)))

    def test_residual_wetland_only_counts_outside_the_carve(self):
        depth = np.zeros((4, 4), np.float64)
        depth[1, 1] = .5                       # inside the carve
        depth[2, 2] = .3                       # outside
        carved = np.zeros((4, 4))
        carved[1, 1] = .4
        residual = residual_wetland(depth, spacing_m=10., carved_depth_m=carved)
        self.assertEqual(residual["residual_cells"], 1)
        self.assertAlmostEqual(residual["residual_volume_m3"], .3 * 100.)


class HydrographTests(unittest.TestCase):
    def test_volume_is_converted_by_dividing_by_the_interval(self):
        rates = hydrograph(np.array([[7200.], [3600.]]), 3600.)
        np.testing.assert_allclose(rates[:, 0], [2., 1.])
        self.assertGreater(rates[0, 0], 0.)

    def test_wrong_rank_is_refused(self):
        with self.assertRaises(ValueError):
            hydrograph(np.array([1., 2.]), 3600.)


class ReachCouplingTests(unittest.TestCase):
    """The reach-side helpers the runner uses to build the injection hydrograph."""

    def test_substeps_are_binned_by_physical_time_not_by_step_count(self):
        from tools.run_floodplain_2d import aggregate_reach_outgoing

        # Sub-steps at 0 / 1200 / 3000 / 4200 s: the first three sit inside the first
        # hour, the last one inside the second hour.
        seconds = np.array([0., 1200., 3000., 4200.])
        outgoing = np.zeros((4, 2))
        outgoing[0, 0] = 10.
        outgoing[1, 0] = 20.
        outgoing[2, 0] = 30.
        outgoing[3, 1] = 40.
        volumes = aggregate_reach_outgoing(seconds, outgoing, [0, 1],
                                          interval_s=3600., intervals=3)
        np.testing.assert_allclose(volumes[:, 0], [60., 0., 0.])
        np.testing.assert_allclose(volumes[:, 1], [0., 40., 0.])
        # Binning must follow physical time, so the same transfers placed at different
        # sub-step counts give the same answer.
        dense = np.array([0., 300., 600., 900., 3000., 4200.])
        spread = np.zeros((6, 2))
        for row, value in zip((0, 1, 2, 4), (10., 20., 15., 15.)):
            spread[row, 0] = value
        spread[5, 1] = 40.
        same = aggregate_reach_outgoing(dense, spread, [0, 1], interval_s=3600., intervals=3)
        np.testing.assert_allclose(same, volumes)

    def test_negative_transfer_is_refused(self):
        from tools.run_floodplain_2d import aggregate_reach_outgoing

        outgoing = np.zeros((2, 1))
        outgoing[0, 0] = -1.
        with self.assertRaises(ValueError):
            aggregate_reach_outgoing(np.array([0., 100.]), outgoing, [0],
                                     interval_s=3600., intervals=1)


class MergedLedgerTests(unittest.TestCase):
    """The merge must not count the injected volume twice."""

    def test_injected_volume_is_an_internal_transfer_not_an_input_or_export(self):
        from tools.run_floodplain_2d import merged_ledger

        two_d = {"initial_storage_m3": 100., "injected_m3": 500.,
                 "boundary_input_m3": 0., "boundary_output_m3": 50.,
                 "final_storage_m3": 550.}
        sub = {"initial_storage_m3": 20., "local_input_m3": 600.,
               "boundary_input_m3": 0.,
               "export_to_two_dimensional_m3": 500., "final_storage_m3": 120.}
        merged = merged_ledger(two_d, sub, local_runoff_inside_domain_m3=7.)
        self.assertAlmostEqual(merged["input_m3"], 600.)      # not 600 + 500
        self.assertAlmostEqual(merged["export_m3"], 50.)      # not 50 + 500
        self.assertAlmostEqual(merged["initial_storage_m3"], 120.)
        self.assertAlmostEqual(merged["final_storage_m3"], 670.)
        self.assertAlmostEqual(merged["residual_m3"], 0.)
        self.assertAlmostEqual(merged["cancelled_internal_transfer_m3"], 500.)
        self.assertIn("local_runoff_on_two_dimensional_domain_m3",
                      merged["declared_out_of_scope"])

    def test_the_subledger_export_equals_the_two_dimensional_injection(self):
        from tools.run_floodplain_2d import merged_ledger

        two_d = {"initial_storage_m3": 0., "injected_m3": 123.5,
                 "boundary_input_m3": 0., "boundary_output_m3": 0.,
                 "final_storage_m3": 123.5}
        sub = {"initial_storage_m3": 0., "local_input_m3": 200.,
               "boundary_input_m3": 0.,
               "export_to_two_dimensional_m3": 123.5, "final_storage_m3": 76.5}
        merged = merged_ledger(two_d, sub, local_runoff_inside_domain_m3=0.)
        self.assertAlmostEqual(merged["cancelled_internal_transfer_m3"],
                               sub["export_to_two_dimensional_m3"])
        self.assertLess(abs(merged["residual_m3"]), 1e-9)

    def test_boundary_input_is_required_or_the_subledger_is_left_open(self):
        """The reach's declared truncated-upstream inflow must be counted.

        Dropping it left the real 72 h merged ledger open by 1.56e8 m3 (58 %), which
        this test pins so it cannot silently come back.
        """
        from tools.run_floodplain_2d import closed_reach_subledger

        intervals = 2
        node_volume = np.array([[10., 5.], [36010., 5.]])       # node 0 outside, 1 inside
        receiver = np.array([1, -1])
        outgoing = np.zeros((2, 2))                             # one substep per interval
        # The reach's own forcing packet is a discharge; the helper converts to volume
        # with the module's fixed interval, exactly as the runner does.
        products = {
            "water_volume_m3": node_volume,
            "receiver": receiver,
            "outgoing_volume_m3": outgoing,
            "local_bucket_q_m3_s": np.array([[1., 0.], [1., 0.]]),
            "boundary_q_m3_s": np.array([[4., 0.], [4., 0.]]),
        }
        sub = closed_reach_subledger(products, np.array([False, True]))
        interval = sub["interval_s"]
        self.assertAlmostEqual(sub["local_input_m3"], 2. * interval)
        self.assertAlmostEqual(sub["boundary_input_m3"], 8. * interval)
        self.assertLess(abs(sub["residual_m3"]), 1e-6)
        # Dropping the boundary term leaves exactly that term as the residual.
        without = dict(products, boundary_q_m3_s=np.zeros((2, 2)))
        leaky = closed_reach_subledger(without, np.array([False, True]))
        self.assertAlmostEqual(leaky["residual_m3"], 8. * interval)

    def test_subledger_reports_which_nodes_it_excluded(self):
        from tools.run_floodplain_2d import closed_reach_subledger

        products = {"water_volume_m3": np.array([[1., 2.], [1., 2.]]),
                    "receiver": np.array([1, -1]),
                    "outgoing_volume_m3": np.zeros((2, 2)),
                    "local_bucket_q_m3_s": np.zeros((2, 2)),
                    "boundary_q_m3_s": np.zeros((2, 2))}
        sub = closed_reach_subledger(products, np.array([False, True]))
        self.assertEqual(sub["excluded_nodes_inside_window"], [1])


if __name__ == "__main__":
    unittest.main()
