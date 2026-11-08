"""Declared finite +9m geological scenario continued from a saved source year.

Repeats the prescribed water year only. Never resets loose/mobile stores or
reissues old exports. Normal-flow closure rejects actual flat/adverse grades.
No new sediment is connected to any delta by this diagnostic runner.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.common_infra import file_sha256, identity
from terrain_pipeline.surface_rivers.metric_dynamic_feedback import bed_slopes, normal_depth
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters
from terrain_pipeline.surface_rivers.metric_upstream_sediment import load_daily_sediment, route_daily_sediment
from tools.verify_fluvial_channel_remobilization import resource_limits


def run_bundle(bundle, output, *, years=1, added_rock_thickness_m=9., source_path=None):
    if type(years) is not int or not 1 <= years <= 10 or not np.isfinite(added_rock_thickness_m) or added_rock_thickness_m < 0.:
        raise ValueError("1..10 assumed water years and finite nonnegative one-time added rock thickness required")
    a, metadata = bundle["arrays"], bundle["metadata"]
    if np.any(a["external_solid_m3_s"] != 0.):
        raise ValueError("cannot repeat external sediment supply without a separate explicit finite source")
    material = MaterialParameters(**metadata["material"])
    p = material.porosity
    area = a["area_m2"]
    old_floor = a["rock_floor_m"].copy()
    floor = old_floor - added_rock_thickness_m
    current = a["trace_bed_m"][-1].copy()
    loose = a["trace_loose_solid_m3"][-1].copy()
    mobile = a["trace_mobile_solid_m3"][-1].copy()
    old_removed = a["trace_rock_removed_m3"][-1].copy()
    old_reserve = (a["bed_elevation_m"] - a["initial_alluvium_bulk_m3"] / area - old_floor) * area
    old_remaining = old_reserve - old_removed
    if old_remaining.min() < -1.e-7:
        raise ValueError("invalid parent rock inventory")
    new_initial_reserve = np.maximum((current - loose / ((1. - p) * area) - floor) * area, 0.)
    new_removed = np.zeros_like(current)
    start_time = float(a["time_seconds"][-1])
    hydro_duration = np.diff(a["time_seconds"])
    repeated_year_s = float(hydro_duration.sum())
    xz = a["node_xz_m"]
    receiver = a["receiver"]
    roughness = float(metadata.get("manning_roughness", .035))
    terminal_slope = metadata.get("terminal_slope")
    output.mkdir(parents=True, exist_ok=False)
    (output / "daily").mkdir()
    implementations = ("tools/run_finite_multiyear_source.py", "terrain_pipeline/surface_rivers/metric_dynamic_feedback.py",
        "terrain_pipeline/surface_rivers/metric_upstream_sediment.py", "terrain_pipeline/surface_rivers/metric_bed_update.py")
    hashes = {name: file_sha256(ROOT / name) for name in implementations}
    traces = {"trace_bed_m": [current.copy()], "trace_loose_solid_m3": [loose.copy()],
        "trace_mobile_solid_m3": [mobile.copy()], "trace_added_scenario_rock_removed_solid_m3": [new_removed.copy()],
        "trace_lifetime_rock_removed_solid_m3": [old_removed.copy()]}
    daily = {name: [] for name in ("water_q_m3_s", "water_depth_m", "friction_slope", "eroded_rock_m3",
        "exported_solid_m3", "eroded_loose_solid_m3", "deposited_solid_m3", "incoming_solid_m3", "outgoing_solid_m3")}
    times = [start_time]
    failure = None
    annual = []
    initial_stores = float((loose + mobile).sum())
    cumulative_export = 0.
    for year in range(years):
        start_export = cumulative_export
        for day, dt in enumerate(hydro_duration):
            try:
                slopes = bed_slopes(receiver, current, xz, terminal_slope)
                q = a["water_q_m3_s"][day]
                depth = np.asarray([normal_depth(float(flow), float(width), float(slope), roughness)
                    for flow, width, slope in zip(q, a["width_m"], slopes)])
                hydraulic_id = identity({"q": q, "depth": depth, "slope": slopes},
                    {"scenario": "finite-new-geological-layer", "year": year + 1, "day": day, "roughness": roughness})
                one = route_daily_sediment(receiver=receiver, length_m=a["length_m"], width_m=a["width_m"],
                    bed_elevation_m=current, water_depth_m=depth[None], water_q_m3_s=q[None], friction_slope=slopes[None],
                    time_seconds=np.asarray([times[-1], times[-1] + dt]), rock_floor_m=floor,
                    initial_alluvium_bulk_m3=loose / (1. - p), initial_mobile_solid_m3=mobile,
                    hardness=a["hardness_source"], material=material, retention_fraction=a["retention_fraction"],
                    external_solid_m3_s=np.zeros((1, current.size)),
                    geometry_identity_sha256=metadata["geometry_identity_sha256"], hydraulic_identity_sha256=hydraulic_id,
                    material_provenance=metadata["material_provenance"] + "; declared one-time deeper finite geological layer")
                r = one["arrays"]
                # Do not deliver an interval whose new bed invalidates the next
                # normal-flow state. Keep the full proposed failing transition.
                try:
                    bed_slopes(receiver, r["trace_bed_m"][-1], xz, terminal_slope)
                except ValueError:
                    np.savez_compressed(output / "rejected-day-proposal.npz", **r)
                    raise
            except ValueError as error:
                failure = {"year": year + 1, "day_index": day, "time_start_s": times[-1],
                    "reason": str(error), "rejected_proposal_not_delivered": (output / "rejected-day-proposal.npz").exists()}
                break
            # One-day ledgers use a local rock-removal origin; the scenario
            # ledger below carries both new increments and old lifetime debit.
            np.savez_compressed(output / "daily" / f"{year + 1:02d}-{day:03d}.npz", **r)
            current = r["trace_bed_m"][-1].copy()
            loose = r["trace_loose_solid_m3"][-1].copy()
            mobile = r["trace_mobile_solid_m3"][-1].copy()
            new_removed += r["eroded_rock_m3"][0]
            cumulative_export += float(r["exported_solid_m3"].sum())
            times.append(times[-1] + float(dt))
            for name, value in (("trace_bed_m", current), ("trace_loose_solid_m3", loose), ("trace_mobile_solid_m3", mobile),
                    ("trace_added_scenario_rock_removed_solid_m3", new_removed), ("trace_lifetime_rock_removed_solid_m3", old_removed + new_removed)):
                traces[name].append(value.copy())
            for name in daily:
                daily[name].append(r[name][0].copy())
        annual.append({"year": year + 1, "completed": failure is None,
            "exported_solid_m3": cumulative_export - start_export,
            "remaining_rock_solid_m3": float((new_initial_reserve - new_removed).sum()),
            "remaining_loose_solid_m3": float(loose.sum()), "remaining_mobile_solid_m3": float(mobile.sum())})
        if failure is not None:
            break
    arrays = {name: np.asarray(values) for name, values in traces.items()}
    arrays.update({name: np.asarray(values).reshape(-1, current.size) for name, values in daily.items()})
    arrays.update(time_seconds=np.asarray(times), old_rock_floor_m=old_floor, rock_floor_m=floor,
        old_rock_removed_solid_m3=old_removed, old_rock_reserve_solid_m3=old_reserve,
        initial_scenario_rock_reserve_solid_m3=new_initial_reserve,
        remaining_rock_solid_m3=np.maximum(new_initial_reserve - new_removed, 0.),
        appended_rock_solid_m3=added_rock_thickness_m * area,
        node_xz_m=xz, receiver=receiver, area_m2=area, length_m=a["length_m"], width_m=a["width_m"], hardness_source=a["hardness_source"])
    np.savez_compressed(output / "result.npz", **arrays)
    residual = initial_stores + float(new_removed.sum()) - float((loose + mobile).sum()) - cumulative_export
    summary = {"schema": "finite-one-time-deeper-geological-layer-repeated-water-year-v1",
        "status": "failed-normal-flow-closure" if failure else "completed", "failure": failure,
        "source_path": str(source_path) if source_path else None,
        "source_sha256": file_sha256(source_path) if source_path else None, "source_identity_sha256": bundle["identity_sha256"],
        "scenario": "counterfactual geological material layer, not observed multiyear watershed; no sediment delivered to delta yet",
        "assumed_repeated_water_years": years, "repeated_water_year_s": repeated_year_s,
        "physical_start_time_s": start_time, "physical_committed_end_time_s": times[-1], "accepted_intervals": len(times) - 1,
        "source_nodes": int(current.size), "source_area_m2": float(area.sum()),
        "one_time_added_rock_thickness_m": added_rock_thickness_m,
        "one_time_added_rock_solid_m3": float(added_rock_thickness_m * area.sum()),
        "old_rock_removed_solid_m3": float(old_removed.sum()), "new_rock_removed_solid_m3": float(new_removed.sum()),
        "lifetime_rock_removed_solid_m3": float((old_removed + new_removed).sum()),
        "remaining_scenario_rock_solid_m3": float((new_initial_reserve - new_removed).sum()),
        "initial_carried_loose_solid_m3": float(traces["trace_loose_solid_m3"][0].sum()),
        "initial_carried_mobile_solid_m3": float(traces["trace_mobile_solid_m3"][0].sum()),
        "final_loose_solid_m3": float(loose.sum()), "final_mobile_solid_m3": float(mobile.sum()),
        "new_deliverable_export_solid_m3": cumulative_export, "old_exports_reissued_solid_m3": 0.,
        "external_solid_m3": 0., "global_residual_solid_m3": residual, "annual": annual,
        "material": asdict(material), "manning_roughness": roughness,
        "hydraulics": "daily actual geometric grades and rectangular Manning normal depth recomputed; no backwater or transient flow; adverse slopes rejected without editing heights",
        "implementation_hashes": hashes, "implementation_unchanged": all(file_sha256(ROOT / name) == digest for name, digest in hashes.items())}
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "verification/fluvial-delta/adaptive-tree-16km-20261018-02/feedback_bundle.npz")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--years", type=int, default=1)
    parser.add_argument("--added-rock-thickness-m", type=float, default=9.)
    args = parser.parse_args()
    resource_limits()
    source = load_daily_sediment(args.source, file_sha256(args.source))
    print(json.dumps(run_bundle(source, args.output, years=args.years,
        added_rock_thickness_m=args.added_rock_thickness_m, source_path=args.source), indent=2))
