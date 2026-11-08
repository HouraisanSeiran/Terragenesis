"""Consolidated test_frozen_hybrid_geometry implementations; numeric expressions preserved."""
from __future__ import annotations
import copy as _i19_copy
import importlib as _i19_importlib
import json as _i19_json
from pathlib import Path as _i19_Path
import shutil as _i19_shutil
import subprocess as _i19_subprocess
import sys as _i19_sys
import tempfile as _i19_tempfile
import unittest as _i19_unittest
from unittest import mock as _i19_mock
from tools.frozen_hybrid_geometry import GeometryLegacyReplay as _i19_GeometryLegacyReplay
from tools.frozen_hybrid_geometry import CODE_ROOT as _i19_CODE_ROOT
from tools import hybrid_geometry_records as _i19_current_io
CATEGORY = 'C'
ROOT = _i19_Path(__file__).resolve().parents[1]

class HybridGeometryMigrationTests(_i19_unittest.TestCase):

    def test_archive_closure_covers_saved_dynamic_code_maps(self):
        context = _i19_GeometryLegacyReplay()
        stage_tool = context.load('tools.prepare_hybrid_surface_composition_v3')
        data = stage_tool.load_stage({'path': str(stage_tool.SOURCE), 'sha256': stage_tool.SOURCE_SHA})
        lineage = data[8]
        for group in ('source_code_sha256', 'source_readonly_dependency_code_sha256'):
            for name, sha in lineage[group].items():
                self.assertIn(name, context.manifest['files'])
                self.assertEqual(context.manifest['files'][name]['sha256'], sha)
                self.assertEqual(context.source_sha256(ROOT / name), sha)
        self.assertEqual(stage_tool.ROOT, ROOT)
        self.assertTrue(str(stage_tool.SOURCE).startswith(str(ROOT / 'verification')))
        self.assertEqual(data[0]['material']['total_removed_m3'], 1835.3713650176417)

    def test_historical_v3_source_gate_accepts_frozen_not_live_sources(self):
        context = _i19_GeometryLegacyReplay()
        audit = context.load('tools.audit_hybrid_surface_composition_v3')
        path = ROOT / 'verification/natural-river-network/hybrid-surface-composition-20261006-03/composition.json'
        record = _i19_json.loads(path.read_bytes())
        audit.check_code_pins(record)
        audit.check_stage_lineage(record)
        changed = _i19_copy.deepcopy(record)
        changed['code_sha256'].pop(next(iter(changed['code_sha256'])))
        with self.assertRaises(ValueError):
            audit.check_code_pins(changed)

    def test_legacy_source_registry_missing_entry_is_not_subset_accepted(self):
        context = _i19_GeometryLegacyReplay()
        missing = 'tests/test_hybrid_cave_geometry.py'
        self.assertIn(missing, context.manifest['files'])
        context.manifest['files'].pop(missing)
        with self.assertRaisesRegex(ValueError, 'unregistered frozen'):
            context.source_path(ROOT / missing)
        with self.assertRaisesRegex(ValueError, 'unregistered frozen'):
            context.source_path(ROOT / 'terrain_pipeline/not_a_frozen_source.py')

    def test_legacy_manifest_and_source_tampering_rejected_together(self):
        with _i19_tempfile.TemporaryDirectory() as directory:
            archive = _i19_Path(directory) / 'archive'
            _i19_shutil.copytree(_i19_CODE_ROOT, archive)
            source = archive / 'terrain_pipeline/hybrid_mesh_plane.py'
            source.write_bytes(source.read_bytes() + b'\n# altered\n')
            manifest_path = archive / 'manifest.json'
            manifest = _i19_json.loads(manifest_path.read_bytes())
            import hashlib
            manifest['files']['terrain_pipeline/hybrid_mesh_plane.py']['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            manifest_path.write_text(_i19_json.dumps(manifest), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'manifest sha256 mismatch'):
                _i19_GeometryLegacyReplay(code_root=archive)

    def test_legacy_source_tamper_after_context_creation_is_rejected(self):
        with _i19_tempfile.TemporaryDirectory() as directory:
            archive = _i19_Path(directory) / 'archive'
            _i19_shutil.copytree(_i19_CODE_ROOT, archive)
            context = _i19_GeometryLegacyReplay(code_root=archive)
            source = archive / 'terrain_pipeline/hybrid_mesh_plane.py'
            source.write_bytes(source.read_bytes() + b'\n# altered\n')
            with self.assertRaisesRegex(ValueError, 'legacy source changed'):
                context.source_sha256(ROOT / 'terrain_pipeline/hybrid_mesh_plane.py')

    def test_current_source_context_never_falls_back_to_archive(self):
        record = {'code_source_context': 'current', 'code_sha256': {name: _i19_current_io.file_sha(ROOT / name) for name in _i19_current_io.CURRENT_GENERATOR_FILES}}
        _i19_current_io.verify_current_code(record)
        with _i19_tempfile.TemporaryDirectory() as directory:
            copied_root = _i19_Path(directory)
            for name in _i19_current_io.CURRENT_GENERATOR_FILES:
                target = copied_root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                _i19_shutil.copyfile(ROOT / name, target)
            (copied_root / 'terrain_pipeline/hybrid_geometry.py').write_bytes(b'# corrupted current source\n')
            with _i19_mock.patch.object(_i19_current_io, 'ROOT', copied_root):
                with self.assertRaisesRegex(ValueError, 'current source sha256 mismatch'):
                    _i19_current_io.verify_current_code(record)
        incomplete = _i19_copy.deepcopy(record)
        incomplete['code_sha256'].pop(next(iter(incomplete['code_sha256'])))
        with self.assertRaisesRegex(ValueError, 'complete code registry'):
            _i19_current_io.verify_current_code(incomplete)

    def test_current_default_import_does_not_import_retired_geometry_algorithms(self):
        script = "import sys; import tools.prepare_hybrid_geometry; assert not any(k.startswith('_hybrid_geometry_legacy_') for k in sys.modules); retired=['terrain_pipeline.hybrid_mesh_plane','terrain_pipeline.hybrid_river_faces','terrain_pipeline.hybrid_surface_composition','terrain_pipeline.hybrid_surface_composition_v2']; assert not any(k in sys.modules for k in retired)"
        process = _i19_subprocess.run([_i19_sys.executable, '-B', '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_legacy_stage_read_preserves_sys_path_and_current_module_bindings(self):
        from terrain_pipeline import hybrid_geometry as current_mesh
        before_path = list(_i19_sys.path)
        current_name = 'terrain_pipeline.hybrid_geometry'
        context = _i19_GeometryLegacyReplay()
        stage_tool = context.load('tools.prepare_hybrid_surface_composition_v3')
        data = stage_tool.load_stage({'path': str(stage_tool.SOURCE), 'sha256': stage_tool.SOURCE_SHA})
        self.assertEqual(_i19_sys.path, before_path)
        self.assertIs(_i19_sys.modules[current_name], current_mesh)
        self.assertTrue(stage_tool.__name__.startswith('_hybrid_geometry_legacy_'))
        self.assertFalse(data[0]['hydraulic_ready'])
        with self.assertRaises(ImportError):
            context.load('terrain_pipeline.unregistered_geometry_algorithm')
        self.assertEqual(_i19_sys.path, before_path)
        self.assertIs(_i19_sys.modules[current_name], current_mesh)

    def test_missing_legacy_module_does_not_leave_an_importable_stub(self):
        context = _i19_GeometryLegacyReplay()
        before = {name for name in _i19_sys.modules if name.startswith(context.prefix + '.')}
        with self.assertRaisesRegex(ImportError, 'outside frozen hybrid closure'):
            context.load('terrain_pipeline.unregistered_geometry_algorithm')
        after = {name for name in _i19_sys.modules if name.startswith(context.prefix + '.')}
        self.assertEqual(after, before)
        self.assertNotIn('terrain_pipeline.unregistered_geometry_algorithm', context.modules)

    def test_shared_current_frame_matches_archived_original(self):
        from terrain_pipeline.hybrid_geometry import plane_frame
        old = _i19_GeometryLegacyReplay().load('terrain_pipeline.hybrid_river_faces')
        arguments = ([10.0, 17.0, -3.0], [1.0, 2.0], [1.0, 10.0, -4.0])
        self.assertEqual(plane_frame(*arguments), old.plane_frame(*arguments))

class CurrentNativeIdentityBindingTests(_i19_unittest.TestCase):

    def fixture(self, root):
        import hashlib
        import numpy as np
        from terrain_pipeline.hybrid_geometry import identity
        from tools import td_shared_channel_fine_saved_audit as shared
        from tools.audit_hybrid_geometry import load_native_for_geometry
        expected = 'a' * 64
        hierarchy = root / 'native.npz'
        np.savez(hierarchy, manifest=np.frombuffer(_i19_json.dumps({'identity_sha256': expected, 'metadata': {'origin_m_xz': [0.0, 0.0], 'spacing_m': 1.0}}).encode(), dtype=np.uint8), height_m=np.zeros((2, 2)), valid_mask=np.ones((2, 2), bool), protected_mask=np.zeros((2, 2), bool), open_boundary_mask=np.zeros((2, 2), bool), cell_owner=np.zeros((2, 2), int), contribution_owner=np.zeros((2, 2), int), node_unknown_contact=np.zeros((2, 2), bool))

        def persist(name, record):
            record = dict(record)
            record['identity_sha256'] = identity(record)
            path = root / name
            path.write_text(_i19_json.dumps(record), encoding='utf-8')
            return ({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}, record)
        sections_pin, sections = persist('sections.json', {'hierarchy_identity_sha256': expected, 'selected_leaf_ids': [0]})
        protection_pin, _ = persist('protection.json', {'wet_protection': {'covered_native_cell_ids': [], 'stage_by_leaf': []}})
        native_pin = {'path': str(hierarchy), 'sha256': hashlib.sha256(hierarchy.read_bytes()).hexdigest()}
        geometry = {'inputs': {'original_hierarchy': native_pin, 'original_06_sections': sections_pin, 'original_wet_protection_manifest': protection_pin}}
        return (geometry, sections, persist, load_native_for_geometry, shared)

    def test_sections_external_pin_is_trust_anchor_and_is_recorded(self):
        with _i19_tempfile.TemporaryDirectory() as directory:
            root = _i19_Path(directory)
            geometry, _, _, load, shared = self.fixture(root)
            with _i19_mock.patch.object(_i19_current_io, 'ROOT', root), _i19_mock.patch.object(shared, 'ROOT', root):
                native, binding = load(geometry)
            self.assertEqual(native.height.shape, (2, 2))
            self.assertEqual(binding['sections_pin'], geometry['inputs']['original_06_sections'])
            self.assertEqual(binding['sections_identity_field'], 'hierarchy_identity_sha256')
            self.assertEqual(binding['expected_hierarchy_identity_sha256'], 'a' * 64)
            self.assertNotIn('identity_sha256', geometry['inputs']['original_hierarchy'])

    def test_rehashed_sections_content_still_fails_unchanged_external_pin(self):
        with _i19_tempfile.TemporaryDirectory() as directory:
            root = _i19_Path(directory)
            geometry, sections, persist, load, shared = self.fixture(root)
            sections.pop('identity_sha256')
            sections['hierarchy_identity_sha256'] = 'b' * 64
            persist('sections.json', sections)
            with _i19_mock.patch.object(_i19_current_io, 'ROOT', root), _i19_mock.patch.object(shared, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'SHA'):
                    load(geometry)

    def test_optional_original_pin_identity_cannot_conflict_with_sections(self):
        with _i19_tempfile.TemporaryDirectory() as directory:
            root = _i19_Path(directory)
            geometry, _, _, load, shared = self.fixture(root)
            geometry['inputs']['original_hierarchy']['identity_sha256'] = 'b' * 64
            with _i19_mock.patch.object(_i19_current_io, 'ROOT', root), _i19_mock.patch.object(shared, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'optional hierarchy pin identity differs'):
                    load(geometry)

    def test_manifest_identity_cannot_conflict_with_trusted_sections(self):
        with _i19_tempfile.TemporaryDirectory() as directory:
            root = _i19_Path(directory)
            geometry, sections, persist, load, shared = self.fixture(root)
            sections.pop('identity_sha256')
            sections['hierarchy_identity_sha256'] = 'b' * 64
            new_pin, _ = persist('sections.json', sections)
            geometry['inputs']['original_06_sections'] = new_pin
            with _i19_mock.patch.object(_i19_current_io, 'ROOT', root), _i19_mock.patch.object(shared, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'manifest/sections hierarchy identity differs'):
                    load(geometry)
