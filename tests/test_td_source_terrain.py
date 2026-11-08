import json
from pathlib import Path

import numpy as np
import pytest

from terrain_pipeline import td_source as terrain


def test_published_v2_manifest_cold_read():
    path = Path(__file__).resolve().parents[1] / ".scratch/river-upgrade-20261101/terrain-v2"
    if not path.exists():
        pytest.skip("historical saved product is not present")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["algorithm_sha256"] == "dfa8195c2f7267f200b54ae56bce4afb3c873709e365790de7f59a094d55cd11"
    result, _ = terrain.read_world_terrain(path, expected_identity="544ced61ff6efd7ab421a7c23633221a332faa9647c45416d0fd2589f8266e43")
    assert result == manifest


@pytest.fixture
def parent_data(tmp_path, monkeypatch):
    raw = np.ones((405, 405), np.float32)
    raw[200, 200:405] = -1
    raw[201, 202] = -1
    raw[100, 100] = -1
    raw[0:3, 50] = -1
    source = {"raw_td": raw, "macro": -np.ones_like(raw),
              "td_climate": np.zeros((5, 405, 405), np.float32)}
    parent = {"coastal": True, "origin_native_xz": [10, 20],
              "bed_origin_native_xz": [106, 116], "anchor_bed_zx": [104, 104],
              "source_shape_zx": [405, 405], "world_seed": 20261020,
              "spacing_m": 30, "sea_m": 0, "plate_identity": "b" * 64}
    def read(path, expected_identity):
        if expected_identity != "a" * 64 or not (Path(path) / "intact").exists():
            raise ValueError("wrong or damaged source")
        return parent, source
    monkeypatch.setattr(terrain.plate_td_product, "read_plate_source", read)
    source_path = tmp_path / "source"
    source_path.mkdir()
    (source_path / "intact").touch()
    return parent, source, source_path


def test_anchor_classification_and_readonly_windows(parent_data):
    parent, source, _ = parent_data
    arrays = terrain._derive(parent, source)
    assert arrays["ocean_mask"][200, 300]
    assert arrays["closed_below_sea_mask"][100, 100]  # macro is ocean everywhere
    assert arrays["unknown_mask"][0, 50]
    manifest = {"origin_native_xz": [10, 20], "shape_zx": [405, 405],
                "identity": "i", "source_identity": "s"}
    _, window = terrain.query_world_terrain((manifest, arrays), (300, 219), (3, 20))
    assert all(not a.flags.writeable for a in window.values())
    assert window["ocean_mask"][1, 10]
    with pytest.raises(ValueError):
        terrain.query_world_terrain((manifest, arrays), (10.5, 20), (1, 1))
    with pytest.raises(ValueError):
        terrain.query_world_terrain((manifest, arrays), (415, 20), (1, 1))
    source["raw_td"][200, 200] = 1
    dry = terrain._derive(parent, source)
    assert not dry["ocean_mask"].any()
    assert dry["unknown_mask"][200, 300]
    assert dry["closed_below_sea_mask"][100, 100]


def test_prepare_and_parent_revalidation(tmp_path, parent_data):
    parent, source, source_path = parent_data
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        terrain.prepare_world_terrain(source_path, out, expected_source_identity="c" * 64)
    manifest, arrays = terrain.prepare_world_terrain(source_path, out, expected_source_identity="a" * 64)
    assert manifest["world_seed"] == 20261020
    assert all(not a.flags.writeable for a in arrays.values())
    with pytest.raises(ValueError):
        terrain.read_world_terrain(out, expected_identity="c" * 64)
    with pytest.raises(FileExistsError):
        terrain.prepare_world_terrain(source_path, out, expected_source_identity="a" * 64)
    source["td_climate"][0, 0, 0] = 1
    with pytest.raises(ValueError, match="derivation"):
        terrain.read_world_terrain(out)
    source["td_climate"][0, 0, 0] = 0
    parent["origin_native_xz"] = [11, 20]
    with pytest.raises(ValueError, match="metadata"):
        terrain.read_world_terrain(out)
    parent["origin_native_xz"] = [10, 20]
    (source_path / "intact").unlink()
    with pytest.raises(ValueError, match="damaged"):
        terrain.read_world_terrain(out)


def test_rehashed_forgery_and_metadata_rejected(tmp_path, parent_data):
    _, _, source_path = parent_data
    out = tmp_path / "out"
    terrain.prepare_world_terrain(source_path, out, expected_source_identity="a" * 64)
    path = out / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    ocean = np.load(out / "ocean_mask.npy")
    ocean[100, 100] = True
    np.save(out / "ocean_mask.npy", ocean)
    manifest["files"]["ocean_mask"] = terrain.plate_td_product.digest(out / "ocean_mask.npy")
    manifest["identity"] = terrain._identity({k: v for k, v in manifest.items() if k != "identity"})
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="derivation"):
        terrain.read_world_terrain(out)
    manifest["world_seed"] = 1
    manifest["identity"] = terrain._identity({k: v for k, v in manifest.items() if k != "identity"})
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="contract"):
        terrain.read_world_terrain(out)
