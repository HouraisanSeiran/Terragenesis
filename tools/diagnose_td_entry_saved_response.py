"""Separate upstream pulse propagation from engineering lake inflow using saved cuts."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import publish_bytes
from tools.audit_td_entry_shallow_water import read_bundle, read_json, check_memory


def diagnose(index, audit):
    if audit["status"] != "passed" or not audit["local_saved_hydraulics_verified"]:
        raise ValueError("saved local hydraulic audit required")
    bed, geometry = (read_bundle(index[key]) for key in ("carrier", "geometry"))
    distance = bed["arrays"]["longitudinal_from_upstream_m"].ravel()
    center = bed["arrays"]["centerline_offset_m"].ravel() <= .175
    left, right = (geometry["arrays"][key] for key in ("face_left", "face_right"))
    reports = []
    for case in index["cases"]:
        if case["level"] != 1:
            continue
        state, transfers = (read_bundle(case[key]) for key in ("state", "intervals"))
        depth = state["arrays"]["depth_m"].reshape(-1, len(distance))
        cuts = []
        for station in (5., 30., 60.):
            forward = (distance[left] < station) & (distance[right] >= station)
            backward = (distance[right] < station) & (distance[left] >= station)
            transfer = transfers["arrays"]["internal_transfer_m3"]
            signed = transfer[:, forward].sum(axis=1)-transfer[:, backward].sum(axis=1)
            cuts.append(dict(station_m=station, signed_interval_downstream_m3=signed.tolist(),
                             cumulative_downstream_m3=float(signed.sum()),
                             interval_forward_m3=float(np.maximum(signed, 0).sum()),
                             interval_reverse_m3=float(np.maximum(-signed, 0).sum()),
                             gross_substep_direction_certified=False))
        fronts = [float(distance[(row > 1e-6) & center & (distance < 60)].max(initial=0)) for row in depth]
        reports.append(dict(case_name=case["case_id"], time_s=state["arrays"]["time_s"].tolist(),
                            centerline_land_wet_front_m=fronts, cuts=cuts,
                            supplied_m3=state["metadata"]["supplied_m3"],
                            engineering_lake_input_m3=state["metadata"]["boundary_input_m3"],
                            engineering_lake_output_m3=state["metadata"]["boundary_output_m3"],
                            pulse_volume_attribution_verified=False))
    normal = next(item for item in reports if item["case_name"].startswith("normal-pulse"))
    at_lake = next(item for item in normal["cuts"] if item["station_m"] == 60.)
    return dict(schema="td-entry-saved-response-diagnostic-v1", status="diagnostic_only", cases=reports,
                ordinary_pulse_positive_net_crosses_60m=at_lake["cumulative_downstream_m3"] > 1e-12,
                upstream_pulse_to_lake_verified=False, tracer_attribution_verified=False,
                natural_outlet_verified=False, full_river_verified=False,
                semantics="signed cuts are net saved interval transfers; engineering lake inflow is separate from injected upstream supply; no rerun or particle attribution",
                actual_peak_rss_bytes=check_memory())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index = read_json(dict(path=str(args.input.resolve()), sha256=args.sha256))
    audit = read_json(dict(path=str(args.audit.resolve()), sha256=args.audit_sha256))
    if audit["index_sha256"] != args.sha256:
        raise ValueError("response audit bound to different event")
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"verification/natural-river-network"):
        raise ValueError("new response diagnostic output required")
    result = diagnose(index, audit)
    result.update(index_sha256=args.sha256, audit_sha256=args.audit_sha256)
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode())
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
