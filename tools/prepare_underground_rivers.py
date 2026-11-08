"""Consolidated prepare_underground_rivers implementations; numeric expressions preserved."""
from __future__ import annotations
import argparse as _i43_argparse
from dataclasses import asdict as _i43_asdict
import json as _i43_json
from pathlib import Path as _i43_Path
import shutil as _i43_shutil
import sys as _i43_sys
import time as _i43_time
from terrain_pipeline.hybrid_geometry import MAX_BYTES as _i43_MAX_BYTES
from terrain_pipeline.hybrid_geometry import hybrid_cave_geometry_guard as _i43_guard
from terrain_pipeline.hybrid_geometry import seal as _i43_seal
from terrain_pipeline.hybrid_geometry import FilePin as _i43_FilePin
from terrain_pipeline.underground_rivers import CAPABILITIES as _i43_CAPABILITIES
from terrain_pipeline.underground_rivers import Parameters as _i43_Parameters
from terrain_pipeline.underground_rivers import build_preview as _i43_build_preview
from tools.prepare_hybrid_geometry import checked_identity as _x33_checked_identity
from tools.prepare_hybrid_geometry import file_sha as _x34_file_sha
from tools.prepare_hybrid_geometry import load_inputs as _x35_load_inputs
from tools.prepare_hybrid_geometry import read as _x36_read
from tools.prepare_hybrid_geometry import save as _x37_save
CATEGORY = 'C'
ROOT = _i43_Path(__file__).resolve().parents[1]
_i43_sys.path.insert(0, str(ROOT))
_i43_sys.path.insert(0, str(ROOT / '.scratch/hybrid-river-network/python-deps'))
SOURCE = ROOT / 'verification/natural-river-network/hybrid-cave-geometry-20261006-03'
INDEX_SHA = 'd7b971d28f07ff457776e0ce65ff8d583a4d1f70e50cbb3bdaad8e4909679fd6'
AUDIT_SHA = '703d457eb93afa0a74ab9fc5a7bae7149cbe45d492a89202b484948a434c3364'
DEFAULT_OUTPUT = ROOT / 'verification/natural-river-network/underground-river-v1-20261006-01'
CODE_FILES = ('terrain_pipeline/underground_rivers.py', 'tools/prepare_underground_rivers.py', 'tests/test_underground_rivers.py')

def load_source():
    pins = {'geometry03_index': {'path': str(SOURCE / 'index.json'), 'sha256': INDEX_SHA}, 'geometry03_audit': {'path': str(SOURCE / 'independent-audit-v2.json'), 'sha256': AUDIT_SHA}}
    index, audit = (_x36_read(pins['geometry03_index']), _x36_read(pins['geometry03_audit']))
    _x33_checked_identity(index)
    _x33_checked_identity(audit)
    if audit['status'] != 'passed' or audit.get('errors') or audit['geometry_sha256'] != index['geometry']['sha256']:
        raise ValueError('fixed geometry03 passed audit linkage required')
    for name, expected in index['code_sha256'].items():
        if _x34_file_sha(ROOT / name) != expected:
            raise ValueError('frozen geometry03 code changed:' + name)
    geometry = _x36_read(index['geometry'])
    _x33_checked_identity(geometry)
    for name, expected in geometry['readonly_dependency_code_sha256'].items():
        if _x34_file_sha(ROOT / name) != expected:
            raise ValueError('frozen source dependency changed:' + name)
    for key in ('rock_before', 'vdm'):
        pins[key] = index['artifacts'][key]
    pins['geometry03'] = index['geometry']
    pins['graph'] = index['graph']
    rock, vdm = (_x36_read(pins['rock_before']), _x36_read(pins['vdm']))
    _x33_checked_identity(rock)
    _x33_checked_identity(vdm)
    _, sampler = _x35_load_inputs(_i43_FilePin(**index['graph']))
    return (rock, vdm, sampler, pins)

def prepare(output, parameters=_i43_Parameters()):
    output = _i43_Path(output).resolve()
    partial = output.with_name(output.name + '.partial')
    if output.exists() or partial.exists() or (not output.is_relative_to(ROOT / 'verification/natural-river-network')):
        raise ValueError('new natural-river-network output directory required; never overwrite')
    started = _i43_time.perf_counter()
    parents = {}
    preview = None
    try:
        rock, vdm, sampler, parents = load_source()
        preview = _i43_build_preview(rock, vdm, sampler, parents, parameters, started=started)
        if _i43_time.perf_counter() - started > 60.0:
            raise ValueError('60s generation budget exceeded')
        index = {'schema': 'td-underground-river-preparation-v1', 'status': 'geometry_checked', 'rejection_reasons': []}
    except (ValueError, MemoryError, OSError) as error:
        preview = None
        index = {'schema': 'td-underground-river-preparation-v1', 'status': 'refused', 'rejection_reasons': [str(error)]}
    index.update(parameters=_i43_asdict(parameters), parents=parents, capabilities=dict(_i43_CAPABILITIES), code_sha256={name: _x34_file_sha(ROOT / name) for name in CODE_FILES}, resource={'elapsed_s': _i43_time.perf_counter() - started, 'max_rss_bytes': 1024 ** 3, 'max_payload_bytes': _i43_MAX_BYTES, 'max_elapsed_s': 60.0, 'actual_peak_rss_bytes': _i43_guard(), 'solver_calls': 0})
    partial.mkdir(parents=True)
    try:
        if preview is not None:
            pin = _x37_save(partial / 'preview.json', preview)
            pin['path'] = str(output / 'preview.json')
            index['preview'] = pin
            index['metrics'] = preview['metrics']
        _i43_seal(index)
        _x37_save(partial / 'index.json', index)
        if sum((path.stat().st_size for path in partial.iterdir())) > _i43_MAX_BYTES:
            raise ValueError('total payload exceeds 64MiB')
        if preview is not None and _i43_time.perf_counter() - started > 60.0:
            raise ValueError('60s publication budget exceeded')
        partial.rename(output)
    except BaseException:
        _i43_shutil.rmtree(partial)
        raise
    return index

def _entry_prepare_underground_river_v1():
    parser = _i43_argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=_i43_Path, default=DEFAULT_OUTPUT)
    for name, default in _i43_asdict(_i43_Parameters()).items():
        parser.add_argument('--' + name.replace('_', '-'), type=int if name == 'seed' else float, default=default)
    args = parser.parse_args()
    try:
        parameters = _i43_Parameters(**{name: getattr(args, name) for name in _i43_asdict(_i43_Parameters())})
        index = prepare(args.output, parameters)
        summary = {'status': index['status'], 'metrics': index.get('metrics'), 'rejection_reasons': index['rejection_reasons'], 'output': str(args.output.resolve())}
    except (ValueError, MemoryError, OSError) as error:
        summary = {'status': 'refused', 'metrics': None, 'rejection_reasons': [str(error)]}
    print(_i43_json.dumps(summary, allow_nan=False))
    return 0 if summary['status'] == 'geometry_checked' else 2

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'prepare-underground-river-v1': '_entry_prepare_underground_river_v1'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('command', choices=tuple(commands))
        parsed, values = parser.parse_known_args(values)
        selected = parsed.command
    function = globals()[commands[selected]]
    previous = sys.argv
    try:
        sys.argv = [previous[0]] + values
        return function(values) if inspect.signature(function).parameters else function()
    finally:
        sys.argv = previous
if __name__ == '__main__':
    main()
