"""Pinned serial full-region runs; interval continuity and sampled momentum evidence."""

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.regional_surface_forcing import load_forcing
from terrain_pipeline.regional_surface_hydraulics import SurfaceBudget, prepare_surface_geometry, advance_inertial_surface


SOURCE = ROOT / "verification/regional-source/run-20261001T095258008789Z"
FORCING = ROOT / "verification/regional-forcing/run-20261001T095608600719Z"
SOURCE_SHA = "ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da"


def write_packet(directory, name, packet):
    arrays = {key: value for key, value in packet.items() if isinstance(value, np.ndarray)}
    meta = {key: value for key, value in packet.items() if not isinstance(value, np.ndarray)}
    with (directory / (name + ".npz")).open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    publish_bytes(directory / (name + ".json"), json.dumps(meta, indent=2).encode("ascii"))


def main():
    source = load_source(SOURCE / "source.npz", expected_sha256=SOURCE_SHA)
    handoff = json.loads((FORCING / "handoff-manifest.json").read_text(encoding="utf-8"))
    height = source["arrays"]["height_m"]
    if height.shape != (256, 256):
        raise ValueError("entire 65536-cell finite region required")
    output = ROOT / "verification/regional-hydraulics" / ("full-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    budget = SurfaceBudget()
    cases = [("dry", "dry", False, False), ("wet_no_rain", "wet_no_rain", False, False),
             ("uniform_heavy", "uniform_heavy", False, False), ("uniform_heavy_tailwater", "uniform_heavy", True, False),
             ("uniform_heavy_half_cfl", "uniform_heavy", False, True)]
    if "--case" in sys.argv:
        selected = sys.argv[sys.argv.index("--case") + 1]
        cases = [case for case in cases if case[0] == selected]
        if not cases:
            raise ValueError("unknown predeclared case")
    paths = [Path(__file__), ROOT / "terrain_pipeline/regional_surface_hydraulics.py"]
    source_hashes = {str(path.relative_to(ROOT)): file_sha256(path) for path in paths}
    declaration = {"algorithm": "regional-surface-local-inertial-D4-implicit-new-q-drag-v2", "cases": cases,
        "budget": vars(budget), "duration_s": 259200., "source_sha256": SOURCE_SHA,
        "source_identity": source["identity_sha256"], "height_source_identity": source["metadata"]["height_source_identity"],
        "forcing_handoff_sha256": file_sha256(FORCING / "handoff-manifest.json"),
        "source_hashes": source_hashes, "disk_budget_per_case_bytes": 2 * 1024**3,
        "tailwater": {"east_rows": [252, 253, 254, 255], "south_columns": [252, 253, 254, 255],
            "absolute_stage_m": float(height[-1, -1] + 10), "start_s": 43200., "end_s": 86400.,
            "outside_event": "engineering_drainage_stage_at_local_boundary_crest"},
        "sampled_momentum_intervals": list(range(0, 288, 24)), "sampling_scope": "first_substep_only_not_all_trajectory_momentum",
        "sensitivity": {"max_dt_s": 15., "inertial_cfl": .225, "forcing_interval_s": 900.}}
    publish_bytes(output / "predeclared.json", json.dumps(declaration, indent=2).encode("ascii"))
    print("FULL_OUTPUT", output, flush=True)
    for name, forcing_name, raised, half in cases:
        directory = output / name
        directory.mkdir()
        forcing_sha = handoff["cases"][forcing_name]["manifest_sha256"]
        loaded = load_forcing(FORCING / forcing_name, expected_manifest_sha256=forcing_sha, source_identity=source["identity_sha256"])
        kinds = np.ones(1024, np.int64)
        selected_faces = np.r_[256 + np.arange(252, 256), 768 + np.arange(252, 256)]
        if raised:
            kinds[selected_faces] = 2
        geometry = prepare_surface_geometry(height, spacing_m=30., origin_m_xz=source["metadata"]["origin_m_xz"],
            source_identity=source["identity_sha256"], boundary_kind=kinds)
        write_packet(directory, "geometry", {**geometry["arrays"], **geometry["metadata"]})
        def tailwater(index):
            result = geometry["arrays"]["boundary_crest_m"].copy()
            if raised and 48 <= index < 96:
                result[selected_faces] = declaration["tailwater"]["absolute_stage_m"]
            return result
        def interval_observer(packet):
            write_packet(directory, "interval-%03d" % packet["interval"], packet)
            if packet["interval"] % 12 == 0:
                print(name, "INTERVAL", packet["interval"], "depth", float(packet["depth_after_m"].max()), flush=True)
        def momentum_observer(packet):
            if packet["interval"] in declaration["sampled_momentum_intervals"]:
                write_packet(directory, "momentum-%03d" % packet["interval"], packet)
        case_budget = replace(budget, max_dt_s=15., inertial_cfl=.225) if half else budget
        publish_bytes(directory / "binding.json", json.dumps({"forcing_manifest_sha256": forcing_sha,
            "forcing_directory": str((FORCING / forcing_name).relative_to(ROOT)), "source_identity": source["identity_sha256"],
            "height_source_identity": source["metadata"]["height_source_identity"], "budget": vars(case_budget)}, indent=2).encode("ascii"))
        result = advance_inertial_surface(geometry, initial_depth_m=np.zeros(height.shape), forcing_interval_s=900., intervals=288,
            forcing_provider=lambda index: loaded["runoff_volume_m3"][index].astype(np.float64) / 900.,
            boundary_stage_provider=tailwater, source_identity=source["identity_sha256"], forcing_identity=forcing_sha,
            budget=case_budget, interval_observer=interval_observer, momentum_observer=momentum_observer)
        write_packet(directory, "states", {**result["arrays"], "metadata": result["metadata"], "diagnostics": result["diagnostics"]})
        loaded["runoff_volume_m3"]._mmap.close()
        hashes = {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
        size = sum(path.stat().st_size for path in directory.iterdir() if path.is_file())
        publish_bytes(directory / "manifest.json", json.dumps({"artifacts": hashes, "bytes": size,
            "disk_budget_passed": size <= declaration["disk_budget_per_case_bytes"], "source_hashes": source_hashes,
            "source_unchanged": all(file_sha256(ROOT / key) == value for key, value in source_hashes.items())}, indent=2).encode("ascii"))
        print("CASE_DONE", name, json.dumps(result["metadata"]), json.dumps(result["diagnostics"]), flush=True)
        del result
    print("FULL_DONE", output, flush=True)


if __name__ == "__main__":
    main()
