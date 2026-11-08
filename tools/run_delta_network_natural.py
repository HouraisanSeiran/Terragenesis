"""Opt-in naturalness refinement of an archived source-controlled delta.

Read fixed major geometry once, refine on native 30 m terrain once, then
rasterize the identical metre-coordinate graph at the requested spacings.
No legacy product or default world is changed.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import time

import networkx as nx
import numpy as np
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from terrain_pipeline import delta_network_morphology as morph
from terrain_pipeline import delta_network_site as site
from terrain_pipeline import delta_network_skeleton_v3 as skeleton
from terrain_pipeline.delta_network_frozen import load_graph, topology_identity
from terrain_pipeline.delta_network_path_refinement import refine_graph
from terrain_pipeline.delta_network_sections import rasterize_channels
import run_delta_network_v1 as common
import run_delta_network_v4 as renderer


BASE = ROOT / ".scratch/delta-completion-20261107/source-controlled-v5-100m-r3/base"


def _spec(manifest, spacing):
    original = site.SiteSpec(**manifest["site"])
    return replace(original, spacing_m=spacing,
                   nu=int(round(original.nu * original.spacing_m / spacing)),
                   nv=int(round(original.nv * original.spacing_m / spacing)))


def _plain(spec, manifest):
    bed, ocean, valid = site.sample_td(spec)
    if not valid.all():
        raise ValueError("naturalness experiment must stay within the immutable TD source")
    plain = morph.whole_plain(spec, bed, ocean, morph.PlainParameters(**manifest["params"]["plain"]))
    return bed, ocean, valid, plain


def _terrain(spec, graph, source, ocean, plain):
    sections = rasterize_channels(spec, plain["bed"], source, ocean, graph)
    water = (sections["bed"] < 0.0) | sections["chan"]
    dry = ~water
    labels, count = ndi.label(dry)
    edge_labels = np.unique(np.r_[labels[0], labels[-1], labels[:, 0], labels[:, -1]])
    mainland = np.isin(labels, edge_labels[edge_labels > 0])
    island_ids = np.unique(labels[(labels > 0) & ~mainland])
    remap = np.zeros(count + 1, np.int32)
    remap[island_ids] = np.arange(1, len(island_ids) + 1)
    masks = np.zeros_like(water)
    terrain = dict(
        grid=morph._Grid(spec), bed=sections["bed"], chan=sections["chan"], water=water,
        z_plain=plain["bed"], land_dry=dry, land_env=plain["bed"] >= 0.0,
        mainland=mainland, island_label=remap[labels], tidal=masks, sand=masks.copy(),
        spit=masks.copy(), whole_plain=plain, levee=sections["levee"],
    )
    return terrain, sections


def _plot(spec, source, terrain, output, previous=None):
    plt = common._setup_mpl()
    rgb = renderer.rgb_v4(terrain, spec.spacing_m)
    extent = common._extent_km(spec)
    fig, ax = plt.subplots(figsize=(11, 10))
    ax.imshow(rgb, origin="upper", extent=extent, interpolation="nearest")
    ax.set(xlim=(-16, 17), ylim=(22, -8), xlabel="local v / km", ylabel="local u / km",
           title=f"Frozen v5 network: naturalness phase 1, {spec.spacing_m:g} m, geological t=0")
    ax.plot([-14, -9], [20, 20], color="white", lw=3)
    ax.text(-11.5, 19.5, "5 km", color="white", ha="center")
    ax.text(0.015, 0.015, "Saved TD + actual constructed bed/wet cells; terrain colours, no vegetation inference",
            transform=ax.transAxes, fontsize=8, color="white", bbox=dict(facecolor="black", alpha=.6))
    fig.tight_layout()
    fig.savefig(output / "main.png", dpi=150)
    plt.close(fig)
    if previous is not None:
        old_bed = np.load(previous / "bed_dem_float64.npy")
        old_water = np.load(previous / "water_mask.npy").astype(bool)
        old_channel = np.load(previous / "channel_mask.npy").astype(bool)
        old = dict(bed=old_bed, water=old_water, chan=old_channel,
                   sand=np.zeros_like(old_water), z_plain=np.load(previous / "geological_surface_m.npy"))
        fig, axes = plt.subplots(1, 3, figsize=(20, 8))
        for ax, image_data, title in zip(axes[:2], (renderer.rgb_v4(old, spec.spacing_m), rgb),
                                         ("Archived v5", "Naturalness phase 1")):
            ax.imshow(image_data, origin="upper", extent=extent, interpolation="nearest")
            ax.set_title(title)
        difference = terrain["bed"] - old_bed
        im = axes[2].imshow(difference, origin="upper", extent=extent, cmap="RdBu_r", vmin=-5, vmax=5)
        axes[2].set_title("New bed - archived v5 (m; colours clipped to +/-5)")
        for ax in axes:
            ax.set(xlim=(-8, 6), ylim=(17, -5), xlabel="local v / km", ylabel="local u / km")
        fig.colorbar(im, ax=axes[2], fraction=.035)
        fig.tight_layout()
        fig.savefig(output / "same-site-comparison.png", dpi=145)
        plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    for ax in axes:
        ax.imshow(rgb, origin="upper", extent=extent, interpolation="nearest")
    axes[0].set(xlim=(-3, 3), ylim=(6, -3), title="Upper splits / bank clearance")
    axes[1].set(xlim=(-5.5, 2.5), ylim=(16.5, 7.5), title="Lower distributaries / confluences")
    for ax in axes:
        ax.set(xlabel="local v / km", ylabel="local u / km")
    fig.tight_layout()
    fig.savefig(output / "details.png", dpi=160)
    plt.close(fig)


def _save(directory, spec, graph, terrain, sections, source, ocean, valid, manifest, frozen, refinement):
    directory.mkdir(parents=True, exist_ok=False)
    arrays = dict(
        bed_dem_float64=terrain["bed"], water_mask=terrain["water"], channel_mask=terrain["chan"],
        td_original_bed_m=source, td_ocean_mask=ocean, valid_mask=valid,
        construction_reference_bed_m=source, geological_surface_m=terrain["z_plain"],
        geological_deposit_thickness_m=terrain["whole_plain"]["deposit"],
        plain_construction_mask=terrain["whole_plain"]["active"],
        landward_reconstruction_weight=terrain["whole_plain"]["landward_weight"],
        water_surface_m=sections["stage"], physical_channel_width_m=sections["width"],
        water_depth_m=np.where(terrain["chan"], sections["depth"], np.maximum(-terrain["bed"], 0.0)),
        subcell_coverage_mask=sections["raster_coverage_only"],
        tidal_mask=terrain["tidal"], sand_mask=terrain["sand"], spit_mask=terrain["spit"],
        island_labels=terrain["island_label"],
    )
    for name, array in arrays.items():
        np.save(directory / (name + ".npy"), array)
    graph_json = common.graph_dict(graph, spec)
    for edge, profile in zip(graph_json["edges"], sections["profiles"]):
        path = np.asarray(edge["path_uv_m"])
        distance = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
        edge["width_profile_m"] = np.interp(distance, profile["distance_m"], profile["actual_width_m"]).tolist()
        edge["width_profile_semantics"] = "terrain-constrained physical width; sampled by existing irregular hydraulic accounts"
    graph_json.update(construction_profiles=graph.construction_profiles,
                      flow_semantics="Saved design discharge, not solved physical event discharge",
                      source_semantics="Frozen catchment source; no invented upstream extension")
    common.write_json(directory / "channel_graph.json", graph_json)
    common.write_json(directory / "cross_section_profiles.json", sections["profiles"])
    topology = nx.MultiGraph()
    topology.add_nodes_from(range(len(graph.node_uv)))
    topology.add_edges_from(zip(graph.edge_from, graph.edge_to))
    metrics = dict(validation=skeleton.validate_graph(graph),
                   geometry_audit=morph.geometry_audit(spec, graph, terrain),
                   sections=sections["report"], path_refinement=refinement,
                   skeleton=dict(n_nodes=len(graph.node_uv), n_edges=len(graph.edge_from),
                                 n_mouths=len(graph.mouth_nodes), loops=len(graph.edge_from) - len(graph.node_uv) + nx.number_connected_components(topology)),
                   whole_plain=morph.whole_plain_metrics(spec, graph, terrain, ocean))
    common.write_json(directory / "metrics.json", metrics)
    ledger = dict(terrain["whole_plain"]["ledger"])
    ledger["channel_excavated_solid_m3"] = float(np.maximum(terrain["z_plain"] - terrain["bed"], 0.0).sum() * spec.spacing_m**2 * .6)
    ledger["channel_excavation_is_unresolved_construction_stock"] = True
    ledger["channel_raster_excavation_is_resolution_dependent"] = True
    common.write_json(directory / "geological_ledger.json", ledger)
    modules = [Path(morph.__file__), ROOT / "terrain_pipeline/delta_network_frozen.py",
               ROOT / "terrain_pipeline/delta_network_path_refinement.py", ROOT / "terrain_pipeline/delta_network_sections.py",
               ROOT / "terrain_pipeline/delta_network_skeleton.py", Path(skeleton.__file__),
               ROOT / "terrain_pipeline/delta_network_terrain.py", Path(site.__file__),
               ROOT / "terrain_pipeline/large_delta_landform_regional.py", Path(common.__file__),
               Path(renderer.__file__), ROOT / "tools/delta_reference_metrics.py", Path(__file__)]
    snapshot = directory / "algorithm-source"
    snapshot.mkdir()
    for path in modules:
        shutil.copyfile(path, snapshot / path.name)
    result_manifest = dict(
        product="source-controlled-delta-naturalness-phase1-v1", site=spec.to_dict(),
        world_seed=morph.WORLD_SEED, source_world_seed=manifest["source_world_seed"],
        derived_seeds=graph.seeds, params=manifest["params"], td_source=manifest["td_source"],
        frozen_major_geometry=dict(directory=str(frozen.resolve()),
                                   original_graph_sha256=common.sha256_file(frozen / "channel_graph.json"),
                                   refined_geometry_shared_at_all_spacings=True,
                                   refinement_reference_spacing_m=30.0),
        cross_section_parameters=dict(protected_elevation_m=45.0, freeboard_m=0.8,
                                      lowland_excavation_ceiling_m=12.0,
                                      physical_junction_min_transition_m=120.0),
        construction_reference=dict(file="construction_reference_bed_m.npy", semantics="Immutable sampled native TD; no replacement shelf"),
        geological_initial_condition=True, physical_elapsed_seconds=0.0,
        code_sha256={str(path.relative_to(ROOT)).replace(chr(92), "/"): common.sha256_file(path) for path in modules},
        known_limits=["Geological initialization, not calibrated long-term growth",
                      "Plain is independently sampled at each resolution; only major river geometry is frozen",
                      "Subcell water coverage is not a physical river width",
                      "Hydraulic controls sample the exported physical width profile; unresolved within-control pinches remain approximate",
                      "Natural levees, differential bay fill, tidal reversal and avulsion remain later phases"],
        metrics=metrics,
    )
    common.write_json(directory / "manifest.json", result_manifest)
    common.write_json(directory / "sha256sums.json", {
        str(path.relative_to(directory)).replace(chr(92), "/"): common.sha256_file(path)
        for path in sorted(directory.rglob("*")) if path.is_file() and path.name != "sha256sums.json"
    })
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=BASE)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--spacings", default="100,30")
    parser.add_argument("--no-refine", action="store_true")
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("use a fresh output directory")
    spacings = [float(value) for value in args.spacings.split(",")]
    if any(not np.isfinite(dx) or dx <= 0 for dx in spacings) or len(set(spacings)) != len(spacings):
        parser.error("distinct positive finite spacings required")
    started = time.perf_counter()
    manifest = json.loads((args.source / "manifest.json").read_text(encoding="utf-8"))
    for name in ("bed_m.npy", "ocean_mask.npy"):
        item = manifest["td_source"][name]
        if common.sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("native TD source identity differs from the archived product")
    graph = load_graph(args.source)
    identity = topology_identity(graph)
    reference_spec = _spec(manifest, 30.0)
    reference = _plain(reference_spec, manifest)
    if not args.no_refine:
        graph, refinement = refine_graph(graph, reference_spec, reference[3]["bed"], reference[0], reference[1])
    else:
        refinement = dict(enabled=False)
    if topology_identity(graph) != identity:
        raise RuntimeError("refinement changed frozen topology, endpoints or discharge")
    args.out.mkdir(parents=True, exist_ok=True)
    cases = []
    for spacing in spacings:
        spec = _spec(manifest, spacing)
        source, ocean, valid, plain = reference if spacing == 30.0 else _plain(spec, manifest)
        terrain, sections = _terrain(spec, graph, source, ocean, plain)
        output = args.out / f"{spacing:g}m"
        metrics = _save(output, spec, graph, terrain, sections, source, ocean, valid, manifest, args.source, refinement)
        _plot(spec, source, terrain, output, args.source if spacing == manifest["site"]["spacing_m"] else None)
        common.write_json(output / "figures.json", dict(
            td_source=manifest["td_source"], source_product=str(output.resolve()),
            source_dem_sha256=common.sha256_file(output / "bed_dem_float64.npy"),
            spacing_m=spacing, physical_elapsed_seconds=0.0,
            rendering="Saved constructed DEM hillshade and actual wet masks; terrain colours, no inferred vegetation",
            files={path.name: common.sha256_file(path) for path in sorted(output.glob("*.png"))},
        ))
        common.write_json(output / "sha256sums.json", {
            path.relative_to(output).as_posix(): common.sha256_file(path)
            for path in sorted(output.rglob("*")) if path.is_file() and path.name != "sha256sums.json"
        })
        accepted = (metrics["geometry_audit"]["ok"]
                    and sections["report"]["blocked_centreline_cell_count"] == 0
                    and sections["report"]["channel_components_4_connected"] == 1
                    and sections["report"]["protected_source_cells_cut"] == 0)
        cases.append(dict(spacing_m=spacing, directory=str(output.resolve()),
                          acceptance="phase1_geometry_pass" if accepted else "diagnostic_rejected",
                          geometry_audit_ok=metrics["geometry_audit"]["ok"],
                          blocked_centerline_cells=sections["report"]["blocked_centreline_cell_count"],
                          protected_cells_cut=sections["report"]["protected_source_cells_cut"]))
        print(json.dumps(cases[-1]), flush=True)
    common.write_json(args.out / "suite.json", dict(cases=cases, refinement=refinement,
                                                    elapsed_seconds=time.perf_counter() - started,
                                                    phase="river geometry and sections; overall naturalness goal remains active"))
    if not all(case["acceptance"] == "phase1_geometry_pass" for case in cases):
        raise RuntimeError("saved diagnostic case failed phase1 geometry acceptance")


if __name__ == "__main__":
    main()
