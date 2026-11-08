"""Bounded actual-scenario durable routing evidence; no terrain regeneration."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from terrain_pipeline.new_world_game_hydrology import lifecycle_inputs, read_product
from terrain_pipeline.new_world_river_lifecycle import PartitionRouter

ROOT = Path('.scratch/river-upgrade-20261101')
OUT = ROOT / 'hydro-lifecycle-v1'


def main():
    OUT.mkdir(exist_ok=False)
    product = read_product(ROOT / 'game-hydro-v1')
    adapted, local, state = lifecycle_inputs(product, ROOT / 'game-grade-90m', ROOT / 'terrain-v3')
    source = product.identity
    reference = product.arrays['node_water_m3'][0]
    rows = []
    for partitions in (1, 2, 4):
        journal = OUT / f'partition-{partitions}.sqlite'
        start = time.monotonic()
        router = PartitionRouter(journal, adapted, local, 15 * 86400, interval=0, source=source,
                                 partitions=partitions, state=state, trace=True,
                                 reverse_preparation=partitions == 4)
        prepared = time.monotonic()
        router.run(max_cells=20000)
        cursor = router.cursor
        router.close()
        restart = time.monotonic()
        router = PartitionRouter(journal, adapted, local, 15 * 86400, interval=0, source=source,
                                 partitions=partitions, state=state, trace=True,
                                 reverse_preparation=partitions == 4)
        router.run(max_cells=20000)
        trace = list(router.db.execute('SELECT cell, volume FROM trace'))
        error = max((abs(volume - float(reference[cell])) for cell, volume in trace), default=0.)
        if error != 0:
            raise ValueError('saved reference mismatch')
        packets = router.db.execute('SELECT COUNT(*) FROM packets').fetchone()[0]
        budget = router.budget()
        rows.append(dict(partitions=partitions, prepare_s=prepared-start, first_cursor=cursor,
                         final_cursor=router.cursor, total_active=len(router.order), packets=packets,
                         traced_nodes=len(trace), max_reference_error_m3=error, budget=budget,
                         resume_and_run_s=time.monotonic()-restart, total_s=time.monotonic()-start))
        router.close()
    digest = hashlib.sha256((product.directory / 'manifest.json').read_bytes()).hexdigest()
    result = dict(product_identity=source, source_manifest_sha256=digest, interval=0, rows=rows)
    (OUT / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
