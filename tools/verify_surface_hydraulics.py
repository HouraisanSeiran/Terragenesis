"""Consolidated verify_surface_hydraulics implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dataclasses import replace as _i2_replace
from datetime import datetime as _i2_datetime
from datetime import timezone as _i2_timezone
import json as _i2_json
from pathlib import Path as _i2_Path
import sys as _i2_sys
import numpy as _i2_np
from dataclasses import replace as _i8_replace
from datetime import datetime as _i8_datetime
from datetime import timezone as _i8_timezone
import json as _i8_json
from pathlib import Path as _i8_Path
import sys as _i8_sys
import numpy as _i8_np
import json as _i3_json
from pathlib import Path as _i3_Path
import sys as _i3_sys
import types as _i3_types
from dataclasses import replace as _i3_replace
from datetime import datetime as _i4_datetime
from datetime import timezone as _i4_timezone
import json as _i4_json
from pathlib import Path as _i4_Path
import sys as _i4_sys
import time as _i4_time
from dataclasses import replace as _i4_replace
import numpy as _i4_np
from terrain_pipeline import surface_hydraulics as _i4_base
from terrain_pipeline import surface_hydraulics as _i4_accelerated
import argparse as _i5_argparse
import json as _i5_json
from pathlib import Path as _i5_Path
import sys as _i5_sys
import numpy as _i5_np
from scipy.ndimage import label as _i5_label
from datetime import datetime as _i6_datetime
from datetime import timezone as _i6_timezone
import json as _i6_json
from pathlib import Path as _i6_Path
import sys as _i6_sys
import numpy as _i6_np
from dataclasses import replace as _i7_replace
from datetime import datetime as _i7_datetime
from datetime import timezone as _i7_timezone
import json as _i7_json
from pathlib import Path as _i7_Path
import sys as _i7_sys
import numpy as _i7_np
import json as _i9_json
from pathlib import Path as _i9_Path
import sys as _i9_sys
import zipfile as _i9_zipfile
import numpy as _i9_np
import cProfile as _i10_cProfile
from datetime import datetime as _i10_datetime
from datetime import timezone as _i10_timezone
import io as _i10_io
import json as _i10_json
from pathlib import Path as _i10_Path
import pstats as _i10_pstats
import sys as _i10_sys
import time as _i10_time
import numpy as _i10_np
from datetime import datetime as _i11_datetime
from datetime import timezone as _i11_timezone
import json as _i11_json
from pathlib import Path as _i11_Path
import sys as _i11_sys
import numpy as _i11_np
import json as _i12_json
from pathlib import Path as _i12_Path
import sys as _i12_sys
import zipfile as _i12_zipfile
import numpy as _i12_np
import json as _i13_json
from pathlib import Path as _i13_Path
import sys as _i13_sys
import numpy as _i13_np
CATEGORY = 'B'
ROOT = _i2_Path(__file__).resolve().parents[1]
_i2_sys.path.insert(0, str(ROOT))
RAW = ROOT / 'verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-td-output.npz'
RAW_SHA = 'e1dc646b990388af3bf284b614b10c2a834d0259429539d2a7d3d2cc844712ae'

def benchmark():
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i2_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i2_prepare_surface_geometry
    from terrain_pipeline.surface_hydraulics import advance_inertial_surface as _i2_advance_inertial_surface
    from terrain_pipeline.common_infra import file_sha256 as _i2_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i2_publish_bytes
    if _i2_file_sha256(RAW) != RAW_SHA:
        raise ValueError('pinned primary TD raw hash mismatch')
    with _i2_np.load(RAW, allow_pickle=False) as archive:
        height = archive['elevation_m'].astype(_i2_np.float64)
    if height.shape != (256, 256):
        raise ValueError('full primary region required')
    output = ROOT / 'verification/regional-hydraulics' / ('benchmark-' + _i2_datetime.now(_i2_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    geometry = _i2_prepare_surface_geometry(height, spacing_m=30.0, origin_m_xz=[-184320.0, 61440.0], source_identity=RAW_SHA)
    budget = _i2_replace(_i2_SurfaceBudget(), max_wall_s=120.0, max_substeps=10000)
    report = {'schema': 'regional-hydraulics-short-preflight-v1', 'raw_sha256': RAW_SHA, 'full_cells': 65536, 'area_m2': 58982400.0, 'budget': vars(budget), 'cases': {}, 'source_hashes': {'terrain_pipeline/surface_hydraulics.py': _i2_file_sha256(ROOT / 'terrain_pipeline/surface_hydraulics.py'), 'tools/verify_surface_hydraulics.py': _i2_file_sha256(_i2_Path(__file__))}}
    _i2_publish_bytes(output / 'predeclared.json', _i2_json.dumps(report, indent=2).encode('ascii'))
    for name, depth in (('dry_zero_input', 0.0), ('uniform_005m_closed', 0.05)):
        result = _i2_advance_inertial_surface(geometry, initial_depth_m=_i2_np.full(height.shape, depth), forcing_interval_s=900.0, intervals=1, forcing_provider=lambda index: _i2_np.zeros(height.shape), boundary_stage_provider=lambda index: _i2_np.zeros(1024), source_identity=RAW_SHA, forcing_identity='benchmark_no_rain_not_A_hydrology', budget=budget, snapshot_interval_s=900.0)
        meta = result['metadata']
        physical = meta['committed_time_s']
        cost = meta['wall_s'] / max(physical, 1e-30)
        steps_rate = meta['substeps'] / max(physical, 1e-30)
        report['cases'][name] = {'metadata': meta, 'diagnostics': result['diagnostics'], 'linear_cost_projection_not_guarantee': {'24h_wall_s': cost * 86400, '72h_wall_s': cost * 259200, '24h_substeps': steps_rate * 86400, '72h_substeps': steps_rate * 259200}, 'max_depth_m': float(result['arrays']['depth_m'].max()), 'volume_balance_error_m3': meta['final_volume_m3'] - meta['initial_volume_m3']}
        print(name, _i2_json.dumps(report['cases'][name]), flush=True)
    report['source_unchanged'] = all((_i2_file_sha256(ROOT / key) == value for key, value in report['source_hashes'].items()))
    _i2_publish_bytes(output / 'report.json', _i2_json.dumps(report, indent=2).encode('ascii'))
    print('BENCHMARK', output)

def forcing_benchmark():
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i2_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i2_prepare_surface_geometry
    from terrain_pipeline.surface_hydraulics import advance_inertial_surface as _i2_advance_inertial_surface
    from terrain_pipeline.common_infra import publish_bytes as _i2_publish_bytes
    from terrain_pipeline.regional_surface_source import load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as load_forcing
    source_dir = ROOT / 'verification/regional-source/run-20261001T095258008789Z'
    forcing_dir = ROOT / 'verification/regional-forcing/run-20261001T095608600719Z'
    source_meta = _i2_json.loads((source_dir / 'manifest.json').read_text(encoding='utf-8'))
    handoff = _i2_json.loads((forcing_dir / 'handoff-manifest.json').read_text(encoding='utf-8'))
    source = load_source(source_dir / 'source.npz', expected_sha256=source_meta['source_sha256'])
    loaded = load_forcing(forcing_dir / 'uniform_heavy', expected_manifest_sha256=handoff['cases']['uniform_heavy']['manifest_sha256'], source_identity=source['identity_sha256'])
    height = source['arrays']['height_m']
    geometry = _i2_prepare_surface_geometry(height, spacing_m=30.0, origin_m_xz=source['metadata']['origin_m_xz'], source_identity=source['identity_sha256'], boundary_kind=_i2_np.ones(1024, _i2_np.int64))
    output = ROOT / 'verification/regional-hydraulics' / ('forcing-benchmark-' + _i2_datetime.now(_i2_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    budget = _i2_replace(_i2_SurfaceBudget(), max_wall_s=120.0, max_substeps=10000)
    peak = int(_i2_np.asarray(loaded['metadata']['ledger']['runoff_m3']).argmax())
    report = {'source_identity': source['identity_sha256'], 'height_source_identity': source['metadata']['height_source_identity'], 'forcing_manifest_sha256': handoff['cases']['uniform_heavy']['manifest_sha256'], 'budget': vars(budget), 'scope': 'full_grid_900s_performance_probes_not_continuous_storm', 'cases': {}}
    _i2_publish_bytes(output / 'predeclared.json', _i2_json.dumps(report, indent=2).encode('ascii'))
    probes = [(peak, cap) for cap in (30.0, 3.0, 0.3)] if '--drag-sensitivity' in _i2_sys.argv else [(0, 30.0), (peak, 30.0)]
    report['probes'] = probes
    report['discretization'] = 'local_inertia_analytic_implicit_new_q_Manning_drag'
    _i2_publish_bytes(output / 'probe-declaration.json', _i2_json.dumps(report, indent=2).encode('ascii'))
    for index, cap in probes:
        forcing = loaded['runoff_volume_m3'][index].copy() / 900.0
        result = _i2_advance_inertial_surface(geometry, initial_depth_m=_i2_np.zeros(height.shape), forcing_interval_s=900.0, intervals=1, forcing_provider=lambda step: forcing, boundary_stage_provider=lambda step: _i2_np.zeros(1024), source_identity=source['identity_sha256'], forcing_identity=report['forcing_manifest_sha256'], budget=_i2_replace(budget, max_dt_s=cap))
        key = str(index) + '_dt' + str(cap)
        report['cases'][key] = {'metadata': result['metadata'], 'diagnostics': result['diagnostics'], 'projection_24h_wall_s': result['metadata']['wall_s'] * 86400 / max(result['metadata']['committed_time_s'], 1e-30)}
        _i2_np.save(output / (key + '-final-depth.npy'), result['arrays']['depth_m'][-1], allow_pickle=False)
        print('A_FORCING', key, _i2_json.dumps(report['cases'][key]), flush=True)
    loaded['runoff_volume_m3']._mmap.close()
    _i2_publish_bytes(output / 'report.json', _i2_json.dumps(report, indent=2).encode('ascii'))
    print('FORCING_BENCHMARK', output)

def continuous_probe():
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i2_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i2_prepare_surface_geometry
    from terrain_pipeline.surface_hydraulics import advance_inertial_surface as _i2_advance_inertial_surface
    from terrain_pipeline.common_infra import file_sha256 as _i2_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i2_publish_bytes
    from terrain_pipeline.regional_surface_source import load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as load_forcing
    source_dir = ROOT / 'verification/regional-source/run-20261001T095258008789Z'
    forcing_dir = ROOT / 'verification/regional-forcing/run-20261001T095608600719Z'
    source_meta = _i2_json.loads((source_dir / 'manifest.json').read_text(encoding='utf-8'))
    handoff = _i2_json.loads((forcing_dir / 'handoff-manifest.json').read_text(encoding='utf-8'))
    source = load_source(source_dir / 'source.npz', expected_sha256=source_meta['source_sha256'])
    forcing_sha = handoff['cases']['uniform_heavy']['manifest_sha256']
    loaded = load_forcing(forcing_dir / 'uniform_heavy', expected_manifest_sha256=forcing_sha, source_identity=source['identity_sha256'])
    height = source['arrays']['height_m']
    geometry = _i2_prepare_surface_geometry(height, spacing_m=30.0, origin_m_xz=source['metadata']['origin_m_xz'], source_identity=source['identity_sha256'], boundary_kind=_i2_np.ones(1024, _i2_np.int64))
    output = ROOT / 'verification/regional-hydraulics' / ('continuous-probe-' + _i2_datetime.now(_i2_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    budget = _i2_SurfaceBudget()
    intervals = 28
    declaration = {'model': 'local_inertia_analytic_implicit_new_q_drag', 'budget': vars(budget), 'intervals': intervals, 'duration_s': intervals * 900, 'source_identity': source['identity_sha256'], 'height_source_identity': source['metadata']['height_source_identity'], 'forcing_manifest_sha256': forcing_sha, 'source_hashes': {str(path.relative_to(ROOT)): _i2_file_sha256(path) for path in (ROOT / 'terrain_pipeline/surface_hydraulics.py', _i2_Path(__file__))}}
    _i2_publish_bytes(output / 'predeclared.json', _i2_json.dumps(declaration, indent=2).encode('ascii'))

    def observe(certificate):
        index = certificate['interval']
        print('INTERVAL', index, certificate['time_end_s'], float(certificate['depth_after_m'].max()), flush=True)
    result = _i2_advance_inertial_surface(geometry, initial_depth_m=_i2_np.zeros(height.shape), forcing_interval_s=900.0, intervals=intervals, forcing_provider=lambda index: loaded['runoff_volume_m3'][index].astype(_i2_np.float64) / 900.0, boundary_stage_provider=lambda index: _i2_np.zeros(1024), source_identity=source['identity_sha256'], forcing_identity=forcing_sha, budget=budget, interval_observer=observe)
    with (output / 'states.npz').open('xb') as stream:
        _i2_np.savez_compressed(stream, **result['arrays'])
    declaration['result'] = {'metadata': result['metadata'], 'diagnostics': result['diagnostics']}
    declaration['source_unchanged'] = all((_i2_file_sha256(ROOT / key) == value for key, value in declaration['source_hashes'].items()))
    _i2_publish_bytes(output / 'report.json', _i2_json.dumps(declaration, indent=2).encode('ascii'))
    loaded['runoff_volume_m3']._mmap.close()
    print('CONTINUOUS_PROBE', output, _i2_json.dumps(declaration['result']), flush=True)

def _entry_verify_regional_hydraulics():
    if '--continuous-probe' in _i2_sys.argv:
        continuous_probe()
    elif '--forcing-benchmark' in _i2_sys.argv:
        forcing_benchmark()
    else:
        benchmark()
_i8_sys.path.insert(0, str(ROOT))
SOURCE = ROOT / 'verification/regional-source/run-20261001T095258008789Z'
FORCING = ROOT / 'verification/regional-forcing/run-20261001T095608600719Z'
SOURCE_SHA = 'ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da'

def write_packet(directory, name, packet):
    from terrain_pipeline.common_infra import publish_bytes as _i8_publish_bytes
    arrays = {key: value for key, value in packet.items() if isinstance(value, _i8_np.ndarray)}
    meta = {key: value for key, value in packet.items() if not isinstance(value, _i8_np.ndarray)}
    with (directory / (name + '.npz')).open('xb') as stream:
        _i8_np.savez_compressed(stream, **arrays)
    _i8_publish_bytes(directory / (name + '.json'), _i8_json.dumps(meta, indent=2).encode('ascii'))

def _run_verify_regional_hydraulics_full():
    from terrain_pipeline.common_infra import file_sha256 as _i8_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i8_publish_bytes
    from terrain_pipeline.regional_surface_source import load_source as _i8_load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as _i8_load_forcing
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i8_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i8_prepare_surface_geometry
    from terrain_pipeline.surface_hydraulics import advance_inertial_surface as _i8_advance_inertial_surface
    source = _i8_load_source(SOURCE / 'source.npz', expected_sha256=SOURCE_SHA)
    handoff = _i8_json.loads((FORCING / 'handoff-manifest.json').read_text(encoding='utf-8'))
    height = source['arrays']['height_m']
    if height.shape != (256, 256):
        raise ValueError('entire 65536-cell finite region required')
    output = ROOT / 'verification/regional-hydraulics' / ('full-' + _i8_datetime.now(_i8_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    budget = _i8_SurfaceBudget()
    cases = [('dry', 'dry', False, False), ('wet_no_rain', 'wet_no_rain', False, False), ('uniform_heavy', 'uniform_heavy', False, False), ('uniform_heavy_tailwater', 'uniform_heavy', True, False), ('uniform_heavy_half_cfl', 'uniform_heavy', False, True)]
    if '--case' in _i8_sys.argv:
        selected = _i8_sys.argv[_i8_sys.argv.index('--case') + 1]
        cases = [case for case in cases if case[0] == selected]
        if not cases:
            raise ValueError('unknown predeclared case')
    paths = [_i8_Path(__file__), ROOT / 'terrain_pipeline/surface_hydraulics.py']
    source_hashes = {str(path.relative_to(ROOT)): _i8_file_sha256(path) for path in paths}
    declaration = {'algorithm': 'regional-surface-local-inertial-D4-implicit-new-q-drag-v2', 'cases': cases, 'budget': vars(budget), 'duration_s': 259200.0, 'source_sha256': SOURCE_SHA, 'source_identity': source['identity_sha256'], 'height_source_identity': source['metadata']['height_source_identity'], 'forcing_handoff_sha256': _i8_file_sha256(FORCING / 'handoff-manifest.json'), 'source_hashes': source_hashes, 'disk_budget_per_case_bytes': 2 * 1024 ** 3, 'tailwater': {'east_rows': [252, 253, 254, 255], 'south_columns': [252, 253, 254, 255], 'absolute_stage_m': float(height[-1, -1] + 10), 'start_s': 43200.0, 'end_s': 86400.0, 'outside_event': 'engineering_drainage_stage_at_local_boundary_crest'}, 'sampled_momentum_intervals': list(range(0, 288, 24)), 'sampling_scope': 'first_substep_only_not_all_trajectory_momentum', 'sensitivity': {'max_dt_s': 15.0, 'inertial_cfl': 0.225, 'forcing_interval_s': 900.0}}
    _i8_publish_bytes(output / 'predeclared.json', _i8_json.dumps(declaration, indent=2).encode('ascii'))
    print('FULL_OUTPUT', output, flush=True)
    for name, forcing_name, raised, half in cases:
        directory = output / name
        directory.mkdir()
        forcing_sha = handoff['cases'][forcing_name]['manifest_sha256']
        loaded = _i8_load_forcing(FORCING / forcing_name, expected_manifest_sha256=forcing_sha, source_identity=source['identity_sha256'])
        kinds = _i8_np.ones(1024, _i8_np.int64)
        selected_faces = _i8_np.r_[256 + _i8_np.arange(252, 256), 768 + _i8_np.arange(252, 256)]
        if raised:
            kinds[selected_faces] = 2
        geometry = _i8_prepare_surface_geometry(height, spacing_m=30.0, origin_m_xz=source['metadata']['origin_m_xz'], source_identity=source['identity_sha256'], boundary_kind=kinds)
        write_packet(directory, 'geometry', {**geometry['arrays'], **geometry['metadata']})

        def tailwater(index):
            result = geometry['arrays']['boundary_crest_m'].copy()
            if raised and 48 <= index < 96:
                result[selected_faces] = declaration['tailwater']['absolute_stage_m']
            return result

        def interval_observer(packet):
            write_packet(directory, 'interval-%03d' % packet['interval'], packet)
            if packet['interval'] % 12 == 0:
                print(name, 'INTERVAL', packet['interval'], 'depth', float(packet['depth_after_m'].max()), flush=True)

        def momentum_observer(packet):
            if packet['interval'] in declaration['sampled_momentum_intervals']:
                write_packet(directory, 'momentum-%03d' % packet['interval'], packet)
        case_budget = _i8_replace(budget, max_dt_s=15.0, inertial_cfl=0.225) if half else budget
        _i8_publish_bytes(directory / 'binding.json', _i8_json.dumps({'forcing_manifest_sha256': forcing_sha, 'forcing_directory': str((FORCING / forcing_name).relative_to(ROOT)), 'source_identity': source['identity_sha256'], 'height_source_identity': source['metadata']['height_source_identity'], 'budget': vars(case_budget)}, indent=2).encode('ascii'))
        result = _i8_advance_inertial_surface(geometry, initial_depth_m=_i8_np.zeros(height.shape), forcing_interval_s=900.0, intervals=288, forcing_provider=lambda index: loaded['runoff_volume_m3'][index].astype(_i8_np.float64) / 900.0, boundary_stage_provider=tailwater, source_identity=source['identity_sha256'], forcing_identity=forcing_sha, budget=case_budget, interval_observer=interval_observer, momentum_observer=momentum_observer)
        write_packet(directory, 'states', {**result['arrays'], 'metadata': result['metadata'], 'diagnostics': result['diagnostics']})
        loaded['runoff_volume_m3']._mmap.close()
        hashes = {path.name: _i8_file_sha256(path) for path in directory.iterdir() if path.is_file()}
        size = sum((path.stat().st_size for path in directory.iterdir() if path.is_file()))
        _i8_publish_bytes(directory / 'manifest.json', _i8_json.dumps({'artifacts': hashes, 'bytes': size, 'disk_budget_passed': size <= declaration['disk_budget_per_case_bytes'], 'source_hashes': source_hashes, 'source_unchanged': all((_i8_file_sha256(ROOT / key) == value for key, value in source_hashes.items()))}, indent=2).encode('ascii'))
        print('CASE_DONE', name, _i8_json.dumps(result['metadata']), _i8_json.dumps(result['diagnostics']), flush=True)
        del result
    print('FULL_DONE', output, flush=True)

def _entry_verify_regional_hydraulics_full():
    _run_verify_regional_hydraulics_full()
_i3_sys.path.insert(0, str(ROOT))
START_HASHES = {}

def accelerated_budget():
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _x1_SurfaceBudget
    return _i3_replace(_x1_SurfaceBudget(), max_wall_s=21600.0, max_substeps=2000000, max_face_evaluations=300000000000)

def publish_backend(path, payload):
    from terrain_pipeline.common_infra import file_sha256 as _i3_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i3_publish_bytes
    if _i3_Path(path).name == 'predeclared.json':
        declaration = _i3_json.loads(payload)
        declaration['execution_backend'] = 'numba_face_limiter_fastmath_false_v1_reference_control_flow'
        declaration['scope'] = 'new_independent_from_initial_run_not_resume_not_old_budget_extension'
        declaration['source_hashes']['terrain_pipeline/surface_hydraulics.py'] = _i3_file_sha256(ROOT / 'terrain_pipeline/surface_hydraulics.py')
        declaration['source_hashes']['tools/verify_surface_hydraulics.py'] = _i3_file_sha256(_i3_Path(__import__('sys').modules[__name__].__file__))
        declaration['source_hashes'].update(START_HASHES)
        payload = _i3_json.dumps(declaration, indent=2).encode('ascii')
    elif _i3_Path(path).name == 'manifest.json':
        manifest = _i3_json.loads(payload)
        manifest['source_hashes'].update(START_HASHES)
        manifest['source_unchanged'] = manifest['source_unchanged'] and all((_i3_file_sha256(ROOT / name) == digest for name, digest in START_HASHES.items()))
        payload = _i3_json.dumps(manifest, indent=2).encode('ascii')
    _i3_publish_bytes(path, payload)

def _run_verify_regional_hydraulics_accelerated_full():
    from terrain_pipeline.surface_hydraulics import advance_accelerated_surface as _i3_advance_accelerated_surface
    from terrain_pipeline.common_infra import file_sha256 as _i3_file_sha256
    for path in (_i3_Path(__file__), _i3_Path(__import__('sys').modules[__name__].__file__), ROOT / 'terrain_pipeline/surface_hydraulics.py', ROOT / 'terrain_pipeline/surface_hydraulics.py', ROOT / 'terrain_pipeline/regional_surface_source.py', ROOT / 'terrain_pipeline/climate_forcing.py', ROOT / 'terrain_pipeline/common_infra.py'):
        START_HASHES[str(path.relative_to(ROOT))] = _i3_file_sha256(path)
    namespace = dict(_run_verify_regional_hydraulics_full.__globals__)
    namespace['_i8_advance_inertial_surface'] = _i3_advance_accelerated_surface
    namespace['__file__'] = __file__
    namespace['_i8_publish_bytes'] = publish_backend
    namespace['_i8_SurfaceBudget'] = accelerated_budget
    run = _i3_types.FunctionType(_run_verify_regional_hydraulics_full.__code__, namespace, 'accelerated_full')
    run()

def _entry_verify_regional_hydraulics_accelerated_full():
    _run_verify_regional_hydraulics_accelerated_full()
_i4_sys.path.insert(0, str(ROOT))

def _run_verify_regional_hydraulics_acceleration():
    from terrain_pipeline.common_infra import publish_bytes as _i4_publish_bytes
    from terrain_pipeline.common_infra import file_sha256 as _i4_file_sha256
    case = ROOT / 'verification/regional-hydraulics/full-20261001T110401380014Z/uniform_heavy_half_cfl'
    packet_path = sorted(case.glob('interval-*.npz'))[-1]
    with _i4_np.load(case / 'geometry.npz', allow_pickle=False) as archive:
        geometry = {'arrays': {key: archive[key] for key in archive.files}, 'metadata': _i4_json.loads((case / 'geometry.json').read_text())}
    with _i4_np.load(packet_path, allow_pickle=False) as archive:
        packet = {key: archive[key] for key in archive.files}
    arguments = (geometry, packet['depth_before_m'], packet['internal_q_before_m3_s'], packet['boundary_q_before_m3_s'], geometry['arrays']['boundary_crest_m'], packet['forcing_volume_m3'] / 900.0, 0.5, _i4_base.SurfaceBudget())
    outputs = {}
    timings = {}
    for name, function in (('numpy', _i4_base.limited_inertial_fluxes), ('numba', _i4_accelerated.regional_surface_hydraulics_accelerated_limited_inertial_fluxes)):
        outputs[name] = function(*arguments)
        start = _i4_time.perf_counter()
        for index in range(200):
            function(*arguments)
        timings[name] = _i4_time.perf_counter() - start
    errors = []
    for index in (0, 1):
        expected, actual = (outputs['numpy'][index], outputs['numba'][index])
        if not _i4_np.allclose(actual, expected, rtol=2e-13, atol=1e-12):
            raise ValueError('accelerated real-state flux mismatch')
        errors.append(float(abs(actual - expected).max(initial=0)))
    report = {'packet': str(packet_path.relative_to(ROOT)), 'packet_sha256': _i4_file_sha256(packet_path), 'timing_200_calls_s': timings, 'speedup': timings['numpy'] / timings['numba'], 'max_flux_absolute_error_m3_s': errors, 'reference_limiter': outputs['numpy'][2], 'accelerated_limiter': outputs['numba'][2], 'warmup_excluded': True, 'fastmath': False, 'hashes': {str(path.relative_to(ROOT)): _i4_file_sha256(path) for path in (ROOT / 'terrain_pipeline/surface_hydraulics.py', ROOT / 'terrain_pipeline/surface_hydraulics.py', _i4_Path(__file__))}}
    output = ROOT / 'verification/regional-hydraulics' / ('acceleration-probe-' + _i4_datetime.now(_i4_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir()
    _i4_publish_bytes(output / 'predeclared.json', _i4_json.dumps({'scope': 'full_grid_900s_from_saved_depth_zero_Q_not_resume', 'budget': vars(_i4_replace(_i4_base.SurfaceBudget(), max_dt_s=15.0, inertial_cfl=0.225, max_wall_s=300.0)), 'source_packet_sha256': report['packet_sha256'], 'hashes': report['hashes']}, indent=2).encode('ascii'))
    trajectories = {}
    for name, function in (('numpy', _i4_base.advance_inertial_surface), ('numba', _i4_accelerated.advance_accelerated_surface)):
        trajectories[name] = function(geometry, initial_depth_m=packet['depth_before_m'].reshape(256, 256).copy(), forcing_interval_s=900.0, intervals=1, forcing_provider=lambda index: (packet['forcing_volume_m3'] / 900.0).reshape(256, 256), boundary_stage_provider=lambda index: geometry['arrays']['boundary_crest_m'].copy(), source_identity=geometry['metadata']['source_identity'], forcing_identity='saved_interval_constant_probe_not_resume', budget=_i4_replace(_i4_base.SurfaceBudget(), max_dt_s=15.0, inertial_cfl=0.225, max_wall_s=300.0))
    report['full_step_900s'] = {name: {'metadata': result['metadata'], 'diagnostics': result['diagnostics']} for name, result in trajectories.items()}
    report['trajectory_max_errors'] = {}
    for key in trajectories['numpy']['arrays']:
        expected, actual = (trajectories['numpy']['arrays'][key], trajectories['numba']['arrays'][key])
        if expected.shape != actual.shape or not _i4_np.allclose(actual, expected, rtol=2e-10, atol=1e-08):
            raise ValueError('900s full-step trajectory mismatch: ' + key)
        report['trajectory_max_errors'][key] = float(abs(actual - expected).max(initial=0))
    report['full_step_speedup'] = trajectories['numpy']['metadata']['wall_s'] / trajectories['numba']['metadata']['wall_s']
    _i4_publish_bytes(output / 'report.json', _i4_json.dumps(report, indent=2).encode('ascii'))
    print(_i4_json.dumps(report), flush=True)

def _entry_verify_regional_hydraulics_acceleration():
    _run_verify_regional_hydraulics_acceleration()
_i5_sys.path.insert(0, str(ROOT))

def read_states(directory, *, expected_manifest_sha256, space=False):
    from terrain_pipeline.common_infra import file_sha256 as _i5_file_sha256
    from terrain_pipeline.regional_hydraulics_archive import read_arrays as _i5_read_arrays
    from terrain_pipeline.regional_hydraulics_archive import strict_json as _i5_strict_json
    directory = _i5_Path(directory)
    if _i5_file_sha256(directory / 'manifest.json') != expected_manifest_sha256:
        raise ValueError('external comparison manifest SHA')
    manifest = _i5_strict_json(directory / 'manifest.json')
    digest = manifest['artifacts']['states.npz']
    if _i5_file_sha256(directory / 'states.npz') != digest:
        raise ValueError('comparison saved archive hash')
    import zipfile
    with zipfile.ZipFile(directory / 'states.npz') as archive:
        with archive.open('time_s.npy') as stream:
            version = _i5_np.lib.format.read_magic(stream)
            header = _i5_np.lib.format.read_array_header_1_0 if version == (1, 0) else _i5_np.lib.format.read_array_header_2_0
            shape, order, dtype = header(stream)
            if len(shape) != 1 or not 1 <= shape[0] <= 50 or order or (dtype != _i5_np.float64):
                raise ValueError('comparison bounded snapshot header')
    count = shape[0]
    size, faces, boundary = (128, 32512, 512) if space else (256, 130560, 1024)
    specs = {'time_s': ((count,), 'float64'), 'depth_m': ((count, size, size), 'float64'), 'initial_depth_m': ((size, size), 'float64'), 'ledger': ((count, 5), 'float64'), 'final_internal_q_m3_s': ((faces,), 'float64'), 'final_boundary_q_m3_s': ((boundary,), 'float64')}
    if space:
        specs['H0_m'] = ((128, 128), 'float64')
    arrays = _i5_read_arrays(directory / 'states.npz', specs, expected_sha256=digest)
    return (arrays, _i5_file_sha256(directory / 'manifest.json'))

def compare(base_directory, other_directory, *, base_sha256, other_sha256, space=False, tailwater=False):
    from terrain_pipeline.common_infra import file_sha256 as _i5_file_sha256
    from terrain_pipeline.regional_hydraulics_archive import read_arrays as _i5_read_arrays
    from terrain_pipeline.regional_hydraulics_archive import strict_json as _i5_strict_json
    from terrain_pipeline.regional_hydraulics_archive import GEOMETRY as _i5_GEOMETRY
    base, base_sha = read_states(base_directory, expected_manifest_sha256=base_sha256)
    other, other_sha = read_states(other_directory, expected_manifest_sha256=other_sha256, space=space)

    def authenticated(directory, name):
        manifest = _i5_strict_json(_i5_Path(directory) / 'manifest.json')
        if name not in manifest['artifacts'] or _i5_file_sha256(_i5_Path(directory) / name) != manifest['artifacts'][name]:
            raise ValueError('comparison authenticated metadata')
        return _i5_strict_json(_i5_Path(directory) / name)
    base_binding = authenticated(base_directory, 'binding.json')
    base_status = authenticated(base_directory, 'states.json')['metadata']
    base_geometry = authenticated(base_directory, 'geometry.json')
    if base_geometry['spacing_m'] != 30.0 or base_geometry['origin_m_xz'] != [-184320.0, 61440.0] or base_geometry['area_m2'] != 58982400.0:
        raise ValueError('comparison actual base footprint')
    if space:
        other_binding = authenticated(other_directory, 'report.json')
        other_status = other_binding['metadata']
        if other_binding['origin_m_xz'] != [-184305.0, 61455.0] or other_binding['spacing_m'] != 60.0 or other_binding['area_m2'] != 58982400.0:
            raise ValueError('comparison same spatial footprint')
    else:
        other_binding = authenticated(other_directory, 'binding.json')
        other_status = authenticated(other_directory, 'states.json')['metadata']
        other_geometry = authenticated(other_directory, 'geometry.json')
        if base_geometry != other_geometry:
            raise ValueError('comparison same original geometry metadata')
        for key, value in base_binding['budget'].items():
            if key in ('max_wall_s', 'max_bytes', 'max_face_evaluations', 'max_substeps'):
                continue
            if not tailwater and key in ('max_dt_s', 'inertial_cfl'):
                continue
            if other_binding['budget'][key] != value:
                raise ValueError('comparison fixed non-sensitivity budget')
        base_manifest = _i5_strict_json(_i5_Path(base_directory) / 'manifest.json')
        other_manifest = _i5_strict_json(_i5_Path(other_directory) / 'manifest.json')
        for directory, manifest in ((base_directory, base_manifest), (other_directory, other_manifest)):
            if _i5_file_sha256(_i5_Path(directory) / 'geometry.npz') != manifest['artifacts']['geometry.npz']:
                raise ValueError('comparison authenticated boundary geometry')
        base_arrays = _i5_read_arrays(_i5_Path(base_directory) / 'geometry.npz', _i5_GEOMETRY, expected_sha256=base_manifest['artifacts']['geometry.npz'])
        other_arrays = _i5_read_arrays(_i5_Path(other_directory) / 'geometry.npz', _i5_GEOMETRY, expected_sha256=other_manifest['artifacts']['geometry.npz'])
        for key in _i5_GEOMETRY.keys() - {'boundary_kind'}:
            if not _i5_np.array_equal(base_arrays[key], other_arrays[key]):
                raise ValueError('comparison same bed/shared faces/crests required')
        base_kinds, other_kinds = (base_arrays['boundary_kind'], other_arrays['boundary_kind'])
        expected = base_kinds.copy()
        if tailwater:
            expected[_i5_np.r_[256 + _i5_np.arange(252, 256), 768 + _i5_np.arange(252, 256)]] = 2
        if not _i5_np.array_equal(base_kinds, _i5_np.ones(1024, _i5_np.int64)) or not _i5_np.array_equal(other_kinds, expected):
            raise ValueError('comparison intended boundary difference only')
    for key in ('source_identity', 'height_source_identity', 'forcing_manifest_sha256'):
        if base_binding[key] != other_binding[key]:
            raise ValueError('comparison same source/forcing identity')
    if tailwater and (space or _i5_Path(other_directory).name != 'uniform_heavy_tailwater'):
        raise ValueError('explicit fixed tailwater case only')
    frames = []
    for index, time in enumerate(base['time_s']):
        matches = _i5_np.flatnonzero(_i5_np.abs(other['time_s'] - time) < 1e-07)
        if not len(matches):
            continue
        target = int(matches[0])
        left, right = (base['depth_m'][index], other['depth_m'][target])
        if space:
            left = left.reshape(128, 2, 128, 2).sum(axis=(1, 3)) / 4.0
        delta = right - left
        area = 3600.0 if space else 900.0
        frame = {'time_s': float(time), 'max_abs_depth_difference_m': float(abs(delta).max()), 'RMS_depth_difference_m': float(_i5_np.sqrt(_i5_np.mean(delta ** 2))), 'volume_L1_difference_m3': float(abs(delta).sum() * area), 'storage_difference_m3': float(other['ledger'][target, 3] - base['ledger'][index, 3]), 'external_input_difference_m3': float(other['ledger'][target, 1] - base['ledger'][index, 1]), 'net_external_output_difference_m3': float(other['ledger'][target, 2] - other['ledger'][target, 1] - (base['ledger'][index, 2] - base['ledger'][index, 1]))}
        stored = float(base['ledger'][index, 3])
        frame['relative_volume_L1_to_base_storage'] = frame['volume_L1_difference_m3'] / stored if stored > 0 else None
        supplied = float(base['ledger'][index, 0])
        frame['relative_net_output_difference_to_supplied'] = frame['net_external_output_difference_m3'] / supplied if supplied > 0 else None
        if tailwater:
            affected = delta > 0.001
            wet_union = (left > 0.001) | (right > 0.001)
            labels, count = _i5_label(wet_union)
            seeds = _i5_np.zeros((256, 256), bool)
            seeds[252:, -1] = True
            seeds[-1, 252:] = True
            connected_labels = _i5_np.unique(labels[seeds & wet_union])
            connected = affected & _i5_np.isin(labels, connected_labels[connected_labels > 0])
            rows, columns = _i5_np.nonzero(connected)
            distances = _i5_np.sqrt((255 - rows) ** 2 + (255 - columns) ** 2) * 30.0
            frame['backwater'] = {'positive_depth_difference_threshold_m': 0.001, 'affected_cells': int(affected.sum()), 'D4_wet_connected_to_tailwater_cells': int(connected.sum()), 'maximum_SE_corner_distance_m': float(distances.max(initial=0)), 'max_positive_stage_change_m': float(delta.max(initial=0)), 'scope': 'D4_saved_wet_mask_connectivity_and_euclidean_distance_not_dynamic_travel_time'}
        frames.append(frame)
    if not any((frame['time_s'] > 0 for frame in frames)):
        raise ValueError('comparison requires nonzero common saved time')
    if not _i5_np.allclose([base['ledger'][index, 0] for index, time in enumerate(base['time_s']) if any((abs(frame['time_s'] - time) < 1e-07 for frame in frames))], [other['ledger'][_i5_np.argmin(abs(other['time_s'] - frame['time_s'])), 0] for frame in frames], rtol=2e-11, atol=1e-06):
        raise ValueError('comparison identical supplied volume at matched times')
    events = {str(event): {'requested_time_s': event, 'actual_saved_time_s': min((frame['time_s'] for frame in frames), key=lambda time: abs(time - event)) if frames else None, 'exact_saved': bool(any((abs(frame['time_s'] - event) < 1e-07 for frame in frames)))} for event in (43200.0, 86400.0, 259200.0)}
    report = {'base_manifest_sha256': base_sha, 'other_manifest_sha256': other_sha, 'base_run': {key: base_status[key] for key in ('status', 'requested_time_s', 'committed_time_s', 'failure', 'wall_s', 'substeps', 'face_evaluations')}, 'other_run': {key: other_status[key] for key in ('status', 'requested_time_s', 'committed_time_s', 'failure', 'wall_s', 'substeps', 'face_evaluations')}, 'frames': frames, 'events': events, 'alignment': 'exact_common_saved_times_no_state_interpolation', 'scope': 'differences_not_automatic_convergence_or_backwater_physical_certification', 'tailwater_comparison': tailwater, 'common_final_time_s': frames[-1]['time_s'], 'resource_budgets_may_differ': True, 'both_saved_full_72h': bool(abs(base['time_s'][-1] - 259200.0) < 1e-07 and abs(other['time_s'][-1] - 259200.0) < 1e-07)}
    if space:
        report['spatial'] = {'comparison': '30m_depth_2x2_volume_average_vs_60m_saved_depth_not_same_bed_stage', 'potential_fill_capacity_30m_m3': 6783370.751953, 'potential_fill_capacity_60m_m3': 15616526.879883, 'capacity_source': 'coordinator_independent_D4_diagnostic_only_for_source_81d12179658ed02fefc94883cea1ce32888ff36199952d2bd88f68eb576f8cb2_and_space60_102320', 'bed_scope': 'block_mean_changes_topology_not_pure_convergence'}
    return report

def _entry_verify_regional_hydraulics_compare():
    from terrain_pipeline.common_infra import publish_bytes as _i5_publish_bytes
    parser = _i5_argparse.ArgumentParser()
    parser.add_argument('base', type=_i5_Path)
    parser.add_argument('other', type=_i5_Path)
    parser.add_argument('output', type=_i5_Path)
    parser.add_argument('--space', action='store_true')
    parser.add_argument('--tailwater', action='store_true')
    parser.add_argument('--base-sha256', required=True)
    parser.add_argument('--other-sha256', required=True)
    args = parser.parse_args()
    report = compare(args.base, args.other, base_sha256=args.base_sha256, other_sha256=args.other_sha256, space=args.space, tailwater=args.tailwater)
    _i5_publish_bytes(args.output, _i5_json.dumps(report, indent=2).encode('ascii'))
    print('COMPARISON', args.output)
_i6_sys.path.insert(0, str(ROOT))

def export_case(directory):
    from terrain_pipeline.common_infra import file_sha256 as _i6_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i6_publish_bytes
    from terrain_pipeline.regional_surface_source import load_source as _i6_load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as _i6_load_forcing
    from terrain_pipeline.regional_hydraulics_archive import load_case as _i6_load_case
    from terrain_pipeline.regional_hydraulics_mesh import water_columns as _i6_water_columns
    from terrain_pipeline.regional_hydraulics_mesh import validate_water_columns as _i6_validate_water_columns
    directory = _i6_Path(directory).resolve()
    binding = _i6_json.loads((directory / 'binding.json').read_text(encoding='utf-8'))
    source = _i6_load_source(ROOT / 'verification/regional-source/run-20261001T095258008789Z/source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
    forcing = _i6_load_forcing(ROOT / binding['forcing_directory'], expected_manifest_sha256=binding['forcing_manifest_sha256'], source_identity=source['identity_sha256'])
    case_sha = _i6_file_sha256(directory / 'manifest.json')
    result = _i6_load_case(directory, expected_manifest_sha256=case_sha, trusted_height=source['arrays']['height_m'], source_identity=source['identity_sha256'], forcing_volumes=forcing['runoff_volume_m3'])
    forcing['runoff_volume_m3']._mmap.close()
    output = ROOT / 'verification/regional-hydraulics' / ('mesh-' + directory.name + '-' + _i6_datetime.now(_i6_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    states, geometry = (result['states'], result['geometry'])
    indices = sorted(set([0, int(_i6_np.argmax(states['ledger'][:, 3])), len(states['time_s']) - 1] + [int(_i6_np.argmin(abs(states['time_s'] - hour * 3600.0))) for hour in (6, 12, 18, 24, 48, 72)]))
    index = {'schema': 'regional-saved-B-mesh-index-v1', 'source_identity': source['identity_sha256'], 'status': 'B_static_validated_saved_mesh', 'source_case_manifest_sha256': case_sha, 'source_case_directory': str(directory.relative_to(ROOT)), 'snapshots': [], 'display_threshold_m': 0.001, 'sampling': 'initial_storage_peak_nearest_6_12_18_24_48_72h_final_keyframes_not_all_substeps', 'representation': 'independent_flat_cell_top_quads_not_continuous_shared_stage_surface'}
    consumer_cases = []
    consumer_frames = []
    full_frames = []
    for state_index in indices:
        depth = states['depth_m'][state_index]
        packet = _i6_water_columns(source['arrays']['height_m'], depth, spacing_m=30.0, origin_m_xz=source['metadata']['origin_m_xz'], source_identity=source['identity_sha256'], time_s=states['time_s'][state_index])
        proof = _i6_validate_water_columns(packet, trusted_height=source['arrays']['height_m'], saved_depth=depth, source_identity=source['identity_sha256'], trusted_spacing_m=30.0, trusted_origin_m_xz=source['metadata']['origin_m_xz'])
        name = 'physical-water-%04d' % state_index
        with (output / (name + '.npz')).open('xb') as stream:
            _i6_np.savez_compressed(stream, **packet['arrays'])
        _i6_publish_bytes(output / (name + '.json'), _i6_json.dumps({**packet['metadata'], 'proof': proof}, indent=2).encode('ascii'))
        ids = packet['arrays']['cell_id']
        shown = depth.ravel()[ids] >= 0.001
        tops = packet['arrays']['vertices_xyz_m'].reshape(-1, 8, 3)[shown, 4:]
        count = len(tops)
        triangles = (_i6_np.array([[0, 2, 1], [0, 3, 2]])[None] + _i6_np.arange(count)[:, None, None] * 4).reshape(-1, 3)
        display = {'source_identity': source['identity_sha256'], 'time_s': float(states['time_s'][state_index]), 'vertices_xyz_m': tops.reshape(-1, 3).tolist(), 'triangles': triangles.tolist(), 'display_cell_ids': ids[shown].tolist(), 'display_threshold_m': 0.001, 'omitted_wet_cells': int((~shown).sum()), 'omitted_volume_m3': float(packet['arrays']['cell_volume_m3'][~shown].sum()), 'solver_volume_m3': proof['volume_m3'], 'display_volume_m3': float(packet['arrays']['cell_volume_m3'][shown].sum()), 'representation': index['representation'], 'physical_archive': name + '.npz'}
        payload = _i6_json.dumps(display, separators=(',', ':'), allow_nan=False).encode('ascii')
        if len(payload) > 16 * 1024 ** 2 or count * 4 > 300000 or count * 2 > 400000:
            index.setdefault('display_refusals', []).append({'state_index': state_index, 'bytes': len(payload), 'reason': 'A_consumer_budget'})
        else:
            filename = 'saved-water-%04d.json' % state_index
            _i6_publish_bytes(output / filename, payload)
            index['snapshots'].append({'time_s': display['time_s'], 'path': filename, 'sha256': _i6_file_sha256(output / filename), 'omitted_volume_m3': display['omitted_volume_m3'], 'solver_volume_m3': display['solver_volume_m3']})
            consumer_frames.append({'time_s': display['time_s'], 'path': filename, 'sha256': _i6_file_sha256(output / filename), 'volume_m3': proof['volume_m3'], 'max_depth_m': float(depth.max())})
        all_tops = packet['arrays']['vertices_xyz_m'].reshape(-1, 8, 3)[:, 4:]
        all_count = len(all_tops)
        full_consumer = {'source_identity': source['identity_sha256'], 'vertices_xyz_m': all_tops.reshape(-1, 3).tolist(), 'triangles': (_i6_np.array([[0, 2, 1], [0, 3, 2]])[None] + _i6_np.arange(all_count)[:, None, None] * 4).reshape(-1, 3).tolist(), 'time_s': float(states['time_s'][state_index]), 'display_cell_ids': ids.tolist(), 'display_threshold_m': 0.0, 'omitted_wet_cells': 0, 'omitted_volume_m3': 0.0, 'solver_volume_m3': proof['volume_m3'], 'display_volume_m3': proof['volume_m3'], 'representation': index['representation'], 'physical_archive': name + '.npz'}
        full_payload = _i6_json.dumps(full_consumer, separators=(',', ':'), allow_nan=False).encode('ascii')
        if len(full_payload) <= 16 * 1024 ** 2:
            full_filename = 'consumer-full-water-%04d.json' % state_index
            _i6_publish_bytes(output / full_filename, full_payload)
            full_frames.append({'time_s': float(states['time_s'][state_index]), 'path': full_filename, 'sha256': _i6_file_sha256(output / full_filename), 'volume_m3': proof['volume_m3'], 'max_depth_m': float(depth.max())})
        else:
            index.setdefault('representation_export_failures', []).append({'state_index': state_index, 'threshold_m': 0.0, 'bytes': len(full_payload), 'reason': 'A_16MiB_JSON_budget'})
        del all_tops, full_consumer, full_payload
        del packet, display, payload, tops
    meta = result['metadata']['metadata']
    for label, frames in (('display_filtered_1mm', consumer_frames), ('full_top_threshold_0', full_frames)):
        if len(frames) != len(indices):
            continue
        consumer_cases.append({'id': directory.name + '_' + label, 'model': meta['schema'] + '; keyframes; ' + label, 'requested_time_s': meta['requested_time_s'], 'committed_time_s': meta['committed_time_s'], 'status': meta['status'], 'failure': None if meta['failure'] is None else str(meta['failure']), 'B_validation': 'cold-validation.json; exact closed-column physical NPZ; display-filter statistics saved-mesh-index.json; keyframes only', 'snapshots': frames})
    _i6_publish_bytes(output / 'consumer-cases-index.json', _i6_json.dumps({'schema': 'regional-saved-B-mesh-cases-v1', 'source_identity': source['identity_sha256'], 'fixture_only': False, 'cases': consumer_cases}, indent=2).encode('ascii'))
    _i6_publish_bytes(output / 'saved-mesh-index.json', _i6_json.dumps(index, indent=2).encode('ascii'))
    _i6_publish_bytes(output / 'cold-validation.json', _i6_json.dumps({key: value for key, value in result.items() if key not in ('geometry', 'states')}, indent=2).encode('ascii'))
    hashes = {path.name: _i6_file_sha256(path) for path in output.iterdir()}
    _i6_publish_bytes(output / 'manifest.json', _i6_json.dumps({'artifacts': hashes, 'case_manifest_sha256': case_sha, 'exporter_sha256': _i6_file_sha256(_i6_Path(__file__)), 'mesh_module_sha256': _i6_file_sha256(ROOT / 'terrain_pipeline/regional_hydraulics_mesh.py'), 'archive_module_sha256': _i6_file_sha256(ROOT / 'terrain_pipeline/regional_hydraulics_archive.py')}, indent=2).encode('ascii'))
    print('MESH_OUTPUT', output, flush=True)

def _entry_verify_regional_hydraulics_export():
    export_case(_i6_sys.argv[1])
_i7_sys.path.insert(0, str(ROOT))

def _run_verify_regional_hydraulics_failure():
    from terrain_pipeline.regional_surface_source import load_source as _i7_load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as _i7_load_forcing
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i7_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i7_prepare_surface_geometry
    from terrain_pipeline.surface_hydraulics import advance_inertial_surface as _i7_advance_inertial_surface
    from terrain_pipeline.regional_hydraulics_archive import load_case as _i7_load_case
    from terrain_pipeline.common_infra import publish_bytes as _i7_publish_bytes
    from terrain_pipeline.common_infra import file_sha256 as _i7_file_sha256
    source = _i7_load_source(SOURCE / 'source.npz', expected_sha256=SOURCE_SHA)
    handoff = _i7_json.loads((FORCING / 'handoff-manifest.json').read_text(encoding='utf-8'))
    sha = handoff['cases']['uniform_heavy']['manifest_sha256']
    loaded = _i7_load_forcing(FORCING / 'uniform_heavy', expected_manifest_sha256=sha, source_identity=source['identity_sha256'])
    height = source['arrays']['height_m']
    output = ROOT / 'verification/regional-hydraulics' / ('failure-' + _i7_datetime.now(_i7_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    cases = [('depth_zero_commit', _i7_replace(_i7_SurfaceBudget(), max_depth_m=1e-12)), ('work_two_commit', _i7_replace(_i7_SurfaceBudget(), max_substeps=2))]
    declaration = {'source_identity': source['identity_sha256'], 'height_source_identity': source['metadata']['height_source_identity'], 'source_sha256': SOURCE_SHA, 'forcing_manifest_sha256': sha, 'cases': {name: vars(budget) for name, budget in cases}, 'solver_sha256': _i7_file_sha256(ROOT / 'terrain_pipeline/surface_hydraulics.py'), 'scope': 'explicit_resource_and_depth_failure_real_full_grid_not_main_budget_changes'}
    _i7_publish_bytes(output / 'predeclared.json', _i7_json.dumps(declaration, indent=2).encode('ascii'))
    for name, budget in cases:
        directory = output / name
        directory.mkdir()
        geometry = _i7_prepare_surface_geometry(height, spacing_m=30.0, origin_m_xz=source['metadata']['origin_m_xz'], source_identity=source['identity_sha256'], boundary_kind=_i7_np.ones(1024, _i7_np.int64))
        write_packet(directory, 'geometry', {**geometry['arrays'], **geometry['metadata']})
        _i7_publish_bytes(directory / 'binding.json', _i7_json.dumps({'source_identity': source['identity_sha256'], 'height_source_identity': source['metadata']['height_source_identity'], 'forcing_manifest_sha256': sha, 'forcing_directory': str((FORCING / 'uniform_heavy').relative_to(ROOT)), 'budget': vars(budget)}, indent=2).encode('ascii'))
        result = _i7_advance_inertial_surface(geometry, initial_depth_m=_i7_np.zeros(height.shape), forcing_interval_s=900.0, intervals=288, forcing_provider=lambda index: loaded['runoff_volume_m3'][index].astype(_i7_np.float64) / 900.0, boundary_stage_provider=lambda index: geometry['arrays']['boundary_crest_m'].copy(), source_identity=source['identity_sha256'], forcing_identity=sha, budget=budget, interval_observer=lambda packet: write_packet(directory, 'interval-%03d' % packet['interval'], packet), momentum_observer=lambda packet: write_packet(directory, 'momentum-%03d' % packet['interval'], packet))
        write_packet(directory, 'states', {**result['arrays'], 'metadata': result['metadata'], 'diagnostics': result['diagnostics']})
        _i7_publish_bytes(directory / 'manifest.json', _i7_json.dumps({'artifacts': {path.name: _i7_file_sha256(path) for path in directory.iterdir()}}, indent=2).encode('ascii'))
        verified = _i7_load_case(directory, expected_manifest_sha256=_i7_file_sha256(directory / 'manifest.json'), trusted_height=height, source_identity=source['identity_sha256'], forcing_volumes=loaded['runoff_volume_m3'])
        proof = {key: value for key, value in verified.items() if key not in ('geometry', 'states')}
        _i7_publish_bytes(output / (name + '-cold.json'), _i7_json.dumps(proof, indent=2).encode('ascii'))
        print('FAILURE_COLD', name, result['metadata']['committed_time_s'], result['metadata']['failure'], flush=True)
    loaded['runoff_volume_m3']._mmap.close()
    print('FAILURE_OUTPUT', output, flush=True)

def _entry_verify_regional_hydraulics_failure():
    _run_verify_regional_hydraulics_failure()
_i9_sys.path.insert(0, str(ROOT))

def check(directory, *, expected_manifest_sha256):
    from terrain_pipeline.common_infra import file_sha256 as _i9_file_sha256
    from terrain_pipeline.regional_hydraulics_archive import read_arrays as _i9_read_arrays
    from terrain_pipeline.regional_hydraulics_archive import strict_json as _i9_strict_json
    from terrain_pipeline.regional_hydraulics_mesh import validate_water_columns as _i9_validate_water_columns
    from terrain_pipeline.regional_surface_source import load_source as _i9_load_source
    directory = _i9_Path(directory)
    if _i9_file_sha256(directory / 'manifest.json') != expected_manifest_sha256:
        raise ValueError('external trusted mesh manifest')
    manifest = _i9_strict_json(directory / 'manifest.json')
    for name, digest in manifest['artifacts'].items():
        if _i9_Path(name).name != name or _i9_file_sha256(directory / name) != digest:
            raise ValueError('mesh authenticated artifact')
    source = _i9_load_source(ROOT / 'verification/regional-source/run-20261001T095258008789Z/source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
    if 'saved-mesh-index.json' not in manifest['artifacts'] or not (directory / 'saved-mesh-index.json').is_file():
        raise ValueError('saved mesh index is required')
    index = _i9_strict_json(directory / 'saved-mesh-index.json')
    if index['source_identity'] != source['identity_sha256'] or not isinstance(index['snapshots'], list) or (not index['snapshots']):
        raise ValueError('nonempty authenticated mesh keyframe declaration required')
    declared_times = {float(item['time_s']): item for item in index['snapshots']}
    if len(declared_times) != len(index['snapshots']):
        raise ValueError('duplicate declared mesh keyframe')
    for item in index['snapshots']:
        if set(item) != {'time_s', 'path', 'sha256', 'omitted_volume_m3', 'solver_volume_m3'}:
            raise ValueError('exact declared mesh keyframe schema')
        path = item['path']
        if _i9_Path(path).name != path or path not in manifest['artifacts'] or _i9_file_sha256(directory / path) != item['sha256']:
            raise ValueError('declared mesh keyframe artifact binding')
    case = ROOT / index['source_case_directory']
    if _i9_file_sha256(case / 'manifest.json') != index['source_case_manifest_sha256'] or index['source_case_manifest_sha256'] != manifest['case_manifest_sha256']:
        raise ValueError('mesh source case binding')
    case_manifest = _i9_strict_json(case / 'manifest.json')
    with _i9_zipfile.ZipFile(case / 'states.npz') as archive:
        with archive.open('time_s.npy') as stream:
            version = _i9_np.lib.format.read_magic(stream)
            header = _i9_np.lib.format.read_array_header_1_0 if version == (1, 0) else _i9_np.lib.format.read_array_header_2_0
            shape, order, dtype = header(stream)
            if len(shape) != 1 or not 1 <= shape[0] <= 50 or order or (dtype != _i9_np.float64):
                raise ValueError('mesh source bounded saved state header')
            count = shape[0]
    states = _i9_read_arrays(case / 'states.npz', {'time_s': ((count,), 'float64'), 'depth_m': ((count, 256, 256), 'float64'), 'initial_depth_m': ((256, 256), 'float64'), 'ledger': ((count, 5), 'float64'), 'final_internal_q_m3_s': ((130560,), 'float64'), 'final_boundary_q_m3_s': ((1024,), 'float64')}, expected_sha256=case_manifest['artifacts']['states.npz'])
    times, depths = (states['time_s'], states['depth_m'])
    proofs = []
    for name, digest in manifest['artifacts'].items():
        if not name.startswith('physical-water-') or not name.endswith('.npz'):
            continue
        state_index = int(name.removeprefix('physical-water-').removesuffix('.npz'))
        depth = depths[state_index]
        wet = int((depth > 0).sum())
        packet = {'arrays': _i9_read_arrays(directory / name, {'vertices_xyz_m': ((wet * 8, 3), 'float64'), 'triangles': ((wet * 12, 3), 'int64'), 'cell_id': ((wet,), 'int64'), 'cell_volume_m3': ((wet,), 'float64')}, expected_sha256=digest), 'metadata': _i9_strict_json(directory / name.replace('.npz', '.json'))}
        if packet['metadata']['time_s'] != times[state_index]:
            raise ValueError('mesh saved physical time')
        proof = _i9_validate_water_columns(packet, trusted_height=source['arrays']['height_m'], saved_depth=depth, source_identity=source['identity_sha256'], trusted_spacing_m=30.0, trusted_origin_m_xz=source['metadata']['origin_m_xz'])
        proofs.append({'state_index': state_index, 'time_s': float(times[state_index]), **proof})
    if not proofs:
        raise ValueError('mesh index must contain at least one authenticated physical water archive')
    if not proofs:
        raise ValueError('physical water proof set cannot be empty')
    proof_times = {item['time_s'] for item in proofs}
    if proof_times != set(declared_times):
        raise ValueError('declared keyframes must all have physical-column proof')
    display_names = []
    for name in manifest['artifacts']:
        if not (name.startswith('saved-water-') or name.startswith('consumer-full-water-')) or not name.endswith('.json'):
            continue
        if (directory / name).stat().st_size > 16 * 1024 ** 2:
            raise ValueError('mesh display bounded JSON')
        display = _i9_json.loads((directory / name).read_text(encoding='utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite display')))
        display_names.append(name)
        physical_name = display['physical_archive']
        state_index = int(physical_name.removeprefix('physical-water-').removesuffix('.npz'))
        depth = depths[state_index]
        threshold = display['display_threshold_m']
        if threshold not in (0.0, 0.001) or display['source_identity'] != source['identity_sha256'] or display['time_s'] != times[state_index]:
            raise ValueError('mesh display identity/threshold/time')
        ids = _i9_np.flatnonzero((depth.ravel() > 0) & (depth.ravel() >= threshold))
        vertices = _i9_np.asarray(display['vertices_xyz_m'], _i9_np.float64).reshape(-1, 4, 3)
        triangles = _i9_np.asarray(display['triangles'], _i9_np.int64).reshape(-1, 3)
        if not _i9_np.array_equal(ids, display['display_cell_ids']) or vertices.shape != (len(ids), 4, 3) or (not _i9_np.array_equal(triangles, (_i9_np.array([[0, 2, 1], [0, 3, 2]])[None] + _i9_np.arange(len(ids))[:, None, None] * 4).reshape(-1, 3))):
            raise ValueError('mesh display support/topology')
        rows, columns = _i9_np.divmod(ids, 256)
        origin = source['metadata']['origin_m_xz']
        expected_x = origin[0] + columns[:, None] * 30 + _i9_np.array([-15.0, 15.0, 15.0, -15.0])
        expected_z = origin[1] + rows[:, None] * 30 + _i9_np.array([-15.0, -15.0, 15.0, 15.0])
        stage = (source['arrays']['height_m'] + depth).ravel()[ids]
        if not _i9_np.array_equal(vertices[:, :, 0], expected_x) or not _i9_np.array_equal(vertices[:, :, 2], expected_z) or (not _i9_np.array_equal(vertices[:, :, 1], _i9_np.repeat(stage[:, None], 4, axis=1))):
            raise ValueError('mesh display source coordinates/stage')
        shown = float(depth.ravel()[ids].sum() * 900.0)
        total = float(depth.sum() * 900.0)
        if not _i9_np.isclose(display['display_volume_m3'], shown, atol=1e-08, rtol=1e-12) or not _i9_np.isclose(display['solver_volume_m3'], total, atol=1e-08, rtol=1e-12) or (not _i9_np.isclose(display['omitted_volume_m3'], total - shown, atol=1e-08, rtol=1e-12)) or (display['omitted_wet_cells'] != int((depth > 0).sum()) - len(ids)):
            raise ValueError('mesh display filtering ledger')
    if set(display_names) != {item['path'] for item in index['snapshots']}:
        raise ValueError('declared display keyframes must be exactly covered')
    return {'manifest_sha256': expected_manifest_sha256, 'physical_states': proofs, 'scope': 'all_saved_column_source_geometry_volume_and_display_filter_correspondence'}

def _entry_verify_regional_hydraulics_mesh_load():
    from terrain_pipeline.common_infra import publish_bytes as _i9_publish_bytes
    directory = _i9_Path(_i9_sys.argv[1])
    result = check(directory, expected_manifest_sha256=_i9_sys.argv[2])
    _i9_publish_bytes(directory.parent / (directory.name + '-cold.json'), _i9_json.dumps(result, indent=2).encode('ascii'))
    print(_i9_json.dumps(result), flush=True)
_i10_sys.path.insert(0, str(ROOT))

def _run_verify_regional_hydraulics_profile():
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i10_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import limited_inertial_fluxes as _i10_limited_inertial_fluxes
    from terrain_pipeline.surface_hydraulics import _net_flux as _i10__net_flux
    from terrain_pipeline.common_infra import publish_bytes as _i10_publish_bytes
    from terrain_pipeline.common_infra import file_sha256 as _i10_file_sha256
    case = ROOT / 'verification/regional-hydraulics/full-20261001T110401380014Z/uniform_heavy_half_cfl'
    packets = sorted(case.glob('interval-*.npz'))
    path = packets[-1]
    with _i10_np.load(case / 'geometry.npz', allow_pickle=False) as archive:
        geometry = {'arrays': {key: archive[key] for key in archive.files}, 'metadata': _i10_json.loads((case / 'geometry.json').read_text())}
    with _i10_np.load(path, allow_pickle=False) as archive:
        packet = {key: archive[key] for key in archive.files}
    depth = packet['depth_before_m']
    forcing = packet['forcing_volume_m3'] / 900.0
    internal, boundary = (packet['internal_q_before_m3_s'], packet['boundary_q_before_m3_s'])
    tailwater = geometry['arrays']['boundary_crest_m']
    budget = _i10_SurfaceBudget()
    profile = _i10_cProfile.Profile()
    start = _i10_time.perf_counter()
    profile.enable()
    for index in range(200):
        updated_internal, updated_boundary, stats = _i10_limited_inertial_fluxes(geometry, depth, internal, boundary, tailwater, forcing, 0.5, budget)
        net = _i10__net_flux(geometry, updated_internal, updated_boundary)
        residual = 900 * (depth + 0.5 * (forcing + net) / 900 - depth) - 0.5 * (forcing + net)
    profile.disable()
    elapsed = _i10_time.perf_counter() - start
    stream = _i10_io.StringIO()
    _i10_pstats.Stats(profile, stream=stream).sort_stats('cumtime').print_stats(25)
    compression = {}
    for compressed in (False, True):
        buffer = _i10_io.BytesIO()
        start = _i10_time.perf_counter()
        (_i10_np.savez_compressed if compressed else _i10_np.savez)(buffer, **packet)
        compression[str(compressed)] = {'wall_s': _i10_time.perf_counter() - start, 'bytes': buffer.tell()}
    output = ROOT / 'verification/regional-hydraulics' / ('profile-' + _i10_datetime.now(_i10_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir()
    report = {'input_packet': str(path.relative_to(ROOT)), 'input_sha256': _i10_file_sha256(path), 'iterations': 200, 'wall_s': elapsed, 'compression': compression, 'profile': stream.getvalue(), 'state_max_depth_m': float(depth.max())}
    _i10_publish_bytes(output / 'report.json', _i10_json.dumps(report, indent=2).encode('ascii'))
    print(_i10_json.dumps(report), flush=True)

def _entry_verify_regional_hydraulics_profile():
    _run_verify_regional_hydraulics_profile()
_i11_sys.path.insert(0, str(ROOT))

def aggregate(array):
    return array.reshape(128, 2, 128, 2).sum(axis=(1, 3))

def _run_verify_regional_hydraulics_space():
    from terrain_pipeline.common_infra import file_sha256 as _i11_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _i11_publish_bytes
    from terrain_pipeline.regional_surface_source import load_source as _i11_load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as _i11_load_forcing
    from terrain_pipeline.surface_hydraulics import SurfaceBudget as _i11_SurfaceBudget
    from terrain_pipeline.surface_hydraulics import prepare_surface_geometry as _i11_prepare_surface_geometry
    from terrain_pipeline.surface_hydraulics import advance_inertial_surface as _i11_advance_inertial_surface
    source = _i11_load_source(ROOT / 'verification/regional-source/run-20261001T095258008789Z/source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
    forcing_sha = '699a34ee51a68d98aa99a1c63a0cc9435845a2fb315a9e51b0f9343b3a839bbc'
    loaded = _i11_load_forcing(ROOT / 'verification/regional-forcing/run-20261001T095608600719Z/uniform_heavy', expected_manifest_sha256=forcing_sha, source_identity=source['identity_sha256'])
    original = source['arrays']['height_m']
    bed = aggregate(original) / 4.0
    origin = _i11_np.asarray(source['metadata']['origin_m_xz']) + 15.0
    identity = source['identity_sha256'] + ':same-footprint-60m-block-mean-v1'
    geometry = _i11_prepare_surface_geometry(bed, spacing_m=60.0, origin_m_xz=origin, source_identity=identity, boundary_kind=_i11_np.ones(512, _i11_np.int64))
    output = ROOT / 'verification/regional-hydraulics' / ('space60-' + _i11_datetime.now(_i11_timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    budget = _i11_SurfaceBudget()
    difference = _i11_np.repeat(_i11_np.repeat(bed, 2, axis=0), 2, axis=1) - original
    paths = (_i11_Path(__file__), ROOT / 'terrain_pipeline/surface_hydraulics.py')
    declaration = {'source_identity': source['identity_sha256'], 'derived_identity': identity, 'height_source_identity': source['metadata']['height_source_identity'], 'forcing_manifest_sha256': forcing_sha, 'shape': [128, 128], 'spacing_m': 60.0, 'origin_m_xz': origin.tolist(), 'area_m2': 58982400.0, 'bed_rule': '2x2_mean_changes_depressions_not_pure_numerical_convergence', 'forcing_rule': '2x2_sum_same_interval_volume', 'bed_max_abs_change_m': float(_i11_np.abs(difference).max()), 'bed_mean_abs_change_m': float(_i11_np.abs(difference).mean()), 'budget': vars(budget), 'duration_s': 259200.0, 'source_hashes': {str(path.relative_to(ROOT)): _i11_file_sha256(path) for path in paths}}
    _i11_publish_bytes(output / 'predeclared.json', _i11_json.dumps(declaration, indent=2).encode('ascii'))

    def observe(packet):
        if packet['interval'] % 24 == 0:
            print('SPACE60', packet['interval'], float(packet['depth_after_m'].max()), flush=True)
    result = _i11_advance_inertial_surface(geometry, initial_depth_m=_i11_np.zeros((128, 128)), forcing_interval_s=900.0, intervals=288, forcing_provider=lambda index: aggregate(loaded['runoff_volume_m3'][index]) / 900.0, boundary_stage_provider=lambda index: _i11_np.zeros(512), source_identity=identity, forcing_identity=forcing_sha, budget=budget, interval_observer=observe)
    with (output / 'states.npz').open('xb') as stream:
        _i11_np.savez_compressed(stream, **result['arrays'], H0_m=bed)
    declaration['metadata'] = result['metadata']
    declaration['diagnostics'] = result['diagnostics']
    declaration['source_unchanged'] = all((_i11_file_sha256(ROOT / key) == value for key, value in declaration['source_hashes'].items()))
    loaded['runoff_volume_m3']._mmap.close()
    _i11_publish_bytes(output / 'report.json', _i11_json.dumps(declaration, indent=2).encode('ascii'))
    _i11_publish_bytes(output / 'manifest.json', _i11_json.dumps({'artifacts': {path.name: _i11_file_sha256(path) for path in output.iterdir()}}, indent=2).encode('ascii'))
    print('SPACE60_DONE', output, flush=True)

def _entry_verify_regional_hydraulics_space():
    _run_verify_regional_hydraulics_space()
_i12_sys.path.insert(0, str(ROOT))

def validate(directory, expected_manifest_sha256):
    from terrain_pipeline.common_infra import file_sha256 as _i12_file_sha256
    from terrain_pipeline.regional_hydraulics_archive import read_arrays as _i12_read_arrays
    from terrain_pipeline.regional_hydraulics_archive import strict_json as _i12_strict_json
    from terrain_pipeline.regional_surface_source import load_source as _i12_load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as _i12_load_forcing
    directory = _i12_Path(directory)
    if _i12_file_sha256(directory / 'manifest.json') != expected_manifest_sha256:
        raise ValueError('external space manifest SHA')
    manifest = _i12_strict_json(directory / 'manifest.json')
    for name, digest in manifest['artifacts'].items():
        if _i12_Path(name).name != name or _i12_file_sha256(directory / name) != digest:
            raise ValueError('space artifacts authentic basenames')
    report = _i12_strict_json(directory / 'report.json')
    source = _i12_load_source(ROOT / 'verification/regional-source/run-20261001T095258008789Z/source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
    forcing = _i12_load_forcing(ROOT / 'verification/regional-forcing/run-20261001T095608600719Z/uniform_heavy', expected_manifest_sha256='699a34ee51a68d98aa99a1c63a0cc9435845a2fb315a9e51b0f9343b3a839bbc', source_identity=source['identity_sha256'])
    if report['source_identity'] != source['identity_sha256'] or report['height_source_identity'] != source['metadata']['height_source_identity'] or report['shape'] != [128, 128] or (report['spacing_m'] != 60.0) or (report['origin_m_xz'] != [-184305.0, 61455.0]) or (report['area_m2'] != 58982400.0):
        raise ValueError('same source/footprint identity')
    with _i12_zipfile.ZipFile(directory / 'states.npz') as archive:
        with archive.open('time_s.npy') as stream:
            version = _i12_np.lib.format.read_magic(stream)
            header = _i12_np.lib.format.read_array_header_1_0 if version == (1, 0) else _i12_np.lib.format.read_array_header_2_0
            shape, order, dtype = header(stream)
            if len(shape) != 1 or not 1 <= shape[0] <= 50 or order or (dtype != _i12_np.float64):
                raise ValueError('space bounded time header')
            count = shape[0]
    arrays = _i12_read_arrays(directory / 'states.npz', {'time_s': ((count,), 'float64'), 'depth_m': ((count, 128, 128), 'float64'), 'initial_depth_m': ((128, 128), 'float64'), 'ledger': ((count, 5), 'float64'), 'final_internal_q_m3_s': ((32512,), 'float64'), 'final_boundary_q_m3_s': ((512,), 'float64'), 'H0_m': ((128, 128), 'float64')}, expected_sha256=manifest['artifacts']['states.npz'])
    expected_bed = source['arrays']['height_m'].reshape(128, 2, 128, 2).mean(axis=(1, 3))
    if not _i12_np.allclose(arrays['H0_m'], expected_bed, atol=1e-12, rtol=0):
        raise ValueError('same-source block bed mean')
    times, depths, ledger = (arrays['time_s'], arrays['depth_m'], arrays['ledger'])
    meta = report['metadata']
    if times[0] != 0 or abs(times[-1] - meta['committed_time_s']) > 1e-07 or (_i12_np.diff(times) <= 0).any() or (depths < 0).any() or (depths > 20).any() or _i12_np.any(depths[0] != 0):
        raise ValueError('space physical snapshot states')
    if not _i12_np.array_equal(arrays['initial_depth_m'], depths[0]):
        raise ValueError('space initial identity')
    if meta['status'] == 'completed':
        if meta['failure'] is not None or abs(meta['committed_time_s'] - 259200.0) > 1e-07:
            raise ValueError('space completed status')
    elif meta['status'] == 'refused':
        if not isinstance(meta['failure'], dict) or not meta['committed_time_s'] < 259200.0:
            raise ValueError('space refused prefix')
    else:
        raise ValueError('space status')
    expected_input = []
    rates = forcing['runoff_volume_m3'].sum(axis=(1, 2)) / 900.0
    prefix = _i12_np.r_[0.0, _i12_np.cumsum(rates * 900.0)]
    for time in times:
        index = min(int(time // 900), len(rates))
        expected_input.append(prefix[index] + (time - index * 900.0) * rates[index] if index < len(rates) else prefix[-1])
    volume = depths.sum(axis=(1, 2)) * 3600.0
    residual = volume - expected_input + ledger[:, 2] - ledger[:, 1]
    if not _i12_np.allclose(ledger[:, 0], expected_input, atol=1e-06, rtol=2e-11) or not _i12_np.allclose(ledger[:, 3], volume, atol=1e-07, rtol=1e-12) or (not _i12_np.allclose(ledger[:, 4], residual, atol=1e-06, rtol=1e-12)) or (abs(residual) > 1e-05 + _i12_np.asarray(expected_input) * 2e-11).any():
        raise ValueError('space saved forcing/storage ledger')
    for key, value in (('final_volume_m3', volume[-1]), ('supplied_m3', ledger[-1, 0]), ('boundary_output_m3', ledger[-1, 2]), ('boundary_input_m3', ledger[-1, 1])):
        if not _i12_np.isclose(meta[key], value, atol=1e-06, rtol=1e-12):
            raise ValueError('space metadata totals')
    forcing['runoff_volume_m3']._mmap.close()
    return {'manifest_sha256': expected_manifest_sha256, 'status': meta['status'], 'committed_time_s': meta['committed_time_s'], 'max_snapshot_mass_residual_m3': float(abs(residual).max()), 'scope': 'source_footprint_saved_snapshot_volume_forcing_ledger_no_interval_or_momentum_certificates'}

def _entry_verify_regional_hydraulics_space_load():
    from terrain_pipeline.common_infra import publish_bytes as _i12_publish_bytes
    directory = _i12_Path(_i12_sys.argv[1])
    result = validate(directory, _i12_sys.argv[2])
    _i12_publish_bytes(directory.parent / (directory.name + '-cold-check.json'), _i12_json.dumps(result, indent=2).encode('ascii'))
    print(_i12_json.dumps(result), flush=True)
_i13_sys.path.insert(0, str(ROOT))

def summarize(directory):
    from terrain_pipeline.common_infra import file_sha256 as _i13_file_sha256
    from terrain_pipeline.regional_surface_source import load_source as _i13_load_source
    from terrain_pipeline.climate_forcing import regional_load_forcing as _i13_load_forcing
    from terrain_pipeline.regional_hydraulics_archive import load_case as _i13_load_case
    from terrain_pipeline.regional_hydraulics_archive import strict_json as _i13_strict_json
    directory = _i13_Path(directory).resolve()
    source = _i13_load_source(ROOT / 'verification/regional-source/run-20261001T095258008789Z/source.npz', expected_sha256='ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da')
    binding = _i13_strict_json(directory / 'binding.json')
    forcing = _i13_load_forcing(ROOT / binding['forcing_directory'], expected_manifest_sha256=binding['forcing_manifest_sha256'], source_identity=source['identity_sha256'])
    manifest_sha = _i13_file_sha256(directory / 'manifest.json')
    case = _i13_load_case(directory, expected_manifest_sha256=manifest_sha, trusted_height=source['arrays']['height_m'], source_identity=source['identity_sha256'], forcing_volumes=forcing['runoff_volume_m3'])
    arrays, states = (source['arrays'], case['states'])
    lake, channel = (arrays['diagnostic_lake_id'] > 0, arrays['channel_mask'])
    masks = {'potential_lake': lake, 'non_lake': ~lake, 'static_channel': channel, 'non_channel': ~channel, 'lake_channel': lake & channel, 'lake_non_channel': lake & ~channel, 'non_lake_channel': ~lake & channel, 'non_lake_non_channel': ~lake & ~channel}
    frames = []
    previous_time = previous_out = previous_in = 0.0
    for index, depth in enumerate(states['depth_m']):
        time = float(states['time_s'][index])
        duration = time - previous_time
        out, entered = (states['ledger'][index, 2], states['ledger'][index, 1])
        frames.append({'time_s': time, 'total_volume_m3': float(depth.sum() * 900.0), 'preceding_saved_interval_external_outflow_mean_m3_s': float((out - previous_out) / duration) if duration else None, 'preceding_saved_interval_external_inflow_mean_m3_s': float((entered - previous_in) / duration) if duration else None, 'partitions': {name: {'volume_m3': float(depth[mask].sum() * 900.0), 'positive_wet_area_m2': int((depth[mask] > 0).sum()) * 900, 'wet_area_at_least_1mm_m2': int((depth[mask] >= 0.001).sum()) * 900} for name, mask in masks.items()}})
        previous_time, previous_out, previous_in = (time, out, entered)
    left, right = (case['geometry']['arrays']['face_left'], case['geometry']['arrays']['face_right'])
    receiver = arrays['receiver'].ravel()
    direction = _i13_np.where(receiver[left] == right, 1.0, _i13_np.where(receiver[right] == left, -1.0, 0.0))
    opposed_volume = _i13_np.zeros(len(left))
    opposed_count = 0
    manifest = _i13_strict_json(directory / 'manifest.json')
    for name in sorted(manifest['artifacts']):
        if not name.startswith('interval-') or not name.endswith('.npz'):
            continue
        with _i13_np.load(directory / name, allow_pickle=False) as archive:
            transfer = archive['internal_transfer_m3']
        opposed = (direction != 0) & (transfer * direction < -1e-10)
        opposed_count += int(opposed.sum())
        opposed_volume[opposed] += _i13_np.abs(transfer[opposed])
    ledger = forcing['metadata']['ledger']
    committed = case['metadata']['metadata']['committed_time_s']
    intervals = int(committed // 900.0)
    fraction = (committed - intervals * 900.0) / 900.0

    def integral(key):
        values = _i13_np.asarray(ledger[key])
        return float(values[:intervals].sum() + (values[intervals] * fraction if intervals < len(values) else 0.0))
    initial_soil = float(forcing['initial_states_mm'].sum() * 0.9)
    if abs(committed - 259200.0) < 1e-07:
        final_soil = float(forcing['final_states_mm'].sum() * 0.9)
        soil_scope = 'saved_exact_final_soil_fast_slow_states'
    else:
        storage = _i13_np.asarray(forcing['metadata']['total_soil_fast_slow_storage_m3'])
        final_soil = float(storage[intervals] + fraction * (storage[intervals + 1] - storage[intervals]))
        soil_scope = 'interval_ledger_linear_interpolation_not_nonlinear_intermediate_soil_state'
    surface_meta = case['metadata']['metadata']
    joint = final_soil - initial_soil + surface_meta['final_volume_m3'] - surface_meta['initial_volume_m3'] - integral('rain_m3') + integral('et_m3') - surface_meta['boundary_input_m3'] + surface_meta['boundary_output_m3']
    report = {'case_directory': str(directory.relative_to(ROOT)), 'case_manifest_sha256': manifest_sha, 'forcing_manifest_sha256': binding['forcing_manifest_sha256'], 'status': surface_meta['status'], 'requested_time_s': surface_meta['requested_time_s'], 'committed_time_s': surface_meta['committed_time_s'], 'failure': surface_meta['failure'], 'source_identity': source['identity_sha256'], 'source_height_identity': source['metadata']['height_source_identity'], 'frames': frames, 'partition_scope': 'lake_channel_pairs_overlap_use_four_intersections_for_partition_sum', 'recession_scope': 'outlet_rate_and_each_partition_storage_separate_no_global_recession_claim_from_rain_stopping', 'non_DAG': {'opposed_interval_face_occurrences': opposed_count, 'unique_opposed_receiver_faces': int((opposed_volume > 0).sum()), 'sum_opposed_interval_net_transfer_m3': float(opposed_volume.sum()), 'scope': 'interval_net_signed_transfer_not_substep_gross_backflow_or_unique_river_segments'}, 'rain_soil_surface': {'rain_m3': integral('rain_m3'), 'ET_m3': integral('et_m3'), 'surface_runoff_m3': integral('runoff_m3'), 'soil_fast_slow_storage_change_m3': integral('storage_change_m3'), 'forcing_balance_residual_m3': integral('residual_m3'), 'initial_soil_fast_slow_m3': initial_soil, 'final_soil_fast_slow_m3': final_soil, 'soil_final_scope': soil_scope, 'initial_surface_m3': surface_meta['initial_volume_m3'], 'final_surface_m3': surface_meta['final_volume_m3'], 'external_input_m3': surface_meta['boundary_input_m3'], 'external_output_m3': surface_meta['boundary_output_m3'], 'combined_rain_soil_surface_residual_m3': joint}, 'geometry_scope': '30m_flat_cells_no_subgrid_cross_sections_no_dynamic_channel_graph_certification', 'cold_evidence': {key: value for key, value in case.items() if key not in ('geometry', 'states')}}
    forcing['runoff_volume_m3']._mmap.close()
    return report

def _entry_verify_regional_hydraulics_summary():
    from terrain_pipeline.common_infra import publish_bytes as _i13_publish_bytes
    directory = _i13_Path(_i13_sys.argv[1])
    report = summarize(directory)
    destination = directory.parent / (directory.name + '-summary.json')
    _i13_publish_bytes(destination, _i13_json.dumps(report, indent=2).encode('ascii'))
    print('SUMMARY', destination, flush=True)

def main(argv=None):
    import argparse
    import inspect
    import sys
    commands = {'baseline': '_entry_verify_regional_hydraulics', 'accelerated-full': '_entry_verify_regional_hydraulics_accelerated_full', 'acceleration': '_entry_verify_regional_hydraulics_acceleration', 'compare': '_entry_verify_regional_hydraulics_compare', 'export': '_entry_verify_regional_hydraulics_export', 'failure': '_entry_verify_regional_hydraulics_failure', 'full': '_entry_verify_regional_hydraulics_full', 'mesh-load': '_entry_verify_regional_hydraulics_mesh_load', 'profile': '_entry_verify_regional_hydraulics_profile', 'space': '_entry_verify_regional_hydraulics_space', 'space-load': '_entry_verify_regional_hydraulics_space_load', 'summary': '_entry_verify_regional_hydraulics_summary'}
    values = list(sys.argv[1:] if argv is None else argv)
    if len(commands) == 1:
        selected = next(iter(commands))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        option = '--check'
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
