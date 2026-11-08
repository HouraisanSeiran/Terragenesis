"""Finite declared30m tide reversal and Airy wave-mobilization controls."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import environment_delta_fv as fv
from terrain_pipeline.common_infra import file_sha256, identity, publish_bytes
from terrain_pipeline.surface_rivers.metric_fv_coastal_sediment import BedloadConfig


def residuals(product):
    a, m = product["arrays"], product["metadata"]
    ledger, area = m["ledger"], m["spacing_m"]**2
    water = float(a["depth_m"].sum())*area + ledger["water_export_m3"] - m["initial_water_m3"] - ledger["water_input_m3"] - ledger["sea_import_m3"]
    solid = (float(((a["bed_m"]-a["floor_m"])*area*(1.-m["config"]["bedload"]["porosity"])).sum()) +
             float(a["suspended_solid_m3"].sum()) + ledger["solid_export_m3"] - m["initial_bed_solid_m3"] - ledger["solid_input_m3"])
    return {"water_m3": water, "solid_m3": solid}


def run_case(bed, boundary, height, output):
    config = fv.FVDeltaConfig(coupling_interval_s=20., max_hydro_dt_s=5., max_wall_s=120.,
        tide_amplitude_m=.15, tide_period_s=1200.,
        bedload=BedloadConfig(wave_height_m=height, wave_direction_xz=(1, 0), max_bed_change_m=.05))
    parent = identity({"bed_m": bed, "marine_boundary_mask": boundary},
                      {"world_seed": 20261020, "origin_m_xz": [0., 0.], "spacing_m": 30., "scenario": "declared planar single shoreline"})
    product = fv.initialize(bed, boundary, np.array([4*12+6], np.int64), origin_m_xz=[0., 0.],
        source_world_identity="declared-seed20261020-coastal-control", source_identity=parent,
        spacing_m=30., erodible_cover_m=.2, config=config)
    initial = product
    name = "waves-%.1fm" % height
    fv.save(output / (name + "-initial.npz"), initial)
    series = []
    started = time.monotonic()
    for index in range(20):
        start, end = index*60., (index+1)*60.
        before = product["metadata"]["ledger"]
        product = fv.advance(product, [{"id": "declared-control-%02d" % index,
            "time_start_s": start, "time_end_s": end, "water_m3": .2*(end-start), "solid_m3": 0.,
            "source": "declared finite river-water control; zero external sediment; finite bed cover only"}])
        after = product["metadata"]["ledger"]
        a = product["arrays"]
        increment = a["boundary_water_transfer_m3"] - (previous_boundary if index else np.zeros_like(a["boundary_water_transfer_m3"]))
        previous_boundary = a["boundary_water_transfer_m3"].copy()
        internal = a["internal_last_water_transfer_m3"]
        series.append({"time_end_s": end, "sea_stage_at_interval_start_m": .15*np.sin(2.*np.pi*start/1200.),
            "sea_import_m3": after["sea_import_m3"]-before["sea_import_m3"],
            "water_export_m3": after["water_export_m3"]-before["water_export_m3"],
            "signed_boundary_net_m3": float(increment.sum()),
            "minimum_boundary_face_net_m3": float(increment.min()), "maximum_boundary_face_net_m3": float(increment.max()),
            "minimum_internal_last_face_m3": float(internal.min()), "maximum_internal_last_face_m3": float(internal.max()),
            "suspended_solid_m3": float(a["suspended_solid_m3"].sum()),
            "bed_change_l1_m3": float(np.abs(a["bed_m"]-bed).sum()*900.),
            "residuals": residuals(product)})
    fv.save(output / (name + "-final.npz"), product)
    return {"product": product, "initial": initial, "series": series,
            "wall_s": time.monotonic()-started, "config": asdict(config), "source_identity": parent}


def render(off, on, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    t = [r["time_end_s"] for r in off["series"]]
    axes[0, 0].plot(t, [r["sea_import_m3"] for r in off["series"]], label="Sea import per60s")
    axes[0, 0].plot(t, [-r["water_export_m3"] for r in off["series"]], label="Sea export per60s (negative)")
    axes[0, 0].axhline(0., color="black", linewidth=.5)
    axes[0, 0].set(xlabel="Physical mechanism time (s)", ylabel="Water volume (m3)", title="Declared1200s tide: actual FV boundary transfer")
    axes[0, 0].legend()
    for case, label in ((off, "H=0m"), (on, "H=0.3m")):
        axes[0, 1].plot(t, [r["bed_change_l1_m3"] for r in case["series"]], label=label)
    axes[0, 1].set(xlabel="Physical mechanism time (s)", ylabel="Absolute bed change volume (m3)", title="Same bed, water and tide; Airy mobilization control")
    axes[0, 1].legend()
    limit = max(float(np.abs(c["product"]["arrays"]["bed_m"]-c["product"]["arrays"]["initial_bed_m"]).max()) for c in (off, on))
    for axis, case, label in ((axes[1, 0], off, "H=0m actual bed change"), (axes[1, 1], on, "H=0.3m actual bed change")):
        a = case["product"]["arrays"]
        field = a["bed_m"]-a["initial_bed_m"]
        image = axis.imshow(field, origin="upper", cmap="RdBu_r", vmin=-limit, vmax=limit)
        fig.colorbar(image, ax=axis, label="Bed change (m)")
        axis.set(title=label, xlabel="Native30m column", ylabel="Native30m row")
    fig.savefig(output / "tide-wave-controls.png", dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    bed = np.broadcast_to(-1.2 + .16*np.arange(12), (8, 12)).copy()
    boundary = np.zeros_like(bed, bool)
    boundary[:, 0] = True
    off = run_case(bed, boundary, 0., args.output)
    on = run_case(bed, boundary, .3, args.output)
    pa, pb = off["product"], on["product"]
    bed_difference = float(np.abs(pa["arrays"]["bed_m"]-pb["arrays"]["bed_m"]).sum()*900.)
    checks = {"same_source_parent": off["source_identity"] == on["source_identity"],
              "same_initial_inventory": off["initial"]["metadata"]["initial_bed_solid_m3"] == on["initial"]["metadata"]["initial_bed_solid_m3"],
              "original_initial_bed_unchanged": bool(np.array_equal(pa["arrays"]["initial_bed_m"], bed) and np.array_equal(pb["arrays"]["initial_bed_m"], bed)),
              "tidal_sea_import": any(r["sea_import_m3"] > 1e-6 for r in off["series"]),
              "tidal_sea_export": any(r["water_export_m3"] > 1e-6 for r in off["series"]),
              "signed_boundary_reversal": any(r["signed_boundary_net_m3"] < -1e-6 for r in off["series"]) and any(r["signed_boundary_net_m3"] > 1e-6 for r in off["series"]),
              "wave_changes_actual_bed": bed_difference > 1e-8,
              "finite_floor_respected": all(np.min(c["product"]["arrays"]["bed_m"]-c["product"]["arrays"]["floor_m"]) >= -1e-9 for c in (off, on)),
              "budgets_close": all(abs(v) < 1e-6 for c in (off, on) for v in residuals(c["product"]).values())}
    report = {"checks": checks, "script_sha256": file_sha256(__file__),
        "grid_shape_zx": [8, 12], "spacing_m": 30., "world_seed": 20261020,
        "declared_scenario": "single planar shoreline; west fixed-stage marine edge; north/south/east closed; finite0.2m cover; river0.2m3/s; zero external sediment",
        "time_semantics": "one compressed1200s physical mechanism cycle, amplitude0.15m; not a GBM tidal calibration or a real1200s astronomical tide",
        "wave_semantics": "Airy shoaling/breaking and phase-averaged sand mobilization carried by net FV water; no wave radiation stress, longshore-current or Ebro/CEM model",
        "wave_bed_difference_l1_m3": bed_difference,
        "cases": {name: {"config": case["config"], "ledger": case["product"]["metadata"]["ledger"],
            "residuals": residuals(case["product"]), "wall_s": case["wall_s"], "series": case["series"],
            "identity_sha256": case["product"]["identity_sha256"], "initial_bed_solid_m3": case["initial"]["metadata"]["initial_bed_solid_m3"]}
            for name, case in (("wave_off", off), ("wave_on", on))}}
    publish_bytes(args.output / "report.json", json.dumps(report, indent=2, allow_nan=False).encode())
    render(off, on, args.output)
    print(json.dumps({"checks": checks, "wave_bed_difference_l1_m3": bed_difference, "wall_s": [off["wall_s"], on["wall_s"]]}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
