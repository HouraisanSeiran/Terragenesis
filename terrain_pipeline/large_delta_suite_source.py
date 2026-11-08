"""Read-only, coordinate-preserving regional sampling of the frozen TD mosaic."""
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_region(source, output, *, start_zx, shape_zx, stride):
    """Copy native cell centres at integer stride; reject missing coverage and bad pins."""
    source, output = Path(source), Path(output)
    manifest_path = source / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if manifest.get('schema') != 'new-world-terrain-v3' or manifest.get('world_seed') != 20261020 or manifest.get('spacing_m') != 30:
        raise ValueError('unsupported source identity, seed or spacing')
    if (type(stride) is not int or stride < 1 or len(start_zx) != 2 or len(shape_zx) != 2
            or any(type(v) is not int for v in (*start_zx, *shape_zx))
            or any(v < 0 for v in start_zx) or any(v < 1 for v in shape_zx)):
        raise ValueError('invalid region')
    if any(start + (count - 1) * stride >= size for start, count, size in zip(start_zx, shape_zx, manifest['shape_zx'])):
        raise ValueError('region exceeds actual TD coverage')
    if output.exists():
        raise FileExistsError(output)
    inputs = {'bed_m': 'bed_m', 'valid': 'valid_mask', 'ocean': 'ocean_mask'}
    arrays = {}
    source_hashes = {}
    slices = tuple(slice(s, s + n * stride, stride) for s, n in zip(start_zx, shape_zx))
    for name, key in inputs.items():
        path = source / (key + '.npy')
        actual = sha256(path)
        if actual != manifest['files'][key]:
            raise ValueError('source hash mismatch: ' + key)
        source_hashes[key] = actual
        array = np.load(path, mmap_mode='r', allow_pickle=False)
        if list(array.shape) != manifest['shape_zx']:
            raise ValueError('source shape mismatch: ' + key)
        arrays[name] = np.array(array[slices], copy=True)
    if not np.isfinite(arrays['bed_m'][arrays['valid']]).all() or np.any(arrays['ocean'] & ~arrays['valid']):
        raise ValueError('invalid source data')
    output.mkdir(parents=True)
    files = {}
    for name, array in arrays.items():
        path = output / (name + '.npy')
        np.save(path, array, allow_pickle=False)
        files[name] = sha256(path)
    native_origin = manifest['origin_native_xz']
    result = {'schema': 'large-delta-regional-source-v1', 'world_seed': 20261020,
              'source_identity': manifest['identity'], 'plate_identity': manifest['plate_identity'],
              'source_manifest_sha256': sha256(manifest_path), 'source_files_sha256': source_hashes,
              'files_sha256': files, 'shape_zx': list(shape_zx),
              'origin_xz_m': [(native_origin[0] + start_zx[1]) * 30, (native_origin[1] + start_zx[0]) * 30],
              'spacing_m': 30 * stride, 'sea_m': manifest['sea_m'],
              'sampling': 'native cell centre integer decimation; no interpolation',
              'known': ['source coordinates', 'world seed', 'TD source identity', 'finite valid mask'],
              'assumed': ['finite-boundary ocean classification inherits frozen macro, not global certification'],
              'ocean_note': manifest['classification_support'],
              'stats': {'valid_cells': int(arrays['valid'].sum()), 'ocean_cells': int(arrays['ocean'].sum()),
                        'shallow_ocean_minus_50_to_0_cells': int((arrays['ocean'] & (arrays['bed_m'] >= -50)).sum())}}
    (output / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result
