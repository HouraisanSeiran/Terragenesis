"""Cold-read a frozen TD partition and publish an externally hashed audit."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import publish_bytes
from terrain_pipeline.surface_domain import audit_td_partition, save_cross_domain_report
from tests.test_surface_domain import frozen_pins

def verify():
    hierarchy, storage = frozen_pins()
    report = audit_td_partition(hierarchy, partition_column=128, storage_record=storage)
    report['implementation_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ('terrain_pipeline/surface_domain.py', 'terrain_pipeline/td_surface_river_edges.py', 'tools/verify_surface_cross_domain_td.py', 'tests/test_surface_domain.py')}
    report['cross_precision_scope'] = 'Coarse face splitting remains tested synthetically. Frozen TD cut is native 30m; no finer physical evidence or synthetic TD flux division is claimed.'
    report['algorithm_scope'] = 'Frozen v2 stored flux only. v3 step-size trends are internal algorithm trends, not pair correctness.'
    output = ROOT / 'verification/surface-cross-domain' / ('td-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    save_cross_domain_report(report, output / 'report.json')
    digest = hashlib.sha256((output / 'report.json').read_bytes()).hexdigest()
    publish_bytes(output / 'pins.json', json.dumps({'report.json': digest}, indent=2).encode())
    print(json.dumps({'path': str(output), 'report_sha256': digest, 'flags': report['flags']}, ensure_ascii=False))
if __name__ == '__main__':
    verify()
