"""Bounded independent material evidence and hostile archive checks."""

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import checked_archive, file_sha256
from terrain_pipeline.td_material_field import _bundle, _save_bundle, load_material_field, make_material_field, save_material_field


def hostile_checks(bundle, loader):
    checks = {}
    with tempfile.TemporaryDirectory(dir=ROOT / "verification/td-basin-generation") as temporary:
        directory = Path(temporary)
        forged = _bundle(bundle["arrays"], {**bundle["metadata"], "forged": True})
        forged_path = directory / "forged.npz"
        _save_bundle(forged, forged_path)
        for name, expected in (("rehashed_forgery_identity_rejected", {"expected_identity": bundle["identity_sha256"]}),
                               ("rehashed_forgery_archive_rejected", {"expected_sha256": "0" * 64})):
            try:
                loader(forged_path, **expected)
            except ValueError:
                checks[name] = True
            else:
                raise AssertionError(name)
        header = io.BytesIO()
        np.lib.format.write_array_header_1_0(header, {"descr": "<f8", "fortran_order": False, "shape": (2 ** 40,)})
        bad_path = directory / "malicious.npz"
        with zipfile.ZipFile(bad_path, "w") as archive:
            archive.writestr("huge.npy", header.getvalue())
        with patch("numpy.load", side_effect=AssertionError("must not allocate")):
            try:
                loader(bad_path, expected_sha256=file_sha256(bad_path))
            except ValueError:
                checks["malicious_header_rejected_before_numpy_load"] = True
            else:
                raise AssertionError("malicious header accepted")
    return checks


def verify(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source_path = ROOT / "verification/mountain-real-td/mountain-run-20261001T080705728662Z/primary-source.npz"
    source_sha256 = "6e7fdf63dc02e9f14e7d83550d0c5f806b42aa7f13367ea96012787bcf069382"
    source = checked_archive(source_path, expected_sha256=source_sha256)
    source_manifest = json.loads(source["manifest"].tobytes().decode("utf-8"))
    source_metadata = source_manifest["metadata"]
    shape = source["height_m"].shape
    options = {"origin_m_xz": source_metadata["origin_m_xz"], "spacing_m": source_metadata["spacing_m"], "seed": 20261002}
    protected = np.zeros(shape, bool)
    field = make_material_field(shape, protected_mask=protected, **options)
    path = output / "material.npz"
    save_material_field(field, path)
    digest = file_sha256(path)
    with patch("terrain_pipeline.td_material_field.make_material_field", side_effect=AssertionError("cold generation forbidden")):
        loaded = load_material_field(path, expected_sha256=digest, expected_identity=field["identity_sha256"])
    checks = {"pinned_cold_read_without_generation": loaded["identity_sha256"] == field["identity_sha256"],
              "same_seed_replay": make_material_field(shape, protected_mask=protected, **options)["identity_sha256"] == field["identity_sha256"]}
    different = make_material_field(shape, **{**options, "seed": 20261003})
    checks["different_seed_variation"] = not np.array_equal(field["arrays"]["erodibility"], different["arrays"]["erodibility"])
    for reverse in (False, True):
        windows = [(row, col) for row in range(0, 256, 64) for col in range(0, 256, 64)]
        if reverse:
            windows.reverse()
        for row, col in windows:
            tile = make_material_field((64, 64), origin_m_xz=(options["origin_m_xz"][0] + 30 * col, options["origin_m_xz"][1] + 30 * row), spacing_m=30,
                                       protected_mask=protected[row:row + 64, col:col + 64])
            for name in field["arrays"]:
                np.testing.assert_array_equal(tile["arrays"][name], field["arrays"][name][row:row + 64, col:col + 64])
        checks["reversed_tiles_exact" if reverse else "row_major_tiles_exact"] = True
    fine = make_material_field((1, 1000), origin_m_xz=(895, 0), spacing_m=0.01)
    maximum_step = float(np.max(np.abs(np.diff(fine["arrays"]["erodibility"]))))
    checks["continuous_lattice_seam"] = maximum_step < 1e-4
    bounds = {}
    for name, low, high in (("erodibility", 0.25, 1), ("erodible_thickness_m", 0.25, 4), ("weak_path_preference", 0.8, 1.2)):
        values = loaded["arrays"][name]
        bounds[name] = [float(values.min()), float(values.max())]
        assert np.isfinite(values).all() and np.all(values >= low) and np.all(values <= high)
    checks["finite_legal_ranges"] = True
    for config in ({"solid_density_kg_m3": 0}, {"source_porosity": 1}, {"deposit_porosity": np.nan}):
        try:
            make_material_field((2, 2), origin_m_xz=(0, 0), spacing_m=1, parameters=config)
        except ValueError:
            pass
        else:
            raise AssertionError("illegal material accepted")
    checks["illegal_density_porosity_rejected"] = True
    protected_fixture = np.zeros((4, 4), bool)
    protected_fixture[1, 1] = True
    mask_fixture = make_material_field((4, 4), origin_m_xz=(0, 0), spacing_m=30, protected_mask=protected_fixture)
    np.testing.assert_array_equal(mask_fixture["arrays"]["protected_mask"], protected_fixture)
    checks["explicit_protected_mask_preserved"] = True
    checks["source_unchanged"] = file_sha256(source_path) == source_sha256
    checks.update(hostile_checks(field, load_material_field))
    assert all(checks.values())
    report = {"verified": True, "issue": 52, "checks": checks, "bounds": bounds,
              "maximum_fine_step": maximum_step, "archive": str(path.resolve()),
              "expected_sha256": digest, "expected_identity": field["identity_sha256"],
              "parameters": field["metadata"]["parameters"],
              "source": {"path": str(source_path.resolve()), "sha256": source_sha256,
                         "identity_sha256": source_manifest["identity_sha256"],
                         "shape": list(shape), "origin_m_xz": options["origin_m_xz"],
                         "spacing_m": options["spacing_m"], "valid_cells": int(np.count_nonzero(source["hydrology_mask"])),
                         "protected_mask_policy": "none declared in frozen source; all false"},
              "code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "terrain_pipeline/td_material_field.py", "tools/verify_td_material_field.py")},
              "array_bytes": sum(values.nbytes for values in field["arrays"].values()),
              "limitations": "synthetic materials; no measured lithology or morphology naturalness claim"}
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ("verification/td-basin-generation/B-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "/material"))
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.output), ensure_ascii=False))
