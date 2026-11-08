"""Continue actual native TD checkpoint with only a new finite source export."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.surface_rivers.metric_natural_delta import NaturalDeltaConfig, finite_schedule
from terrain_pipeline.surface_rivers.metric_natural_delta_continuation import continue_natural_delta, CHECKPOINT_GRIDS
from tools.run_natural_delta import morphology_evidence
from tools.verify_fluvial_channel_remobilization import resource_limits

IMPLEMENTATIONS = ("tools/continue_natural_delta.py", "terrain_pipeline/surface_rivers/metric_natural_delta_continuation.py",
    "terrain_pipeline/surface_rivers/metric_natural_delta.py", "terrain_pipeline/surface_rivers/metric_fluvial_native_routers.py",
    "terrain_pipeline/surface_rivers/metric_fluvial_water_repair.py", "terrain_pipeline/surface_rivers/metric_fluvial_morphodynamics.py")


def consumed_sources(parent_report):
    consumed = set(parent_report.get("consumed_source_sha256s", []))
    source_sha256 = parent_report.get("forcing", {}).get("source_sha256")
    if source_sha256:
        consumed.add(source_sha256)
    return sorted(consumed)


def prepare(parent, new_source, *, max_step_solid_m3=1000.):
    if not np.isfinite(max_step_solid_m3) or max_step_solid_m3 <= 0.:
        raise ValueError("positive finite sediment packet size required")
    parent_report = json.loads((parent / "summary.json").read_text(encoding="utf-8"))
    inherited_consumed = consumed_sources(parent_report)
    new_source_sha256 = file_sha256(new_source / "result.npz")
    if new_source_sha256 in inherited_consumed:
        raise ValueError("new source was already consumed in parent ancestry; restarting its export would redeliver sediment")
    source_report = json.loads((new_source / "summary.json").read_text(encoding="utf-8"))
    if source_report["status"] != "completed" or source_report["old_exports_reissued_solid_m3"] != 0.:
        raise ValueError("completed new finite source scenario without recycled exports required")
    if parent_report.get("zero_supply") or parent_report.get("reference_erosion"):
        raise ValueError("parent must be the non-reference finite-supply natural experiment")
    cfg = dict(parent_report["config"])
    cfg["shape"] = tuple(cfg["shape"])
    config = replace(NaturalDeltaConfig(**cfg), max_step_solid_m3=max_step_solid_m3)
    with np.load(parent / "result.npz") as saved:
        parent_arrays = {name: saved[name].copy() for name in saved.files}
    with np.load(new_source / "result.npz") as saved:
        q = saved["water_q_m3_s"][:, -1].copy()
        solid = saved["exported_solid_m3"].sum(axis=1)
        duration = np.diff(saved["time_seconds"])
        real_times = saved["time_seconds"].copy()
    np.testing.assert_allclose(solid.sum(), source_report["new_deliverable_export_solid_m3"], atol=1.e-8, rtol=0.)
    schedule = finite_schedule(q, solid, duration, config, mode="mechanism")
    checkpoint = parent / "backend/checkpoint.npz"
    with np.load(checkpoint) as saved:
        inventory = {name: {"shape": list(saved[name].shape), "dtype": str(saved[name].dtype)} for name in CHECKPOINT_GRIDS}
        for name, key in (("eta", "bed_m"), ("depth", "depth_m"), ("stage", "stage_m"), ("qx", "qx_m2_s"), ("qy", "qz_m2_s")):
            np.testing.assert_array_equal(saved[name], parent_arrays[key][-1])
        checkpoint_time = float(saved["time"])
        checkpoint_step = int(saved["time_iter"])
    forcing = {"source": str(new_source / "result.npz"), "source_sha256": new_source_sha256,
        "source_summary": str(new_source / "summary.json"), "source_summary_sha256": file_sha256(new_source / "summary.json"),
        "new_geological_source_solid_m3": float(solid.sum()), "old_annual_input_repeated_solid_m3": 0.,
        "old_parent_input_solid_m3": float(parent_arrays["cumulative_input_solid_m3"][-1]),
        "daily_input_solid_m3": solid.tolist(), "daily_water_q_m3_s": q.tolist(),
        "real_source_start_time_s": float(real_times[0]), "real_source_end_time_s": float(real_times[-1]),
        "real_source_water_m3": float(np.sum(q * duration)),
        "scheduled_solid_m3": float(schedule[:, 3].sum()), "schedule_steps": len(schedule),
        "max_step_solid_m3": max_step_solid_m3, "parent_max_step_solid_m3": parent_report["config"]["max_step_solid_m3"],
        "scheduled_mechanism_duration_s": float(schedule[:, 4].sum()),
        "scheduled_mechanism_water_m3": float(np.sum(schedule[:, 2] * schedule[:, 4])),
        "semantics": "independent coarser finite-packet mechanism chronology, not actual annual water chronology; same real new export once, no old sediment redelivery"}
    provenance = {"parent_result": str(parent / "result.npz"), "parent_result_sha256": file_sha256(parent / "result.npz"),
        "parent_summary": str(parent / "summary.json"), "parent_summary_sha256": file_sha256(parent / "summary.json"),
        "parent_checkpoint": str(checkpoint), "parent_checkpoint_sha256": file_sha256(checkpoint),
        "checkpoint_inventory": inventory, "checkpoint_rng": "native saved object RNG tuple, restored and checked by the native resume path",
        "checkpoint_time_s": checkpoint_time, "checkpoint_step": checkpoint_step,
        "inherited_consumed_source_sha256s": inherited_consumed,
        "source_floor_parent_archive": "source_floor_m inherited exactly, never reset to parent final bed minus cover",
        "final_bed_tide_handoff": "new final native bed requires a new FV hydraulic relaxation/tidal run; old TD02 low-tide water may not be copied onto it"}
    return parent_arrays, config, schedule, forcing, provenance


def run(parent, new_source, output, *, max_step_solid_m3=1000., steps=None, prepare_only=False):
    parent_arrays, config, schedule, forcing, provenance = prepare(parent, new_source, max_step_solid_m3=max_step_solid_m3)
    hashes = {name: file_sha256(ROOT / name) for name in IMPLEMENTATIONS}
    if prepare_only:
        output.mkdir(parents=True, exist_ok=False)
        np.savez_compressed(output / "schedule.npz", schedule=schedule)
        report = {"status": "prepared-only", "forcing": forcing, "provenance": provenance}
    else:
        started = time.perf_counter()
        arrays, report = continue_natural_delta(parent, parent_arrays, schedule, output, config, steps=steps,
            progress=lambda step, seconds, solid: print("PROGRESS", step, "native_seconds", seconds,
                "new_input_solid_m3", solid, "wall_s", time.perf_counter() - started, flush=True))
        report.update(status="completed", forcing=forcing, provenance=provenance, runtime_s=time.perf_counter() - started)
        # Even a partial diagnostic child cannot restart this finite source from its beginning.
        report["consumed_source_sha256s"] = sorted(set(provenance["inherited_consumed_source_sha256s"]) | {forcing["source_sha256"]})
        report["morphology_evidence"] = morphology_evidence(arrays)
        report["new_packet_schedule_scope"] = "1000m3 maximum is a separate coarser step scenario, not resolution-equivalent to parent 200m3"
        np.savez_compressed(output / "result.npz", **arrays)
    report["implementation_hashes"] = hashes
    report["implementation_unchanged_during_run"] = all(file_sha256(ROOT / name) == digest for name, digest in hashes.items())
    report["parent_and_new_source_archives_unchanged"] = all(file_sha256(Path(path)) == digest for path, digest in (
        (provenance["parent_result"], provenance["parent_result_sha256"]), (provenance["parent_checkpoint"], provenance["parent_checkpoint_sha256"]),
        (forcing["source"], forcing["source_sha256"])))
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {"status": report["status"], "output": str(output), "forcing": forcing, "runtime_s": report.get("runtime_s"),
        "ledger_bulk_m3": report.get("ledger_bulk_m3"), "restored_native_checkpoint_grids": report.get("restored_native_checkpoint_grids")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--new-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-step-solid-m3", type=float, default=1000.)
    parser.add_argument("--steps", type=int)
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    resource_limits()
    print(json.dumps(run(args.parent, args.new_source, args.output, max_step_solid_m3=args.max_step_solid_m3,
        steps=args.steps, prepare_only=args.prepare), indent=2))
