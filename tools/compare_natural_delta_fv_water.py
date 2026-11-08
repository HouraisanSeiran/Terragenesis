"""Compare saved reference and accelerated fixed-bed FV experiments."""
import argparse
import json
from pathlib import Path

import numpy as np


def compare(reference, accelerated):
    reports = [json.loads((path / "summary.json").read_text(encoding="utf-8"))
        for path in (reference, accelerated)]
    if reports[0]["parent_sha256"] != reports[1]["parent_sha256"] or reports[0]["forcing"] != reports[1]["forcing"]:
        raise ValueError("matching parent and forcing required")
    state_errors = {}
    roundoff_tolerance_match = True
    with np.load(reference / "result.npz") as first, np.load(accelerated / "result.npz") as second:
        for name in first.files:
            roundoff_tolerance_match &= bool(np.allclose(first[name], second[name], rtol=2.e-10, atol=2.e-9))
            state_errors[name] = float(np.max(abs(first[name] - second[name])))
    packet_errors = {}
    for path in sorted((reference / "intervals").glob("*.npz")):
        if path.stem.endswith("first-substep"):
            continue
        with np.load(path) as first, np.load(accelerated / "intervals" / path.name) as second:
            for name in first.files:
                roundoff_tolerance_match &= bool(np.allclose(first[name], second[name], rtol=2.e-10, atol=2.e-9))
                packet_errors[name] = max(packet_errors.get(name, 0.), float(np.max(abs(first[name] - second[name]))))
    closure = []
    for directory in (reference, accelerated):
        maximum = 0.
        with np.load(directory / "result.npz") as geometry:
            for path in sorted((directory / "intervals").glob("*.npz")):
                if path.stem.endswith("first-substep"):
                    continue
                with np.load(path) as packet:
                    net = packet["forcing_volume_m3"].copy()
                    np.add.at(net, geometry["face_left"], -packet["internal_transfer_m3"])
                    np.add.at(net, geometry["face_right"], packet["internal_transfer_m3"])
                    np.add.at(net, geometry["boundary_cell"], -packet["boundary_transfer_m3"])
                    # Infer cell area from the saved whole-domain initial volume.
                    area = reports[0]["metadata"]["initial_volume_m3"] / geometry["initial_depth_m"].sum()
                    residual = (packet["depth_after_m"] - packet["depth_before_m"]) * area - net
                    maximum = max(maximum, float(abs(residual).max()))
        closure.append(maximum)
    walls = [report["metadata"]["wall_s"] for report in reports]
    result = {"reference": str(reference), "accelerated": str(accelerated),
        "parent_and_forcing_match": True, "all_shared_states_and_interval_fields_match_tolerance": roundoff_tolerance_match,
        "comparison_atol": 2.e-9, "comparison_rtol": 2.e-10,
        "state_max_abs_differences": state_errors, "interval_max_abs_differences": packet_errors,
        "maximum_per_cell_water_closure_error_m3_reference_accelerated": closure,
        "wall_s_reference_accelerated": walls, "measured_speedup": walls[0] / walls[1],
        "acceleration_wall_s_includes_cached_JIT_startup": True,
        "projected_3h_wall_s_linear": walls[1] * 10800. / reports[1]["metadata"]["committed_time_s"],
        "projected_44714s_wall_s_linear": reports[1]["projected_44714s_wall_s_linear"],
        "projection_limitation": "short-run linear estimate; later CFL and wetting may change runtime"}
    (accelerated / "reference-comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--accelerated", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.reference, args.accelerated), indent=2))
