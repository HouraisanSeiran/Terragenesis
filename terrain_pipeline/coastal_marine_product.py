"""Explicit preparation and verified loading of marine base products."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
import shutil
import numpy as np
from terrain_pipeline.coastal_marine_base import MarineBaseParameters, reorganize
from terrain_pipeline.tectonic import load_product as load_tectonic


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def identity(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def prepare(source_dir, output_dir, params=MarineBaseParameters(), *, plate_path='.scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz'):
    source_dir, output_dir = Path(source_dir), Path(output_dir)
    if output_dir.exists():
        raise FileExistsError(output_dir)
    source = json.loads((source_dir / 'manifest.json').read_text(encoding='utf-8-sig'))
    if source['schema'] != 'large-delta-regional-source-v1':
        raise ValueError('unsupported source')
    arrays = {}
    for name in ('bed_m', 'valid', 'ocean', 'unknown_wet'):
        path = source_dir / (name + '.npy')
        if file_hash(path) != source['files_sha256'][name]:
            raise ValueError('source file hash mismatch')
        arrays[name] = np.load(path, allow_pickle=False)
        if list(arrays[name].shape) != source['shape_zx']:
            raise ValueError('source shape mismatch')
    plate = load_tectonic(plate_path, expected_identity=source['plate_identity'])
    x = source['origin_xz_m'][0] + np.arange(source['shape_zx'][1])[None, :] * source['spacing_m']
    z = source['origin_xz_m'][1] + np.arange(source['shape_zx'][0])[:, None] * source['spacing_m']
    context = plate.sample(x, z, outside='reject')
    result = reorganize(arrays['bed_m'], arrays['valid'], arrays['ocean'], arrays['unknown_wet'], source['spacing_m'], params,
                        continental_fraction=context['continental_fraction'], crust_thickness_m=context['crust_thickness_m'])
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.marine-base-', dir=output_dir.parent))
    try:
        hashes = {}
        for name, array in result.items():
            path = tmp / (name + '.npy')
            np.save(path, array, allow_pickle=False)
            hashes[name] = file_hash(path)
        manifest = {'schema': 'coastal-marine-base-v1', 'algorithm_version': 'coast-following-v2',
                    'source_identity': source['source_identity'], 'source_manifest_sha256': file_hash(source_dir / 'manifest.json'),
                    'source_files_sha256': source['files_sha256'], 'source_path': str(source_dir.resolve()),
                    'plate_identity': source['plate_identity'], 'plate_path': str(Path(plate_path).resolve()), 'plate_file_sha256': file_hash(plate_path), 'world_seed': source['world_seed'],
                    'origin_xz_m': source['origin_xz_m'], 'spacing_m': source['spacing_m'], 'shape_zx': source['shape_zx'],
                    'coordinate_convention': 'cell centres, x east, z south, arrays [z,x]',
                    'parameters': asdict(params), 'scenario': 'source morphology and frozen model crust mapped to assumed shelf geometry; no sediment inventory',
                    'files_sha256': hashes}
        manifest['identity'] = identity(manifest)
        (tmp / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        load_product(tmp)
        os.rename(tmp, output_dir)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return load_product(output_dir)


def load_product(path):
    path = Path(path)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8-sig'))
    expected = manifest.pop('identity')
    if manifest.get('schema') != 'coastal-marine-base-v1' or identity(manifest) != expected:
        raise ValueError('invalid product identity')
    manifest['identity'] = expected
    arrays = {}
    for name, digest in manifest['files_sha256'].items():
        file = path / (name + '.npy')
        if file_hash(file) != digest:
            raise ValueError('product file hash mismatch')
        array = np.load(file, allow_pickle=False)
        if list(array.shape) != manifest['shape_zx']:
            raise ValueError('product shape mismatch')
        array.flags.writeable = False
        arrays[name] = array
    return manifest, arrays


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_dir')
    parser.add_argument('output_dir')
    parser.add_argument('--plate-path', default='.scratch/plate-formation-coast-20261101/shaped-run-v4/product.npz')
    args = parser.parse_args()
    manifest, _ = prepare(args.source_dir, args.output_dir, plate_path=args.plate_path)
    print(manifest['identity'])
