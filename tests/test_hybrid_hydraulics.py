"""Consolidated test_hybrid_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
from dataclasses import replace as _i30_replace
import unittest as _i30_unittest
import numpy as _i30_np
from terrain_pipeline.hybrid_hydraulics import common_Experiment as _i30_Experiment
from terrain_pipeline.hybrid_hydraulics import common_Section as _i30_Section
from terrain_pipeline.hybrid_hydraulics import common_compare_refinement as _i30_compare_refinement
from terrain_pipeline.hybrid_hydraulics import common_signed_flow as _i30_signed_flow
from terrain_pipeline.hybrid_hydraulics import build_system as _i30_build_system
from builtins import ValueError as _i30_HydraulicDiagnosticStop
from terrain_pipeline.hybrid_hydraulics import local_experiment as _i30_local_experiment
from terrain_pipeline.hybrid_hydraulics import local_model as _i30_local_model
from terrain_pipeline.hybrid_hydraulics import numerical_frame as _i30_numerical_frame
from terrain_pipeline.hybrid_hydraulics import local_frame_run_experiment as _i30_run_experiment
from terrain_pipeline.hybrid_hydraulics import translate_section as _i30_translate_section
from terrain_pipeline.hybrid_hydraulics import accelerate_model as _i30_accelerate_model
from terrain_pipeline.hybrid_hydraulics import FastSection as _i30_FastSection
from tests.hybrid_hydraulics_fixtures import tiny_model as _i30_tiny_model
from tools.prepare_hybrid_hydraulics import ROOT as _i30_ROOT
from tools.prepare_hybrid_hydraulics import _x5_file_sha as _i30_file_sha
from tools.prepare_hybrid_hydraulics import _x10_paired_refinement as _i30_paired_refinement
from tools.prepare_hybrid_hydraulics import _x12_precision_experiments as _i30_precision_experiments
from tools.prepare_hybrid_hydraulics import source_identity as _i30_source_identity
import math as _i31_math
import tempfile as _i31_tempfile
from pathlib import Path as _i31_Path
import unittest as _i31_unittest
from terrain_pipeline.hybrid_hydraulics import common_Section as _i31_Section
from terrain_pipeline.hybrid_hydraulics import FastSection as _i31_FastSection
from tools.hybrid_hydraulics_records import atomic_save as _i31_atomic_save
CATEGORY = 'C'

class LocalVerticalFrameTests(_i30_unittest.TestCase):

    def test_synthetic_sections_storage_and_large_datum_flux_jacobian(self):
        sections = [_i30_Section.from_record(record) for record in ({'kind': 'open_polyline', 'sidewall_extension': 'explicit_engineering_vertical', 'polyline_transverse_elevation_m': [[-3, 1362.75], [-1, 1360.25], [1, 1360.25], [4, 1363.5]]}, {'kind': 'closed_polygon', 'pressure_slot_width_m': 0.02, 'polygon_transverse_elevation_m': [[-3, 1358.25], [3, 1358.25], [3.5, 1360.75], [-3.5, 1360.75]]})]
        datum = float(_i30_np.floor(min((section.floor_m for section in sections))))
        for section in sections:
            global_section = _i30_FastSection(section)
            translated = _i30_translate_section(section, datum)
            heads = [section.floor_m + 0.05, section.floor_m + 0.3]
            if section.crown_m is not None:
                heads.extend((section.crown_m, section.crown_m + 0.01, section.crown_m + 3))
            for head in heads:
                _i30_np.testing.assert_allclose(global_section.area_perimeter(head), translated.area_perimeter(head - datum), rtol=2e-11, atol=2e-11)
                area = global_section.area_perimeter(head)[0]
                self.assertAlmostEqual(translated.head_for_area(area) + datum, global_section.head_for_area(area), places=10)
        original = _i30_tiny_model()
        raised = _i30_replace(original, cells=tuple((_i30_replace(cell, section=_i30_translate_section(cell.section, -1350)) for cell in original.cells)))
        frame = _i30_numerical_frame(raised)
        lowered = _i30_local_model(raised, frame)
        parameters = _i30_Experiment('pulse', 2, 0.5, 0.05, 1350.15, (1350.3, 1350.23, 1350.18), (0, 1, 2))
        global_system = _i30_build_system(_i30_accelerate_model(raised), parameters, 0.02)
        local_system = _i30_build_system(lowered, _i30_local_experiment(parameters, frame), 0.02)
        state = local_system.initial_state.copy()
        state[:9] = (_i30_np.array([0.3, 0.4, 0.3])[:, None] * local_system.initial_volumes).ravel()
        _i30_np.testing.assert_allclose(global_system.rhs_for(0.05)(0, state), local_system.rhs_for(0.05)(0, state), rtol=2e-10, atol=2e-10)
        _i30_np.testing.assert_allclose(global_system.jacobian_for(0.05)(0, state), local_system.jacobian_for(0.05)(0, state), rtol=2e-10, atol=2e-10)
        local_head = lowered.cells[1].section.head_for_area(1.00000000000001)
        displaced = lowered.cells[1].section.head_for_area(1.00000000000002)
        self.assertNotEqual(displaced, local_head)
        self.assertNotEqual(_i30_signed_flow(500, displaced - local_head, 9, 0.0001), 0)
        current_code, historical_code = _i30_source_identity()
        for name, expected in current_code.items():
            self.assertEqual(_i30_file_sha(_i30_ROOT / name), expected, name)
        self.assertEqual(len(historical_code), 33)

    def test_two_second_pulse_reverse_refinement_and_failure_frames(self):
        original = _i30_tiny_model()
        model = _i30_replace(original, cells=tuple((_i30_replace(cell, section=_i30_translate_section(cell.section, -1350)) for cell in original.cells)))
        for scenario, tailwater in (('pulse', 1350.1), ('reverse_tailwater', 1350.4)):
            parameters = _i30_Experiment(scenario, 2, 0.5 if scenario == 'pulse' else 0, 0.05 if scenario == 'pulse' else 0, tailwater, (1350.2, 1350.2, 1350.2), (0, 0.5, 1, 2), max_step_s=0.2, source_arrival_threshold_m3=1e-08)
            base_parameters, refined_parameters = _i30_precision_experiments(parameters)
            base = _i30_run_experiment(model, base_parameters, 0.02)
            fine = _i30_run_experiment(model, refined_parameters, 0.02)
            self.assertEqual(_i30_compare_refinement(base, fine)['status'], 'passed')
            self.assertEqual(_i30_paired_refinement(base, fine)['status'], 'passed')
            origins = _i30_np.array([fine['untraced_water_volume_m3'], fine['source_tracer_mass_m3'], fine['tailwater_tracer_mass_m3']])
            self.assertTrue(_i30_np.all(origins >= 0))
            _i30_np.testing.assert_array_equal(origins.sum(axis=0), fine['water_volume_m3'])
            _i30_np.testing.assert_array_equal(_i30_np.array(fine['local_hydraulic_head_m']) + 1350, fine['hydraulic_head_m'])
            self.assertEqual(fine['local_tailwater_head_m'], tailwater - 1350)
            self.assertEqual(fine['work']['jacobian_rhs_evaluations'], 0)
            self.assertTrue(fine['source_reached_engineered_outlet'] if scenario == 'pulse' else fine['reverse_reached_sink'])
            with self.assertRaises(_i30_HydraulicDiagnosticStop) as stopped:
                _i30_run_experiment(model, base_parameters, 0.02, diagnostic_stop_s=0.5)
            progress = stopped.exception.progress
            self.assertEqual(progress['last_accepted_physical_time_s'], 0.5)
            self.assertGreater(progress['work']['rhs_evaluations'], 0)
            self.assertEqual(progress['numerical_frame'], _i30_numerical_frame(model))
            for cell in progress['last_accepted_inventory']['cells']:
                self.assertEqual(cell['head_m'], cell['local_head_m'] + 1350)
            self.assertEqual(progress['global_parameters']['tailwater_head_m'], tailwater)

class FastSectionTests(_i31_unittest.TestCase):

    def compare(self, record):
        original = _i31_Section.from_record(record)
        fast = _i31_FastSection(original)
        heads = [fast.floor_m - 0.25, fast.floor_m, fast.levels_m[-1] + 0.25, fast.levels_m[-1] + 3]
        for height in fast.levels_m:
            heads.extend((_i31_math.nextafter(height, -_i31_math.inf), height, _i31_math.nextafter(height, _i31_math.inf)))
        heads.extend((lower + (upper - lower) / 2 for lower, upper in zip(fast.levels_m[:-1], fast.levels_m[1:])))
        for head in heads:
            with self.subTest(kind=record['kind'], head=head):
                expected_area, expected_perimeter = original.area_perimeter(head)
                area, perimeter = fast.area_perimeter(head)
                self.assertAlmostEqual(area, expected_area, delta=1e-10)
                self.assertAlmostEqual(perimeter, expected_perimeter, delta=1e-09)
                self.assertAlmostEqual(area * 8.125, expected_area * 8.125, delta=1e-09)
                if area > 0:
                    self.assertAlmostEqual(fast.head_for_area(area), head, delta=1e-10)
                    self.assertAlmostEqual(fast.head_for_area(area), original.head_for_area(area), delta=2e-10)
        return fast

    def test_actual_linear_sections_breakpoints_pressure_and_open_bench(self):
        self.compare({'kind': 'open_polyline', 'polyline_transverse_elevation_m': [[-3.1160651283571497, 1367.680989361264], [-1.876967859454453, 1366.8883733087805], [0.0, 1366.626213114155], [1.876967859454453, 1366.5685119310874], [3.1160651283571497, 1367.1499686088753]], 'sidewall_extension': 'explicit_engineering_vertical'})
        closed = self.compare({'kind': 'closed_polygon', 'polygon_transverse_elevation_m': [[-3.1967823050840103, 1361.9088846317172], [-1.9354601538332739, 1361.1410485018523], [0.0, 1360.9324492759495], [1.9354601538332739, 1360.9335159861266], [3.1967823050840103, 1361.5633909417586], [3.25678230507099, 1363.8488846317173], [-3.25678230507099, 1363.8488846317173]], 'pressure_slot_width_m': 0.02})
        self.assertAlmostEqual(closed.area_perimeter(closed.crown_m + 1)[0] - closed.area_perimeter(closed.crown_m)[0], 0.02)
        for origin in (0.0, 1360.0):
            bench = self.compare({'kind': 'open_polyline', 'polyline_transverse_elevation_m': [[0, origin], [1, origin], [2, origin + 1], [3, origin + 1]], 'sidewall_extension': 'explicit_engineering_vertical'})
            self.assertAlmostEqual(bench.area_perimeter(origin + 0.5)[0], 0.625)
            self.assertAlmostEqual(bench.area_perimeter(origin + 1)[0], 1.5)
            self.assertAlmostEqual(bench.area_perimeter(origin + 1)[1], 2 + _i31_math.sqrt(2))
            self.assertAlmostEqual(bench.area_perimeter(_i31_math.nextafter(origin + 1, _i31_math.inf))[1], 3 + _i31_math.sqrt(2))

    def test_nonconvex_multispan_narrowing_fallback_invalid_and_checkpoint(self):
        shape = self.compare({'kind': 'closed_polygon', 'polygon_transverse_elevation_m': [[0, 0], [1, 0], [1, 2], [3, 2], [3, 0], [4, 0], [4, 4], [0, 4]], 'pressure_slot_width_m': 0.02})
        for head, area, perimeter in ((1, 2, 6), (2, 4, 12), (3, 8, 14), (4, 12, 20), (5, 12.02, 20)):
            self.assertAlmostEqual(shape.area_perimeter(head)[0], area)
            self.assertAlmostEqual(shape.area_perimeter(head)[1], perimeter)
        self.assertAlmostEqual(shape.area_perimeter(_i31_math.nextafter(2, -_i31_math.inf))[1], 10)
        self.assertAlmostEqual(shape.area_perimeter(_i31_math.nextafter(4, -_i31_math.inf))[1], 16)
        narrowing = self.compare({'kind': 'closed_polygon', 'polygon_transverse_elevation_m': [[0, 0], [4, 0], [3, 2], [1, 2]], 'pressure_slot_width_m': 0.02})
        self.assertAlmostEqual(narrowing.area_perimeter(1)[0], 3.5)
        self.assertAlmostEqual(narrowing.area_perimeter(1)[1], 4 + _i31_math.sqrt(5))
        original = _i31_Section.from_record({'kind': 'native_bed', 'pieces': [{'width_m': 2, 'bed_coefficients_m_t012': [1360, 0, 1]}], 'sidewall_extension': 'explicit_engineering_vertical'})
        fallback = _i31_FastSection(original)
        self.assertEqual(fallback.bands, ())
        self.assertEqual(fallback.area_perimeter(1360.5), original.area_perimeter(1360.5))
        self.assertEqual(fallback.head_for_area(0.25), original.head_for_area(0.25))
        for area in (-1e-16, 0, _i31_math.nan, _i31_math.inf):
            with self.assertRaises(ValueError):
                shape.head_for_area(area)
        with self.assertRaises(ValueError):
            shape.area_perimeter(_i31_math.nan)
        with self.assertRaises(ValueError):
            _i31_FastSection.from_record({'kind': 'closed_polygon', 'polygon_transverse_elevation_m': [[0, 0], [1, 1], [0, 1], [1, 0]], 'pressure_slot_width_m': 0.02})
        with _i31_tempfile.TemporaryDirectory() as temporary:
            output = _i31_Path(temporary)
            completed = _i31_atomic_save(output, 'pulse-base.json', {'status': 'diagnostic_completed', 'value': 1})
            before = (output / 'pulse-base.json').read_bytes()
            _i31_atomic_save(output, 'checkpoint.json', {'status': 'failed_partial', 'artifacts': {'pulse-base.json': completed}})
            self.assertEqual(before, (output / 'pulse-base.json').read_bytes())
            self.assertFalse(list(output.glob('*.tmp')))
