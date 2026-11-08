"""Consolidated test_frozen_hybrid_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
import ast as _i20_ast
from dataclasses import asdict as _i20_asdict
from dataclasses import replace as _i20_replace
import hashlib as _i20_hashlib
import json as _i20_json
from pathlib import Path as _i20_Path
from types import SimpleNamespace as _i20_SimpleNamespace
from unittest.mock import patch as _i20_patch
import shutil as _i20_shutil
import subprocess as _i20_subprocess
import sys as _i20_sys
import tempfile as _i20_tempfile
import unittest as _i20_unittest
from terrain_pipeline.hybrid_hydraulics import common_Experiment as _i20_Experiment
from terrain_pipeline.hybrid_hydraulics import common_Model as _i20_Model
from terrain_pipeline.hybrid_hydraulics import common_Section as _i20_Section
from builtins import ValueError as _i20_HydraulicDiagnosticStop
from builtins import ValueError as _i20_HydraulicExecutionFailure
from terrain_pipeline.hybrid_hydraulics import local_frame_run_experiment as _i20_run_experiment
from terrain_pipeline.hybrid_hydraulics import translate_section as _i20_translate_section
from tests.hybrid_hydraulics_fixtures import tiny_model as _i20_tiny_model
from tools.frozen_hybrid_hydraulics import DATA_ROOT as _i20_DATA_ROOT
from tools.frozen_hybrid_hydraulics import SOURCE_ROOT as _i20_SOURCE_ROOT
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i20_HydraulicsLegacyReplay
from tools.prepare_hybrid_hydraulics import source_identity as _i20_source_identity
import unittest as _i21_unittest
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i21_HydraulicsLegacyReplay
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i22_HydraulicsLegacyReplay
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i23_HydraulicsLegacyReplay
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i24_HydraulicsLegacyReplay
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i25_HydraulicsLegacyReplay
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i26_HydraulicsLegacyReplay
from tools.frozen_hybrid_hydraulics import HydraulicsLegacyReplay as _i27_HydraulicsLegacyReplay
CATEGORY = 'C'
VOLATILE = frozenset(('elapsed_wall_seconds', 'actual_peak_rss_bytes', 'wall_seconds'))

def stable(value):
    if isinstance(value, dict):
        return {key: stable(item) for key, item in value.items() if key not in VOLATILE}
    if isinstance(value, (list, tuple)):
        return [stable(item) for item in value]
    return value

class HydraulicsConsolidationTests(_i20_unittest.TestCase):

    def setUp(self):
        self.replay = _i20_HydraulicsLegacyReplay()
        self.addCleanup(self.replay.close)

    def test_frozen_all_pins_ast_and_roots_without_path_mutation(self):
        before = list(_i20_sys.path)
        for version in ('', '_v2', '_v3', '_v4', '_v5', '_v6', '_v7', '_v8'):
            module = self.replay.load('tools.prepare_hybrid_river_hydraulics' + version)
            self.assertEqual(module.ROOT, _i20_DATA_ROOT)
            self.assertEqual(module.SOURCE_ROOT, _i20_SOURCE_ROOT)
            for name, expected in getattr(module, 'FROZEN_CODE', {}).items():
                self.assertEqual(module.file_sha(_i20_DATA_ROOT / name), expected, name)
        self.replay.load('tools.audit_hybrid_river_hydraulics').check_same_physics(True)
        from tools.audit_hybrid_hydraulics import check_same_physics
        check_same_physics(True)
        self.assertEqual(_i20_sys.path, before)
        self.assertNotIn('terrain_pipeline.hybrid_river_hydraulics_v7', _i20_sys.modules)
        with self.assertRaises(ImportError):
            self.replay.load('terrain_pipeline.hybrid_river_faces')
        with self.assertRaises(ValueError):
            self.replay.source_path(_i20_DATA_ROOT / 'tools/not_allowlisted.py')

    def test_common_and_radau_ast_exact_function_identity(self):

        def declarations(path):
            return {node.name: _i20_ast.dump(node, include_attributes=False) for node in _i20_ast.parse(path.read_bytes()).body if isinstance(node, (_i20_ast.FunctionDef, _i20_ast.ClassDef))}
        original = declarations(_i20_SOURCE_ROOT / 'terrain_pipeline/hybrid_river_hydraulics.py')
        common = declarations(_i20_DATA_ROOT / 'legacy-code/refactor-merge-20261105/M2/terrain_pipeline/hybrid_river_hydraulics_common.py')
        self.assertNotIn('run_experiment', common)
        self.assertEqual(common, {key: value for key, value in original.items() if key != 'run_experiment'})
        self.assertEqual(declarations(_i20_DATA_ROOT / 'legacy-code/refactor-merge-20261105/M2/terrain_pipeline/hybrid_river_hydraulics_radau.py'), declarations(_i20_SOURCE_ROOT / 'terrain_pipeline/hybrid_river_hydraulics_v6.py'))

    def test_current_original_v8_all_arrays_metadata_and_physical_identity(self):
        old_fixture = self.replay.load('tests.test_hybrid_river_hydraulics')
        old_base = self.replay.load('terrain_pipeline.hybrid_river_hydraulics')
        old_solver = self.replay.load('terrain_pipeline.hybrid_river_hydraulics_v8')
        old_prepare = self.replay.load('tools.prepare_hybrid_river_hydraulics_v8')
        from tools.hybrid_hydraulics_records import physical_model_identity
        current_model = _i20_tiny_model()
        self.assertIs(type(current_model), _i20_Model)
        self.assertIs(type(current_model.cells[0].section), _i20_Section)
        for datum in (0, 1350):
            for scenario, tailwater in (('pulse', 0.1), ('reverse_tailwater', 0.4)):
                with self.subTest(datum=datum, scenario=scenario):
                    current = _i20_replace(current_model, cells=tuple((_i20_replace(cell, section=_i20_translate_section(cell.section, -datum)) for cell in current_model.cells)))
                    previous_model = old_fixture.tiny_model()
                    previous = _i20_replace(previous_model, cells=tuple((_i20_replace(cell, section=old_solver.translate_section(cell.section, -datum)) for cell in previous_model.cells)))
                    parameters = _i20_Experiment(scenario, 0.2, 0.05 if scenario == 'pulse' else 0, 0.05 if scenario == 'pulse' else 0, datum + tailwater, (datum + 0.2,) * 3, (0, 0.05, 0.1, 0.2), max_step_s=0.02)
                    old_parameters = old_base.Experiment(**_i20_asdict(parameters))
                    expected = old_solver.run_experiment(previous, old_parameters, 0.02)
                    actual = _i20_run_experiment(current, parameters, 0.02)
                    self.assertEqual(stable(actual), stable(expected))
                    record = {key: actual.get(key, {'fixed': key}) for key in ('model_version', 'model_parameters', 'friction_policy', 'inventory_policy', 'forcing_configuration_pin', 'graph_identity_sha256', 'geometry_identity_sha256')}
                    self.assertEqual(physical_model_identity(record), old_prepare.physical_model_identity(record))

    def test_current_original_diagnostic_and_guard_failure_metadata(self):
        old_solver = self.replay.load('terrain_pipeline.hybrid_river_hydraulics_v8')
        old_base = self.replay.load('terrain_pipeline.hybrid_river_hydraulics')
        old_model = self.replay.load('tests.test_hybrid_river_hydraulics').tiny_model()
        parameters = _i20_Experiment('pulse', 0.2, 0.05, 0.05, 0.1, (0.2,) * 3, (0, 0.05, 0.1, 0.2), max_step_s=0.02)
        for diagnostic, limit in ((0.075, parameters.max_rhs_evaluations), (None, 1)):
            case = _i20_replace(parameters, max_rhs_evaluations=limit)
            with self.assertRaises((old_solver.HydraulicDiagnosticStop, old_solver.HydraulicExecutionFailure)) as before:
                old_solver.run_experiment(old_model, old_base.Experiment(**_i20_asdict(case)), 0.02, diagnostic)
            with self.assertRaises((_i20_HydraulicDiagnosticStop, _i20_HydraulicExecutionFailure)) as after:
                _i20_run_experiment(_i20_tiny_model(), case, 0.02, diagnostic)
            self.assertIs(type(after.exception), ValueError)
            self.assertEqual(after.exception.diagnostic_stop, isinstance(before.exception, old_solver.HydraulicDiagnosticStop))
            self.assertEqual(str(after.exception), str(before.exception))
            self.assertEqual(stable(after.exception.progress), stable(before.exception.progress))

    def test_manifest_and_source_double_tamper_refused(self):
        with _i20_tempfile.TemporaryDirectory() as temporary:
            archive = _i20_Path(temporary) / 'archive'
            _i20_shutil.copytree(_i20_SOURCE_ROOT, archive)
            source = archive / 'terrain_pipeline/hybrid_river_hydraulics_v6.py'
            source.write_bytes(source.read_bytes() + b'\n# tamper\n')
            with self.assertRaisesRegex(ValueError, 'source sha256 mismatch'):
                _i20_HydraulicsLegacyReplay(source_root=archive)
            manifest_path = archive / 'manifest.json'
            manifest = _i20_json.loads(manifest_path.read_bytes())
            entry = manifest['files']['terrain_pipeline/hybrid_river_hydraulics_v6.py']
            entry.update(sha256=_i20_hashlib.sha256(source.read_bytes()).hexdigest(), bytes=source.stat().st_size)
            manifest_path.write_text(_i20_json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'manifest sha256 mismatch'):
                _i20_HydraulicsLegacyReplay(source_root=archive)

    def test_source_data_root_separation_and_late_tamper_refused(self):
        with _i20_tempfile.TemporaryDirectory() as temporary:
            root = _i20_Path(temporary)
            archive, data = (root / 'source', root / 'data')
            _i20_shutil.copytree(_i20_SOURCE_ROOT, archive)
            data.mkdir()
            (data / 'terrain_pipeline').mkdir()
            (data / 'terrain_pipeline/hybrid_river_hydraulics.py').write_bytes(b'not the frozen source')
            replay = _i20_HydraulicsLegacyReplay(source_root=archive, data_root=data)
            self.addCleanup(replay.close)
            module = replay.load('tools.prepare_hybrid_river_hydraulics_v8')
            self.assertEqual(module.ROOT, data)
            for name, expected in module.FROZEN_CODE.items():
                self.assertEqual(module.file_sha(data / name), expected)
            artifact = data / 'input.json'
            artifact.write_bytes(b'{"unchanged":true}')
            self.assertEqual(module.file_sha(artifact), _i20_hashlib.sha256(artifact.read_bytes()).hexdigest())
            source = archive / 'terrain_pipeline/hybrid_river_hydraulics_v6.py'
            source.write_bytes(source.read_bytes() + b'\n')
            with self.assertRaises(ValueError):
                replay.source_path(source)
            with self.assertRaises(ValueError):
                replay.load('terrain_pipeline.hybrid_river_hydraulics_v6') if 'terrain_pipeline.hybrid_river_hydraulics_v6' not in replay.modules else replay.source_path(source)

    def test_new_source_identity_different_and_not_historical_hash_relabel(self):
        current, historical = _i20_source_identity()
        self.assertIn('terrain_pipeline/hybrid_hydraulics.py', current)
        for name in ('terrain_pipeline/hybrid_river_hydraulics_v6.py', 'terrain_pipeline/hybrid_river_hydraulics.py'):
            self.assertNotIn(name, current)
        self.assertNotEqual(current['terrain_pipeline/hybrid_hydraulics.py'], historical['terrain_pipeline/hybrid_river_hydraulics_v8.py'])
        for name, sha in current.items():
            self.assertEqual(_i20_hashlib.sha256((_i20_DATA_ROOT / name).read_bytes()).hexdigest(), sha)
        self.assertNotIn('BDF', _i20_json.dumps(current))

    def test_current_cold_import_does_not_load_legacy_kernels_or_mutate_path(self):
        code = "import sys\nbefore=list(sys.path)\nimport terrain_pipeline.hybrid_hydraulics\nimport tools.prepare_hybrid_hydraulics\nassert sys.path == before\nfor name in ('terrain_pipeline.hybrid_river_hydraulics', 'terrain_pipeline.hybrid_river_hydraulics_v3', 'terrain_pipeline.hybrid_river_hydraulics_v4', 'terrain_pipeline.hybrid_river_hydraulics_v5', 'terrain_pipeline.hybrid_river_hydraulics_v6', 'terrain_pipeline.hybrid_river_hydraulics_v7'):\n    assert name not in sys.modules, name\nassert not any(name.startswith('_hybrid_hydraulics_legacy_') for name in sys.modules)\n"
        _i20_subprocess.run([_i20_sys.executable, '-B', '-c', code], cwd=_i20_DATA_ROOT, check=True, capture_output=True, text=True)

    def test_actual_small_prepare_outputs_and_source_identity_change(self):
        from terrain_pipeline.hybrid_geometry import identity
        from tools import prepare_hybrid_hydraulics as current_prepare
        from tools.hybrid_hydraulics_records import file_sha
        with _i20_tempfile.TemporaryDirectory() as temporary:
            root = _i20_Path(temporary)
            parent = root / 'verification/hybrid-river-network'
            parent.mkdir(parents=True)
            graph = {'identity_sha256': 'fixed-graph'}
            geometry = {'identity_sha256': 'fixed-geometry'}
            arguments = {}
            for name, record in (('graph', graph), ('geometry', geometry), ('geometry_audit', {'fixed': True})):
                path = root / (name + '.json')
                path.write_text(_i20_json.dumps(record), encoding='utf-8')
                arguments[name] = path
                arguments[name + '_sha256'] = file_sha(path)
            inputs = {name: {'path': str(arguments[name]), 'sha256': arguments[name + '_sha256']} for name in ('graph', 'geometry', 'geometry_audit')}
            scenarios = [_i20_asdict(_i20_Experiment(scenario, 0.2, 0.05 if scenario == 'pulse' else 0, 0.05 if scenario == 'pulse' else 0, tailwater, (0.2,) * 3, (0, 0.05, 0.1, 0.2), max_step_s=0.02)) for scenario, tailwater in (('pulse', 0.1), ('reverse_tailwater', 0.4))]
            configuration = {'schema': 'td-hybrid-river-engineering-experiments-v1', 'scenarios': scenarios, 'graph_identity_sha256': graph['identity_sha256'], 'geometry_identity_sha256': geometry['identity_sha256'], 'inputs': inputs}
            configuration['identity_sha256'] = identity(configuration)
            config_path = root / 'experiments.json'
            config_path.write_text(_i20_json.dumps(configuration), encoding='utf-8')
            arguments.update(experiments=config_path, experiments_sha256=file_sha(config_path), crown_friction_transition_m=0.02, diagnostic_stop_s=None)
            old_context = _i20_HydraulicsLegacyReplay(data_root=root)
            self.addCleanup(old_context.close)
            old_prepare = old_context.load('tools.prepare_hybrid_river_hydraulics_v8')
            old_model = old_context.load('tests.test_hybrid_river_hydraulics').tiny_model()
            with _i20_patch.object(old_prepare, 'validate_geometry', return_value=(old_model, geometry)):
                before = old_prepare.prepare(_i20_SimpleNamespace(**arguments, output=parent / 'original'))
            with _i20_patch.object(current_prepare, 'ROOT', root), _i20_patch.object(current_prepare, '_x7_validate_geometry', return_value=(_i20_tiny_model(), geometry)):
                after = current_prepare.prepare(_i20_SimpleNamespace(**arguments, output=parent / 'current'))
            self.assertEqual(before['status'], after['status'])
            self.assertEqual(after['status'], 'refused_diagnostic_evidence')
            self.assertEqual(before['physical_model_identity_sha256'], after['physical_model_identity_sha256'])
            self.assertNotEqual(before['code_sha256'], after['code_sha256'])
            for case in ('pulse-base', 'pulse-refined', 'reverse_tailwater-base', 'reverse_tailwater-refined'):
                first = _i20_json.loads((parent / 'original' / (case + '.json')).read_bytes())
                second = _i20_json.loads((parent / 'current' / (case + '.json')).read_bytes())
                for record in (first, second):
                    for key in ('identity_sha256', 'code_sha256', 'hydraulic_model_parameters', 'hydraulic_model_parameters_identity_sha256'):
                        record.pop(key)
                self.assertEqual(stable(first), stable(second), case)

    def test_preexisting_historical_wrong_source_pin_is_not_relabelled(self):
        saved_pin = {'path': str(_i20_DATA_ROOT / 'terrain_pipeline/hybrid_river_hydraulics_v3.py'), 'sha256': '472f3114a235d8c68fe449b4a514beceb8069853722abeb1664c822473a7311d'}
        reader = self.replay.load('tools.td_shared_channel_fine_saved_audit')
        with self.assertRaisesRegex(ValueError, 'historical source pin mismatch'):
            reader.checked_path(saved_pin)
        self.assertEqual(saved_pin['sha256'], '472f3114a235d8c68fe449b4a514beceb8069853722abeb1664c822473a7311d')

def load_tests(loader, tests, pattern):
    replay = _i21_HydraulicsLegacyReplay()
    suite = _i21_unittest.TestSuite()
    for name in sorted(replay.sources):
        if name.startswith('tests.test_hybrid_river_'):
            suite.addTests(loader.loadTestsFromModule(replay.load(name)))
    suite._hydraulics_replay = replay
    return suite

def _test_hybrid_river_hydraulics_load_tests(loader, tests, pattern):
    replay = _i22_HydraulicsLegacyReplay()
    suite = loader.loadTestsFromModule(replay.load('tests.test_hybrid_river_hydraulics'))
    suite._hydraulics_replay = replay
    return suite

def _test_hybrid_river_hydraulics_mechanism_3_load_tests(loader, tests, pattern):
    replay = _i23_HydraulicsLegacyReplay()
    suite = loader.loadTestsFromModule(replay.load('tests.test_hybrid_river_hydraulics_v3'))
    suite._hydraulics_replay = replay
    return suite

def _test_hybrid_river_hydraulics_mechanism_4_load_tests(loader, tests, pattern):
    replay = _i24_HydraulicsLegacyReplay()
    suite = loader.loadTestsFromModule(replay.load('tests.test_hybrid_river_hydraulics_v4'))
    suite._hydraulics_replay = replay
    return suite

def _test_hybrid_river_hydraulics_mechanism_5_load_tests(loader, tests, pattern):
    replay = _i25_HydraulicsLegacyReplay()
    suite = loader.loadTestsFromModule(replay.load('tests.test_hybrid_river_hydraulics_v5'))
    suite._hydraulics_replay = replay
    return suite

def _test_hybrid_river_hydraulics_mechanism_6_load_tests(loader, tests, pattern):
    replay = _i26_HydraulicsLegacyReplay()
    suite = loader.loadTestsFromModule(replay.load('tests.test_hybrid_river_hydraulics_v6'))
    suite._hydraulics_replay = replay
    return suite

def _test_hybrid_river_hydraulics_mechanism_7_load_tests(loader, tests, pattern):
    replay = _i27_HydraulicsLegacyReplay()
    suite = loader.loadTestsFromModule(replay.load('tests.test_hybrid_river_hydraulics_v7'))
    suite._hydraulics_replay = replay
    return suite
