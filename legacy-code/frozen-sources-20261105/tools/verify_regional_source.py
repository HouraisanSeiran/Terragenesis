"""Prepare the fixed full regional source, with no GPU or surface solver."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.regional_surface_source import build_source, save_source, load_source
from terrain_pipeline.mountain_source_adapter import file_sha256
from tools.verify_mountain_source_adapter import write_json, snapshot, assert_unchanged

def main():
    destination = ROOT / 'verification/regional-source' / ('run-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    before = snapshot()
    static = ROOT / 'verification/mountain-real-td/frozen-20261001-inland256-v1'
    report = json.loads((static / 'report.json').read_text(encoding='utf-8'))
    source = build_source(ROOT / 'verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-td-output.npz', static / 'primary-geometry.npz', geometry_sha256=report['windows']['primary']['geometry_sha256'])
    save_source(destination / 'source.npz', source)
    cold = load_source(destination / 'source.npz', expected_sha256=file_sha256(destination / 'source.npz'))
    write_json(destination / 'manifest.json', {'schema': 'regional-source-handoff-v1', 'source_identity': cold['identity_sha256'], 'source_path': str(destination / 'source.npz'), 'source_sha256': file_sha256(destination / 'source.npz'), 'metadata': cold['metadata'], 'frozen_after': assert_unchanged(before), 'delivery_sha256': {name: file_sha256(ROOT / name) for name in ('terrain_pipeline/regional_surface_source.py', 'tools/verify_regional_source.py')}})
    print(str(destination), flush=True)
if __name__ == '__main__':
    main()
