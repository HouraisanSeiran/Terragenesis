import json

import numpy as np
import pytest

from terrain_pipeline import td_source as mosaic
from terrain_pipeline import td_source as terrain


def test_classification_four_neighbour_and_boundary_condition():
    raw = np.ones((6, 6), np.float32)
    raw[0:2, 0] = -1
    raw[2, 1] = -1  # diagonal only
    raw[5, 5] = -1
    evidence = np.ones_like(raw, bool)
    evidence[5, 5] = False
    ocean, closed, unknown = mosaic.classify_boundary_ocean(raw, evidence)
    assert ocean[0, 0] and closed[2, 1] and unknown[5, 5]


def test_resume_publish_cold_read_owner_seams_and_corruption(tmp_path, monkeypatch):
    pages = tmp_path / "pages"
    calls = []
    def prepare(source, path, origin, side, config, **kwargs):
        calls.append(origin)
        path.mkdir()
        x = np.arange(origin[0], origin[0] + side)[None, :]
        z = np.arange(origin[1], origin[1] + side)[:, None]
        raw = (x + 10 * z).astype(np.float32)
        np.save(path / "raw_td.npy", raw)
        np.save(path / "td_climate.npy", np.stack([raw] * 5))
        (path / "origin.json").write_text(json.dumps(origin), encoding="utf-8")
    def read(path, expected_identity=None):
        path = __import__("pathlib").Path(path)
        origin = json.loads((path / "origin.json").read_text(encoding="utf-8"))
        raw = np.load(path / "raw_td.npy", mmap_mode="r")
        climate = np.load(path / "td_climate.npy", mmap_mode="r")
        files = {n: mosaic.plate_td_product.digest(path / (n + ".npy")) for n in ("raw_td", "td_climate")}
        identity = mosaic.mosaic_identity({"origin": origin, "files": files})
        return {"identity": identity, "files": files, "plate_identity": mosaic.PLATE_IDENTITY,
                "world_seed": mosaic.WORLD_SEED, "origin_native_xz": origin,
                "source_shape_zx": list(raw.shape), "coastal": False, "spacing_m": 30, "sea_m": 0}, {"raw_td": raw, "td_climate": climate}
    monkeypatch.setattr(mosaic.plate_td_product, "prepare_plate_source", prepare)
    monkeypatch.setattr(mosaic.plate_td_product, "read_plate_source", read)
    mosaic.prepare_mosaic_pages(pages, core=4, halo=1, indices=range(2), generate=True)
    assert len(calls) == 4
    # A neighbor's halo can disagree without changing either fixed owner core.
    halo_path = pages / mosaic.page_name(1, 0) / "raw_td.npy"
    halo_data = np.load(halo_path)
    halo_data[:, 0] += 0.5
    np.save(halo_path, halo_data)
    mosaic.prepare_mosaic_pages(pages, core=4, halo=1, indices=range(2), generate=True)
    assert len(calls) == 4
    class Plate:
        manifest = {"config": {"world_seed": mosaic.WORLD_SEED}}
        def sample(self, x, z, outside):
            return {"ocean_connected": np.ones(np.broadcast_arrays(x, z)[0].shape, bool)}
    monkeypatch.setattr(mosaic, "load_product", lambda *args, **kwargs: Plate())
    broken_output = tmp_path / "broken"
    original_page = mosaic._page
    def fail_page(path, origin, side, plate_identity):
        if origin == [3, -1]:
            raise InterruptedError("cancelled during assembly")
        return original_page(path, origin, side, plate_identity)
    monkeypatch.setattr(mosaic, "_page", fail_page)
    with pytest.raises(InterruptedError):
        mosaic.assemble(pages, broken_output, core=4, halo=1, indices=range(2))
    assert not broken_output.exists()
    assert not list(tmp_path.glob(".mosaic-stage-*"))
    monkeypatch.setattr(mosaic, "_page", original_page)
    out = tmp_path / "mosaic"
    m, arrays = mosaic.assemble(pages, out, core=4, halo=1, indices=range(2))
    assert arrays["raw_td"][4, 4] == 44
    assert any(s["overlap_max_abs_m"] == 0.5 for s in mosaic.seam_report(out))
    terrain_path = tmp_path / "terrain"
    tm, ta = terrain.prepare_world_terrain(out, terrain_path, expected_source_identity=m["identity"])
    cold, _ = terrain.read_world_terrain(terrain_path, expected_identity=tm["identity"])
    assert cold["source_schema"] == mosaic.MOSAIC_SCHEMA
    _, window = terrain.query_world_terrain((tm, ta), [3, 3], [2, 2])
    assert window["raw_td_m"][1, 1] == 44
    assert not window["raw_td_m"].flags.writeable
    with pytest.raises(ValueError):
        mosaic.read_mosaic_product(out, "f" * 64)
    with pytest.raises(FileExistsError):
        mosaic.assemble(pages, out, core=4, halo=1, indices=range(2))
    page = pages / mosaic.page_name(0, 0) / "raw_td.npy"
    changed = np.load(page)
    changed[1, 1] += 1
    np.save(page, changed)
    with pytest.raises(ValueError, match="page identity"):
        mosaic.read_mosaic_product(out)
    assert m["identity"]


def test_interrupted_pages_resume_without_replacing_success(tmp_path, monkeypatch):
    calls = []
    def prepare(source, path, origin, side, config, **kwargs):
        calls.append(tuple(origin))
        if len(calls) == 2:
            raise InterruptedError("cancelled")
        path.mkdir()
        (path / "origin.json").write_text(json.dumps(origin), encoding="utf-8")
    def check(path, origin, side, plate):
        assert json.loads((path / "origin.json").read_text(encoding="utf-8")) == origin
        return {}, {}
    monkeypatch.setattr(mosaic.plate_td_product, "prepare_plate_source", prepare)
    monkeypatch.setattr(mosaic, "_page", check)
    pages = tmp_path / "pages"
    with pytest.raises(InterruptedError):
        mosaic.prepare_mosaic_pages(pages, core=4, halo=1, indices=range(2), generate=True)
    mosaic.prepare_mosaic_pages(pages, core=4, halo=1, indices=range(2), generate=True)
    assert calls.count((-1, -1)) == 1
    assert len(list(pages.iterdir())) == 4
