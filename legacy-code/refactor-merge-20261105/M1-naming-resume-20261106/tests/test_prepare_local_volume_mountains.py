import json
import numpy as np
from PIL import Image
import pytest

from tools.prepare_local_volume_mountains import LOW, HIGH, decode_height, encode_height, generate, save_height


def test_mapping_png_and_saturation(tmp_path):
    values = np.array([[LOW-1, LOW, 200., HIGH, HIGH+1]])
    path = tmp_path / 'height.png'
    info = save_height(path, values)
    with Image.open(path) as image:
        actual = np.asarray(image)
    assert np.array_equal(actual, encode_height(values))
    assert np.max(np.abs(decode_height(actual[:, 1:4])-values[:, 1:4])) <= (HIGH-LOW)/65535/2 + 1e-10
    assert info['saturated_below_count'] == info['saturated_above_count'] == 1
    assert Image.open(tmp_path / 'height_preview.png').mode == 'L'


def test_existing_output_is_preserved(tmp_path):
    target = tmp_path / 'run'
    target.mkdir()
    (target / 'marker').write_text('keep')
    with pytest.raises(FileExistsError):
        generate(target, 3, 200.)
    assert (target / 'marker').read_text() == 'keep'


def test_manifest_arrays_and_png(tmp_path, monkeypatch):
    import tools.prepare_local_volume_mountains as delivery
    monkeypatch.setattr(delivery, 'render', lambda *args: None)
    target = generate(tmp_path / 'run', 3, 200.)
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert [c['name'] for c in manifest['cases']] == ['main_control', 'main_deep_only', 'main_local_only', 'main_combined', 'negative_combined']
    for case in manifest['cases']:
        with np.load(target / case['npz']) as fields:
            assert fields['height_m'].dtype == np.float64
            actual = np.asarray(Image.open(target / case['height_images']['height_m']['file']))
            assert np.array_equal(actual, encode_height(fields['height_m']))
        assert delivery.digest(target / case['npz']) == case['npz_sha256']
