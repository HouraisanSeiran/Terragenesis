"""Prepare an auditable 100 m window from fixed-owner native TD pages."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy import ndimage, sparse
from terrain_pipeline.coastal_marine_product import load_product, file_hash
from terrain_pipeline.coastal_marine_sediment import load_state, save_state, make_state

ROOT = Path('.scratch/coast-marine-reorganization-20261102')
SOURCE = Path('.scratch/delta-scale-suite-20261102/source-case300')
ORIGIN = (-19950., -19950.)
SHAPE = (450, 450)
SPACING = 100.
RETAINED_DEPTH_FRACTION = 0.1
UPLIFT_SOFTENING_START = 0.9


def overlap_matrix(n_old, old_origin, old_spacing, n_new, new_origin, new_spacing):
    """Fraction of each old cell covered by each new cell, including partial crops."""
    rows, cols, vals = [], [], []
    for j in range(n_new):
        lo = new_origin + j * new_spacing - new_spacing / 2
        hi = lo + new_spacing
        first = max(0, int(np.floor((lo - old_origin + old_spacing / 2) / old_spacing)))
        last = min(n_old, int(np.ceil((hi - old_origin + old_spacing / 2) / old_spacing)))
        for i in range(first, last):
            a = old_origin + i * old_spacing - old_spacing / 2
            length = max(0., min(hi, a + old_spacing) - max(lo, a))
            if length:
                rows.append(j); cols.append(i); vals.append(length / old_spacing)
    return sparse.csr_matrix((vals, (rows, cols)), shape=(n_new, n_old))


def migrate_volume(array, old_origin, old_spacing, shape=SHAPE, origin=ORIGIN, spacing=SPACING):
    z = overlap_matrix(array.shape[0], old_origin[1], old_spacing, shape[0], origin[1], spacing)
    x = overlap_matrix(array.shape[1], old_origin[0], old_spacing, shape[1], origin[0], spacing)
    return (x @ (z @ array).T).T


def classify(source_bed, valid, parent_ocean):
    wet = valid & (source_bed < 0)
    edge = np.zeros(valid.shape, bool)
    edge[[0, -1], :] = True; edge[:, [0, -1]] = True
    seeds = edge & wet & parent_ocean
    labels, _ = ndimage.label(wet)
    ids = np.unique(labels[seeds]); ids = ids[ids != 0]
    ocean = wet & np.isin(labels, ids)
    return ocean, wet & ~ocean, seeds


def sample_pages(manifest, shape=SHAPE, origin=ORIGIN, spacing=SPACING):
    # Nearest native node; ties go toward +infinity. Owner is based on the node.
    xx = np.floor((origin[0] + np.arange(shape[1]) * spacing) / 30 + .5).astype(int)
    zz = np.floor((origin[1] + np.arange(shape[0]) * spacing) / 30 + .5).astype(int)
    result = np.full(shape, np.nan, np.float32)
    records = []
    pages = {tuple(p['page_xz']): p for p in manifest['pages']}
    for pz in np.unique(np.floor_divide(zz, 1024)):
        rz = np.flatnonzero(np.floor_divide(zz, 1024) == pz)
        for px in np.unique(np.floor_divide(xx, 1024)):
            cx = np.flatnonzero(np.floor_divide(xx, 1024) == px)
            rec = pages.get((int(px), int(pz)))
            if rec is None:
                continue
            path = Path(rec['path'])
            if file_hash(path / 'manifest.json') != rec['manifest_sha256']:
                raise ValueError('page manifest hash mismatch: ' + str(path))
            pm = json.loads((path / 'manifest.json').read_text(encoding='utf-8-sig'))
            raw = path / 'raw_td.npy'
            if file_hash(raw) != rec['raw_td_sha256'] or pm['identity'] != rec['identity'] or pm['files']['raw_td'] != rec['raw_td_sha256']:
                raise ValueError('page identity/hash mismatch: ' + str(path))
            data = np.load(raw, mmap_mode='r', allow_pickle=False)
            if list(data.shape) != pm['source_shape_zx'] or pm['spacing_m'] != 30:
                raise ValueError('bad native page geometry')
            ox, oz = pm['origin_native_xz']
            iz, ix = zz[rz] - oz, xx[cx] - ox
            if min(iz.min(), ix.min()) < 0 or iz.max() >= data.shape[0] or ix.max() >= data.shape[1]:
                raise ValueError('owner outside native page')
            result[np.ix_(rz, cx)] = data[np.ix_(iz, ix)]
            records.append(rec)
    return result, records


def geological_base(bed, valid, ocean, correction, retained_depth_fraction=RETAINED_DEPTH_FRACTION,
                    softening_start=UPLIFT_SOFTENING_START):
    """Smoothly limit positive uplift by source depth; leave negative change intact."""
    if not 0 < retained_depth_fraction < 1 or not 0 < softening_start < 1:
        raise ValueError('depth fraction and softening start must lie between zero and one')
    source = np.asarray(bed, dtype=np.float64)
    change = np.asarray(correction, dtype=np.float64)
    result = np.where(valid, source, 0.).copy()
    if np.any(ocean & (~valid | (source >= 0))) or not np.isfinite(change[ocean]).all():
        raise ValueError('invalid ocean or correction')
    depth = -source[ocean]
    uplift = change[ocean]
    capacity = depth * (1. - retained_depth_fraction)
    threshold = capacity * softening_start
    tail = capacity - threshold
    positive = np.maximum(uplift, 0.)
    limited = np.minimum(uplift, 0.) + np.minimum(positive, threshold)
    limited += tail * (-np.expm1(-np.maximum(positive - threshold, 0.) / tail))
    result[ocean] = source[ocean] + limited
    return result


def prepare(output=ROOT / 'window100-v2'):
    started = time.perf_counter()
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    sm = json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8-sig'))
    bed, pages = sample_pages(sm)
    valid = np.isfinite(bed)
    bm, ba = load_product(ROOT / 'base-product-v2')
    old = load_state(ROOT / 'tidal-plain-v1-year10.npz')
    z = (ORIGIN[1] + np.arange(SHAPE[0]) * SPACING - bm['origin_xz_m'][1]) / bm['spacing_m']
    x = (ORIGIN[0] + np.arange(SHAPE[1]) * SPACING - bm['origin_xz_m'][0]) / bm['spacing_m']
    coords = np.meshgrid(z, x, indexing='ij')
    parent = np.load(SOURCE / 'ocean.npy', mmap_mode='r')
    if file_hash(SOURCE / 'ocean.npy') != sm['files_sha256']['ocean']:
        raise ValueError('parent ocean hash mismatch')
    parent_ocean = ndimage.map_coordinates(parent.astype(np.uint8), coords, order=0, mode='constant', cval=0).astype(bool)
    ocean, unknown, seeds = classify(bed, valid, parent_ocean)
    correction = ndimage.map_coordinates(ba['base_change_m'], coords, order=1, mode='nearest')
    derived = geological_base(bed, valid, ocean, correction)
    volumes = {name: migrate_volume(getattr(old, name), old.origin_xz_m, old.spacing_m) for name in ('bed_solid_m3', 'mobile_solid_m3', 'stranded_solid_m3')}
    if any(np.any(v[~valid] > 1e-9) for v in volumes.values()):
        raise ValueError('historical stock overlaps missing TD coverage')
    ledger = {name: {'old_m3': float(getattr(old, name).sum()), 'inside_m3': float(v.sum()), 'outside_crop_m3': float(getattr(old, name).sum() - v.sum())} for name, v in volumes.items()}
    conflict = valid & ~ocean
    conflict_amount = float((volumes['bed_solid_m3'][conflict] + volumes['mobile_solid_m3'][conflict]).sum())
    volumes['stranded_solid_m3'][conflict] += volumes['bed_solid_m3'][conflict] + volumes['mobile_solid_m3'][conflict]
    volumes['bed_solid_m3'][conflict] = 0; volumes['mobile_solid_m3'][conflict] = 0
    por = ndimage.map_coordinates(old.porosity, coords, order=0, mode='nearest')
    payload = {'algorithm': 'fixed-owner-nearest30-parent-edge-overlap-v2', 'geological_uplift': {'method': 'depth-limited-exponential-v1', 'retained_depth_fraction': RETAINED_DEPTH_FRACTION, 'softening_start_fraction_of_capacity': UPLIFT_SOFTENING_START}, 'world_seed': 20261020, 'origin_xz_m': ORIGIN, 'spacing_m': SPACING, 'shape_zx': SHAPE, 'pages': pages, 'parent_identity': sm['source_identity'], 'base_identity': bm['identity'], 'old_state_sha256': file_hash(ROOT / 'tidal-plain-v1-year10.npz')}
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    state = make_state(base_bed_m=derived, porosity=por, valid_mask=valid, ocean_seed_mask=seeds, spacing_m=SPACING, origin_xz_m=ORIGIN, source_identity=identity, time_s=old.time_s, **volumes)
    state = replace(state, exported_solid_m3=old.exported_solid_m3, unresolved_solid_m3=old.unresolved_solid_m3, water_input_m3=old.water_input_m3, consumed_packets=old.consumed_packets)
    output.mkdir(parents=True)
    np.savez_compressed(output / 'source.npz', source_bed_m=bed, derived_base_bed_m=derived, valid_mask=valid, source_ocean=ocean, unknown_wet=unknown, ocean_seed_mask=seeds, origin_xz_m=ORIGIN, spacing_m=SPACING)
    save_state(output / 'state.npz', state)
    load_state(output / 'state.npz')
    coarse_bed = np.load(SOURCE / 'bed_m.npy', mmap_mode='r')
    coarse = ndimage.map_coordinates(coarse_bed, coords, order=1, mode='nearest')
    delta = bed[valid] - coarse[valid]
    manifest = dict(payload, schema='coastal-delta-window-v1', source_identity=identity, source_sha256=file_hash(output / 'source.npz'), state_sha256=file_hash(output / 'state.npz'), old_checkpoint_json_sha256=file_hash(ROOT / 'tidal-plain-v1-year10.json'), crop_inventory=ledger, conflict_to_stranded_m3=conflict_amount, valid_cells=int(valid.sum()), ocean_cells=int(ocean.sum()), unknown_wet_cells=int(unknown.sum()), sample_difference_m={'mean': float(delta.mean()), 'rms': float(np.sqrt(np.mean(delta**2))), 'max_abs': float(np.max(np.abs(delta)))}, coastline_sign_disagreement_cells=int(np.sum(valid & ((bed < 0) != (coarse < 0)))), elapsed_s=time.perf_counter()-started, notes=['Nearest native 30 m samples; no 600 m terrain upsampling.', 'Coarse geological correction sampled continuously on connected source ocean; positive uplift smoothly limited by source depth, land and unknown unchanged.', 'Historical outside crop is not export; no nested flux coupling.', 'Historical counters and packet identities retained; no new evolution.'])
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


if __name__ == '__main__':
    print(json.dumps(prepare(), ensure_ascii=False))
