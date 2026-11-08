import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from unittest.mock import patch

from terrain_pipeline.regional_surface_review import CAMERA_PAGE, export_review, validate_snapshot_index, validate_saved_mesh, read_bounded_json, adapt_B_index
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.common_infra import file_sha256


class RegionalReviewTests(unittest.TestCase):
    def index(self):
        return {'schema': 'regional-saved-B-mesh-cases-v1', 'source_identity': 'source', 'fixture_only': True,
            'cases': [{'id': 'fixture', 'model': 'UI fixture only', 'requested_time_s': 900,
                'committed_time_s': 900, 'status': 'completed', 'failure': None,
                'B_validation': 'synthetic display test, not physics acceptance',
                'snapshots': [{'time_s': time, 'path': 'mesh.json', 'sha256': 'a' * 64,
                    'volume_m3': 0, 'max_depth_m': 0} for time in (0, 900)]}]}

    def test_time_status_negative_water_and_paths_rejected(self):
        validate_snapshot_index(self.index(), source_identity='source')
        attacks = [('requested_time_s', float('nan')), ('requested_time_s', True),
            ('committed_time_s', 450), ('status', 'arbitrary'), ('failure', 'unexpected')]
        for key, value in attacks:
            index = self.index()
            index['cases'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_snapshot_index(index, source_identity='source')
        refused = self.index()
        case = refused['cases'][0]
        case['status'] = 'refused'
        case['committed_time_s'] = 0
        case['failure'] = {'reason': 'budget', 'time_s': 0.}
        case['snapshots'] = case['snapshots'][:1]
        validate_snapshot_index(refused, source_identity='source')
        case['failure']['time_s'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'failure'):
            validate_snapshot_index(refused, source_identity='source')
        for key, value in [('time_s', -1), ('time_s', 900), ('volume_m3', -1),
                ('max_depth_m', float('inf')), ('path', '../mesh.json')]:
            index = self.index()
            index['cases'][0]['snapshots'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_snapshot_index(index, source_identity='source')

    def test_mesh_limits_and_indices(self):
        empty = {'source_identity': 'source', 'vertices_xyz_m': [], 'triangles': []}
        validate_saved_mesh(empty, source_identity='source')
        for mesh in [dict(empty, triangles=[[0, 1, 2]]),
                dict(empty, vertices_xyz_m=[[0, float('nan'), 0]]),
                dict(empty, triangles=[[]] * 400001)]:
            with self.assertRaises(ValueError):
                validate_saved_mesh(mesh, source_identity='source')

    def test_B_display_omitted_storage_is_preserved_and_checked(self):
        mesh = {'source_identity': 'source', 'vertices_xyz_m': [], 'triangles': [], 'time_s': 0.,
            'display_cell_ids': [], 'display_threshold_m': .001, 'omitted_wet_cells': 1,
            'omitted_volume_m3': 10., 'solver_volume_m3': 10., 'display_volume_m3': 0.,
            'representation': 'independent_flat_cell_top_quads_not_continuous_shared_stage_surface',
            'physical_archive': 'physical-water.npz'}
        self.assertIs(validate_saved_mesh(mesh, source_identity='source'), mesh)
        for key, value in [('solver_volume_m3', 11.), ('omitted_volume_m3', -1.),
                ('physical_archive', '../physical.npz'), ('omitted_wet_cells', True)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_saved_mesh(dict(mesh, **{key: value}), source_identity='source')

    def test_actual_B_dry_adapter_export_readonly(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / 'verification/regional-source/run-20261001T095258008789Z'
        source = load_source(directory / 'source.npz',
            expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        metadata = json.loads((root / 'verification/regional-hydraulics/full-20261001T101153406000Z/dry/states.json').read_text())['metadata']
        original = root / 'verification/regional-hydraulics/mesh-dry-20261001T101953058448Z/saved-mesh-index.json'
        with patch('terrain_pipeline.surface_hydraulics.advance_inertial_surface', side_effect=AssertionError('advance')), \
                patch('terrain_pipeline.surface_hydraulics.prepare_surface_geometry', side_effect=AssertionError('prepare')), \
                patch('terrain_pipeline.climate_forcing.regional_generate_forcing', side_effect=AssertionError('forcing')):
            adapted = adapt_B_index(original,
                expected_sha256='38753aad771d3f16197f7fb9f69c7b981dbbb8fa70f90295931d728d38436ba8',
                source_identity=source['identity_sha256'], case_metadata=metadata, case_id='dry',
                trusted_height=source['arrays']['height_m'],
                expected_case_manifest_sha256='022bac4a53442e22ba9c85acbe7936e29ac601063a7f05d4b4ade1acbf906857')
        self.assertEqual([s['time_s'] for s in adapted['cases'][0]['snapshots']], [0., 86400., 259200.])
        self.assertFalse(adapted['fixture_only'])
        with tempfile.TemporaryDirectory() as temporary:
            index_path = Path(temporary) / 'index.json'
            for state in adapted['cases'][0]['snapshots']:
                (Path(temporary) / state['path']).write_bytes((original.parent / state['path']).read_bytes())
            index_path.write_text(json.dumps(adapted))
            network = root / 'verification/regional-source-network/run-20261001T095553240102Z/network.json'
            result = export_review(source, network, Path(temporary) / 'review', network_sha256=file_sha256(network),
                snapshot_index_path=index_path, snapshot_index_sha256=file_sha256(index_path))
            self.assertTrue(result['saved_dynamic_states_available'])
            self.assertEqual(result['case_status'][0]['status'], 'completed')
            loaded = json.loads((Path(temporary) / 'review' / adapted['cases'][0]['snapshots'][0]['path']).read_text())
            self.assertIn('omitted_volume_m3', loaded)

    def test_B_adapter_rejects_re_signed_mesh_index_volume_conflict(self):
        root = Path(__file__).resolve().parents[1]
        original = root / 'verification/regional-hydraulics/mesh-dry-20261001T101953058448Z/saved-mesh-index.json'
        metadata = json.loads((root / 'verification/regional-hydraulics/full-20261001T101153406000Z/dry/states.json').read_text())['metadata']
        index = json.loads(original.read_text())
        index['snapshots'][0]['solver_volume_m3'] = 1.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'index.json'
            path.write_text(json.dumps(index))
            for state in index['snapshots']:
                (path.parent / state['path']).write_bytes((original.parent / state['path']).read_bytes())
            with self.assertRaisesRegex(ValueError, 'volume mismatch'):
                adapt_B_index(path, expected_sha256=file_sha256(path), source_identity=index['source_identity'],
                    case_metadata=metadata, case_id='dry', trusted_height=np.zeros((256, 256)),
                    expected_case_manifest_sha256=index['source_case_manifest_sha256'])

    def test_actual_failure_full_and_filtered_representations(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / 'verification/regional-hydraulics/mesh-work_two_commit-20261001T103232437820Z'
        path = directory / 'consumer-cases-index.json'
        metadata = json.loads((root / 'verification/regional-hydraulics/failure-20261001T102852005353Z/work_two_commit/states.json').read_text())['metadata']
        source = load_source(root / 'verification/regional-source/run-20261001T095258008789Z/source.npz',
            expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        for label in ('display_filtered_1mm', 'full_top_threshold_0'):
            adapted = adapt_B_index(path, expected_sha256='94c0988874b200865060b7a182e2c866b75d006ad4d8305685944a4c2b617591',
                source_identity=source['identity_sha256'], case_metadata=metadata, case_id=label,
                trusted_height=source['arrays']['height_m'], origin_m_xz=source['metadata']['origin_m_xz'],
                expected_case_manifest_sha256='1684db4a0ae3bbb4efc9a5b80ea7b1b43644aad25fb0a52397b8eac7832501fd',
                representation_id='work_two_commit_' + label)
            case = adapted['cases'][0]
            self.assertIsInstance(case['failure'], dict)
            self.assertEqual(case['committed_time_s'], 60.)
            mesh = json.loads((directory / case['snapshots'][-1]['path']).read_text())
            if label == 'full_top_threshold_0':
                self.assertEqual(mesh['omitted_volume_m3'], 0.)
                self.assertGreater(case['snapshots'][-1]['display_max_depth_m'], 0.)
            else:
                self.assertEqual(mesh['omitted_volume_m3'], mesh['solver_volume_m3'])
                self.assertEqual(case['snapshots'][-1]['display_max_depth_m'], 0.)

    def test_byte_cap_before_hash_or_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'oversized.json'
            path.write_bytes(b' ' * 32)
            with patch('terrain_pipeline.regional_surface_review.file_sha256', side_effect=AssertionError('hash read')):
                with self.assertRaisesRegex(ValueError, 'budget'):
                    read_bounded_json(path, expected_sha256='a' * 64, max_bytes=16)

    def test_camera_projection_has_no_fullgrid_reduction(self):
        projection = CAMERA_PAGE.split('function point(v)', 1)[1].split('function triangle', 1)[0]
        self.assertNotIn('reduce', projection)
        self.assertNotIn('height_m', projection)
        self.assertIn('prepareTerrain()', CAMERA_PAGE)
        self.assertIn('gl.DEPTH_TEST', CAMERA_PAGE)
        self.assertIn('waterReference!==water', CAMERA_PAGE)
        self.assertIn('gl.deleteBuffer', CAMERA_PAGE)
        self.assertIn("getElementById('terrainVisible').checked", CAMERA_PAGE)

    def test_network_duplicate_keys_rejected(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / 'verification/regional-source/run-20261001T095258008789Z'
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        source = load_source(directory / 'source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'network.json'
            path.write_text('{"source_identity":"a","source_identity":"b"}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                export_review(source, path, Path(temporary) / 'output', network_sha256=file_sha256(path))

    def test_real_review_is_static_and_has_no_fixture_water(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / 'verification/regional-source/run-20261001T095258008789Z'
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        source = load_source(directory / 'source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        network = root / 'verification/regional-source-network/run-20261001T095553240102Z/network.json'
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'review'
            with patch('terrain_pipeline.regional_surface_source.build_source', side_effect=AssertionError('prepared')):
                export_review(source, network, destination, network_sha256=file_sha256(network))
            index = json.loads((destination / 'saved-mesh-index.json').read_text())
            self.assertEqual(index['snapshots'], [])
            self.assertTrue((destination / 'review-3d.html').is_file())

    def test_fixture_rejection_leaves_no_partial_review(self):
        root = Path(__file__).resolve().parents[1]
        directory = root / 'verification/regional-source/run-20261001T095258008789Z'
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        source = load_source(directory / 'source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
        network = root / 'verification/regional-source-network/run-20261001T095553240102Z/network.json'
        index = self.index()
        index['source_identity'] = source['identity_sha256']
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'index.json'
            path.write_text(json.dumps(index), encoding='utf-8')
            destination = Path(temporary) / 'review'
            with self.assertRaisesRegex(ValueError, 'fixture'):
                export_review(source, network, destination, network_sha256=file_sha256(network),
                    snapshot_index_path=path, snapshot_index_sha256=file_sha256(path))
            self.assertFalse(destination.exists())


if __name__ == '__main__':
    unittest.main()
