"""CPU-only source-controlled bay/plain construction on frozen TD terrain."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from terrain_pipeline import delta_network_site as site
from terrain_pipeline import delta_network_morphology as morph
from terrain_pipeline import delta_network_skeleton_v3 as sk
import run_delta_network_v1 as r1
import run_delta_network_v4 as r4

DEFAULT_OUT = ROOT / ".scratch/delta-completion-20261107/source-controlled-v5-100m-r2"
DEFAULT_FIGS = ROOT / "验收图片/地形约束三角洲v5-20261108-100m"


def source_site(spacing=100.0):
    """Changed site within the same immutable TD, not the historical v4 site."""
    if not np.isfinite(spacing) or spacing <= 0.0:
        raise ValueError("positive finite spacing required")
    return site.SiteSpec(
        anchor_world_m=(28000.0, -24000.0),
        alpha_deg=0.0,
        u0_m=-10000.0,
        v0_m=-30000.0,
        nu=int(43000.0 / spacing),
        nv=int(60000.0 / spacing),
        spacing_m=spacing,
    )


def _show_map(ax, T, spec, title, coast=None, graph=None):
    ax.imshow(
        r4.rgb_v4(T, spec.spacing_m), extent=r1._extent_km(spec), origin="upper", interpolation="nearest"
    )
    if coast is not None:
        u, v = site.grid_centres(spec)
        ax.contour(
            v / 1000.0, u / 1000.0, coast.astype(float), levels=[0.5], colors=["#ee75a3"], linewidths=0.65
        )
    if graph is not None:
        for eid in range(len(graph.edge_from)):
            points = sk.edge_points(graph, eid)
            ax.plot(points[:, 1] / 1000.0, points[:, 0] / 1000.0, color="white", lw=0.5, alpha=0.85)
    ax.set_title(title)
    ax.set_xlabel("local v / km (right = north)")
    ax.set_ylabel("local u / km (down = east / seaward)")
    ax.set_xlim(-16.0, 17.0)
    ax.set_ylim(22.0, -8.0)
    ax.plot([-14.0, -9.0], [20.0, 20.0], color="white", lw=3)
    ax.text(-11.5, 19.5, "5 km", ha="center", color="white", fontsize=10)


def figures(name, spec, tdb, tdo, g, T, figs):
    plt = r1._setup_mpl()
    raw = dict(bed=tdb, water=tdo, chan=np.zeros_like(tdo), sand=np.zeros_like(tdo), z_plain=tdb)
    fig, ax = plt.subplots(figsize=(10, 9))
    _show_map(
        ax,
        T,
        spec,
        f"v5 {name}: source-controlled plain, {spec.spacing_m:g} m terrain colours, geological t=0",
        tdo,
    )
    ax.text(
        0.02,
        0.02,
        "Pink: original TD coast. Actual wet raster; no vegetation/material classification.",
        transform=ax.transAxes,
        fontsize=8,
        color="white",
        bbox=dict(facecolor="black", alpha=0.5),
    )
    fig.tight_layout()
    fig.savefig(figs / (name + "-main.png"), dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 3, figsize=(21, 8))
    _show_map(axes[0], raw, spec, "Original frozen TD: same coordinates")
    _show_map(axes[1], T, spec, "Constructed bed + wet raster; white = complete DAG", tdo, g)
    im = axes[2].imshow(
        T["bed"] - tdb, extent=r1._extent_km(spec), origin="upper", cmap="RdBu_r", vmin=-50.0, vmax=50.0
    )
    axes[2].set_xlim(-16.0, 17.0)
    axes[2].set_ylim(22.0, -8.0)
    axes[2].set_title("Constructed bed minus original TD (m; colour range clipped)")
    axes[2].set_xlabel("local v / km")
    axes[2].set_ylabel("local u / km")
    fig.colorbar(im, ax=axes[2], fraction=0.035)
    fig.tight_layout()
    fig.savefig(figs / (name + "-source-and-change.png"), dpi=140)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 9))
    im = ax.imshow(
        T["bed"], extent=r1._extent_km(spec), origin="upper", cmap="terrain", vmin=-10.0, vmax=20.0
    )
    ax.set_xlim(-16.0, 17.0)
    ax.set_ylim(22.0, -8.0)
    ax.set_title(f"v5 {name}: saved actual bed elevation, m (range clipped)")
    ax.set_xlabel("local v / km")
    ax.set_ylabel("local u / km")
    fig.colorbar(im, ax=ax, fraction=0.04)
    fig.tight_layout()
    fig.savefig(figs / (name + "-dem.png"), dpi=140)
    plt.close(fig)


def run(name, spec, tdb, tdo, inside, out, figs, make_figs=True):
    started = time.perf_counter()
    od = out / name
    if od.exists() and any(od.iterdir()):
        raise FileExistsError("refusing to overwrite morphology evidence: " + str(od))
    g, T, tp = morph.build(spec, tdb, tdo, name)
    validation = sk.validate_graph(g)
    audit = morph.geometry_audit(spec, g, T, tp)
    if not validation["ok"] or not audit["ok"]:
        raise RuntimeError("network or geometry audit failed")
    plain = T["whole_plain"]
    metrics = dict(
        validation=validation,
        geometry_audit=audit,
        skeleton=sk.skeleton_metrics_v3(g),
        whole_plain=morph.whole_plain_metrics(spec, g, T, tdo),
        nan_in_bed=int(np.isnan(T["bed"]).sum()),
    )
    od.mkdir(parents=True, exist_ok=True)
    stage = np.where(T["chan"], np.maximum(0.0, T["z_plain"] - tp.freeboard_m), 0.0)
    arrays = dict(
        bed_dem_float64=T["bed"],
        water_mask=T["water"],
        channel_mask=T["chan"],
        tidal_mask=T["tidal"],
        sand_mask=T["sand"],
        island_labels=T["island_label"],
        spit_mask=T["spit"],
        valid_mask=inside,
        water_surface_m=stage,
        water_depth_m=np.where(T["water"], np.maximum(stage - T["bed"], 0.0), 0.0),
        td_original_bed_m=tdb,
        td_ocean_mask=tdo,
        construction_reference_bed_m=tdb,
        geological_surface_m=T["z_plain"],
        plain_construction_mask=plain["active"],
        geological_deposit_thickness_m=plain["deposit"],
        landward_reconstruction_weight=plain["landward_weight"],
    )
    for fn, array in arrays.items():
        np.save(od / (fn + ".npy"), array)
    graph = r1.graph_dict(g, spec)
    graph.update(
        flow_semantics="Q_m3s is design discharge, not solved physical discharge",
        construction_profiles=g.construction_profiles,
        source_semantics="Explicit catchment inflow at the saved source node; no invented upstream window-edge extension",
    )
    r1.write_json(od / "channel_graph.json", graph)
    r1.write_json(od / "metrics.json", metrics)
    r1.write_json(od / "geological_ledger.json", T["geological_ledger"])
    code_paths = [
        Path(morph.__file__),
        Path(sk.__file__),
        ROOT / "terrain_pipeline/delta_network_skeleton.py",
        ROOT / "terrain_pipeline/delta_network_terrain.py",
        ROOT / "terrain_pipeline/large_delta_landform_regional.py",
        Path(__file__),
    ]
    manifest = dict(
        product="source-controlled-complex-delta-v5",
        world_seed=morph.WORLD_SEED,
        source_world_seed=site.WORLD_SEED,
        site=spec.to_dict(),
        td_source=r1.td_cache_identity(),
        site_identity="northeast source bay; explicitly changed from historical v4 steep-coast site",
        params=dict(delta=g.params.to_dict(), terrain=tp.to_dict(), plain=asdict(morph.PlainParameters())),
        derived_seeds=g.seeds,
        coordinate_note="arrays[row_u,col_v]; model X=v Z=u; cell centres u0+(i+.5)*dx; saved affine gives world XZ",
        geological_initial_condition=True,
        physical_elapsed_seconds=0.0,
        event_input_solid_m3=0.0,
        construction_reference=dict(
            file="construction_reference_bed_m.npy",
            semantics="Original saved TD topography and bathymetry before geological construction; no replacement shelf",
        ),
        declaration="Finite-stock geological bay fill and source-lowland reconstruction; channel excavation parked separately. No physical event elapsed.",
        known_limits=[
            "Tidal exchange and creeks are not yet simulated",
            "Terrain colours are not vegetation or material observations",
            "Geological deposition is an initialization, not a calibrated sediment history",
            "Historical v4 uses a different site and algorithm seed",
        ],
        code_sha256={
            str(path.relative_to(ROOT)).replace(chr(92), "/"): r1.sha256_file(path) for path in code_paths
        },
        metrics=metrics,
    )
    r1.write_json(od / "manifest.json", manifest)
    if make_figs:
        figs.mkdir(parents=True, exist_ok=True)
        figures(name, spec, tdb, tdo, g, T, figs)
    resources = dict(
        elapsed_seconds=time.perf_counter() - started,
        output_bytes=sum(p.stat().st_size for p in od.iterdir()),
        grid_shape=list(T["bed"].shape),
        spacing_m=spec.spacing_m,
        native_td_spacing_m=site.TD_SPACING_M,
    )
    r1.write_json(od / "resources.json", resources)
    r1.write_json(
        od / "sha256sums.json",
        {path.name: r1.sha256_file(path) for path in sorted(od.iterdir()) if path.name != "sha256sums.json"},
    )
    print(
        json.dumps(
            dict(
                variant=name,
                output=str(od),
                validation=validation,
                audit=audit,
                skeleton=metrics["skeleton"],
                whole_plain=metrics["whole_plain"],
                resources=resources,
            )
        ),
        flush=True,
    )
    return dict(variant=name, source=str(od.resolve()), metrics=metrics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variants", default="base,few_loops,many_loops")
    parser.add_argument("--spacing", type=float, default=100.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--figs", type=Path, default=DEFAULT_FIGS)
    parser.add_argument("--no-figs", action="store_true")
    args = parser.parse_args()
    variants = args.variants.split(",")
    if any(name not in morph.VARIANTS for name in variants) or len(set(variants)) != len(variants):
        parser.error("variants must be unique known morphology scenarios")
    for name in variants:
        if (args.out / name).exists() and any((args.out / name).iterdir()):
            parser.error("output variant directories must be new or empty")
    spec = source_site(args.spacing)
    tdb, tdo, inside = site.sample_td(spec)
    if not inside.all():
        parser.error("selected support is not entirely covered by the immutable TD")
    cases = [run(name, spec, tdb, tdo, inside, args.out, args.figs, not args.no_figs) for name in variants]
    r1.write_json(
        args.out / "suite.json", dict(cases=cases, site=spec.to_dict(), world_seed=morph.WORLD_SEED)
    )
    if not args.no_figs:
        r1.write_json(
            args.figs / "manifest.json",
            dict(
                terrain_basis=r1.td_cache_identity(),
                coverage_status="complete_in_window",
                algorithms=[
                    "source-controlled finite-stock plain",
                    "source-steered v3 DAG",
                    "v4 channel cross-section stamp",
                ],
                physical_elapsed_seconds=0.0,
                source_cases=[item["source"] for item in cases],
                spacing_m=spec.spacing_m,
                display_crop_local_km=dict(u=[-8.0, 22.0], v=[-16.0, 17.0]),
                rendering="Saved bed hillshade and terrain colours; actual wet masks; no inferred vegetation; original coast overlay",
                files={path.name: r1.sha256_file(path) for path in sorted(args.figs.glob("*.png"))},
            ),
        )


if __name__ == "__main__":
    main()
