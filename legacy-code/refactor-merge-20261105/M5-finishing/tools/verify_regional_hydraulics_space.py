"""Independent same-footprint 60m full-region sensitivity, no frozen runner changes."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.climate_forcing import regional_load_forcing as load_forcing
from terrain_pipeline.surface_hydraulics import SurfaceBudget, prepare_surface_geometry, advance_inertial_surface


def aggregate(array):
    return array.reshape(128, 2, 128, 2).sum(axis=(1, 3))


def main():
    source = load_source(ROOT / "verification/regional-source/run-20261001T095258008789Z/source.npz",
        expected_sha256="ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da")
    forcing_sha = "699a34ee51a68d98aa99a1c63a0cc9435845a2fb315a9e51b0f9343b3a839bbc"
    loaded = load_forcing(ROOT / "verification/regional-forcing/run-20261001T095608600719Z/uniform_heavy",
        expected_manifest_sha256=forcing_sha, source_identity=source["identity_sha256"])
    original = source["arrays"]["height_m"]
    bed = aggregate(original) / 4.
    origin = np.asarray(source["metadata"]["origin_m_xz"]) + 15.
    identity = source["identity_sha256"] + ":same-footprint-60m-block-mean-v1"
    geometry = prepare_surface_geometry(bed, spacing_m=60., origin_m_xz=origin, source_identity=identity, boundary_kind=np.ones(512, np.int64))
    output = ROOT / "verification/regional-hydraulics" / ("space60-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    budget = SurfaceBudget()
    difference = np.repeat(np.repeat(bed, 2, axis=0), 2, axis=1) - original
    paths = (Path(__file__), ROOT / "terrain_pipeline/regional_surface_hydraulics.py")
    declaration = {"source_identity": source["identity_sha256"], "derived_identity": identity,
        "height_source_identity": source["metadata"]["height_source_identity"], "forcing_manifest_sha256": forcing_sha,
        "shape": [128, 128], "spacing_m": 60., "origin_m_xz": origin.tolist(), "area_m2": 58982400.,
        "bed_rule": "2x2_mean_changes_depressions_not_pure_numerical_convergence", "forcing_rule": "2x2_sum_same_interval_volume",
        "bed_max_abs_change_m": float(np.abs(difference).max()), "bed_mean_abs_change_m": float(np.abs(difference).mean()),
        "budget": vars(budget), "duration_s": 259200., "source_hashes": {str(path.relative_to(ROOT)): file_sha256(path) for path in paths}}
    publish_bytes(output / "predeclared.json", json.dumps(declaration, indent=2).encode("ascii"))
    def observe(packet):
        if packet["interval"] % 24 == 0:
            print("SPACE60", packet["interval"], float(packet["depth_after_m"].max()), flush=True)
    result = advance_inertial_surface(geometry, initial_depth_m=np.zeros((128, 128)), forcing_interval_s=900., intervals=288,
        forcing_provider=lambda index: aggregate(loaded["runoff_volume_m3"][index]) / 900.,
        boundary_stage_provider=lambda index: np.zeros(512), source_identity=identity, forcing_identity=forcing_sha,
        budget=budget, interval_observer=observe)
    with (output / "states.npz").open("xb") as stream:
        np.savez_compressed(stream, **result["arrays"], H0_m=bed)
    declaration["metadata"] = result["metadata"]
    declaration["diagnostics"] = result["diagnostics"]
    declaration["source_unchanged"] = all(file_sha256(ROOT / key) == value for key, value in declaration["source_hashes"].items())
    loaded["runoff_volume_m3"]._mmap.close()
    publish_bytes(output / "report.json", json.dumps(declaration, indent=2).encode("ascii"))
    publish_bytes(output / "manifest.json", json.dumps({"artifacts": {path.name: file_sha256(path) for path in output.iterdir()}}, indent=2).encode("ascii"))
    print("SPACE60_DONE", output, flush=True)


if __name__ == "__main__":
    main()
