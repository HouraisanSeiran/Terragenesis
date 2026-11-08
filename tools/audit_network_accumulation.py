"""Cold-audit finite joint-graph discharge on saved native TD receivers.

Uses existing fixed-seed rain forcing, never generates terrain. A cropped diagnostic
cuts outgoing links to unknown terminals explicitly. Full source mode does not modify
receivers. Source topology consistency is not certified by a mass balance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.ndimage import maximum_filter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.surface_rivers.metric_network_discharge_product import (
    build_discharge_product, save_discharge_product,
)
from terrain_pipeline.climate_forcing import interval_mean_rain_mm_h


def run(source, output, side=128):
    start = time.perf_counter()
    with np.load(source, allow_pickle=False) as data:
        full_rec = np.array(data['receiver'], np.int64)
        valid = np.array(data['covered_mask'], bool)
        old_q = np.array(data['routed_q_m3_s'], np.float64)
        origin = np.array(data['origin_native_cells'], np.int64)
    full_rows, full_cols = full_rec.shape
    rows = full_rows if side == 0 else min(side, full_rows)
    cols = full_cols if side == 0 else min(side, full_cols)
    valid = valid[:rows, :cols].copy()
    old_q = old_q[:rows, :cols].copy()
    rec = full_rec[:rows, :cols].copy()
    del full_rec
    live = rec >= 0
    rr = np.where(live, rec // full_cols, 0)
    cc = np.where(live, rec % full_cols, 0)
    outside = live & ((rr >= rows) | (cc >= cols))
    rec = np.where(live & ~outside, rr * cols + cc, -1).astype(np.int64)
    del rr, cc, live
    # Boundary-adjacent cells might receive absent upstream contributions. This
    # is conservative; no finite crop is declared an infinite-world catchment.
    unknown = valid & maximum_filter((~valid).astype(np.uint8), size=3,
                                     mode='constant', cval=1).astype(bool)
    kinds = np.full(rec.shape, 'interior', dtype='U16')
    kinds[(rec < 0) & valid] = 'retained'
    kinds[(rec < 0) & valid & (unknown | outside)] = 'unknown_boundary'
    kinds[~valid] = 'inactive'
    local = np.zeros(rec.shape, np.float64)
    for r0 in range(0, rows, 128):
        r1 = min(rows, r0 + 128)
        x = np.broadcast_to((origin[0] + np.arange(cols))[None, :] * 30., (r1-r0, cols))
        z = np.broadcast_to((origin[1] + np.arange(r0, r1))[:, None] * 30., (r1-r0, cols))
        rain = interval_mean_rain_mm_h(20261020, x.ravel(), z.ravel(), 0., 3600.)
        local[r0:r1] = rain.reshape(r1-r0, cols) / 1000. / 3600. * 900.
    local[~valid] = 0.
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    product = build_discharge_product(
        rec, local, valid, kinds, unknown,
        origin_native_cells=tuple(int(value) for value in origin),
        world_seed=20261020, interval_seconds=(0., 3600.),
        source_sha256=source_sha256,
        forcing_semantics='declared rain_mm_h / 1000 / 3600 * 900; no infiltration, ET or storage')
    result = dict(product['metadata']['ledger'])
    result['policy'] = product['metadata']['policy']
    result.update({name: product['arrays'][name] for name in
                   ('known_routed_q_m3_s', 'complete_mask', 'terminal_q_m3_s')})
    new_q = result['known_routed_q_m3_s']
    comparison = None
    if side:
        # Independent, source-by-source reference, not another Kahn sweep.
        expected = np.zeros(rec.size, np.float64)
        dirty = np.zeros(rec.size, bool)
        for source_cell in np.flatnonzero(valid.ravel()):
            current = int(source_cell)
            seen = set()
            while current >= 0:
                if current in seen:
                    raise AssertionError('cycle in independent walk')
                seen.add(current)
                expected[current] += local.ravel()[source_cell]
                dirty[current] |= unknown.ravel()[source_cell]
                current = int(rec.ravel()[current])
        np.testing.assert_allclose(new_q.ravel(), expected, rtol=1e-12, atol=1e-15)
        np.testing.assert_array_equal(result['complete_mask'], valid & ~dirty.reshape(rec.shape))
        comparison = float(np.max(np.abs(new_q.ravel() - expected)))
    relative = abs(result['residual_m3_s']) / max(result['input_total_m3_s'], 1e-300)
    if relative > 1e-12:
        raise AssertionError('water ledger failed tolerance')
    complete = result['complete_mask']
    delta = np.abs(new_q - old_q)
    report = {key: value for key, value in result.items() if not isinstance(value, np.ndarray)}
    report.update({
        'source': str(source), 'source_sha256': source_sha256,
        'product_identity_sha256': product['identity_sha256'],
        'product_directory': 'flow-product',
        'product_cold_recomputation': True,
        'shape': list(rec.shape), 'world_seed': 20261020, 'spacing_m': 30.,
        'forcing_interval_s': [0., 3600.], 'conversion': 'rain_mm_h / 1000 / 3600 * 900',
        'complete_cells': int(complete.sum()), 'unknown_seed_cells': int(unknown.sum()),
        'complete_means': 'no declared unknown upstream in this finite graph; not infinite-world certified',
        'independent_path_max_abs_difference_m3_s': comparison,
        'independent_path_executed': bool(side),
        'ledger_relative_residual': relative,
        'old_tiled_q_max_abs_difference_m3_s': float(delta[valid].max()),
        'old_tiled_q_differing_over_1e_12': int((valid & (delta > 1e-12)).sum()),
        'old_tiled_q_complete_region_max_abs_difference_m3_s': float(delta[complete].max()) if complete.any() else None,
        'seconds': time.perf_counter() - start,
        'not_claimed': ['receiver window invariance', 'hydraulics', 'unbounded streaming', 'natural outlets'],
    })
    output.mkdir(parents=True, exist_ok=False)
    save_discharge_product(output / 'flow-product', product)
    # Keep the diagnostic array view for old analysis scripts; consumers should
    # cold-read flow-product, not treat this compatibility view as certified Q.
    np.savez_compressed(output / 'known-flow.npz', known_routed_q_m3_s=new_q,
                        complete_mask=complete, terminal_q_m3_s=result['terminal_q_m3_s'])
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--side', type=int, default=128, help='0 for full saved graph')
    args = parser.parse_args()
    if args.side < 0:
        parser.error('side must be nonnegative')
    run(args.source, args.output, args.side)
