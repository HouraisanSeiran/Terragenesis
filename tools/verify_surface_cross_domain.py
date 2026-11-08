"""Generate a small, read-only cross-domain seam audit report."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.surface_domain import adapt_saved_mosaics, save_cross_domain_report
from terrain_pipeline.surface_domain import load_domain_mosaic

def fixture():

    def make(domain_id, reverse=False):
        sign = -1.0 if reverse else 1.0
        edges = [{'local_id': 0, 'start': 0, 'end': 1, 'flux_m3_s': sign * 0.25, 'boundary': False}, {'local_id': 1, 'start': 1, 'end': 2, 'flux_m3_s': sign * 0.1, 'boundary': False}]
        if reverse:
            for edge in edges:
                edge['start'], edge['end'] = (edge['end'], edge['start'])
        return {'domain_id': domain_id, 'grid': {'origin_x_m': 0.0, 'origin_z_m': 0.0, 'spacing_x_m': 1.0, 'spacing_z_m': 1.0, 'lod': 0}, 'nodes': [{'local_id': 0, 'x_m': 0.0, 'z_m': 0.0, 'h0_m': 10.0, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}, {'local_id': 1, 'x_m': 1.0, 'z_m': 0.0, 'h0_m': 9.0, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}, {'local_id': 2, 'x_m': 1.0, 'z_m': 1.0, 'h0_m': 8.0, 'unknown': False, 'protected': False, 'water_surface_m': 3.0}], 'edges': edges}
    return [make('A'), make('B', True)]
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'verification' / 'surface-cross-domain' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')) / 'report.json')
    arguments = parser.parse_args()
    fixture_path = ROOT / 'verification/surface-domain-mosaic/run-20260930T170535.835312Z/two-domain-dry-extension.npz'
    if not fixture_path.exists():
        raise FileNotFoundError(fixture_path)
    report = adapt_saved_mosaics([{'domain_id': 'saved-domain-mosaic', 'mosaic': load_domain_mosaic(fixture_path)}])
    report['fixture'] = {'path': str(fixture_path.resolve()), 'source_algorithm': 'surface-domain-mosaic-v1'}
    report['implementation_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ('terrain_pipeline/surface_domain.py', 'tests/test_surface_domain.py', 'tools/verify_surface_cross_domain.py')}
    save_cross_domain_report(report, arguments.output)
    print(json.dumps({'report': str(arguments.output.resolve()), 'flags': report['flags'], 'ledger': report['ledger']}, ensure_ascii=False))
