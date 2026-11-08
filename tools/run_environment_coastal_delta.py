"""Run finite same-mouth delta/G8 from hash-validated regional export packets."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terrain_pipeline.environment_coastal_delta import (
    load_coastal_delta, prepare_coastal_delta, run_coastal_delta, save_coastal_delta,
    continue_coastal_delta,
)
from terrain_pipeline.common_infra import file_sha256, publish_bytes


def render(result, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    a, m = result["arrays"], result["metadata"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
    image = axes[0].imshow(a["height_delta_m"], cmap="viridis", origin="upper")
    fig.colorbar(image, ax=axes[0], label="Actual sediment-derived bed change (m)")
    axes[0].set_title("Actual finite bed change; max %.3e m" % np.max(a["height_delta_m"]))
    axes[1].imshow(a["final_bed_m"], cmap="terrain", origin="upper")
    origin = np.asarray(m["prepared_source"]["origin_native_xz"]) * 30.
    for name in ("trunk0", "trunk1", "branch0", "branch1", "branch2"):
        points = (a["path_" + name] - origin) / 30.
        axes[1].plot(points[:, 0], points[:, 1], label=name, linewidth=1.5)
    axes[1].contour(a["depth_m"] > 0., levels=[.5], colors="cyan", linewidths=.5)
    axes[1].legend(fontsize=8)
    axes[1].set_title("Saved bed + declared reduced branch paths")
    for axis in axes:
        axis.set_xlabel("Native column (30m)")
        axis.set_ylabel("Native row (30m)")
    fig.savefig(destination, dpi=150)
    plt.close(fig)


def coastal_rain_packets(store, output):
    """Actual explicit-v2 rain/weathering export, then existing regional solvers."""
    from terrain_pipeline.environment_product import context_from_store
    from terrain_pipeline.environment_product import initialize, advance, save_product, product_identity
    from terrain_pipeline.environment_regional_hydraulics import prepare_process_handoff, advance as route, save_checkpoint
    ctx, sources = context_from_store(store, 0, 168, 33)
    selected = [609, 608]
    mask = np.zeros((33, 33), bool)
    mask.ravel()[selected] = True
    initial_ice = np.where(mask, .02, 0.)
    product = initialize(ctx, sources, mode="explicit-v2", initial={
        "soil_chemistry": {"water_depth_m": 0.},
        "frozen_ground": {"liquid_water_m": 0., "ground_ice_m": initial_ice}})
    save_product(product, output / "source-initial.npz")
    forcing = {"rainfall_m_s": 2e-5, "air_temperature_c": 12., "hydraulic_handoff_mask": mask,
               "groundwater": {"surface_conductance_m2_s": 0.},
               "mass": {"transport_fraction_per_s": .001, "repose_angle_deg": 0.}}
    completed = advance(product, forcing, 3600.)
    save_product(completed, output / "source-completed.npz")
    rows, cols = np.indices((33, 33))
    ids = (rows * 256 + cols + 168).astype(np.int64)
    regions = prepare_process_handoff(completed, ids, time_start_s=0., selected_nodes=selected)
    save_checkpoint(output / "regions-initial", regions)
    regions = route(regions, 30.)
    save_checkpoint(output / "regions-checkpoint", regions)
    regions = route(regions, 30.)
    save_checkpoint(output / "regions-final", regions)
    mouth = next(value for value in regions.values() if value["metadata"]["target_node"] == 4534)
    packets = mouth["metadata"]["exports"]
    publish_bytes(output / "packets.json", json.dumps(packets, indent=2).encode())
    publish_bytes(output / "source-evidence.json", json.dumps({
        "source_product_identity": product_identity(completed), "forcing": {
            "rainfall_m_s": 2e-5, "temperature_c": 12., "duration_s": 3600.,
            "initial_selected_ground_ice_m": .02, "initial_liquid_and_soil_water_m": 0.,
            "status": "declared engineering explicit-v2, not climate-supported coastal weather"},
        "source_world_identity": sources["source_world_identity"],
        "initial_regional_water_and_solid": "zero; only actual source exports received",
        "exported_water_m3": float(completed["last_transfers"]["external_hydraulic_water_m3"].sum()),
        "exported_solid_m3": float(completed["last_transfers"]["external_hydraulic_solid_m3"].sum()),
        "source_budget": completed["last_budget"],
        "regional_final": {key: {
            "water_m3": float(value["arrays"]["water_m3"].sum()),
            "mobile_solid_m3": float(value["arrays"]["mobile_solid_m3"].sum()),
            "bed_alluvium_solid_m3": float(value["arrays"]["loose_solid_m3"].sum()),
            "cumulative_rock_erosion_m3": float(value["arrays"]["rock_removed_m3"].sum()),
            "exports": value["metadata"]["exports"]} for key, value in regions.items()},
        "regional_last_solver": mouth["metadata"]["last_solver"]}, indent=2).encode())
    return packets


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=ROOT / ".scratch/river-generation-review/real-coastal")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--packets", type=Path)
    source.add_argument("--coastal-rain-scenario", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    packets = (coastal_rain_packets(args.store, args.output) if args.coastal_rain_scenario else
               json.loads(args.packets.read_text(encoding="utf-8")))
    prepared = prepare_coastal_delta(args.store)
    result = run_coastal_delta(prepared, packets)
    control = run_coastal_delta(prepared, packets, zero_sediment_control=True)
    save_coastal_delta(args.output / "delta.npz", result)
    save_coastal_delta(args.output / "zero-sediment.npz", control)
    cold = load_coastal_delta(args.output / "delta.npz", expected_sha256=file_sha256(args.output / "delta.npz"))
    checks = {"cold_identity": cold["identity_sha256"] == result["identity_sha256"],
              "nonzero_deposition": result["metadata"]["solid_ledger"]["deposited_solid_m3"] > 0.,
              "zero_sediment_no_added_bed": bool(np.all(control["arrays"]["height_delta_m"] == 0.)),
              "same_input_water": result["metadata"]["marine_ledger"]["river_water_input_m3"] ==
                                  control["metadata"]["marine_ledger"]["river_water_input_m3"],
              "no_construction_supply": result["metadata"]["construction_budget"]["excavated_solid_m3"] == 0.}
    if len(packets) > 1:
        first = run_coastal_delta(prepared, packets[:1])
        save_coastal_delta(args.output / "delta-checkpoint.npz", first)
        first = load_coastal_delta(args.output / "delta-checkpoint.npz",
                                  expected_sha256=file_sha256(args.output / "delta-checkpoint.npz"))
        continued = continue_coastal_delta(first, packets[1:])
        save_coastal_delta(args.output / "delta-continued.npz", continued)
        checks["cold_continue_matches_batch"] = continued["identity_sha256"] == result["identity_sha256"]
    report = {"checks": checks, "solid_ledger": result["metadata"]["solid_ledger"],
              "marine_ledger": result["metadata"]["marine_ledger"],
              "identity_sha256": result["identity_sha256"], "packet_source_sha256": file_sha256(
                  args.output / "packets.json" if args.coastal_rain_scenario else args.packets),
              "source_world_identity": prepared["metadata"]["source_world_identity"]}
    publish_bytes(args.output / "acceptance.json", json.dumps(report, indent=2).encode())
    render(result, args.output / "bed-and-branches.png")
    print(json.dumps(report, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
