"""Prepare, advance, query or verify an actual saved-mouth FV delta."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline import environment_delta_fv as fv
from terrain_pipeline import environment_delta_source as source
from terrain_pipeline.common_infra import file_sha256, identity, publish_bytes


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load(path, digest):
    return fv.load(path, expected_sha256=digest)


def render(product, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    a, m = product["arrays"], product["metadata"]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)
    for axis, field, title, cmap in zip(axes,
            (a["bed_m"], a["bed_m"]-a["initial_bed_m"], a["depth_m"]),
            ("Actual saved bed + FV flow", "Actual sediment bed change (m)", "Computed water depth (m)"),
            ("terrain", "RdBu_r", "Blues")):
        plot = axis.imshow(field, origin="upper", cmap=cmap)
        axis.set_title(title)
        axis.set_xlabel("Native 30m column")
        axis.set_ylabel("Native 30m row")
        fig.colorbar(plot, ax=axis, shrink=.75)
    momentum = a["momentum_m2_s"].reshape((*a["bed_m"].shape, 2))
    rr, cc = np.indices(a["bed_m"].shape)
    step = max(1, min(a["bed_m"].shape)//12)
    peak = float(np.linalg.norm(momentum, axis=2).max())
    axes[0].quiver(cc[::step, ::step], rr[::step, ::step],
                   momentum[::step, ::step, 0], momentum[::step, ::step, 1], color="black",
                   angles="xy", scale_units="xy", scale=max(peak / 3., 1e-30))
    fig.suptitle("Actual regional packets at physical t=%.0fs; cropped artificial marine boundary" % m["physical_time_s"])
    fig.savefig(destination, dpi=140)
    plt.close(fig)


def actual_case(store, packets_path, output, bounds=None):
    packets = _read(packets_path)
    prepared = source.prepare(store)
    initial = source.initialize(prepared, packets[0], bounds=bounds)
    whole = source.advance(initial, packets)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    fv.save(output / "initial.npz", initial)
    fv.save(output / "delta.npz", whole)
    checkpoint = source.advance(initial, packets[:1])
    fv.save(output / "checkpoint.npz", checkpoint)
    cold = fv.load(output / "checkpoint.npz", expected_sha256=file_sha256(output / "checkpoint.npz"))
    continued = source.advance(cold, packets[1:]) if len(packets) > 1 else cold
    fv.save(output / "continued.npz", continued)
    control_records = []
    for packet in packets:
        control_records.append({"id": "zero-sediment-control-" + packet["packet_id"],
                                "time_start_s": packet["time_start_s"], "time_end_s": packet["time_end_s"],
                                "water_m3": packet["water_m3"], "solid_m3": 0.,
                                "reference_actual_packet_id": packet["packet_id"],
                                "source": "diagnostic zero-sediment counterfactual; actual source water quantity only"})
    control = source.initialize(prepared, packets[0], bounds=bounds)
    control["metadata"]["diagnostic_control"] = True
    control["identity_sha256"] = identity(control["arrays"], control["metadata"])
    control = fv.advance(control, control_records)
    fv.save(output / "zero-sediment.npz", control)
    a, m = whole["arrays"], whole["metadata"]
    left, top, right, bottom = m["coastal_source"]["crop_bounds_native"]
    checks = {"native_source_bed_unchanged": bool(np.array_equal(a["initial_bed_m"], prepared["arrays"]["bed_m"][top:bottom, left:right])),
              "cold_continue_matches_batch": continued["identity_sha256"] == whole["identity_sha256"],
              "actual_water_consumed_once": bool(np.isclose(m["ledger"]["water_input_m3"], sum(p["water_m3"] for p in packets))),
              "actual_solid_consumed_once": bool(np.isclose(m["ledger"]["solid_input_m3"], sum(p["solid_m3"] for p in packets), rtol=1e-12, atol=1e-15)),
              "zero_sediment_no_added_bed": bool(np.array_equal(control["arrays"]["initial_bed_m"], control["arrays"]["bed_m"]))}
    area = m["spacing_m"]**2
    ledger = m["ledger"]
    water_residual = (float(a["depth_m"].sum()) * area + ledger["water_export_m3"] -
                      m["initial_water_m3"] - ledger["water_input_m3"] - ledger["sea_import_m3"])
    solid_residual = (float(((a["bed_m"]-a["floor_m"]) * area * (1.-m["config"]["bedload"]["porosity"])).sum()) +
                      float(a["suspended_solid_m3"].sum()) + ledger["solid_export_m3"] -
                      m["initial_bed_solid_m3"] - ledger["solid_input_m3"])
    report = {"checks": checks, "identity_sha256": whole["identity_sha256"],
              "packet_source_path": str(Path(packets_path).resolve()), "packet_source_sha256": file_sha256(packets_path),
              "source": m["coastal_source"], "ledger": m["ledger"],
              "water_residual_m3": water_residual, "solid_residual_m3": solid_residual,
              "maximum_bed_change_m": float(np.max(a["bed_m"] - a["initial_bed_m"])),
              "interpretation": "actual saved TD mouth and already-debited finite tiny sediment export; no maturity or visible distributary claim"}
    publish_bytes(output / "acceptance.json", json.dumps(report, indent=2, allow_nan=False).encode())
    render(whole, output / "actual-bed-water-flow.png")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "case"):
        p = commands.add_parser(name)
        p.add_argument("--store", type=Path, default=ROOT / ".scratch/river-generation-review/real-coastal")
        p.add_argument("--packets", type=Path, default=ROOT / ".scratch/stage2-finish-20261030/coast-v3/packets.json")
        p.add_argument("--bounds", nargs=4, type=int)
        p.add_argument("--output", type=Path, required=True)
    for name in ("advance", "query"):
        p = commands.add_parser(name)
        p.add_argument("--input", type=Path, required=True)
        p.add_argument("--sha256", required=True)
        if name == "advance":
            p.add_argument("--packets", type=Path, required=True)
            p.add_argument("--output", type=Path, required=True)
        else:
            p.add_argument("--x-m", type=float, required=True)
            p.add_argument("--z-m", type=float, required=True)
    args = parser.parse_args(argv)
    if args.command == "case":
        result = actual_case(args.store, args.packets, args.output, args.bounds)
    elif args.command == "prepare":
        result = source.initialize(source.prepare(args.store), _read(args.packets)[0], bounds=args.bounds)
        fv.save(args.output, result)
        result = {"identity_sha256": result["identity_sha256"], "sha256": file_sha256(args.output)}
    elif args.command == "advance":
        result = source.advance(_load(args.input, args.sha256), _read(args.packets))
        fv.save(args.output, result)
        result = {"identity_sha256": result["identity_sha256"], "sha256": file_sha256(args.output)}
    else:
        result = fv.query(_load(args.input, args.sha256), args.x_m, args.z_m)
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if all(result.get("checks", {}).values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
