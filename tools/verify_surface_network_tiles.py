"""Fixed implementation verification; no generation, GPU, game or independent certification."""

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shutil
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline import surface_network_tiles as tiles
from terrain_pipeline.surface_network_consumer import GEOMETRY, _file_hash, load_surface_network_delivery
from tests.test_surface_network_consumer import forbid_generation
from tests.test_surface_network_tiles import BASELINES, CONSUMER, mutate_tile, write_manifest


def reject(action):
    try:
        action()
    except (ValueError, OSError) as error:
        return {'rejected': True, 'reason': str(error)}
    raise AssertionError('negative case unexpectedly accepted')


def snapshot(directory):
    return {str(path.relative_to(directory)).replace('\\', '/'): _file_hash(path)
            for path in directory.rglob('*') if path.is_file()}


def verify(directory):
    before = snapshot(CONSUMER)
    report = {'verification': tiles.VERSION, 'independent_acceptance': False,
              'source': str(CONSUMER), 'tile_cell_span': 13, 'scope': {
                  'square_stride_only': True, 'rectangular_query_windows': True,
                  'no_game_gpu_model_or_generation': True, 'publisher_authenticated': False},
              'successes': {}, 'rejections': {}, 'lifecycle': {}}
    stream = io.StringIO()
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromName('tests.test_surface_network_tiles')
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (directory / 'focused-tests.txt').write_text(stream.getvalue(), encoding='utf-8')
    report['tests'] = {'count': tests.testsRun, 'failures': len(tests.failures), 'errors': len(tests.errors),
                       'seconds': time.perf_counter() - started, 'passed': tests.wasSuccessful()}
    if not tests.wasSuccessful():
        raise AssertionError('focused tests failed; see focused-tests.txt')
    for kind, (volume, area) in BASELINES.items():
        source = load_surface_network_delivery(CONSUMER / kind)
        destination = directory / kind
        tiles.prepare_surface_network_tiles(CONSUMER / kind, destination, tile_cells=13)
        with forbid_generation():
            store = tiles.load_surface_network_tiles(destination)
            lazy = tiles.sample_surface_network_tiles(store, 1., 1.)
            assert set(store._cache) == {0}
            right = tiles.slice_surface_network_tiles(store, slice(0, 61), slice(25, 61))
            left = tiles.slice_surface_network_tiles(store, slice(0, 61), slice(0, 40))
            for name in GEOMETRY:
                np.testing.assert_array_equal(left['arrays'][name], source['geometry'][name][:, :40])
                np.testing.assert_array_equal(right['arrays'][name], source['geometry'][name][:, 25:])
                np.testing.assert_array_equal(left['arrays'][name][:, 25:], right['arrays'][name][:, :15])
            audit = tiles._plain(tiles.verify_all_tiles(store))
            assert abs(audit['integrals']['total_cut_m']['volume_m3'] - volume) < 1e-9
            assert audit['integrals']['total_cut_m']['area_m2'] == area
            for array in (*store.centerline.values(), *lazy['arrays'].values()):
                try:
                    array.flags.writeable = True
                except ValueError:
                    pass
                else:
                    raise AssertionError('mutable loaded array')
        report['successes'][kind] = {'path': str(destination), 'content_id': store.manifest['content_id'],
                                   'audit': audit, 'expected_volume_m3': volume, 'expected_area_m2': area,
                                   'save_reload': True, 'source_geometry_equal': True,
                                   'overlapping_windows_equal': True, 'hard_readonly': True,
                                   'lazy_sample_tile_and_proof_only': True}

    failures = directory / 'failures'
    failures.mkdir()

    def copied(name):
        destination = failures / name
        shutil.copytree(directory / 'baseline', destination)
        return destination

    for operation in ('stage', 'new-wet', 'disconnected-wet', 'cut', 'protected'):
        path = copied('rehashed-' + operation)
        index = 0 if operation == 'disconnected-wet' else 1

        def change(arrays):
            if operation in ('new-wet', 'disconnected-wet'):
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
            else:
                row, column = np.argwhere(arrays['wet_mask'])[0]
                if operation == 'stage':
                    arrays['water_surface_m'][row, column] += 2.
                elif operation == 'cut':
                    arrays['final_surface_m'][row, column] -= 5.
                    arrays['bed_cut_m'][:] = arrays['valley_surface_m'] - arrays['final_surface_m']
                    arrays['total_cut_m'][:] = arrays['source_surface_m'] - arrays['final_surface_m']
                else:
                    arrays['protected_mask'][row, column] = True

        mutate_tile(path, index, change)
        store = tiles.load_surface_network_tiles(path)
        report['rejections'][operation] = {**reject(lambda: tiles.sample_surface_network_tiles(store, 1. if index == 0 else 14., 1.)),
                                           'path': str(path), 'query_rejected': True, 'save_reload': True}
    for operation in ('missing-range', 'duplicate-range'):
        path = copied(operation)
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        if operation == 'missing-range':
            manifest['tiles'].pop()
        else:
            manifest['tiles'][1] = manifest['tiles'][0]
        write_manifest(path, manifest)
        report['rejections'][operation] = {**reject(lambda: tiles.load_surface_network_tiles(path)), 'path': str(path)}

    path = copied('cached-damage')
    store = tiles.load_surface_network_tiles(path)
    tiles.sample_surface_network_tiles(store, 1., 1.)
    file = path / 'tiles/000000.npz'
    payload = bytearray(file.read_bytes())
    payload[-1] ^= 1
    file.write_bytes(payload)
    report['rejections']['cached-damage'] = {**reject(lambda: tiles.sample_surface_network_tiles(store, 1., 1.)), 'path': str(path)}

    path = copied('proof-also-rehashed')

    def disconnected(arrays):
        arrays['wet_mask'][1, 1] = True
        arrays['water_surface_m'][1, 1] = arrays['final_surface_m'][1, 1] + .1

    mutate_tile(path, 0, disconnected, also_proof=True)
    store = tiles.load_surface_network_tiles(path)
    tiles.sample_surface_network_tiles(store, 1., 1.)
    report['rejections']['proof-also-rehashed'] = {**reject(lambda: tiles.verify_all_tiles(store)), 'path': str(path),
                                                 'query_local_check_passed': True, 'requires_full_audit': True,
                                                 'not_publisher_authentication': True}
    paused = directory / 'resume-success'
    assert tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', paused, tile_cells=13, max_tiles=1) is False
    staging = paused.with_name(paused.name + '.staging')
    report['lifecycle']['unfinished_load'] = reject(lambda: tiles.load_surface_network_tiles(staging))
    completed_hash = _file_hash(staging / 'tiles/000000.npz')
    assert tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', paused, tile_cells=13, resume=True, cancel=lambda: True) is False
    assert tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', paused, tile_cells=13, resume=True) == paused
    assert _file_hash(paused / 'tiles/000000.npz') == completed_hash
    report['lifecycle']['resume_success'] = {'path': str(paused), 'completed_tile_unchanged': True,
                                            'audit': tiles._plain(tiles.verify_all_tiles(tiles.load_surface_network_tiles(paused)))}
    damaged = failures / 'resume-damaged'
    assert tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', damaged, tile_cells=13, max_tiles=1) is False
    staging = damaged.with_name(damaged.name + '.staging')
    report['rejections']['resume-identity'] = {**reject(lambda: tiles.prepare_surface_network_tiles(CONSUMER / 'valley', damaged, tile_cells=13, resume=True)),
                                             'path': str(staging)}
    (staging / 'tiles/000000.npz').write_bytes(b'fixed damaged completed tile')
    report['rejections']['resume-damaged'] = {**reject(lambda: tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', damaged, tile_cells=13, resume=True)),
                                            'path': str(staging), 'destination_absent': not damaged.exists()}
    cancelled = failures / 'cancelled'
    assert tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', cancelled, tile_cells=13, cancel=lambda: True) is False
    report['rejections']['cancelled-load'] = {**reject(lambda: tiles.load_surface_network_tiles(cancelled.with_name('cancelled.staging'))),
                                            'path': str(cancelled.with_name('cancelled.staging'))}

    local_source = directory / 'source-copy-unavailable'
    shutil.copytree(CONSUMER / 'baseline', local_source)
    standalone = directory / 'standalone'
    tiles.prepare_surface_network_tiles(local_source, standalone, tile_cells=13)
    local_source.rename(directory / 'source-copy-moved')
    store = tiles.load_surface_network_tiles(standalone)
    tiles.sample_surface_network_tiles(store, 30., 30.)
    report['lifecycle']['original_source_unavailable'] = {'path': str(standalone), 'query_passed': True,
                                                        'audit': tiles._plain(tiles.verify_all_tiles(store))}
    lock_destination = failures / 'contention'
    competitors = []

    def owner(*args, **kwargs):
        for number in (2, 3):
            outcome = reject(lambda: tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', lock_destination, tile_cells=13))
            assert (lock_destination.with_name('contention.staging') / '.prepare.lock').exists()
            competitors.append({'caller': number, **outcome, 'owner_lock_preserved': True})
        return False

    with patch.object(tiles, '_prepare_unlocked', side_effect=owner):
        assert tiles.prepare_surface_network_tiles(CONSUMER / 'baseline', lock_destination, tile_cells=13) is False
    report['lifecycle']['lock_contention'] = competitors
    assert before == snapshot(CONSUMER)
    report['original_sources_unchanged'] = True
    report['source_file_hashes'] = before
    report['passed'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    utc = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    directory = ROOT / 'verification/surface-network-tiles' / ('run-' + utc)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    try:
        report = verify(directory)
    except Exception as error:
        report = {'verification': tiles.VERSION, 'passed': False, 'independent_acceptance': False,
                  'error_type': type(error).__name__, 'reason': str(error)}
        raise
    finally:
        report.update(utc_run=utc, path=str(directory), seconds=time.perf_counter() - started)
        (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        print(json.dumps({'path': str(directory), 'passed': report['passed'], 'seconds': report['seconds']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
