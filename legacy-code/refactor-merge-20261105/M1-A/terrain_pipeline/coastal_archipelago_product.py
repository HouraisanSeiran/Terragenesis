"""Source-bound immutable coastal archipelago derivative."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import numpy as np
import psutil
from terrain_pipeline.coastal_terrain import classify, coastal_support, CoastalParameters
from terrain_pipeline.coastal_terrain_product import read_product as read_v1, file_hash, plate_macro
from terrain_pipeline.coastal_archipelago import relief, SUBSEED


PARAMETERS = {'amplitude_m':300.0, 'envelope_spacing_m':18000.0, 'envelope_offset':0.55, 'envelope_range':0.9, 'envelope_power':2, 'warp_spacing_m':4000.0, 'warp_m':900.0, 'rotation_cos_sin':[0.8,0.6], 'ridge_spacing_m':850.0, 'ridge_anisotropy':1.8, 'detail_spacing_m':260.0, 'micro_spacing_m':150.0, 'weights':[0.78,0.17,0.05], 'depth_limit_m':450.0, 'depth_taper_m':250.0, 'salts':[10,20,30,50,60,70]}

def identity(m):
    return hashlib.sha256(json.dumps(m, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def anchor_for(m):
    z0, _, x0, _ = m['fixed_source_slice_zx']
    radius = m['valid_margin_cells']
    return (m['anchor_source_zx'][0]-z0-radius, m['anchor_source_zx'][1]-x0-radius)


def read_product(path, expected_identity=None):
    path = Path(path)
    m = json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    ident = m.pop('identity')
    if identity(m) != ident or (expected_identity and ident != expected_identity):
        raise ValueError('identity mismatch')
    m['identity'] = ident
    if (m.get('schema') != 'coastal-archipelago-v3' or m.get('algorithm_version') != 'regional-relief-v3' or
        m.get('parameters') != PARAMETERS or m.get('subseed_derivation') != 'first 8 bytes big endian SHA256 of 20261020:regional-coastal-relief-v3' or m.get('noise_helper_sha256') != file_hash(Path(__file__).resolve().parents[1]/'diffusion/geographic_noise.py') or m.get('world_seed') != 20261020 or m.get('subseed') != SUBSEED or not isinstance(m.get('strength'), (int,float)) or
        not np.isfinite(m['strength']) or not 0 <= m['strength'] <= 1 or
        set(m['files']) != {'bed.npy','valid.npy','classification.npy','shoreline.npy','relief.npy','support.npy'}):
        raise ValueError('invalid schema or parameters')
    arrays = {}
    for name, digest in m['files'].items():
        if file_hash(path/name) != digest:
            raise ValueError('file hash mismatch')
        arrays[name[:-4]] = np.load(path/name, allow_pickle=False)
    b, v, c, s, r, support = (arrays[k] for k in ('bed','valid','classification','shoreline','relief','support'))
    if (any(list(a.shape) != m['shape_zx'] for a in arrays.values()) or b.dtype != np.float32 or r.dtype != np.float32 or support.dtype != np.float32 or v.dtype != np.bool_ or c.dtype != np.uint8 or s.dtype != np.bool_ or not np.isfinite(b).all() or not np.isfinite(r).all() or not np.isfinite(support).all() or np.any((support<0)|(support>1)) or np.any(r[~v] != 0) or np.any(np.abs(r) > 300*m['strength']+0.001)):
        raise ValueError('invalid fields')
    base, source = read_v1(m['baseline_path'], expected_identity=m['baseline_identity'])
    if (any(m[k] != base[k] for k in ('origin_xz_m','spacing_m','terrain_identity','raw_file_sha256','macro_identity','anchor_world_xz_m')) or not np.array_equal(v, source['valid']) or not np.array_equal(b, source['bed'] + r)):
        raise ValueError('source mismatch')
    expected_relief = relief(source['bed'], v, support, m['origin_xz_m'], m['spacing_m'], m['strength'])
    if not np.array_equal(r, expected_relief):
        raise ValueError('relief parameter mismatch')
    cc, ss = classify(b, v, [anchor_for(base)])
    if not np.array_equal(c, cc) or not np.array_equal(s, ss):
        raise ValueError('classification mismatch')
    for a in arrays.values(): a.flags.writeable = False
    return m, arrays


def prepare(baseline, output, strength, expected_baseline_identity, memory_budget_bytes=1200000000):
    output = Path(output)
    if output.exists(): raise FileExistsError(output)
    if not expected_baseline_identity or not np.isfinite(strength) or not 0 <= strength <= 1: raise ValueError('invalid source or strength')
    parent = output.parent
    while not parent.exists(): parent = parent.parent
    if memory_budget_bytes < 1200000000 or psutil.virtual_memory().available < 1200000000 or shutil.disk_usage(parent).free < 400000000: raise ValueError('insufficient resources')
    m, a = read_v1(baseline, expected_identity=expected_baseline_identity)
    z0,z1,x0,x1 = m['fixed_source_slice_zx']
    if m['plate_path']:
        if file_hash(m['plate_path']) != m['plate_file_sha256']: raise ValueError('plate source mismatch')
        macro = plate_macro(m['plate_path'], m['macro_identity'], (z1-z0,x1-x0), (100530+x0*30,-57510+z0*30), 30)
    else:
        if file_hash(m['original_macro_path']) != m['original_macro_file_sha256']: raise ValueError('macro source mismatch')
        macro = np.load(m['original_macro_path'], mmap_mode='r', allow_pickle=False)[z0:z1,x0:x1]
    if file_hash(m['raw_path']) != m['raw_file_sha256']: raise ValueError('TD source mismatch')
    support = coastal_support(macro, CoastalParameters(**m['parameters']), anchors=[(m['anchor_source_zx'][0]-z0,m['anchor_source_zx'][1]-x0)])
    radius=m['valid_margin_cells']; support=support[radius:-radius,radius:-radius].copy()
    r = relief(a['bed'], a['valid'], support, m['origin_xz_m'], m['spacing_m'], strength)
    bed = a['bed'] + r
    codes, shore = classify(bed, a['valid'], [anchor_for(m)])
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.archipelago-', dir=output.parent))
    try:
        arrays = {'bed':bed, 'valid':a['valid'], 'classification':codes, 'shoreline':shore, 'relief':r, 'support':support}
        files = {}
        for name, array in arrays.items():
            np.save(tmp/(name+'.npy'), array, allow_pickle=False)
            files[name+'.npy'] = file_hash(tmp/(name+'.npy'))
        manifest = {'schema':'coastal-archipelago-v3', 'algorithm_version':'regional-relief-v3', 'baseline_path':str(Path(baseline).resolve()), 'baseline_identity':m['identity'], 'terrain_identity':m['terrain_identity'], 'raw_file_sha256':m['raw_file_sha256'], 'macro_identity':m['macro_identity'], 'origin_xz_m':m['origin_xz_m'], 'spacing_m':m['spacing_m'], 'shape_zx':m['shape_zx'], 'world_seed':20261020, 'subseed':SUBSEED, 'subseed_derivation':'first 8 bytes big endian SHA256 of 20261020:regional-coastal-relief-v3', 'strength':strength, 'anchor_world_xz_m':m['anchor_world_xz_m'], 'parameters': PARAMETERS, 'noise_helper_sha256': file_hash(Path(__file__).resolve().parents[1]/'diffusion/geographic_noise.py'), 'engineering_note':'continuous engineering relief; not geological reconstruction', 'algorithm_sha256':{p.name:file_hash(p) for p in [Path(__file__),Path(__file__).with_name('coastal_archipelago.py')]}, 'files':files}
        manifest['identity'] = identity(manifest)
        (tmp/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        read_product(tmp, manifest['identity'])
        os.rename(tmp, output)
    finally:
        if tmp.exists() and tmp.parent.resolve() == output.parent.resolve() and tmp.name.startswith('.archipelago-'): shutil.rmtree(tmp)
    return read_product(output)

