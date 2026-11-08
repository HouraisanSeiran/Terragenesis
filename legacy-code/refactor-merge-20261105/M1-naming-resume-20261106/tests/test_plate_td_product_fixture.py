"""Portable CPU unit products. Fake raw TD is never acceptance inference."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pytest

from diffusion.paths import ROOT
from diffusion.physical_config import PhysicalGenerationConfig
from diffusion.plate_td_conditioning import WORLD_SEED
from diffusion.world_layout_backend import BUDGETS
from terrain_pipeline import tectonic as td
from terrain_pipeline.coastal_terrain import relief
from terrain_pipeline.coastal_terrain import coastal_support, compose
from terrain_pipeline.tectonic import TectonicConfig, evolve
from terrain_pipeline.tectonic import freeze, save_product


def model_fixture(directory):
    directory.mkdir()
    (directory / "config.json").write_text(json.dumps({
        "native_resolution": 30, "latent_compression": 8}), encoding="utf-8")
    (directory / "unit-weights.bin").write_bytes(b"small unit fixture; never TD weights")
    files = {p.name: {"bytes": p.stat().st_size, "sha256": td.digest(p)}
             for p in directory.iterdir()}
    (directory / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")
    return PhysicalGenerationConfig(model_dir=str(directory.relative_to(ROOT)))


def fake_td(source, origin, side, config, *, expected_identity):
    identity, metadata = config.generation_identity()
    files = [ROOT / "diffusion" / name for name in
             ("plate_td_backend.py", "plate_td_conditioning.py", "geographic_noise.py")]
    files += [ROOT / "terrain_pipeline" / name for name in
              ("tectonic.py", "coastal_terrain.py")]
    generation = {"record": {"source": str(Path(source).resolve()),
                  "plate_identity": expected_identity, "seed": WORLD_SEED,
                  "origin": list(origin), "side": side, "config": config.record()},
                  "physical_generation_identity": identity, "physical_generation": metadata,
                  "source_sha256": {p.name: td.digest(p) for p in files},
                  "coordinates": "30m cell centres; x east, z south; arrays [z,x]; sea datum 0m",
                  "boundary": "finite reject; product bilinear interpolation wraps at edge",
                  "gpu_monitor": "allocator",
                  "gpu_scope": "PyTorch allocator only; excludes driver, non-PyTorch allocations and other processes",
                  "budgets": dict(BUDGETS, page_side_cells=side),
                  "wall_clock_s": 1., "peak_child_rss_mib": 12.,
                  "allocated_peak_mib": 0., "reserved_peak_mib": 0.}
    # Preserve frozen macro and add only a modest deterministic residual.
    product = td.load_product(source, expected_identity=expected_identity)
    macro = td._macro(product, origin, side)
    x = origin[0] + np.arange(side)[None, :]
    z = origin[1] + np.arange(side)[:, None]
    raw = (macro + 10 * np.sin(x / 17.) * np.cos(z / 23.)).astype(np.float32)
    return raw, np.zeros((5, side, side), np.float32), generation


@pytest.fixture(scope="module")
def frozen():
    config = TectonicConfig(shape=(12, 16), plate_count=4, steps=3,
                            origin_x_m=-80000., origin_z_m=-60000.)
    return freeze(config, evolve(config))


@pytest.fixture
def portable(frozen, monkeypatch):
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".unit-plate-") as directory:
        directory = Path(directory)
        source = directory / "source.npz"
        save_product(frozen, source)
        config = model_fixture(directory / "model")
        monkeypatch.setattr("diffusion.plate_td_backend.generate", fake_td)
        yield directory, source, config, frozen


def prepare_fixture(portable, name, origin, side=513, coastal=True, strength=.7):
    directory, source, config, frozen = portable
    output = directory / name
    td.prepare_plate_source(source, output, origin, side, config, compose_coast=coastal,
               expected_identity=frozen.identity, relief_strength=strength)
    return output


def locate(product, kind):
    # Select from macro alone, before fake TD generation. Keep the entire halo finite.
    for z in range(-1400, 1401, 100):
        for x in range(-2000, 2001, 100):
            origin = (x - 256, z - 256)
            xx = (origin[0] + np.arange(0, 513, 16))[None, :] * 30.
            zz = (origin[1] + np.arange(0, 513, 16))[:, None] * 30.
            sample = product.sample(xx, zz, outside="reject")
            elevation = sample["elevation_m"]
            if kind == "coast":
                core = elevation[13:20, 13:20]
                if core.min() < -10 and core.max() > 10 and sample["ocean_connected"][13:20, 13:20].any():
                    return origin
            elif kind == "sea" and elevation.max() < -100 and sample["ocean_connected"].all():
                return origin
            elif kind == "land" and elevation.min() > 100:
                return origin
    raise AssertionError("missing deterministic " + kind + " fixture")


def save_manifest(path, manifest):
    manifest["identity"] = td._identity({k: v for k, v in manifest.items() if k != "identity"})
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_cold_read_and_no_overwrite(portable):
    path = prepare_fixture(portable, "raw", (-10, -10), 16, False, 0.)
    manifest, arrays = td.read_plate_source(path)
    assert not arrays["raw_td"].flags.writeable
    code = "from terrain_pipeline.plate_td_product import read_product; import sys; m,a=read_product(sys.argv[1],sys.argv[2]); assert a['raw_td'].dtype.name=='float32'"
    subprocess.run([sys.executable, "-c", code, str(path), manifest["identity"]], check=True)
    before = (path / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare_fixture(portable, "raw", (-10, -10), 16, False, 0.)
    assert before == (path / "manifest.json").read_bytes()


def test_relocation_and_runtime_identity_stability(portable):
    directory, source, config, frozen = portable
    first = prepare_fixture(portable, "first", (-10, -10), 16, False, 0.)
    alternate = directory / "relocated-source"
    alternate.mkdir()
    relocated = alternate / "same.npz"
    shutil.copyfile(source, relocated)
    other_config = model_fixture(directory / "other-model")
    def delayed(*args, **kwargs):
        raw, climate, generation = fake_td(*args, **kwargs)
        generation.update(wall_clock_s=99., peak_child_rss_mib=222., allocated_peak_mib=10., reserved_peak_mib=20.)
        return raw, climate, generation
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("diffusion.plate_td_backend.generate", delayed)
        td.prepare_plate_source(relocated, directory / "second", (-10, -10), 16, other_config,
                   compose_coast=False, expected_identity=frozen.identity)
    a = td.read_plate_source(first)[0]
    b = td.read_plate_source(directory / "second")[0]
    assert a["generation"]["physical_generation_identity"] != b["generation"]["physical_generation_identity"]
    assert a["generation"]["physical_generation"]["conditioning_identity"] != b["generation"]["physical_generation"]["conditioning_identity"]
    assert a["identity"] == b["identity"]


@pytest.fixture
def coastal(portable):
    origin = locate(portable[3], "coast")
    return portable, prepare_fixture(portable, "coast", origin)


def test_composed_relief_zero_baseline_and_shifted_shared_support(coastal):
    portable, path = coastal
    manifest, arrays = td.read_plate_source(path)
    origin = manifest["origin_native_xz"]
    baseline_path = prepare_fixture(portable, "zero", origin, strength=0.)
    baseline_manifest, baseline = td.read_plate_source(baseline_path)
    macro = baseline["macro"]
    anchor = tuple(np.asarray(baseline_manifest["anchor_bed_zx"]) + 96)
    support = coastal_support(macro, anchors=[anchor])
    expected = compose(baseline["raw_td"], macro, support=support)
    np.testing.assert_array_equal(baseline["bed"], expected)
    assert not baseline["relief"].any()
    assert arrays["relief"].any()
    np.testing.assert_array_equal(arrays["bed"], (expected + arrays["relief"]).astype(np.float32))
    shared = support[96:-96, 96:-96]
    world = ((origin[0] + 96) * 30., (origin[1] + 96) * 30.)
    for z, x in ((110, 110), (125, 130), (110, 110)):
        window = np.s_[z:z+70, x:x+65]
        calculated = relief(expected[window], arrays["valid"][window], shared[window],
                            (world[0] + x * 30., world[1] + z * 30.), strength=.7)
        assert calculated.any()
        np.testing.assert_array_equal(calculated, arrays["relief"][window])


def test_all_sea_and_land(portable):
    sea = prepare_fixture(portable, "sea", locate(portable[3], "sea"))
    _, arrays = td.read_plate_source(sea)
    assert not arrays["relief"].any()
    support = np.zeros(arrays["macro"].shape, np.float32)
    np.testing.assert_array_equal(arrays["bed"], compose(arrays["raw_td"], arrays["macro"], support=support))
    with pytest.raises(ValueError, match="no certified ocean anchor"):
        prepare_fixture(portable, "land", locate(portable[3], "land"))
    assert not (portable[0] / "land").exists()


@pytest.mark.parametrize("key,value", [("valid_margin_bed_cells", 103),
    ("bed_origin_native_xz", [0, 0]), ("origin_native_xz", [0, 0]),
    ("relief_strength", .8), ("world_seed", 1)])
def test_rehashed_semantic_tamper(coastal, key, value):
    _, path = coastal
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    manifest[key] = value
    save_manifest(path, manifest)
    with pytest.raises(ValueError):
        td.read_plate_source(path)


@pytest.mark.parametrize("name,dtype", [("raw_td", "float64"), ("td_climate", "float64"),
    ("macro", "float64"), ("bed", "float64"), ("relief", "float64"),
    ("valid", "uint8"), ("classification", "int32"), ("shoreline", "uint8")])
def test_rehashed_array_dtype_rejection(coastal, name, dtype):
    _, path = coastal
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    file = path / (name + ".npy")
    array = np.load(file).astype(dtype)
    np.save(file, array, allow_pickle=False)
    manifest["files"][name] = td.digest(file)
    save_manifest(path, manifest)
    with pytest.raises(ValueError):
        td.read_plate_source(path)


@pytest.mark.parametrize("kind", ["model", "source", "code", "physical_identity", "conditioning_identity"])
def test_model_source_and_code_mismatch(portable, kind):
    path = prepare_fixture(portable, "raw", (-10, -10), 16, False, 0.)
    directory, source, config, frozen = portable
    if kind == "model":
        (directory / "model/unit-weights.bin").write_bytes(b"wrong model")
    elif kind == "source":
        other_config = TectonicConfig(shape=(12, 16), plate_count=4, steps=4,
                                     origin_x_m=-80000., origin_z_m=-60000.)
        other_source = directory / "other-source.npz"
        save_product(freeze(other_config, evolve(other_config)), other_source)
        shutil.copyfile(other_source, source)
    else:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        generation = manifest["generation"]
        if kind == "code":
            generation["source_sha256"]["plate_td_backend.py"] = "0" * 64
        elif kind == "physical_identity":
            generation["physical_generation_identity"] = "0" * 64
        else:
            generation["physical_generation"]["conditioning_identity"] = "0" * 64
        save_manifest(path, manifest)
    with pytest.raises((ValueError, OSError)):
        td.read_plate_source(path)
