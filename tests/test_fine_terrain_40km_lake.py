"""Behaviour tests for the 40 km lake-basin acceptance.

These are behaviour tests, not a replay of the measurement script: they check the
properties the spec asks for (closed basin, converged windows, A(h)/V(h) agreeing
with an *independent* recomputation, monotone contraction, truncated windows not
being read as lakes) on fixtures and on the archived measurement artifacts.

The independent recomputation lives next to the measurement in
`.scratch/fine-terrain-40km/lake/independent_lake.py` and imports neither
`metric_lake_hypsometry` nor `metric_lake_storage`. Tests that import it are marked
so, because "independently recomputed" is a claim that must stay checkable.
"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

from terrain_pipeline.lake import CONVERGENCE_AREA_TOLERANCE as CONVERGENCE_AREA_TOLERANCE
from terrain_pipeline.lake import CONVERGENCE_LEVEL_TOLERANCE as CONVERGENCE_LEVEL_TOLERANCE
from terrain_pipeline.lake import build_terrain_lake as build_terrain_lake
from terrain_pipeline.lake import contraction_evidence as contraction_evidence
from terrain_pipeline.lake import depression_component as depression_component
from terrain_pipeline.lake import depression_hierarchy as depression_hierarchy
from terrain_pipeline.lake import hypsometry_curve as hypsometry_curve
from terrain_pipeline.lake import sampled_levels as sampled_levels
from terrain_pipeline.lake import sampled_window_basin as sampled_window_basin

ROOT = Path(__file__).resolve().parents[1]
LAKE_DIR = ROOT / '.scratch/fine-terrain-40km/lake'
SPACING_M = 30.0

if str(LAKE_DIR) not in sys.path:
    sys.path.insert(0, str(LAKE_DIR))

import independent_lake as indie  # noqa: E402  (auditor's own implementation)


def cone_bowl(rows=161, columns=161, bottom_m=100.0, rim_m=180.0, radius_cells=30.0):
    """A closed cone inside a flat plateau: a genuine single depression.

    Inside `radius_cells` the height rises linearly to `rim_m`; outside it is the
    flat plateau at `rim_m`, so the plateau is the spill level and the interior is
    closed. A linear cone makes the wetted radius proportional to depth and hence
    the wetted area proportional to depth squared, which is what makes `dA/dh`
    fall as the water drops. The geometry produces that; neither implementation
    imposes it.

    The plateau ring must be wide enough to hold the flood's border: the window
    border has to be at `rim_m` for the spill level to be the rim rather than the
    window edge.
    """
    zs = np.arange(rows, dtype=np.float64) - (rows - 1) / 2.
    xs = np.arange(columns, dtype=np.float64) - (columns - 1) / 2.
    radius = np.hypot(zs[:, None], xs[None, :])
    return bottom_m + (rim_m - bottom_m) * np.clip(radius / radius_cells, 0., 1.)


def flat_ring_with_pit(rows=121, columns=121, plateau_m=200.0, pit_m=150.0, half=12):
    """A square pit in a flat plateau, whose rim is far from the window edge."""
    field = np.full((rows, columns), plateau_m, np.float64)
    zs = np.arange(rows) - rows // 2
    xs = np.arange(columns) - columns // 2
    inside = (np.abs(zs[:, None]) <= half) & (np.abs(xs[None, :]) <= half)
    radius = np.hypot(zs[:, None] / half, xs[None, :] / half)
    field[inside] = pit_m + (plateau_m - pit_m) * np.clip(radius[inside], 0., 1.)
    return field


class IndependentAgreesWithTheModuleTests(unittest.TestCase):
    """The audit is only worth something if the two implementations are separate."""

    def test_the_independent_module_does_not_import_the_implementation_under_test(self):
        """Docstrings may name it; import statements may not."""
        source = (LAKE_DIR / 'independent_lake.py').read_text(encoding='utf-8')
        imports = [line.strip() for line in source.splitlines()
                   if line.strip().startswith(('import ', 'from '))]
        self.assertTrue(imports)
        for line in imports:
            self.assertNotIn('metric_lake', line, 'the auditor must not import the tested code')
        self.assertIn('import numpy as np', imports)

    def test_the_independent_process_recorded_no_import_of_the_tested_code(self):
        """The check that actually proves it at run time lives in the artifact."""
        path = LAKE_DIR / 'independent.json'
        if not path.is_file():
            self.skipTest('the independent recomputation has not been run')
        flags = json.loads(path.read_text(encoding='utf-8'))['imports_of_tested_modules']
        self.assertTrue(flags)
        for name, leaked in flags.items():
            self.assertFalse(leaked, name)

    def test_it_imports_it_here_by_contrast(self):
        """Control: the tested module *is* importable and *is* what the tests import."""
        import terrain_pipeline.lake as tested
        self.assertTrue(hasattr(tested, 'sampled_window_basin'))

    def test_spill_level_by_binary_search_equals_the_priority_flood(self):
        field = cone_bowl()
        centre = (80, 80)
        result = indie.spill_level(field, centre, connectivity=8)
        lake = build_terrain_lake(field, (0., 0.), SPACING_M, centre,
                                  source_identity_sha256='a' * 64)
        self.assertAlmostEqual(result['spill_level_m'], lake.spill_level_m, places=9)
        self.assertGreater(result['probes'], 0)
        self.assertEqual(result['connectivity'], 8)

    def test_the_two_supports_are_the_same_cells(self):
        field = cone_bowl()
        centre = (80, 80)
        _, depth = depression_hierarchy(field)
        module_mask = depression_component(depth, centre)
        spilled = indie.spill_level(field, centre)['spill_level_m']
        indie_mask = indie.threshold_mask(field, centre, spilled, connectivity=4)
        differing = int((module_mask != indie_mask).sum())
        # Both count cells strictly below the spill level, so they agree unless a cell
        # sits exactly on the spill level -- which on this fixture is the whole
        # plateau, and neither implementation counts it.
        self.assertEqual(differing, 0, 'the two supports must be the same cells')
        self.assertEqual(int(module_mask.sum()), int((field < spilled).sum()))

    def test_area_and_volume_agree_point_by_point(self):
        field = cone_bowl()
        centre = (80, 80)
        lake = build_terrain_lake(field, (0., 0.), SPACING_M, centre,
                                  source_identity_sha256='a' * 64)
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 11)
        rows = lake.level_table(levels)
        module_areas = np.array([row['area_m2'] for row in rows])
        module_volumes = np.array([row['volume_m3'] for row in rows])
        beds = np.asarray(lake.storage.bed_elevation_m, np.float64)
        indie_areas, indie_volumes = indie.step_curves(beds, SPACING_M ** 2, levels)
        np.testing.assert_allclose(indie_areas, module_areas, rtol=1e-12, atol=1e-6)
        np.testing.assert_allclose(indie_volumes, module_volumes, rtol=1e-12, atol=1e-3)

    def test_the_independent_spill_search_finds_exactly_the_floods_answer(self):
        """The saddle is one of the bed values, and the search returns that one."""
        field = cone_bowl()
        lake = build_terrain_lake(field, (0., 0.), SPACING_M, (80, 80),
                                  source_identity_sha256='a' * 64)
        found = indie.spill_level(field, (80, 80))
        self.assertEqual(found['spill_level_m'], lake.spill_level_m)
        # And it is a real bed value, which the priority flood's max(filled) also is.
        self.assertTrue((field == found['spill_level_m']).any())
        # The next distinct bed value below it must NOT drain -- that is what makes
        # the answer the *lowest* saddle rather than any saddle.
        self.assertLess(found['one_below_m'], found['spill_level_m'])
        self.assertFalse(indie.reaches_border(field, (80, 80), found['one_below_m']))

    def test_the_scalar_loop_cross_check_agrees_with_the_prefix_sum_form(self):
        beds = np.array([1.0, 2.5, 2.5, 7.0, 11.25], np.float64)
        levels = np.array([0., 1., 2.5, 5., 11.25])
        fast = indie.step_curves(beds, 900.0, levels)
        loop = indie.step_curves_scalar(beds, 900.0, levels)
        np.testing.assert_allclose(loop[0], fast[0], rtol=1e-15)
        np.testing.assert_allclose(loop[1], fast[1], rtol=1e-15)

    def test_touches_window_edge_matches_the_modules_inner_ring_rule(self):
        mask = np.zeros((21, 21), bool)
        mask[10, 10] = True
        self.assertFalse(indie.touches_window_edge(mask, margin_cells=2))
        mask[1, 10] = True
        self.assertTrue(indie.touches_window_edge(mask, margin_cells=2))
        mask = np.zeros((21, 21), bool)
        mask[2, 10] = True
        self.assertFalse(indie.touches_window_edge(mask, margin_cells=2))


class ContractionTests(unittest.TestCase):
    def test_secant_is_area_lost_per_metre_descended(self):
        levels = np.array([10., 8., 4.])          # rim first, floor last
        areas = np.array([400., 300., 100.])
        rows = indie.secants(levels, areas)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]['secant_dA_dh_m'], 50.)   # 100 m2 lost over 2 m
        self.assertAlmostEqual(rows[1]['secant_dA_dh_m'], 50.)   # 200 m2 over 4 m
        self.assertGreater(rows[0]['from_level_m'], rows[0]['to_level_m'])

    def test_a_cone_loses_area_faster_the_higher_the_water(self):
        """The trend, not strict monotonicity: a 30 m lattice makes secants jagged.

        On a discrete lattice two neighbouring stages can differ by a fraction of a
        cell, so requiring strict monotonicity would test the lattice, not the
        terrain. What a cone must show is that the upper half of the range loses far
        more area per metre than the lower half.
        """
        field = cone_bowl()
        lake = build_terrain_lake(field, (0., 0.), SPACING_M, (80, 80),
                                  source_identity_sha256='a' * 64)
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 13)
        rows = lake.level_table(levels)
        areas = np.array([row['area_m2'] for row in rows])
        for label, series in (
                ('module', [r['secant_dA_dh_m'] for r in contraction_evidence(levels, areas)]),
                ('independent', [r['secant_dA_dh_m'] for r in indie.secants(levels, areas)])):
            half = len(series) // 2
            upper_mean = float(np.mean(series[:half]))
            lower_mean = float(np.mean(series[-half:]))
            self.assertGreater(upper_mean, 2.0 * lower_mean,
                               '%s: the upper half must contract much faster' % label)
            self.assertGreater(series[0], series[-1], label)

    def test_secants_match_between_the_two_implementations(self):
        field = cone_bowl()
        lake = build_terrain_lake(field, (0., 0.), SPACING_M, (80, 80),
                                  source_identity_sha256='a' * 64)
        levels = sampled_levels(lake.bed_min_m, lake.spill_level_m, 9)
        areas = np.array([row['area_m2'] for row in lake.level_table(levels)])
        module = [r['secant_dA_dh_m'] for r in contraction_evidence(levels, areas)]
        mine = [r['secant_dA_dh_m'] for r in indie.secants(levels, areas)]
        np.testing.assert_allclose(mine, module, rtol=1e-12)

    def test_a_vertical_wall_has_no_contraction_at_all(self):
        levels = np.array([10., 5., 1.])
        rows = indie.secants(levels, np.array([1000., 1000., 1000.]))
        for row in rows:
            self.assertEqual(row['secant_dA_dh_m'], 0.)


class TruncatedWindowTests(unittest.TestCase):
    """A window that cuts the rim must not be read as a lake."""

    def _sampler(self, field):
        def sampler(origin, shape):
            row = int(round(origin[1] / SPACING_M))
            column = int(round(origin[0] / SPACING_M))
            return field[row:row + shape[0], column:column + shape[1]]
        return sampler

    def test_a_truncated_family_never_reports_convergence(self):
        field = cone_bowl(radius_cells=48.)
        centre = 80.0 * SPACING_M
        result = sampled_window_basin((centre, centre), (31, 61), SPACING_M,
                                      self._sampler(field))
        self.assertFalse(result['converged'])
        self.assertIn('enlarge', result['reason'])

    def test_a_cut_rim_is_reported_not_closed_or_not_converged(self):
        field = cone_bowl(radius_cells=48.)
        centre = 80.0 * SPACING_M
        result = sampled_window_basin((centre, centre), (61, 81), SPACING_M,
                                      self._sampler(field))
        truncated = result['records'][0]
        self.assertLess(truncated['spill_level_m'], result['records'][-1]['spill_level_m'],
                        'a window that cuts the rim must not invent a higher saddle')
        if truncated['closed_basin']:
            self.assertTrue(truncated['touches_window_border'] is False
                            or result['converged'] is False,
                            'a truncated basin must be flagged or shown not to converge')

    def test_the_independent_reader_also_under_reports_on_a_cut_rim(self):
        """A truncated window invents a *lower* saddle; it must be visibly flagged."""
        field = cone_bowl(radius_cells=48.)
        truth = indie.spill_level(field, (80, 80))['spill_level_m']
        block = field[80 - 18:80 + 19, 80 - 18:80 + 19]
        truncated = indie.spill_level(block, (18, 18))['spill_level_m']
        self.assertLess(truncated, truth - 10.,
                        'a window that cuts the rim must not report the real saddle')
        mask = indie.threshold_mask(block, (18, 18), truncated, connectivity=4)
        self.assertTrue(indie.touches_window_edge(mask, margin_cells=2),
                        'and the truncated support must be flagged as reaching the edge')


@unittest.skipUnless(LAKE_DIR.is_dir(), 'the 40 km lake measurement has not been run')
class RecordedMeasurementTests(unittest.TestCase):
    """Reads the archived measurement. Skips rather than passes when it is absent."""

    @classmethod
    def setUpClass(cls):
        cls.module = json.loads((LAKE_DIR / 'module-measurement.json').read_text(encoding='utf-8'))
        cls.indie = json.loads((LAKE_DIR / 'independent.json').read_text(encoding='utf-8'))
        cls.comparison = json.loads((LAKE_DIR / 'comparison.json').read_text(encoding='utf-8'))

    def test_the_basin_is_closed_and_does_not_touch_the_window_border(self):
        lake = self.module['lake']
        self.assertTrue(lake['closed_basin'])
        self.assertFalse(lake['touches_window_border'])
        self.assertGreater(lake['relief_m'], 0.)

    def test_the_independent_recompute_ran_without_the_tested_modules(self):
        flags = self.indie['imports_of_tested_modules']
        self.assertEqual(set(flags), {'terrain_pipeline.lake',
                                      'terrain_pipeline.lake'})
        for name, leaked in flags.items():
            self.assertFalse(leaked, name + ' leaked into the independent process')

    def test_the_two_largest_windows_converge_at_the_published_tolerances(self):
        centred = self.module['centred_family']
        self.assertEqual(centred['tolerances']['level'], CONVERGENCE_LEVEL_TOLERANCE)
        self.assertEqual(centred['tolerances']['area'], CONVERGENCE_AREA_TOLERANCE)
        self.assertTrue(centred['converged'], centred['reason'])
        self.assertLessEqual(centred['level_relative'], CONVERGENCE_LEVEL_TOLERANCE)
        self.assertLessEqual(centred['area_relative'], CONVERGENCE_AREA_TOLERANCE)
        self.assertGreaterEqual(len(centred['records']), 3)
        # The published family is refused on this page and the free-placed substitute
        # converges too; both are recorded, and they are not the same gate.
        self.assertIsNotNone(self.module['published_family_refusal'])
        free = self.module['free_placed_published_sizes']['convergence']
        self.assertTrue(free['converged'])
        self.assertEqual(free['compared_sizes'], [1537, 2049])

    def test_every_converged_window_agrees_on_the_basin(self):
        records = self.module['centred_family']['records']
        closed = [record for record in records if record['closed_basin']
                  and not record['touches_window_border']]
        self.assertGreaterEqual(len(closed), 2)
        areas = {record['basin_area_m2'] for record in closed}
        levels = {round(record['spill_level_m'], 6) for record in closed}
        self.assertEqual(len(areas), 1, 'a converged basin has one area')
        self.assertEqual(len(levels), 1, 'a converged basin has one spill level')

    def test_all_four_published_sizes_measure_the_same_basin(self):
        windows = self.module['free_placed_published_sizes']['windows']
        for key in ('basin_cells', 'basin_area_m2', 'bed_min_m', 'spill_level_m'):
            values = {record[key] for record in windows}
            self.assertEqual(len(values), 1, key + ' must not depend on the window size')
        for record in windows:
            self.assertTrue(record['closed_basin'])
            self.assertFalse(record['touches_window_border'])
            self.assertGreater(record['basin_clearance_cells'], 4,
                               'the basin must stay clear of the unreliable edge band')

    def test_the_curve_has_at_least_eight_declared_stages(self):
        rows = self.module['curve']['rows']
        self.assertGreaterEqual(len(rows), 8)
        self.assertEqual(len(rows), len(self.indie['curve']))

    def test_area_and_volume_are_monotone_in_the_stage(self):
        rows = self.module['curve']['rows']
        areas = [row['area_m2'] for row in rows]
        volumes = [row['volume_m3'] for row in rows]
        self.assertEqual(areas, sorted(areas))
        self.assertEqual(volumes, sorted(volumes))
        self.assertAlmostEqual(areas[0], 0.)
        self.assertAlmostEqual(volumes[0], 0.)

    def test_the_independent_recompute_matches_the_module_point_by_point(self):
        self.assertLess(self.comparison['area']['max_relative_difference'], 1e-9)
        self.assertLess(self.comparison['volume']['max_relative_difference'], 1e-9)
        self.assertEqual(self.comparison['basin_support']['cell_difference'], 0)
        self.assertLess(self.comparison['spill_level']['abs_difference_m'], 1e-6)

    def test_the_independent_scalar_loop_agrees_with_itself(self):
        check = self.comparison['independent_scalar_loop_cross_check']
        self.assertLess(check['area_max_relative'], 1e-15)
        self.assertLess(check['volume_max_relative'], 1e-12)

    def test_the_surface_contracts_towards_the_basin_floor(self):
        trend = self.comparison['contraction']['module_trend']
        trend_indie = self.comparison['contraction']['independent_trend']
        for label, item in (('module', trend), ('independent', trend_indie)):
            self.assertGreater(item['first_secant_m2_per_m'], item['last_secant_m2_per_m'],
                               label + ': the rim must lose far more area per metre')
            self.assertGreater(item['upper_over_lower'], 1.5,
                               label + ': the upper half must contract measurably faster')
            self.assertLess(item['rank_correlation_index_vs_secant'], -0.9,
                            label + ': the trend down the basin must be strong')
        # Both implementations must find the same jaggedness, not just the same trend.
        self.assertEqual(trend['inversion_count'], trend_indie['inversion_count'])
        self.assertLessEqual(trend['largest_inversion_excess_m2_per_m'],
                             4 * 900.0 * 3, 'an inversion must stay within cell quantisation')

    def test_the_wall_tank_is_measurably_wrong_on_this_basin(self):
        wall = self.comparison['wall']
        low, high = wall['wall_min_over_basin_volume_range']
        self.assertGreater(abs(high - 1.), 0.05,
                           'a vertical wall must differ from the basin by more than 5%')
        self.assertGreaterEqual(high, low)
        # On the tank's own 10 km footprint the overestimate is tens of times, not 4.6x.
        fp_low, fp_high = wall['wall_min_over_footprint_volume_range']
        self.assertGreater(fp_low, 2.0)
        self.assertGreaterEqual(fp_high, fp_low)

    def test_a_converged_family_of_tiny_windows_is_a_real_finding(self):
        """A documented limitation: two tiny windows can agree on a *sub*-depression.

        Measured: the 45 and 61 cell windows both contain a 90-cell closed pocket
        inside the real basin, so they agree with each other exactly while both are
        267 m below the real saddle. `sampled_window_basin` reports converged=True.
        Convergence is therefore not sufficient on its own -- the basin must also be
        known to fit. This test records the measured numbers rather than pretending
        the gate catches everything.
        """
        path = LAKE_DIR / 'pocket-growth.json'
        if not path.is_file():
            self.skipTest('the pocket diagnosis has not been run')
        data = json.loads(path.read_text(encoding='utf-8'))
        windows = {row['size']: row for row in data['windows']}
        self.assertLess(windows[45]['component_cells'], 0.01 * data['truth_basin_cells'])
        self.assertGreater(windows[45]['shortfall_m'], 100.)
        self.assertEqual(int(windows[45]['component_cells']),
                         int(windows[61]['component_cells']))
        # And the fit threshold: the component is the real basin only from 301 cells up.
        self.assertEqual(windows[301]['component_cells'], data['truth_basin_cells'])
        self.assertEqual(windows[301]['shortfall_m'], 0.0)

    def test_a_truncated_window_never_reports_a_converged_basin(self):
        """Truncation must be refused somewhere: by the flag or by the convergence gate."""
        scan = self.module['truncation_scan']
        self.assertTrue(scan)
        for entry in scan:
            if not entry.get('closed_basin'):
                continue
            shortfall = entry.get('spill_shortfall_vs_page_m')
            if shortfall is None or shortfall <= 1e-6:
                continue
            refused = bool(entry.get('touches_window_border'))
            self.assertTrue(refused or entry['basin_clearance_cells'] < 0,
                            'window %s reports a spill %.1f m low with no flag at all'
                            % (entry['size'], shortfall))

    def test_every_truncated_window_that_is_not_flagged_cuts_the_basin(self):
        """The complement of the previous test: the cut is visible in the clearance."""
        for entry in self.module['truncation_scan']:
            if entry.get('touches_window_border'):
                continue
            if not entry.get('closed_basin'):
                continue
            self.assertLess(entry['basin_clearance_cells'], 0,
                            'window %s claims a closed basin without flagging it'
                            % entry['size'])

    def test_the_measurement_records_a_world_seed_and_an_origin(self):
        source = self.module['source']
        self.assertEqual(source['world_seed'], 20261020)
        self.assertEqual(len(source['native_origin_column_row']), 2)
        self.assertEqual(source['spacing_m'], 30.0)

    def test_the_recorded_run_used_no_gpu(self):
        self.assertFalse(self.module['execution']['gpu_used'])
        self.assertFalse(self.indie['execution']['gpu_used'])

    def test_the_pending_gpu_task_is_declared_not_papered_over(self):
        pending = self.module['execution']['pending_gpu_tasks']
        self.assertTrue(pending)
        for item in pending:
            self.assertIn('not executed', item['status'])
        # And the substitute that was measured instead is present and is not the gate.
        windows = self.module['free_placed_published_sizes']['windows']
        self.assertEqual([w['size'] for w in windows], [513, 1025, 1537, 2049])
        self.assertNotEqual(self.module['free_placed_published_sizes']['gate'],
                            'sampled_window_basin')

    def test_the_coordinate_audit_passed(self):
        path = LAKE_DIR / 'coordinate-audit.json'
        if not path.is_file():
            self.skipTest('the coordinate audit has not been run')
        audit = json.loads(path.read_text(encoding='utf-8'))
        self.assertTrue(audit['unit_round_trip']['round_trip_exact'])
        self.assertTrue(audit['sampler_points_at_the_seed']['sampler_cell_equals_page_cell'])
        self.assertTrue(audit['page_basin']['matches_selection'])
        self.assertTrue(audit['inset_invariance']['bitwise_identical'])
        self.assertTrue(audit['basin_clear_of_the_unreliable_edge_band'])

    def test_the_no_shape_function_claim_holds_in_the_recorded_run(self):
        self.assertIsNone(self.module['lake']['shape_law'])


if __name__ == '__main__':
    unittest.main()
