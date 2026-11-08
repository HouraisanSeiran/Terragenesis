"""Read-only full-domain water partitions and non-DAG signed transfer diagnostics."""

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.regional_surface_source import load_source
from terrain_pipeline.regional_surface_forcing import load_forcing
from terrain_pipeline.regional_hydraulics_archive import load_case, read_arrays, strict_json


def summarize(directory):
    directory = Path(directory).resolve()
    source = load_source(ROOT / "verification/regional-source/run-20261001T095258008789Z/source.npz", expected_sha256="ac91c12b1f07b91872d9eed91982ad678a9eb72aaaf3fe0a41947cd4918563da")
    binding = strict_json(directory / "binding.json")
    forcing = load_forcing(ROOT / binding["forcing_directory"], expected_manifest_sha256=binding["forcing_manifest_sha256"], source_identity=source["identity_sha256"])
    manifest_sha = file_sha256(directory / "manifest.json")
    case = load_case(directory, expected_manifest_sha256=manifest_sha, trusted_height=source["arrays"]["height_m"], source_identity=source["identity_sha256"], forcing_volumes=forcing["runoff_volume_m3"])
    arrays, states = source["arrays"], case["states"]
    lake, channel = arrays["diagnostic_lake_id"] > 0, arrays["channel_mask"]
    masks = {"potential_lake": lake, "non_lake": ~lake, "static_channel": channel, "non_channel": ~channel,
        "lake_channel": lake & channel, "lake_non_channel": lake & ~channel,
        "non_lake_channel": ~lake & channel, "non_lake_non_channel": ~lake & ~channel}
    frames = []
    previous_time = previous_out = previous_in = 0.
    for index, depth in enumerate(states["depth_m"]):
        time = float(states["time_s"][index])
        duration = time - previous_time
        out, entered = states["ledger"][index, 2], states["ledger"][index, 1]
        frames.append({"time_s": time, "total_volume_m3": float(depth.sum() * 900.),
            "preceding_saved_interval_external_outflow_mean_m3_s": float((out-previous_out)/duration) if duration else None,
            "preceding_saved_interval_external_inflow_mean_m3_s": float((entered-previous_in)/duration) if duration else None,
            "partitions": {name: {"volume_m3": float(depth[mask].sum() * 900.),
                "positive_wet_area_m2": int((depth[mask] > 0).sum()) * 900,
                "wet_area_at_least_1mm_m2": int((depth[mask] >= .001).sum()) * 900} for name, mask in masks.items()}})
        previous_time, previous_out, previous_in = time, out, entered
    left, right = case["geometry"]["arrays"]["face_left"], case["geometry"]["arrays"]["face_right"]
    receiver = arrays["receiver"].ravel()
    direction = np.where(receiver[left] == right, 1., np.where(receiver[right] == left, -1., 0.))
    opposed_volume = np.zeros(len(left))
    opposed_count = 0
    manifest = strict_json(directory / "manifest.json")
    for name in sorted(manifest["artifacts"]):
        if not name.startswith("interval-") or not name.endswith(".npz"):
            continue
        with np.load(directory / name, allow_pickle=False) as archive:
            transfer = archive["internal_transfer_m3"]
        opposed = (direction != 0) & (transfer * direction < -1e-10)
        opposed_count += int(opposed.sum())
        opposed_volume[opposed] += np.abs(transfer[opposed])
    ledger = forcing["metadata"]["ledger"]
    committed = case["metadata"]["metadata"]["committed_time_s"]
    intervals = int(committed // 900.)
    fraction = (committed - intervals * 900.) / 900.
    def integral(key):
        values = np.asarray(ledger[key])
        return float(values[:intervals].sum() + (values[intervals] * fraction if intervals < len(values) else 0.))
    initial_soil = float(forcing["initial_states_mm"].sum() * .9)
    if abs(committed - 259200.) < 1e-7:
        final_soil = float(forcing["final_states_mm"].sum() * .9)
        soil_scope = "saved_exact_final_soil_fast_slow_states"
    else:
        storage = np.asarray(forcing["metadata"]["total_soil_fast_slow_storage_m3"])
        final_soil = float(storage[intervals] + fraction * (storage[intervals + 1] - storage[intervals]))
        soil_scope = "interval_ledger_linear_interpolation_not_nonlinear_intermediate_soil_state"
    surface_meta = case["metadata"]["metadata"]
    joint = final_soil - initial_soil + surface_meta["final_volume_m3"] - surface_meta["initial_volume_m3"] - integral("rain_m3") + integral("et_m3") - surface_meta["boundary_input_m3"] + surface_meta["boundary_output_m3"]
    report = {"case_directory": str(directory.relative_to(ROOT)), "case_manifest_sha256": manifest_sha,
        "forcing_manifest_sha256": binding["forcing_manifest_sha256"], "status": surface_meta["status"],
        "requested_time_s": surface_meta["requested_time_s"], "committed_time_s": surface_meta["committed_time_s"],
        "failure": surface_meta["failure"],
        "source_identity": source["identity_sha256"], "source_height_identity": source["metadata"]["height_source_identity"],
        "frames": frames, "partition_scope": "lake_channel_pairs_overlap_use_four_intersections_for_partition_sum",
        "recession_scope": "outlet_rate_and_each_partition_storage_separate_no_global_recession_claim_from_rain_stopping",
        "non_DAG": {"opposed_interval_face_occurrences": opposed_count, "unique_opposed_receiver_faces": int((opposed_volume > 0).sum()),
            "sum_opposed_interval_net_transfer_m3": float(opposed_volume.sum()),
            "scope": "interval_net_signed_transfer_not_substep_gross_backflow_or_unique_river_segments"},
        "rain_soil_surface": {"rain_m3": integral("rain_m3"), "ET_m3": integral("et_m3"),
            "surface_runoff_m3": integral("runoff_m3"), "soil_fast_slow_storage_change_m3": integral("storage_change_m3"),
            "forcing_balance_residual_m3": integral("residual_m3"), "initial_soil_fast_slow_m3": initial_soil,
            "final_soil_fast_slow_m3": final_soil, "soil_final_scope": soil_scope,
            "initial_surface_m3": surface_meta["initial_volume_m3"], "final_surface_m3": surface_meta["final_volume_m3"],
            "external_input_m3": surface_meta["boundary_input_m3"], "external_output_m3": surface_meta["boundary_output_m3"],
            "combined_rain_soil_surface_residual_m3": joint},
        "geometry_scope": "30m_flat_cells_no_subgrid_cross_sections_no_dynamic_channel_graph_certification",
        "cold_evidence": {key: value for key, value in case.items() if key not in ("geometry", "states")}}
    forcing["runoff_volume_m3"]._mmap.close()
    return report


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    report = summarize(directory)
    destination = directory.parent / (directory.name + "-summary.json")
    publish_bytes(destination, json.dumps(report, indent=2).encode("ascii"))
    print("SUMMARY", destination, flush=True)
