"""Read pinned canonical TD cores, route their real terrain, and render a standalone preview."""
import argparse
import html
import json
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.common_infra import checked_archive, file_sha256, identity


def load_core_mosaic(folder, seed, first_tile_xz, tile_count=5):
    folder = Path(folder)
    height = np.empty((256 * tile_count, 256 * tile_count), np.float64)
    records, generation = [], None
    tx0, tz0 = first_tile_xz
    for dz in range(tile_count):
        for dx in range(tile_count):
            tx, tz = tx0 + dx, tz0 + dz
            path = folder / f"tile-x{tx}-z{tz}.npz"
            digest = path.with_suffix(".sha256").read_text(encoding="ascii").strip()
            a = checked_archive(path, expected_sha256=digest)
            m = json.loads(str(a["metadata_json"].item()))
            if (m.get("artifact_kind") != "terrain_diffusion_output" or int(m["seed"]) != seed
                    or m["native_origin"] != [tx * 256, tz * 256] or m["shape"] != [257, 257]
                    or m["native_resolution_m"] != 30. or a["elevation_m"].shape != (257, 257)
                    or not np.isfinite(a["elevation_m"]).all()):
                raise ValueError("pinned real TD tile seed/grid/source mismatch")
            generation = m["identity"] if generation is None else generation
            if m["identity"] != generation:
                raise ValueError("tiles have different generation identities")
            height[dz * 256:(dz + 1) * 256, dx * 256:(dx + 1) * 256] = a["elevation_m"][:256, :256]
            records.append({"path": str(path.resolve()), "sha256": digest, "tile_xz": [tx, tz]})
    origin = [tx0 * 256 * 30., tz0 * 256 * 30.]
    metadata = {"seed": seed, "generation_identity": generation, "tile_sources": records,
        "origin_xz_m": origin, "spacing_m": 30., "shape": list(height.shape),
        "node_span_m_xz": [(height.shape[1] - 1) * 30., (height.shape[0] - 1) * 30.],
        "cell_footprint_m_xz": [height.shape[1] * 30., height.shape[0] * 30.],
        "grid_semantics": "unaltered canonical NW256 native node values assigned to 30m cell centres",
        "model_inference_run": False, "hydrologic_tile_seams_certified": False}
    metadata["source_identity"] = identity({"elevation_m": height}, metadata)
    return height, metadata


def frozen_domain_diagnostics(plan, shape, origin, spacing, receiver, outlet_kind, selected):
    x = origin[0] + np.arange(shape[1]) * spacing
    z = origin[1] + np.arange(shape[0]) * spacing
    cx = np.rint((x - plan["origin_xz_m"][0]) / plan["spacing_m"]).astype(int)
    cz = np.rint((z - plan["origin_xz_m"][1]) / plan["spacing_m"]).astype(int)
    if cx.min() < 0 or cz.min() < 0 or cx.max() >= plan["height_m"].shape[1] or cz.max() >= plan["height_m"].shape[0]:
        raise ValueError("TD source extends beyond frozen planning support")
    owner = plan["owner_domain_id"][np.ix_(cz, cx)]
    coarse_ids = cz[:, None] * plan["height_m"].shape[1] + cx[None, :]
    terminals = {int(cell) for domain in plan["domains"] for cell in domain["terminal_indices"]}
    rec = np.asarray(receiver).ravel()
    source = np.flatnonzero(rec >= 0)
    target = rec[source]
    conflicts = (owner.ravel()[source] >= 0) & (owner.ravel()[target] != owner.ravel()[source]) & (owner.ravel()[target] != -1)
    selected_conflicts = np.isin(source[conflicts], selected)
    source_coarse = coarse_ids.ravel()[source]
    target_coarse = coarse_ids.ravel()[target]
    coarse_receiver = plan.get("receiver")
    coarse_disagreements = np.zeros(source.size, bool)
    if coarse_receiver is not None:
        expected = np.asarray(coarse_receiver).ravel()[source_coarse]
        coarse_disagreements = (source_coarse != target_coarse) & (expected >= 0) & (target_coarse != expected)
    terminal_ids = np.flatnonzero(rec < 0)
    kinds = np.asarray(outlet_kind).ravel()[terminal_ids]
    legal = np.isin(coarse_ids.ravel()[terminal_ids], list(terminals))
    unresolved = kinds == "unknown_boundary"
    report = {"status": "native_td_routing_candidate", "owner_sampling": "same nearest coarse node convention as derive_detail",
        "all_native_owner_crossing_conflicts": int(conflicts.sum()),
        "selected_owner_crossing_conflicts": int(selected_conflicts.sum()),
        "native_cross_coarse_step_receiver_disagreements": int(coarse_disagreements.sum()),
        "coarse_direction_check_scope": "native steps crossing nearest coarse cells compared with frozen receiver; internal-cell turns unconstrained",
        "selected_unknown_owner_edge_count": int(np.sum(owner.ravel()[np.asarray(selected)] < -1)),
        "terminal_count": len(terminal_ids), "unclosed_boundary_terminal_count": int(unresolved.sum()),
        "internal_raw_sink_count": int(np.sum(~unresolved)),
        "internal_sink_in_registered_terminal_region_count": int(np.sum(legal & ~unresolved)),
        "internal_sink_outside_registered_terminal_region_count": int(np.sum(~legal & ~unresolved)),
        "terminal_region_semantics": "coarse frozen terminal cell overlap; does not certify exact legal port or lake footprint",
        "actual_bed_verified": False, "frozen_domain_routing_certified": False}
    return owner, source[conflicts], terminal_ids[unresolved], report


def prepare_network(height, metadata, plan, *, bounded_spill=False):
    from terrain_pipeline.common_infra import TerrainGrid, BoundaryGrid
    from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
    from terrain_pipeline.channel_geometry import build_network_geometry_plan
    terrain = TerrainGrid(height, np.ones(height.shape, bool), *metadata["origin_xz_m"], 30., 30.,
        "generated_terrain", metadata["source_identity"], metadata["source_identity"], generation_seed=metadata["seed"])
    kind = np.full(height.shape, "interior", dtype="U24")
    kind[[0, -1], :] = "unknown_boundary"
    kind[:, [0, -1]] = "unknown_boundary"
    boundary = BoundaryGrid(kind, np.zeros(height.shape, bool), "unclosed-TD-perimeter", identity({}, {"perimeter": "unknown"}))
    spill_metadata = None
    work = height
    if bounded_spill:
        from terrain_pipeline.surface_rivers.metric_td_generated_rivers import spill_candidate
        graph, work, spill_metadata = spill_candidate(terrain, boundary, max_depth=4.)
    else:
        graph = route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")
    network = build_network_geometry_plan(terrain, graph)
    a = network["arrays"]
    owner, conflicts, unclosed, diagnostics = frozen_domain_diagnostics(plan, height.shape, metadata["origin_xz_m"], 30.,
        graph.receiver, graph.outlet_kind, a["selected_edge_source_ids"])
    arrays = {"original_td_m": height, "receiver": graph.receiver, "outlet_kind": graph.outlet_kind,
        "contributing_area_m2": a["contributing_area_m2"], "selected_edge_source_ids": a["selected_edge_source_ids"],
        "selected_edge_target_ids": a["selected_edge_target_ids"], "frozen_owner_domain_id": owner,
        "owner_conflict_source_ids": conflicts, "unclosed_terminal_ids": unclosed}
    if bounded_spill:
        arrays["working_height_m"] = work
        arrays["working_raise_m"] = work - height
        source = np.flatnonzero(graph.receiver >= 0)
        raw_uphill = height.ravel()[graph.receiver[source]] - height.ravel()[source]
        selected = a["selected_edge_source_ids"]
        spill_metadata.update(raised_cell_count=int(np.sum(work > height + 1e-8)),
            raised_area_m2=float(np.sum(work > height + 1e-8) * 900.),
            raw_uphill_native_edge_count=int(np.sum(raw_uphill > 1e-8)),
            maximum_raw_uphill_edge_m=float(raw_uphill.max(initial=0)),
            selected_source_raise_quantiles_m=np.quantile((work-height).ravel()[selected], [.5, .95, 1]).tolist() if selected.size else [],
            selected_raw_uphill_edge_count=int(np.sum(height.ravel()[graph.receiver[selected]] - height.ravel()[selected] > 1e-8)),
            budget_semantics="4m shallow-depression fill limit on a separate routing work surface; not a certified local bed-cut budget")
    return arrays, {**metadata, "routing_identity": graph.identity_sha256, "network_identity": network["identity_sha256"],
        "selection_minimum_contributing_area_m2": network["metadata"]["config"]["min_contributing_area_m2"],
        "selected_edge_count": len(a["selected_edge_source_ids"]), "domain_diagnostics": diagnostics,
        "bed_solver_run": False, "naturalness_certified": False, "bounded_spill": spill_metadata}


def render_maps(arrays, metadata, output, *, elevation_limits=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    from matplotlib.collections import LineCollection
    from tools.compare_hydrology_projection_naturalness import fixed_hillshade
    h = arrays["original_td_m"]
    ox, oz = metadata["origin_xz_m"]
    spacing = metadata["spacing_m"]
    extent = [ox - spacing / 2, ox + (h.shape[1] - .5) * spacing,
              oz + (h.shape[0] - .5) * spacing, oz - spacing / 2]
    work = arrays.get("working_height_m")
    low, high = elevation_limits or (float(h.min()), max(float(h.max()), float(work.max()) if work is not None else float(h.max())))
    cmap = LinearSegmentedColormap.from_list("blue-cyan-green-yellow-orange-red",
        ["#123a9b", "#00a8d5", "#27bb72", "#f3e85b", "#ef9a33", "#cb2d32"])
    rgb = cmap(Normalize(low, high)(h))[..., :3]
    rgb = np.clip(rgb * (.55 + .65 * fixed_hillshade(h, spacing)[..., None]), 0., 1.)
    ids = arrays["selected_edge_source_ids"]
    targets = arrays["selected_edge_target_ids"]
    def coords(values):
        return np.c_[ox + values % h.shape[1] * spacing, oz + values // h.shape[1] * spacing] / 1000.
    lines = np.stack((coords(ids), coords(targets)), axis=1)
    maps = []
    cases = [("full-region", None, h), ("central-zoom", (.25, .75), h)]
    if work is not None:
        cases += [("full-work-surface", None, work), ("central-work-surface", (.25, .75), work)]
    for name, zoom, surface in cases:
        rgb = np.clip(cmap(Normalize(low, high)(surface))[..., :3] * (.55 + .65 * fixed_hillshade(surface, spacing)[..., None]), 0., 1.)
        fig, ax = plt.subplots(figsize=(12, 11), constrained_layout=True)
        ax.imshow(rgb, extent=np.array(extent) / 1000., interpolation="nearest")
        ax.add_collection(LineCollection(lines, colors="#e9f6ff", linewidths=1.4, alpha=.8))
        ax.add_collection(LineCollection(lines, colors="#083f76", linewidths=.7, alpha=.9))
        bad = np.isin(ids, arrays["owner_conflict_source_ids"])
        if bad.any():
            ax.add_collection(LineCollection(lines[bad], colors="#e60077", linewidths=1.4))
        unclosed = coords(arrays["unclosed_terminal_ids"])
        ax.scatter(unclosed[:, 0], unclosed[:, 1], s=4, c="#ffffff", marker="x", linewidths=.4)
        if zoom:
            x0, x1 = extent[0], extent[1]
            z1, z0 = extent[2], extent[3]
            ax.set_xlim((x0 + zoom[0] * (x1-x0)) / 1000., (x0 + zoom[1] * (x1-x0)) / 1000.)
            ax.set_ylim((z0 + zoom[1] * (z1-z0)) / 1000., (z0 + zoom[0] * (z1-z0)) / 1000.)
        policy = "4m spill work-surface route candidate" if work is not None else "native TD routing candidate"
        ax.set(title=f"Seed {metadata['seed']} / {policy} / {name}", xlabel="World x east (km)", ylabel="World z south (km)", aspect="equal")
        scalar = plt.cm.ScalarMappable(norm=Normalize(low, high), cmap=cmap)
        fig.colorbar(scalar, ax=ax, label="Elevation (m), fixed source/work scale", shrink=.8)
        ax.plot([], [], color="#083f76", label="Work-surface route; bed unverified" if work is not None else "Native terrain route; bed unverified")
        ax.plot([], [], color="#e60077", label="Frozen owner conflict")
        ax.plot([], [], "x", color="#555555", label="Unclosed boundary terminal")
        ax.plot([], [], color="#123a9b", linewidth=5, label="Blue = low elevation, not water")
        ax.legend(loc="lower left", fontsize=8)
        path = output / (name + ".png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        maps.append(path.name)
    return maps, [low, high]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-folder", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--first-tile", type=int, nargs=2, default=(46, -188))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--saved-network", type=Path)
    parser.add_argument("--spill-from", type=Path)
    args = parser.parse_args()
    from tools.prepare_hydrology_v5_lake import limit_resources
    limit_resources()
    started = time.perf_counter()
    from terrain_pipeline.hydrology_planning import load_plan
    if args.spill_from:
        with np.load(args.spill_from, allow_pickle=False) as archive:
            source_metadata = json.loads(str(archive["metadata_json"].item()))
            h = archive["original_td_m"].copy()
        plan = load_plan(args.plan)
        if source_metadata["seed"] != int(plan["seed"]) or source_metadata["frozen_plan"]["sha256"] != file_sha256(args.plan):
            raise ValueError("spill source/frozen plan differs")
        arrays, metadata = prepare_network(h, source_metadata, plan, bounded_spill=True)
        metadata["routing_parent"] = {"path": str(args.spill_from.resolve()), "sha256": file_sha256(args.spill_from)}
        args.output.mkdir(parents=True, exist_ok=False)
        path = args.output / "native-routing.npz"
        with path.open("xb") as stream:
            np.savez_compressed(stream, **arrays, metadata_json=np.array(json.dumps(metadata)))
    elif args.saved_network:
        path = args.saved_network
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata_json"].item()))
            arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
        h = arrays["original_td_m"]
    else:
        h, metadata = load_core_mosaic(args.cache_folder, args.seed, args.first_tile)
        plan = load_plan(args.plan)
        if int(plan["seed"]) != args.seed:
            raise ValueError("frozen plan seed differs from TD")
        arrays, metadata = prepare_network(h, metadata, plan)
        metadata["frozen_plan"] = {"path": str(args.plan.resolve()), "sha256": file_sha256(args.plan), "identity": plan["identity_sha256"]}
        args.output.mkdir(parents=True, exist_ok=False)
        path = args.output / "native-routing.npz"
        with path.open("xb") as stream:
            np.savez_compressed(stream, **arrays, metadata_json=np.array(json.dumps(metadata)))
    maps, limits = render_maps(arrays, metadata, args.output)
    import ctypes
    from ctypes import wintypes
    class MemoryCounters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in
            ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
             "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    memory = MemoryCounters()
    memory.cb = ctypes.sizeof(memory)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    process = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
    if not ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(memory), memory.cb):
        raise OSError("Windows process memory query failed")
    metadata.update(network_archive={"path": str(path.resolve()), "sha256": file_sha256(path)}, figures=maps, elevation_limits_m=limits,
                    resources={"source_route": metadata.get("resources", {}).get("source_route", {
                        "wall_seconds": None, "peak_working_set_bytes": None,
                        "measurement_status": "not_recorded_during_original_route_run"}),
                        "render": {"wall_seconds": time.perf_counter() - started,
                            "peak_working_set_bytes": memory.PeakWorkingSetSize, "loaded_saved_network": bool(args.saved_network)},
                        "static_grid_limit_cells": 1280**2, "max_cpu_cores": 2, "numeric_threads": 1, "priority": "BelowNormal"})
    (args.output / "preview.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    description = f"种子 {args.seed} · 真实 TD 地形，{h.shape[1]} × {h.shape[0]} 个原生采样点，间距 30 米。采样点跨度 {metadata['node_span_m_xz'][0]/1000:.2f} 公里，单元覆盖范围 {metadata['cell_footprint_m_xz'][0]/1000:.2f} 公里。"
    content = "<!doctype html><meta charset='utf-8'><title>山川形意 · 河网预览</title><style>body{font:16px system-ui;margin:24px;color:#202830;background:#f5f7fa}img{max-width:100%;height:auto}main{max-width:1400px;margin:auto}table{border-collapse:collapse}td,th{padding:8px 20px;text-align:left;border-bottom:1px solid #ccd3db}</style><main><h1>山川形意 · 河网预览</h1><p>" + html.escape(description) + "</p><p>蓝色表示低高程，并非海洋或水体。河线是原始地形上的流向候选，尚未生成实际河床；粉色为冻结域归属冲突，白色叉号为未闭合边界端口。</p>"
    content += "".join(f"<figure><img src='{html.escape(name)}' alt='{html.escape(name)}'></figure>" for name in maps)
    diagnostics = metadata["domain_diagnostics"]
    rows = [("预览状态", "原生流向候选，河床未验收"), ("河线数量", metadata["selected_edge_count"]),
        ("选中河路的跨域冲突", diagnostics["selected_owner_crossing_conflicts"]),
        ("未闭合边界终点", diagnostics["unclosed_boundary_terminal_count"]),
        ("地形内部洼地终点", diagnostics["internal_raw_sink_count"])]
    content += "<h2>当前检查范围</h2><table>" + "".join("<tr><th>" + html.escape(label) + "</th><td>" + html.escape(str(value)) + "</td></tr>" for label, value in rows) + "</table><p><a href='preview.json'>详细来源与检查记录</a></p></main>"
    (args.output / "preview.html").write_text(content, encoding="utf-8")
    print(json.dumps({"preview": str(args.output / "preview.html"), "routing": metadata["domain_diagnostics"]}), flush=True)


def render_local_candidate(report_path, output):
    """Render a separately located repair without inserting its pixels in the large map."""
    from tools.compare_hydrology_projection_naturalness import load_projection, check_same_inputs, fixed_hillshade, pin
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    report_path, output = Path(report_path), Path(output)
    record = json.loads(report_path.read_text(encoding="utf-8"))["records"][0]
    baseline, bm, bp = load_projection(record["baseline_projection_path"], record["baseline_projection_sha256"])
    candidate, cm, cp = load_projection(record["projection_path"], record["projection_sha256"])
    check_same_inputs(baseline, candidate, bm, cm, target_policy=record.get("target_policy"))
    audit_path = Path(record["cold_audit_path"])
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit.get("projection_sha256") != cp["sha256"] or audit.get("status") != "cold_verified_finite_local_projection":
        raise ValueError("repair projection lacks matching accepted cold audit")
    fields = [baseline["original_td_m"][1:-1, 1:-1], baseline["projection_height_m"][1:-1, 1:-1], candidate["projection_height_m"][1:-1, 1:-1]]
    low, high = min(float(h.min()) for h in fields), max(float(h.max()) for h in fields)
    cmap = LinearSegmentedColormap.from_list("high-contrast-terrain", ["#123a9b", "#00a8d5", "#27bb72", "#f3e85b", "#ef9a33", "#cb2d32"])
    norm = Normalize(low, high)
    origin = np.asarray(cm["support_origin_xz_m"]) + 30.
    extent = np.array([origin[0], origin[0] + 2880., origin[1] + 2880., origin[1]]) / 1000.
    output.mkdir(parents=True, exist_ok=False)
    fig, axes = plt.subplots(1, 3, figsize=(15, 6), constrained_layout=True)
    for ax, h, label in zip(axes, fields, ("Original TD", "Frozen baseline", "Repair candidate")):
        rgb = np.clip(cmap(norm(h))[..., :3] * (.55 + .65 * fixed_hillshade(h)[..., None]), 0., 1.)
        ax.imshow(rgb, extent=extent, interpolation="nearest")
        ax.set(title=label, xlabel="World x east (km)", ylabel="World z south (km)")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=list(axes), label="Elevation (m)", shrink=.8)
    fig.suptitle(f"Seed{record['seed']} {record['kind']} / separate 2.88km node span / macro projection cold verified; fine bed unverified")
    path = output / "repair-comparison.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    result = {"candidate_report": pin(report_path), "baseline": bp, "candidate": cp, "cold_audit": pin(audit_path),
        "figure": pin(path), "seed": record["seed"], "node_span_m_xz": [2880., 2880.], "origin_xz_m": origin.tolist(),
        "elevation_limits_m": [low, high], "inserted_in_large_map": False, "bed_certified": False, "naturalness_certified": False}
    (output / "repair-preview.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def render_candidate_pair(before_report, after_report, output):
    """Same-source, same-target relief and curvature for two saved local candidates."""
    from tools.compare_hydrology_projection_naturalness import load_projection, check_same_inputs, fixed_hillshade, pin
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, Normalize
    reports = [json.loads(Path(path).read_text(encoding="utf-8"))["records"][0] for path in (before_report, after_report)]
    loaded = []
    for record in reports:
        arrays, meta, archive_pin = load_projection(record["projection_path"], record["projection_sha256"])
        audit = json.loads(Path(record["cold_audit_path"]).read_text(encoding="utf-8"))
        if audit.get("projection_sha256") != archive_pin["sha256"] or audit.get("status") != "cold_verified_finite_local_projection":
            raise ValueError("comparison candidate cold audit differs")
        loaded.append((arrays, meta, archive_pin))
    a, am, ap = loaded[0]
    b, bm, bp = loaded[1]
    check_same_inputs(a, b, am, bm)
    fields = [field[1:-1, 1:-1] for field in (a["original_td_m"], a["target_height_m"], a["projection_height_m"], b["projection_height_m"])]
    labels = ["Original TD", "Same harmonic target", am["algorithm"].rsplit("-", 1)[-1], bm["algorithm"].rsplit("-", 1)[-1]]
    low, high = min(float(field.min()) for field in fields), max(float(field.max()) for field in fields)
    cmap = LinearSegmentedColormap.from_list("high-contrast-terrain", ["#123a9b", "#00a8d5", "#27bb72", "#f3e85b", "#ef9a33", "#cb2d32"])
    norm = Normalize(low, high)
    curves = [field[1:-1, :-2] + field[1:-1, 2:] + field[:-2, 1:-1] + field[2:, 1:-1] - 4 * field[1:-1, 1:-1] for field in fields]
    curve_bound = max(float(np.abs(curve).max()) for curve in curves)
    origin = np.asarray(am["support_origin_xz_m"]) + 30.
    extent = np.array([origin[0], origin[0] + 2880., origin[1] + 2880., origin[1]]) / 1000.
    curve_extent = np.array([origin[0] + 30., origin[0] + 2850., origin[1] + 2850., origin[1] + 30.]) / 1000.
    fig, axes = plt.subplots(2, 4, figsize=(18, 10), constrained_layout=True)
    for ax, field, label in zip(axes[0], fields, labels):
        rgb = np.clip(cmap(norm(field))[..., :3] * (.55 + .65 * fixed_hillshade(field)[..., None]), 0., 1.)
        ax.imshow(rgb, extent=extent, interpolation="nearest")
        ax.set_title(label + " / fixed relief")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), ax=list(axes[0]), label="Elevation (m)", shrink=.8)
    for ax, curve, label in zip(axes[1], curves, labels):
        im = ax.imshow(curve, extent=curve_extent, cmap="RdBu_r", vmin=-curve_bound, vmax=curve_bound, interpolation="nearest")
        ax.set_title(label + " / four-neighbor curvature")
    fig.colorbar(im, ax=list(axes[1]), label="Four-neighbor Laplacian (m) / 30m grid", shrink=.8)
    for ax in axes.ravel():
        ax.set(xlabel="World x east (km)", ylabel="World z south (km)")
    fig.suptitle("Seed29 river / local repair comparison / same source, target, bounds and color scales / fine bed unverified")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    path = output / "candidate-pair-relief-curvature.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    result = {"reports": [pin(before_report), pin(after_report)], "candidates": [ap, bp],
        "cold_audits": [pin(record["cold_audit_path"]) for record in reports], "figure": pin(path),
        "inputs_equal": True, "target_changed": False, "inserted_in_large_map": False,
        "elevation_limits_m": [low, high], "curvature_limits_m": [-curve_bound, curve_bound], "fine_bed_verified": False}
    (output / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def diagnose_saved_network(path):
    """Measure the preserved original routing and tile interfaces without rerouting."""
    from collections import deque
    path = Path(path)
    with np.load(path, allow_pickle=False) as archive:
        m = json.loads(str(archive["metadata_json"].item()))
        a = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
    receiver = a["receiver"]
    terminal = receiver < 0
    internal = terminal & (a["outlet_kind"] != "unknown_boundary")
    area = a["contributing_area_m2"]
    ids, targets = a["selected_edge_source_ids"], a["selected_edge_target_ids"]
    lookup = dict(zip(map(int, ids), map(int, targets)))
    donors = {cell: 0 for cell in lookup}
    for target in lookup.values():
        if target in donors:
            donors[target] += 1
    pending = deque(cell for cell, count in donors.items() if count == 0)
    lengths, longest = {}, 0.
    width = a["original_td_m"].shape[1]
    while pending:
        cell = pending.popleft()
        target = lookup[cell]
        step = 30. * np.hypot(target % width - cell % width, target // width - cell // width)
        length = lengths.get(cell, 0.) + step
        lengths[target] = max(lengths.get(target, 0.), length)
        longest = max(longest, length)
        if target in donors:
            donors[target] -= 1
            if donors[target] == 0:
                pending.append(target)
    tiles = {}
    for record in m["tile_sources"]:
        tile = checked_archive(record["path"], expected_sha256=record["sha256"])
        tiles[tuple(record["tile_xz"])] = tile["elevation_m"]
    overlaps, jumps = [], []
    for (tx, tz), tile in tiles.items():
        if (tx + 1, tz) in tiles:
            neighbor = tiles[tx + 1, tz]
            overlaps.extend((neighbor[:256, 0] - tile[:256, 256]).tolist())
            jumps.extend((neighbor[:256, 0] - tile[:256, 255]).tolist())
        if (tx, tz + 1) in tiles:
            neighbor = tiles[tx, tz + 1]
            overlaps.extend((neighbor[0, :256] - tile[256, :256]).tolist())
            jumps.extend((neighbor[0, :256] - tile[255, :256]).tolist())
    quantiles = lambda values: dict(zip(("p50", "p95", "max"), np.quantile(np.abs(values), [.5, .95, 1]).tolist()))
    return {"network_archive_sha256": file_sha256(path), "internal_raw_sink_count": int(internal.sum()),
        "maximum_internal_sink_catchment_m2": float(area[internal].max(initial=0)),
        "maximum_any_terminal_catchment_m2": float(area[terminal].max(initial=0)),
        "longest_continuous_selected_path_m": float(longest),
        "selected_path_scope": "continuous selected native edges above the existing 1km2 contributing-area threshold",
        "tile_owned_neighbor_step_abs_m": quantiles(jumps), "tile_same_coordinate_halo_overlap_abs_m": quantiles(overlaps),
        "halo_overlap_sample_count": len(overlaps), "source_modified": False, "routing_recomputed": False}


if __name__ == "__main__":
    main()
