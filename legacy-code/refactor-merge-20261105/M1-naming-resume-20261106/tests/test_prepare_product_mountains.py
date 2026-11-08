from pathlib import Path
import numpy as np
from PIL import Image
import pytest

from tools.prepare_product_mountains import LOW, HIGH, decode_height, encode_height, generate, save_height


def test_fixed_mapping_and_round_trip(tmp_path):
    values = np.array([[LOW, 0., 200., HIGH, LOW - 1, HIGH + 1]])
    path = tmp_path / 'height.png'
    info = save_height(path, values)
    with Image.open(path) as image:
        assert image.mode in ('I;16', 'I')
        assert image.getextrema() == (0, 65535)
        actual = np.asarray(image)
    assert np.array_equal(actual, encode_height(values))
    assert np.max(np.abs(decode_height(actual[:, :4]) - values[:, :4])) <= (HIGH - LOW) / 65535 / 2 + 1e-10
    assert info['saturated_below_count'] == info['saturated_above_count'] == 1
    assert Image.open(tmp_path / 'height_preview.png').mode == 'L'
    assert encode_height(np.array([200.]))[0] == encode_height(np.array([-500., 200., 4500.]))[1]


def test_output_never_overwrites(tmp_path):
    existing = tmp_path / 'run'
    existing.mkdir()
    marker = existing / 'marker'
    marker.write_text('keep')
    with pytest.raises(FileExistsError):
        generate(existing, 2, 200.)
    assert marker.read_text() == 'keep'


def test_output_identity_and_truth(tmp_path, monkeypatch):
    import json
    import tools.prepare_product_mountains as delivery

    def fake_render(path, cases, spacing):
        path.write_bytes(b'comparison')
        path.with_name(path.stem + '_terrain.png').write_bytes(b'terrain')

    monkeypatch.setattr(delivery, 'render', fake_render)
    target = generate(tmp_path / 'fresh', 3, 200.)
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['cases']) == 4
    assert manifest['cases'][0]['origin_xz_m'] == [0.0, 0.0]
    assert manifest['cases'][-1]['origin_xz_m'] == [-24000.0, -24000.0]
    for case in manifest['cases']:
        truth = np.load(target / case['npz'])
        assert truth['height_m'].dtype == np.float64
        image = np.asarray(Image.open(target / case['height_images']['height_m']['file']))
        assert np.array_equal(image, encode_height(truth['height_m']))
        assert case['npz_sha256'] == delivery.digest(target / case['npz'])
