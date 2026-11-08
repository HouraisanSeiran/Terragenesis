"""Replay a finite 30 m single-feeder delta scenario without downstream paths."""
import argparse
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.environment_delta_fv import FVDeltaConfig, initialize, advance, save, load


def plot(product, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    a = product["arrays"]
    shape = a["bed_m"].shape
    h = a["depth_m"]
    velocity = np.divide(a["momentum_m2_s"], h.ravel()[:, None], out=np.zeros_like(a["momentum_m2_s"]),
                         where=h.ravel()[:, None] > 1.e-5).reshape(*shape, 2)
    x, z = np.arange(shape[1])*30., np.arange(shape[0])*30.
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), layout="constrained")
    for axis, data, title in zip(axes, [a["bed_m"]-a["initial_bed_m"], h, np.linalg.norm(velocity, axis=2)],
                               ["Bed change (m)", "Water depth (m)", "Velocity (m/s)"]):
        im = axis.pcolormesh(x, z, data, shading="nearest", cmap="viridis")
        fig.colorbar(im, ax=axis)
        axis.set_aspect("equal")
        axis.set(xlabel="x (m)", ylabel="z (m)", title=title)
    for axis in axes[1:]:
        axis.streamplot(x, z, velocity[:, :, 0], velocity[:, :, 1], color="white", density=1.3, linewidth=.6)
    axes[0].contour(x, z, a["bed_m"], levels=[0.], colors="white", linewidths=.8)
    fig.suptitle("Finite engineering coast: single upstream feeder; no prescribed downstream branches")
    fig.savefig(output, dpi=150)
    plt.close(fig)


def run(args):
    if (not np.isfinite([args.duration_s, args.warmup_s, args.water_q, args.solid_rate]).all()
            or args.duration_s <= 0. or min(args.warmup_s, args.water_q, args.solid_rate) < 0.):
        raise ValueError("finite positive duration and nonnegative forcing required")
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    bed = np.full((32, 48), -.5)
    bed[:, 36:] = .8
    baseline = bed.copy()
    bed[15:18, 36:] = -1.
    ocean = np.zeros(bed.shape, bool)
    ocean[:, :36] = True
    product = initialize(bed, ocean, [16*48+46], origin_m_xz=[0., 0.],
        source_world_identity="seed20261020", source_identity="declared-30m-single-feeder-coast-v1",
        config=FVDeltaConfig(coupling_interval_s=10., max_hydro_dt_s=3., max_wall_s=args.max_wall_s))
    save(args.output/"initial.npz", product)
    plot(product, args.output/"initial.png")
    if args.warmup_s:
        product = advance(product, [{"id": "clear-water-warmup", "source": "declared finite engineering warmup",
            "time_start_s": 0., "time_end_s": args.warmup_s, "water_m3": args.water_q*args.warmup_s, "solid_m3": 0.}])
    save(args.output/"ready.npz", product)
    plot(product, args.output/"ready.png")
    source = "declared finite engineering sediment supply" if not args.zero_sediment else "declared same-water zero-sediment control"
    solid_rate = 0. if args.zero_sediment else args.solid_rate
    for index in range(2):
        start = args.warmup_s + index*args.duration_s/2.
        end = args.warmup_s + (index+1)*args.duration_s/2.
        product = advance(product, [{"id": "finite-supply-"+str(index), "source": source,
            "time_start_s": start, "time_end_s": end, "water_m3": args.water_q*(end-start), "solid_m3": solid_rate*(end-start)}])
        if index == 0:
            checkpoint = args.output/"midpoint.npz"
            save(checkpoint, product)
            product = load(checkpoint, expected_sha256=file_sha256(checkpoint))
            plot(product, args.output/"midpoint.png")
    save(args.output/"final.npz", product)
    plot(product, args.output/"final.png")
    a, m = product["arrays"], product["metadata"]
    delta = a["bed_m"]-a["initial_bed_m"]
    # Actual signed FV flux across each full seaward section, plus its cell profile.
    left = a["face_left"]
    sections = {}
    final_dt = m["last_coupling_interval_s"]
    for col in (35, 32, 28, 24):
        faces = (left % 48 == col) & (a["face_right"] == left+1)
        sections[str(col)] = {"x_m": float((col+.5)*30.),
            "last_interval_net_q_m3_s_by_row": (a["internal_last_water_transfer_m3"][faces]/final_dt).tolist(),
            "bed_m_by_row": a["bed_m"][:, col].tolist(), "depth_m_by_row": a["depth_m"][:, col].tolist()}
    report = {"scenario": "finite uncalibrated engineering coast, no pre-existing offshore bars or downstream branches",
        "world_seed": 20261020, "spacing_m": 30., "shape_zx": [32, 48],
        "initial_geometry": "flat -0.5m basin, +0.8m land, one 90m wide 360m long feeder bed at -1m",
        "initial_construction": {"excavated_bulk_m3": float((baseline-bed).sum()*900.),
            "excavated_solid_m3_at_porosity_035": float((baseline-bed).sum()*900.*.65),
            "semantics": "declared initial geometry; excavation is removed before simulation and never reused as sediment supply"},
        "erodible_substrate_solid_m3": m["initial_bed_solid_m3"], "zero_sediment": args.zero_sediment,
        "parameters": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "physical_time_s": m["physical_time_s"], "ledger": m["ledger"],
        "maximum_bed_rise_m": float(delta.max()), "ocean_cells_above_mean_sea": int(np.count_nonzero(a["bed_m"][ocean] > 0.)),
        "ocean_dry_cells": int(np.count_nonzero(a["depth_m"][ocean] <= 1.e-5)),
        "maximum_offshore_bed_rise_m": float(delta[ocean].max()),
        "deposition_cells_above_01m": int(np.count_nonzero(delta > .1)),
        "completed_coupling_steps": m["completed_coupling_steps"], "rejected_coupling_steps": m["rejected_coupling_steps"],
        "runtime_s": time.monotonic()-started, "final_sha256": file_sha256(args.output/"final.npz"),
        "cold_restart": "actual midpoint saved and SHA256-pinned cold load before second half",
        "sections": sections, "morphology_acceptance": "inspect saved bed/depth/velocity and section profiles; multiple outgoing faces alone do not certify distributaries"}
    (args.output/"summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration-s", type=float, default=21600.)
    parser.add_argument("--warmup-s", type=float, default=300.)
    parser.add_argument("--water-q", type=float, default=100.)
    parser.add_argument("--solid-rate", type=float, default=1.)
    parser.add_argument("--max-wall-s", type=float, default=150.)
    parser.add_argument("--zero-sediment", action="store_true")
    result = run(parser.parse_args())
    print(json.dumps({key: result[key] for key in ("physical_time_s", "maximum_bed_rise_m", "ocean_cells_above_mean_sea", "runtime_s", "ledger")}))


if __name__ == "__main__":
    main()
