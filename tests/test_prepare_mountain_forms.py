"""Consolidated tests.test_prepare_mountain_forms implementations; numeric expressions preserved."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json as _i28_json
import numpy as _i28_np
from PIL import Image as _i28_Image
import pytest as _i28_pytest
import tools.prepare_mountain_forms as _patch_prepare_plot_results_skeleton
import tools.prepare_mountain_forms as _patch_prepare_plot_sections
import tools.prepare_mountain_forms as _patch_prepare_sample_skeleton
import json as _i29_json
import numpy as _i29_np
from PIL import Image as _i29_Image
import pytest as _i29_pytest
import tools.prepare_mountain_forms as _patch_delivery_render_local_volume
from pathlib import Path as _i30_Path
import numpy as _i30_np
from PIL import Image as _i30_Image
import pytest as _i30_pytest
import tools.prepare_mountain_forms as _patch_delivery_render_product
import hashlib as _i31_hashlib
import json as _i31_json
from pathlib import Path as _i31_Path
import subprocess as _i31_subprocess
import sys as _i31_sys
import numpy as _i31_np
import numpy as _i32_np
import pytest as _i32_pytest
from terrain_pipeline.mountain_forms import VoronoiConfig as _i32_VoronoiConfig
from terrain_pipeline.mountain_forms import rasterize_voronoi as _i32_rasterize
import numpy as _i33_np
import pytest as _i33_pytest
from tools.prepare_ridge_breakup import generate as _i33_generate
from tools.prepare_ridge_breakup import metrics as _i33_metrics
import json as _i34_json
import numpy as _i34_np
from PIL import Image as _i34_Image
import pytest as _i34_pytest
from terrain_pipeline.tectonic import TectonicConfig as _i34_TectonicConfig
from terrain_pipeline.tectonic import evolve as _i34_evolve
from terrain_pipeline.tectonic import freeze as _i34_freeze
from terrain_pipeline.tectonic import save_product as _i34_save_base
from terrain_pipeline.mountain_forms import load_belt_product as _i34_load_product
from tools import prepare_mountain_belts as _i34_delivery
from tools.prepare_mountain_forms import LOW as _x0_LOW
from tools.prepare_mountain_forms import HIGH as _x1_HIGH
from tools.prepare_mountain_forms import decode_height as _x2_decode_height
from tools.prepare_mountain_forms import encode_height as _x3_encode_height
from tools.prepare_mountain_forms import generate_local_volume as _x4_generate_local_volume
from tools.prepare_mountain_forms import save_height as _x5_save_height
from tools.prepare_mountain_forms import PREPARE_PRODUCT_MOUNTAINS_LOW as _x6_PREPARE_PRODUCT_MOUNTAINS_LOW
from tools.prepare_mountain_forms import PREPARE_PRODUCT_MOUNTAINS_HIGH as _x7_PREPARE_PRODUCT_MOUNTAINS_HIGH
from tools.prepare_mountain_forms import prepare_product_mountains_decode_height as _x8_prepare_product_mountains_decode_height
from tools.prepare_mountain_forms import prepare_product_mountains_encode_height as _x9_prepare_product_mountains_encode_height
from tools.prepare_mountain_forms import generate_product as _x10_generate_product
from tools.prepare_mountain_forms import prepare_product_mountains_save_height as _x11_prepare_product_mountains_save_height
from tools.prepare_mountain_forms import generate_voronoi as _x12_generate_voronoi
from tools.prepare_mountain_forms import routing as _x13_routing
from tools.prepare_mountain_forms import generate_skeleton as _x14_generate_skeleton
from tools.prepare_mountain_forms import digest as _x15_digest
from terrain_pipeline.mountain_forms import LocalVolumeConfig as _x16_LocalVolumeConfig
from terrain_pipeline.skeleton_mountains import SkeletonMountainConfig as _x17_SkeletonMountainConfig
from tools.prepare_mountain_forms import sample_skeleton as _x18_sample_skeleton

CATEGORY = 'B'

# Source: tests.test_prepare_skeleton_mountains
def test_export_real_arrays_gray_depth_hashes_and_refuse_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(_patch_prepare_plot_results_skeleton, 'plot_results_skeleton', lambda *args: None)
    monkeypatch.setattr(_patch_prepare_plot_sections, 'plot_sections', lambda *args: None)
    out = tmp_path / 'height-evidence'
    _x14_generate_skeleton(out, size=17, spacing=1500.0)
    manifest = _i28_json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['world_seed'] == 20260903
    assert len(manifest['cases']) == 7
    for item in manifest['cases']:
        with _i28_np.load(out / item['npz']) as saved:
            fields = dict(saved)
        for key, image in item['height_images'].items():
            path = out / image['file']
            assert path.read_bytes()[24:26] == bytes([16, 0])
            with _i28_Image.open(path) as png:
                decoded = -500 + _i28_np.asarray(png, dtype=_i28_np.float64) * 6500 / 65535
            assert _i28_np.max(_i28_np.abs(decoded - fields[key])) <= 6500 / 65535 / 2 + 1e-10
            assert _x15_digest(path) == image['sha256']
        x, z = item['origin_xz_m']
        config_class = _x16_LocalVolumeConfig if item['name'] == 'main_previous' else _x17_SkeletonMountainConfig
        fresh = _x18_sample_skeleton(config_class(**item['config']), x + 7500.0, z + 9000.0)
        assert fields['height_m'][6, 5] == fresh['height_m']
    before = _x15_digest(out / 'manifest.json')
    with _i28_pytest.raises(FileExistsError):
        _x14_generate_skeleton(out, size=17, spacing=1500.0)
    assert before == _x15_digest(out / 'manifest.json')

# Source: tests.test_prepare_skeleton_mountains
def test_failed_generation_never_publishes_partial_target(tmp_path, monkeypatch):

    def fail(*args):
        raise RuntimeError('injected generation failure')
    monkeypatch.setattr(_patch_prepare_sample_skeleton, 'sample_skeleton', fail)
    with _i28_pytest.raises(RuntimeError, match='injected'):
        _x14_generate_skeleton(tmp_path / 'failed')
    assert list(tmp_path.iterdir()) == []
    with _i28_pytest.raises(ValueError):
        _x14_generate_skeleton(tmp_path / 'invalid', size=0)
    assert list(tmp_path.iterdir()) == []

# Source: tests.test_prepare_local_volume_mountains
def test_mapping_png_and_saturation(tmp_path):
    values = _i29_np.array([[_x0_LOW - 1, _x0_LOW, 200.0, _x1_HIGH, _x1_HIGH + 1]])
    path = tmp_path / 'height.png'
    info = _x5_save_height(path, values)
    with _i29_Image.open(path) as image:
        actual = _i29_np.asarray(image)
    assert _i29_np.array_equal(actual, _x3_encode_height(values))
    assert _i29_np.max(_i29_np.abs(_x2_decode_height(actual[:, 1:4]) - values[:, 1:4])) <= (_x1_HIGH - _x0_LOW) / 65535 / 2 + 1e-10
    assert info['saturated_below_count'] == info['saturated_above_count'] == 1
    assert _i29_Image.open(tmp_path / 'height_preview.png').mode == 'L'

# Source: tests.test_prepare_local_volume_mountains
def test_existing_output_is_preserved(tmp_path):
    target = tmp_path / 'run'
    target.mkdir()
    (target / 'marker').write_text('keep')
    with _i29_pytest.raises(FileExistsError):
        _x4_generate_local_volume(target, 3, 200.0)
    assert (target / 'marker').read_text() == 'keep'

# Source: tests.test_prepare_local_volume_mountains
def test_manifest_arrays_and_png(tmp_path, monkeypatch):
    import tools.prepare_mountain_forms as delivery
    monkeypatch.setattr(_patch_delivery_render_local_volume, 'render_local_volume', lambda *args: None)
    target = _x4_generate_local_volume(tmp_path / 'run', 3, 200.0)
    manifest = _i29_json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert [c['name'] for c in manifest['cases']] == ['main_control', 'main_deep_only', 'main_local_only', 'main_combined', 'negative_combined']
    for case in manifest['cases']:
        with _i29_np.load(target / case['npz']) as fields:
            assert fields['height_m'].dtype == _i29_np.float64
            actual = _i29_np.asarray(_i29_Image.open(target / case['height_images']['height_m']['file']))
            assert _i29_np.array_equal(actual, _x3_encode_height(fields['height_m']))
        assert delivery.digest(target / case['npz']) == case['npz_sha256']

# Source: tests.test_prepare_product_mountains
def test_fixed_mapping_and_round_trip(tmp_path):
    values = _i30_np.array([[_x6_PREPARE_PRODUCT_MOUNTAINS_LOW, 0.0, 200.0, _x7_PREPARE_PRODUCT_MOUNTAINS_HIGH, _x6_PREPARE_PRODUCT_MOUNTAINS_LOW - 1, _x7_PREPARE_PRODUCT_MOUNTAINS_HIGH + 1]])
    path = tmp_path / 'height.png'
    info = _x11_prepare_product_mountains_save_height(path, values)
    with _i30_Image.open(path) as image:
        assert image.mode in ('I;16', 'I')
        assert image.getextrema() == (0, 65535)
        actual = _i30_np.asarray(image)
    assert _i30_np.array_equal(actual, _x9_prepare_product_mountains_encode_height(values))
    assert _i30_np.max(_i30_np.abs(_x8_prepare_product_mountains_decode_height(actual[:, :4]) - values[:, :4])) <= (_x7_PREPARE_PRODUCT_MOUNTAINS_HIGH - _x6_PREPARE_PRODUCT_MOUNTAINS_LOW) / 65535 / 2 + 1e-10
    assert info['saturated_below_count'] == info['saturated_above_count'] == 1
    assert _i30_Image.open(tmp_path / 'height_preview.png').mode == 'L'
    assert _x9_prepare_product_mountains_encode_height(_i30_np.array([200.0]))[0] == _x9_prepare_product_mountains_encode_height(_i30_np.array([-500.0, 200.0, 4500.0]))[1]

# Source: tests.test_prepare_product_mountains
def test_output_never_overwrites(tmp_path):
    existing = tmp_path / 'run'
    existing.mkdir()
    marker = existing / 'marker'
    marker.write_text('keep')
    with _i30_pytest.raises(FileExistsError):
        _x10_generate_product(existing, 2, 200.0)
    assert marker.read_text() == 'keep'

# Source: tests.test_prepare_product_mountains
def test_output_identity_and_truth(tmp_path, monkeypatch):
    import json
    import tools.prepare_mountain_forms as delivery

    def fake_render(path, cases, spacing):
        path.write_bytes(b'comparison')
        path.with_name(path.stem + '_terrain.png').write_bytes(b'terrain')
    monkeypatch.setattr(_patch_delivery_render_product, 'render_product', fake_render)
    target = _x10_generate_product(tmp_path / 'fresh', 3, 200.0)
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['cases']) == 4
    assert manifest['cases'][0]['origin_xz_m'] == [0.0, 0.0]
    assert manifest['cases'][-1]['origin_xz_m'] == [-24000.0, -24000.0]
    for case in manifest['cases']:
        truth = _i30_np.load(target / case['npz'])
        assert truth['height_m'].dtype == _i30_np.float64
        image = _i30_np.asarray(_i30_Image.open(target / case['height_images']['height_m']['file']))
        assert _i30_np.array_equal(image, _x9_prepare_product_mountains_encode_height(truth['height_m']))
        assert case['npz_sha256'] == delivery.digest(target / case['npz'])

# Source: tests.test_prepare_procedural_mountains
ROOT = _i31_Path(__file__).resolve().parents[1]

# Source: tests.test_prepare_procedural_mountains
SCRIPT = ROOT / 'tools' / 'prepare_mountain_forms.py'

# Source: tests.test_prepare_procedural_mountains
def run_cli(*args):
    return _i31_subprocess.run([_i31_sys.executable, '-B', '-X', 'utf8', str(SCRIPT), "procedural", *map(str, args)], cwd=ROOT, capture_output=True, text=True)

# Source: tests.test_prepare_procedural_mountains
def test_invalid_size_refuses_without_output(tmp_path):
    out = tmp_path / 'invalid'
    result = run_cli('--output-dir', out, '--size', '2')
    assert result.returncode != 0
    assert not out.exists()

# Source: tests.test_prepare_procedural_mountains
def test_saved_output_roundtrip_and_no_overwrite(tmp_path):
    out = tmp_path / 'run'
    args = ('--output-dir', out, '--size', '9', '--benchmark-sizes', '4')
    result = run_cli(*args)
    assert result.returncode == 0, result.stderr
    manifest = _i31_json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    record = manifest['rasters'][0]
    path = out / record['file']
    assert _i31_hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256']
    with _i31_np.load(path, allow_pickle=False) as data:
        assert data['height_m'].shape == (9, 9)
        _i31_np.testing.assert_allclose(data['height_m'], data['advanced_base_m'] + data['regional_noise_delta_m'])
        assert data['base_noise_m'].shape == (9, 9)
        metadata = _i31_json.loads(str(data['metadata_json']))
        assert metadata['source_family'] == 'independent_procedural_mountains'
        assert metadata['spacing_m'] == 60.0
    assert all((item['nonblank'] for item in manifest['images'].values()))
    before = (out / 'manifest.json').read_bytes()
    assert run_cli(*args).returncode != 0
    assert (out / 'manifest.json').read_bytes() == before

# Source: tests.test_prepare_voronoi_mountains
def test_routing_reports_real_three_field_comparison():
    fields = _i32_rasterize((0.0, 0.0), (17, 17), 375.0, _i32_VoronoiConfig())
    report, arrays = _x13_routing(fields, (0.0, 0.0), 375.0, 20260903)
    assert report['protection']['core_fraction'] > 0
    assert report['protection']['core_max_abs_error_m'] == 0
    assert report['protection']['outside_mean_abs_change_m'] > 0
    assert all((abs(report[key]['residual_m3_s']) < 1e-10 for key in ('advanced_base_m', 'unprotected_height_m', 'height_m')))
    assert arrays['height_m_terminal'].shape == (17 * 17,)
    assert _i32_np.isfinite(arrays['height_m_routed_q_m3_s']).all()

# Source: tests.test_prepare_voronoi_mountains
def test_existing_output_is_never_overwritten(tmp_path):
    target = tmp_path / 'existing'
    target.mkdir()
    marker = target / 'keep'
    marker.write_text('keep')
    with _i32_pytest.raises(FileExistsError):
        _x12_generate_voronoi(target)
    assert marker.read_text() == 'keep'

# Source: tests.test_prepare_ridge_breakup
def test_metrics_show_constant_structure_has_no_gradient():
    fields = {name: _i33_np.ones((5, 5)) for name in ('original_delta_m', 'gaussian_delta_m', 'breakup_delta_m', 'final_delta_m', 'gap_field')}
    fields['metadata'] = {'config': {'gap_strength': 0.65}}
    fields['ridge_retention'] = _i33_np.ones((5, 5))
    fields['warped_delta_m'] = _i33_np.ones((5, 5))
    result = _i33_metrics(fields, 120.0)
    assert result['gaussian']['mean_abs_change_from_original_m'] == 0
    assert result['gaussian']['gradient_energy'] == 0

# Source: tests.test_prepare_ridge_breakup
def test_existing_destination_is_preserved(tmp_path):
    target = tmp_path / 'output'
    target.mkdir()
    (target / 'keep').write_text('keep')
    with _i33_pytest.raises(FileExistsError):
        _i33_generate(target)
    assert (target / 'keep').read_text() == 'keep'

# Source: tests.test_prepare_world_mountain_belts
def test_height_png_has_one_fixed_mapping_and_exact_readback(tmp_path):
    height = _i34_np.array([[_i34_delivery.LOW, -3200.0, 0.0, 900.0, _i34_delivery.HIGH], [_i34_delivery.LOW - 1.0, 100.0, 4000.0, 9000.0, _i34_delivery.HIGH + 1.0]])
    info = _i34_delivery.export_height(tmp_path / 'height.png', height)
    with _i34_Image.open(tmp_path / 'height.png') as image:
        codes = _i34_np.asarray(image)
        assert image.mode in ('I;16', 'I')
    assert _i34_np.array_equal(codes, _i34_delivery.encode_height(height))
    in_range = (height >= _i34_delivery.LOW) & (height <= _i34_delivery.HIGH)
    error = _i34_delivery.decode_height(codes) - height
    assert _i34_np.max(_i34_np.abs(error[in_range])) <= (_i34_delivery.HIGH - _i34_delivery.LOW) / 65535 / 2 + 1e-10
    assert info['saturated_below_count'] == info['saturated_above_count'] == 1
    assert info['png_readback_equal']
    assert _i34_delivery.encode_height(_i34_np.array([[900.0]]))[0, 0] == codes[0, 3]
    with _i34_pytest.raises(ValueError):
        _i34_delivery.encode_height(_i34_np.array([[_i34_np.nan]]))

# Source: tests.test_prepare_world_mountain_belts
def test_export_keeps_source_seeds_cold_arrays_and_gallery(tmp_path, monkeypatch):
    config = _i34_TectonicConfig(shape=(12, 16), plate_count=4, steps=2, origin_x_m=-80000.0, origin_z_m=-60000.0)
    base = _i34_freeze(config, _i34_evolve(config))
    source = tmp_path / 'base.npz'
    _i34_save_base(base, source)
    source_hash = _i34_delivery.digest(source)

    def render_stub(product, stage):
        _i34_Image.fromarray(_i34_delivery.encode_height(product.arrays['elevation_m'])).save(stage / 'terrain.png')
        return {'test_render': True}
    monkeypatch.setattr(_i34_delivery, 'render_figures', render_stub)
    output = _i34_delivery.generate(tmp_path / 'run', source=source, expected_identity=base.identity, expected_sha256=source_hash, spacing_m=5000.0, gallery=tmp_path / 'gallery')
    manifest = _i34_json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    product = _i34_load_product(output / 'product.npz', expected_identity=manifest['identity'])
    assert manifest['world_seed'] == 20260903
    assert manifest['base_world_seed'] == 20261020
    assert manifest['base_source']['identity'] == base.identity
    assert manifest['td_binding'] is None
    assert manifest['checks']['ocean_elevation_max_abs_change_m'] == 0
    assert manifest['checks']['source_unchanged']
    assert _i34_delivery.digest(source) == source_hash
    for key, record in manifest['arrays'].items():
        assert _i34_np.array_equal(_i34_np.load(output / record['file']), product.arrays[key])
        assert record['sha256'] == _i34_delivery.digest(output / record['file'])
    for key, record in manifest['height_images'].items():
        with _i34_Image.open(output / record['file']) as image:
            assert _i34_np.array_equal(_i34_np.asarray(image), _i34_delivery.encode_height(product.arrays[key]))
    gallery = _i34_json.loads((tmp_path / 'gallery/gallery-manifest.json').read_text(encoding='utf-8'))
    assert gallery['copy_checks_passed']
    for name, sha in gallery['copies_sha256'].items():
        assert _i34_delivery.digest(tmp_path / 'gallery' / name) == sha
    with _i34_pytest.raises(FileExistsError):
        _i34_delivery.generate(output, source=source)
    with _i34_pytest.raises(FileExistsError):
        _i34_delivery.copy_gallery(output, tmp_path / 'gallery')

# Source: tests.test_prepare_world_mountain_belts
def test_bad_source_sha_does_not_publish(tmp_path):
    source = tmp_path / 'base.npz'
    source.write_bytes(b'not the declared source')
    with _i34_pytest.raises(ValueError, match='SHA256'):
        _i34_delivery.generate(tmp_path / 'run', source=source)
    assert not (tmp_path / 'run').exists()

# Source: tests.test_prepare_world_mountain_belts
def test_existing_output_is_checked_before_source_access(tmp_path):
    target = tmp_path / 'run'
    target.mkdir()
    (target / 'marker').write_text('preserve')
    with _i34_pytest.raises(FileExistsError):
        _i34_delivery.generate(target, source=tmp_path / 'missing.npz')
    assert (target / 'marker').read_text() == 'preserve'
