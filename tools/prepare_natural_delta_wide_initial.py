"""Explicit counterfactual wide incoming river on the unchanged marine base."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import file_sha256
from tools.prepare_natural_delta_expanded_initial import SCENE, CENTERLINE, FORCING


def prepare():
    with np.load(SCENE) as saved:
        meta = json.loads(str(saved["metadata_json"]))
        source = {key: saved[key] for key in ("base_bed_m", "macro_bed_m", "raw_td_sample_m", "td_residual_m")}
    mouth = np.asarray(meta["mouth_xz_m"])
    with np.load(CENTERLINE) as saved:
        path = saved["node_xz_m"]
        direction = path[-1] - path[0]
    direction /= np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    rows, cols = np.indices((220, 240))
    station = rows * 5. - 360.
    cross = (cols - 120) * 5.
    world = mouth + station[..., None] * direction + cross[..., None] * normal
    coordinates = (world - np.asarray(meta["origin_xz_m"])) / float(meta["spacing_m"])
    if coordinates.min() < 0. or coordinates[..., 0].max() > 799. or coordinates[..., 1].max() > 799.:
        raise ValueError("wide initial state exceeds scene support")
    arrays = {name: map_coordinates(source[field], [coordinates[..., 1], coordinates[..., 0]], order=1)
        for name, field in (("source_base_bed_m", "base_bed_m"), ("source_macro_bed_m", "macro_bed_m"),
            ("raw_td_sample_m", "raw_td_sample_m"), ("source_td_residual_m", "td_residual_m"))}
    base = arrays["source_base_bed_m"]
    inlet = np.arange(112, 128, dtype=np.int64)
    inlet_bed = float(base[0, 120] - 4.)
    fraction = np.clip((station + 360.) / 360., 0., 1.)
    mouth_section = base[72][None, :]
    target = inlet_bed * (1. - fraction) + mouth_section * fraction
    lateral_distance = np.maximum.reduce([112 - cols, cols - 127, np.zeros_like(cols)]) * 5.
    taper = np.clip(1. - lateral_distance / 20., 0., 1.)
    construction = np.minimum(target - base, 0.) * taper
    construction[station >= 0.] = 0.
    bed = base + construction
    edge = np.zeros_like(bed, bool)
    edge[[0, -1]] = True
    edge[:, [0, -1]] = True
    cell_type = np.zeros(bed.shape, np.int64)
    cell_type[edge & (bed >= 0.)] = -2
    cell_type[edge & (bed < 0.)] = -1
    stub = np.zeros_like(edge)
    stub[:2, inlet] = True
    cell_type[stub] = 1
    inlet_stage = inlet_bed + 4.
    center_stage = np.interp(station[:, 0], [-360., 0., 400., 735.], [inlet_stage, 3., 0., 0.])
    # This is a declared non-equilibrium flood/plume initial water state.
    # Only row zero is maintained as a boundary by the independent runner.
    stage = np.maximum(bed, 0.)
    stage = np.maximum(stage, center_stage[:, None] * taper)
    depth = stage - bed
    floor = bed - .3
    floor[edge] = bed[edge]
    with np.load(FORCING) as saved:
        q = float(saved["water_q_m3_s"][0, -1])
    section_area = depth[:, inlet].sum(axis=1) * 5.
    sections = [{"station_m": float(station[row, 120]), "center_base_m": float(base[row, 120]),
        "center_bed_m": float(bed[row, 120]), "center_stage_m": float(stage[row, 120]),
        "center_depth_m": float(depth[row, 120]), "core_width_m": 80.,
        "core_wet_area_m2": float(section_area[row]),
        "q_divided_by_core_area_m_s": float(q / section_area[row]) if section_area[row] > 0. else None}
        for row in range(220)]
    arrays.update(initial_bed_m=bed, initial_stage_m=stage, initial_depth_m=depth,
        local_world_xz_m=world, station_m=station, cross_stream_m=cross,
        construction_height_delta_m=construction, cell_type=cell_type, inlet_columns=inlet,
        inlet_stub_mask=stub, fixed_boundary_mask=edge, source_floor_m=floor,
        initial_erodible_solid_m3=(bed - floor) * 25. * .65)
    center_rise = np.diff(bed[:73, 120])
    core_rise = np.diff(bed[:73, inlet], axis=0)
    report = {"schema": "wide-counterfactual-natural-initial-v1", "status": "prepared-for-short-validation",
        "scenario": "independent counterfactual 80m incoming river; not recovery of archived 8m sections",
        "parent_checkpoint": None, "old_final_bed_imported": False, "relative_piece_cuts_imported": False,
        "source_scene": str(SCENE), "source_scene_sha256": file_sha256(SCENE), "source_field": "base_bed_m",
        "saved_centerline": str(CENTERLINE), "saved_centerline_sha256": file_sha256(CENTERLINE),
        "source_role": "frozen macro+0.35 TD residual; real saved incoming path direction only",
        "frame": {"direction_xz": direction.tolist(), "normal_xz": normal.tolist(), "mouth_xz_m": mouth.tolist()},
        "shape": [220, 240], "dx_m": 5., "extent_m": [1200., 1100.],
        "construction": {"policy": "landward cut-only linear bottom to original mouth section; 20m bank transition; no marine cut",
            "cut_bulk_m3": float(-construction.sum() * 25.), "fill_bulk_m3": 0.,
            "role": "explicit initial geometry removal; not injected or exported model sediment",
            "marine_base_exact": bool(np.array_equal(bed[station >= 0.], base[station >= 0.])),
            "maximum_center_downstream_rise_m": float(max(0., center_rise.max())),
            "maximum_core_downstream_rise_m": float(max(0., core_rise.max())),
            "mouth_center_jump_m": float(bed[72, 120] - bed[71, 120])},
        "inlet": {"columns": inlet.tolist(), "width_m": 80., "h0_m": 4., "native_L0_m": 10.,
            "bed_m": inlet_bed, "stage_m": inlet_stage, "q_m3_s": q, "u0_m_s": q / 320.,
            "external_boundary": "specified upstream flood stage and discharge of this counterfactual; not sea level",
            "native_finalize": "row0 only eta=specified-stage-h0; delta retained as inlet correction budget",
            "stage_depth_bed_max_error_m": float(abs(stage[0, inlet] - 4. - bed[0, inlet]).max())},
        "initial_water": {"policy": "non-equilibrium flood: inlet head to mouth+3m, then linearly to far-sea0 at400m; 20m lateral transition",
            "fixed_each_step": "row0 inlet only; all interior stages evolve freely",
            "volume_m3": float(depth.sum() * 25.),
            "excess_above_sea_equilibrium_m3": float((depth - np.maximum(-bed, 0.)).sum() * 25.),
            "velocity_target_m_s": [1., 2.], "maximum_core_velocity_inlet_to_sea50m_m_s": float(np.max(q / section_area[:83])),
            "not_hydraulic_equilibrium_or_tide_solution": True},
        "sections": sections, "substrate_cover_m": .3,
        "substrate_inventory_solid_m3": float(arrays["initial_erodible_solid_m3"].sum()),
        "substrate_role": "finite cover under constructed bed; no boundary sediment entitlement",
        "forcing": {"source": str(FORCING), "sha256": file_sha256(FORCING),
            "scenario": "old annual finite source replayed as a separate initial counterfactual, no continuation ancestry"},
        "simulations_started": 0, "injected_boundary_solid_m3": 0.}
    if report["construction"]["maximum_core_downstream_rise_m"] > 1.e-7:
        raise ValueError("cut-only adapted core contains adverse longitudinal slope")
    return arrays, report


def render(output, arrays, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    extent = [-602.5, 597.5, 737.5, -362.5]
    for ax, key, title in ((axes[0, 0], "initial_bed_m", "Counterfactual 80m incoming river; marine base unchanged"),
            (axes[0, 1], "construction_height_delta_m", "Explicit initial cut (m), not sediment input")):
        im = ax.imshow(arrays[key], extent=extent, cmap="terrain" if key == "initial_bed_m" else "RdBu_r")
        ax.axhline(0., color="black", linewidth=.7)
        ax.set(xlabel="Cross stream (m)", ylabel="Station from mouth (m)", title=title)
        fig.colorbar(im, ax=ax, shrink=.8)
    sections = report["sections"]
    x = [s["station_m"] for s in sections]
    for key, label in (("center_base_m", "Frozen base"), ("center_bed_m", "Initial bed"), ("center_stage_m", "Non-equilibrium initial stage")):
        axes[1, 0].plot(x, [s[key] for s in sections], label=label)
    axes[1, 0].legend()
    axes[1, 0].set(xlabel="Station (m)", ylabel="Elevation (m)", xlim=(-360., 450.), title="Longitudinal bed / initial water")
    axes[1, 1].plot(x, [s["q_divided_by_core_area_m_s"] for s in sections])
    axes[1, 1].axhline(2., color="gray", linestyle="--")
    axes[1, 1].set(xlabel="Station (m)", ylabel="Q / 80m core wet area (m/s)", xlim=(-360., 100.), title="Section preflight including mouth and marine +50m")
    fig.savefig(output / "initialization.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    arrays, report = prepare()
    report["implementation_hashes"] = {"tools/prepare_natural_delta_wide_initial.py": file_sha256(Path(__file__)),
        "tools/prepare_natural_delta_expanded_initial.py": file_sha256(ROOT / "tools/prepare_natural_delta_expanded_initial.py")}
    args.output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.output / "initialization.npz", **arrays)
    report["initialization_sha256"] = file_sha256(args.output / "initialization.npz")
    (args.output / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    render(args.output, arrays, report)
    print(json.dumps({k: v for k, v in report.items() if k != "sections"}, indent=2))


if __name__ == "__main__":
    main()
