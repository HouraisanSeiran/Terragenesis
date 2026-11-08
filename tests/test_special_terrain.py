"""Consolidated test_special_terrain implementations; numeric expressions preserved."""
from __future__ import annotations
from tools.preview_special_terrain import render_preview as _merged__i35_eggs_render_preview
from tools.preview_special_terrain import uluru_flare_render as _merged__i37_flare_uluru_flare_render
import json as _i32_json
from pathlib import Path as _i32_Path
import sys as _i32_sys
import tempfile as _i32_tempfile
import unittest as _i32_unittest
import numpy as _i32_np
from terrain_pipeline.special_terrain import METRIC_FORMS_ALGORITHM as _i32_ALGORITHM
from terrain_pipeline.special_terrain import KINDS as _i32_KINDS
from terrain_pipeline.special_terrain import PARAMETER_SOURCES as _i32_PARAMETER_SOURCES
from terrain_pipeline.special_terrain import METRIC_FORMS_SCHEMA as _i32_SCHEMA
from terrain_pipeline.special_terrain import FormTarget as _i32_FormTarget
from terrain_pipeline.special_terrain import SpecialFormRecipe as _i32_SpecialFormRecipe
from terrain_pipeline.special_terrain import analytic_base_chart as _i32_analytic_base_chart
from terrain_pipeline.special_terrain import build_special_form_vdm as _i32_build_special_form_vdm
from terrain_pipeline.special_terrain import form_preset as _i32_form_preset
from terrain_pipeline.special_terrain import load_special_form_vdm as _i32_load_special_form_vdm
from terrain_pipeline.special_terrain import pillar_field_targets as _i32_pillar_field_targets
from terrain_pipeline.special_terrain import save_special_form_vdm as _i32_save_special_form_vdm
from terrain_pipeline.special_terrain import validate_special_form_vdm as _i32_validate_special_form_vdm
from terrain_pipeline.common_infra import file_sha256 as _i32_file_sha256
from tools import audit_special_terrain as _i32_auditor
from tools import prepare_special_terrain as _i32_prepare
import json as _i33_json
from pathlib import Path as _i33_Path
import sys as _i33_sys
import tempfile as _i33_tempfile
import unittest as _i33_unittest
import numpy as _i33_np
from terrain_pipeline.special_terrain import KINDS as _i33_KINDS
from terrain_pipeline.special_terrain import FormTarget as _i33_FormTarget
from terrain_pipeline.special_terrain import SpecialFormRecipe as _i33_SpecialFormRecipe
from terrain_pipeline.special_terrain import analytic_base_chart as _i33_analytic_base_chart
from terrain_pipeline.special_terrain import build_special_form_vdm as _i33_build_special_form_vdm
from terrain_pipeline.special_terrain import METRIC_SURFACE_ALGORITHM as _i33_ALGORITHM
from terrain_pipeline.special_terrain import ARRAY_KEYS as _i33_ARRAY_KEYS
from terrain_pipeline.special_terrain import KERNEL_FILES as _i33_KERNEL_FILES
from terrain_pipeline.special_terrain import RETIRED_RECIPE_FIELDS as _i33_RETIRED_RECIPE_FIELDS
from terrain_pipeline.special_terrain import METRIC_SURFACE_SCHEMA as _i33_SCHEMA
from terrain_pipeline.special_terrain import SUPERSEDES_ALGORITHM as _i33_SUPERSEDES_ALGORITHM
from terrain_pipeline.special_terrain import DissectionRecipe as _i33_DissectionRecipe
from terrain_pipeline.special_terrain import FacetRoughnessRecipe as _i33_FacetRoughnessRecipe
from terrain_pipeline.special_terrain import build_special_form_surface as _i33_build_special_form_surface
from terrain_pipeline.special_terrain import kernel_revisions as _i33_kernel_revisions
from terrain_pipeline.special_terrain import load_special_form_surface as _i33_load_special_form_surface
from terrain_pipeline.special_terrain import save_special_form_surface as _i33_save_special_form_surface
from terrain_pipeline.special_terrain import surface_preset as _i33_surface_preset
from terrain_pipeline.special_terrain import validate_special_form_surface as _i33_validate_special_form_surface
from terrain_pipeline.common_infra import file_sha256 as _i33_file_sha256
from terrain_pipeline.common_infra import identity as _i33_identity
from dataclasses import asdict as _i34_asdict
import hashlib as _i34_hashlib
import json as _i34_json
import math as _i34_math
from pathlib import Path as _i34_Path
import tempfile as _i34_tempfile
import unittest as _i34_unittest
import numpy as _i34_np
from terrain_pipeline import hybrid_geometry as _i34_boolean
from terrain_pipeline import special_terrain as _i34_bridge
from terrain_pipeline.hybrid_geometry import manifold_from_record as _i34_manifold_from_record
from terrain_pipeline.hybrid_geometry import ray_hits as _i34_ray_hits
from terrain_pipeline.hybrid_geometry import signed_volume as _i34_signed_volume
from terrain_pipeline.hybrid_geometry import identity as _i34_identity
import json as _i35_json
import math as _i35_math
from pathlib import Path as _i35_Path
import tempfile as _i35_tempfile
import unittest as _i35_unittest
import numpy as _i35_np
from terrain_pipeline import special_terrain as _i35_eggs
from terrain_pipeline.hybrid_geometry import ray_hits as _i35_ray_hits
from terrain_pipeline.hybrid_geometry import identity as _i35_identity
from terrain_pipeline.hybrid_geometry import FLAGS as _i35_FLAGS
from terrain_pipeline.hybrid_geometry import BooleanParameters as _i35_BooleanParameters
from terrain_pipeline.hybrid_geometry import SOLID_SCHEMA as _i35_SOLID_SCHEMA
from terrain_pipeline.hybrid_geometry import census as _i35_census
from terrain_pipeline.hybrid_geometry import combine as _i35_combine
from terrain_pipeline.hybrid_geometry import solid_from_record as _i35_solid_from_record
import json as _i36_json
from pathlib import Path as _i36_Path
import tempfile as _i36_tempfile
import unittest as _i36_unittest
import numpy as _i36_np
from terrain_pipeline.hybrid_geometry import FLAGS as _i36_FLAGS
from terrain_pipeline.hybrid_geometry import identity as _i36_identity
from terrain_pipeline.special_terrain import SINKHOLE_ALGORITHM as _i36_ALGORITHM
from terrain_pipeline.special_terrain import BASE_KIND as _i36_BASE_KIND
from terrain_pipeline.special_terrain import BASE_NOTE as _i36_BASE_NOTE
from terrain_pipeline.special_terrain import CUTTER_ROLES as _i36_CUTTER_ROLES
from terrain_pipeline.special_terrain import SINKHOLE_EXPLICIT_ASSUMPTIONS as _i36_EXPLICIT_ASSUMPTIONS
from terrain_pipeline.special_terrain import LOCAL_ORIGIN as _i36_LOCAL_ORIGIN
from terrain_pipeline.special_terrain import SINKHOLE_SCHEMA as _i36_SCHEMA
from terrain_pipeline.special_terrain import SOLID_SCHEMA as _i36_SOLID_SCHEMA
from terrain_pipeline.special_terrain import SinkholeParameters as _i36_SinkholeParameters
from terrain_pipeline.special_terrain import assumption_list as _i36_assumption_list
from terrain_pipeline.special_terrain import audit as _i36_audit
from terrain_pipeline.special_terrain import sinkhole_build as _i36_build
from terrain_pipeline.special_terrain import solid_winding as _i36_solid_winding
from tools.preview_special_terrain import write_preview as _i36_write_preview
import json as _i37_json
import sys as _i37_sys
from pathlib import Path as _i37_Path
import unittest as _i37_unittest
import numpy as _i37_np
from terrain_pipeline import special_terrain as _i37_flare
from terrain_pipeline.hybrid_geometry import ray_hits as _i37_ray_hits
from terrain_pipeline.hybrid_geometry import FLAGS as _i37_FLAGS
from terrain_pipeline.hybrid_geometry import census as _i37_census
from terrain_pipeline.hybrid_geometry import solid_from_record as _i37_solid_from_record
from terrain_pipeline.hybrid_geometry import identity as _i37_identity
import json as _i38_json
from pathlib import Path as _i38_Path
import sys as _i38_sys
import tempfile as _i38_tempfile
import unittest as _i38_unittest
import numpy as _i38_np
from terrain_pipeline.special_terrain import load_special_form_vdm as _i38_load_special_form_vdm
from terrain_pipeline.common_infra import file_sha256 as _i38_file_sha256
from terrain_pipeline.basin_topology import load_basin_hierarchy as _i38_load_basin_hierarchy
from terrain_pipeline.special_terrain import TD_ADAPTER_ALGORITHM as _i38_ALGORITHM
from terrain_pipeline.special_terrain import CHANNEL_POLICIES as _i38_CHANNEL_POLICIES
from terrain_pipeline.special_terrain import MAX_FINE_CELLS as _i38_MAX_FINE_CELLS
from terrain_pipeline.special_terrain import MAX_FINE_SIDE as _i38_MAX_FINE_SIDE
from terrain_pipeline.special_terrain import NATIVE_SPACING_M as _i38_NATIVE_SPACING_M
from terrain_pipeline.special_terrain import TD_ADAPTER_SCHEMA as _i38_SCHEMA
from terrain_pipeline.special_terrain import build_td_form_chart as _i38_build_td_form_chart
from terrain_pipeline.special_terrain import select_native_window as _i38_select_native_window
from tools import preview_special_terrain as _i38_preview
CATEGORY = 'C'
ROOT = _i32_Path(__file__).resolve().parents[1]
_i32_sys.path.insert(0, str(ROOT))

class SpecialTerrainFormsTests(_i32_unittest.TestCase):

    def build(self, kind):
        recipe = _i32_form_preset(kind)
        chart = _i32_analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m, spacing_m=recipe.spacing_m)
        mask = _i32_np.zeros(chart.shape[:2], dtype=bool)
        return _i32_build_special_form_vdm(chart, recipe=recipe, protected_mask=mask, source_identity='base-1', protection_identity='mask-1')

    def test_four_kinds_are_distinct_and_replayable(self):
        self.assertEqual(_i32_KINDS, {'volcanic_plug', 'inselberg', 'sandstone_pillar_field', 'karst_tower_field'})
        reliefs = {}
        for kind in sorted(_i32_KINDS):
            first, second = (self.build(kind), self.build(kind))
            self.assertTrue(_i32_validate_special_form_vdm(first))
            self.assertEqual(first['identity_sha256'], second['identity_sha256'])
            self.assertEqual(first['metadata']['schema'], _i32_SCHEMA)
            self.assertEqual(first['metadata']['algorithm'], _i32_ALGORITHM)
            self.assertEqual(first['metadata']['base'], 'synthetic_analytic')
            for flag in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'):
                self.assertIs(first['metadata'][flag], False)
            displacement = first['arrays']['displacement_xyz_m']
            self.assertTrue(_i32_np.all(displacement[:, :, 0] == 0))
            self.assertTrue(_i32_np.all(displacement[:, :, 2] == 0))
            self.assertTrue(_i32_np.all(displacement[0] == 0))
            self.assertTrue(_i32_np.all(displacement[-1] == 0))
            self.assertTrue(_i32_np.all(displacement[:, 0] == 0))
            self.assertTrue(_i32_np.all(displacement[:, -1] == 0))
            self.assertGreater(displacement[:, :, 1].max(), 0)
            reliefs[kind] = displacement[:, :, 1].tobytes()
        self.assertEqual(len(set(reliefs.values())), 4)

    def test_provenance_is_recorded_for_every_kind(self):
        for kind in sorted(_i32_KINDS):
            sources = _i32_PARAMETER_SOURCES[kind]
            self.assertTrue(sources)
            for field, (grade, reference) in sources.items():
                self.assertIn(grade, ('verified', 'secondary', 'assumed'))
                self.assertIn('parameters-and-sources.md', reference)
            result = self.build(kind)
            recorded = result['metadata']['parameter_sources'][kind]
            self.assertEqual(set(recorded), set(sources))

    def test_synthetic_base_is_declared_and_never_real_detail(self):
        result = self.build('volcanic_plug')
        self.assertEqual(result['metadata']['base'], 'synthetic_analytic')
        self.assertNotIn('td_fine_bed', _i32_json.dumps(result['metadata']))
        with self.assertRaises(ValueError):
            _i32_build_special_form_vdm(_i32_analytic_base_chart(size_x_m=400.0, size_z_m=400.0, spacing_m=1.0), recipe=_i32_form_preset('volcanic_plug'), protected_mask=_i32_np.zeros((401, 401), bool), source_identity='s', protection_identity='p', base_kind='real_dem')

    def test_rejects_unknown_kind_and_bad_targets(self):
        with self.assertRaises(ValueError):
            _i32_SpecialFormRecipe('karst_cave', 100.0, 100.0, 1.0, 10.0, (_i32_FormTarget('x', 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, 'assumed', 'r'),), 1)
        with self.assertRaises(ValueError):
            _i32_FormTarget('x', 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, 'guessed', 'r')
        with self.assertRaises(ValueError):
            _i32_FormTarget('x', 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, 'assumed', '  ')
        with self.assertRaises(ValueError):
            _i32_FormTarget('x', 0.0, 0.0, 0.0, -1.0, 5.0, 5.0, 'assumed', 'r')
        with self.assertRaises(ValueError):
            _i32_SpecialFormRecipe('inselberg', 900.0, 900.0, 1.0, 10.0, (_i32_FormTarget('a', 0.0, 0.0, 0.0, 10.0, 5.0, 5.0, 'assumed', 'r'), _i32_FormTarget('a', 50.0, 0.0, 0.0, 10.0, 5.0, 5.0, 'assumed', 'r')), 1)
        with self.assertRaises(ValueError):
            _i32_SpecialFormRecipe('inselberg', 900.0, 900.0, 1.0, 10.0, (), 1)
        with self.assertRaises(ValueError):
            _i32_form_preset('karst_cave')

    def test_sampling_gate_and_collar(self):
        with self.assertRaises(ValueError):
            _i32_build_special_form_vdm(_i32_analytic_base_chart(size_x_m=600.0, size_z_m=600.0, spacing_m=30.0), recipe=_i32_form_preset('volcanic_plug'), protected_mask=_i32_np.zeros((21, 21), bool), source_identity='s', protection_identity='p')
        shifted = _i32_SpecialFormRecipe('volcanic_plug', 410.0, 410.0, 1.0, 50.0, (_i32_FormTarget('moved', 0.0, 250.0, 0.0, 264.0, 152.5, 152.5, 'secondary', 'r'),), 20261003)
        with self.assertRaises(ValueError):
            _i32_build_special_form_vdm(_i32_analytic_base_chart(size_x_m=410.0, size_z_m=410.0, spacing_m=1.0), recipe=shifted, protected_mask=_i32_np.zeros((411, 411), bool), source_identity='s', protection_identity='p')
        with self.assertRaises(ValueError):
            _i32_analytic_base_chart(size_x_m=100.0, size_z_m=100.0, spacing_m=3.0)

    def test_protection_blocks_displacement(self):
        recipe = _i32_form_preset('volcanic_plug')
        chart = _i32_analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m, spacing_m=recipe.spacing_m)
        mask = _i32_np.zeros(chart.shape[:2], dtype=bool)
        mask[205, 205] = True
        result = _i32_build_special_form_vdm(chart, recipe=recipe, protected_mask=mask, source_identity='s', protection_identity='p')
        self.assertEqual(float(result['arrays']['displacement_xyz_m'][205, 205, 1]), 0.0)
        unprotected = _i32_build_special_form_vdm(chart, recipe=recipe, protected_mask=_i32_np.zeros(chart.shape[:2], dtype=bool), source_identity='s', protection_identity='p')
        self.assertGreater(float(unprotected['arrays']['displacement_xyz_m'][205, 205, 1]), 0.0)

    def test_roundtrip_and_tampering(self):
        result = self.build('inselberg')
        with _i32_tempfile.TemporaryDirectory() as folder:
            path = _i32_Path(folder) / 'form.npz'
            _i32_save_special_form_vdm(path, result)
            loaded = _i32_load_special_form_vdm(path, expected_sha256=_i32_file_sha256(path), expected_identity=result['identity_sha256'])
            for key in result['arrays']:
                _i32_np.testing.assert_array_equal(loaded['arrays'][key], result['arrays'][key])
            self.assertEqual(loaded['metadata'], result['metadata'])
            with self.assertRaises(ValueError):
                _i32_load_special_form_vdm(path, expected_sha256='0' * 64, expected_identity=result['identity_sha256'])
            with self.assertRaises(ValueError):
                _i32_load_special_form_vdm(path, expected_sha256=_i32_file_sha256(path), expected_identity='0' * 64)
        for mutation in ({'publishable': True}, {'base': 'real_dem'}, {'source_identity': ''}):
            with self.subTest(mutation=mutation):
                forged = {**result, 'metadata': {**result['metadata'], **mutation}}
                with self.assertRaises(ValueError):
                    _i32_validate_special_form_vdm(forged)
        changed = {**result, 'arrays': {**result['arrays'], 'vertices_xyz_m': result['arrays']['vertices_xyz_m'] + 1.0}}
        with self.assertRaises(ValueError):
            _i32_validate_special_form_vdm(changed)

    def test_pillar_field_jitter_is_seeded(self):
        kwargs = dict(prefix='p', rows=2, cols=2, pitch_m=10.0, radius_m=2.0, height_band_m=(10.0, 20.0), jitter_fraction=0.2, source_grade='assumed', source_ref='r')
        self.assertEqual(_i32_pillar_field_targets(seed=7, **kwargs), _i32_pillar_field_targets(seed=7, **kwargs))
        self.assertNotEqual(_i32_pillar_field_targets(seed=7, **kwargs), _i32_pillar_field_targets(seed=8, **kwargs))
        with self.assertRaises(ValueError):
            _i32_pillar_field_targets(seed=7, **{**kwargs, 'jitter_fraction': 0.6})
        with self.assertRaises(ValueError):
            _i32_pillar_field_targets(seed=7, **{**kwargs, 'height_band_m': (20.0, 10.0)})

    def test_independent_cold_audit_passes(self):
        with _i32_tempfile.TemporaryDirectory() as folder:
            output = _i32_Path(folder)
            self.assertEqual(_i32_prepare._entry_prepare_special_terrain_forms(['--output', str(output)]), 0)
            manifest = _i32_json.loads((output / 'manifest-report.json').read_text(encoding='utf-8'))
            self.assertEqual(set(manifest['forms']), set(_i32_KINDS))
            audited = {}
            for kind, entry in manifest['forms'].items():
                report = _i32_auditor.audit_bundle(output / entry['file'], expected_sha256=entry['sha256'])
                self.assertEqual(report['identity_sha256'], entry['identity_sha256'])
                self.assertLess(report['max_replay_difference_m'], _i32_auditor.TOLERANCE)
                self.assertEqual(report['status'], 'candidate')
                self.assertTrue(all((value is False for value in report['flags'].values())))
                self.assertTrue(all(report['perimeter_zero'].values()))
                self.assertGreater(report['mesh']['min_area_ratio'], 0.0)
                audited[kind] = report
            self.assertEqual(len(audited), 4)
            self.assertEqual(_i32_auditor._entry_audit_special_terrain_forms([str(output)]), 0)
            self.assertEqual(_i32_json.loads((output / 'independent-audit.json').read_text(encoding='utf-8'))['generator_imported'], False)
if str(ROOT) not in _i33_sys.path:
    _i33_sys.path.insert(0, str(ROOT))
SMALL_SIZE_M = 40.0
SMALL_SPACING_M = 0.5
SMALL_RADIUS_M = 8.0
SMALL_HEIGHT_M = 20.0

def small_parent():
    recipe = _i33_SpecialFormRecipe('volcanic_plug', SMALL_SIZE_M, SMALL_SIZE_M, SMALL_SPACING_M, 8.0, (_i33_FormTarget('tiny', 0.0, 0.0, 0.0, SMALL_HEIGHT_M, SMALL_RADIUS_M, SMALL_RADIUS_M, 'assumed', 'parameters-and-sources.md#4.1'),), 20261003)
    chart = _i33_analytic_base_chart(size_x_m=recipe.size_x_m, size_z_m=recipe.size_z_m, spacing_m=recipe.spacing_m)
    mask = _i33_np.zeros(chart.shape[:2], dtype=bool)
    return _i33_build_special_form_vdm(chart, recipe=recipe, protected_mask=mask, source_identity='unit-base', protection_identity='unit-mask')

def small_recipes():
    roughness = _i33_FacetRoughnessRecipe(20261003, ((12.0, 1.0), (8.0, 0.5), (5.0, 0.25)), 0.1)
    dissection = _i33_DissectionRecipe(repose_angle_deg=34.0, steps=3, detachment_per_step_m=4.0, maximum_cut_fraction=0.05, maximum_incision_fraction=0.15, mobile_fraction=0.03, mobile_minimum_m=0.75, deposition_fraction=0.35, tolerance_m=0.001, max_sweeps=64)
    return (roughness, dissection)

class SpecialTerrainSurfaceTests(_i33_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.parent = small_parent()
        cls.roughness, cls.dissection = small_recipes()
        cls.result = _i33_build_special_form_surface(cls.parent, roughness=cls.roughness, dissection=cls.dissection)

    def test_identity_is_deterministic_and_supersedes_v1(self):
        repeat = _i33_build_special_form_surface(self.parent, roughness=self.roughness, dissection=self.dissection)
        self.assertTrue(_i33_validate_special_form_surface(repeat))
        self.assertEqual(self.result['identity_sha256'], repeat['identity_sha256'])
        metadata = self.result['metadata']
        self.assertEqual(metadata['schema'], _i33_SCHEMA)
        self.assertEqual(metadata['algorithm'], _i33_ALGORITHM)
        self.assertEqual(metadata['supersedes_algorithm'], _i33_SUPERSEDES_ALGORITHM)
        self.assertEqual(metadata['parent_identity_sha256'], self.parent['identity_sha256'])
        self.assertEqual(self.result['identity_sha256'], _i33_identity(self.result['arrays'], metadata))
        for flag in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'self_intersection_verified'):
            self.assertIs(metadata[flag], False)
        self.assertEqual(set(metadata['kernel_revisions']), set(_i33_KERNEL_FILES))
        self.assertEqual(metadata['kernel_revisions'], _i33_kernel_revisions())

    def test_facet_wavelengths_are_absolute_metres_and_metadata_only(self):
        metadata = self.result['metadata']
        scales = self.roughness.scales
        self.assertEqual(metadata['facet_wavelengths_m'], [[cells * SMALL_SPACING_M, weight] for cells, weight in scales])
        self.assertNotEqual(metadata['facet_wavelengths_m'], [list(pair) for pair in scales])
        self.assertEqual(metadata['facet_recipe']['scales'], [list(pair) for pair in scales])
        self.assertEqual(metadata['facet_recipe'], _i33_json.loads(_i33_json.dumps(metadata['facet_recipe'])))

    def test_retired_recipe_field_is_refused(self):
        self.assertEqual(_i33_RETIRED_RECIPE_FIELDS, ('immobile_rock_fraction',))
        recipe = self.result['metadata']['dissection_recipe']
        self.assertFalse(any((field in recipe for field in _i33_RETIRED_RECIPE_FIELDS)))
        for field in _i33_RETIRED_RECIPE_FIELDS:
            with self.subTest(field=field):
                forged = {**self.result, 'metadata': {**self.result['metadata'], 'dissection_recipe': {**recipe, field: 0.38}}}
                with self.assertRaises(ValueError):
                    _i33_validate_special_form_surface(forged)

    def test_collar_and_protection_are_untouched(self):
        arrays = self.result['arrays']
        change = arrays['erosion_change_m']
        self.assertTrue(_i33_np.all(change[0] == 0.0))
        self.assertTrue(_i33_np.all(change[-1] == 0.0))
        self.assertTrue(_i33_np.all(change[:, 0] == 0.0))
        self.assertTrue(_i33_np.all(change[:, -1] == 0.0))
        mask = arrays['protected_mask']
        self.assertFalse(mask.any())
        surface = arrays['surface_xyz_m']
        reference = arrays['reference_xyz_m']
        for edge in (surface[0], surface[-1], surface[:, 0], surface[:, -1]):
            self.assertTrue(_i33_np.isfinite(edge).all())
        self.assertTrue(_i33_np.array_equal(surface[0], reference[0]))
        self.assertTrue(_i33_np.array_equal(surface[-1], reference[-1]))

    def test_surface_is_reference_plus_roughened_relief_plus_change(self):
        arrays = self.result['arrays']
        self.assertEqual(set(arrays), _i33_ARRAY_KEYS)
        vertical = _i33_np.zeros_like(arrays['reference_xyz_m'])
        vertical[:, :, 1] = arrays['erosion_change_m']
        recomputed = arrays['reference_xyz_m'] + arrays['displacement_xyz_m'] + vertical
        self.assertTrue(_i33_np.array_equal(arrays['surface_xyz_m'], recomputed))
        self.assertTrue(_i33_np.array_equal(arrays['vertices_xyz_m'], arrays['surface_xyz_m'].reshape(-1, 3)))
        self.assertGreater(float(_i33_np.max(_i33_np.abs(arrays['displacement_xyz_m'][:, :, 1] - self.parent['arrays']['displacement_xyz_m'][:, :, 1]))), 0.0)

    def test_ledgers_are_separate_and_never_cancel(self):
        ledger = self.result['metadata']['ledger']
        for key in ('detachment_ledger_m3', 'transport_deposition_ledger_m3', 'relaxation_transferred_ledger_m3'):
            self.assertGreaterEqual(ledger[key], 0.0)
        self.assertGreater(ledger['detachment_ledger_m3'], 0.0)
        self.assertGreater(ledger['incised_cells'], 0)
        self.assertGreater(ledger['maximum_incision_m'], 0.0)
        self.assertLessEqual(ledger['maximum_incision_m'], ledger['rock_floor_depth_m'] + 1e-09)
        self.assertEqual(len(ledger['steps']), self.dissection.steps)
        self.assertEqual([step['step_index'] for step in ledger['steps']], list(range(self.dissection.steps)))
        total_detached = ledger['detachment_ledger_m3']
        total_deposited = ledger['transport_deposition_ledger_m3']
        total_relaxed = ledger['relaxation_transferred_ledger_m3']
        self.assertLessEqual(total_deposited, total_detached + total_relaxed + 1e-06)
        phase = ledger['phase_balance']
        self.assertEqual(phase['phase'], 'hydraulic-dissection')
        self.assertEqual(phase['step_index'], self.dissection.steps - 1)
        self.assertEqual(phase['injected_bulk_m3'], 0.0)
        exported = float(_i33_np.sum(self.result['arrays']['erosion_change_m']) * SMALL_SPACING_M ** 2)
        self.assertAlmostEqual(phase['exported_bulk_m3'], -exported, places=9)
        self.assertAlmostEqual(ledger['net_change_ledger_m3'], exported, places=9)
        self.assertAlmostEqual(phase['raw_residual_bulk_m3'], 0.0, places=9)
        self.assertTrue(all((step['mobile_column_volume_m3'] >= 0.0 for step in ledger['steps'])))

    def test_rock_floor_is_never_penetrated(self):
        arrays = self.result['arrays']
        change = arrays['erosion_change_m']
        metadata = self.result['metadata']
        final = arrays['surface_xyz_m'][:, :, 1]
        depth = self.dissection.maximum_incision_fraction * metadata['roughened_relief_reference_m']
        base = arrays['reference_xyz_m'][:, :, 1]
        roughened = base + arrays['displacement_xyz_m'][:, :, 1]
        floor = _i33_np.minimum(_i33_np.maximum(roughened - depth, base), roughened)
        self.assertTrue(_i33_np.all(final >= floor - 1e-09))
        self.assertTrue(_i33_np.isfinite(final).all())
        self.assertGreater(int((final < roughened - 1e-09).sum()), 0)
        self.assertGreater(int((change > 0.0).sum()), 0)
        self.assertLess(float(_i33_np.sum(change)), 0.0)
        self.assertEqual(metadata['roughened_relief_reference_m'], float(_i33_np.max(roughened)))
        self.assertEqual(metadata['relief_reference_m'], float(_i33_np.max(self.parent['arrays']['displacement_xyz_m'][:, :, 1])))

    def test_relaxation_convergence_is_derived_not_trusted(self):
        ledger = self.result['metadata']['ledger']
        recipe = self.result['metadata']['dissection_recipe']
        steps = ledger['steps']
        for step in steps:
            self.assertIs(step['relaxation_converged'], step['relaxation_maximum_excess_m'] <= recipe['tolerance_m'])
            self.assertLessEqual(step['relaxation_sweeps'], recipe['max_sweeps'])
            self.assertFalse(step['relaxation_stalled_at_float64_resolution'])
        self.assertIs(ledger['relaxation_converged'], all((step['relaxation_maximum_excess_m'] <= recipe['tolerance_m'] for step in steps)))
        self.assertEqual(ledger['relaxation_tolerance_m'], recipe['tolerance_m'])
        self.assertEqual(ledger['relaxation_sweep_budget'], recipe['max_sweeps'])
        self.assertEqual(ledger['relaxation_maximum_excess_m'], max((step['relaxation_maximum_excess_m'] for step in steps)))
        self.assertEqual(ledger['relaxation_sweeps_max'], max((step['relaxation_sweeps'] for step in steps)))
        self.assertTrue(ledger['relaxation_converged'])
        for mutation in ({'relaxation_converged': not ledger['relaxation_converged']}, {'relaxation_maximum_excess_m': ledger['relaxation_maximum_excess_m'] + 1.0}, {'relaxation_tolerance_m': recipe['tolerance_m'] * 10.0}):
            with self.subTest(mutation=mutation):
                forged = {**self.result, 'metadata': {**self.result['metadata'], 'ledger': {**ledger, **mutation}}}
                with self.assertRaises(ValueError):
                    _i33_validate_special_form_surface(forged)
        flipped = {**steps[0], 'relaxation_converged': not steps[0]['relaxation_converged']}
        forged = {**self.result, 'metadata': {**self.result['metadata'], 'ledger': {**ledger, 'steps': [flipped] + steps[1:]}}}
        with self.assertRaises(ValueError):
            _i33_validate_special_form_surface(forged)

    def test_rejects_mismatched_or_forged_bundles(self):
        with self.assertRaises(ValueError):
            _i33_build_special_form_surface(self.parent, roughness=object(), dissection=self.dissection)
        with self.assertRaises(ValueError):
            _i33_build_special_form_surface(self.parent, roughness=self.roughness, dissection=object())
        with self.assertRaises(ValueError):
            _i33_FacetRoughnessRecipe(20261003, ((2.0, 1.0),), 0.1)
        with self.assertRaises(ValueError):
            _i33_FacetRoughnessRecipe(20261003, ((12.0, 1.0),), 0.6)
        with self.assertRaises(ValueError):
            _i33_DissectionRecipe(repose_angle_deg=34.0, steps=3, detachment_per_step_m=4.0, maximum_cut_fraction=0.05, maximum_incision_fraction=0.0, mobile_fraction=0.03, mobile_minimum_m=0.75, deposition_fraction=0.35, tolerance_m=1e-06, max_sweeps=8)
        for mutation in ({'publishable': True}, {'algorithm': 'other'}, {'parent_schema': 'x'}):
            with self.subTest(mutation=mutation):
                forged = {**self.result, 'metadata': {**self.result['metadata'], **mutation}}
                with self.assertRaises(ValueError):
                    _i33_validate_special_form_surface(forged)
        raised = {**self.result, 'arrays': {**self.result['arrays'], 'erosion_change_m': self.result['arrays']['erosion_change_m'] + 1.0}}
        with self.assertRaises(ValueError):
            _i33_validate_special_form_surface(raised)

    def test_roundtrip_and_tampering(self):
        with _i33_tempfile.TemporaryDirectory() as folder:
            path = _i33_Path(folder) / 'surface.npz'
            _i33_save_special_form_surface(path, self.result)
            digest = _i33_file_sha256(path)
            loaded = _i33_load_special_form_surface(path, expected_sha256=digest, expected_identity=self.result['identity_sha256'])
            self.assertEqual(loaded['metadata'], self.result['metadata'])
            for key in self.result['arrays']:
                _i33_np.testing.assert_array_equal(loaded['arrays'][key], self.result['arrays'][key])
            with self.assertRaises(ValueError):
                _i33_load_special_form_surface(path, expected_sha256='0' * 64, expected_identity=self.result['identity_sha256'])
            with self.assertRaises(ValueError):
                _i33_load_special_form_surface(path, expected_sha256=digest, expected_identity='0' * 64)

    def test_every_production_preset_is_declared_and_resolved(self):
        recorded = {}
        for kind in sorted(_i33_KINDS):
            roughness, dissection = _i33_surface_preset(kind)
            self.assertEqual(roughness.seed, 20261004 if kind == 'karst_tower_field' else 20261003)
            self.assertGreaterEqual(roughness.finest_cells, 4.0)
            self.assertGreater(dissection.detachment_per_step_m, 0.0)
            self.assertLess(dissection.maximum_incision_fraction, 1.0)
            self.assertEqual(dissection.deposition_fraction, 0.35)
            recorded[kind] = _i33_json.dumps(asdict_of(roughness, dissection), sort_keys=True)
            self.assertTrue(roughness.wavelengths_m(2.0)[0][0] > roughness.wavelengths_m(1.0)[0][0])
        with self.assertRaises(ValueError):
            _i33_surface_preset('karst_cave')
        self.assertEqual(len(set(recorded.values())), len(_i33_KINDS))

def asdict_of(roughness, dissection):
    from dataclasses import asdict
    return {'roughness': asdict(roughness), 'dissection': asdict(dissection)}
CONTRACT_KEYS = ('schema', 'algorithm', 'status', 'synthetic_base', 'parameters', 'explicit_assumptions', 'solids', 'boolean', 'witnesses', 'flags', 'library_versions', 'figures', 'identity_sha256')
SOLID_KEYS = ('schema', 'role', 'local_origin_xyz_m', 'vertices_local_xyz_m', 'triangles', 'signed_volume_m3', 'sampled_not_native_exact', 'identity_sha256')
BRIDGE_ROLES = ('cutter_skylight_a', 'cutter_skylight_b')
_REPORT = None
_SOLIDS = None

def report():
    """One shared default build; the build is deterministic, so sharing is safe."""
    global _REPORT, _SOLIDS
    if _REPORT is None:
        _REPORT, _SOLIDS = _i34_bridge.cave_bridge_report()
    return (_REPORT, _SOLIDS)

def rebuild(record):
    """Rebuild a closed Manifold straight from a saved record, no generator involved."""
    mesh = __import__('manifold3d').Mesh64(_i34_np.array(record['vertices_local_xyz_m'], dtype=_i34_np.float64, order='C', copy=True), _i34_np.array(record['triangles'], dtype=_i34_np.uint64, order='C', copy=True))
    return __import__('manifold3d').Manifold(mesh)

def replayed_ray(witness, solids, origin):
    solid = rebuild(solids[witness['solid_role']])
    return _i34_ray_hits(solid, _i34_np.array(witness['from_xyz_m'], float), _i34_np.array(witness['to_xyz_m'], float), origin)

class DefaultLattice(_i34_unittest.TestCase):
    """The default assumed lattice excavates one cavity and leaves a bridge."""

    def test_status_census_and_flags(self):
        record, _ = report()
        self.assertEqual(record['status'], 'candidate')
        self.assertEqual(record['schema'], _i34_bridge.CAVE_BRIDGE_REPORT_SCHEMA)
        boolean_record = record['boolean']
        self.assertEqual(boolean_record['status'], 'candidate')
        census = boolean_record['census']
        self.assertEqual(census['removed_components'], 1)
        self.assertEqual(census['rock_after_components'], 1)
        self.assertEqual(census['cutter_union_components'], 1)
        self.assertEqual(census['cutter_count'], 4)
        self.assertEqual(record['flags'], {flag: False for flag in _i34_boolean.FLAGS})
        self.assertEqual(boolean_record['rejection_reasons'], [])
        self.assertEqual(boolean_record['operation'], 'rock_minus_closed_cutter_union')
        self.assertEqual(boolean_record['fill_rock_m3'], 0.0)

    def test_tunnel_network_and_both_skylights_share_one_cavity(self):
        record, solids = report()
        self.assertEqual(sorted(solids), sorted(record['solids']))
        for role in BRIDGE_ROLES + ('cutter_main_tunnel', 'cutter_side_branch', 'rock_before', 'rock_after', 'removed', 'cutter_union'):
            self.assertIn(role, solids)
        self.assertEqual(len(rebuild(solids['cutter_union']).decompose()), 1)
        self.assertEqual(len(rebuild(solids['rock_after']).decompose()), 1)
        self.assertEqual(len(rebuild(solids['removed']).decompose()), 1)

class MaterialAccount(_i34_unittest.TestCase):
    """Actual closed-solid volume, never a formula the Boolean did not produce."""

    def test_analytic_lattice_volumes(self):
        record, solids = report()
        parameters = _i34_bridge.PARAMETERS
        self.assertAlmostEqual(solids['rock_before']['signed_volume_m3'], 432000.0, delta=1e-06)
        self.assertAlmostEqual(solids['cutter_main_tunnel']['signed_volume_m3'], 6400.0, delta=1e-06)
        self.assertAlmostEqual(solids['cutter_side_branch']['signed_volume_m3'], 5760.0, delta=1e-06)
        ring_area = parameters.skylight_segments / 2.0 * parameters.skylight_radius_m ** 2 * _i34_math.sin(2.0 * _i34_math.pi / parameters.skylight_segments)
        bore = ring_area * (parameters.top_y_m - parameters.tunnel_roof_y_m)
        for role in BRIDGE_ROLES:
            self.assertAlmostEqual(solids[role]['signed_volume_m3'], bore, delta=1e-06)
        overlap = 2.0 * parameters.tunnel_half_width_m * (2.0 * parameters.branch_half_width_m) * (parameters.tunnel_roof_y_m - parameters.tunnel_floor_y_m)
        expected = solids['cutter_main_tunnel']['signed_volume_m3'] + solids['cutter_side_branch']['signed_volume_m3'] - overlap + 2.0 * bore
        self.assertAlmostEqual(solids['cutter_union']['signed_volume_m3'], expected, delta=1e-06)

    def test_balance_closes_on_the_saved_solids(self):
        record, solids = report()
        material = record['boolean']['material']
        self.assertEqual(material['fill_rock_m3'], 0.0)
        self.assertLessEqual(abs(material['signed_residual_m3']), material['balance_budget_m3'])
        self.assertAlmostEqual(material['rock_before_m3'] - material['rock_after_m3'], material['excavated_rock_m3'], delta=1e-07)
        self.assertAlmostEqual(solids['cutter_union']['signed_volume_m3'], solids['removed']['signed_volume_m3'], delta=1e-07)
        self.assertAlmostEqual(solids['rock_after']['signed_volume_m3'], material['rock_after_m3'], delta=1e-07)

    def test_saved_void_is_a_closed_reverse_two_use_surface(self):
        _, solids = report()
        uses = {}
        for triangle in _i34_np.asarray(solids['removed']['triangles'], int):
            for first, second in zip(triangle, _i34_np.roll(triangle, -1)):
                uses.setdefault(tuple(sorted((int(first), int(second)))), []).append((int(first), int(second)))
        for sides in uses.values():
            self.assertEqual(len(sides), 2)
            self.assertEqual(sides[0], sides[1][::-1])

class BridgeAndSkylights(_i34_unittest.TestCase):
    """The three decisive verdicts, each replayed from the saved meshes."""

    def test_bridge_axis_stays_solid_under_the_top_face(self):
        record, solids = report()
        witness = record['witnesses']['bridge_axis_under_top_face']
        hits = replayed_ray(witness, solids, _i34_bridge.ORIGIN)
        self.assertEqual(len(hits), witness['expected_hit_count'])
        self.assertEqual(len(hits), 4)
        xs = [hit['position_xyz_m'][0] for hit in hits]
        self.assertAlmostEqual(hits[1]['position_xyz_m'][0], -21.0, delta=1e-09)
        self.assertAlmostEqual(hits[2]['position_xyz_m'][0], 21.0, delta=1e-09)
        self.assertLess(xs[1], 0.0)
        self.assertGreater(xs[2], 0.0)

    def test_both_bridge_probe_centres_cross_rock_above_the_gallery_roof(self):
        record, solids = report()
        parameters = _i34_bridge.PARAMETERS
        witness = record['witnesses']['bridge_probe_centres_are_both_bridges']
        self.assertEqual(witness['observed']['crossings_above_gallery_roof'], [1, 1])
        for probe in witness['observed']['probes']:
            hits = replayed_ray(probe['ray'], solids, _i34_bridge.ORIGIN)
            self.assertEqual(len(hits), 4)
            over_roof = [hit for hit in hits if hit['position_xyz_m'][1] > parameters.tunnel_roof_y_m]
            self.assertEqual(len(over_roof), 1)
            self.assertAlmostEqual(over_roof[0]['position_xyz_m'][1], parameters.top_y_m, delta=1e-09)
        self.assertLess(witness['observed']['probes'][0]['x_m'], parameters.skylight_x_m[1] - parameters.skylight_radius_m)
        self.assertGreater(witness['observed']['probes'][1]['x_m'], parameters.skylight_x_m[1] + parameters.skylight_radius_m)

    def test_skylights_are_open_to_the_sky_and_the_top_face_between_them_is_not(self):
        record, solids = report()
        parameters = _i34_bridge.PARAMETERS
        for role, centre in zip(BRIDGE_ROLES, parameters.skylight_x_m):
            suffix = role.split('_')[-1]
            aperture = record['witnesses']['skylight_' + suffix + '_open_to_sky']
            self.assertEqual(replayed_ray(aperture, solids, _i34_bridge.ORIGIN), [])
            bore = record['witnesses']['skylight_' + suffix + '_bores_into_the_block']
            hits = replayed_ray(bore, solids, _i34_bridge.ORIGIN)
            self.assertEqual(len(hits), 2)
            self.assertEqual([round(hit['position_xyz_m'][1], 6) for hit in hits], [parameters.tunnel_floor_y_m, parameters.bottom_y_m])
            self.assertAlmostEqual([hit['position_xyz_m'][0] for hit in hits][0], centre, delta=1e-09)
        over_roof = record['witnesses']['bridge_axis_over_the_roof']
        hits = replayed_ray(over_roof, solids, _i34_bridge.ORIGIN)
        self.assertEqual(len(hits), 1)
        self.assertAlmostEqual(hits[0]['position_xyz_m'][1], parameters.top_y_m, delta=1e-09)
        self.assertAlmostEqual(hits[0]['position_xyz_m'][2], 0.0, delta=1e-09)

class WindingVerdicts(_i34_unittest.TestCase):
    """The tolerant independent point-in-solid test, with its tolerance made explicit."""

    def test_tolerance_separates_a_residual_zero_from_a_real_interior(self):
        self.assertFalse(_i34_bridge.inside(0.0))
        self.assertFalse(_i34_bridge.inside(1e-12))
        self.assertFalse(_i34_bridge.inside(3.05e-16))
        self.assertTrue(_i34_bridge.inside(1.0))
        self.assertTrue(_i34_bridge.inside(0.9999999999999))
        with self.assertRaises(ValueError):
            _i34_bridge.inside(-1.0)
        with self.assertRaises(ValueError):
            _i34_bridge.inside(float('nan'))

    def test_winding_numbers_of_the_saved_rock_after(self):
        record, solids = report()
        parameters = _i34_bridge.PARAMETERS
        mesh = solids['rock_after']
        mid_y = (parameters.tunnel_roof_y_m + parameters.top_y_m) / 2.0
        void_y = (parameters.tunnel_floor_y_m + parameters.tunnel_roof_y_m) / 2.0
        samples = {'bridge centre': ((0.0, mid_y, 0.0), True), 'bridge above the floor': ((0.0, parameters.tunnel_roof_y_m + 1.0, 0.0), True), 'gallery void': ((0.0, void_y, 0.0), False), 'branch void': ((0.0, void_y, parameters.branch_end_z_m - 6.0), False), 'bore a column': ((parameters.skylight_x_m[0], void_y + 2.0, 0.0), False), 'bore b column': ((parameters.skylight_x_m[1], void_y + 2.0, 0.0), False), 'outer rock': ((parameters.plan_half_x_m - 5.0, mid_y, parameters.plan_half_z_m - 5.0), True)}
        for label, (point, expected) in samples.items():
            value = _i34_bridge.cave_bridge_winding_number(point, mesh['vertices_local_xyz_m'], mesh['triangles'])
            self.assertEqual(_i34_bridge.inside(value), expected, label + ' winding=' + repr(value))
            if expected:
                self.assertAlmostEqual(value, 1.0, delta=1e-09)
            else:
                self.assertLess(abs(value), _i34_bridge.WINDING_INSIDE_TOLERANCE)

    def test_every_saved_winding_witness_replays_from_the_mesh(self):
        record, solids = report()
        seen = 0
        for name, witness in record['witnesses'].items():
            if witness['method'] != 'Solid.winding':
                continue
            mesh = solids[witness['solid_role']]
            self.assertEqual(mesh['identity_sha256'], _i34_identity({key: value for key, value in mesh.items() if key != 'identity_sha256'}))
            replayed = _i34_bridge.cave_bridge_winding_number(witness['point_xyz_m'], mesh['vertices_local_xyz_m'], mesh['triangles'])
            self.assertAlmostEqual(replayed, witness['observed']['winding'], delta=1e-12, msg=name)
            self.assertEqual(_i34_bridge.inside(replayed), witness['expected_inside'], name)
            self.assertTrue(witness['verdict'])
            seen += 1
        self.assertEqual(seen, 6)
        nested = record['witnesses']['bridge_probe_centres_are_both_bridges']['observed']['probes']
        self.assertEqual(len(nested), 2)
        for probe in nested:
            mesh = solids[probe['winding']['solid_role']]
            replayed = _i34_bridge.cave_bridge_winding_number(probe['winding']['point_xyz_m'], mesh['vertices_local_xyz_m'], mesh['triangles'])
            self.assertAlmostEqual(replayed, probe['winding']['observed']['winding'], delta=1e-12)
            self.assertTrue(_i34_bridge.inside(replayed))

class ColdReadContract(_i34_unittest.TestCase):
    """What a reader who does not import the generator can actually re-check."""

    def test_report_shape_and_sealed_solid_identities(self):
        record, solids = report()
        for key in CONTRACT_KEYS:
            self.assertIn(key, record)
        self.assertEqual(record['synthetic_base']['kind'], 'synthetic_analytic')
        self.assertIn('not TD native terrain', record['synthetic_base']['note'])
        self.assertEqual(record['identity_sha256'], _i34_identity({key: value for key, value in record.items() if key != 'identity_sha256'}))
        self.assertEqual(record['parameters_identity_sha256'], _i34_identity(record['parameters']))
        self.assertEqual(record['parameters'], _i34_asdict(_i34_bridge.PARAMETERS))
        self.assertIn('manifold3d', record['library_versions'])
        self.assertIn('numpy', record['library_versions'])
        for role, mesh in record['solids'].items():
            for key in SOLID_KEYS:
                self.assertIn(key, mesh, role)
            self.assertTrue(mesh['sampled_not_native_exact'], role)
            self.assertEqual(mesh['role'], role)
            self.assertEqual(mesh['identity_sha256'], _i34_identity({key: value for key, value in mesh.items() if key != 'identity_sha256'}))
            recomputed = _i34_signed_volume(_i34_np.array(mesh['vertices_local_xyz_m'], float), _i34_np.array(mesh['triangles'], int))
            self.assertAlmostEqual(recomputed, mesh['signed_volume_m3'], delta=1e-06, msg=role)
            self.assertEqual(rebuild(mesh).status().name, 'NoError')

    def test_every_assumption_is_declared_as_an_explicit_assumption(self):
        record, _ = report()
        assumptions = {item['name']: item for item in record['explicit_assumptions']}
        self.assertTrue(assumptions)
        for item in record['explicit_assumptions']:
            self.assertEqual(item['grade'], 'assumed')
            self.assertTrue(item['reason'])
        for name in ('tunnel_roof_y_m', 'tunnel_floor_y_m', 'skylight_x_m', 'skylight_radius_m'):
            self.assertIn(name, assumptions)
        self.assertEqual(sorted(assumptions), sorted((name for name in record['parameters'])))

    def test_every_ray_witness_replays_and_names_a_saved_solid(self):
        record, solids = report()
        seen = 0
        for name, witness in record['witnesses'].items():
            if witness['method'] != 'Manifold.ray_cast':
                continue
            if 'probes' in witness.get('observed', {}):
                continue
            self.assertIn(witness['solid_role'], solids)
            hits = replayed_ray(witness, solids, _i34_bridge.ORIGIN)
            self.assertEqual(len(hits), witness['observed']['hit_count'], name)
            self.assertEqual(len(hits), witness['expected_hit_count'], name)
            accompanied = {key: value for key, value in witness.items() if key != 'observed'}
            self.assertEqual(sorted(accompanied), sorted(['method', 'solid_role', 'from_xyz_m', 'to_xyz_m', 'expected_hit_count', 'verdict', 'claim']))
            seen += 1
        self.assertGreaterEqual(seen, 6)

    def test_material_witnesses_replay_by_redoing_the_subtract(self):
        record, solids = report()
        for name in ('material_balance', 'saved_void_closure'):
            witness = record['witnesses'][name]
            self.assertEqual(witness['method'], 'Mesh64_boolean')
            self.assertEqual(witness['operation'], 'subtract')
            rock = _i34_boolean.solid_from_record(solids[witness['rock_role']], name)
            cutters = [_i34_boolean.solid_from_record(solids[role], name) for role in witness['cutter_roles']]
            union = rebuild(solids['cutter_union'])
            self.assertAlmostEqual(union.volume(), rock.volume() - (rock - union).volume(), delta=1e-07)
            self.assertAlmostEqual(union.volume(), (rock ^ union).volume(), delta=1e-07)
            self.assertAlmostEqual(union.volume(), witness['expected_removed_m3'], delta=1e-07)
            for role in witness['cutter_roles']:
                self.assertIn(role, solids)
            self.assertEqual(len(cutters), len(record['parameters']['skylight_x_m']) + 2)

    def test_figures_are_labelled_display_only(self):
        record, _ = report()
        self.assertEqual(record['figure_scope'], 'display only; a figure is never a certification')
        self.assertEqual(record['figures'], [])

    def test_report_bytes_and_previews_are_reproducible(self):
        with _i34_tempfile.TemporaryDirectory() as shared:
            shared = _i34_Path(shared)
            first = _i34_bridge.cave_bridge_write_report(shared / 'report.json', output_directory=shared)
            blob = (shared / 'report.json').read_bytes()
            digests = {path.name: _i34_hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(shared.glob('*.png'))}
            self.assertEqual(len(digests), 3)
            second = _i34_bridge.cave_bridge_write_report(shared / 'report.json', output_directory=shared)
            self.assertEqual(blob, (shared / 'report.json').read_bytes())
            self.assertEqual(first['identity_sha256'], second['identity_sha256'])
            self.assertEqual(first['figures'], second['figures'])
            for path in sorted(shared.glob('*.png')):
                self.assertEqual(_i34_hashlib.sha256(path.read_bytes()).hexdigest(), digests[path.name])
            self.assertTrue(blob.endswith(b'}'))
            self.assertNotIn(b'\n', blob)
            self.assertEqual(set(_i34_json.loads(blob.decode('utf-8'))), set(first))

class Refusals(_i34_unittest.TestCase):
    """The lattice refuses a geometry that would not actually be a bridge."""

    def test_skylights_too_close_to_leave_a_bridge_are_refused(self):
        with self.assertRaises(ValueError):
            _i34_bridge.Parameters(skylight_x_m=(-6.0, 6.0))
        with self.assertRaises(ValueError):
            _i34_bridge.Parameters(skylight_x_m=(25.0, -25.0))
        with self.assertRaises(ValueError):
            _i34_bridge.Parameters(skylight_x_m=[-25.0, 25.0])

    def test_a_bore_swallowing_the_block_centre_is_refused(self):
        Parameters = _i34_bridge.Parameters
        for centres in ((-3.0, 40.0), (-40.0, 3.0)):
            with self.assertRaises(ValueError, msg=str(centres)):
                Parameters(skylight_x_m=centres)

    def test_tunnel_outside_the_block_or_through_the_walls_is_refused(self):
        Parameters = _i34_bridge.Parameters
        with self.assertRaises(ValueError):
            Parameters(tunnel_roof_y_m=1.0)
        with self.assertRaises(ValueError):
            Parameters(tunnel_floor_y_m=-31.0)
        with self.assertRaises(ValueError):
            Parameters(tunnel_floor_y_m=-14.0, tunnel_roof_y_m=-22.0)
        with self.assertRaises(ValueError):
            Parameters(tunnel_length_x_m=60.0)
        with self.assertRaises(ValueError):
            Parameters(branch_end_z_m=70.0)
        with self.assertRaises(ValueError):
            Parameters(plan_half_x_m=5.0)
        with self.assertRaises(ValueError):
            Parameters(branch_end_z_m=3.0)

    def test_mistyped_lattice_fields_are_refused(self):
        Parameters = _i34_bridge.Parameters
        with self.assertRaises(ValueError):
            Parameters(solids_spacing_m=1)
        with self.assertRaises(ValueError):
            Parameters(skylight_segments=4)
        with self.assertRaises(ValueError):
            Parameters(component_limit=4096)
        with self.assertRaises(ValueError):
            Parameters(skylight_x_m=(-25, 25))
        with self.assertRaises(ValueError):
            _i34_bridge.cave_bridge_build(parameters=None)

class IndependentGeometry(_i34_unittest.TestCase):
    """The saved meshes are real closed solids, not displays."""

    def test_every_saved_solid_is_a_closed_use_manifold_with_positive_volume(self):
        _, solids = report()
        library = __import__('manifold3d')
        for role, mesh in solids.items():
            solid = rebuild(mesh)
            self.assertEqual(solid.status(), library.Error.NoError, role)
            self.assertFalse(solid.is_empty(), role)
            self.assertGreater(solid.volume(), 0.0, role)
            self.assertAlmostEqual(solid.volume(), mesh['signed_volume_m3'], delta=1e-06, msg=role)
            self.assertGreater(len(mesh['triangles']), 3, role)
            uses = {}
            for triangle in _i34_np.asarray(mesh['triangles'], int):
                self.assertEqual(len(set(triangle.tolist())), 3, role)
                for first, second in zip(triangle, _i34_np.roll(triangle, -1)):
                    uses.setdefault(tuple(sorted((int(first), int(second)))), []).append((int(first), int(second)))
            for sides in uses.values():
                self.assertEqual(len(sides), 2, role)
                self.assertEqual(sides[0], sides[1][::-1], role)

    def test_the_block_top_face_is_only_broken_over_the_two_bores(self):
        _, solids = report()
        parameters = _i34_bridge.PARAMETERS
        rock = rebuild(solids['rock_after'])
        for x_m in _i34_np.arange(-parameters.plan_half_x_m + 1.0, parameters.plan_half_x_m - 1.0, 1.0):
            hits = _i34_ray_hits(rock, _i34_np.array([x_m, parameters.top_y_m + 3.0, 0.0]), _i34_np.array([x_m, parameters.top_y_m - 1.0, 0.0]), _i34_bridge.ORIGIN)
            inside_bore = any((abs(float(x_m) - centre) < parameters.skylight_radius_m - 0.5 for centre in parameters.skylight_x_m))
            self.assertEqual(len(hits), 0 if inside_bore else 1, 'x=%.1f inside_bore=%s' % (x_m, inside_bore))

    def test_the_world_frame_is_the_identity(self):
        record, solids = report()
        self.assertIn('zero local origin', record['world_frame'])
        for mesh in solids.values():
            self.assertEqual(mesh['local_origin_xyz_m'], [0.0, 0.0, 0.0])
        vertices = _i34_np.array(solids['rock_before']['vertices_local_xyz_m'], float)
        self.assertEqual(vertices[:, 0].min(), -_i34_bridge.PARAMETERS.plan_half_x_m)
        self.assertEqual(vertices[:, 1].min(), _i34_bridge.PARAMETERS.bottom_y_m)
        self.assertEqual(vertices[:, 1].max(), _i34_bridge.PARAMETERS.top_y_m)
ALLOWED_METHODS = ('Manifold.ray_cast', 'Solid.winding', 'Mesh64_boolean')
TEST_ROCK_EGGS_CONTRACT_KEYS = {'schema', 'algorithm', 'status', 'synthetic_base', 'parameters', 'explicit_assumptions', 'solids', 'boolean', 'witnesses', 'flags', 'library_versions', 'figures', 'identity_sha256'}

def unsealed(record):
    return {key: value for key, value in record.items() if key != 'identity_sha256'}

def independent_union(records, library=None):
    """Rebuild Manifold from saved meshes only, then Add -- what a cold audit reader does."""
    library = library or __import__('manifold3d')
    solids = [_i35_solid_from_record(record, record['role']) for record in records]
    return library.Manifold.batch_boolean(solids, library.OpType.Add)

class RockEggPileTests(_i35_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.document, cls.artifacts = _i35_eggs.rock_eggs_build()
        cls.solids = cls.document['solids']
        cls.pile = cls.solids[_i35_eggs.PILE_ROLE]
        cls.solid = _i35_solid_from_record(cls.pile, 'pile')

    def test_at_least_seven_closed_eggs_are_saved_with_recomputable_identity(self):
        self.assertGreaterEqual(len(_i35_eggs.EGGS), 7)
        self.assertEqual(len(_i35_eggs.EGGS), 8)
        self.assertEqual(len(self.solids), len(_i35_eggs.EGGS) + 1)
        roles = set()
        for item in _i35_eggs.EGGS:
            record = self.solids[item.egg_id]
            self.assertEqual(record['schema'], _i35_SOLID_SCHEMA)
            self.assertEqual(record['role'], item.egg_id)
            self.assertTrue(record['sampled_not_native_exact'])
            self.assertGreater(record['signed_volume_m3'], 0.0)
            self.assertEqual(record['identity_sha256'], _i35_identity(unsealed(record)))
            self.assertEqual(record['local_origin_xyz_m'], _i35_eggs.ROCK_EGGS_LOCAL_ORIGIN.tolist())
            ideal = 4.0 / 3.0 * _i35_math.pi * item.radius_m ** 3
            self.assertGreater(record['signed_volume_m3'], ideal * 0.97)
            self.assertLess(record['signed_volume_m3'], ideal)
            roles.add(record['role'])
        self.assertEqual(len(roles), len(_i35_eggs.EGGS))
        radii = sorted((item.radius_m for item in _i35_eggs.EGGS))
        self.assertGreaterEqual(radii[-1] - radii[0], 1.0)
        self.assertGreaterEqual(len(set(radii)), 4)
        self.assertLessEqual(radii[-1], 3.0)

    def test_pile_union_is_closed_with_the_declared_component_census(self):
        components = _i35_census(self.solid)
        self.assertEqual(components, _i35_eggs.EXPECTED_COMPONENTS)
        self.assertEqual(self.document['assembly']['connected_components'], components)
        self.assertEqual(self.document['assembly']['connected_components_declared'], components)
        self.assertGreater(components, 1)
        self.assertLess(components, len(_i35_eggs.EGGS))
        self.assertGreater(self.document['assembly']['sum_of_parts_m3'], self.document['assembly']['signed_volume_m3'])
        self.assertEqual(self.document['assembly']['fill_rock_m3'], 0.0)
        self.assertEqual(self.document['assembly']['excavated_rock_m3'], 0.0)
        self.assertEqual(self.document['identity_sha256'], _i35_identity(unsealed(self.document)))

    def test_separated_pair_is_the_exact_sum_and_stacked_pair_really_merges(self):
        separated = self.document['witnesses']['separated_pair_union_is_exact_sum']
        stacked = self.document['witnesses']['stacked_pair_union_is_strictly_smaller']
        self.assertEqual(separated['method'], 'Mesh64_boolean')
        self.assertEqual(stacked['method'], 'Mesh64_boolean')
        self.assertTrue(separated['verdict'])
        self.assertTrue(stacked['verdict'])
        self.assertLessEqual(separated['observed']['relative_difference'], 1e-12)
        self.assertGreater(separated['observed']['analytic_surface_gap_m'], 0.0)
        self.assertEqual(separated['observed']['connected_components'], 2)
        self.assertLess(stacked['observed']['union_m3'], stacked['observed']['sum_of_parts_m3'] - 1e-06)
        self.assertLess(stacked['observed']['analytic_surface_gap_m'], 0.0)
        self.assertEqual(stacked['observed']['connected_components'], 1)
        for witness in (separated, stacked):
            chosen = [self.solids[role] for role in witness['cutter_roles']]
            union = independent_union(chosen)
            self.assertAlmostEqual(union.volume(), witness['observed']['union_m3'], places=9)
            self.assertAlmostEqual(union.volume(), witness['expected_union_m3'], places=9)
        sum_parts = separated['observed']['sum_of_parts_m3']
        self.assertAlmostEqual(sum_parts, sum((self.solids[role]['signed_volume_m3'] for role in separated['cutter_roles'])), places=9)

    def test_hover_void_is_outside_zero_overlap_and_open_to_free_space(self):
        winding = self.document['witnesses']['hover_void_midpoint_is_outside']
        reach = self.document['witnesses']['hover_void_is_open_to_free_space']
        clearance = self.document['witnesses']['hover_clearance_is_bracketed_by_two_surfaces']
        self.assertTrue(winding['verdict'])
        self.assertTrue(reach['verdict'])
        self.assertTrue(clearance['verdict'])
        self.assertEqual(winding['solid_role'], _i35_eggs.PILE_ROLE)
        self.assertFalse(winding['expected_inside'])
        self.assertLessEqual(abs(winding['observed']['winding']), _i35_eggs.WINDING_TOLERANCE)
        self.assertEqual(winding['observed']['probe_overlap_m3'], 0.0)
        self.assertEqual(reach['expected_hit_count'], 0)
        self.assertEqual(reach['observed']['hit_count'], 0)
        self.assertEqual(len(clearance['observed']['hits']), 2)
        measured = clearance['observed']['measured_mesh_clearance_m']
        self.assertGreater(measured, 0.0)
        self.assertGreaterEqual(measured, clearance['observed']['analytic_surface_gap_m'])
        self.assertLess(clearance['observed']['mesh_clearance_minus_analytic_gap_m'], 0.01)
        self.assertTrue(clearance['observed']['lateral_support']['actually_interpenetrates'])
        point = _i35_np.asarray(winding['point_xyz_m'], float)
        self.assertEqual(_i35_eggs.rock_eggs_winding_number(self.pile, point), winding['observed']['winding'])
        self.assertEqual(_i35_eggs.probe_overlap_m3(self.solid, point), 0.0)
        hits = _i35_ray_hits(self.solid, reach['from_xyz_m'], reach['to_xyz_m'], _i35_eggs.ROCK_EGGS_LOCAL_ORIGIN)
        self.assertEqual(len(hits), 0)
        axis = _i35_ray_hits(self.solid, clearance['from_xyz_m'], clearance['to_xyz_m'], _i35_eggs.ROCK_EGGS_LOCAL_ORIGIN)
        self.assertEqual(len(axis), 2)
        self.assertAlmostEqual(float(_i35_np.linalg.norm(_i35_np.asarray(axis[1]['position_xyz_m'], float) - _i35_np.asarray(axis[0]['position_xyz_m'], float))), measured, places=9)

    def test_bad_geometry_and_declared_shortfalls_are_refused(self):
        with self.assertRaises(ValueError):
            _i35_eggs.EggSpec('egg-x', (0.0, 0.0, 0.0), 4.0, 'cluster', 'too_tall')
        with self.assertRaises(ValueError):
            _i35_eggs.EggSpec('egg-x', (0.0, 0.0, 'z'), 2.0, 'cluster', 'not_a_number')
        with self.assertRaises(ValueError):
            _i35_eggs.EggSpec('egg-x', (0.0, 0.0, 0.0), 2.0, 'bogus_group', 'bad_group')
        with self.assertRaises(ValueError):
            _i35_eggs.EggSpec('', (0.0, 0.0, 0.0), 2.0, 'cluster', 'empty_id')
        records = _i35_eggs.build_records()
        with self.assertRaises(ValueError):
            _i35_combine(records, _i35_eggs.ROCK_EGGS_LOCAL_ORIGIN, 'bad', _i35_eggs.parameters(), minimum_components=_i35_eggs.EXPECTED_COMPONENTS + 1)
        with self.assertRaises(ValueError):
            _i35_combine(records, _i35_eggs.ROCK_EGGS_LOCAL_ORIGIN, 'bad', _i35_BooleanParameters(solids_spacing_m=1.0, component_limit=2), minimum_components=1)
        tampered = dict(self.pile)
        tampered['signed_volume_m3'] = tampered['signed_volume_m3'] + 1.0
        with self.assertRaises(ValueError):
            _i35_solid_from_record(tampered, 'tampered')

    def test_evidence_document_contract_is_cold_auditable_and_reproducible(self):
        document = self.document
        self.assertTrue(TEST_ROCK_EGGS_CONTRACT_KEYS.issubset(document.keys()))
        self.assertEqual(document['schema'], _i35_eggs.ROCK_EGGS_SCHEMA)
        self.assertEqual(document['algorithm'], _i35_eggs.ROCK_EGGS_ALGORITHM)
        self.assertEqual(document['status'], 'candidate')
        self.assertEqual(document['synthetic_base'], {'kind': 'synthetic_analytic', 'note': 'not TD native terrain, not surveyed'})
        self.assertEqual(set(document['flags']), set(_i35_FLAGS))
        self.assertTrue(all((value is False for value in document['flags'].values())))
        for flag in _i35_FLAGS:
            self.assertIs(document[flag], False)
        self.assertIn('manifold3d', document['library_versions'])
        self.assertIn('numpy', document['library_versions'])
        self.assertTrue(document['explicit_assumptions'])
        for entry in document['explicit_assumptions']:
            self.assertEqual(set(entry), {'name', 'value', 'grade', 'reason'})
            self.assertEqual(entry['grade'], 'assumed')
            self.assertTrue(entry['reason'])
        for name, witness in document['witnesses'].items():
            self.assertIn(witness['method'], ALLOWED_METHODS, name)
            self.assertIs(witness['verdict'], True, name)
            self.assertTrue(witness['claim'], name)
            self.assertIn('observed', witness, name)
            if witness['method'] == 'Mesh64_boolean':
                self.assertTrue(witness['cutter_roles'], name)
                for role in witness['cutter_roles']:
                    self.assertIn(role, document['solids'], name)
            else:
                self.assertIn(witness['solid_role'], document['solids'], name)
        self.assertEqual(document['boolean']['status'], 'candidate')
        self.assertEqual(document['boolean']['schema'], 'td-hybrid-rock-boolean-result-v1')
        second, _ = _i35_eggs.rock_eggs_build()
        self.assertEqual(_i35_eggs.write_canonical_bytes(second), _i35_eggs.write_canonical_bytes(document))
        self.assertEqual(second['identity_sha256'], document['identity_sha256'])

    def test_preview_writes_three_auditable_figures_and_a_compact_report(self):
        with _i35_tempfile.TemporaryDirectory() as directory:
            document, artifacts = _i35_eggs.rock_eggs_build()
            figures = _merged__i35_eggs_render_preview(artifacts['rock_after'], directory, artifacts['hover'])
            document['figures'] = figures
            from terrain_pipeline.hybrid_geometry import seal
            seal(document)
            report = _i35_Path(directory) / _i35_eggs.REPORT_NAME
            report.write_bytes(_i35_eggs.write_canonical_bytes(document))
            self.assertEqual(len(figures), 3)
            self.assertEqual(report.read_bytes(), _i35_eggs.write_canonical_bytes(document))
            raw = report.read_text(encoding='utf-8')
            self.assertEqual(len(raw.splitlines()), 1)
            reread = _i35_json.loads(raw)
            self.assertEqual(reread['identity_sha256'], document['identity_sha256'])
            self.assertEqual(reread['identity_sha256'], _i35_identity(unsealed(reread)))
            for figure in figures:
                path = _i35_Path(directory) / figure['path']
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 1000)
                self.assertEqual(len(figure['sha256']), 64)

def cold_manifold(record):
    """Rebuild one saved solid without the generator's helpers (cold-reader style)."""
    import manifold3d as manifold
    mesh = manifold.Mesh64(_i36_np.array(record['vertices_local_xyz_m'], dtype=_i36_np.float64, order='C', copy=True), _i36_np.array(record['triangles'], dtype=_i36_np.uint64, order='C', copy=True))
    solid = manifold.Manifold(mesh)
    if solid.status() != manifold.Error.NoError or solid.is_empty():
        raise AssertionError('saved solid is not a closed manifold: ' + str(record.get('role')))
    return solid

class SinkholeVolumeTests(_i36_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.record, cls.solids = _i36_build()

    def test_material_balance_and_one_connected_void(self):
        boolean = self.record['boolean']
        material, census = (boolean['material'], boolean['census'])
        self.assertEqual(self.record['schema'], _i36_SCHEMA)
        self.assertEqual(self.record['algorithm'], _i36_ALGORITHM)
        self.assertEqual(self.record['status'], 'candidate')
        self.assertEqual(self.record['synthetic_base'], {'kind': _i36_BASE_KIND, 'note': _i36_BASE_NOTE})
        self.assertEqual(material['rock_before_m3'], 576000.0)
        self.assertEqual(material['fill_rock_m3'], 0.0)
        self.assertEqual(material['exported_excavated_rock_m3'], material['excavated_rock_m3'])
        self.assertGreater(material['rock_after_m3'], 0.0)
        self.assertGreater(material['excavated_rock_m3'], 0.0)
        residual = material['rock_before_m3'] - material['rock_after_m3'] - material['excavated_rock_m3']
        self.assertLessEqual(abs(residual), material['balance_budget_m3'])
        self.assertAlmostEqual(residual, material['signed_residual_m3'], places=9)
        self.assertEqual(census['cutter_count'], len(_i36_CUTTER_ROLES))
        self.assertEqual(census['cutter_union_components'], 1)
        self.assertEqual(census['removed_components'], 1)
        self.assertEqual(census['rock_after_components'], 1)

    def test_every_solid_record_is_sealed_and_volume_accounted(self):
        self.assertEqual(sorted(self.solids), sorted(['rock_before', 'rock_after', 'removed', 'cutter_union', *_i36_CUTTER_ROLES]))
        for name, solid in self.solids.items():
            self.assertEqual(solid['schema'], _i36_SOLID_SCHEMA)
            self.assertEqual(solid['role'], name)
            self.assertTrue(solid['sampled_not_native_exact'])
            self.assertEqual(_i36_identity({key: value for key, value in solid.items() if key != 'identity_sha256'}), solid['identity_sha256'])
            self.assertGreater(solid['signed_volume_m3'], 0.0)
            self.assertEqual(self.record['solids'][name], solid)
        self.assertGreaterEqual(self.solids['cutter_union']['signed_volume_m3'], self.solids['subsurface_river']['signed_volume_m3'])
        self.assertLessEqual(self.solids['removed']['signed_volume_m3'], self.solids['cutter_union']['signed_volume_m3'])

    def test_skylight_and_single_surface_opening_are_measured_witnesses(self):
        witnesses = self.record['witnesses']
        open_axis = witnesses['skylight_axis_open_after_excavation']
        closed_axis = witnesses['skylight_axis_blocked_before_excavation']
        self.assertEqual(open_axis['method'], 'Manifold.ray_cast')
        self.assertEqual(open_axis['solid_role'], 'rock_after')
        self.assertEqual(open_axis['expected_hit_count'], 0)
        self.assertEqual(open_axis['observed']['hit_count'], 0)
        self.assertEqual(closed_axis['expected_hit_count'], 1)
        self.assertEqual(closed_axis['observed']['hit_count'], 1)
        self.assertEqual(closed_axis['observed']['first_hit_y_m'], 0.0)
        floor = witnesses['shaft_floor_is_the_buried_river_bed']
        self.assertEqual(floor['observed']['first_hit_y_m'], -36.0)
        open_samples = [entry for name, entry in witnesses.items() if name.startswith('collar_footprint_open_sample')]
        closed_samples = [entry for name, entry in witnesses.items() if name.startswith('outside_collar_surface_intact_sample')]
        self.assertGreaterEqual(len(open_samples), 3)
        self.assertGreaterEqual(len(closed_samples), 8)
        self.assertTrue(all((entry['observed']['hit_count'] == 0 for entry in open_samples)))
        self.assertTrue(all((entry['observed']['hit_count'] == 1 for entry in closed_samples)))
        self.assertTrue(all((entry['observed']['first_hit_y_m'] == 0.0 for entry in closed_samples)))
        self.assertTrue(all((entry['verdict'] is True for entry in witnesses.values())))
        for entry in witnesses.values():
            self.assertIn(entry['method'], ('Manifold.ray_cast', 'Solid.winding', 'Mesh64_boolean'))
        winding = witnesses['shaft_interior_is_void']
        self.assertEqual(winding['method'], 'Solid.winding')
        self.assertFalse(winding['expected_inside'])
        self.assertAlmostEqual(winding['observed']['winding'], 0.0, places=6)
        self.assertAlmostEqual(witnesses['intact_rock_mass_is_solid']['observed']['winding'], 1.0, places=6)

    def test_cold_recomputation_from_saved_solids_matches_the_witnesses(self):
        import manifold3d as manifold
        solids = self.record['solids']
        rock = cold_manifold(solids['rock_before'])
        cutters = [cold_manifold(solids[role]) for role in _i36_CUTTER_ROLES]
        union = manifold.Manifold.batch_boolean(cutters, manifold.OpType.Add)
        after = rock - union
        removed = rock ^ union
        entry = self.record['witnesses']['material_balance_actual_volume']
        self.assertEqual(entry['method'], 'Mesh64_boolean')
        self.assertEqual(entry['operation'], 'subtract')
        self.assertEqual(entry['cutter_roles'], list(_i36_CUTTER_ROLES))
        self.assertAlmostEqual(after.volume(), entry['expected_rock_after_m3'], places=6)
        self.assertAlmostEqual(removed.volume(), entry['expected_removed_m3'], places=6)
        union_saved = entry['observed']['cutter_union_m3']
        self.assertLess(abs(union.volume() - union_saved) / union_saved, 1e-08)
        for name, witness in self.record['witnesses'].items():
            if witness['method'] != 'Solid.winding':
                continue
            recomputed = _i36_solid_winding(solids[witness['solid_role']], witness['point_xyz_m'], self.record['local_origin_xyz_m'])
            self.assertAlmostEqual(recomputed, witness['observed']['winding'], places=9)
            self.assertEqual(recomputed > 0.5, witness['expected_inside'])

    def test_identical_input_gives_identical_identity(self):
        first, first_solids = _i36_build(_i36_SinkholeParameters(), _i36_LOCAL_ORIGIN)
        second, second_solids = _i36_build(_i36_SinkholeParameters(), _i36_np.array(_i36_LOCAL_ORIGIN, float))
        self.assertEqual(first['identity_sha256'], second['identity_sha256'])
        self.assertEqual(first['identity_sha256'], self.record['identity_sha256'])
        self.assertEqual(first_solids['rock_after']['identity_sha256'], self.solids['rock_after']['identity_sha256'])
        unsigned = {key: value for key, value in first.items() if key != 'identity_sha256'}
        self.assertEqual(_i36_identity(unsigned), first['identity_sha256'])

    def test_every_capability_flag_is_false_and_audit_passes(self):
        self.assertEqual(sorted(self.record['flags']), sorted(_i36_FLAGS))
        self.assertTrue(all((self.record['flags'][flag] is False for flag in _i36_FLAGS)))
        self.assertTrue(all((self.record['boolean'][flag] is False for flag in _i36_FLAGS)))
        self.assertEqual(self.record['boolean']['status'], 'candidate')
        self.assertEqual(self.record['boolean']['rejection_reasons'], [])
        report = _i36_audit(self.record)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['identity_sha256'], self.record['identity_sha256'])
        self.assertIn('material_balance', report['checks'])

    def test_tampered_or_promoted_record_is_refused(self):
        promoted = _i36_json.loads(_i36_json.dumps(self.record))
        promoted['flags']['hydraulic_ready'] = True
        promoted.pop('identity_sha256')
        promoted['identity_sha256'] = _i36_identity(promoted)
        with self.assertRaises(ValueError):
            _i36_audit(promoted)
        forged = _i36_json.loads(_i36_json.dumps(self.record))
        forged['boolean']['material']['excavated_rock_m3'] += 1.0
        forged.pop('identity_sha256')
        with self.assertRaises(ValueError):
            _i36_audit(forged)
        broken_seal = _i36_json.loads(_i36_json.dumps(self.record))
        broken_seal['solids']['rock_after']['identity_sha256'] = '0' * 64
        broken_seal.pop('identity_sha256')
        broken_seal['identity_sha256'] = _i36_identity(broken_seal)
        with self.assertRaises(ValueError):
            _i36_audit(broken_seal)

    def test_out_of_range_and_degenerate_parameters_are_refused(self):
        baseline = {field: getattr(_i36_SinkholeParameters(), field) for field in _i36_SinkholeParameters.__dataclass_fields__}
        cases = ({'shaft_collar_y_m': -1.0}, {'shaft_radius_top_m': 12.0}, {'shaft_radius_top_m': 80.0}, {'river_bed_y_m': -41.0}, {'river_ceiling_y_m': -35.99}, {'river_ceiling_y_m': 0.5}, {'shaft_bottom_y_m': -27.0}, {'upper_terrace_top_y_m': 1.0}, {'lower_terrace_top_y_m': -8.5}, {'lower_terrace_top_y_m': -33.0}, {'river_reach_x_m': 61.0}, {'river_reach_x_m': 4.0}, {'branch_x_high_m': -30.0}, {'branch_z_end_m': 61.0}, {'branch_z_low_m': 6.0}, {'river_half_width_m': float('nan')}, {'shaft_segments': 8}, {'terrace_segments': 600})
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    _i36_SinkholeParameters(**{**baseline, **change})
        with self.assertRaises(ValueError):
            _i36_build(_i36_SinkholeParameters(), [1.0, 2.0])
        with self.assertRaises(ValueError):
            _i36_build('not parameters')
        with self.assertRaises(ValueError):
            _i36_solid_winding(self.solids['rock_after'], [40.0, -20.0, 40.0], [0.0, float('nan'), 0.0])

    def test_explicit_assumptions_are_graded_and_named(self):
        entries = _i36_assumption_list(_i36_SinkholeParameters())
        self.assertEqual(len(entries), len(_i36_EXPLICIT_ASSUMPTIONS))
        self.assertEqual(self.record['explicit_assumptions'], entries)
        self.assertTrue(all((entry['grade'] == 'assumed' for entry in entries)))
        self.assertTrue(all((entry['reason'] for entry in entries)))
        names = [entry['name'] for entry in entries]
        self.assertEqual(names, sorted(names))
        self.assertEqual(self.record['source_grade'], 'no_ledger_source_for_any_dimension_here')

    def test_preview_report_is_compact_and_byte_identical(self):
        with _i36_tempfile.TemporaryDirectory() as first, _i36_tempfile.TemporaryDirectory() as second:
            report = _i36_write_preview(first)
            _i36_write_preview(second)
            payload = (_i36_Path(first) / 'report.json').read_bytes()
            self.assertEqual(payload, (_i36_Path(second) / 'report.json').read_bytes())
            self.assertNotIn(b'\n', payload)
            self.assertNotIn(b'NaN', payload)
            saved = _i36_json.loads(payload.decode('utf-8'))
            self.assertEqual(saved['identity_sha256'], report['identity_sha256'])
            unsigned = {key: value for key, value in saved.items() if key != 'identity_sha256'}
            self.assertEqual(_i36_identity(unsigned), saved['identity_sha256'])
            self.assertEqual([figure['name'] for figure in saved['figures']], ['sinkhole-a-plan.png', 'sinkhole-b-profile.png', 'sinkhole-c-solid.png'])
            for figure in saved['figures']:
                self.assertEqual(figure['path'], figure['name'])
                self.assertEqual(len(figure['sha256']), 64)
                self.assertTrue((_i36_Path(first) / figure['name']).is_file())
            self.assertEqual(saved['status'], 'candidate')
            self.assertEqual(saved['library_versions']['manifold3d'], '3.5.4')
            self.assertTrue(all((saved['flags'][flag] is False for flag in _i36_FLAGS)))
            self.assertEqual(_i36_audit(saved)['status'], 'passed')
if str(ROOT) not in _i37_sys.path:
    _i37_sys.path.insert(0, str(ROOT))

class FlaredBaseTests(_i37_unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.record, cls.geometry = _i37_flare.uluru_flare_report()
        cls.solid = cls.geometry['solid']
        cls.origin = cls.geometry['origin']
        cls.parameters = cls.geometry['parameters']
        cls.solids = cls.record['solids']

    def test_report_is_candidate_with_every_flag_false(self):
        record = self.record
        self.assertEqual(record['status'], 'candidate')
        self.assertEqual(record['schema'], _i37_flare.ULURU_FLARE_REPORT_SCHEMA)
        self.assertEqual(record['algorithm'], _i37_flare.ULURU_FLARE_ALGORITHM)
        self.assertEqual(record['synthetic_base']['kind'], 'synthetic_analytic')
        self.assertEqual(set(record['flags']), set(_i37_FLAGS))
        self.assertTrue(record['flags'])
        self.assertFalse(any(record['flags'].values()))
        for role in (_i37_flare.SKIRT_ROLE, _i37_flare.BODY_ROLE, _i37_flare.ULURU_FLARE_SOLID_ROLE):
            self.assertTrue(self.solids[role]['sampled_not_native_exact'])

    def test_report_identity_recomputes_and_encoding_is_deterministic(self):
        record = self.record
        self.assertEqual(record['identity_sha256'], _i37_flare.uluru_flare_report_identity(record))
        first = record['solids'][_i37_flare.ULURU_FLARE_SOLID_ROLE]
        self.assertEqual(first['identity_sha256'], _i37_identity({key: value for key, value in first.items() if key != 'identity_sha256'}))
        again, _ = _i37_flare.uluru_flare_report()
        self.assertEqual(_i37_flare.encode_report(again), _i37_flare.encode_report(record))
        self.assertEqual(again['identity_sha256'], record['identity_sha256'])
        self.assertNotIn(b'\n', _i37_flare.encode_report(record))

    def test_union_volume_matches_the_two_input_bodies(self):
        skirt = self.solids[_i37_flare.SKIRT_ROLE]
        body = self.solids[_i37_flare.BODY_ROLE]
        union = self.solids[_i37_flare.ULURU_FLARE_SOLID_ROLE]
        measured = float(self.solid.volume())
        self.assertAlmostEqual(measured, union['signed_volume_m3'], delta=1e-06)
        overlap = skirt['signed_volume_m3'] + body['signed_volume_m3'] - union['signed_volume_m3']
        self.assertGreater(overlap, 0.0)
        self.assertLess(overlap, min(skirt['signed_volume_m3'], body['signed_volume_m3']))
        self.assertEqual(_i37_census(self.solid), 1)
        self.assertEqual(self.record['boolean']['census']['assembled_components'], 1)

    def test_every_solid_record_is_closed_and_volume_gated(self):
        for role, mesh in self.solids.items():
            self.assertEqual(mesh['schema'], 'td-hybrid-local-solid-mesh-v1')
            rebuilt = _i37_solid_from_record(mesh, role)
            self.assertAlmostEqual(float(rebuilt.volume()), mesh['signed_volume_m3'], delta=1e-06)
        tampered = _i37_json.loads(_i37_json.dumps(self.solids[_i37_flare.ULURU_FLARE_SOLID_ROLE]))
        tampered['signed_volume_m3'] += 1.0
        with self.assertRaises(ValueError):
            _i37_solid_from_record(tampered, 'tampered')

    def test_overhang_point_is_outside_and_controls_are_not_vacuous(self):
        witnesses = self.record['witnesses']
        for name in ('overhang_point_outside_union', 'control_point_inside_tower', 'control_point_far_outside'):
            witness = witnesses[name]
            self.assertEqual(witness['method'], 'Solid.winding')
            self.assertEqual(witness['solid_role'], _i37_flare.ULURU_FLARE_SOLID_ROLE)
            self.assertTrue(witness['verdict'], name)
            self.assertTrue(self.solids[witness['solid_role']]['identity_sha256'])
            inside, winding = _i37_flare.uluru_flare_inside_by_winding(self.solids[witness['solid_role']], witness['point_xyz_m'], self.origin)
            self.assertEqual(inside, witness['observed']['inside'])
            self.assertEqual(inside, witness['expected_inside'])
            self.assertAlmostEqual(witness['observed']['winding'], 1.0 if inside else 0.0, places=9)
            if not inside:
                self.assertLess(abs(witness['observed']['winding']), 1e-09)
                self.assertEqual(witness['probe_cube_intersection_volume_m3'], 0.0)
            else:
                self.assertGreater(witness['probe_cube_intersection_volume_m3'], 0.0)
        far = witnesses['control_point_far_outside']['point_xyz_m']
        self.assertAlmostEqual(far[0], float(self.origin[0]) + self.parameters.tower_base_radius_m + self.parameters.overhang_amplitude_m + 100.0)
        under = witnesses['overhang_point_outside_union']['point_xyz_m']
        self.assertGreater(under[0] - float(self.origin[0]), self.parameters.skirt_outer_radius_m)
        self.assertLess(under[0] - float(self.origin[0]), self.parameters.tower_base_radius_m)
        self.assertLess(under[1], self.parameters.skirt_top_elevation_m)

    def test_winding_number_is_an_independent_containment_oracle(self):
        mesh = self.solids[_i37_flare.ULURU_FLARE_SOLID_ROLE]
        origin = self.origin
        corner = _i37_np.asarray(mesh['vertices_local_xyz_m'], float).max(axis=0) + _i37_np.asarray(origin, float) + 5.0
        winding = _i37_flare.uluru_flare_winding_number(mesh['vertices_local_xyz_m'], mesh['triangles'], corner, origin)
        self.assertAlmostEqual(winding, 0.0, places=9)
        centre = [float(origin[0]), self.parameters.total_height_m * 0.5, float(origin[2])]
        self.assertTrue(_i37_flare.uluru_flare_inside_by_winding(mesh, centre, origin)[0])
        beside = [centre[0] + self.parameters.tower_base_radius_m + 50.0, centre[1], centre[2]]
        self.assertAlmostEqual(_i37_flare.uluru_flare_winding_number(mesh['vertices_local_xyz_m'], mesh['triangles'], beside, origin), 0.0, places=9)
        self.assertFalse(_i37_flare.uluru_flare_inside_by_winding(mesh, beside, origin)[0])

    def test_ray_witnesses_cross_void_then_hit_rock(self):
        witnesses = self.record['witnesses']
        for name in ('vertical_ray_crosses_void_then_hits_rock', 'horizontal_ray_crosses_void_then_hits_rock'):
            witness = witnesses[name]
            self.assertEqual(witness['method'], 'Manifold.ray_cast')
            self.assertTrue(witness['verdict'], name)
            hits = _i37_ray_hits(self.solid, witness['from_xyz_m'], witness['to_xyz_m'], self.origin)
            self.assertEqual(len(hits), witness['expected_hit_count'])
            self.assertEqual(len(hits), witness['observed']['hit_count'])
            hit = _i37_np.array(hits[0]['position_xyz_m'], float)
            from_xyz = _i37_np.array(witness['from_xyz_m'], float)
            self.assertGreater(_i37_np.linalg.norm(hit - from_xyz), 1.0)
            self.assertGreater(_i37_flare.uluru_flare_contains_point(self.solid, hit + (hit - from_xyz) / _i37_np.linalg.norm(hit - from_xyz) * 0.01, self.origin), 0.0)

    def test_vertical_ray_endpoint_is_inside_the_tower(self):
        witness = self.record['witnesses']['vertical_ray_crosses_void_then_hits_rock']
        endpoint = witness['to_xyz_m']
        self.assertGreater(_i37_flare.uluru_flare_contains_point(self.solid, endpoint, self.origin), 0.0)
        start = witness['from_xyz_m']
        self.assertAlmostEqual(_i37_flare.uluru_flare_contains_point(self.solid, start, self.origin), 0.0, delta=1e-12)
        self.assertLess(start[1], self.parameters.skirt_top_elevation_m)
        self.assertGreater(start[1], 0.0)

    def test_overhang_amplitude_and_slopes_are_positive_and_consistent(self):
        parameters = self.parameters
        amplitude = parameters.tower_base_radius_m - parameters.skirt_outer_radius_m
        self.assertAlmostEqual(parameters.overhang_amplitude_m, amplitude)
        self.assertGreater(amplitude, 0.0)
        self.assertTrue(0.0 < parameters.tower_top_radius_m < parameters.tower_base_radius_m)
        self.assertGreater(parameters.tower_side_slope_deg, 0.0)
        self.assertGreater(parameters.skirt_wall_slope_deg, 0.0)
        self.assertGreater(parameters.skirt_top_elevation_m, parameters.tower_base_elevation_m)
        for name in ('overhang_amplitude_m', 'skirt_height_m', 'skirt_wall_slope_deg', 'tower_side_slope_deg', 'total_height_m'):
            entry = [item for item in self.record['explicit_assumptions'] if item['name'] == name]
            self.assertEqual(len(entry), 1, name)
            self.assertEqual(entry[0]['grade'], 'assumed')
        conflict = self.record['height_conflict']
        self.assertEqual(conflict['resolution'], 'unresolved')
        self.assertEqual(sorted(conflict['published_m']), [335.0, 348.0])
        self.assertEqual(conflict['chosen_m'], 348.0)
        derived = self.record['derived']
        declared = {item['name']: item['value'] for item in self.record['explicit_assumptions']}
        self.assertAlmostEqual(declared['overhang_amplitude_m'], derived['overhang_amplitude_m'], places=6)
        self.assertAlmostEqual(declared['skirt_wall_slope_deg'], derived['skirt_wall_slope_deg'], places=3)
        self.assertAlmostEqual(declared['tower_side_slope_deg'], derived['tower_side_slope_deg'], places=3)
        self.assertAlmostEqual(declared['skirt_height_m'], parameters.skirt_top_elevation_m, places=9)
        self.assertAlmostEqual(declared['total_height_m'], parameters.total_height_m, places=9)
        self.assertEqual(self.record['world_frame'], _i37_flare.WORLD_FRAME_NOTE)
        self.assertEqual(self.record['figure_scope'], _i37_flare.FIGURE_SCOPE)
        self.assertEqual(self.record['parent_algorithm'], _i37_flare.ULURU_FLARE_PARENT_ALGORITHM)

    def test_parameters_refuse_incoherent_geometry(self):
        with self.assertRaises(ValueError):
            _i37_flare.FlareParameters(total_height_m=5.0)
        with self.assertRaises(ValueError):
            _i37_flare.FlareParameters(tower_top_radius_m=200.0)
        with self.assertRaises(ValueError):
            _i37_flare.FlareParameters(skirt_outer_radius_m=180.0)
        with self.assertRaises(ValueError):
            _i37_flare.FlareParameters(skirt_top_elevation_m=5.0)
        with self.assertRaises(ValueError):
            _i37_flare.FlareParameters(tower_segments=2)
        with self.assertRaises(ValueError):
            _i37_flare.FlareParameters(total_height_m=348)
        with self.assertRaises(ValueError):
            _i37_flare.uluru_flare_build('not parameters')
        self.assertEqual(_i37_flare.FlareParameters().total_height_m, 348.0)

    def test_plane_section_returns_actual_mesh_crossings(self):
        mesh = self.solids[_i37_flare.ULURU_FLARE_SOLID_ROLE]
        value = float(self.origin[2])
        segments = _i37_flare.uluru_flare_plane_section_segments(mesh, 2, value)
        self.assertGreater(len(segments), 20)
        for first, second in segments:
            for point in (first, second):
                self.assertEqual(len(point), 2)
                self.assertTrue(_i37_np.isfinite(point).all())
        radii = [abs(float(point[0]) - float(self.origin[0])) for pair in segments for point in pair]
        self.assertGreater(max(radii), self.parameters.tower_base_radius_m * 0.5)

    def test_report_json_matches_the_shared_contract_and_is_reproducible(self):
        import tempfile
        required = {'schema', 'algorithm', 'status', 'synthetic_base', 'parameters', 'explicit_assumptions', 'solids', 'boolean', 'witnesses', 'flags', 'library_versions', 'figures', 'identity_sha256'}
        self.assertTrue(required <= set(self.record))
        self.assertEqual(self.record['status'], 'candidate')
        for item in self.record['explicit_assumptions']:
            self.assertEqual(sorted(item), ['grade', 'name', 'reason', 'value'])
            self.assertEqual(item['grade'], 'assumed')
        for role, mesh in self.record['solids'].items():
            self.assertTrue({'schema', 'role', 'local_origin_xyz_m', 'vertices_local_xyz_m', 'triangles', 'signed_volume_m3', 'sampled_not_native_exact', 'identity_sha256'} <= set(mesh))
            self.assertEqual(mesh['role'], role)
        for witness in self.record['witnesses'].values():
            self.assertIn(witness['method'], ('Manifold.ray_cast', 'Solid.winding', 'Mesh64_boolean'))
            self.assertIn('verdict', witness)
            self.assertIn('claim', witness)
        with tempfile.TemporaryDirectory() as folder:
            first = _i37_flare.uluru_flare_write_report(_i37_Path(folder) / 'report.json')
            written = (_i37_Path(folder) / 'report.json').read_bytes()
            self.assertNotIn(b'\n', written)
            self.assertEqual(written, _i37_flare.encode_report(first))
            self.assertEqual(first['identity_sha256'], self.record['identity_sha256'])
            self.assertEqual(first['figures'], [])

    def test_rendered_figures_are_hashed_and_reported(self):
        import hashlib
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            panels = _merged__i37_flare_uluru_flare_render(self.solids[_i37_flare.ULURU_FLARE_SOLID_ROLE], self.parameters, _i37_Path(folder))
            self.assertEqual(len(panels), 3)
            for panel in panels:
                path = _i37_Path(panel['path'])
                self.assertTrue(path.exists())
                self.assertEqual(panel['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
_i38_sys.path.insert(0, str(ROOT))
NATIVE_SHAPE = (256, 256)
NATIVE_ORIGIN = [-184320.0, 61440.0]
REAL_HIERARCHY = ROOT / _i38_preview.SOURCE_PATH

def select(**overrides):
    kwargs = dict(center_m_xz=[-177600.0, 67680.0], size_m_xz=[960.0, 960.0], spacing_m=4.0, native_shape=NATIVE_SHAPE, native_origin_m_xz=NATIVE_ORIGIN, max_growth_m=60.0)
    kwargs.update(overrides)
    return _i38_select_native_window(**kwargs)

class SelectWindowTests(_i38_unittest.TestCase):

    def test_full_grid_request_is_already_on_the_lattice(self):
        window = select()
        self.assertEqual(window['schema'], _i38_SCHEMA)
        self.assertEqual(window['algorithm'], _i38_ALGORITHM)
        self.assertEqual(window['native_window'], [208, 240, 192, 224])
        self.assertEqual(window['native_span_cells_xz'], [32, 32])
        self.assertEqual(window['fine_shape_zx'], [240, 240])
        self.assertEqual(window['maximum_snap_observed_m'], 0.0)
        self.assertEqual(window['growth_m'], [0.0, 0.0])
        self.assertEqual(window['actual_size_m_xz'], [960.0, 960.0])
        self.assertEqual(window['corner_origin_m_xz'], [-178080.0, 67200.0])

    def test_off_lattice_request_snaps_outward_and_reports_the_offset(self):
        window = select(center_m_xz=[-177610.0, 67690.0], size_m_xz=[930.0, 930.0], max_growth_m=60.0)
        self.assertEqual(window['native_window'], [208, 240, 192, 224])
        for value in window['snap_m']:
            self.assertGreaterEqual(value, 0.0)
            self.assertLess(value, _i38_NATIVE_SPACING_M)
        self.assertAlmostEqual(window['maximum_snap_observed_m'], 25.0)
        self.assertAlmostEqual(window['maximum_snap_observed_m'], max(window['snap_m']))
        self.assertEqual(window['growth_m'], [30.0, 30.0])
        self.assertAlmostEqual(window['maximum_growth_observed_m'], 30.0)
        self.assertAlmostEqual(window['requested_size_m_xz'][0], 930.0)

    def test_growth_beyond_the_declared_maximum_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[924.0, 924.0], max_growth_m=_i38_NATIVE_SPACING_M)
        message = str(caught.exception)
        self.assertIn('would grow by 36 m', message)
        self.assertIn('maximum', message)
        with self.assertRaises(ValueError):
            select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[924.0, 924.0], max_growth_m=None)
        relaxed = select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[924.0, 924.0], max_growth_m=36.0)
        self.assertEqual(relaxed['native_window'], [208, 240, 192, 224])
        self.assertAlmostEqual(relaxed['maximum_growth_observed_m'], 36.0)

    def test_realised_window_always_covers_the_request(self):
        accepted = ((900.0, 0.0), (924.0, 0.0), (924.0, 29.0), (930.0, 0.0), (930.0, 7.0), (930.0, 29.0), (960.0, 0.0))
        for size, offset in accepted:
            with self.subTest(size=size, offset=offset):
                center = [-177600.0 + offset, 67680.0 + offset]
                window = select(center_m_xz=center, size_m_xz=[size, size], max_growth_m=60.0)
                self.assertGreaterEqual(window['actual_size_m_xz'][0], size)
                self.assertGreaterEqual(window['actual_size_m_xz'][1], size)
                self.assertLessEqual(window['maximum_growth_observed_m'], 60.0)
                for axis in (0, 1):
                    origin = window['corner_origin_m_xz'][axis]
                    realised = window['actual_size_m_xz'][axis]
                    requested_low = center[axis] - size / 2.0
                    requested_high = center[axis] + size / 2.0
                    self.assertLessEqual(origin, requested_low + 1e-06)
                    self.assertGreaterEqual(origin + realised, requested_high - 1e-06)

    def test_window_leaving_the_native_extent_is_refused(self):
        for center in ([-184300.0, 67680.0], [0.0, 0.0], [-100000.0, 61200.0]):
            with self.subTest(center=center):
                with self.assertRaises(ValueError):
                    select(center_m_xz=center, size_m_xz=[960.0, 960.0])

    def test_spacing_must_be_one_of_the_declared_fine_ladders(self):
        for spacing in (0.5, 3.0, 8.0, 30.0, '1'):
            with self.subTest(spacing=spacing):
                with self.assertRaises(ValueError):
                    select(spacing_m=spacing)
        for spacing, size in ((1.0, 240.0), (2.0, 480.0), (4.0, 960.0)):
            with self.subTest(spacing=spacing):
                window = select(spacing_m=spacing, size_m_xz=[size, size])
                self.assertEqual(window['spacing_m'], spacing)
                self.assertEqual(window['fine_shape_zx'], [_i38_MAX_FINE_SIDE, _i38_MAX_FINE_SIDE])
                self.assertEqual(window['fine_cells'], _i38_MAX_FINE_SIDE ** 2)
                self.assertLessEqual(window['fine_cells'], _i38_MAX_FINE_CELLS)
                self.assertEqual(window['actual_size_m_xz'], [size, size])
        for spacing, size in ((1.0, 480.0), (2.0, 960.0)):
            with self.subTest(spacing=spacing):
                with self.assertRaises(ValueError):
                    select(spacing_m=spacing, size_m_xz=[size, size])

    def test_fine_cell_budget_is_refused_with_the_stitch_hint(self):
        with self.assertRaises(ValueError) as caught:
            select(size_m_xz=[960.0, 960.0], spacing_m=1.0, max_growth_m=60.0)
        message = str(caught.exception)
        self.assertIn('fine window would need', message)
        self.assertIn('stitch', message)

    def test_non_integral_cell_count_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            select(center_m_xz=[-177593.0, 67687.0], size_m_xz=[900.0, 900.0], spacing_m=4.0, max_growth_m=60.0)
        self.assertIn('whole number', str(caught.exception))
        on_lattice = select(center_m_xz=[-177600.0, 67680.0], size_m_xz=[900.0, 900.0], spacing_m=4.0, max_growth_m=60.0)
        self.assertEqual(on_lattice['native_window'], [209, 239, 193, 223])
        self.assertEqual(on_lattice['fine_shape_zx'], [225, 225])

    def test_degenerate_and_malformed_requests_are_refused(self):
        with self.assertRaises(ValueError):
            select(size_m_xz=[960.0, 0.0])
        with self.assertRaises(ValueError):
            select(size_m_xz=[960.0, -1.0])
        with self.assertRaises(ValueError):
            select(size_m_xz=[960.0])
        with self.assertRaises(ValueError):
            select(center_m_xz=[float('nan'), 67680.0])
        with self.assertRaises(ValueError):
            select(native_shape=(256, 256, 1))
        with self.assertRaises(ValueError):
            select(native_shape=(2, 256))
        with self.assertRaises(ValueError):
            select(native_origin_m_xz=[0.0])
        with self.assertRaises(ValueError):
            select(size_m_xz=[20.0, 20.0], spacing_m=4.0, max_growth_m=_i38_NATIVE_SPACING_M)
        snapped = select(size_m_xz=[30.0, 30.0], spacing_m=4.0, max_growth_m=_i38_NATIVE_SPACING_M)
        self.assertEqual(snapped['native_span_cells_xz'], [2, 2])
        self.assertEqual(snapped['fine_shape_zx'], [15, 15])
        self.assertAlmostEqual(snapped['maximum_growth_observed_m'], 30.0)
        with self.assertRaises(ValueError):
            select(size_m_xz=[240.0, 240.0], spacing_m=1.0, max_growth_m=0.0)

class _FakeHierarchy:
    """Stand-in that refuses to be consumed as a hierarchy.

    The chart contract must reject a malformed window, spacing or channel selection *before*
    it hands anything to the shared bed builder. If a bad input slips through, this object
    raises AssertionError from the build path instead of returning a plausible record, so the
    test fails loudly rather than passing on a wrong success.
    """

    def __init__(self, rows, cols):
        self.arrays = {'height_m': _i38_np.zeros((rows, cols), dtype=_i38_np.float64)}
        self.metadata = {'origin_m_xz': list(NATIVE_ORIGIN)}

    def __getitem__(self, key):
        raise AssertionError('the bed builder must not run for a refused chart request')

class BuildChartTests(_i38_unittest.TestCase):

    def test_chart_contract_rejects_mismatched_records(self):
        window = select()
        empty = _i38_np.zeros((0, 2), dtype=_i38_np.int64)
        for mutation in ({'schema': 'other'}, {'schema': _i38_SCHEMA, 'native_window': [32, 64, 32], 'spacing_m': 4.0}, {'schema': _i38_SCHEMA, 'native_window': [32.0, 64.0, 32.0, 64.0], 'spacing_m': 4.0}):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    _i38_build_td_form_chart(_FakeHierarchy(256, 256), window=mutation, spacing_m=4.0, source_hierarchy_sha256='a' * 64, selected_edge_cell_ids=empty)
        with self.assertRaises(ValueError):
            _i38_build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=2.0, source_hierarchy_sha256='a' * 64, selected_edge_cell_ids=empty)
        with self.assertRaises(ValueError):
            _i38_build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=4.0, source_hierarchy_sha256='a' * 64, selected_edge_cell_ids=empty, channel_policy='keep')

    def test_channel_selection_must_be_an_explicit_int64_edge_array(self):
        window = select()
        for bad in (None, _i38_np.zeros((2, 2), dtype=_i38_np.int32), _i38_np.zeros((2,), dtype=_i38_np.int64), _i38_np.zeros((2, 3), dtype=_i38_np.int64)):
            with self.subTest(selected=repr(bad)):
                with self.assertRaises(ValueError):
                    _i38_build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=4.0, source_hierarchy_sha256='a' * 64, selected_edge_cell_ids=bad)
        empty = _i38_np.zeros((0, 2), dtype=_i38_np.int64)
        self.assertEqual(_i38_np.asarray([[1, 2]]).dtype, _i38_np.int64)
        with self.assertRaises(AssertionError):
            _i38_build_td_form_chart(_FakeHierarchy(256, 256), window=window, spacing_m=4.0, source_hierarchy_sha256='a' * 64, selected_edge_cell_ids=empty)

    def test_channel_policy_whitelist_is_declared(self):
        self.assertEqual(_i38_CHANNEL_POLICIES, ('reject', 'protect'))

class EndToEndTests(_i38_unittest.TestCase):
    """The declared ladder over the pinned hierarchy: bed -> chart -> form -> preview.

    These cases read the 16 MB pinned hierarchy and run the real fine bed builder, so they
    are slower than the contract tests above. They are the only place where the declared
    foot elevation (the fix for the silent all-zero form) is exercised against a real bed.
    """

    @classmethod
    def setUpClass(cls):
        cls.hierarchy = _i38_load_basin_hierarchy(path=str(REAL_HIERARCHY), expected_sha256=_i38_preview.SOURCE['expected_sha256'], expected_identity=_i38_preview.SOURCE['expected_identity'])

    def test_declared_ladder_covers_real_bed_and_is_replayable(self):
        with _i38_tempfile.TemporaryDirectory() as folder:
            output = _i38_Path(folder)
            self.assertEqual(_i38_preview._entry_preview_td_special_terrain(['--output', str(output)]), 0)
            first = {entry.name: _i38_file_sha256(entry) for entry in output.iterdir()}
            self.assertEqual(set(first), {'report.json', 'volcanic_plug-td-bundle.npz', 'volcanic_plug-td-a-plan.png', 'volcanic_plug-td-b-profile.png', 'volcanic_plug-td-c-solid.png', 'karst_tower_field-td-bundle.npz', 'karst_tower_field-td-a-plan.png', 'karst_tower_field-td-b-profile.png', 'karst_tower_field-td-c-solid.png'})
            report = _i38_json.loads((output / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(set(report['cases']), {'volcanic_plug', 'karst_tower_field'})
            self.assertFalse(report['claims']['real_terrain_reconstruction'])
            self.assertFalse(report['claims']['foot_elevation_surveyed'])
            self.assertTrue(report['claims']['preset_foot_is_synthetic'])
            self.assertFalse(report['claims']['excavation_modelled'])
            for flag in _i38_preview.ALL_FLAGS:
                self.assertFalse(report['claims'][flag])
            for kind, case in report['cases'].items():
                with self.subTest(kind=kind):
                    self.assertGreater(case['max_relief_m'], 0.0)
                    self.assertLess(case['max_relief_m'], 2.0 * 1000.0)
                    self.assertEqual(case['collar_max_abs_m'], 0.0)
                    self.assertFalse(any(case['declared_flags'].values()))
                    self.assertEqual(case['form_algorithm'], 'special-terrain-field-forms-v1')
                    self.assertEqual(case['adapter_schema'], _i38_SCHEMA)
                    self.assertEqual(case['base'], 'td_fine_bed')
                    placement = case['placement']
                    foot = placement['declared_foot_elevation_m']
                    self.assertGreater(foot, 0.0)
                    self.assertLessEqual(foot, placement['window_bed_max_m'])
                    self.assertEqual(foot, placement['window_bed_min_m'])
                    for value in placement['nominal_footprint_bed_min_m']:
                        self.assertGreaterEqual(value, foot)
                    chain = case['chart_record']['identity_chain']
                    self.assertEqual(chain['fine_bed_identity'], chain['chart_source_identity'])
                    self.assertEqual(chain['source_hierarchy_identity'], _i38_preview.SOURCE['expected_identity'])
                    bundle = output / case['file']
                    self.assertEqual(_i38_file_sha256(bundle), case['sha256'])
                    loaded = _i38_load_special_form_vdm(bundle, expected_sha256=case['sha256'], expected_identity=case['identity_sha256'])
                    self.assertEqual(loaded['metadata']['base'], 'td_fine_bed')
                    self.assertEqual(loaded['metadata']['source_identity'], chain['chart_source_identity'])
                    for target in loaded['metadata']['recipe']['targets']:
                        self.assertEqual(target['base_elevation_m'], foot)
                    self.assertEqual(float(_i38_np.max(loaded['arrays']['displacement_xyz_m'][:, :, 1])), case['max_relief_m'])
            self.assertEqual({entry.name: _i38_file_sha256(entry) for entry in output.iterdir()}, first)

    def test_declared_foot_reproduces_the_form_over_the_raw_chart(self):
        window = _i38_select_native_window(center_m_xz=_i38_preview.WINDOW_CENTER_M_XZ, size_m_xz=[_i38_preview.WINDOW_SIZE_M] * 2, spacing_m=4.0, native_shape=self.hierarchy['arrays']['height_m'].shape, native_origin_m_xz=self.hierarchy['metadata']['origin_m_xz'])
        chart = _i38_build_td_form_chart(self.hierarchy, window=window, spacing_m=4.0, source_hierarchy_sha256=_i38_preview.SOURCE['expected_sha256'], selected_edge_cell_ids=_i38_np.zeros((0, 2), dtype=_i38_np.int64), channel_policy='reject')
        bed = chart['chart_reference_xyz_m'][:, :, 1]
        self.assertGreater(float(_i38_np.min(bed)), 1000.0)
        self.assertGreater(float(_i38_np.min(bed)) - 1000.0, 264.0)
