"""Consolidated prepare_source_conforming_banks implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import argparse as _i14_argparse
from datetime import datetime as _i14_datetime
from datetime import timezone as _i14_timezone
import json as _i14_json
import os as _i14_os
from pathlib import Path as _i14_Path
import sys as _i14_sys
import time as _i14_time
import traceback as _i14_traceback
import psutil as _i14_psutil
import argparse as _i15_argparse
from datetime import datetime as _i15_datetime
from datetime import timezone as _i15_timezone
import json as _i15_json
from pathlib import Path as _i15_Path
import sys as _i15_sys
import time as _i15_time
import traceback as _i15_traceback
import psutil as _i15_psutil
CATEGORY = 'B'
ROOT = _i14_Path(__file__).resolve().parents[1]
_i14_sys.path.insert(0, str(ROOT))
PARENT = ROOT / 'verification/natural-river-network/fine-bed-shards-entry-20261005-01'
INDEX_SHA = 'af3c777166218e8968c0083e0a8e32ad5a416f8d841f5c09ebcd4c8f544261f9'
AUDIT_SHA = '5ef4a0ae5a09244a148dd5bee4db96f28aa7c479eda97e33c835826ae3888ea7'
MANIFEST_SHA = '2ad6022687e0c696aff9bedb60b5a4910ba36ce3dcbd0c911d9ac8e3496d3c84'
PREVIOUS_FAILURE = ROOT / 'verification/natural-river-network/source-conforming-banks-entry-20261006-01-failure.json'

def _read(path, expected_sha):
    from terrain_pipeline.common_infra import file_sha256 as _i14_file_sha256
    from terrain_pipeline.channel_geometry import _i46_MAX_BYTES as _i14_MAX_BYTES
    path = path.resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > _i14_MAX_BYTES or _i14_file_sha256(path) != expected_sha:
        raise ValueError('frozen JSON path/SHA/byte budget mismatch: ' + str(path))
    return _i14_json.loads(path.read_text(encoding='utf-8'))

def _read_pin(pin):
    record = _read(_i14_Path(pin['path']), pin['sha256'])
    if 'identity_sha256' in pin and record.get('identity_sha256') != pin['identity_sha256']:
        raise ValueError('frozen parent identity mismatch')
    return record

def _pin(path, record=None):
    from terrain_pipeline.common_infra import file_sha256 as _i14_file_sha256
    result = {'path': str(path.resolve()), 'sha256': _i14_file_sha256(path), 'bytes': path.stat().st_size}
    if record is not None and 'identity_sha256' in record:
        result['identity_sha256'] = record['identity_sha256']
    return result

def _observe(resource, process, phase, counters):
    memory = process.memory_info()
    resource['actual_peak_rss_bytes'] = max(resource['actual_peak_rss_bytes'], memory.rss, getattr(memory, 'peak_wset', 0))
    resource['last_rss_bytes'] = memory.rss
    resource['phase'] = phase
    resource['counters'] = counters
    resource['phase_samples'][phase] = {'rss_bytes': memory.rss, 'peak_rss_bytes': resource['actual_peak_rss_bytes'], 'counters': counters}

def _failure_log(output, resource, started, error):
    from terrain_pipeline.common_infra import file_sha256 as _i14_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i14_publish_bytes
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_FLAGS as _i14_FLAGS
    from terrain_pipeline.channel_geometry import MAX_RSS as _i14_MAX_RSS
    stamp = _i14_datetime.now(_i14_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = output.parent / (output.name + '-failure-' + stamp + '-' + str(_i14_os.getpid()) + '.json')
    result = {'schema': 'td-source-conforming-banks-preparation-failure-v2', 'status': 'diagnostic_failure', 'attempt_output': str(output), 'exception': type(error).__name__ + ': ' + str(error), 'traceback': ''.join(_i14_traceback.format_exception(type(error), error, error.__traceback__))[-6000:], 'resource': resource, 'actual_peak_rss_bytes': resource['actual_peak_rss_bytes'], 'max_rss_bytes': _i14_MAX_RSS, 'elapsed_s': _i14_time.perf_counter() - started, 'candidate_directory_exists': output.exists(), 'published_candidate': False, 'previous_failure': _pin(PREVIOUS_FAILURE) if PREVIOUS_FAILURE.exists() else None, 'frozen_parent_index_sha256': INDEX_SHA, 'water_solves': 0, 'code_sha256': {name: _i14_file_sha256(ROOT / name) for name in ('terrain_pipeline/channel_geometry.py', 'tools/prepare_source_conforming_banks.py', 'tests/test_channel_geometry.py')}, **{flag: False for flag in _i14_FLAGS}}
    _i14_publish_bytes(path, _i14_json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode('utf-8'))
    return path

def _run_prepare_td_source_conforming_banks():
    from terrain_pipeline.channel_geometry import _i46_MAX_BYTES as _i14_MAX_BYTES
    from terrain_pipeline.channel_geometry import MAX_RSS as _i14_MAX_RSS
    parser = _i14_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=_i14_Path, required=True)
    parser.add_argument('--max-cells', type=int, default=2000000)
    parser.add_argument('--max-shard-bytes', type=int, default=_i14_MAX_BYTES)
    args = parser.parse_args()
    output = args.output.resolve()
    parent = (ROOT / 'verification/natural-river-network').resolve()
    if output.exists() or not output.is_relative_to(parent) or output == parent:
        raise ValueError('new verification output directory required')
    started = _i14_time.perf_counter()
    process = _i14_psutil.Process()
    resource = {'actual_peak_rss_bytes': 0, 'last_rss_bytes': 0, 'phase': 'load_inputs', 'counters': {}, 'phase_samples': {}}

    def resource_check():
        _observe(resource, process, getattr(resource_check, 'phase', 'load_inputs'), getattr(resource_check, 'counters', {}))
        if resource['actual_peak_rss_bytes'] > _i14_MAX_RSS:
            raise MemoryError('hard 1GiB peak RSS exceeded')
    try:
        _prepare(args, output, resource_check, resource, started)
    except Exception as error:
        _observe(resource, process, resource['phase'], resource['counters'])
        try:
            failure = _failure_log(output, resource, started, error)
            print('Failure diagnostics: ' + str(failure), file=_i14_sys.stderr)
        except Exception as log_error:
            print('Failure diagnostics unavailable: ' + str(log_error), file=_i14_sys.stderr)
        raise

def _prepare(args, output, resource_check, resource, started):
    from terrain_pipeline.common_infra import file_sha256 as _i14_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i14_publish_bytes
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _i14_load_basin_hierarchy
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_FLAGS as _i14_FLAGS
    from terrain_pipeline.channel_geometry import MAX_RSS as _i14_MAX_RSS
    from terrain_pipeline.channel_geometry import build_source_conforming_banks as _i14_build_source_conforming_banks
    from terrain_pipeline.channel_geometry import save_source_conforming_banks as _i14_save_source_conforming_banks
    resource_check()
    index = _read(PARENT / 'index.json', INDEX_SHA)
    audit = _read(PARENT / 'independent-audit.json', AUDIT_SHA)
    if audit['status'] != 'passed' or audit['index_sha256'] != INDEX_SHA or audit['manifest_sha256'] != MANIFEST_SHA or (index['manifest']['sha256'] != MANIFEST_SHA):
        raise ValueError('frozen shards01 independent audit binding mismatch')
    pins = {**index['inputs'], 'shards_index': _pin(PARENT / 'index.json'), 'shards_independent_audit': _pin(PARENT / 'independent-audit.json'), 'shards_manifest': index['manifest'], 'shards_raw': index['raw'], **{'shard:' + str(number): pin for number, pin in enumerate(index['shards'])}}
    for name, pin in pins.items():
        path = _i14_Path(pin['path']).resolve(strict=True)
        if not path.is_relative_to(ROOT) or _i14_file_sha256(path) != pin['sha256']:
            raise ValueError('immutable input changed: ' + name)
    base = _read_pin(pins['base_raster'])
    manifest, raw = (_read_pin(index['manifest']), _read_pin(index['raw']))
    shards = [_read_pin(pin) for pin in index['shards']]
    if raw['identity_sha256'] != manifest['raw_identity_sha256'] or [item['identity_sha256'] for item in shards] != manifest['shard_identities'] or audit['material_ledger'] != manifest['material_ledger_merged']:
        raise ValueError('saved shard raw/material/transaction identity chain mismatch')
    sections = _read_pin(pins['06_sections'])
    transitions = _read_pin(pins['09_transitions'])
    paths = _read_pin(pins['06_paths'])
    hierarchy_pin = pins['hierarchy']
    hierarchy = _i14_load_basin_hierarchy(_i14_Path(hierarchy_pin['path']), expected_sha256=hierarchy_pin['sha256'], expected_identity=hierarchy_pin['identity_sha256'])
    resource_check()
    package = _i14_build_source_conforming_banks(base, {'manifest': manifest, 'raw': raw, 'shards': shards}, hierarchy, sections, transitions, paths, audit['readiness'], input_pins=pins, max_cells=args.max_cells, max_shard_bytes=args.max_shard_bytes, resource_check=resource_check)
    resource_check.phase = 'save_candidate'
    resource_check.counters = {}
    _i14_save_source_conforming_banks(package, output, resource_check=resource_check)
    resource_check()
    chunks = {kind: [_pin(output / kind / (chunk['chunk_id'] + '.json'), chunk) for chunk in package[kind]] for kind in ('raw', 'proofs', 'effects')}
    result = {'schema': 'td-source-conforming-banks-preparation-v2', 'status': 'candidate_only', 'inputs': pins, 'manifest': _pin(output / 'manifest.json', package['manifest']), 'chunks': chunks, 'connection_queue': _pin(output / 'connection-queue.json', package['queue']), 'summary': package['manifest']['summary'], 'material_ledger_parent': package['manifest']['material_ledger_parent'], 'material_ledger_delta': package['manifest']['material_ledger_delta'], 'resource': {'actual_peak_rss_bytes': resource['actual_peak_rss_bytes'], 'max_rss_bytes': _i14_MAX_RSS, 'phase_samples': resource['phase_samples'], 'elapsed_s': _i14_time.perf_counter() - started, 'water_solves': 0, 'old_fine_center_source_resamples': 0, 'new_lattice_cells': 0, 'old_package_reaudited': False}, 'previous_failure': _pin(PREVIOUS_FAILURE) if PREVIOUS_FAILURE.exists() else None, 'code_sha256': {name: _i14_file_sha256(ROOT / name) for name in ('terrain_pipeline/channel_geometry.py', 'tools/prepare_source_conforming_banks.py', 'terrain_pipeline/td_fine_bed_raster.py', 'terrain_pipeline/td_fine_bed_shards.py', 'terrain_pipeline/mountain_source_adapter.py', 'terrain_pipeline/basin_topology.py')}, 'old_mesh_passed': False, 'full_watershed_fine_verified': False, 'independent_audit_passed': False, **{flag: False for flag in _i14_FLAGS}}
    payload = _i14_json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode('utf-8')
    if len(payload) > args.max_shard_bytes:
        raise MemoryError('new preparation index exceeds bounded byte budget')
    resource_check()
    _i14_publish_bytes(output / 'index.json', payload)
    print(_i14_json.dumps({'summary': result['summary'], 'material_ledger_delta': result['material_ledger_delta']}, sort_keys=True))

def _entry_prepare_td_source_conforming_banks():
    _run_prepare_td_source_conforming_banks()
_i15_sys.path.insert(0, str(ROOT))
PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_PARENT = ROOT / 'verification/natural-river-network/source-conforming-banks-entry-20261006-03'
PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_INDEX_SHA = 'aac571e0a6f0b730e0ebd5c67db9ac9182f2f1398409754d33d9d66273fc277e'
PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_AUDIT_SHA = 'c410f1871d8b17cee5b48cb2ba141f3cce41b447daa042ddb8637abdc42041d9'
DIAGNOSIS_SHA = 'b4db6be9440d251f03273e90dfa62c26c71871f5531ba3a33c10caf963c1e871'
CODE_FILES = ('terrain_pipeline/channel_geometry.py', 'tools/prepare_source_conforming_banks.py', 'tests/test_channel_geometry.py')

def _frozen_inputs():
    from terrain_pipeline.common_infra import file_sha256 as _i15_file_sha256
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES as _i15_MAX_BYTES
    index = _read(PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_PARENT / 'index.json', PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_INDEX_SHA)
    audit = _read(PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_PARENT / 'independent-audit.json', PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_AUDIT_SHA)
    diagnosis = _read(PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_PARENT / 'boundary-diagnosis.json', DIAGNOSIS_SHA)
    if audit['status'] != 'passed' or audit['index_sha256'] != PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_INDEX_SHA or audit['manifest_sha256'] != index['manifest']['sha256'] or (diagnosis['index_sha256'] != PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_INDEX_SHA) or (index['summary']['candidate_components'] != 0) or (index['summary']['refused_components'] != 14):
        raise ValueError('fixed rejected 03/audit/diagnosis linkage mismatch')
    for code_pins in (index['code_sha256'], audit['audit_code_sha256']):
        for name, expected in code_pins.items():
            path = (ROOT / name).resolve(strict=True)
            if not path.is_relative_to(ROOT) or _i15_file_sha256(path) != expected:
                raise ValueError('frozen v2 implementation/audit changed: ' + name)
    pins = dict(index['inputs'])
    pins.update(source_banks_v2_index=_pin(PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_PARENT / 'index.json'), source_banks_v2_independent_audit=_pin(PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_PARENT / 'independent-audit.json'), source_banks_v2_boundary_diagnosis=_pin(PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_PARENT / 'boundary-diagnosis.json'), source_banks_v2_manifest=index['manifest'], source_banks_v2_connection_queue=index['connection_queue'])
    for kind in ('raw', 'proofs', 'effects'):
        for number, pin in enumerate(index['chunks'][kind]):
            pins['source_banks_v2_' + kind + ':' + str(number)] = pin
    for name, pin in pins.items():
        path = _i15_Path(pin['path']).resolve(strict=True)
        if not path.is_relative_to(ROOT) or path.stat().st_size > _i15_MAX_BYTES or _i15_file_sha256(path) != pin['sha256']:
            raise ValueError('immutable fixed input changed: ' + name)
    if pins['shards_index']['sha256'] != INDEX_SHA or pins['shards_independent_audit']['sha256'] != AUDIT_SHA or pins['shards_manifest']['sha256'] != MANIFEST_SHA:
        raise ValueError('original shard01 hard pins mismatch')
    shard_index = _read_pin(pins['shards_index'])
    shard_audit = _read_pin(pins['shards_independent_audit'])
    if shard_audit['status'] != 'passed' or shard_audit['index_sha256'] != INDEX_SHA or shard_audit['manifest_sha256'] != MANIFEST_SHA or (shard_index['manifest'] != pins['shards_manifest']) or (shard_index['raw'] != pins['shards_raw']) or any((pin != pins['shard:' + str(number)] for number, pin in enumerate(shard_index['shards']))):
        raise ValueError('original shard01 index/audit/raw/shards chain mismatch')
    return (pins, shard_index, shard_audit)

def _prepare_td_source_conforming_banks_mechanism_3_prepare(args, output, resource_check, resource, started):
    from terrain_pipeline.common_infra import file_sha256 as _i15_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i15_publish_bytes
    from terrain_pipeline.basin_topology import load_basin_hierarchy as _i15_load_basin_hierarchy
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_FLAGS as _i15_FLAGS
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_RSS as _i15_MAX_RSS
    from terrain_pipeline.channel_geometry import POLICY as _i15_POLICY
    from terrain_pipeline.channel_geometry import POLICY_IDENTITY_SHA256 as _i15_POLICY_IDENTITY_SHA256
    from terrain_pipeline.channel_geometry import td_source_conforming_banks_mechanism_3_build_source_conforming_banks as _i15_build_source_conforming_banks
    from terrain_pipeline.channel_geometry import td_source_conforming_banks_mechanism_3_save_source_conforming_banks as _i15_save_source_conforming_banks
    resource_check()
    pins, shard_index, shard_audit = _frozen_inputs()
    base = _read_pin(pins['base_raster'])
    manifest, raw = (_read_pin(pins['shards_manifest']), _read_pin(pins['shards_raw']))
    shards = [_read_pin(pin) for pin in shard_index['shards']]
    if raw['identity_sha256'] != manifest['raw_identity_sha256'] or [shard['identity_sha256'] for shard in shards] != manifest['shard_identities'] or shard_audit['material_ledger'] != manifest['material_ledger_merged']:
        raise ValueError('frozen raw/shard material identity chain mismatch')
    sections, paths = (_read_pin(pins['06_sections']), _read_pin(pins['06_paths']))
    transitions = _read_pin(pins['09_transitions'])
    hierarchy_pin = pins['hierarchy']
    hierarchy = _i15_load_basin_hierarchy(_i15_Path(hierarchy_pin['path']), expected_sha256=hierarchy_pin['sha256'], expected_identity=hierarchy_pin['identity_sha256'])
    resource_check()
    package = _i15_build_source_conforming_banks(base, {'manifest': manifest, 'raw': raw, 'shards': shards}, hierarchy, sections, transitions, paths, shard_audit['readiness'], input_pins=pins, max_cells=args.max_cells, max_shard_bytes=args.max_shard_bytes, resource_check=resource_check)
    resource_check.phase = 'save_v3_candidate'
    resource_check.counters = {}
    _i15_save_source_conforming_banks(package, output, resource_check=resource_check)
    resource_check()
    chunks = {kind: [_pin(output / kind / (chunk['chunk_id'] + '.json'), chunk) for chunk in package[kind]] for kind in ('raw', 'proofs', 'effects')}
    result = {'schema': 'td-source-conforming-banks-preparation-v3', 'status': 'candidate_only', 'policy': _i15_POLICY, 'policy_identity_sha256': _i15_POLICY_IDENTITY_SHA256, 'inputs': pins, 'parent_candidate_index_sha256': PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_INDEX_SHA, 'parent_candidate_audit_sha256': PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_AUDIT_SHA, 'manifest': _pin(output / 'manifest.json', package['manifest']), 'chunks': chunks, 'connection_queue': _pin(output / 'connection-queue.json', package['queue']), 'summary': package['manifest']['summary'], 'material_ledger_parent': package['manifest']['material_ledger_parent'], 'material_ledger_delta': package['manifest']['material_ledger_delta'], 'resource': {'actual_peak_rss_bytes': resource['actual_peak_rss_bytes'], 'max_rss_bytes': _i15_MAX_RSS, 'phase_samples': resource['phase_samples'], 'elapsed_s': _i15_time.perf_counter() - started, 'water_solves': 0, 'old_fine_center_source_resamples': 0, 'new_lattice_cells': 0, 'old_package_reaudited': False}, 'code_sha256': {name: _i15_file_sha256(ROOT / name) for name in CODE_FILES + ('terrain_pipeline/channel_geometry.py', 'tools/prepare_source_conforming_banks.py', 'terrain_pipeline/td_fine_bed_raster.py', 'terrain_pipeline/td_fine_bed_shards.py', 'terrain_pipeline/mountain_source_adapter.py', 'terrain_pipeline/basin_topology.py')}, 'old_mesh_passed': False, 'independent_audit_passed': False, **{flag: False for flag in _i15_FLAGS}}
    payload = _i15_json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode('utf-8')
    if len(payload) > args.max_shard_bytes:
        raise MemoryError('new v3 preparation index exceeds bounded byte budget')
    resource_check()
    _i15_publish_bytes(output / 'index.json', payload)
    print(_i15_json.dumps({'summary': result['summary'], 'policy_identity_sha256': _i15_POLICY_IDENTITY_SHA256, 'material_ledger_delta': result['material_ledger_delta']}, sort_keys=True))

def _run_prepare_td_source_conforming_banks_v3():
    from terrain_pipeline.common_infra import file_sha256 as _i15_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i15_publish_bytes
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_FLAGS as _i15_FLAGS
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_BYTES as _i15_MAX_BYTES
    from terrain_pipeline.channel_geometry import MAX_CELLS as _i15_MAX_CELLS
    from terrain_pipeline.channel_geometry import TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_MAX_RSS as _i15_MAX_RSS
    from terrain_pipeline.channel_geometry import POLICY_IDENTITY_SHA256 as _i15_POLICY_IDENTITY_SHA256
    parser = _i15_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=_i15_Path, required=True)
    parser.add_argument('--max-cells', type=int, default=_i15_MAX_CELLS)
    parser.add_argument('--max-shard-bytes', type=int, default=_i15_MAX_BYTES)
    args = parser.parse_args()
    output = args.output.resolve()
    parent = (ROOT / 'verification/natural-river-network').resolve()
    if output.exists() or not output.is_relative_to(parent) or output == parent:
        raise ValueError('new verification output directory required')
    if not (1 <= args.max_cells <= _i15_MAX_CELLS and 4096 <= args.max_shard_bytes <= _i15_MAX_BYTES):
        raise ValueError('invalid v3 preparation resource budget')
    started = _i15_time.perf_counter()
    process = _i15_psutil.Process()
    resource = {'actual_peak_rss_bytes': 0, 'last_rss_bytes': 0, 'phase': 'load_fixed_v2_inputs', 'counters': {}, 'phase_samples': {}}

    def resource_check():
        _observe(resource, process, getattr(resource_check, 'phase', 'load_fixed_v2_inputs'), getattr(resource_check, 'counters', {}))
        if resource['actual_peak_rss_bytes'] > _i15_MAX_RSS:
            raise MemoryError('hard 1GiB peak RSS exceeded')
    try:
        _prepare_td_source_conforming_banks_mechanism_3_prepare(args, output, resource_check, resource, started)
    except Exception as error:
        _observe(resource, process, resource['phase'], resource['counters'])
        stamp = _i15_datetime.now(_i15_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        failure_path = output.parent / (output.name + '-failure-' + stamp + '.json')
        failure = {'schema': 'td-source-conforming-banks-preparation-failure-v3', 'status': 'diagnostic_failure', 'policy_identity_sha256': _i15_POLICY_IDENTITY_SHA256, 'attempt_output': str(output), 'exception': type(error).__name__ + ': ' + str(error), 'traceback': ''.join(_i15_traceback.format_exception(type(error), error, error.__traceback__))[-6000:], 'resource': resource, 'max_rss_bytes': _i15_MAX_RSS, 'elapsed_s': _i15_time.perf_counter() - started, 'candidate_directory_exists': output.exists(), 'published_candidate': False, 'frozen_parent_index_sha256': PREPARE_TD_SOURCE_CONFORMING_BANKS_MECHANISM_3_INDEX_SHA, 'code_sha256': {name: _i15_file_sha256(ROOT / name) for name in CODE_FILES}, 'water_solves': 0, **{flag: False for flag in _i15_FLAGS}}
        _i15_publish_bytes(failure_path, _i15_json.dumps(failure, sort_keys=True, allow_nan=False, indent=2).encode('utf-8'))
        raise

def _entry_prepare_td_source_conforming_banks_v3():
    _run_prepare_td_source_conforming_banks_v3()

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'bands': '_entry_prepare_td_source_conforming_banks', 'sweep': '_entry_prepare_td_source_conforming_banks_v3'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        option = '--profile'
        if option:
            parser.add_argument(option, choices=tuple(commands), required=True)
            parsed, values = parser.parse_known_args(values)
            selected = getattr(parsed, option[2:].replace('-', '_'))
        else:
            parser.add_argument('command', choices=tuple(commands))
            parsed, values = parser.parse_known_args(values)
            selected = parsed.command
    function = globals()[commands[selected]]
    previous = sys.argv
    try:
        sys.argv = [previous[0]] + values
        return function()
    finally:
        sys.argv = previous
if __name__ == '__main__':
    main()
