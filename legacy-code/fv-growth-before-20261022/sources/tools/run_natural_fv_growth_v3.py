"""v3 transactional adaptive FV finite exchange and wet-bank slope growth."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import MorphodynamicStepTooLarge
from tools import run_natural_fv_growth_interval_v3 as legacy
from tools import run_natural_fv_growth_v2 as previous
from tools.inspect_natural_fv_growth import read_arrays

SELF = "tools/run_natural_fv_growth_v3.py"
STATE = ("bed_m", "depth_m", "momentum_m2_s", "suspended_solid_m3")


def identities():
    return {name: file_sha256(ROOT / name) for name in legacy.IMPLEMENTATIONS}


def load_checkpoint(path):
    saved = read_arrays(path)
    meta = json.loads(str(saved.pop("metadata_json")))
    current = identities()
    archived = meta["implementation_hashes"]
    if meta["schema"] == "finite-FV-growth-checkpoint-v3":
        if archived != current:
            raise ValueError("v3 checkpoint implementation identity mismatch")
    else:
        # The v2 loader certifies all frozen signatures before state-only migration.
        previous.load_checkpoint(path)
    meta["checkpoint_migration"] = {"from_schema": meta["schema"], "source": str(path), "source_sha256": file_sha256(path),
        "from_runner_sha256": archived.get(SELF), "to_runner_sha256": current[SELF],
        "policy": "v2-to-v3 state-only numerical upgrade; all frozen dependencies verified; bed/floor/live water/suspended state and source cursor/quota preserved"}
    meta["schema"] = "finite-FV-growth-checkpoint-v3"
    meta["implementation_hashes"] = current
    meta["resumed_checkpoint"] = str(path)
    meta["resumed_checkpoint_sha256"] = file_sha256(path)
    return saved, meta


def save_checkpoint(path, data, meta):
    np.savez_compressed(path, **data, metadata_json=json.dumps(meta))


def remove_trial(path, output):
    resolved = path.resolve()
    if resolved.parent != output.resolve() or not resolved.name.startswith(".trial-") or not resolved.name[7:].isdigit():
        raise ValueError("refusing to remove a path outside this output's numbered trial directories")
    if resolved.exists():
        shutil.rmtree(resolved)


def finish(output, snapshots, times, data, start_meta, meta, ledgers, args, started, status, attempts):
    arrays = {key: np.asarray(value) for key, value in snapshots.items()}
    arrays.update(time_s=np.asarray(times), **{key: data[key] for key in
        ("source_floor_m", "cell_type", "initial_bed_m", "local_world_xz_m", "fixed_boundary_mask")})
    arrays["stage_m"] = arrays["bed_m"] + arrays["depth_m"]
    np.savez_compressed(output / "result.npz", **arrays)
    initial = float(((arrays["bed_m"][0] - data["source_floor_m"]) * 25. * .65).sum() + arrays["suspended_solid_m3"][0].sum())
    final = float(((arrays["bed_m"][-1] - data["source_floor_m"]) * 25. * .65).sum() + arrays["suspended_solid_m3"][-1].sum())
    injected = meta["cumulative_injected_solid_m3"] - start_meta["cumulative_injected_solid_m3"]
    exported = meta["cumulative_exported_solid_m3"] - start_meta["cumulative_exported_solid_m3"]
    water = np.zeros(3)
    for path in sorted(output.glob("chunk-audit-*.npz")):
        with np.load(path) as block:
            boundary = block["water_boundary_transfer_m3"]
            water += [block["water_forcing_volume_m3"].sum(), -np.minimum(boundary, 0.).sum(), np.maximum(boundary, 0.).sum()]
    checkpoint = sorted(output.glob("checkpoint-*.npz"))[-1]
    parameters = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    parameters.update(intervals=len(ledgers), adaptive_intervals=True)
    report = {"schema": "finite-FV-suspended-growth-v3", "status": status, "checkpoint": str(checkpoint),
        "checkpoint_sha256": file_sha256(checkpoint), "start": start_meta, "end": meta, "parameters": parameters,
        "planned_duration_s": args.duration_s, "actual_duration_s": float(times[-1] - times[0]),
        "initial_bed_plus_suspended_solid_m3": initial, "final_bed_plus_suspended_solid_m3": final,
        "injected_solid_m3": injected, "exported_solid_m3": exported,
        "combined_residual_solid_m3": final + exported - initial - injected,
        "maximum_phase_residual_solid_m3": max(abs(row["combined_residual_solid_m3"]) for row in ledgers),
        "remaining_finite_source_solid_m3": meta["source_total_solid_m3"] - meta["cumulative_injected_solid_m3"],
        "water_supplied_imported_exported_m3": water.tolist(),
        "water_volume_residual_m3": float((arrays["depth_m"][-1] - arrays["depth_m"][0]).sum() * 25. - water[0] - water[1] + water[2]),
        "implementation_hashes": identities(), "runtime_s": time.monotonic() - started, "attempts": attempts,
        "exchange_config": meta.get("exchange_config"),
        "limitations": "v3 finite Shields bed-suspended exchange and wet-bank excess-slope transport; frozen FV and MPM retained. Empirical rates, no calibrated cohesive banks or wave radiation stress. Interval-net advection."}
    (output / "interval-ledgers.json").write_text(json.dumps(ledgers, indent=2), encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run(args):
    if args.recover_completed_prefix:
        raise ValueError("recover old prefixes with frozen v2; v3 requires an explicit complete checkpoint")
    if (args.duration_s <= 0. or args.chunk_duration_s <= 0. or args.interval_s not in (2., 1., .5, .25, .125, .0625)
            or not 0. < args.min_interval_s <= args.interval_s):
        raise ValueError("positive duration/chunk/minimum interval and initial power-of-two interval <=2s required")
    started = time.monotonic()
    data, meta = load_checkpoint(args.resume)
    if args.append_source:
        legacy.append_source(data, meta, args.append_source)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "packets").mkdir()
    snapshots = {key: [data[key].copy()] for key in STATE}
    times = [meta["physical_time_s"]]
    start_meta = deepcopy(meta)
    ledgers, attempts = [], []
    target = times[0] + args.duration_s
    dt = args.interval_s
    done = 0
    trial_number = 0
    while meta["physical_time_s"] < target - 1.e-9:
        remaining = target - meta["physical_time_s"]
        trial_dt = min(dt, remaining)
        count = min(64, max(1, int(min(args.chunk_duration_s, remaining) / trial_dt + 1.e-10)))
        trial_number += 1
        temporary = args.output / f".trial-{trial_number:06d}"
        trial_input = args.output / ".trial-input.npz"
        trial_meta = deepcopy(meta)
        trial_meta["schema"] = "finite-FV-growth-checkpoint-v3"
        trial_meta["implementation_hashes"] = identities()
        save_checkpoint(trial_input, {key: value.copy() for key, value in data.items()}, trial_meta)
        trial_args = deepcopy(args)
        trial_args.resume, trial_args.output = trial_input, temporary
        trial_args.intervals, trial_args.interval_s, trial_args.chunk_intervals = count, trial_dt, count
        trial_args.append_source = None
        try:
            report = legacy.run(trial_args)
        except MorphodynamicStepTooLarge as error:
            attempts.append({"attempt": trial_number, "status": "rejected", "time_s": meta["physical_time_s"],
                "interval_s": trial_dt, "interval_count": count, "error": str(error),
                "source_cursor_unchanged_s": meta["source_cursor_s"]})
            (args.output / "attempts.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")
            remove_trial(temporary, args.output)
            trial_input.unlink()
            if dt <= args.min_interval_s:
                raise
            dt = max(args.min_interval_s, dt * .5)
            continue
        next_data = read_arrays(Path(report["checkpoint"]))
        next_meta = json.loads(str(next_data.pop("metadata_json")))
        next_meta.update(schema="finite-FV-growth-checkpoint-v3", implementation_hashes=identities(),
            resumed_checkpoint=start_meta["resumed_checkpoint"], resumed_checkpoint_sha256=start_meta["resumed_checkpoint_sha256"])
        block_ledgers = json.loads((temporary / "interval-ledgers.json").read_text(encoding="utf-8"))
        for index, row in enumerate(block_ledgers):
            row["global_interval"] = done + index
        done += count
        audit_path = next(temporary.glob("chunk-audit-*.npz"))
        shutil.move(str(audit_path), args.output / f"chunk-audit-{done:07d}.npz")
        save_checkpoint(args.output / f"checkpoint-{done:07d}.npz", next_data, next_meta)
        for path in (temporary / "packets").glob("*.npz"):
            number, suffix = path.name.split("-", 1)
            shutil.move(str(path), args.output / "packets" / f"{done - count + int(number):07d}-{suffix}")
        # Commit only after the complete legacy chunk succeeded, including source cursor.
        data, meta = next_data, next_meta
        ledgers.extend(block_ledgers)
        for key in STATE:
            snapshots[key].append(data[key].copy())
        times.append(meta["physical_time_s"])
        peak = max(row["maximum_bed_change_m"] for row in block_ledgers)
        attempts.append({"attempt": trial_number, "status": "committed", "interval_s": trial_dt,
            "interval_count": count, "end_time_s": meta["physical_time_s"], "peak_bed_change_m": peak})
        (args.output / "attempts.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")
        (args.output / "interval-ledgers.json").write_text(json.dumps(ledgers, indent=2), encoding="utf-8")
        remove_trial(temporary, args.output)
        trial_input.unlink()
        print("COMMITTED", done, "physical_s", meta["physical_time_s"], "dt", trial_dt, "bed_change", peak, flush=True)
        if peak < args.max_bed_change * .2 and dt < args.interval_s:
            dt = min(args.interval_s, dt * 2.)
        if time.monotonic() - started > args.max_wall_s:
            raise RuntimeError("wall budget reached; resume last committed v2 checkpoint")
    return finish(args.output, snapshots, times, data, start_meta, meta, ledgers, args, started, "completed", attempts)


def parser():
    p = legacy.parser()
    p.description = __doc__
    p.add_argument("--duration-s", type=float, required=True)
    p.add_argument("--chunk-duration-s", type=float, default=16.)
    p.add_argument("--min-interval-s", type=float, default=.0625)
    p.add_argument("--recover-completed-prefix", type=Path)
    p.set_defaults(interval_s=2.)
    return p


if __name__ == "__main__":
    legacy.resource_limits()
    args = parser().parse_args()
    if not args.resume:
        raise ValueError("explicit complete checkpoint required")
    print(json.dumps(run(args), indent=2))
