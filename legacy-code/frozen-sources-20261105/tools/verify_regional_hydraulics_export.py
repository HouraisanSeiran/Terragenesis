"""Cold validation and read-only exact columns plus explicitly thresholded top display."""

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
from terrain_pipeline.regional_hydraulics_archive import load_case
from terrain_pipeline.regional_hydraulics_mesh import water_columns, validate_water_columns


def export_case(directory):
    directory = Path(directory).resolve()
    binding = json.loads((directory / "binding.json").read_text(encoding="utf-8"))
    source = load_source(ROOT / "verification/regional-source/run-20261001T095258008789Z/source.npz",
        expected_sha256="ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da")
    forcing = load_forcing(ROOT / binding["forcing_directory"], expected_manifest_sha256=binding["forcing_manifest_sha256"], source_identity=source["identity_sha256"])
    case_sha = file_sha256(directory / "manifest.json")
    result = load_case(directory, expected_manifest_sha256=case_sha, trusted_height=source["arrays"]["height_m"],
        source_identity=source["identity_sha256"], forcing_volumes=forcing["runoff_volume_m3"])
    forcing["runoff_volume_m3"]._mmap.close()
    output = ROOT / "verification/regional-hydraulics" / ("mesh-" + directory.name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    states, geometry = result["states"], result["geometry"]
    indices = sorted(set([0, int(np.argmax(states["ledger"][:, 3])), len(states["time_s"]) - 1] +
        [int(np.argmin(abs(states["time_s"] - hour * 3600.))) for hour in (6, 12, 18, 24, 48, 72)]))
    index = {"schema": "regional-saved-B-mesh-index-v1", "source_identity": source["identity_sha256"],
        "status": "B_static_validated_saved_mesh", "source_case_manifest_sha256": case_sha,
        "source_case_directory": str(directory.relative_to(ROOT)), "snapshots": [],
        "display_threshold_m": .001, "sampling": "initial_storage_peak_nearest_6_12_18_24_48_72h_final_keyframes_not_all_substeps",
        "representation": "independent_flat_cell_top_quads_not_continuous_shared_stage_surface"}
    consumer_cases = []
    consumer_frames = []
    full_frames = []
    for state_index in indices:
        depth = states["depth_m"][state_index]
        packet = water_columns(source["arrays"]["height_m"], depth, spacing_m=30., origin_m_xz=source["metadata"]["origin_m_xz"],
            source_identity=source["identity_sha256"], time_s=states["time_s"][state_index])
        proof = validate_water_columns(packet, trusted_height=source["arrays"]["height_m"], saved_depth=depth, source_identity=source["identity_sha256"],
            trusted_spacing_m=30., trusted_origin_m_xz=source["metadata"]["origin_m_xz"])
        name = "physical-water-%04d" % state_index
        with (output / (name + ".npz")).open("xb") as stream:
            np.savez_compressed(stream, **packet["arrays"])
        publish_bytes(output / (name + ".json"), json.dumps({**packet["metadata"], "proof": proof}, indent=2).encode("ascii"))
        ids = packet["arrays"]["cell_id"]
        shown = depth.ravel()[ids] >= .001
        tops = packet["arrays"]["vertices_xyz_m"].reshape(-1, 8, 3)[shown, 4:]
        count = len(tops)
        triangles = (np.array([[0, 2, 1], [0, 3, 2]])[None] + np.arange(count)[:, None, None] * 4).reshape(-1, 3)
        display = {"source_identity": source["identity_sha256"], "time_s": float(states["time_s"][state_index]),
            "vertices_xyz_m": tops.reshape(-1, 3).tolist(), "triangles": triangles.tolist(),
            "display_cell_ids": ids[shown].tolist(), "display_threshold_m": .001,
            "omitted_wet_cells": int((~shown).sum()), "omitted_volume_m3": float(packet["arrays"]["cell_volume_m3"][~shown].sum()),
            "solver_volume_m3": proof["volume_m3"], "display_volume_m3": float(packet["arrays"]["cell_volume_m3"][shown].sum()),
            "representation": index["representation"], "physical_archive": name + ".npz"}
        payload = json.dumps(display, separators=(",", ":"), allow_nan=False).encode("ascii")
        if len(payload) > 16 * 1024**2 or count * 4 > 300000 or count * 2 > 400000:
            index.setdefault("display_refusals", []).append({"state_index": state_index, "bytes": len(payload), "reason": "A_consumer_budget"})
        else:
            filename = "saved-water-%04d.json" % state_index
            publish_bytes(output / filename, payload)
            index["snapshots"].append({"time_s": display["time_s"], "path": filename, "sha256": file_sha256(output / filename),
                "omitted_volume_m3": display["omitted_volume_m3"], "solver_volume_m3": display["solver_volume_m3"]})
            consumer_frames.append({"time_s": display["time_s"], "path": filename,
                "sha256": file_sha256(output / filename), "volume_m3": proof["volume_m3"], "max_depth_m": float(depth.max())})
        all_tops = packet["arrays"]["vertices_xyz_m"].reshape(-1, 8, 3)[:, 4:]
        all_count = len(all_tops)
        full_consumer = {"source_identity": source["identity_sha256"], "vertices_xyz_m": all_tops.reshape(-1, 3).tolist(),
            "triangles": (np.array([[0, 2, 1], [0, 3, 2]])[None] + np.arange(all_count)[:, None, None] * 4).reshape(-1, 3).tolist(),
            "time_s": float(states["time_s"][state_index]), "display_cell_ids": ids.tolist(),
            "display_threshold_m": 0., "omitted_wet_cells": 0, "omitted_volume_m3": 0.,
            "solver_volume_m3": proof["volume_m3"], "display_volume_m3": proof["volume_m3"],
            "representation": index["representation"], "physical_archive": name + ".npz"}
        full_payload = json.dumps(full_consumer, separators=(",", ":"), allow_nan=False).encode("ascii")
        if len(full_payload) <= 16 * 1024**2:
            full_filename = "consumer-full-water-%04d.json" % state_index
            publish_bytes(output / full_filename, full_payload)
            full_frames.append({"time_s": float(states["time_s"][state_index]), "path": full_filename,
                "sha256": file_sha256(output / full_filename), "volume_m3": proof["volume_m3"], "max_depth_m": float(depth.max())})
        else:
            index.setdefault("representation_export_failures", []).append({"state_index": state_index, "threshold_m": 0., "bytes": len(full_payload), "reason": "A_16MiB_JSON_budget"})
        del all_tops, full_consumer, full_payload
        del packet, display, payload, tops
    meta = result["metadata"]["metadata"]
    for label, frames in (("display_filtered_1mm", consumer_frames), ("full_top_threshold_0", full_frames)):
        if len(frames) != len(indices):
            continue
        consumer_cases.append({"id": directory.name + "_" + label, "model": meta["schema"] + "; keyframes; " + label,
            "requested_time_s": meta["requested_time_s"], "committed_time_s": meta["committed_time_s"], "status": meta["status"],
            "failure": None if meta["failure"] is None else str(meta["failure"]),
            "B_validation": "cold-validation.json; exact closed-column physical NPZ; display-filter statistics saved-mesh-index.json; keyframes only",
            "snapshots": frames})
    publish_bytes(output / "consumer-cases-index.json", json.dumps({"schema": "regional-saved-B-mesh-cases-v1",
        "source_identity": source["identity_sha256"], "fixture_only": False, "cases": consumer_cases}, indent=2).encode("ascii"))
    publish_bytes(output / "saved-mesh-index.json", json.dumps(index, indent=2).encode("ascii"))
    publish_bytes(output / "cold-validation.json", json.dumps({key: value for key, value in result.items() if key not in ("geometry", "states")}, indent=2).encode("ascii"))
    hashes = {path.name: file_sha256(path) for path in output.iterdir()}
    publish_bytes(output / "manifest.json", json.dumps({"artifacts": hashes, "case_manifest_sha256": case_sha,
        "exporter_sha256": file_sha256(Path(__file__)), "mesh_module_sha256": file_sha256(ROOT / "terrain_pipeline/regional_hydraulics_mesh.py"),
        "archive_module_sha256": file_sha256(ROOT / "terrain_pipeline/regional_hydraulics_archive.py")}, indent=2).encode("ascii"))
    print("MESH_OUTPUT", output, flush=True)


if __name__ == "__main__":
    export_case(sys.argv[1])
