import tempfile
import json
from pathlib import Path
import shutil
import unittest
import zipfile
from unittest.mock import patch

import numpy as np

from terrain_pipeline.artifacts.contracts import digest
from terrain_pipeline.surface_network_consumer import GEOMETRY, _file_hash, load_surface_network_delivery
from terrain_pipeline import surface_network_tiles as tiles
from terrain_pipeline.surface_network_tiles import (
    load_surface_network_tiles, prepare_surface_network_tiles, sample_surface_network_tiles,
    slice_surface_network_tiles, slice_surface_network_tiles_world, verify_all_tiles,
)
from tests.test_surface_network_consumer import forbid_generation


ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / 'verification/surface-network-consumer/run-20260930T080544.956105Z'
BASELINES = {'baseline': (169.508735962729, 518.5), 'valley': (1051.594182146892, 2930.),
             'reroute': (29.111269224638, 89.5)}


def write_manifest(path, manifest):
    manifest['content_id'] = digest({name: value for name, value in manifest.items() if name != 'content_id'})
    (path / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')


def mutate_tile(path, index, change, *, also_proof=False):
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    tile = manifest['tiles'][index]
    file = path / tile['path']
    with np.load(file, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    change(arrays)
    np.savez(file, **arrays)
    tile['arrays'] = {name: tiles._record(array) for name, array in arrays.items()}
    tile['sha256'] = _file_hash(file)
    if also_proof:
        proof = path / 'proof' / f'{index:06d}.npz'
        np.savez(proof, **arrays)
        tile['proof_sha256'] = _file_hash(proof)
        manifest['recipe']['source_windows'][index] = tile['arrays']
    write_manifest(path, manifest)


class SurfaceNetworkTilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory()
        cls.root = Path(cls.workspace.name)
        cls.expected = {}
        cls.prepared = {}
        for kind in BASELINES:
            cls.expected[kind] = load_surface_network_delivery(CONSUMER / kind)
            cls.prepared[kind] = prepare_surface_network_tiles(CONSUMER / kind, cls.root / kind, tile_cells=13)

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def copy_store(self, directory, kind='baseline'):
        destination = Path(directory) / 'copy'
        shutil.copytree(self.prepared[kind], destination)
        return destination

    def test_three_final_consumer_packages_nondivisible_square_span_and_integrals(self):
        for kind, (volume, area) in BASELINES.items():
            with self.subTest(kind=kind), forbid_generation():
                store = load_surface_network_tiles(self.prepared[kind])
                audit = verify_all_tiles(store)
                self.assertEqual(audit['unique_nodes'], 61 * 61)
                self.assertEqual(audit['tile_count'], 25)
                self.assertEqual(store.manifest['tiles'][-1]['bounds'], (52, 61, 52, 61))
                self.assertAlmostEqual(audit['integrals']['total_cut_m']['volume_m3'], volume, places=10)
                self.assertEqual(audit['integrals']['total_cut_m']['area_m2'], area)
                for field in audit['integrals']:
                    for quantity in ('volume_m3', 'area_m2'):
                        self.assertAlmostEqual(audit['integrals'][field][quantity],
                                               audit['tile_weighted_integrals'][field][quantity], places=10)

    def test_every_seam_and_query_order_match_source(self):
        for kind in BASELINES:
            store = load_surface_network_tiles(self.prepared[kind])
            for start in reversed((0, 12, 25, 38, 51)):
                window = slice_surface_network_tiles(store, slice(start, min(start + 10, 61)), slice(0, 61))
                for name in GEOMETRY:
                    np.testing.assert_array_equal(window['arrays'][name], self.expected[kind]['geometry'][name][start:min(start + 10, 61)])
            left = slice_surface_network_tiles(store, slice(0, 61), slice(0, 40))
            right = slice_surface_network_tiles(store, slice(0, 61), slice(25, 61))
            for name in GEOMETRY:
                np.testing.assert_array_equal(left['arrays'][name][:, 25:], right['arrays'][name][:, :15])

    def test_load_and_query_are_lazy_only_intersecting_tile_and_proof(self):
        with patch.object(tiles, 'load_surface_network_delivery', side_effect=AssertionError('no full source load')), forbid_generation():
            with patch.object(tiles, '_read_arrays', wraps=tiles._read_arrays) as reads:
                store = load_surface_network_tiles(self.prepared['baseline'])
                self.assertEqual([call.args[0].name for call in reads.call_args_list], ['graph.npz'])
                reads.reset_mock()
                sample_surface_network_tiles(store, 1., 1.)
                self.assertEqual([call.args[0].relative_to(store.path).as_posix() for call in reads.call_args_list],
                                 ['tiles/000000.npz', 'proof/000000.npz'])
                reads.reset_mock()
                sample_surface_network_tiles(store, 1., 1.)
                self.assertEqual(reads.call_count, 0)
                self.assertEqual(set(store._cache), {0})

    def test_irrelevant_corrupt_tile_is_not_read_but_its_query_and_audit_reject(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.copy_store(directory)
            (path / 'tiles/000024.npz').write_bytes(b'corrupt')
            store = load_surface_network_tiles(path)
            sample_surface_network_tiles(store, 1., 1.)
            with self.assertRaises(ValueError):
                sample_surface_network_tiles(store, 59., 59.)
            with self.assertRaises(ValueError):
                verify_all_tiles(store)

    def test_cached_tile_and_cached_proof_are_rehashed_each_access(self):
        for filename in ('tiles/000000.npz', 'proof/000000.npz'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)
                store = load_surface_network_tiles(path)
                sample_surface_network_tiles(store, 1., 1.)
                target = path / filename
                data = bytearray(target.read_bytes())
                data[-1] ^= 1
                target.write_bytes(data)
                with self.assertRaises(ValueError):
                    sample_surface_network_tiles(store, 1., 1.)

    def test_cache_eviction_and_oversize_tile_hard_refusal(self):
        store = load_surface_network_tiles(self.prepared['baseline'])
        size = sum(math_record['shape'][0] * math_record['shape'][1] * np.dtype(math_record['dtype']).itemsize
                   for math_record in store.manifest['tiles'][0]['arrays'].values())
        with patch.object(tiles, 'MAX_CACHE_BYTES', size):
            sample_surface_network_tiles(store, 1., 1.)
            self.assertEqual(store._cache_bytes, size)
            sample_surface_network_tiles(store, 14., 1.)
            self.assertEqual(set(store._cache), {1})
            self.assertLessEqual(store._cache_bytes, size)
        store = load_surface_network_tiles(self.prepared['baseline'])
        with patch.object(tiles, 'MAX_CACHE_BYTES', size - 1):
            with self.assertRaisesRegex(ValueError, 'cache bound'):
                sample_surface_network_tiles(store, 1., 1.)
            self.assertEqual(store._cache_bytes, 0)

    def test_window_hard_limit_before_tile_read_or_allocation(self):
        store = load_surface_network_tiles(self.prepared['baseline'])
        with patch.object(tiles, 'MAX_WINDOW_CELLS', 4), patch.object(store, '_tile', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(ValueError, 'window cell bound'):
                slice_surface_network_tiles(store, slice(0, 3), slice(0, 2))
        for part in (slice(None, 2), slice(-1, 2), slice(0, 62), slice(0, 2, 2), slice(1, 1), slice(True, 2)):
            with self.assertRaises(ValueError):
                slice_surface_network_tiles(store, part, slice(0, 1))

    def test_world_sample_and_inclusive_world_window(self):
        store = load_surface_network_tiles(self.prepared['baseline'])
        window = slice_surface_network_tiles_world(store, (12., 12., 14., 14.))
        self.assertEqual(window['arrays']['wet_mask'].shape, (3, 3))
        np.testing.assert_array_equal(window['arrays']['final_surface_m'], self.expected['baseline']['geometry']['final_surface_m'][12:15, 12:15])
        for coordinates in ((-.1, 0.), (61., 0.), (float('nan'), 0.)):
            with self.assertRaises(ValueError):
                sample_surface_network_tiles(store, *coordinates)

    def test_arrays_cannot_reenable_write_and_nested_manifest_cannot_mutate(self):
        store = load_surface_network_tiles(self.prepared['baseline'])
        window = sample_surface_network_tiles(store, 1., 1.)
        for array in (*store.centerline.values(), *window['arrays'].values(), *store._cache[0].values()):
            with self.assertRaises(ValueError):
                array.flags.writeable = True
            with self.assertRaises(ValueError):
                array.flat[0] = 0
        with self.assertRaises(TypeError):
            store.manifest['recipe']['grid']['origin_x_m'] = 1
        with self.assertRaises(TypeError):
            store.manifest['tiles'][0]['arrays']['wet_mask']['dtype'] = '<f8'
        with self.assertRaises(TypeError):
            store.manifest['recipe']['grid']['shape_zx'][0] = 1

    def test_source_directory_unavailable_still_load_query_and_full_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            shutil.copytree(CONSUMER / 'baseline', source)
            destination = Path(directory) / 'tiles'
            prepare_surface_network_tiles(source, destination, tile_cells=17)
            source.rename(Path(directory) / 'source-unavailable')
            store = load_surface_network_tiles(destination)
            sample_surface_network_tiles(store, 30., 30.)
            self.assertTrue(verify_all_tiles(store)['source_replayed'])

    def test_cancel_and_budget_pause_resume_revalidate_and_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'tiles'
            self.assertIs(prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, max_tiles=1), False)
            staging = destination.with_name('tiles.staging')
            before = _file_hash(staging / 'tiles/000000.npz')
            with self.assertRaises(ValueError):
                load_surface_network_tiles(staging)
            self.assertIs(prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True, cancel=lambda: True), False)
            self.assertEqual(before, _file_hash(staging / 'tiles/000000.npz'))
            self.assertEqual(prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True), destination)
            self.assertEqual(before, _file_hash(destination / 'tiles/000000.npz'))
            self.assertTrue(verify_all_tiles(load_surface_network_tiles(destination))['verified'])
            with self.assertRaises(FileExistsError):
                prepare_surface_network_tiles(CONSUMER / 'baseline', destination)

    def test_resume_rejects_changed_source_recipe_and_written_tile_damage(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'tiles'
            prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, max_tiles=1)
            for source, span in ((CONSUMER / 'valley', 13), (CONSUMER / 'baseline', 17)):
                with self.assertRaisesRegex(ValueError, 'resume source or recipe changed'):
                    prepare_surface_network_tiles(source, destination, tile_cells=span, resume=True)
            staging = destination.with_name('tiles.staging')
            (staging / 'tiles/000000.npz').write_bytes(b'damage')
            with self.assertRaisesRegex(ValueError, 'completed tile damaged'):
                prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True, cancel=lambda: True)
            self.assertFalse(destination.exists())
            self.assertFalse((staging / 'manifest.json').exists())
            self.assertEqual((staging / 'tiles/000000.npz').read_bytes(), b'damage')

    def test_resume_rejects_staged_source_damage_and_completed_proof_damage(self):
        for relative in ('source/hydro.npz', 'proof/000000.npz'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / 'tiles'
                prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, max_tiles=1)
                staging = destination.with_name('tiles.staging')
                (staging / relative).write_bytes(b'damage')
                with self.assertRaises((ValueError, OSError, zipfile.BadZipFile)):
                    prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True)
                self.assertFalse(destination.exists())

    def test_cancel_immediately_before_and_after_manifest_commit_never_publishes(self):
        for point in (25, 26, 27):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / 'tiles'
                calls = 0

                def cancel():
                    nonlocal calls
                    calls += 1
                    return calls > point

                self.assertIs(prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, cancel=cancel), False)
                self.assertFalse(destination.exists())
                self.assertFalse((destination.with_name('tiles.staging') / 'manifest.json').exists())
                self.assertEqual(prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, resume=True), destination)

    def test_missing_duplicate_and_changed_ranges_rejected_at_load(self):
        for operation in ('missing', 'duplicate', 'range'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)
                manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
                if operation == 'missing':
                    manifest['tiles'].pop()
                elif operation == 'duplicate':
                    manifest['tiles'][1] = manifest['tiles'][0]
                else:
                    manifest['tiles'][0]['bounds'][1] -= 1
                write_manifest(path, manifest)
                with self.assertRaises(ValueError):
                    load_surface_network_tiles(path)

    def test_rehashed_stage_new_wet_and_disconnected_wet_reject_on_query(self):
        for operation in ('stage', 'new-wet', 'disconnected-wet'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)

                def change(arrays):
                    if operation == 'stage':
                        row, column = np.argwhere(arrays['wet_mask'])[0]
                        arrays['water_surface_m'][row, column] += 2.
                    else:
                        row, column = (1, 1)
                        if operation == 'new-wet':
                            neighbors = np.zeros_like(arrays['wet_mask'])
                            neighbors[1:] |= arrays['wet_mask'][:-1]
                            neighbors[:-1] |= arrays['wet_mask'][1:]
                            neighbors[:, 1:] |= arrays['wet_mask'][:, :-1]
                            neighbors[:, :-1] |= arrays['wet_mask'][:, 1:]
                            row, column = np.argwhere(neighbors & ~arrays['wet_mask'])[0]
                        arrays['wet_mask'][row, column] = True
                        arrays['water_surface_m'][row, column] = arrays['final_surface_m'][row, column] + .1

                index = 0 if operation == 'disconnected-wet' else 1
                mutate_tile(path, index, change)
                with self.assertRaisesRegex(ValueError, 'validated source window'):
                    sample_surface_network_tiles(load_surface_network_tiles(path), 14. if index else 1., 1.)

    def test_semantic_gate_rejects_depth_cut_domain_protection_even_with_rehashed_window_proof(self):
        for operation in ('depth', 'cut', 'domain', 'protected', 'stage-jump'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)

                def change(arrays):
                    row, column = np.argwhere(arrays['wet_mask'])[0]
                    if operation == 'depth':
                        arrays['water_surface_m'][row, column] = arrays['final_surface_m'][row, column] + .001
                    elif operation == 'cut':
                        arrays['final_surface_m'][row, column] -= 5.
                        arrays['bed_cut_m'][:] = arrays['valley_surface_m'] - arrays['final_surface_m']
                        arrays['total_cut_m'][:] = arrays['source_surface_m'] - arrays['final_surface_m']
                    elif operation == 'stage-jump':
                        arrays['water_surface_m'][row, column] += 2.
                    else:
                        arrays[operation + '_mask'][row, column] = operation == 'protected'

                mutate_tile(path, 1, change, also_proof=True)
                with self.assertRaises(ValueError):
                    sample_surface_network_tiles(load_surface_network_tiles(path), 14., 1.)

    def test_shared_seam_mismatch_rejects_query_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.copy_store(directory)

            def change(arrays):
                for name in ('source_surface_m', 'valley_surface_m', 'final_surface_m'):
                    arrays[name][1, 0] += .1

            mutate_tile(path, 1, change, also_proof=True)
            store = load_surface_network_tiles(path)
            with self.assertRaisesRegex(ValueError, 'seam mismatch'):
                slice_surface_network_tiles(store, slice(1, 2), slice(13, 14))
            with self.assertRaises(ValueError):
                verify_all_tiles(store)

    def test_npz_aggregate_uncompressed_bound_and_header_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'arrays.npz'
            arrays = {'first': np.zeros(1000), 'second': np.zeros(1000)}
            records = {name: tiles._record(array) for name, array in arrays.items()}
            np.savez_compressed(path, **arrays)
            with self.assertRaisesRegex(ValueError, 'total uncompressed'):
                tiles._read_arrays(path, records, limit=16100)
            np.savez(path, **arrays)
            records['first']['shape'] = [999]
            with self.assertRaisesRegex(ValueError, 'header mismatch'):
                tiles._read_arrays(path, records)

    def test_graph_integer_indices_and_topology_reject_after_rehash(self):
        for operation in ('float', 'order'):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as directory:
                path = self.copy_store(directory)
                manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
                with np.load(path / 'graph.npz') as archive:
                    arrays = {name: archive[name] for name in archive.files}
                if operation == 'float':
                    arrays['receiver'] = arrays['receiver'].astype(float)
                else:
                    arrays['order'] = arrays['order'][::-1]
                np.savez(path / 'graph.npz', **arrays)
                records = {name: tiles._record(array) for name, array in arrays.items()}
                manifest['graph']['arrays'] = records
                manifest['graph']['sha256'] = _file_hash(path / 'graph.npz')
                manifest['recipe']['source_manifest']['arrays'].update(records)
                source = manifest['recipe']['source_manifest']
                source['content_id'] = digest({name: value for name, value in source.items() if name != 'content_id'})
                manifest['recipe']['source_content_id'] = source['content_id']
                write_manifest(path, manifest)
                with self.assertRaises(ValueError):
                    load_surface_network_tiles(path)

    def test_invalid_span_budget_and_resume_reject_before_source_load(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'tiles'
            with patch.object(tiles, 'load_surface_network_delivery', side_effect=AssertionError('must not load')):
                for span in (True, 0, -1, 256, (13, 17), 13.0):
                    with self.assertRaises(ValueError):
                        prepare_surface_network_tiles('unused', destination, tile_cells=span)
                for options in ({'max_tiles': 0}, {'max_tiles': True}, {'resume': 1}, {'cancel': 1}):
                    with self.assertRaises(ValueError):
                        prepare_surface_network_tiles('unused', destination, **options)
            self.assertFalse(destination.with_name('tiles.staging').exists())

    def test_copy_only_declared_source_files_not_extra_files_or_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            shutil.copytree(CONSUMER / 'baseline', source)
            (source / 'undeclared.bin').write_bytes(b'must not be copied')
            (source / 'extras').mkdir()
            (source / 'extras/nested.bin').write_bytes(b'must not be copied')
            destination = Path(directory) / 'tiles'
            with self.assertRaisesRegex(ValueError, 'directory layout'):
                prepare_surface_network_tiles(source, destination, tile_cells=13, max_tiles=1)
            self.assertFalse(destination.exists())
            self.assertFalse((destination.with_name('tiles.staging') / 'manifest.json').exists())
            staging = destination.with_name('tiles.staging')
            staging.mkdir(exist_ok=True)
            manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
            copied = tiles._source_files(source, staging, manifest)
            self.assertFalse((copied / 'undeclared.bin').exists())
            self.assertFalse((copied / 'extras').exists())
            self.assertEqual({file.relative_to(copied).as_posix() for file in copied.rglob('*') if file.is_file()}, tiles.SOURCE_FILES)

    def test_entire_window_proof_rehash_is_not_publisher_authentication_full_audit_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.copy_store(directory)

            def change(arrays):
                arrays['wet_mask'][1, 1] = True
                arrays['water_surface_m'][1, 1] = arrays['final_surface_m'][1, 1] + .1

            mutate_tile(path, 0, change, also_proof=True)
            store = load_surface_network_tiles(path)
            self.assertTrue(sample_surface_network_tiles(store, 1., 1.)['arrays']['wet_mask'][0, 0])
            with self.assertRaisesRegex(ValueError, 'validated source'):
                verify_all_tiles(store)

    def test_exception_leaves_unpublished_staging_and_owner_unlocks(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'tiles'

            def cancel():
                raise RuntimeError('caller cancellation failure')

            with self.assertRaisesRegex(RuntimeError, 'caller cancellation failure'):
                prepare_surface_network_tiles(CONSUMER / 'baseline', destination, tile_cells=13, cancel=cancel)
            staging = destination.with_name('tiles.staging')
            self.assertFalse(destination.exists())
            self.assertFalse((staging / '.prepare.lock').exists())
            self.assertFalse((staging / 'manifest.json').exists())

    def test_destination_cannot_be_inside_immutable_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source'
            source.mkdir()
            with self.assertRaises(ValueError):
                prepare_surface_network_tiles(source, source / 'tiles')
            self.assertEqual(list(source.iterdir()), [])


class SurfaceNetworkTilesLockTests(unittest.TestCase):
    def test_failed_contender_does_not_unlock_owner_or_admit_third_call(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'tiles'
            staging = destination.with_name(destination.name + '.staging')

            def owner(*args, **kwargs):
                with self.assertRaises(FileExistsError):
                    prepare_surface_network_tiles('unused', destination)
                self.assertTrue((staging / '.prepare.lock').exists())
                with self.assertRaises(FileExistsError):
                    prepare_surface_network_tiles('unused', destination)
                return False

            with patch('terrain_pipeline.surface_network_tiles._prepare_unlocked', side_effect=owner) as work:
                self.assertIs(prepare_surface_network_tiles('unused', destination), False)
                self.assertEqual(work.call_count, 1)
            self.assertFalse((staging / '.prepare.lock').exists())
