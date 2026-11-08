"""Serial full-grid forcing preparation; mmap output, no surface simulation."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.regional_surface_forcing import generate_forcing, load_forcing
from terrain_pipeline.rainfall_runoff import RunoffParameters
from terrain_pipeline.mountain_storm_forcing import StormParameters
from terrain_pipeline.mountain_source_adapter import file_sha256
from tools.verify_mountain_source_adapter import write_json, snapshot, assert_unchanged

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-directory', type=Path, required=True)
    args = parser.parse_args()
    source_manifest = json.loads((args.source_directory / 'manifest.json').read_text(encoding='utf-8'))
    source = load_source(args.source_directory / 'source.npz', expected_sha256=source_manifest['source_sha256'])
    destination = ROOT / 'verification/regional-forcing' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    before = snapshot()
    write_json(destination / 'resource-proposal.json', {'cases': ['dry', 'wet_no_rain', 'uniform_heavy'], 'grid': [256, 256], 'area_m2': 58982400.0, 'steps': 288, 'dt_s': 900.0, 'block_cells': 4096, 'max_resident_budget_bytes': 134217728, 'max_disk_case_bytes': 536870912, 'planned_runoff_case_bytes': 150994944, 'serial_cases': True, 'surface_initial_depth_m': 0.0, 'wet_initial_soil_mm': 135.0, 'dry_initial_soil_fast_slow_mm': 0.0, 'heavy_mm_h': 24.0, 'heavy_active_hours': [6.0, 18.0], 'expected_heavy_rain_m3': 16986931.2, 'no_direct_surface_rain': True, 'B_adds_runoff_once': True, 'no_GPU': True, 'no_surface_solver': True})
    report = {'source_identity': source['identity_sha256'], 'source_manifest_sha256': file_sha256(args.source_directory / 'manifest.json'), 'cases': {}}
    for name, initial, storm in (('dry', 0.0, None), ('wet_no_rain', 135.0, None), ('uniform_heavy', 135.0, StormParameters(0.0, 0.0, 0.0, 0.0, 300.0, 24.0, 21600.0, 64800.0, spatial_mode='uniform'))):
        started = time.perf_counter()
        generated = generate_forcing(source, destination / name, parameters=RunoffParameters(initial_soil_mm=initial), storm=storm)
        manifest_sha = file_sha256(destination / name / 'manifest.json')
        cold = load_forcing(destination / name, expected_manifest_sha256=manifest_sha, source_identity=source['identity_sha256'])
        cold['runoff_volume_m3']._mmap.close()
        report['cases'][name] = {'path': str(destination / name), 'manifest_sha256': manifest_sha, 'seconds': time.perf_counter() - started, 'cold_static_passed': True, **{key: generated[key] for key in ('total_rain_m3', 'total_et_m3', 'total_runoff_to_B_m3', 'whole_account_residual_m3', 'max_cell_residual_m3')}}
        write_json(destination / (name + '-completed.json'), report['cases'][name])
    report['frozen_after'] = assert_unchanged(before)
    report['delivery_sha256'] = {name: file_sha256(ROOT / name) for name in ('terrain_pipeline/regional_surface_forcing.py', 'tools/verify_regional_forcing.py')}
    write_json(destination / 'handoff-manifest.json', report)
    print(json.dumps({'directory': str(destination), **report}, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
