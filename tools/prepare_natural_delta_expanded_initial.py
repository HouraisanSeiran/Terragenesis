"""Independent expanded initial state from frozen base and saved relative cuts."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256

SCENE = ROOT / ".scratch/hydrological-planning-domain/coast-bounded-mouth-16km-20261017-15/scene.npz"
CENTERLINE = ROOT / ".scratch/hydrological-planning-domain/saved-bed-mouth-20261016-01/centerline.npz"
FORCING = ROOT / "verification/fluvial-delta/adaptive-tree-16km-20261018-02/feedback_bundle.npz"


def sample_piece(piece, world):
    import matplotlib.tri as tri
    with np.load(piece["source_path"]) as saved:
        vertices = saved["vertices_xz_m"]
        origin = vertices[0]
        mesh = tri.Triangulation(*(vertices - origin).T, triangles=saved["triangles"])
        values = tri.LinearTriInterpolator(mesh, saved["local_channel_delta_m"])(
            world[..., 0] - origin[0], world[..., 1] - origin[1])
        delta = np.asarray(values.filled(0.), float)
        if delta.max() > 1.e-8:
            raise ValueError("saved relative channel field contains fill")
        return np.minimum(delta, 0.), ~np.ma.getmaskarray(values), {
            "index": piece["index"], "path": piece["source_path"],
            "sha256": file_sha256(Path(piece["source_path"])),
            "identity": piece["identity"], "field": "local_channel_delta_m",
            "node_width_m": saved["width_m"].tolist(),
            "source_delta_range_m": [float(saved["local_channel_delta_m"].min()),
                float(saved["local_channel_delta_m"].max())]}


def prepare():
    with np.load(SCENE) as saved:
        meta = json.loads(str(saved["metadata_json"]))
        direction = np.asarray(meta["river_direction_xz"], float)
        direction /= np.linalg.norm(direction)
        normal = np.array([-direction[1], direction[0]])
        rows, cols = np.indices((220, 240))
        station = rows * 5. - 360.
        cross = (cols - 120) * 5.
        world = np.asarray(meta["mouth_xz_m"]) + station[..., None] * direction + cross[..., None] * normal
        coordinates = (world - np.asarray(meta["origin_xz_m"])) / float(meta["spacing_m"])
        if (coordinates.min() < 0. or coordinates[..., 0].max() > saved["base_bed_m"].shape[1] - 1
                or coordinates[..., 1].max() > saved["base_bed_m"].shape[0] - 1):
            raise ValueError("expanded initial state leaves frozen source")
        arrays = {name: map_coordinates(saved[source], [coordinates[..., 1], coordinates[..., 0]], order=1)
            for name, source in (("source_base_bed_m", "base_bed_m"), ("source_macro_bed_m", "macro_bed_m"),
                ("raw_td_sample_m", "raw_td_sample_m"), ("source_td_residual_m", "td_residual_m"))}
    with np.load(CENTERLINE) as saved:
        pieces = [p for p in json.loads(str(saved["metadata_json"]))["pieces"] if p["index"] in (15, 16, 17)]
    deltas, supports, identities = [], [], []
    for piece in pieces:
        if file_sha256(Path(piece["source_path"])) != piece["archive_sha256"]:
            raise ValueError("saved river piece identity changed")
        delta, support, identity = sample_piece(piece, world)
        deltas.append(delta)
        supports.append(support)
        identities.append(identity)
    relative = np.minimum.reduce(deltas)
    relative[station >= 0.] = 0.
    base = arrays["source_base_bed_m"]
    bed = base + relative
    # A single 5m-wide inlet follows the represented 8m source section. Only
    # its first 10m are boundary stub; the remaining imported cut is interior.
    inlet = np.array([120], dtype=np.int64)
    stub = np.zeros_like(bed, bool)
    stub[:2, inlet] = True
    cell_type = np.zeros(bed.shape, np.int64)
    edge = np.zeros_like(stub)
    edge[[0, -1]] = True
    edge[:, [0, -1]] = True
    cell_type[edge & (bed >= 0.)] = -2
    cell_type[edge & (bed < 0.)] = -1
    cell_type[stub] = 1
    floor = bed - .3
    floor[edge] = bed[edge]
    # Initial wetting is an explicit water-state hypothesis, not added bed.
    # Water follows the local base datum with 0.25m head above that datum,
    # on the imported channel support only; sea water remains at zero.
    stage = np.maximum(bed, 0.)
    channel = (relative < -1.e-8) & (station < 0.)
    stage[channel] = np.maximum(base[channel] + .25, 0.)
    depth = stage - bed
    inlet_stage = float(stage[0, 120])
    inlet_depth = float(depth[0, 120])
    overlap = []
    for i in range(len(deltas)):
        for j in range(i + 1, len(deltas)):
            mask = supports[i] & supports[j] & (station < 0.)
            if mask.any():
                overlap.append({"pieces": [identities[i]["index"], identities[j]["index"]],
                    "sample_cells": int(mask.sum()), "maximum_delta_disagreement_m":
                        float(abs(deltas[i][mask] - deltas[j][mask]).max()),
                    "samples": [{"station_m": float(station[row, col]), "cross_m": float(cross[row, col]),
                        "first_delta_m": float(deltas[i][row, col]), "second_delta_m": float(deltas[j][row, col])}
                        for row, col in np.argwhere(mask)]})
    profile = bed[:73, 120]
    rises = np.diff(profile)
    mouth_jump = float(bed[72, 120] - bed[71, 120])
    arrays.update(initial_bed_m=bed, initial_stage_m=stage, initial_depth_m=depth,
        source_floor_m=floor, local_world_xz_m=world, station_m=station, cross_stream_m=cross,
        construction_height_delta_m=relative, saved_relative_channel_delta_m=np.stack(deltas),
        source_piece_support_mask=np.stack(supports), inlet_columns=inlet, inlet_stub_mask=stub,
        fixed_boundary_mask=edge, cell_type=cell_type,
        initial_erodible_solid_m3=(bed - floor) * 25. * .65)
    sections = [{"station_m": float(station[row, 120]), "base_center_m": float(base[row, 120]),
        "bed_center_m": float(bed[row, 120]), "relative_center_cut_m": float(-relative[row, 120]),
        "represented_cut_width_m": float(np.sum(relative[row] < -1.e-4) * 5.),
        "initial_center_depth_m": float(depth[row, 120]), "initial_center_stage_m": float(stage[row, 120])}
        for row in range(73)]
    with np.load(FORCING) as saved:
        source_q = saved["water_q_m3_s"][:, -1]
        first_q = float(source_q[0])
    velocity = first_q / (5. * inlet_depth)
    report = {"schema": "expanded-independent-natural-initial-v1", "status": "geometry-and-inlet-preflight-failed",
        "independent_initial_scenario": True, "parent_checkpoint": None, "old_final_bed_imported": False,
        "source_scene": str(SCENE), "source_scene_sha256": file_sha256(SCENE),
        "source_field": "base_bed_m", "source_role": "frozen macro + 0.35 TD residual; no constructed scene bed",
        "saved_centerline": str(CENTERLINE), "saved_centerline_sha256": file_sha256(CENTERLINE),
        "relative_channel_sources": identities, "relative_channel_policy":
            "linear interpolation on archived triangles; minimum cut on shared support; applied only station<0; no absolute river elevations",
        "shape": [220, 240], "dx_m": 5., "extent_m": [1200., 1100.],
        "station_center_range_m": [-360., 735.], "cross_center_range_m": [-600., 595.],
        "sea_side_base_exact": bool(np.array_equal(bed[station >= 0.], base[station >= 0.])),
        "construction_cut_bulk_m3": float(-relative.sum() * 25.), "construction_fill_bulk_m3": 0.,
        "construction_role": "initial geometric adaptation; removed cut is not upstream sediment supply",
        "local_substrate_inventory_solid_m3": float(arrays["initial_erodible_solid_m3"].sum()),
        "substrate_role": "0.3m finite erodible cover beneath adapted bed; not boundary supply",
        "piece_overlap_seams": overlap, "centerline_sections": sections,
        "maximum_downstream_bed_rise_m": float(max(0., rises.max())),
        "adverse_centerline_steps": [{"from_station_m": float(station[k, 120]), "rise_m": float(value)}
            for k, value in enumerate(rises) if value > 1.e-6],
        "mouth_last_land_to_base_jump_m": mouth_jump,
        "mouth_jump_policy": "measured unchanged; no forced slope, marine cut or fill repair",
        "inlet": {"columns": inlet.tolist(), "width_m": 5., "native_L0_m": 10.,
            "bed_m": float(bed[0, 120]), "stage_m": inlet_stage, "depth_m": inlet_depth,
            "stage_policy": "base+0.25m over relative cut; sea level zero outside imported channel",
            "native_eta_equals_stage_minus_h0_error_m": float(inlet_stage - inlet_depth - bed[0, 120]),
            "hydraulic_acceptance": False, "stage_is_external_boundary_basis": False,
            "forcing_source": str(FORCING), "forcing_sha256": file_sha256(FORCING),
            "forcing_scenario": "old annual source, independent initial scenario only; no parent-chain reuse or packets delivered",
            "first_source_q_m3_s": first_q, "annual_q_range_m3_s": [float(source_q.min()), float(source_q.max())],
            "first_q_divided_by_native_width_depth_velocity_m_s": velocity,
            "first_q_inlet_froude": float(velocity / np.sqrt(9.81 * inlet_depth)),
            "full_initialized_section_area_m2": float(depth[0].sum() * 5.),
            "first_q_full_section_mean_velocity_m_s": float(first_q / (depth[0].sum() * 5.))},
        "water_initialization": "channel wetting hypothesis only; no momentum generated, no hydraulic equilibrium or external boundary claim",
        "short_validation": {"status": "not-runnable-preflight-failed", "command": None,
            "reasons": ["relative-cut clipping creates measured adverse mouth step",
                "shared archived relative cuts disagree on overlapping support",
                "saved 8m source geometry with declared initial wetting does not provide an accepted section for annual source Q"],
            "policy": "do not write or run a solver adapter on failed geometry; no fixed water surface chosen to evade source-floor checks"},
        "simulations_started": 0, "new_boundary_supply_delivered_solid_m3": 0.}
    return arrays, report


def render(output, arrays, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    extent = [-602.5, 597.5, 737.5, -362.5]
    for ax, key, title in ((axes[0, 0], "initial_bed_m", "Independent base + saved relative landward cut"),
            (axes[0, 1], "construction_height_delta_m", "Geometric cut only; marine side unchanged")):
        im = ax.imshow(arrays[key], extent=extent, cmap="terrain" if key == "initial_bed_m" else "RdBu_r")
        ax.axhline(0., color="black", linewidth=.7)
        ax.set(xlabel="Cross stream (m)", ylabel="Station from mouth (m)", title=title)
        fig.colorbar(im, ax=ax, label="m", shrink=.8)
    sections = report["centerline_sections"]
    station = [s["station_m"] for s in sections]
    for key, label in (("base_center_m", "Same-source base"), ("bed_center_m", "Adapted bed"),
            ("initial_center_stage_m", "Initial water surface")):
        axes[1, 0].plot(station, [s[key] for s in sections], label=label)
    axes[1, 0].set(xlabel="Station (m)", ylabel="Elevation (m)", title="Centerline: measured mouth lip retained")
    axes[1, 0].legend()
    for station_value in (-360., -180., -10., -5., 0.):
        row = int((station_value + 360.) / 5.)
        axes[1, 1].plot(arrays["cross_stream_m"][row, 116:125], arrays["initial_bed_m"][row, 116:125], label=f"{station_value:g}m")
    axes[1, 1].set(xlabel="Cross stream (m)", ylabel="Bed elevation (m)", title="Actual 5m grid cross sections")
    axes[1, 1].legend()
    fig.savefig(output / "initialization.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    arrays, report = prepare()
    report["implementation_hashes"] = {str(Path(__file__).relative_to(ROOT)).replace("\\", "/"): file_sha256(Path(__file__))}
    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output / "initialization.npz", **arrays)
    report["initialization_sha256"] = file_sha256(args.output / "initialization.npz")
    (args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render(args.output, arrays, report)
    print(json.dumps({k: v for k, v in report.items() if k != "centerline_sections"}, indent=2))


if __name__ == "__main__":
    main()
