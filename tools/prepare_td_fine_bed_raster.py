"""Pinned task06 and optional task09 to a bounded native-DEM bed raster."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import psutil
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_fine_bed_raster import MAX_BYTES, build_fine_bed_raster, save_fine_bed_raster
from terrain_pipeline.channel_geometry import validate_watershed_sections
GEOMETRY = ROOT / 'verification/natural-river-network/watershed-geometry-20261005-01'
GEOMETRY_INDEX_SHA = 'fec57d5c9df599ba3c419d2283910d27afe172c236743b3536769bf579af662b'
HIERARCHY_SHA = '36a50a14560d3f6bc178350786bcac5bbf53acf97d2754af0e81fef5c79df422'
HIERARCHY_IDENTITY = 'cdb39ff2866281e23ca0cd4f5388ddfa0a158b621fb1fe8dd9d635e887b73998'
MAX_RSS_BYTES = 1024 ** 3

def _read_json(path, expected_sha=None):
    if path.stat().st_size > MAX_BYTES:
        raise MemoryError('input JSON exceeds 64MiB')
    payload = path.read_bytes()
    if expected_sha is not None and hashlib.sha256(payload).hexdigest() != expected_sha:
        raise ValueError('input file SHA mismatch: ' + str(path))
    return json.loads(payload)

def _path(base, pin):
    path = (base / pin['path']).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('input outside workspace')
    return path

def _pin(path, record=None):
    pin = {'path': str(path.resolve()), 'sha256': file_sha256(path), 'bytes': path.stat().st_size}
    if record is not None:
        pin['identity_sha256'] = record['identity_sha256']
    return pin

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--transitions', type=Path)
    parser.add_argument('--transitions-sha256')
    parser.add_argument('--scope', choices=('all', 'lake-entry-neighborhood', 'transitions-only'), default='all')
    parser.add_argument('--fine-spacing-m', type=float, default=2.0)
    parser.add_argument('--max-cut-m', type=float, default=4.0)
    parser.add_argument('--max-cells', type=int, default=2000000)
    parser.add_argument('--max-windows', type=int, default=4096)
    args = parser.parse_args()
    started = time.perf_counter()
    process = psutil.Process()
    peak_rss = 0

    def resource_check():
        nonlocal peak_rss
        memory = process.memory_info()
        peak_rss = max(peak_rss, memory.rss, getattr(memory, 'peak_wset', 0))
        if peak_rss > MAX_RSS_BYTES:
            raise MemoryError('process peak RSS exceeds hard 1GiB limit')
    resource_check()
    output = args.output.resolve()
    allowed = (ROOT / 'verification/natural-river-network').resolve()
    if not output.is_relative_to(allowed) or output == allowed or output.exists():
        raise ValueError('new verification output directory required')
    index_path = GEOMETRY / 'index.json'
    index = _read_json(index_path, GEOMETRY_INDEX_SHA)
    hierarchy_pin = index['inputs']['hierarchy']
    if hierarchy_pin['sha256'] != HIERARCHY_SHA or hierarchy_pin['identity_sha256'] != HIERARCHY_IDENTITY:
        raise ValueError('fixed native hierarchy pin mismatch')
    hierarchy_path = _path(GEOMETRY, hierarchy_pin)
    hierarchy = load_basin_hierarchy(hierarchy_path, expected_sha256=HIERARCHY_SHA, expected_identity=HIERARCHY_IDENTITY)
    resource_check()
    section_path = _path(GEOMETRY, index['sections'])
    sections = _read_json(section_path, index['sections']['sha256'])
    if sections['identity_sha256'] != index['sections']['identity_sha256']:
        raise ValueError('section external identity mismatch')
    validate_watershed_sections(sections)
    path_path = _path(GEOMETRY, index['paths'])
    paths = _read_json(path_path, index['paths']['sha256'])
    if paths['identity_sha256'] != index['paths']['identity_sha256']:
        raise ValueError('paths external identity mismatch')
    wet_protection = {'covered_native_cell_ids': sorted({cell for lake in paths['lakes'] for cell in lake['covered_cell_ids']}), 'stage_by_leaf': [{'leaf_id': lake['leaf_id'], 'stage_m': lake['ordinary_stage_max_m']} for lake in sorted(paths['lakes'], key=lambda item: item['leaf_id'])]}
    land_arcs = {arc['arc_id'] for arc in paths['arcs'] if arc['kind'] == 'land_channel' and arc['channel_candidate'] is True}
    if any((edge['arc_id'] not in land_arcs for edge in sections['edge_sections'])):
        raise ValueError('source support corridor cannot be carved')
    pins = {'06_index': _pin(index_path), 'hierarchy': _pin(hierarchy_path, hierarchy), '06_sections': _pin(section_path, sections), '06_paths': _pin(path_path, paths)}
    transitions = None
    if args.transitions is not None:
        transition_path = args.transitions.resolve(strict=True)
        if not transition_path.is_relative_to(ROOT.resolve()):
            raise ValueError('transition outside workspace')
        transitions = _read_json(transition_path, args.transitions_sha256)
        if 'entries' not in transitions or 'identity_sha256' not in transitions:
            raise ValueError('09 transition entries and identity required')
        declared_wet = transitions.get('wet_protection')
        if not isinstance(declared_wet, dict) or any((declared_wet.get(key) != wet_protection[key] for key in wet_protection)):
            raise ValueError('09 wet protection declaration differs from fixed 06 lakes')
        if transitions.get('paths_identity_sha256', paths['identity_sha256']) != paths['identity_sha256']:
            raise ValueError('09 transition paths identity mismatch')
        if transitions.get('schema') == 'td-lake-entry-taper-v1':
            payload = {key: value for key, value in transitions.items() if key != 'identity_sha256'}
            expected_identity = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
            if expected_identity != transitions['identity_sha256']:
                raise ValueError('09 transition content identity mismatch')
            if any((transitions.get(flag) is not False for flag in ('hydraulic_ready', 'natural_outlet_verified', 'publishable', 'new_bed_hydrology_verified', 'solver_advanced', 'lake_bed_changed'))):
                raise ValueError('09 transition certification/mutation flags must be false')
        pins['09_transitions'] = _pin(transition_path, transitions)
    elif args.transitions_sha256 is not None:
        raise ValueError('transition SHA provided without file')
    record = build_fine_bed_raster(hierarchy, sections, transitions, fine_spacing_m=args.fine_spacing_m, max_cut_m=args.max_cut_m, max_cells=args.max_cells, max_windows=args.max_windows, input_pins=pins, scope=args.scope, resource_check=resource_check, wet_protection=wet_protection)
    code = {str(path.relative_to(ROOT)).replace('\\', '/'): file_sha256(path) for path in (ROOT / 'terrain_pipeline/td_fine_bed_raster.py', Path(__file__).resolve(), ROOT / 'terrain_pipeline/mountain_source_adapter.py', ROOT / 'terrain_pipeline/basin_topology.py', ROOT / 'terrain_pipeline/channel_geometry.py')}
    artifact_path = output / 'fine-bed-raster.json'
    save_fine_bed_raster(record, artifact_path, resource_check=resource_check)
    artifact_pin = _pin(artifact_path, record)
    resource_check()
    result = {'schema': 'td-fine-bed-raster-preparation-v1', 'status': 'candidate_only', 'inputs': pins, 'code_sha256': code, 'raster': artifact_pin, 'summary': record['summary'], 'grid': record['grid'], 'selection': record['selection'], 'material_ledger': record['material_ledger'], 'water_solves': 0, 'hydraulic_ready': False, 'natural_outlet_certified': False, 'publish_ready': False, 'resource': {'peak_rss_bytes': peak_rss, 'max_rss_bytes': MAX_RSS_BYTES, 'rss_measurement': 'Windows peak_wset plus sampled process rss', 'elapsed_s': time.perf_counter() - started, 'water_solves': 0, 'forest_rebuilds': 0, 'artifact_bytes': artifact_pin['bytes'], 'max_json_bytes': MAX_BYTES}, 'in_memory_validation_passed': True, 'cold_structural_read_passed': False, 'independent_native_audit_passed': False}
    payload = json.dumps(result, sort_keys=True, allow_nan=False, indent=2).encode()
    publish_bytes(output / 'index.json', payload)
    print(json.dumps(result['summary'], sort_keys=True))
if __name__ == '__main__':
    main()
