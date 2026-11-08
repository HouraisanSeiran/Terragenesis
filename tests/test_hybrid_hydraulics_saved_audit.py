"""Consolidated test_hybrid_hydraulics_saved_audit implementations; numeric expressions preserved."""
from __future__ import annotations
import copy as _i28_copy
import unittest as _i28_unittest
import numpy as _i28_np
from tools.audit_hybrid_hydraulics import accuracy_parameters as _i28_accuracy_parameters
from tools.audit_hybrid_hydraulics import check_accuracy_policy as _i28_check_accuracy_policy
from tools.audit_hybrid_hydraulics import check_three_origins as _i28_check_three_origins
from tools.audit_hybrid_hydraulics import compare_saved as _i28_compare_saved
from tools.audit_hybrid_hydraulics import physical_identity as _i28_physical_identity
from tools.audit_hybrid_hydraulics import section_area as _i28_section_area
from tools.audit_hybrid_hydraulics import section_friction as _i28_section_friction
import copy as _i29_copy
from dataclasses import asdict as _i29_asdict
from dataclasses import replace as _i29_replace
import json as _i29_json
import unittest as _i29_unittest
from tools.audit_hybrid_hydraulics import check_result as _i29_check_result
from tools.audit_hybrid_hydraulics import check_frame as _i29_check_frame
from tools.audit_hybrid_hydraulics import expected_frame as _i29_expected_frame
from tools.audit_hybrid_hydraulics import local_geometry as _i29_local_geometry
from tools.audit_hybrid_hydraulics import projected_result as _i29_projected_result
from tools.td_shared_channel_fine_saved_audit import digest as _i29_digest
CATEGORY = 'C'

class SavedHydraulicsAuditTests(_i28_unittest.TestCase):

    def test_bdf_precision_binding_preserves_forcing_and_rejects_looser_gate(self):
        from tools.hybrid_hydraulics_records import accuracy_policy
        original = {'max_step_s': 10.0, 'relative_tolerance': 1e-07, 'absolute_tolerance': 1e-09, 'duration_s': 900.0, 'pulse_q_m3_s': 6.0, 'max_rhs_evaluations': 200000}
        base = _i28_accuracy_parameters(original, 'base')
        refined = _i28_accuracy_parameters(original, 'refined')
        self.assertEqual(base['max_step_s'], 2.5)
        self.assertEqual(refined['max_step_s'], 1.25)
        for key in ('duration_s', 'pulse_q_m3_s', 'max_rhs_evaluations'):
            self.assertEqual(base[key], original[key])
            self.assertEqual(refined[key], original[key])
        model = {'model_version': 'fixture', 'model_parameters': {}, 'friction_policy': {}, 'inventory_policy': {}, 'forcing_configuration_pin': {}, 'graph_identity_sha256': 'graph', 'geometry_identity_sha256': 'geometry', 'integration': 'BDF', 'accuracy_policy': accuracy_policy()}
        model['physical_model_identity_sha256'] = _i28_physical_identity(model)
        index = {'integration': 'BDF', 'accuracy_policy': accuracy_policy(), 'reused_cases': {}, 'generated_cases': ['pulse-base'], 'completed_cases': ['pulse-base'], 'physical_model_identity_sha256': model['physical_model_identity_sha256']}
        _i28_check_accuracy_policy(index, model)
        index['accuracy_policy']['comparison_gates_unchanged']['volume_absolute_tolerance_m3'] = 0.001
        with self.assertRaisesRegex(ValueError, 'BDF accuracy policy'):
            _i28_check_accuracy_policy(index, model)

    def test_actual_open_closed_and_pressure_section_storage(self):
        surface = {'kind': 'open_polyline', 'polyline_transverse_elevation_m': [[-1, 100], [0, 99], [1, 100]]}
        self.assertAlmostEqual(_i28_section_area(surface, 99.5), 0.25)
        cave = {'kind': 'closed_polygon', 'polygon_transverse_elevation_m': [[-1, 99], [1, 99], [1, 101], [-1, 101]], 'pressure_slot_width_m': 0.02}
        self.assertAlmostEqual(_i28_section_area(cave, 100), 2)
        self.assertAlmostEqual(_i28_section_area(cave, 102), 4.02)
        cell = {'section': cave, 'roughness_manning': 0.03}
        actual = _i28_section_friction(cell, 101, 0.001)
        self.assertAlmostEqual(actual['actual_wetted_perimeter_m'], 8)
        self.assertAlmostEqual(actual['effective_friction_perimeter_m'], 6)
        self.assertAlmostEqual(_i28_section_friction(cell, 101.001, 0.001)['effective_friction_perimeter_m'], 8)

    def test_cold_refinement_rejects_hidden_internal_exchange_difference(self):
        base = {'cell_ids': ['first', 'second', 'third'], 'times_s': [0, 1], 'hydraulic_head_m': [[1, 1, 1], [1, 1, 1]], 'water_volume_m3': [[1, 1, 1], [1, 1, 1]], 'source_tracer_mass_m3': [[0, 0, 0], [0, 0, 0]], 'tailwater_tracer_mass_m3': [[0, 0, 0], [0, 0, 0]], 'boundary_ledger_m3': [[0] * 6, [0] * 6]}
        for key in ('paired_link_water_integral_m3', 'paired_link_source_integral_m3', 'paired_link_tailwater_integral_m3'):
            base[key] = [[0, 0], [1, 1]]
        _i28_compare_saved(base, _i28_copy.deepcopy(base))
        changed = _i28_copy.deepcopy(base)
        changed['paired_link_water_integral_m3'][1][0] = 2
        with self.assertRaisesRegex(ValueError, 'paired link refinement'):
            _i28_compare_saved(base, changed)
        diluted = _i28_copy.deepcopy(base)
        diluted['paired_link_water_integral_m3'][1] = [1000, 1000]
        changed = _i28_copy.deepcopy(diluted)
        changed['paired_link_water_integral_m3'][1][0] += 0.001
        with self.assertRaisesRegex(ValueError, 'paired link refinement'):
            _i28_compare_saved(diluted, changed)
        volumes = _i28_np.asarray([[3.0, 4.0, 5.0], [3.0, 4.0, 5.0]])
        origins = {'untraced_water_volume_m3': volumes.tolist(), 'outlet_untraced_out_m3': [0, 0]}
        for key in ('paired_link_water_integral_m3', 'paired_link_source_integral_m3', 'paired_link_tailwater_integral_m3', 'paired_link_untraced_integral_m3'):
            origins[key] = [[0, 0], [0, 0]]
        zeros = _i28_np.zeros_like(volumes)
        self.assertTrue(_i28_check_three_origins(origins, volumes, zeros, zeros, volumes[0], _i28_np.zeros((2, 6)))['three_origin_inventory_verified'])
        origins['untraced_water_volume_m3'][1][0] -= 0.01
        with self.assertRaisesRegex(ValueError, 'sum of its three'):
            _i28_check_three_origins(origins, volumes, zeros, zeros, volumes[0], _i28_np.zeros((2, 6)))

class LocalFrameSavedAuditTests(_i29_unittest.TestCase):

    def test_saved_two_second_projection_checks_actual_local_flux_and_inventory(self):
        from terrain_pipeline.hybrid_hydraulics import common_Experiment as Experiment
        from terrain_pipeline.hybrid_hydraulics import local_frame_run_experiment as run_experiment
        from terrain_pipeline.hybrid_hydraulics import translate_section
        from tests.hybrid_hydraulics_fixtures import tiny_model
        model = tiny_model()
        model = _i29_replace(model, cells=tuple((_i29_replace(cell, section=translate_section(cell.section, -1350)) for cell in model.cells)))
        geometry = {'hydraulic_cells': [], 'hydraulic_links': [_i29_asdict(link) for link in model.links]}
        for cell in model.cells:
            section = cell.section.original
            if section.kind == 'closed_polygon':
                saved_section = {'kind': 'closed_polygon', 'polygon_transverse_elevation_m': section.polygon, 'pressure_slot_width_m': section.pressure_slot_width_m}
            else:
                saved_section = {'kind': 'open_polyline', 'polyline_transverse_elevation_m': [[0, 1350], [1, 1350]]}
            geometry['hydraulic_cells'].append({'cell_id': cell.cell_id, 'kind': cell.kind, 'length_m': cell.length_m, 'roughness_manning': cell.roughness_manning, 'section': saved_section})
        experiment = Experiment('pulse', 2, 0.5, 0.05, 1350.1, (1350.2, 1350.2, 1350.2), (0, 0.5, 1, 2), max_step_s=0.05, source_arrival_threshold_m3=1e-08)
        record = run_experiment(model, experiment, 0.02)
        parameters = _i29_json.loads(_i29_json.dumps(_i29_asdict(experiment)))
        record['local_solver_parameters_identity_sha256'] = _i29_digest(record['local_solver_parameters'])
        record = _i29_json.loads(_i29_json.dumps(record))
        projected, local, local_parameters = _i29_projected_result(record, geometry, parameters)
        report = _i29_check_result(projected, local, local_parameters)
        self.assertLess(report['max_per_cell_water_residual_m3'], 1e-09)
        self.assertTrue(report['three_origin_inventory_verified'])
        wrong = _i29_copy.deepcopy(record)
        wrong['local_solver_parameters']['pulse_q_m3_s'] *= 2
        with self.assertRaisesRegex(ValueError, 'local solver parameters'):
            _i29_projected_result(wrong, geometry, parameters)

    def test_common_datum_and_global_output_binding_reject_inconsistent_frame(self):
        geometry = {'hydraulic_cells': [{'section': {'kind': 'open_polyline', 'polyline_transverse_elevation_m': [[-1, 1367], [0, 1366.5], [1, 1367]]}}]}
        original = _i29_copy.deepcopy(geometry)
        frame = _i29_expected_frame(geometry)
        self.assertEqual(frame['datum_m'], 1366)
        self.assertEqual(_i29_local_geometry(geometry, 1366)['hydraulic_cells'][0]['section']['polyline_transverse_elevation_m'], [[-1, 1], [0, 0.5], [1, 1]])
        self.assertEqual(geometry, original)
        record = {'times_s': [0, 1], 'hydraulic_head_m': [[1366.75], [1366.875]], 'local_hydraulic_head_m': [[0.75], [0.875]], 'numerical_frame': frame, 'local_tailwater_head_m': 0.9, 'execution_progress': {'numerical_frame': frame}}
        parameters = {'tailwater_head_m': 1366.9}
        record['local_tailwater_head_m'] = parameters['tailwater_head_m'] - frame['datum_m']
        _i29_check_frame(record, geometry, parameters)
        wrong = _i29_copy.deepcopy(record)
        wrong['local_hydraulic_head_m'][1][0] += 0.01
        with self.assertRaisesRegex(ValueError, 'global/local'):
            _i29_check_frame(wrong, geometry, parameters)
        wrong = _i29_copy.deepcopy(record)
        wrong['numerical_frame']['tiny_flux_deadband'] = True
        with self.assertRaisesRegex(ValueError, 'local vertical datum'):
            _i29_check_frame(wrong, geometry, parameters)
