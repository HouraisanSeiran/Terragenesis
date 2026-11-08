"""Strict same-footprint 60m snapshot cold checks, not interval momentum certification."""

import json
from pathlib import Path
import sys
import zipfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.regional_hydraulics_archive import read_arrays, strict_json
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.climate_forcing import regional_load_forcing as load_forcing


def validate(directory, expected_manifest_sha256):
    directory = Path(directory)
    if file_sha256(directory / "manifest.json") != expected_manifest_sha256:
        raise ValueError("external space manifest SHA")
    manifest = strict_json(directory / "manifest.json")
    for name, digest in manifest["artifacts"].items():
        if Path(name).name != name or file_sha256(directory / name) != digest:
            raise ValueError("space artifacts authentic basenames")
    report = strict_json(directory / "report.json")
    source = load_source(ROOT / "verification/regional-source/run-20261001T095258008789Z/source.npz",
        expected_sha256="ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da")
    forcing = load_forcing(ROOT / "verification/regional-forcing/run-20261001T095608600719Z/uniform_heavy",
        expected_manifest_sha256="699a34ee51a68d98aa99a1c63a0cc9435845a2fb315a9e51b0f9343b3a839bbc", source_identity=source["identity_sha256"])
    if report["source_identity"] != source["identity_sha256"] or report["height_source_identity"] != source["metadata"]["height_source_identity"] or report["shape"] != [128, 128] or report["spacing_m"] != 60. or report["origin_m_xz"] != [-184305., 61455.] or report["area_m2"] != 58982400.:
        raise ValueError("same source/footprint identity")
    with zipfile.ZipFile(directory / "states.npz") as archive:
        with archive.open("time_s.npy") as stream:
            version = np.lib.format.read_magic(stream)
            header = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
            shape, order, dtype = header(stream)
            if len(shape) != 1 or not 1 <= shape[0] <= 50 or order or dtype != np.float64:
                raise ValueError("space bounded time header")
            count = shape[0]
    arrays = read_arrays(directory / "states.npz", {"time_s": ((count,), "float64"),
        "depth_m": ((count, 128, 128), "float64"), "initial_depth_m": ((128, 128), "float64"),
        "ledger": ((count, 5), "float64"), "final_internal_q_m3_s": ((32512,), "float64"),
        "final_boundary_q_m3_s": ((512,), "float64"), "H0_m": ((128, 128), "float64")},
        expected_sha256=manifest["artifacts"]["states.npz"])
    expected_bed = source["arrays"]["height_m"].reshape(128, 2, 128, 2).mean(axis=(1, 3))
    if not np.allclose(arrays["H0_m"], expected_bed, atol=1e-12, rtol=0):
        raise ValueError("same-source block bed mean")
    times, depths, ledger = arrays["time_s"], arrays["depth_m"], arrays["ledger"]
    meta = report["metadata"]
    if times[0] != 0 or abs(times[-1] - meta["committed_time_s"]) > 1e-7 or (np.diff(times) <= 0).any() or (depths < 0).any() or (depths > 20).any() or np.any(depths[0] != 0):
        raise ValueError("space physical snapshot states")
    if not np.array_equal(arrays["initial_depth_m"], depths[0]):
        raise ValueError("space initial identity")
    if meta["status"] == "completed":
        if meta["failure"] is not None or abs(meta["committed_time_s"] - 259200.) > 1e-7:
            raise ValueError("space completed status")
    elif meta["status"] == "refused":
        if not isinstance(meta["failure"], dict) or not meta["committed_time_s"] < 259200.:
            raise ValueError("space refused prefix")
    else:
        raise ValueError("space status")
    expected_input = []
    rates = forcing["runoff_volume_m3"].sum(axis=(1, 2)) / 900.
    prefix = np.r_[0., np.cumsum(rates * 900.)]
    for time in times:
        index = min(int(time // 900), len(rates))
        expected_input.append(prefix[index] + (time - index * 900.) * rates[index] if index < len(rates) else prefix[-1])
    volume = depths.sum(axis=(1, 2)) * 3600.
    residual = volume - expected_input + ledger[:, 2] - ledger[:, 1]
    if not np.allclose(ledger[:, 0], expected_input, atol=1e-6, rtol=2e-11) or not np.allclose(ledger[:, 3], volume, atol=1e-7, rtol=1e-12) or not np.allclose(ledger[:, 4], residual, atol=1e-6, rtol=1e-12) or (abs(residual) > 1e-5 + np.asarray(expected_input) * 2e-11).any():
        raise ValueError("space saved forcing/storage ledger")
    for key, value in (("final_volume_m3", volume[-1]), ("supplied_m3", ledger[-1, 0]), ("boundary_output_m3", ledger[-1, 2]), ("boundary_input_m3", ledger[-1, 1])):
        if not np.isclose(meta[key], value, atol=1e-6, rtol=1e-12):
            raise ValueError("space metadata totals")
    forcing["runoff_volume_m3"]._mmap.close()
    return {"manifest_sha256": expected_manifest_sha256, "status": meta["status"],
        "committed_time_s": meta["committed_time_s"], "max_snapshot_mass_residual_m3": float(abs(residual).max()),
        "scope": "source_footprint_saved_snapshot_volume_forcing_ledger_no_interval_or_momentum_certificates"}


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    result = validate(directory, sys.argv[2])
    publish_bytes(directory.parent / (directory.name + "-cold-check.json"), json.dumps(result, indent=2).encode("ascii"))
    print(json.dumps(result), flush=True)
