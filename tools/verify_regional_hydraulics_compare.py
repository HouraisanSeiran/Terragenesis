"""Read-only aligned hydraulic/spatial differences, never regenerate missing times."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import label

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.regional_hydraulics_archive import read_arrays, strict_json, GEOMETRY


def read_states(directory, *, expected_manifest_sha256, space=False):
    directory = Path(directory)
    if file_sha256(directory / "manifest.json") != expected_manifest_sha256:
        raise ValueError("external comparison manifest SHA")
    manifest = strict_json(directory / "manifest.json")
    digest = manifest["artifacts"]["states.npz"]
    if file_sha256(directory / "states.npz") != digest:
        raise ValueError("comparison saved archive hash")
    import zipfile
    with zipfile.ZipFile(directory / "states.npz") as archive:
        with archive.open("time_s.npy") as stream:
            version = np.lib.format.read_magic(stream)
            header = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
            shape, order, dtype = header(stream)
            if len(shape) != 1 or not 1 <= shape[0] <= 50 or order or dtype != np.float64:
                raise ValueError("comparison bounded snapshot header")
    count = shape[0]
    size, faces, boundary = (128, 32512, 512) if space else (256, 130560, 1024)
    specs = {"time_s": ((count,), "float64"), "depth_m": ((count, size, size), "float64"),
        "initial_depth_m": ((size, size), "float64"), "ledger": ((count, 5), "float64"),
        "final_internal_q_m3_s": ((faces,), "float64"), "final_boundary_q_m3_s": ((boundary,), "float64")}
    if space:
        specs["H0_m"] = ((128, 128), "float64")
    arrays = read_arrays(directory / "states.npz", specs, expected_sha256=digest)
    return arrays, file_sha256(directory / "manifest.json")


def compare(base_directory, other_directory, *, base_sha256, other_sha256, space=False, tailwater=False):
    base, base_sha = read_states(base_directory, expected_manifest_sha256=base_sha256)
    other, other_sha = read_states(other_directory, expected_manifest_sha256=other_sha256, space=space)
    def authenticated(directory, name):
        manifest = strict_json(Path(directory) / "manifest.json")
        if name not in manifest["artifacts"] or file_sha256(Path(directory) / name) != manifest["artifacts"][name]:
            raise ValueError("comparison authenticated metadata")
        return strict_json(Path(directory) / name)
    base_binding = authenticated(base_directory, "binding.json")
    base_status = authenticated(base_directory, "states.json")["metadata"]
    base_geometry = authenticated(base_directory, "geometry.json")
    if base_geometry["spacing_m"] != 30. or base_geometry["origin_m_xz"] != [-184320., 61440.] or base_geometry["area_m2"] != 58982400.:
        raise ValueError("comparison actual base footprint")
    if space:
        other_binding = authenticated(other_directory, "report.json")
        other_status = other_binding["metadata"]
        if other_binding["origin_m_xz"] != [-184305., 61455.] or other_binding["spacing_m"] != 60. or other_binding["area_m2"] != 58982400.:
            raise ValueError("comparison same spatial footprint")
    else:
        other_binding = authenticated(other_directory, "binding.json")
        other_status = authenticated(other_directory, "states.json")["metadata"]
        other_geometry = authenticated(other_directory, "geometry.json")
        if base_geometry != other_geometry:
            raise ValueError("comparison same original geometry metadata")
        for key, value in base_binding["budget"].items():
            if key in ("max_wall_s", "max_bytes", "max_face_evaluations", "max_substeps"):
                continue
            if not tailwater and key in ("max_dt_s", "inertial_cfl"):
                continue
            if other_binding["budget"][key] != value:
                raise ValueError("comparison fixed non-sensitivity budget")
        base_manifest = strict_json(Path(base_directory) / "manifest.json")
        other_manifest = strict_json(Path(other_directory) / "manifest.json")
        for directory, manifest in ((base_directory, base_manifest), (other_directory, other_manifest)):
            if file_sha256(Path(directory) / "geometry.npz") != manifest["artifacts"]["geometry.npz"]:
                raise ValueError("comparison authenticated boundary geometry")
        base_arrays = read_arrays(Path(base_directory) / "geometry.npz", GEOMETRY, expected_sha256=base_manifest["artifacts"]["geometry.npz"])
        other_arrays = read_arrays(Path(other_directory) / "geometry.npz", GEOMETRY, expected_sha256=other_manifest["artifacts"]["geometry.npz"])
        for key in GEOMETRY.keys() - {"boundary_kind"}:
            if not np.array_equal(base_arrays[key], other_arrays[key]):
                raise ValueError("comparison same bed/shared faces/crests required")
        base_kinds, other_kinds = base_arrays["boundary_kind"], other_arrays["boundary_kind"]
        expected = base_kinds.copy()
        if tailwater:
            expected[np.r_[256 + np.arange(252, 256), 768 + np.arange(252, 256)]] = 2
        if not np.array_equal(base_kinds, np.ones(1024, np.int64)) or not np.array_equal(other_kinds, expected):
            raise ValueError("comparison intended boundary difference only")
    for key in ("source_identity", "height_source_identity", "forcing_manifest_sha256"):
        if base_binding[key] != other_binding[key]:
            raise ValueError("comparison same source/forcing identity")
    if tailwater and (space or Path(other_directory).name != "uniform_heavy_tailwater"):
        raise ValueError("explicit fixed tailwater case only")
    frames = []
    for index, time in enumerate(base["time_s"]):
        matches = np.flatnonzero(np.abs(other["time_s"] - time) < 1e-7)
        if not len(matches):
            continue
        target = int(matches[0])
        left, right = base["depth_m"][index], other["depth_m"][target]
        if space:
            left = left.reshape(128, 2, 128, 2).sum(axis=(1, 3)) / 4.
        delta = right - left
        area = 3600. if space else 900.
        frame = {"time_s": float(time), "max_abs_depth_difference_m": float(abs(delta).max()),
            "RMS_depth_difference_m": float(np.sqrt(np.mean(delta**2))), "volume_L1_difference_m3": float(abs(delta).sum() * area),
            "storage_difference_m3": float(other["ledger"][target, 3] - base["ledger"][index, 3]),
            "external_input_difference_m3": float(other["ledger"][target, 1] - base["ledger"][index, 1]),
            "net_external_output_difference_m3": float((other["ledger"][target, 2] - other["ledger"][target, 1]) - (base["ledger"][index, 2] - base["ledger"][index, 1]))}
        stored = float(base["ledger"][index, 3])
        frame["relative_volume_L1_to_base_storage"] = frame["volume_L1_difference_m3"] / stored if stored > 0 else None
        supplied = float(base["ledger"][index, 0])
        frame["relative_net_output_difference_to_supplied"] = frame["net_external_output_difference_m3"] / supplied if supplied > 0 else None
        if tailwater:
            affected = delta > .001
            wet_union = (left > .001) | (right > .001)
            labels, count = label(wet_union)
            seeds = np.zeros((256, 256), bool)
            seeds[252:, -1] = True
            seeds[-1, 252:] = True
            connected_labels = np.unique(labels[seeds & wet_union])
            connected = affected & np.isin(labels, connected_labels[connected_labels > 0])
            rows, columns = np.nonzero(connected)
            distances = np.sqrt((255 - rows)**2 + (255 - columns)**2) * 30.
            frame["backwater"] = {"positive_depth_difference_threshold_m": .001, "affected_cells": int(affected.sum()),
                "D4_wet_connected_to_tailwater_cells": int(connected.sum()), "maximum_SE_corner_distance_m": float(distances.max(initial=0)),
                "max_positive_stage_change_m": float(delta.max(initial=0)),
                "scope": "D4_saved_wet_mask_connectivity_and_euclidean_distance_not_dynamic_travel_time"}
        frames.append(frame)
    if not any(frame["time_s"] > 0 for frame in frames):
        raise ValueError("comparison requires nonzero common saved time")
    if not np.allclose([base["ledger"][index, 0] for index, time in enumerate(base["time_s"]) if any(abs(frame["time_s"] - time) < 1e-7 for frame in frames)],
                       [other["ledger"][np.argmin(abs(other["time_s"] - frame["time_s"])), 0] for frame in frames], rtol=2e-11, atol=1e-6):
        raise ValueError("comparison identical supplied volume at matched times")
    events = {str(event): {"requested_time_s": event, "actual_saved_time_s": min((frame["time_s"] for frame in frames), key=lambda time: abs(time-event)) if frames else None,
        "exact_saved": bool(any(abs(frame["time_s"] - event) < 1e-7 for frame in frames))} for event in (43200., 86400., 259200.)}
    report = {"base_manifest_sha256": base_sha, "other_manifest_sha256": other_sha,
        "base_run": {key: base_status[key] for key in ("status", "requested_time_s", "committed_time_s", "failure", "wall_s", "substeps", "face_evaluations")},
        "other_run": {key: other_status[key] for key in ("status", "requested_time_s", "committed_time_s", "failure", "wall_s", "substeps", "face_evaluations")},
        "frames": frames, "events": events, "alignment": "exact_common_saved_times_no_state_interpolation",
        "scope": "differences_not_automatic_convergence_or_backwater_physical_certification",
        "tailwater_comparison": tailwater, "common_final_time_s": frames[-1]["time_s"],
        "resource_budgets_may_differ": True,
        "both_saved_full_72h": bool(abs(base["time_s"][-1]-259200.) < 1e-7 and abs(other["time_s"][-1]-259200.) < 1e-7)}
    if space:
        report["spatial"] = {"comparison": "30m_depth_2x2_volume_average_vs_60m_saved_depth_not_same_bed_stage",
            "potential_fill_capacity_30m_m3": 6783370.751953, "potential_fill_capacity_60m_m3": 15616526.879883,
            "capacity_source": "coordinator_independent_D4_diagnostic_only_for_source_81d12179658ed02fefc94883cea1ce32888ff36199952d2bd88f68eb576f8cb2_and_space60_102320",
            "bed_scope": "block_mean_changes_topology_not_pure_convergence"}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("other", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--space", action="store_true")
    parser.add_argument("--tailwater", action="store_true")
    parser.add_argument("--base-sha256", required=True)
    parser.add_argument("--other-sha256", required=True)
    args = parser.parse_args()
    report = compare(args.base, args.other, base_sha256=args.base_sha256, other_sha256=args.other_sha256, space=args.space, tailwater=args.tailwater)
    publish_bytes(args.output, json.dumps(report, indent=2).encode("ascii"))
    print("COMPARISON", args.output)
