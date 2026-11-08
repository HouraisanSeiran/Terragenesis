#!/usr/bin/env python3
"""Cold independent verification of a saved river-dominant run against its source."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import (  # noqa: E402
    FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval,
)
from terrain_pipeline.surface_rivers.metric_river_dominant_delta import (  # noqa: E402
    simulate_river_dominant_grid,
)
from tools.verify_fluvial_channel_remobilization import resource_limits  # noqa: E402

DEFAULT_SOURCE = ROOT / "verification/fluvial-delta/same-source-feedback-landward-20261016-02"
DEFAULT_OUTPUT = ROOT / "verification/fluvial-delta/river-dominant-saved-source-20261017-01"
HASH_FILES = ("mouth.npz", "summary.json", "geometry-material-daily.npz", "feedback_bundle.npz")
VERSION = "river-dominant-saved-source-verify-1"


def _hash_all(source):
    return {name: file_sha256(source / name) for name in HASH_FILES}


def load_case(source):
    source = Path(source)
    with np.load(source / "mouth.npz", allow_pickle=False) as d:
        arrays = {k: d[k].copy() for k in d.files}
    meta = json.loads(arrays["metadata_json"].item())
    cfg = FluvialDeltaConfig(**meta["config"])
    bnd = FluvialDeltaBoundary(
        arrays["ocean_mask"], arrays["export_mask"],
        float(meta["sea_level_m"]), float(meta["river_head_m"]),
        str(meta["boundary_source_id"]))
    forcing = tuple(
        FluvialDeltaInterval(tuple(int(x) for x in item["inlet_cell"]),
                             float(item["water_volume_m3"]),
                             float(item["sediment_solid_m3"]))
        for item in meta["forcing"])
    inlet = tuple(int(x) for x in forcing[0].inlet_cell)
    outlets = [tuple(int(x) for x in c) for c in np.argwhere(arrays["export_mask"])]
    with open(source / "summary.json", "r", encoding="utf-8") as fh:
        summary = json.load(fh)
    origin = np.asarray(arrays["origin_xz_m"], dtype=float)
    return {
        "dir": source, "arrays": arrays, "meta": meta, "config": cfg, "boundary": bnd,
        "forcing": forcing, "inlet": inlet, "outlets": outlets, "summary": summary,
        "origin": (float(origin[0]), float(origin[1])),
        "spacing": float(arrays["spacing_m"]),
    }


def _grid(initial, case):
    return TerrainGrid(
        initial, np.ones(initial.shape, bool),
        case["origin"][0], case["origin"][1],
        case["spacing"], case["spacing"],
        "diagnostic_dem_proxy", "saved-source-river-dominant",
        file_sha256(case["dir"] / "mouth.npz"),
        source_path=str(case["dir"] / "mouth.npz"))


def _zero_forcing(forcing):
    return tuple(
        FluvialDeltaInterval(i.inlet_cell, i.water_volume_m3, 0.0) for i in forcing)


def _run_once(case, forcing):
    grid = _grid(case["arrays"]["initial_bed_m"], case)
    return simulate_river_dominant_grid(
        grid, case["boundary"], case["inlet"], case["outlets"], forcing, case["config"]), grid


def collect(actual, control, case):
    arrays = {}
    flow = actual["spatial_result"]
    arrays["initial_bed_m"] = np.asarray(case["arrays"]["initial_bed_m"], dtype=float)
    arrays["final_bed_m"] = np.asarray(actual["final_bed_m"], dtype=float)
    arrays["control_final_bed_m"] = np.asarray(control["final_bed_m"], dtype=float)
    arrays["deposited_solid_m3"] = np.asarray(actual["deposited_solid_m3"], dtype=float)
    arrays["reentrained_solid_m3"] = np.asarray(flow["reentrained_solid_m3"], dtype=float)
    arrays["stored_solid_m3"] = np.asarray(flow["stored_solid_m3"], dtype=float)
    arrays["initial_ocean_mask"] = np.asarray(case["arrays"]["ocean_mask"], dtype=bool)
    arrays["export_mask"] = np.asarray(case["arrays"]["export_mask"], dtype=bool)
    arrays["origin_xz_m"] = np.asarray(case["origin"], dtype=float)
    arrays["spacing_m"] = np.asarray(case["spacing"], dtype=float)
    arrays["outlet_cells"] = np.asarray(case["outlets"], dtype=np.int64)
    bh = actual["branch_history"]
    cbh = control["branch_history"]
    arrays["monthly_bed_after_m"] = np.stack([np.asarray(r["bed_after_m"], dtype=float) for r in bh])
    arrays["monthly_stored_solid_m3"] = np.stack([np.asarray(r["stored_solid_m3"], dtype=float) for r in bh])
    arrays["monthly_deposited_solid_m3"] = np.stack([np.asarray(r["deposited_solid_m3"], dtype=float) for r in bh])
    arrays["monthly_reentrained_solid_m3"] = np.stack([np.asarray(r["reentrained_solid_m3"], dtype=float) for r in bh])
    arrays["monthly_water_throughput_m3"] = np.stack([np.asarray(r["water_throughput_m3"], dtype=float) for r in flow["intervals"]])
    arrays["outlet_water_m3"] = np.stack([np.asarray(r["outlet_water_m3"], dtype=float) for r in bh])
    arrays["outlet_solid_m3"] = np.stack([np.asarray(r["outlet_solid_m3"], dtype=float) for r in bh])
    arrays["outlet_share"] = np.stack([np.asarray(r["branch_share"], dtype=float) for r in bh])
    arrays["control_outlet_share"] = np.stack([np.asarray(r["branch_share"], dtype=float) for r in cbh])
    endpoints = np.asarray(case["arrays"]["monthly_time_seconds"], dtype=float)
    arrays["monthly_time_seconds"] = endpoints
    arrays["metadata_json"] = np.asarray(json.dumps({
        "config": case["meta"]["config"], "forcing": case["meta"]["forcing"],
        "provenance": case["meta"].get("provenance"),
        "source": str(case["dir"].resolve()), "source_hashes": _hash_all(case["dir"]),
        "adapter_metadata": actual["metadata"]}, sort_keys=True, allow_nan=False))
    arrays["budgets_json"] = np.asarray(json.dumps({
        "actual_sediment": actual["sediment_budget"], "actual_water": actual["water_budget"],
        "control_sediment": control["sediment_budget"], "control_water": control["water_budget"]},
        sort_keys=True, allow_nan=False))

    checks = {
        "final_bed_replay": bool(np.array_equal(
            flow["final_bed_m"], case["arrays"]["final_bed_m"])),
        "stored_replay": bool(np.array_equal(
            flow["stored_solid_m3"], case["arrays"]["stored_solid_m3"])),
        "deposited_replay": bool(np.array_equal(
            actual["deposited_solid_m3"], case["arrays"]["deposited_solid_m3"])),
        "control_zero": bool(np.array_equal(
            control["final_bed_m"], case["arrays"]["initial_bed_m"])),
    }
    cell_area = float(case["spacing"]) ** 2
    phi = float(case["config"].porosity)
    fp = flow["final_bed_m"]
    init_bed = np.asarray(case["arrays"]["initial_bed_m"], dtype=float)
    rtol, atol = 1e-12, 1e-8
    per_ok = True
    for label, result in (("actual", actual), ("control", control)):
        water_budget = result["water_budget"]
        solid_budget = result["sediment_budget"]
        checks[label + "_water_closure"] = bool(np.isclose(
            water_budget["input_water_m3"],
            water_budget["ocean_export_water_m3"] + water_budget["retained_water_m3"],
            rtol=rtol, atol=atol))
        checks[label + "_solid_closure"] = bool(np.isclose(
            solid_budget["input_solid_m3"],
            solid_budget["stored_solid_m3"] + solid_budget["ocean_export_solid_m3"]
            + solid_budget["unresolved_solid_m3"], rtol=rtol, atol=atol))
        previous_stored = 0.
        rows, columns = arrays["outlet_cells"].T
        for record in result["intervals"]:
            water_ledger, solid_ledger = record["water_ledger"], record["solid_ledger"]
            stored = float(record["stored_solid_m3"].sum())
            comparisons = (
                (record["water_throughput_m3"][rows, columns].sum(), water_ledger["ocean_export_m3"]),
                (record["sediment_throughput_solid_m3"][rows, columns].sum(), solid_ledger["ocean_export_solid_m3"]),
                (water_ledger["input_m3"], water_ledger["ocean_export_m3"] + water_ledger["retained_m3"]),
                (solid_ledger["input_solid_m3"] + previous_stored,
                 stored + solid_ledger["ocean_export_solid_m3"] + solid_ledger["unresolved_solid_m3"]),
                (previous_stored + float(record["deposited_solid_m3"].sum()),
                 stored + float(record["reentrained_solid_m3"].sum())),
            )
            per_ok = per_ok and all(bool(np.isclose(a, b, rtol=rtol, atol=atol))
                                    for a, b in comparisons)
            previous_stored = stored
    checks["per_interval_outlet_ledger"] = per_ok
    bed_solid = float(((fp - init_bed) * cell_area * (1. - phi)).sum())
    checks["bed_stored_closure"] = bool(np.isclose(
        bed_solid, flow["stored_solid_m3"].sum(), rtol=rtol, atol=atol))
    checks["budget_closure"] = all(checks[name] for name in (
        "bed_stored_closure", "actual_solid_closure", "control_solid_closure",
        "actual_water_closure", "control_water_closure"))

    sea = float(case["meta"]["sea_level_m"])
    land = init_bed > sea
    stored_solid = np.asarray(arrays["stored_solid_m3"], dtype=float)
    land_stored = land & (stored_solid > 1e-9)
    exported = arrays["outlet_share"].sum(axis=1) > 0.0 if arrays["outlet_share"].size else np.zeros(0, bool)
    first_export = int(np.argmax(exported)) if exported.any() else 0
    control_share_drift = float(np.abs(
        arrays["control_outlet_share"] - arrays["control_outlet_share"][:1]).max()) \
        if arrays["control_outlet_share"].size else 0.0
    if control_share_drift > 1e-12:
        raise ValueError(
            "control share drift exceeds 1e-12: %r" % control_share_drift)
    if not checks["final_bed_replay"] or not checks["stored_replay"] \
            or not checks["deposited_replay"]:
        raise ValueError("exact source replay check failed")
    if not checks["control_zero"]:
        raise ValueError("unchanged zero control check failed")
    if not checks["per_interval_outlet_ledger"]:
        raise ValueError("per-interval outlet ledger check failed")
    if not checks["budget_closure"]:
        raise ValueError("budget closure check failed")
    feedback_identity = case["summary"].get("feedback_identity_sha256")
    if feedback_identity is None:
        raise ValueError("missing feedback_identity_sha256 in source summary")
    summary = {
        "version": VERSION,
        "source": str(case["dir"].resolve()),
        "source_hashes": _hash_all(case["dir"]),
        "feedback_identity": feedback_identity,
        "config": case["meta"]["config"],
        "forcing": case["meta"]["forcing"],
        "adapter_metadata": actual["metadata"],
        "budgets": {"actual_sediment": actual["sediment_budget"],
                     "actual_water": actual["water_budget"],
                     "control_sediment": control["sediment_budget"],
                     "control_water": control["water_budget"]},
        "max_outlet_share_change": float(np.abs(arrays["outlet_share"] - arrays["outlet_share"][first_export]).max()) if arrays["outlet_share"].size else 0.0,
        "max_actual_vs_control_share_diff": float(np.abs(arrays["outlet_share"] - arrays["control_outlet_share"]).max()) if arrays["outlet_share"].size else 0.0,
        "control_share_drift": control_share_drift,
        "original_land_stored_m3": float(stored_solid[land].sum()),
        "original_land_area_m2": float(land_stored.sum() * cell_area),
        "emergence_area_m2": float((arrays["initial_ocean_mask"] & (arrays["final_bed_m"] > sea)).sum() * cell_area),
        "flags": {
            "exact_source_replay": bool(checks["final_bed_replay"] and checks["stored_replay"] and checks["deposited_replay"]),
            "unchanged_zero_control": bool(checks["control_zero"]),
            "unchanged_sources": True,
            "budget_closure": bool(checks["budget_closure"]),
            "per_interval_outlet_ledger": bool(checks["per_interval_outlet_ledger"]),
        },
        "state_model": "bed-resistance/prescribed head, not solved free surface",
        "hydraulic_ready": False,
        "publishable": False,
        "tides_waves": "off",
        "extent_m": [float(arrays["initial_bed_m"].shape[1] * case["spacing"]),
                     float(arrays["initial_bed_m"].shape[0] * case["spacing"])],
    }
    return arrays, json.loads(json.dumps(summary, allow_nan=False))


def run(source, output):
    resource_limits()
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise SystemExit("output already exists: " + str(output))
    before = _hash_all(source)
    case = load_case(source)
    actual, _ = _run_once(case, case["forcing"])
    control, _ = _run_once(case, _zero_forcing(case["forcing"]))
    arrays, summary = collect(actual, control, case)
    after = _hash_all(source)
    if before != after:
        raise ValueError("source hashes changed during run")
    summary["source_hashes_before"] = before
    summary["source_hashes_after"] = after
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output / "result.npz", **arrays)
    with open(output / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, sort_keys=True, allow_nan=False)
    render(output, arrays)
    return summary


def audit(output):
    resource_limits()
    output = Path(output).resolve()
    with open(output / "summary.json", "r", encoding="utf-8") as fh:
        saved = json.load(fh)
    with np.load(output / "result.npz", allow_pickle=False) as d:
        saved_arrays = {k: d[k].copy() for k in d.files}
    source = Path(saved["source"])
    before = _hash_all(source)
    if before != saved.get("source_hashes_before"):
        raise ValueError("source hashes differ from saved")
    case = load_case(source)
    actual, _ = _run_once(case, case["forcing"])
    control, _ = _run_once(case, _zero_forcing(case["forcing"]))
    arrays, summary = collect(actual, control, case)
    after = _hash_all(source)
    if before != after:
        raise ValueError("source hashes changed during audit")
    summary["source_hashes_before"] = before
    summary["source_hashes_after"] = after
    if set(saved_arrays) != set(arrays):
        raise ValueError("saved array key set differs from recompute")
    for key in sorted(arrays):
        if not np.array_equal(saved_arrays[key], arrays[key]):
            raise ValueError("array mismatch: " + key)
    if saved != summary:
        raise ValueError("summary mismatch after recompute")
    with open(output / "cold-audit.json", "w", encoding="utf-8") as fh:
        json.dump({"status": "pass", "version": VERSION, "source": str(source)}, fh, sort_keys=True)
    return True


def render(output, arrays):
    spacing = float(arrays["spacing_m"])
    nx = arrays["initial_bed_m"].shape[1]
    nz = arrays["initial_bed_m"].shape[0]
    ext = (0.0, nx * spacing / 1000.0, nz * spacing / 1000.0, 0.0)
    init_bed = np.asarray(arrays["initial_bed_m"], dtype=float)
    fin_bed = np.asarray(arrays["final_bed_m"], dtype=float)
    vmin = float(min(init_bed.min(), fin_bed.min()))
    vmax = float(max(init_bed.max(), fin_bed.max()))
    fig, ax = plt.subplots(2, 2, figsize=(11, 8))
    im = ax[0, 0].imshow(init_bed, extent=ext, origin="upper", vmin=vmin, vmax=vmax)
    ax[0, 0].set_title("initial bed")
    plt.colorbar(im, ax=ax[0, 0], label="m")
    im = ax[0, 1].imshow(fin_bed, extent=ext, origin="upper", vmin=vmin, vmax=vmax)
    ax[0, 1].set_title("final bed")
    plt.colorbar(im, ax=ax[0, 1], label="m")
    change = fin_bed - init_bed
    im = ax[1, 0].imshow(change, extent=ext, origin="upper", cmap="coolwarm")
    ax[1, 0].contour(arrays["initial_ocean_mask"].astype(float), levels=[0.5],
                     colors="k", extent=ext, origin="upper")
    ax[1, 0].set_title("net bed change with initial coastline")
    plt.colorbar(im, ax=ax[1, 0], label="m")
    last = np.asarray(arrays["monthly_water_throughput_m3"], dtype=float)[-1]
    mask = last > 0.0
    img = np.full(last.shape, np.nan, dtype=float)
    if mask.any():
        img[mask] = np.log10(last[mask])
    im = ax[1, 1].imshow(img, extent=ext, origin="upper")
    ax[1, 1].set_title("last interval log10 water volume (m3)")
    plt.colorbar(im, ax=ax[1, 1], label="log10 m3")
    for row in ax:
        for a in row:
            a.set_xlabel("x (km)")
            a.set_ylabel("z (km)")
    fig.tight_layout()
    fig.savefig(output / "overview.png", dpi=110)
    plt.close(fig)

    days = np.asarray(arrays["monthly_time_seconds"], dtype=float)[1:] / 86400.0
    aw_hist = np.asarray(arrays["outlet_water_m3"], dtype=float)
    cshare_hist = np.asarray(arrays["control_outlet_share"], dtype=float)
    total = aw_hist.sum(axis=0)
    order = np.argsort(-total)[:6]
    sink = np.asarray(arrays["outlet_cells"], dtype=np.int64)
    labels = ["r%d,c%d" % (int(sink[j, 0]), int(sink[j, 1])) for j in order] + ["other"]

    def _shares(hist):
        denom = hist.sum(axis=1, keepdims=True)
        share = np.divide(hist, denom, out=np.zeros_like(hist),
                          where=denom > 0.0)
        top = share[:, order]
        other = share.sum(axis=1) - top.sum(axis=1)
        return np.column_stack((top, other))

    actual_share = _shares(aw_hist)
    top_c = cshare_hist[:, order]
    other_c = cshare_hist.sum(axis=1, keepdims=True) - top_c.sum(axis=1, keepdims=True)
    control_share = np.column_stack((top_c, other_c))

    fig, ax = plt.subplots(1, 3, figsize=(15, 4))
    for i, label in enumerate(labels):
        ax[0].plot(days, actual_share[:, i], label=label)
    ax[0].set_title("actual outlet water fraction")
    ax[0].set_xlabel("days")
    ax[0].set_ylabel("fraction")
    ax[0].legend(fontsize=6)
    for i, label in enumerate(labels):
        ax[1].plot(days, control_share[:, i], label=label)
    ax[1].set_title("zero-control outlet water fraction")
    ax[1].set_xlabel("days")
    ax[1].set_ylabel("fraction")
    ax[1].legend(fontsize=6)
    gross_dep = np.asarray(arrays["monthly_deposited_solid_m3"], dtype=float).sum(axis=(1, 2))
    gross_re = np.asarray(arrays["monthly_reentrained_solid_m3"], dtype=float).sum(axis=(1, 2))
    inventory = np.asarray(arrays["monthly_stored_solid_m3"], dtype=float).sum(axis=(1, 2))
    ax[2].plot(days, gross_dep, label="gross deposited", linestyle="-")
    ax[2].plot(days, gross_re, label="gross reentrained", linestyle="--")
    ax[2].plot(days, inventory, label="end inventory", linestyle=":")
    ax[2].set_title("solid budget")
    ax[2].set_xlabel("days")
    ax[2].set_ylabel("solid volume (m3)")
    ax[2].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "outlet-history.png", dpi=110)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--audit", default=None)
    args = ap.parse_args()
    if args.audit:
        audit(Path(args.audit))
    else:
        run(Path(args.source), Path(args.output))


if __name__ == "__main__":
    main()
