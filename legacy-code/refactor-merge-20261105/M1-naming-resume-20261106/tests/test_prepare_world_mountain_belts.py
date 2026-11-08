import json

import numpy as np
from PIL import Image
import pytest

from terrain_pipeline.tectonic import TectonicConfig, evolve
from terrain_pipeline.tectonic import freeze, save_product as save_base
from terrain_pipeline.mountain_forms import load_belt_product as load_product
from tools import prepare_world_mountain_belts as delivery


def test_height_png_has_one_fixed_mapping_and_exact_readback(tmp_path):
    height = np.array([[delivery.LOW, -3200., 0., 900., delivery.HIGH],
                       [delivery.LOW - 1., 100., 4000., 9000., delivery.HIGH + 1.]])
    info = delivery.export_height(tmp_path / 'height.png', height)
    with Image.open(tmp_path / 'height.png') as image:
        codes = np.asarray(image)
        assert image.mode in ('I;16', 'I')
    assert np.array_equal(codes, delivery.encode_height(height))
    in_range = (height >= delivery.LOW) & (height <= delivery.HIGH)
    error = delivery.decode_height(codes) - height
    assert np.max(np.abs(error[in_range])) <= (delivery.HIGH - delivery.LOW) / 65535 / 2 + 1e-10
    assert info['saturated_below_count'] == info['saturated_above_count'] == 1
    assert info['png_readback_equal']
    assert delivery.encode_height(np.array([[900.]]))[0, 0] == codes[0, 3]
    with pytest.raises(ValueError):
        delivery.encode_height(np.array([[np.nan]]))


def test_export_keeps_source_seeds_cold_arrays_and_gallery(tmp_path, monkeypatch):
    config = TectonicConfig(shape=(12, 16), plate_count=4, steps=2,
                            origin_x_m=-80000., origin_z_m=-60000.)
    base = freeze(config, evolve(config))
    source = tmp_path / 'base.npz'
    save_base(base, source)
    source_hash = delivery.digest(source)

    def render_stub(product, stage):
        # Valid bitmap written from the saved product, while this test targets export contracts.
        Image.fromarray(delivery.encode_height(product.arrays['elevation_m'])).save(stage / 'terrain.png')
        return {'test_render': True}

    monkeypatch.setattr(delivery, 'render_figures', render_stub)
    output = delivery.generate(tmp_path / 'run', source=source, expected_identity=base.identity,
                               expected_sha256=source_hash, spacing_m=5000., gallery=tmp_path / 'gallery')
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    product = load_product(output / 'product.npz', expected_identity=manifest['identity'])
    assert manifest['world_seed'] == 20260903
    assert manifest['base_world_seed'] == 20261020
    assert manifest['base_source']['identity'] == base.identity
    assert manifest['td_binding'] is None
    assert manifest['checks']['ocean_elevation_max_abs_change_m'] == 0
    assert manifest['checks']['source_unchanged']
    assert delivery.digest(source) == source_hash
    for key, record in manifest['arrays'].items():
        assert np.array_equal(np.load(output / record['file']), product.arrays[key])
        assert record['sha256'] == delivery.digest(output / record['file'])
    for key, record in manifest['height_images'].items():
        with Image.open(output / record['file']) as image:
            assert np.array_equal(np.asarray(image), delivery.encode_height(product.arrays[key]))
    gallery = json.loads((tmp_path / 'gallery/gallery-manifest.json').read_text(encoding='utf-8'))
    assert gallery['copy_checks_passed']
    for name, sha in gallery['copies_sha256'].items():
        assert delivery.digest(tmp_path / 'gallery' / name) == sha
    with pytest.raises(FileExistsError):
        delivery.generate(output, source=source)
    with pytest.raises(FileExistsError):
        delivery.copy_gallery(output, tmp_path / 'gallery')


def test_bad_source_sha_does_not_publish(tmp_path):
    source = tmp_path / 'base.npz'
    source.write_bytes(b'not the declared source')
    with pytest.raises(ValueError, match='SHA256'):
        delivery.generate(tmp_path / 'run', source=source)
    assert not (tmp_path / 'run').exists()


def test_existing_output_is_checked_before_source_access(tmp_path):
    target = tmp_path / 'run'
    target.mkdir()
    (target / 'marker').write_text('preserve')
    with pytest.raises(FileExistsError):
        delivery.generate(target, source=tmp_path / 'missing.npz')
    assert (target / 'marker').read_text() == 'preserve'
