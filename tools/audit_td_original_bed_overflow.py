"""Cold-read audit for the original-bed overflow diagnostic package."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import load_overflow_event as load_overflow_event
from terrain_pipeline.basin_storage import load_overflow_topology as load_overflow_topology


def _json(path, value):
    publish_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   allow_nan=False, indent=2).encode("utf-8"))


def audit_saved_arrays(topology, event):
    arrays, metadata = event["arrays"], event["metadata"]
    water = arrays["volume_m3"]
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("nonfinite saved overflow data")
    leaf_lookup = {int(leaf): index for index, leaf in enumerate(topology["arrays"]["leaf_ids"])}
    internal = np.zeros_like(water[:-1])
    boundary = np.zeros_like(internal)
    signed = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    for face_index, face in enumerate(topology["faces"]):
        internal[:, leaf_lookup[face["leaf_ids"][0]]] -= signed[:, face_index]
        internal[:, leaf_lookup[face["leaf_ids"][1]]] += signed[:, face_index]
    for face_index, face in enumerate(topology["engineering_boundaries"]):
        boundary[:, leaf_lookup[face["leaf_id"]]] += arrays["engineering_boundary_outflow_m3"][:, face_index]
    residual = arrays["input_volume_m3"] + internal - boundary - np.diff(water, axis=0)
    if np.any(np.abs(residual) > 1e-7):
        raise ValueError("independent per-basin inventory closure failed")
    config = metadata["parameters"]
    rate = arrays["rain_mm_h"] * config["runoff_coefficient"] / 3_600_000.0 + config["baseflow_mm_per_day"] / 86_400_000.0
    expected_input = rate[:, None] * topology["arrays"]["leaf_area_m2"][None, :] * metadata["timestep_s"]
    if not np.allclose(expected_input, arrays["input_volume_m3"], rtol=0, atol=1e-7):
        raise ValueError("independent rainfall input mismatch")
    if "basin_net_internal_m3" in arrays and not np.allclose(internal, arrays["basin_net_internal_m3"], rtol=0, atol=1e-9):
        raise ValueError("independent net exchange mismatch")
    offsets = topology["arrays"]["curve_offsets"]
    max_stage_error = 0.0
    for leaf_index in range(water.shape[1]):
        start, end = offsets[leaf_index:leaf_index + 2]
        levels = topology["arrays"]["curve_level_m"][start:end]
        area = topology["arrays"]["curve_area_m2"][start:end]
        capacities = levels * np.cumsum(area) - np.cumsum(levels * area)
        stages = np.interp(water[:, leaf_index], capacities, levels)
        above = water[:, leaf_index] > capacities[-1]
        stages[above] = levels[-1] + (water[above, leaf_index] - capacities[-1]) / area.sum()
        max_stage_error = max(max_stage_error, float(np.max(np.abs(stages - arrays["stage_m"][:, leaf_index]))))
    if max_stage_error > 1e-8:
        raise ValueError("independent original-bed storage/stage mismatch")
    forward = arrays["face_forward_m3"].sum(axis=0)
    reverse = arrays["face_reverse_m3"].sum(axis=0)
    gross = forward + reverse
    canceled = 2.0 * np.minimum(forward, reverse)
    initial, final = float(water[0].sum()), float(water[-1].sum())
    supplied, exported = float(arrays["input_volume_m3"].sum()), float(boundary.sum())
    return {
        "total_input_m3": supplied, "initial_storage_m3": initial, "final_storage_m3": final,
        "storage_change_m3": final - initial, "engineering_boundary_outflow_m3": exported,
        "whole_event_residual_m3": supplied - exported - (final - initial),
        "max_abs_basin_residual_m3": float(np.max(np.abs(residual))),
        "max_abs_step_internal_sum_m3": float(np.max(np.abs(internal.sum(axis=1)))),
        "max_stage_inversion_error_m": max_stage_error,
        "gross_forward_m3": float(forward.sum()), "gross_reverse_m3": float(reverse.sum()),
        "gross_exchange_m3": float(gross.sum()),
        "sum_absolute_cumulative_face_net_m3": float(np.abs(forward - reverse).sum()),
        "canceled_bidirectional_exchange_m3": float(canceled.sum()),
        "canceled_fraction_of_gross": float(canceled.sum() / gross.sum()) if gross.sum() else 0.0,
        "bidirectional_face_count": int(np.count_nonzero((forward > 0) & (reverse > 0))),
        "spill_face_count": int(np.count_nonzero(arrays["spill_onset_step"] >= 0)),
        "round_trip_semantics": "2*min(cumulative forward, cumulative reverse) is canceled directional volume, not tracked water particles or new input",
        "max_abs_balance_residual_m3": float(np.max(np.abs(arrays["balance_residual_m3"]))),
    }


def audit(directory, *, expected_index_sha256=None):
    directory = Path(directory)
    index_sha256 = file_sha256(directory / "index.json")
    if expected_index_sha256 is not None and index_sha256 != expected_index_sha256:
        raise ValueError("overflow index external hash mismatch")
    index = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    source_pin = index["input_pins"]["original_td"]
    if file_sha256(source_pin["path"]) != source_pin["sha256"]:
        raise ValueError("original TD source pin mismatch")
    hierarchy_pin = index["input_pins"]["hierarchy"]
    hierarchy = load_basin_hierarchy(hierarchy_pin["path"], expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    topology_pin = index["topology"]
    topology = load_overflow_topology(directory / Path(topology_pin["path"]).name,
                                      expected_sha256=topology_pin["sha256"],
                                      expected_identity=topology_pin["identity_sha256"])
    if topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("topology/hierarchy identity mismatch")
    records = []
    for case in index["cases"]:
        event_pin = case["event"]
        event = load_overflow_event(directory / Path(event_pin["path"]).name,
                                    expected_sha256=event_pin["sha256"],
                                    expected_identity=case["event_identity_sha256"], topology=topology)
        records.append(dict(audit_saved_arrays(topology, event), name=case["name"],
                            identity_sha256=event["identity_sha256"],
                            hydraulic_ready=False, natural_outlet_verified=False))
    if file_sha256(directory / "index.json") != index_sha256:
        raise ValueError("overflow index changed during audit")
    report = {"schema": "td-original-bed-overflow-independent-audit-v2", "status": "passed",
              "directory": str(directory), "topology_identity_sha256": topology["identity_sha256"],
              "index_sha256": index_sha256,
              "scope": "independent saved face divergence, rainfall and per-basin inventory closure; not numerical convergence or controlled backwater certification",
              "cases": records, "cold_read": True, "solver_advanced": False,
              "natural_outlet_verified": False, "hydraulic_ready": False, "publishable": False}
    _json(directory / "independent-audit.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-index-sha256")
    args = parser.parse_args()
    print(json.dumps(audit(args.directory, expected_index_sha256=args.expected_index_sha256), ensure_ascii=False))
