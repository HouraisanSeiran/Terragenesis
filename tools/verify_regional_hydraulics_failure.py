"""Real full-grid zero/two-commit refusal packages using frozen production solver."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_regional_hydraulics_full import write_packet, SOURCE, FORCING, SOURCE_SHA
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.regional_surface_forcing import load_forcing
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget, prepare_surface_geometry, advance_inertial_surface
from terrain_pipeline.regional_hydraulics_archive import load_case
from terrain_pipeline.mountain_source_adapter import publish_bytes, file_sha256


def main():
    source = load_source(SOURCE / "source.npz", expected_sha256=SOURCE_SHA)
    handoff = json.loads((FORCING / "handoff-manifest.json").read_text(encoding="utf-8"))
    sha = handoff["cases"]["uniform_heavy"]["manifest_sha256"]
    loaded = load_forcing(FORCING / "uniform_heavy", expected_manifest_sha256=sha, source_identity=source["identity_sha256"])
    height = source["arrays"]["height_m"]
    output = ROOT / "verification/regional-hydraulics" / ("failure-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    cases = [("depth_zero_commit", replace(SurfaceBudget(), max_depth_m=1e-12)),
        ("work_two_commit", replace(SurfaceBudget(), max_substeps=2))]
    declaration = {"source_identity": source["identity_sha256"], "height_source_identity": source["metadata"]["height_source_identity"],
        "source_sha256": SOURCE_SHA, "forcing_manifest_sha256": sha,
        "cases": {name: vars(budget) for name, budget in cases},
        "solver_sha256": file_sha256(ROOT / "terrain_pipeline/regional_surface_hydraulics.py"),
        "scope": "explicit_resource_and_depth_failure_real_full_grid_not_main_budget_changes"}
    publish_bytes(output / "predeclared.json", json.dumps(declaration, indent=2).encode("ascii"))
    for name, budget in cases:
        directory = output / name
        directory.mkdir()
        geometry = prepare_surface_geometry(height, spacing_m=30., origin_m_xz=source["metadata"]["origin_m_xz"], source_identity=source["identity_sha256"], boundary_kind=np.ones(1024, np.int64))
        write_packet(directory, "geometry", {**geometry["arrays"], **geometry["metadata"]})
        publish_bytes(directory / "binding.json", json.dumps({"source_identity": source["identity_sha256"],
            "height_source_identity": source["metadata"]["height_source_identity"], "forcing_manifest_sha256": sha,
            "forcing_directory": str((FORCING / "uniform_heavy").relative_to(ROOT)), "budget": vars(budget)}, indent=2).encode("ascii"))
        result = advance_inertial_surface(geometry, initial_depth_m=np.zeros(height.shape), forcing_interval_s=900., intervals=288,
            forcing_provider=lambda index: loaded["runoff_volume_m3"][index].astype(np.float64) / 900.,
            boundary_stage_provider=lambda index: geometry["arrays"]["boundary_crest_m"].copy(),
            source_identity=source["identity_sha256"], forcing_identity=sha, budget=budget,
            interval_observer=lambda packet: write_packet(directory, "interval-%03d" % packet["interval"], packet),
            momentum_observer=lambda packet: write_packet(directory, "momentum-%03d" % packet["interval"], packet))
        write_packet(directory, "states", {**result["arrays"], "metadata": result["metadata"], "diagnostics": result["diagnostics"]})
        publish_bytes(directory / "manifest.json", json.dumps({"artifacts": {path.name: file_sha256(path) for path in directory.iterdir()}}, indent=2).encode("ascii"))
        verified = load_case(directory, expected_manifest_sha256=file_sha256(directory / "manifest.json"), trusted_height=height,
            source_identity=source["identity_sha256"], forcing_volumes=loaded["runoff_volume_m3"])
        proof = {key: value for key, value in verified.items() if key not in ("geometry", "states")}
        publish_bytes(output / (name + "-cold.json"), json.dumps(proof, indent=2).encode("ascii"))
        print("FAILURE_COLD", name, result["metadata"]["committed_time_s"], result["metadata"]["failure"], flush=True)
    loaded["runoff_volume_m3"]._mmap.close()
    print("FAILURE_OUTPUT", output, flush=True)


if __name__ == "__main__":
    main()
