"""Run native product invariants on routing and event products (read-only)."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.drainage import check_event_budget as check_event_budget
from terrain_pipeline.drainage import check_routing as check_routing

ROOT = Path(__file__).resolve().parents[1] / '.scratch' / 'river-upgrade-20261101'


def main():
    result = {}
    routing = ROOT / 'native-final-routing-v1' / 'routing'
    valid = np.load(ROOT / 'terrain-v3' / 'valid_mask.npy', mmap_mode='r').ravel()
    result['routing'] = check_routing(np.load(routing / 'order.npy'), np.load(routing / 'receiver.npy'), valid)
    for name in ('native-event-v1', 'native-event-v2', 'native-event-v3'):
        manifest = json.loads((ROOT / name / 'manifest.json').read_text(encoding='utf8'))
        result[name] = check_event_budget(manifest)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if all(v['ok'] for v in result.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
