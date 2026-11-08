"""Measure saved growth controls; differences are nonlinear responses, not tracers."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256
from tools.inspect_natural_fv_growth import read_arrays, max_difference


def measurements(run, arrays):
    h = arrays["depth_m"][-1]
    bed = arrays["bed_m"][-1]
    delta = bed - arrays["bed_m"][0]
    sea = np.broadcast_to((np.arange(h.shape[0]) * 5. - 360. >= 0.)[:, None], h.shape)
    dry = h <= 2.e-6
    original_sea = sea & (arrays["initial_bed_m"] < 0.)
    deposited = np.zeros_like(h)
    river_volume = 0.
    for path in sorted(run.glob("chunk-audit-*.npz")):
        with np.load(path) as block:
            deposited += block["suspended_deposited_solid_m3"].reshape(h.shape)
            river_volume += float(block["water_forcing_volume_m3"].sum())
    sample_count = min(3, len(arrays["time_s"]) - 1)
    persistent = np.all(arrays["depth_m"][-sample_count:] <= 2.e-6, axis=0)
    momentum = arrays["momentum_m2_s"][-1].reshape(*h.shape, 2)
    velocity = np.divide(np.linalg.norm(momentum, axis=2), h, out=np.zeros_like(h), where=h > .01)
    concentration = np.divide(arrays["suspended_solid_m3"][-1], h * 25., out=np.zeros_like(h), where=h > 2.e-6)
    report = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    return {"path": str(run), "result_sha256": file_sha256(run / "result.npz"),
        "parameters": report["parameters"], "elapsed_s": float(arrays["time_s"][-1] - arrays["time_s"][0]),
        "resumed_checkpoint_sha256": report["start"].get("resumed_checkpoint_sha256"),
        "actual_river_forcing_volume_m3": river_volume,
        "mean_actual_river_forcing_q_m3_s": river_volume / float(arrays["time_s"][-1] - arrays["time_s"][0]),
        "start_time_s": float(arrays["time_s"][0]), "end_time_s": float(arrays["time_s"][-1]),
        "new_injected_solid_m3": report["injected_solid_m3"], "exported_solid_m3": report["exported_solid_m3"],
        "remaining_source_solid_m3": report["remaining_finite_source_solid_m3"],
        "initial_suspended_solid_m3": float(arrays["suspended_solid_m3"][0].sum()),
        "final_suspended_solid_m3": float(arrays["suspended_solid_m3"][-1].sum()),
        "seaward_final_suspended_solid_m3": float(arrays["suspended_solid_m3"][-1][sea].sum()),
        "gross_settled_solid_m3": float(deposited.sum()), "seaward_gross_settled_solid_m3": float(deposited[sea].sum()),
        "positive_bed_change_bulk_m3": float(np.maximum(delta, 0.).sum() * 25.),
        "negative_bed_change_bulk_m3": float(np.minimum(delta, 0.).sum() * 25.),
        "net_bed_change_solid_m3": float(delta.sum() * 25. * .65),
        "actual_sea_dry_area_m2": float(np.count_nonzero(original_sea & dry) * 25.),
        "sea_thin_water_area_m2": float(np.count_nonzero(original_sea & (h > 2.e-6) & (h <= .01)) * 25.),
        "sea_dry_all_last_saved_states_area_m2": float(np.count_nonzero(original_sea & persistent) * 25.),
        "dry_persistence_sample_count": sample_count, "dry_persistence_start_time_s": float(arrays["time_s"][-sample_count]),
        "maximum_actual_wet_speed_m_s": float(velocity.max()), "maximum_final_concentration": float(concentration.max()),
        "water_volume_m3": float(h.sum() * 25.)}


def compare(run_a, run_b, output, label_a, label_b):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    a, b = read_arrays(run_a / "result.npz"), read_arrays(run_b / "result.npz")
    ra, rb = measurements(run_a, a), measurements(run_b, b)
    initial_errors = {key: max_difference(a[key][0], b[key][0]) for key in
        ("bed_m", "depth_m", "momentum_m2_s", "suspended_solid_m3")}
    static_errors = {key: max_difference(a[key], b[key]) for key in ("source_floor_m", "local_world_xz_m")}
    same_initial = all(value <= 1.e-12 for value in (*initial_errors.values(), *static_errors.values()))
    matched_time = abs(ra["elapsed_s"] - rb["elapsed_s"]) <= 1.e-9 and abs(ra["start_time_s"] - rb["start_time_s"]) <= 1.e-9
    schedules = []
    for directory in (run_a, run_b):
        records = json.loads((directory / "interval-ledgers.json").read_text(encoding="utf-8"))
        schedules.append(np.asarray([[row["physical_time_start_s"], row["physical_time_end_s"]] for row in records]))
    schedule_error = max_difference(schedules[0], schedules[1])
    same_schedule = schedule_error <= 1.e-9
    interval_distributions = []
    for schedule in schedules:
        values, counts = np.unique(np.round(schedule[:, 1] - schedule[:, 0], 12), return_counts=True)
        interval_distributions.append([{"interval_s": float(value), "count": int(count)} for value, count in zip(values, counts)])
    excluded = {"output", "resume", "packet_stride", "max_wall_s", "max_bytes_mib", "chunk_intervals", "parent", "water_run"}
    differences = {key: {label_a: ra["parameters"].get(key), label_b: rb["parameters"].get(key)}
        for key in set(ra["parameters"]) | set(rb["parameters"])
        if key not in excluded and ra["parameters"].get(key) != rb["parameters"].get(key)}
    bed_difference = b["bed_m"][-1] - a["bed_m"][-1]
    depth_difference = b["depth_m"][-1] - a["depth_m"][-1]
    suspended_difference = b["suspended_solid_m3"][-1] - a["suspended_solid_m3"][-1]
    numeric_differences = {key: rb[key] - ra[key] for key in ra if isinstance(ra[key], (float, int))}
    report = {"schema": "actual-fv-control-comparison-v1", "labels": [label_a, label_b],
        "same_initial_state": same_initial, "matched_physical_times": matched_time,
        "same_actual_coupling_interval_sequence": same_schedule,
        "maximum_interval_endpoint_mismatch_s": schedule_error if np.isfinite(schedule_error) else None,
        "actual_interval_distributions": interval_distributions,
        "strict_discrete_control_match": same_initial and matched_time and same_schedule,
        "same_resumed_checkpoint": bool(ra["resumed_checkpoint_sha256"] and ra["resumed_checkpoint_sha256"] == rb["resumed_checkpoint_sha256"]),
        "same_mean_actual_river_q": abs(ra["mean_actual_river_forcing_q_m3_s"] - rb["mean_actual_river_forcing_q_m3_s"]) <= 1.e-8,
        "comparison_valid_for_matched_controls": same_initial and matched_time and same_schedule,
        "comparison_valid_for_same_state_time_description": same_initial and matched_time,
        "initial_state_max_errors": initial_errors, "static_state_max_errors": static_errors,
        "physical_parameter_differences": differences, "runs": [ra, rb], "B_minus_A_measurements": numeric_differences,
        "maximum_absolute_bed_difference_m": float(abs(bed_difference).max()),
        "maximum_absolute_water_depth_difference_m": float(abs(depth_difference).max()),
        "bed_difference_l1_bulk_m3": float(abs(bed_difference).sum() * 25.),
        "signed_bed_difference_solid_m3": float(bed_difference.sum() * 25. * .65),
        "scope": "B-A is the coupled nonlinear response to declared control differences; it is not a direct new-source tracer or source-only deposited mass. Gross settling includes inherited suspended inventory; bed change includes MPM redistribution. Different actual coupling interval sequences add a discretization difference and prevent attributing the entire response to wave/forcing differences.",
        "dry_scope": "actual dry threshold 2e-6m; thin water to 1cm separate; last saved-state intersection is not proof of permanent emergence"}
    output.mkdir(parents=True, exist_ok=False)
    (output / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    np.savez_compressed(output / "differences.npz", bed_B_minus_A_m=bed_difference, depth_B_minus_A_m=depth_difference,
        suspended_B_minus_A_solid_m3=suspended_difference, local_world_xz_m=a["local_world_xz_m"])
    fig, axes = plt.subplots(2, 3, figsize=(18, 11), constrained_layout=True)
    extent = [-602.5, 597.5, 737.5, -362.5]
    for ax, field, title, unit, diverging in (
            (axes[0, 0], a["bed_m"][-1] - a["bed_m"][0], label_a + " net bed change", "m", True),
            (axes[0, 1], b["bed_m"][-1] - b["bed_m"][0], label_b + " net bed change", "m", True),
            (axes[0, 2], bed_difference, "B - A bed response", "m", True),
            (axes[1, 0], a["depth_m"][-1], label_a + " actual depth", "m", False),
            (axes[1, 1], b["depth_m"][-1], label_b + " actual depth", "m", False),
            (axes[1, 2], depth_difference, "B - A water depth", "m", True)):
        limit = max(float(abs(field).max()), 1.e-12)
        options = {"vmin": -limit, "vmax": limit} if diverging else {"vmin": 0.}
        image = ax.imshow(field, extent=extent, cmap="RdBu_r" if diverging else "Blues", **options)
        fig.colorbar(image, ax=ax, label=unit, shrink=.8)
        ax.axhline(0., color="#333333", linewidth=.5)
        ax.set(title=title, xlabel="Cross stream (m)", ylabel="Station (m)")
    fig.suptitle("Matched state, time and coupling intervals" if same_initial and matched_time and same_schedule
        else "Coupling intervals differ: mixed physical and discretization response" if same_initial and matched_time
        else "Unmatched states: descriptive differences only")
    fig.text(.5, .01, "B - A is a nonlinear coupled response, not a source tracer. All water depths and beds are read from saved states.", ha="center", fontsize=10)
    fig.savefig(output / "control-comparison.png", dpi=170)
    plt.close(fig)
    return {key: value for key, value in report.items() if key not in ("runs", "B_minus_A_measurements")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-a", type=Path, required=True)
    parser.add_argument("--run-b", type=Path, required=True)
    parser.add_argument("--label-a", default="Control A")
    parser.add_argument("--label-b", default="Control B")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.run_a, args.run_b, args.output, args.label_a, args.label_b), indent=2))
