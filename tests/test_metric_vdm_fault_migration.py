"""A-plan migration: current v2 generation and explicit frozen-v1 replay."""
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from terrain_pipeline import vdm_cuts as current
from terrain_pipeline.vdm_cuts import FaultRecipe
from terrain_pipeline.vdm_cuts import CliffRecipe
from terrain_pipeline.vdm_cuts import FormRecipe, build_formed_vdm, save_formed_vdm
from terrain_pipeline.common_infra import file_sha256, identity
from tests.metric_vdm_fault_fixtures import chart, source, selection, recipe
from tools import frozen_vdm_fault as legacy
from tools.audit_vdm_fault import audit_fault
from tools.prepare_vdm_fault import prepare
ROOT = Path(__file__).resolve().parents[1]

def _configuration(folder):
    config = CliffRecipe((0.0, 0.0), (1.0, 0.0), 6.0, 7.0, 8.0, 3.0, 2.0, 75.0, 1)
    formed = build_formed_vdm(chart(), recipe=config, form=FormRecipe('fluted_wall', 0.1, 8.0, 20261020), protected_mask=np.zeros((25, 25), bool), source_identity='fixed-source-20261020', protection_identity='none')
    source_path = folder / 'source.npz'
    save_formed_vdm(source_path, formed)
    payload = {'source': {'path': str(source_path), 'expected_sha256': file_sha256(source_path), 'expected_identity': formed['identity_sha256']}, 'selection': {'row_start': 5, 'row_stop': 20, 'column_start': 5, 'column_stop': 20}, 'fault': asdict(recipe(slip=-1.0, strike=18.0))}
    path = folder / 'config.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path

class FaultVersionMigrationTests(unittest.TestCase):

    def test_archive_has_all_before_sources_and_trusted_manifest(self):
        archive, sources = legacy.verify_archive()
        self.assertEqual(len(sources), 11)
        self.assertEqual(file_sha256(archive / 'manifest.json'), legacy.MANIFEST_SHA256)
        self.assertEqual(hashlib.sha256(sources['terrain_pipeline/metric_vdm_fault.py']).hexdigest(), 'bb367e16885450f4278f10f120a1d3d0bb41d1229e6a759cf82e779cc3f2f78a')

    def test_latest_identity_and_arrays_match_before_refactor(self):
        before = legacy._modules()['terrain_pipeline.metric_vdm_fault_v2']
        original = source()
        for slip, strike in ((0.0, 0.0), (-2.0, 18.0), (1.75, 90.0)):
            with self.subTest(slip=slip, strike=strike):
                params = asdict(recipe(slip=slip, strike=strike))
                expected = before.apply_fault(original, recipe=before.FaultRecipe(**params), selection_mask=selection())
                actual = current.apply_fault(original, recipe=FaultRecipe(**params), selection_mask=selection())
                self.assertEqual(actual['identity_sha256'], expected['identity_sha256'])
                self.assertEqual(actual['metadata'], expected['metadata'])
                for key in expected['arrays']:
                    np.testing.assert_array_equal(actual['arrays'][key], expected['arrays'][key])

    def test_current_recipe_type_is_shared_without_old_module(self):
        self.assertIs(current.FaultRecipe, FaultRecipe)
        self.assertFalse((ROOT / 'terrain_pipeline/metric_vdm_fault.py').exists())
        self.assertIsNone(importlib.util.find_spec('terrain_pipeline.metric_vdm_fault'))

    def test_production_imports_do_not_load_archive(self):
        code = "import sys; import terrain_pipeline.vdm_cuts; import tools.prepare_vdm_fault; import tools.audit_vdm_fault; assert not any(n.startswith('_terragenesis_legacy_fault_v1_') for n in sys.modules); assert 'terrain_pipeline.metric_vdm_fault' not in sys.modules"
        subprocess.run([sys.executable, '-B', '-c', code], cwd=ROOT, check=True, capture_output=True, text=True)

    def test_legacy_loading_and_generation_do_not_mutate_sys_path(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            before = list(sys.path)
            legacy.load_legacy_api(project_root=folder)
            self.assertEqual(sys.path, before)
            other = folder / 'other-root'
            other.mkdir()
            legacy.load_legacy_api(project_root=other)
            self.assertEqual(sys.path, before)
            configuration = _configuration(folder)
            legacy.replay_legacy_preparation(configuration, file_sha256(configuration), folder / 'ok', project_root=other)
            self.assertEqual(sys.path, before)
            with self.assertRaisesRegex(ValueError, 'configuration SHA'):
                legacy.replay_legacy_preparation(configuration, '0' * 64, folder / 'failed', project_root=folder)
            self.assertEqual(sys.path, before)

    def test_failed_module_adaptation_cleans_isolated_namespace_and_sys_path(self):
        with tempfile.TemporaryDirectory() as folder:
            before_path = list(sys.path)
            before_modules = {name for name in sys.modules if name.startswith('_terragenesis_legacy_fault_v1_')}
            with patch.object(legacy._ReplayImports, 'visit_ImportFrom', side_effect=ValueError('injected adaptation failure')):
                with self.assertRaisesRegex(ValueError, 'injected adaptation failure'):
                    legacy.load_legacy_api(project_root=folder)
            self.assertEqual(sys.path, before_path)
            self.assertEqual({name for name in sys.modules if name.startswith('_terragenesis_legacy_fault_v1_')}, before_modules)

    def test_modified_archived_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archived = Path(folder) / 'archive'
            shutil.copytree(legacy.ARCHIVE, archived)
            legacy.load_legacy_api(archive_dir=archived)
            path = archived / 'terrain_pipeline/metric_vdm_fault.py'
            path.write_bytes(path.read_bytes() + b'\n# tamper\n')
            before_path = list(sys.path)
            with self.assertRaisesRegex(ValueError, 'source SHA256'):
                legacy.load_legacy_api(archive_dir=archived)
            self.assertEqual(sys.path, before_path)

    def test_source_and_rewritten_manifest_still_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            archived = Path(folder) / 'archive'
            shutil.copytree(legacy.ARCHIVE, archived)
            path = archived / 'terrain_pipeline/metric_vdm_fault.py'
            path.write_bytes(path.read_bytes() + b'\n# tamper\n')
            manifest_path = archived / 'manifest.json'
            record = json.loads(manifest_path.read_text(encoding='utf-8'))
            for entry in record['files']:
                if entry['original_path'] == 'terrain_pipeline/metric_vdm_fault.py':
                    entry['sha256'] = file_sha256(path)
                    entry['bytes'] = path.stat().st_size
            manifest_path.write_text(json.dumps(record), encoding='utf-8')
            before_path = list(sys.path)
            with self.assertRaisesRegex(ValueError, 'manifest SHA256'):
                legacy.load_legacy_api(archive_dir=archived)
            self.assertEqual(sys.path, before_path)

    def test_v1_and_v2_codecs_remain_separate(self):
        old = legacy.load_legacy_api()
        original = source()
        params = asdict(recipe())
        v1 = old.apply_fault(original, recipe=old.FaultRecipe(**params), selection_mask=selection())
        v2 = current.apply_fault(original, recipe=FaultRecipe(**params), selection_mask=selection())
        with tempfile.TemporaryDirectory() as folder:
            one, two = (Path(folder) / 'v1.npz', Path(folder) / 'v2.npz')
            old.save_fault(one, v1)
            current.save_fault(two, v2)
            with self.assertRaises(ValueError):
                current.load_fault(one, expected_sha256=file_sha256(one), expected_identity=v1['identity_sha256'])
            with self.assertRaises(ValueError):
                old.load_fault(two, expected_sha256=file_sha256(two), expected_identity=v2['identity_sha256'])
            loaded = legacy.load_legacy_fault(one, expected_sha256=file_sha256(one), expected_identity=v1['identity_sha256'])
            self.assertEqual(loaded['identity_sha256'], v1['identity_sha256'])
            self.assertTrue(legacy.audit_legacy_fault(one, expected_sha256=file_sha256(one), expected_identity=v1['identity_sha256'])['passed'])

    def test_legacy_validator_keeps_certification_refusal(self):
        old = legacy.load_legacy_api()
        params = asdict(recipe())
        result = old.apply_fault(source(), recipe=old.FaultRecipe(**params), selection_mask=selection())
        result['metadata']['publishable'] = True
        result['identity_sha256'] = identity(result['arrays'], result['metadata'])
        with self.assertRaisesRegex(ValueError, 'certification flags'):
            old.validate_fault(result)

    def test_original_preparation_replays_with_declared_data_root_and_old_code_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            configuration = _configuration(folder)
            output = folder / 'legacy-result'
            report = legacy.replay_legacy_preparation(configuration, file_sha256(configuration), output, project_root=folder)
            self.assertEqual(report['schema'], 'metric-vdm-fault-preparation-v1')
            self.assertEqual(report['fault']['schema'], 'metric-vdm-fault-v1')
            self.assertTrue(report['cold_roundtrip_passed'])
            sidecar = json.loads((output / 'legacy-replay.json').read_text(encoding='utf-8'))
            self.assertEqual(sidecar['project_data_root'], str(folder.resolve()))
            self.assertEqual(sidecar['manifest_sha256'], legacy.MANIFEST_SHA256)
            self.assertEqual(file_sha256(output / 'legacy-replay.json'), report['legacy_replay']['sha256'])
            archive, sources = legacy.verify_archive()
            for name, digest in report['code_sha256'].items():
                self.assertEqual(digest, hashlib.sha256(sources[name]).hexdigest())
            old_result = legacy.load_legacy_fault(**report['fault_bundle'])
            old_api = legacy.load_legacy_api()
            modules = legacy._modules()
            old_source = modules['terrain_pipeline.metric_vdm_forms'].load_formed_vdm(**report['source'])
            config = json.loads(configuration.read_text(encoding='utf-8'))
            params = config['fault']
            params['plane_origin_xz_m'] = tuple(params['plane_origin_xz_m'])
            rebuilt = old_api.apply_fault(old_source, recipe=old_api.FaultRecipe(**params), selection_mask=selection())
            self.assertEqual(old_result['identity_sha256'], rebuilt['identity_sha256'])
            self.assertTrue((output / 'reference.obj').is_file())
            self.assertTrue((output / 'review.json').is_file())

    def test_default_preparation_generates_only_v2_and_rejects_bad_config_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            configuration = _configuration(folder)
            with self.assertRaisesRegex(ValueError, 'configuration SHA'):
                prepare(configuration, '0' * 64, folder / 'bad')
            self.assertFalse((folder / 'bad').exists())
            output = folder / 'latest-result'
            prepare(configuration, file_sha256(configuration), output)
            report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['fault']['schema'], 'metric-vdm-fault-v2')
            audited = audit_fault(output / 'fault.npz', expected_sha256=report['fault_bundle']['expected_sha256'], expected_identity=report['fault_bundle']['expected_identity'])
            self.assertTrue(audited['passed'])

    def test_legacy_cli_is_explicit_and_default_cli_stays_latest(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            configuration = _configuration(folder)
            command = [sys.executable, '-B', 'tools/prepare_vdm_fault.py', '--configuration', str(configuration), '--configuration-sha256', file_sha256(configuration)]
            latest, historical = (folder / 'latest-cli', folder / 'historical-cli')
            subprocess.run(command + ['--output', str(latest)], cwd=ROOT, check=True, capture_output=True)
            subprocess.run(command + ['--output', str(historical), '--legacy-v1-replay'], cwd=ROOT, check=True, capture_output=True)
            for output, schema in ((latest, 'metric-vdm-fault-v2'), (historical, 'metric-vdm-fault-v1')):
                report = json.loads((output / 'report.json').read_text(encoding='utf-8'))
                self.assertEqual(report['fault']['schema'], schema)
if __name__ == '__main__':
    unittest.main()
