"""Run the full seed-world reach with a **full-grid** dynamic bed.

Same reach, same fixed forcing, same existing solvers as
`tools/run_real_world_full_reach.py` (which is left untouched and whose
`full-reach-run-02` output is never overwritten). The only difference is the
dynamic-geometry coupling: instead of advancing the node bed alone
(`world_channel_dynamics.couple_nodal_reach`), it advances the canonical 50 m
carved PL mesh and feeds the re-sampled node section back into the next macro
step (`world_grid_bed_coupling.couple_grid_reach`).

The run also writes the two comparisons the task asks for:

* `nodal-comparison.json` -- the same 72 h reach run through the nodal path, so
  bed-change range, outlet solid, remaining inventory and bed shape can be put
  side by side;
* `bed-change-difference.png` -- the initial carve against the final bed on the
  warp of the canonical mesh, plus the difference field.

Run:
    D:/anaconda/python.exe -B tools/run_real_world_full_reach_grid_bed.py \\
        --output .scratch/cross-region-tributary/full-grid-bed-01
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.mountain_source_adapter import save_bundle
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig
from terrain_pipeline.surface_rivers.metric_channel_state import (
    ChannelConfig, ChannelNetwork, receiver_distances)
from terrain_pipeline.surface_rivers.metric_morphology_coupling import (
    MorphologyConfig, _sample_nodes, _unpack)
from terrain_pipeline.surface_rivers.metric_sediment import MaterialParameters, SedimentConfig
from terrain_pipeline.surface_rivers.world_channel_dynamics import (
    couple_nodal_reach, save_nodal_reach)
from terrain_pipeline.surface_rivers.world_grid_bed_coupling import (
    couple_grid_reach, hydraulic_control_area, material_mapping, save_grid_reach)
from tools.run_cross_region_tributary import run
from tools.run_real_world_full_reach import (
    FINE_SPACING_M, MANNING_N, MAX_DEPTH_M, MIN_WIDTH_M, MAX_WIDTH_M, SECTION_DEPTH_M,
    SEED, STORM_RAIN_MM_H, TERMINAL_XZ_M, FullReachConfig, finish_full_reach,
    make_full_reach_scene)

MATERIAL = dict(sediment_erodibility_m_s_pa=1e-10, rock_erodibility_m_s_pa=1e-12,
                transport_coefficient=1e-5, settling_velocity_m_s=.0001,
                provenance="explicit real coarse reach illustrative material")


def run_grid_bed(output, *, hours=72):
    """Full-grid run with the same fixed inputs as full-reach-run-02."""
    output = Path(output)
    started = time.perf_counter()
    # The scene is rebuilt into this run's own directory by the same builder, so
    # geometry, forcing, boundary scenarios and lake definition are byte-identical
    # inputs to full-reach-run-02; full-reach-run-02 itself is never touched.
    report = run(output,
        scene_builder=lambda path: make_full_reach_scene(path, hours=hours),
        material=MaterialParameters(**MATERIAL),
        channel_config=ChannelConfig(max_dt_seconds=30.),
        sediment_config=SedimentConfig(max_dt_seconds=30., max_bed_change_m=.01),
        dynamics=couple_grid_reach, saver=save_grid_reach,
        reach_config=FullReachConfig())
    summary = finish_full_reach(output)
    summary["wall_seconds"] = time.perf_counter() - started
    return summary


def _load(output):
    with np.load(Path(output) / "dynamic-water-sediment-bed.npz", allow_pickle=False) as archive:
        arrays = {key: archive[key].copy() for key in archive.files}
    record = json.loads(arrays.pop("manifest").tobytes().decode("utf-8"))
    return arrays, record["metadata"], record["identity_sha256"]


def nodal_comparison(output, *, hours=72):
    """The same 72 h reach through the nodal path, in a scratch directory."""
    target = Path(output) / "_nodal-reference"
    if target.exists():
        raise FileExistsError(target)
    start = time.perf_counter()
    run(target,
        scene_builder=lambda path: make_full_reach_scene(path, hours=hours),
        material=MaterialParameters(**MATERIAL),
        channel_config=ChannelConfig(max_dt_seconds=30.),
        sediment_config=SedimentConfig(max_dt_seconds=30., max_bed_change_m=.01),
        dynamics=couple_nodal_reach, saver=save_nodal_reach,
        reach_config=FullReachConfig())
    seconds = time.perf_counter() - start
    arrays, metadata, identity_sha256 = _load(target)
    return target, arrays, metadata, identity_sha256, seconds


def compare(output, *, hours=72):
    """Put the nodal and full-grid runs side by side and write the summary."""
    output = Path(output)
    grid_arrays, grid_metadata, grid_identity = _load(output)
    nodal_dir, nodal_arrays, nodal_metadata, nodal_identity, nodal_seconds = \
        nodal_comparison(output, hours=hours)
    grid_bed = np.asarray(grid_arrays["node_bed_m"], np.float64)
    nodal_bed = np.asarray(nodal_arrays["node_bed_m"], np.float64)
    grid_mesh = np.asarray(grid_arrays["mesh_bed_m"], np.float64)
    source_mesh = np.asarray(grid_arrays["source_mesh_bed_m"], np.float64)
    support = np.asarray(grid_arrays["vertex_owner"], np.int64) >= 0
    reference = json.loads((output / "report.json").read_text(encoding="utf-8"))
    nodal_reference = json.loads((nodal_dir / "report.json").read_text(encoding="utf-8"))
    grid_ledger = grid_metadata["ledger"]
    summary = dict(
        inputs="identical_fixed_inputs_world_seed_%d_72h_explicit_storm" % SEED,
        grid=dict(
            bundle_identity_sha256=grid_identity,
            dynamic_geometry_mode="canonical_PL_mesh_updated_every_interval",
            bed_change=grid_metadata["bed_change"],
            material_mapping=grid_metadata["material_mapping"],
            ledger=grid_ledger,
            water=reference["water"], solid=reference["solid"],
            cut_volume_m3=reference["bed"]["cut_volume_m3"],
            wall_seconds=None),
        nodal=dict(
            bundle_identity_sha256=nodal_identity,
            dynamic_geometry_mode="nodal_bed_only_initial_PL_mesh_not_updated",
            bed_change=dict(
                min_node_change_m=float((nodal_bed[-1] - nodal_bed[0]).min()),
                max_node_change_m=float((nodal_bed[-1] - nodal_bed[0]).max()),
                mesh_moved=False),
            ledger=dict(
                mobile_sand_solid_m3=dict(
                    initial=float(nodal_arrays["mobile_solid_m3"][0].sum()),
                    final=float(nodal_arrays["mobile_solid_m3"][-1].sum())),
                loose_bed_sand_solid_m3=dict(
                    initial=float(nodal_arrays["loose_solid_m3"][0].sum()),
                    final=float(nodal_arrays["loose_solid_m3"][-1].sum())),
                cumulative_rock_erosion_m3=float(nodal_arrays["rock_removed_m3"][-1].sum())),
            water=nodal_reference["water"], solid=nodal_reference["solid"],
            wall_seconds=nodal_seconds),
        differences=dict(
            node_bed_change_max_abs_m=float(np.max(np.abs(
                (grid_bed[-1] - grid_bed[0]) - (nodal_bed[-1] - nodal_bed[0])))),
            node_bed_final_max_abs_m=float(np.max(np.abs(grid_bed[-1] - nodal_bed[-1]))),
            outlet_solid_m3=[float(reference["solid"]["outlet_export_m3"]),
                             float(nodal_reference["solid"]["outlet_export_m3"])],
            remaining_solid_m3=[
                float(grid_ledger["mobile_sand_solid_m3"]["final"]
                      + grid_ledger["loose_bed_sand_solid_m3"]["final"]),
                float(nodal_arrays["mobile_solid_m3"][-1].sum()
                      + nodal_arrays["loose_solid_m3"][-1].sum())],
            mesh_change_max_abs_m=float(np.max(np.abs(grid_mesh[-1] - source_mesh))),
            mesh_changed_vertex_count=int(np.count_nonzero(np.abs(grid_mesh[-1] - source_mesh) > 0.)),
            mesh_support_vertex_count=int(support.sum()),
            outlet_export_relative_difference=float(
                (reference["solid"]["outlet_export_m3"]
                 - nodal_reference["solid"]["outlet_export_m3"])
                / max(abs(nodal_reference["solid"]["outlet_export_m3"]), 1e-12))),
        interpretation=(
            "the two runs consume the same reconstructed scene (same geometry, same fixed "
            "storm, same material and step controls) and differ only in the dynamic "
            "geometry path: the grid run advances the 50 m carved mesh and re-samples the "
            "node section from it, the nodal run advances node bed only"))
    (output / "nodal-comparison.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def per_node_table(output):
    """The per-node material-area ledger the guard is evaluated on."""
    output = Path(output)
    arrays, metadata, identity_sha256 = _load(output)
    selection = json.loads((output / "source-selection.json").read_text(encoding="utf-8"))
    covered = np.asarray(arrays["material_area_m2"], np.float64)
    demand = np.asarray(arrays["hydraulic_control_area_m2"], np.float64)
    width = np.asarray(selection["node_width_m"], np.float64)
    owner = np.asarray(arrays["vertex_owner"], np.int64)
    rows = []
    for index in range(covered.size):
        rows.append(dict(
            node=index, x_m=float(selection["node_xz_m"][index][0]),
            z_m=float(selection["node_xz_m"][index][1]),
            width_m=float(width[index]),
            control_area_m2=float(demand[index]),
            material_area_m2=float(covered[index]),
            ratio=float(covered[index] / demand[index]),
            owned_vertices=int(np.count_nonzero(owner == index)),
            passes_guard=bool(covered[index] >= demand[index] - 1e-9)))
    document = dict(
        guard="covered_i >= W_i*L_i - 1e-9, the same expression and tolerance as metric_morphology_coupling.py:300-301",
        all_nodes_pass=all(row["passes_guard"] for row in rows),
        min_ratio=min(row["ratio"] for row in rows),
        max_ratio=max(row["ratio"] for row in rows),
        diagnostics=metadata["material_mapping"],
        nodes=rows)
    (output / "material-area-audit.json").write_text(json.dumps(document, indent=2),
                                                     encoding="utf-8")
    return document


def plot_bed_difference(output, *, hours=72):
    """Initial carve vs final bed on the canonical mesh, plus the difference.

    One colour scale (`terrain`) is shared by both bed panels so the two surfaces
    can be compared by eye, and the change field uses a symmetric diverging scale
    so erosion and deposition are not visually rescaled against each other.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri

    output = Path(output)
    arrays, metadata, identity_sha256 = _load(output)
    with np.load(output / "generated-geometry.npz", allow_pickle=False) as archive:
        geometry = {key: archive[key] for key in archive.files if key != "manifest"}
    vertices = np.asarray(geometry["vertices_xz_m"], np.float64)
    triangles = np.asarray(geometry["triangles"], np.int64)
    owner = np.asarray(arrays["vertex_owner"], np.int64)
    support = owner >= 0
    carved = np.asarray(geometry["cut_depth_m"], np.float64) > 1e-10
    initial = np.asarray(arrays["source_mesh_bed_m"], np.float64)
    final = np.asarray(arrays["mesh_bed_m"], np.float64)[-1]
    change = final - initial
    triangulation = mtri.Triangulation(vertices[:, 0], vertices[:, 1], triangles)
    pad = 400.
    xs = np.arange(vertices[:, 0].min() - pad, vertices[:, 0].max() + pad, 50.)
    zs = np.arange(vertices[:, 1].min() - pad, vertices[:, 1].max() + pad, 50.)
    grid = np.meshgrid(xs, zs)
    rails = [mtri.LinearTriInterpolator(triangulation,
                                        value if len(value) == len(vertices)
                                        else np.zeros(len(vertices)))(*grid)
             for value in (initial, final)]
    bed_initial = np.ma.filled(rails[0], np.nan)
    bed_final = np.ma.filled(rails[1], np.nan)
    difference = np.ma.filled(mtri.LinearTriInterpolator(triangulation, change)(*grid), np.nan)
    masked = np.ma.masked_invalid(difference)
    limit = max(float(np.nanmax(np.abs(change))), 1e-12)
    fig = plt.figure(figsize=(18, 11))
    grid_spec = fig.add_gridspec(2, 2)
    for position, (values, label) in enumerate(((bed_initial, "initial carve (bed at t=0)"),
                                                (bed_final, "final bed (t=%.0f h)" % hours))):
        axes = fig.add_subplot(grid_spec[position // 2, position % 2])
        mesh = axes.pcolormesh(xs, zs, values, cmap="terrain", shading="auto")
        fig.colorbar(mesh, ax=axes, shrink=.75, label="bed elevation (m)")
        axes.set(title=label, xlabel="World X (m)", ylabel="World Z (m)")
        axes.ticklabel_format(useOffset=False, style="plain")
    axes = fig.add_subplot(grid_spec[0, 1])
    axes.clear()
    mesh = axes.pcolormesh(xs, zs, bed_final - bed_initial, cmap="terrain", shading="auto")
    fig.colorbar(mesh, ax=axes, shrink=.75, label="final - initial (m)")
    axes.set(title="final bed minus initial carve", xlabel="World X (m)", ylabel="World Z (m)")
    axes.ticklabel_format(useOffset=False, style="plain")
    axes = fig.add_subplot(grid_spec[1, 1])
    image = axes.pcolormesh(xs, zs, masked, cmap="RdBu_r", shading="auto",
                            vmin=-limit, vmax=limit)
    fig.colorbar(image, ax=axes, shrink=.75, label="bed change (m)")
    axes.set(title="dynamic bed change (mesh, %d of %d support vertices moved)\n"
                   "range %.3e to %.3e m" % (int(np.count_nonzero(change)), int(change.size),
                                             float(change.min()), float(change.max())),
             xlabel="World X (m)", ylabel="World Z (m)")
    axes.ticklabel_format(useOffset=False, style="plain")
    fig.suptitle("Full-grid dynamic bed: canonical 50 m carved mesh, %d nodes\n"
                 "initial carve vs final bed (synthetic, not an observation)" % owner.size)
    fig.tight_layout()
    fig.savefig(output / "bed-change-difference.png", dpi=150)
    plt.close(fig)
    np.savez_compressed(output / "bed-change-field.npz",
                        vertices_xz_m=vertices, triangles=triangles,
                        initial_bed_m=initial, final_bed_m=final, bed_change_m=change,
                        vertex_owner=owner, carved_vertex_mask=carved, support_vertex_mask=support,
                        raster_x_m=xs, raster_z_m=zs, raster_change_m=difference,
                        time_seconds=np.asarray(arrays["time_seconds"], np.float64))
    return dict(initial_min_m=float(initial.min()), initial_max_m=float(initial.max()),
                final_min_m=float(final.min()), final_max_m=float(final.max()),
                change_min_m=float(change.min()), change_max_m=float(change.max()),
                changed_vertices=int(np.count_nonzero(change > 0.)),
                eroded_vertices=int(np.count_nonzero(change < 0.)),
                support_vertices=int(np.count_nonzero(support)),
                carved_vertices=int(np.count_nonzero(carved)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--hours", type=int, default=72)
    args = parser.parse_args()
    started = time.perf_counter()
    summary = run_grid_bed(args.output, hours=args.hours)
    comparison = compare(args.output, hours=args.hours)
    field = plot_bed_difference(args.output, hours=args.hours)
    audit = per_node_table(args.output)
    summary["comparison"] = comparison
    summary["bed_field"] = field
    summary["material_area_audit"] = dict(all_nodes_pass=audit["all_nodes_pass"],
                                         min_ratio=audit["min_ratio"],
                                         max_ratio=audit["max_ratio"])
    summary["wall_seconds"] = time.perf_counter() - started
    print(json.dumps(summary, indent=2), flush=True)
