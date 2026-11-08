import json
from pathlib import Path
import numpy as np
import pytest
from terrain_pipeline.coastal_terrain import classify
from terrain_pipeline import coastal_terrain as product


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    z, x = np.indices((90, 110))
    raw = ((x - 55) * .4 + 15 * np.sin(x / 3) * np.cos(z / 4)).astype(np.float32)
    raw_path = root / "raw.npy"
    np.save(raw_path, raw)
    bed = np.broadcast_to(((np.arange(100) - 50) * .4).astype(np.float32), (80, 100)).copy()
    valid = np.ones(bed.shape, bool)
    codes, shore = classify(bed, valid, [(40, 0)])
    files = {}
    for name, a in (("bed", bed), ("valid", valid), ("classification", codes), ("shoreline", shore)):
        path = root / (name + ".npy")
        np.save(path, a)
        files[path.name] = product.file_hash(path)
    metadata = {"terrain_identity": "portable-td-fixture", "world_seed": 20261020, "source_shape_zx": [90, 110], "native_spacing_m": 30, "native_source_origin_xz_m": [3000, -6000], "source_origin_native_xz": [100, -200], "native_source_paths": {"raw_td_30m": {"path": str(raw_path), "sha256": product.file_hash(raw_path), "array_sha256": product.array_hash_rowchunk(raw)}}}
    metadata_path = root / "metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    record = {"kind": "frozen-detail-source-v1", "baseline_path": str(root), "baseline_identity": "", "files": files, "raw_path": str(raw_path), "raw_file_sha256": product.file_hash(raw_path), "raw_array_sha256": product.array_hash_rowchunk(raw), "metadata_path": str(metadata_path), "metadata_sha256": product.file_hash(metadata_path), "terrain_identity": "portable-td-fixture", "world_seed": 20261020, "shape_zx": [80, 100], "origin_xz_m": [3150, -5850], "spacing_m": 30, "source_shape_zx": [90, 110], "source_origin_xz_m": [3000, -6000], "source_slice_zx": [5, 85, 5, 105], "anchors_zx": [[40, 0]]}
    record["baseline_identity"] = product._frozen_baseline_identity(record)
    return record


def reseal(path, manifest):
    manifest["identity"] = product.identity_detail(manifest)
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_portable_roundtrip_readonly_no_overwrite(source, tmp_path):
    output = tmp_path / "product"
    manifest = product.prepare_source(source, output)
    _, arrays = product.read_detail_product(output, expected_identity=manifest["identity"])
    assert np.any(arrays["delta"])
    for a in arrays.values():
        assert not a.flags.writeable
        with pytest.raises(ValueError):
            a.flat[0] = 0
    with pytest.raises(FileExistsError):
        product.prepare_source(source, output)
    copy = json.loads(json.dumps(manifest))
    copy["source"]["raw_path"] = "another-machine/raw.npy"
    copy["source"]["baseline_path"] = "another-machine/baseline"
    assert product.identity_detail(copy) == manifest["identity"]


@pytest.mark.parametrize("field", ["bed", "delta", "valid", "classification", "shoreline", "weight", "distance_m"])
def test_resealed_array_forgery_rejected(source, tmp_path, field):
    output = tmp_path / "product"
    m = product.prepare_source(source, output)
    path = output / (field + ".npy")
    a = np.load(path)
    if a.dtype == np.bool_:
        a[40, 50] = ~a[40, 50]
    else:
        a[40, 50] += 1
    np.save(path, a)
    m["files"][path.name] = product.file_hash(path)
    reseal(output, m)
    with pytest.raises(ValueError, match="derived relation"):
        product.read_detail_product(output)


@pytest.mark.parametrize("change", ["raw", "metadata", "mapping", "parameters", "seed", "algorithm", "source-hash"])
def test_source_and_manifest_failures(source, tmp_path, change):
    output = tmp_path / "product"
    m = product.prepare_source(source, output)
    if change in {"raw", "metadata"}:
        path = Path(source[change + "_path"])
        with path.open("ab") as stream:
            stream.write(b"tamper")
    elif change == "mapping":
        m["source"]["source_slice_zx"] = [4, 84, 5, 105]
    elif change == "parameters":
        m["parameters"]["cap_m"] = 7
    elif change == "seed":
        m["source"]["world_seed"] = 0
    elif change == "algorithm":
        m["algorithm_sha256"]["coastal_detail_refinement.py"] = "0" * 64
    else:
        m["source"]["raw_array_sha256"] = "0" * 64
    reseal(output, m)
    with pytest.raises(ValueError):
        product.read_detail_product(output)


def test_mapping_checked_even_with_rehashed_metadata(source, tmp_path):
    metadata_path = Path(source["metadata_path"])
    metadata = json.loads(metadata_path.read_text())
    metadata["native_source_origin_xz_m"][0] += 30
    metadata_path.write_text(json.dumps(metadata))
    source["metadata_sha256"] = product.file_hash(metadata_path)
    with pytest.raises(ValueError, match="coordinates"):
        product.prepare_source(source, tmp_path / "output")


def test_preflight_and_staging_failure(source, tmp_path, monkeypatch):
    output = tmp_path / "product"
    with pytest.raises(ValueError, match="budget"):
        product.prepare_source(source, output, memory_budget_bytes=1)
    def fail(*args, **kwargs):
        raise OSError("simulated write failure")
    monkeypatch.setattr(product.np, "save", fail)
    with pytest.raises(OSError, match="simulated"):
        product.prepare_source(source, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".coastal-detail-*"))


def test_real_entry_rejects_unapproved_baseline(source, tmp_path):
    path = Path(source["baseline_path"])
    (path / "manifest.json").write_text(json.dumps({"identity": "unapproved"}))
    with pytest.raises(ValueError, match="approved baseline"):
        product.prepare_detail(path, tmp_path / "product")


def test_relocated_source_bytes_preserve_identity(source, tmp_path):
    import shutil
    output = tmp_path / "product"
    m = product.prepare_source(source, output)
    relocated = tmp_path / "relocated"
    shutil.copytree(source["baseline_path"], relocated)
    for key in ("baseline_path", "raw_path", "metadata_path"):
        original = Path(m["source"][key])
        m["source"][key] = str(relocated if key == "baseline_path" else relocated / original.name)
    assert product.identity_detail(m) == m["identity"]
    reseal(output, m)
    product.read_detail_product(output, expected_identity=m["identity"])


def test_incomplete_parameters_rejected(source, tmp_path):
    output = tmp_path / "product"
    m = product.prepare_source(source, output)
    del m["parameters"]["strength"]
    reseal(output, m)
    with pytest.raises(ValueError, match="incomplete"):
        product.read_detail_product(output)
