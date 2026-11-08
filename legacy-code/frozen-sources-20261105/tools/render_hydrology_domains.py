"""Render standalone scientific figures and a read-only HTML index; no JavaScript."""

import argparse
import html
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def render_coarse_plan(plan_path, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from terrain_pipeline.hydrology_planning import load_plan

    plan = load_plan(plan_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    h = plan["height_m"]
    original = plan["original_height_m"]
    owner = plan["owner_domain_id"]
    receivers = plan["receiver"].ravel()
    rows, cols = h.shape
    ox, oz = plan["origin_xz_m"]
    s = plan["spacing_m"]
    x = (ox + np.arange(cols) * s) / 1000
    z = (oz + np.arange(rows) * s) / 1000
    accepted_z, accepted_x = np.nonzero(owner >= 0)
    zoom = [x[accepted_x.min()] - s / 1000, x[accepted_x.max()] + s / 1000,
            z[accepted_z.max()] + s / 1000, z[accepted_z.min()] - s / 1000]
    extent = [x.min(), x.max(), z.max(), z.min()]
    for scale in ("full", "selected-domains"):
        fig, axes = plt.subplots(2, 2, figsize=(14, 11), constrained_layout=True)
        panels = [(original, "Original procedural coarse condition (not TD)", "terrain"),
                  (h, "Frozen derived planning height (m)", "terrain"),
                  (h - original, "Planning change (m)", "RdBu_r"),
                  (owner, "Owner: accepted domains >=0, ocean -1, unknown -2", "tab10")]
        limits = (min(original.min(), h.min()), max(original.max(), h.max()))
        for ax, (values, title, cmap) in zip(axes.ravel(), panels):
            kwargs = {"vmin": limits[0], "vmax": limits[1]} if cmap == "terrain" else {}
            if cmap == "RdBu_r":
                bound = max(0.01, float(np.abs(values).max()))
                kwargs = {"vmin": -bound, "vmax": bound}
            image = ax.imshow(values, extent=extent, cmap=cmap, interpolation="nearest", **kwargs)
            if cmap == "terrain":
                ax.contour(x, z, h if values is h else original, levels=[0], colors="cyan", linewidths=0.7)
            ax.set(title=title, xlabel="x east (km)", ylabel="z south (km)")
            if scale != "full":
                ax.set_xlim(zoom[:2])
                ax.set_ylim(zoom[2:])
            fig.colorbar(image, ax=ax, shrink=0.8)
        selected = np.flatnonzero((owner.ravel() >= 0) & (receivers >= 0))
        river = np.asarray(plan.get("river_mask", owner >= 0)).ravel()
        for ax in (axes[0, 1], axes[1, 1]):
            for cell in selected[river[selected]]:
                cz, cx = divmod(int(cell), cols)
                dz, dx = divmod(int(receivers[cell]), cols)
                ax.plot([x[cx], x[dx]], [z[cz], z[dz]], color="#147cbd", alpha=0.65, linewidth=0.5)
            for first, second in plan["shared_boundary_edges"]:
                az, axx = divmod(int(first), cols)
                bz, bxx = divmod(int(second), cols)
                mx, mz = (x[axx] + x[bxx]) / 2, (z[az] + z[bz]) / 2
                ax.plot(mx, mz, marker=".", color="magenta", markersize=2)
            for domain in plan["domains"]:
                for cell in domain["terminal_indices"]:
                    tz, tx = divmod(int(cell), cols)
                    ax.plot(x[tx], z[tz], "x", color="black", markersize=5)
        fig.suptitle("Frozen planning diagnostic - " + scale + "\n" + plan.get("status", "unverified"), fontsize=12)
        fig.savefig(output / ("coarse-" + scale + ".png"), dpi=150)
        plt.close(fig)
    return {"figures": [str(output / "coarse-full.png"), str(output / "coarse-selected-domains.png")]}


def render_detail_gallery(source, output, *, selected_v4=False, selected_projection=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    detail_paths = source.rglob("*-detail.npz") if selected_v4 or selected_projection else source.glob("*-detail.npz")
    for path in sorted(detail_paths):
        if selected_v4 and "global-residual-v4-proposal" not in path.name:
            continue
        if selected_projection and "canonical-projection-v2-detail" not in path.name:
            continue
        with np.load(path, allow_pickle=False) as archive:
            arrays = {key: archive[key] for key in archive.files if key != "metadata_json"}
            metadata = json.loads(str(archive["metadata_json"].item()))
        rows, cols = arrays["original_td_m"].shape
        ox, oz = metadata["origin_xz_m"]
        spacing = metadata["spacing_m"]
        extent = [ox / 1000, (ox + (cols - 1) * spacing) / 1000,
                  (oz + (rows - 1) * spacing) / 1000, oz / 1000]
        fig, axes = plt.subplots(3, 3, figsize=(15, 13), constrained_layout=True)
        elevations = [arrays["original_td_m"], arrays["derived_height_m"]]
        vmin = min(float(a.min()) for a in elevations)
        vmax = max(float(a.max()) for a in elevations)
        panels = [("original_td_m", "Original genuine TD (m)", "terrain", vmin, vmax),
                  ("derived_height_m", "Derived macro geometry (m)", "terrain", vmin, vmax),
                  ("derived_height_m", "Derived local relief (m; independent scale)", "terrain", None, None),
                  ("owner_domain_id", "Frozen domain ownership", "tab10", None, None),
                  ("macro_delta_m", "Macro derivation delta (m)", "RdBu_r", None, None),
                  ("total_delta_m", "Total change from original TD (m)", "RdBu_r", None, None),
                  ("td_residual_retention", "TD residual retained fraction (0..1)", "viridis", 0, 1),
                  ("ocean_mask", "Connected frozen ocean support below sea 0", "Blues", 0, 1),
                  ("connected_lake_wet_mask", "Local connected wet lake footprint", "Blues", 0, 1)]
        for ax, (name, title, cmap, lower, upper) in zip(axes.ravel(), panels):
            if name == "td_residual_retention" and metadata.get("source_residual_fraction") == 1.0:
                title = "TD residual target input fraction (0..1)"
            values = arrays.get(name, np.zeros((rows, cols)))
            if cmap == "RdBu_r" and lower is None:
                limit = max(0.01, float(np.abs(values).max()))
                lower, upper = -limit, limit
            artist = ax.imshow(values, cmap=cmap, vmin=lower, vmax=upper, extent=extent, interpolation="nearest")
            if name == "derived_height_m":
                for mask, color, marker in (("cross_owner_d8_mask", "magenta", "x"),
                                             ("unplanned_sink_mask", "black", ".")):
                    rz, rx = np.nonzero(arrays[mask])
                    ax.scatter((ox + rx * spacing) / 1000, (oz + rz * spacing) / 1000,
                               s=7, c=color, marker=marker, label=mask)
                ax.legend(fontsize=6, loc="upper right")
                heights = arrays["derived_height_m"]
                for level, color in ((0.0, "cyan"), (metadata.get("fixed_lake_level_m"), "royalblue")):
                    if level is not None and heights.min() < level < heights.max():
                        contour = ax.contour(np.linspace(extent[0], extent[1], cols),
                            np.linspace(extent[3], extent[2], rows), heights, levels=[level], colors=[color], linewidths=1.0)
                        ax.clabel(contour, fmt="%.3fm", fontsize=7)
            ax.set(title=title, xlabel="x east (km)", ylabel="z south (km)")
            fig.colorbar(artist, ax=ax, shrink=0.8)
        reasons = "; ".join(metadata["rejection_reasons"]) or "local compatible; global unverified"
        fig.suptitle(metadata["window_kind"] + " - " + metadata["status"] + "\n" + reasons, fontsize=10)
        image_path = output / (path.stem + ".png")
        fig.savefig(image_path, dpi=150)
        plt.close(fig)
        record_path = output / (path.stem + ".json")
        record_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        entries.append((metadata["window_kind"], image_path.name, record_path.name, metadata["status"], reasons))
        if "projection_target_height_m" in arrays:
            target = arrays["projection_target_height_m"]
            projected = arrays["derived_height_m"]
            correction = projected - target
            fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
            lower, upper = min(float(target.min()), float(projected.min())), max(float(target.max()), float(projected.max()))
            limit = max(0.01, float(np.abs(correction).max()))
            for ax, values, title, cmap, vlow, vhigh in zip(axes, (target, projected, correction),
                ("Full-residual target before constraints (m)", "Actual projected geometry (m)", "Actual projected minus target (m)"),
                ("terrain", "terrain", "RdBu_r"), (lower, lower, -limit), (upper, upper, limit)):
                artist = ax.imshow(values, cmap=cmap, vmin=vlow, vmax=vhigh, extent=extent, interpolation="nearest")
                ax.set(title=title, xlabel="x east (km)", ylabel="z south (km)")
                fig.colorbar(artist, ax=ax, shrink=0.8)
            fig.suptitle("Canonical TD target weight is an input, not final residual retention\n"
                + "Actual correction max = " + format(float(np.abs(correction).max()), ".3f") + " m; " + metadata["status"], fontsize=10)
            correction_path = output / (path.stem + "-target-correction.png")
            fig.savefig(correction_path, dpi=150)
            plt.close(fig)
            entries.append((metadata["window_kind"] + " target correction", correction_path.name, record_path.name,
                            metadata["status"], "Target input weight does not certify final retained TD detail."))
    for path in sorted(source.glob("*-planned-conditioned-comparison.npz")):
        with np.load(path, allow_pickle=False) as archive:
            values = {key: archive[key] for key in archive.files if key != "metadata_json"}
            metadata = json.loads(str(archive["metadata_json"].item()))
        audit = metadata["audit"]
        ox, oz = audit["origin_xz_m"]
        spacing = audit["spacing_m"]
        rows, cols = values["original_td_m"].shape
        extent = [ox / 1000, (ox + (cols - 1) * spacing) / 1000, (oz + (rows - 1) * spacing) / 1000, oz / 1000]
        fig, axes = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
        limits = (min(values["original_td_m"].min(), values["planned_conditioned_td_m"].min()),
                  max(values["original_td_m"].max(), values["planned_conditioned_td_m"].max()))
        for ax, name, title in zip(axes.ravel(),
                ("original_td_m", "planned_conditioned_td_m", "total_delta_m", "planned_conditioned_td_m"),
                ("Immutable original genuine TD (m)", "Plan-conditioned genuine TD candidate (m)",
                 "Actual total change from original TD (m)", "Candidate actual D8 faults")):
            delta = name == "total_delta_m"
            lower, upper = (-max(0.01, np.abs(values[name]).max()), max(0.01, np.abs(values[name]).max())) if delta else limits
            image = ax.imshow(values[name], extent=extent, cmap="RdBu_r" if delta else "terrain", vmin=lower, vmax=upper)
            ax.set(title=title, xlabel="x east (km)", ylabel="z south (km)")
            fig.colorbar(image, ax=ax, shrink=0.8)
        for mask, color, marker in (("cross_owner_d8_mask", "magenta", "x"), ("unplanned_sink_mask", "black", ".")):
            rz, rx = np.nonzero(values[mask])
            axes[1, 1].scatter((ox + rx * spacing) / 1000, (oz + rz * spacing) / 1000,
                               c=color, s=8, marker=marker, label=mask)
        axes[1, 1].legend(fontsize=7)
        reasons = "; ".join(audit["rejection_reasons"]) or "local compatible; global unverified"
        fig.suptitle("Plan-conditioned TD candidate: " + metadata["status"] + "\n" + reasons, fontsize=10)
        image_path = output / (path.stem + ".png")
        fig.savefig(image_path, dpi=150)
        plt.close(fig)
        record_path = output / (path.stem + ".json")
        record_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        entries.append(("planned-condition-candidate", image_path.name, record_path.name, metadata["status"], reasons))
    bed_paths = source.rglob("*-continuous-fine-bed.npz") if selected_v4 or selected_projection else source.glob("*-continuous-fine-bed.npz")
    for path in sorted(bed_paths):
        if selected_v4 and "global-residual-v4" not in path.name:
            continue
        if selected_projection and "canonical-projection-v2" not in path.name:
            continue
        with np.load(path, allow_pickle=False) as archive:
            values = {key: archive[key] for key in archive.files if key != "metadata_json"}
            metadata = json.loads(str(archive["metadata_json"].item()))
        vertices, triangles = values["vertices_xz_m"], values["triangles"]
        from matplotlib.ticker import MaxNLocator
        reference = values["node_xz_m"][0]
        local_vertices = vertices - reference
        local_nodes = values["node_xz_m"] - reference
        fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
        for ax, name, title in zip(axes, ("bed_elevation_m", "local_cut_m", "total_delta_m"),
                                   ("Actual continuous bed (m)", "Local incision (m; max 4m)", "Total change from original TD (m)")):
            image = ax.tripcolor(local_vertices[:, 0], local_vertices[:, 1], triangles, values[name], shading="gouraud", cmap="terrain" if name == "bed_elevation_m" else "RdBu_r")
            nodes = local_nodes
            for node in np.flatnonzero(values["receiver"] >= 0):
                other = values["receiver"][node]
                ax.plot(nodes[[node, other], 0], nodes[[node, other], 1], color="black", linewidth=0.5)
            ax.set(title=title, xlabel="x east from reference (m)", ylabel="z south from reference (m)", aspect="equal")
            ax.xaxis.set_major_locator(MaxNLocator(3))
            ax.yaxis.set_major_locator(MaxNLocator(4))
            fig.colorbar(image, ax=ax, shrink=0.7)
        fig.suptitle("Clipped frozen river component: " + metadata["status"] + "; global hydraulics unverified\n"
                     + "Reference x,z = " + str(tuple(float(value) for value in reference)) + " m", fontsize=10)
        image_path = output / (path.stem + ".png")
        fig.savefig(image_path, dpi=150)
        plt.close(fig)
        record_path = output / (path.stem + ".json")
        record_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        entries.append(("continuous-fine-bed", image_path.name, record_path.name, metadata["status"], "local geometric evidence only"))
    fragments = ["<!doctype html><meta charset='utf-8'><title>Hydrological TD review</title>",
                 "<h1>Hydrological TD local review</h1><p>Original TD and derived geometry are distinct. "
                 "Native-grid channel requests are diagnostic only. Global hydraulic connectivity is unverified.</p>"]
    for kind, image_path, record_path, status, reasons in entries:
        fragments.append("<section><h2>" + html.escape(kind + ": " + status) + "</h2><p>"
            + html.escape(reasons) + "</p><a href='" + html.escape(record_path) + "'>Provenance and budget</a>"
            + "<p><img style='max-width:100%' src='" + html.escape(image_path) + "' alt='TD scientific review'></p></section>")
    if not entries:
        fragments.append("<p>No genuine TD detail artifacts present. No substitute figures generated.</p>")
    if selected_projection:
        for path in sorted((source / "canonical-projections-v2").glob("*-failure-*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            (output / path.name).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            fragments.append("<section><h2>" + html.escape(str(record["tile_xz"]) + ": " + record["status"])
                + "</h2><p>" + html.escape(record["reason"]) + "</p><a href='" + html.escape(path.name)
                + "'>Actual projection diagnostic</a></section>")
        for path in sorted(source.glob("*/*-canonical-projection-v2-continuous-fine-bed-review.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["status"] != "rejected":
                continue
            (output / path.name).write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            fragments.append("<section><h2>" + html.escape(record["window_kind"] + ": fine bed rejected")
                + "</h2><p>" + html.escape(record.get("reason", "Independent fine geometry did not pass"))
                + "</p><a href='" + html.escape(path.name) + "'>Actual fine bed diagnostic</a></section>")
    index = output / "index.html"
    index.write_text("\n".join(fragments), encoding="utf-8")
    return {"index": str(index), "figure_count": len(entries)}


def render_full_window_beds(review_path, output):
    """Plot only cold saved geometry; unavailable mesh samples remain gaps."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.ndimage import map_coordinates
    from tools.prepare_hydrology_domains import _read_bed_piece, _artifact_identity
    from terrain_pipeline.hydrology_detail_bed import _mesh_height

    review_path, output = Path(review_path), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = json.loads(review_path.read_text(encoding="utf-8"))

    def detail(path):
        with np.load(path, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata_json"].item()))
            arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
        if _artifact_identity(metadata, arrays) != metadata["identity"]:
            raise ValueError("full-window plot detail identity mismatch")
        return metadata, arrays

    complete_edge = report.get("schema") == "hydrology-complete-edge-bed-review-v1"
    native_meta, native = detail(report["detail_path"] if complete_edge else report["native97_detail_path"])
    support_meta, support = detail(report["detail_path"] if complete_edge else report["computational_support99_path"])
    request_path = report.get("component_request_path")
    if request_path is None:
        requests = list(review_path.parent.glob("request-*.json"))
        requests = [path for path in requests if json.loads(path.read_text())["centerline_profile"]["parent_detail_identity"] == support_meta["identity"]]
        if len(requests) != 1:
            raise ValueError("full-window plot requires one exact shared component request")
        request_path = requests[0]
    specification = json.loads(Path(request_path).read_text(encoding="utf-8"))
    if specification["centerline_profile"]["parent_detail_identity"] != support_meta["identity"]:
        raise ValueError("plot request belongs to a different support detail")
    results, issues = [], []
    records = ([{"path":path,"piece_index":index} for index,path in enumerate(report["piece_paths"])]
               if complete_edge else report["piece_results"])
    for record in records:
        path = Path(record["path"])
        if path.suffix != ".npz" or not path.exists():
            issues.append("Piece " + str(record["piece_index"]) + ": " + record.get("reason", "saved mesh unavailable"))
            continue
        result = _read_bed_piece(path)
        if result["parent_detail_identity"] != support_meta["identity"]:
            raise ValueError("plot mesh belongs to a different support detail")
        result["cell_lookup"] = {tuple(cell): index for index, cell in enumerate(result["arrays"]["cells"])}
        results.append(result)
    if len(results) != report["declared_piece_count"]:
        issues.append("Incomplete coverage: " + str(len(results)) + "/" + str(report["declared_piece_count"]) + " saved pieces; missing values are gaps.")

    points = np.asarray(specification["points_xz_m"])
    receivers = np.asarray(specification["receiver"], int)
    incoming = np.bincount(receivers[receivers >= 0], minlength=len(points))
    boundaries = (incoming != 1) | (receivers < 0)
    routes = []
    for first in np.flatnonzero(boundaries & (receivers >= 0)):
        indices = [int(first)]
        for _ in range(len(points)):
            other = int(receivers[indices[-1]])
            if other < 0:
                break
            indices.append(other)
            if boundaries[other]:
                break
        else:
            raise ValueError("full-window plot requires an acyclic declared receiver graph")
        route = points[indices]
        lengths = np.linalg.norm(np.diff(route, axis=0), axis=1)
        stations = np.r_[0, np.cumsum(lengths)]
        distance = np.unique(np.r_[np.linspace(0, stations[-1], max(2, int(stations[-1] / 2) + 1)), stations])
        locations = np.column_stack([np.interp(distance, stations, route[:, axis]) for axis in range(2)])
        routes.append({"points": route, "lengths": lengths, "stations": stations, "distance": distance, "locations": locations})
    if not routes:
        raise ValueError("full-window plot has no represented directed river arms")

    def native_sample(array, locations):
        coordinates = (locations - support_meta["origin_xz_m"]) / support_meta["spacing_m"]
        return map_coordinates(array, [coordinates[:, 1], coordinates[:, 0]], order=1, mode="constant", cval=np.nan)

    def mesh_sample(locations):
        sampled = np.full(len(locations), np.nan)
        for index, location in enumerate(locations):
            for result in results:
                arrays = result["arrays"]
                nodes = arrays["node_xz_m"]
                represented = False
                for first, other in enumerate(arrays["receiver"]):
                    if other < 0:
                        continue
                    vector = nodes[other] - nodes[first]
                    fraction = float(np.dot(location - nodes[first], vector) / np.dot(vector, vector))
                    if not -1e-8 <= fraction <= 1 + 1e-8:
                        continue
                    width = np.interp(fraction, [0, 1], arrays["width_m"][[first, other]])
                    if np.linalg.norm(location - nodes[first] - fraction * vector) <= width / 2 + 1e-7:
                        represented = True
                        break
                if not represented:
                    continue
                key = tuple(np.floor((location - result["mesh_origin_xz_m"]) / result["fine_spacing_m"]).astype(int))
                cell = result["cell_lookup"].get(key)
                if cell is None:
                    continue
                try:
                    sampled[index] = _mesh_height(location, cell, arrays["vertices_xz_m"], arrays["triangles"], arrays["bed_elevation_m"])
                except ValueError:
                    continue
                break
        return sampled

    shape = native["original_td_m"].shape
    spacing = native_meta["spacing_m"]
    extent = [0, (shape[1]-1)*spacing/1000, (shape[0]-1)*spacing/1000, 0]
    fig, axes = plt.subplots(2, 2, figsize=(13, 11), constrained_layout=True)
    height_limits = {"vmin": min(native["original_td_m"].min(), native["derived_height_m"].min()),
                     "vmax": max(native["original_td_m"].max(), native["derived_height_m"].max())}
    for ax, values, title, cmap in zip(axes.ravel(),
        (native["original_td_m"], native["derived_height_m"], native["derived_height_m"] - native["original_td_m"], native["derived_height_m"]),
        ("Genuine original TD (30 m samples)", "Derived macro terrain (30 m samples)",
         "Macro change within actual finite support (m)" if complete_edge else "Macro change within original97 (m)", "Actual saved 1 m bed cut (m)"),
        ("terrain", "terrain", "RdBu_r", "Greys")):
        color_limits = height_limits if cmap == "terrain" else {}
        if cmap == "RdBu_r":
            maximum_change = max(0.01, float(np.abs(values).max()))
            color_limits = {"vmin": -maximum_change, "vmax": maximum_change}
        image = ax.imshow(values, extent=extent, cmap=cmap, interpolation="nearest", **color_limits)
        for route in routes:
            local_path = (route["points"] - native_meta["origin_xz_m"]) / 1000
            ax.plot(local_path[:, 0], local_path[:, 1], color="#00b8bd", linewidth=1)
            ax.scatter(local_path[1:-1, 0], local_path[1:-1, 1], marker="|", color="black", s=30)
        ax.set(title=title, xlabel="Local east (km)", ylabel="Local south (km)")
        if ax is not axes[1, 1]:
            fig.colorbar(image, ax=ax, shrink=0.8)
    cut_image = None
    for result in results:
        arrays = result["arrays"]
        mask = arrays.get("export_scope_mask",np.ones(len(arrays["vertices_xz_m"]),bool))
        vertices = (arrays["vertices_xz_m"][mask] - native_meta["origin_xz_m"]) / 1000
        cut_image = axes[1, 1].scatter(vertices[:, 0], vertices[:, 1], c=arrays["local_cut_m"][mask], s=1, cmap="viridis", vmin=0, vmax=4)
    if cut_image is not None:
        fig.colorbar(cut_image, ax=axes[1, 1], shrink=0.8)
    coverage = report["coverage"]
    full_coarse_length = coverage.get("full_coarse_edge_length_m")
    if full_coarse_length is None and complete_edge:
        full_coarse_length = sum(route["stations"][-1] for route in routes)
    elif full_coarse_length is None:
        full_coarse_length = sum(edge["full_coarse_edge_length_m"] for edge in coverage["source_edges"])
    represented_length = coverage.get("represented_length_m",full_coarse_length)
    status = report.get("status", "accepted" if report.get("accepted") else "rejected")
    caption = (status + "; represented " + format(represented_length / 1000, ".3f")
        + " km of coarse edge(s) " + format(full_coarse_length / 1000, ".3f") + " km")
    bed_version = report.get("bed_version")
    if bed_version is None:
        bed_version = "v5-continuous-center-floor" if results and all(result.get("continuous_center_lowest") for result in results) else "v4-center-lowest" if results and all(result.get("center_lowest") for result in results) else "v3"
    if bed_version == "v3":
        issues.append("Legacy v3 ceiling-only bed: center-lowest channel cross-section is not certified.")
    scope_caption = ("Complete coarse-edge geometry; actual finite support; global hydrology unverified" if complete_edge
                     else "Original97 acceptance; genuine99 computation only; global hydrology unverified")
    fig.suptitle(caption + "\n" + scope_caption, fontsize=11)
    map_path = output / "full-window-route-and-change.png"
    fig.savefig(map_path, dpi=160)
    plt.close(fig)

    fig = plt.figure(figsize=(14, 10), constrained_layout=True)
    grid = fig.add_gridspec(2, 3, height_ratios=[1.3, 1])
    ax = fig.add_subplot(grid[0, :])
    for index, route in enumerate(routes):
        distance, path_points, stations = route["distance"], route["locations"], route["stations"]
        suffix = " (arm " + str(index + 1) + ")" if len(routes) > 1 else ""
        style = ("-", "--", "-.")[index % 3]
        ax.plot(distance, native_sample(support["original_td_m"], path_points), label="Original TD, 30 m" + suffix, color="#666666", linestyle=style)
        ax.plot(distance, native_sample(support["derived_height_m"], path_points), label="Derived macro, 30 m" + suffix, color="#1980a5", linestyle=style)
        ax.plot(distance, mesh_sample(path_points), label="Saved 1 m bed mesh" + suffix, color="#c8324d", linewidth=1, linestyle=style)
        for station in stations[1:-1]:
            ax.axvline(station, color="#888888", linestyle=":", linewidth=0.7)
    ax.set(title="Every declared directed arm; dotted lines are subdivision nodes", xlabel="Distance from each arm's upstream clip (m)", ylabel="Elevation (m)")
    ax.legend(fontsize=9)
    for column, fraction in enumerate((0.1, 0.5, 0.9)):
        route = routes[column % len(routes)] if len(routes) > 1 else routes[0]
        points, stations, lengths = route["points"], route["stations"], route["lengths"]
        if len(routes) > 1:
            fraction = 0.5
        station = fraction * stations[-1]
        index = min(len(lengths) - 1, np.searchsorted(stations, station, side="right") - 1)
        direction = (points[index + 1] - points[index]) / lengths[index]
        center = points[index] + direction * (station - stations[index])
        normal = np.array([-direction[1], direction[0]])
        offsets = np.linspace(-4, 4, 81)
        locations = center + offsets[:, None] * normal
        ax = fig.add_subplot(grid[1, column])
        td_center = float(native_sample(support["original_td_m"], center[None, :])[0])
        ax.plot(offsets, native_sample(support["derived_height_m"], locations), color="#1980a5", label="Derived macro")
        ax.plot(offsets, mesh_sample(locations), color="#c8324d", label="Saved bed mesh")
        ax.set(title="Cross-section at " + format(station, ".1f") + " m\nOriginal TD center: " + format(td_center, ".3f") + " m",
               xlabel="Transverse offset (m)", ylabel="Elevation (m)")
        ax.legend(fontsize=8)
    seam = report["seam_audit"]
    seam_caption = (str(seam.get("full_width_seam_samples", 0)) + " full-width seam samples; max shared difference "
        + format(seam.get("maximum_shared_full_width_bed_difference_m", float("nan")), ".3g") + " m; accepted=" + str(seam["accepted"]))
    fig.suptitle(caption + "\n" + seam_caption, fontsize=10)
    profile_path = output / "full-window-profiles.png"
    fig.savefig(profile_path, dpi=160)
    plt.close(fig)
    warnings = " ".join(issues) or "All declared pieces have saved meshes."
    index = output / "index.html"
    index.write_text("<!doctype html><meta charset='utf-8'><title>Full-window bed evidence</title><main style='max-width:1200px;margin:auto;font-family:sans-serif'>"
        + "<h1>" + html.escape(("complete edge" if complete_edge else report["window_kind"]) + " bed evidence") + "</h1><p>" + html.escape(caption)
        + "</p><p>" + html.escape(warnings) + "</p><p>Original TD and derived macro use 30 m samples; bed geometry uses saved 1 m meshes. "
        + ("The declared complete coarse edge is represented. Cross-edge continuity and global hydraulics remain unverified.</p>" if complete_edge
           else "The frozen 97 x 97 window is the acceptance scope. The 99 x 99 source only supports computation. The rest of the coarse edge and global hydraulics remain unverified.</p>")
        + "<pre style='white-space:pre-wrap'>" + html.escape(json.dumps({"bed_version": bed_version, "seam_audit": report["seam_audit"], "native_rejections": report.get("parent_detail_rejection_reasons",report.get("parent_native_rejection_reasons"))}, indent=2))
        + "</pre>" + "".join("<img style='width:100%' src='" + path.name + "' alt='Actual saved full-window geometry'>" for path in (map_path, profile_path)) + "</main>", encoding="utf-8")
    return {"index": str(index), "figures": [str(map_path), str(profile_path)], "issues": issues}


def render_hybrid_lake_bundle(plan_path, bundle_path, output):
    """Render a cold-audited periodic lake bundle and its actual fine footprint."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from terrain_pipeline.hydrology_planning import load_plan
    from terrain_pipeline.hydrology_seasonal_hybrid import load_hybrid_lake_bundle

    parent = load_plan(plan_path)
    bundle = load_hybrid_lake_bundle(parent, bundle_path)
    report, detail, result = bundle["manifest"], bundle["detail"], bundle["result"]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    metadata, arrays = detail["metadata"], detail["arrays"]
    domain = bundle["audit"]["domain_id"]
    column = result["metadata"]["domain_ids"].index(domain)
    levels = result["lake_level_m"][:, column]
    connectivity = bundle["connectivity"]
    minimum, maximum = connectivity["minimum_cycle_level_m"], connectivity["maximum_cycle_level_m"]
    spacing = metadata["spacing_m"]
    shape = arrays["derived_height_m"].shape
    extent = [0, (shape[1] - 1) * spacing / 1000, (shape[0] - 1) * spacing / 1000, 0]
    fig, axes = plt.subplots(2, 2, figsize=(13, 11), constrained_layout=True)
    original, derived = arrays["original_td_m"], arrays["derived_height_m"]
    height_limits = {"vmin": min(original.min(), derived.min()), "vmax": max(original.max(), derived.max())}
    delta = derived - original
    limit = max(0.01, float(np.abs(delta).max()))
    for ax, values, title, cmap, limits in zip(axes.ravel(),
        (original, derived, delta, (derived < minimum).astype(int) + (derived < maximum).astype(int)),
        ("Original genuine TD (30 m)", "Pinned derived lake footprint (30 m)", "Change from original TD (m)", "Wet footprint: 0 dry, 1 seasonal, 2 persistently wet"),
        ("terrain", "terrain", "RdBu_r", "Blues"),
        (height_limits, height_limits, {"vmin": -limit, "vmax": limit}, {"vmin": 0, "vmax": 2})):
        image = ax.imshow(values, extent=extent, cmap=cmap, interpolation="nearest", **limits)
        ax.set(title=title, xlabel="Local east (km)", ylabel="Local south (km)")
        fig.colorbar(image, ax=ax, shrink=0.8)
    fig.suptitle(report["status"] + "\nLocal fine footprint plus known retained coarse basin; global hydrology unverified", fontsize=11)
    geometry_path = output / "hybrid-lake-geometry.png"
    fig.savefig(geometry_path, dpi=160)
    plt.close(fig)
    geometry = result["lake_geometry"][str(domain)]
    beds = geometry["bed_elevations_m"]
    areas = geometry.get("bed_areas_m2")
    if areas is None:
        areas = np.full(len(beds), geometry["cell_area_m2"])
    monthly_area = np.array([areas[beds < level].sum() for level in levels])
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    months = np.arange(13)
    axes[0, 0].plot(months, levels, marker=".", color="#177ba0")
    axes[0, 0].set(title="Recomputed periodic lake level", ylabel="Level (m)", xlabel="Month boundary")
    axes[0, 0].ticklabel_format(useOffset=False, axis="y")
    axes[0, 1].plot(months, result["lake_volume_m3"][:, column] / 1e9, color="#177ba0", label="Storage")
    second = axes[0, 1].twinx()
    second.plot(months, monthly_area / 1e6, color="#bd3e53", linestyle="--", label="Actual wet area")
    axes[0, 1].set(title="Storage and changing wet area", ylabel="Storage (billion m3)", xlabel="Month boundary")
    second.set_ylabel("Wet area (km2)")
    axes[0, 1].legend(loc="upper left")
    second.legend(loc="upper right")
    monthly = result["monthly"]
    axes[1, 0].bar(np.arange(1, 13) - 0.2, (monthly["runoff_to_terminal_m3"][:, column] + monthly["lake_rain_m3"][:, column]) / 1e6,
                   width=0.4, label="Lake inflow + rain", color="#177ba0")
    axes[1, 0].bar(np.arange(1, 13) + 0.2, monthly["lake_evaporation_m3"][:, column] / 1e6,
                   width=0.4, label="Lake evaporation", color="#bd3e53")
    axes[1, 0].plot(np.arange(1, 13), monthly["lake_change_m3"][:, column] / 1e6, color="#333333", label="Storage change")
    axes[1, 0].set(title="Actual recomputed monthly lake account", ylabel="Volume (million m3)", xlabel="Month")
    axes[1, 0].legend(fontsize=8)
    stage = np.linspace(float(beds.min()), float(geometry["spill_m"]), 256)
    volume = np.array([np.sum(np.maximum(level - beds, 0) * areas) for level in stage])
    axes[1, 1].plot(volume / 1e9, stage, color="#177ba0")
    axes[1, 1].axhspan(minimum, maximum, color="#bd3e53", alpha=0.3, label="Actual periodic level range")
    axes[1, 1].set(title="Cold weighted basin hypsometry", xlabel="Storage (billion m3)", ylabel="Level (m)")
    axes[1, 1].legend(fontsize=8)
    fig.suptitle(report["status"] + "; cycle connectivity: " + connectivity["status"] + "\nRecomputed soil and lake cycle; retained coarse area is counted once", fontsize=11)
    seasonal_path = output / "hybrid-lake-seasonal-cycle.png"
    fig.savefig(seasonal_path, dpi=160)
    plt.close(fig)
    index = output / "index.html"
    index.write_text("<!doctype html><meta charset='utf-8'><title>Hybrid lake seasonal evidence</title><main style='max-width:1200px;margin:auto;font-family:sans-serif'>"
        + "<h1>Hybrid lake periodic geometry and accounts</h1><p>" + html.escape(report["status"])
        + "</p><p>Pinned 30 m genuine-TD-derived footprint replaces its exact coarse overlap. Retained coarse area remains explicit. "
        + "Soil and lake storage are recomputed to a periodic cycle. Fine geometry certification applies only to the actual cycle range and declared support. Global hydrology remains unverified.</p>"
        + "<pre style='white-space:pre-wrap'>" + html.escape(json.dumps({"replacement_audit": bundle["audit"], "connectivity": connectivity}, indent=2))
        + "</pre>" + "".join("<img style='width:100%' src='" + path.name + "' alt='Cold hybrid lake evidence'>" for path in (geometry_path, seasonal_path))
        + "</main>", encoding="utf-8")
    return {"index": str(index), "figures": [str(geometry_path), str(seasonal_path)], "status": report["status"]}


def render_basin_continuity(review_path, output):
    """Show actual frozen coarse coverage, terminal routes and measured interfaces."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from terrain_pipeline.hydrology_planning import load_plan
    from terrain_pipeline.mountain_source_adapter import file_sha256

    review = json.loads(Path(review_path).read_text(encoding="utf-8"))
    if file_sha256(review["plan_path"]) != review["plan_sha256"]:
        raise ValueError("continuity figure parent plan changed")
    plan = load_plan(review["plan_path"])
    if plan["identity_sha256"] != review["plan_identity"]:
        raise ValueError("continuity figure plan identity mismatch")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    owner = np.asarray(plan["owner_domain_id"])
    columns = owner.shape[1]
    origin = np.asarray(plan["origin_xz_m"])
    spacing = plan["spacing_m"]
    def points(cells):
        cells = np.asarray(cells)
        return (origin + np.column_stack((cells % columns, cells // columns)) * spacing) / 1000
    fig, axes = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True)
    extent = [origin[0] / 1000, (origin[0] + (columns - 1) * spacing) / 1000,
              (origin[1] + (owner.shape[0] - 1) * spacing) / 1000, origin[1] / 1000]
    for ax in axes:
        image = ax.imshow(plan["height_m"], extent=extent, cmap="terrain", interpolation="nearest")
        for edge in review["coarse_river_edges"]:
            line = points(edge)
            ax.plot(line[:, 0], line[:, 1], color="#415563", linewidth=1.2)
        for evidence in review["fine_evidence"]:
            line = points(evidence["source_edge"])
            color = "#29804e" if evidence["local_geometry_accepted"] and evidence["seam_audit"]["accepted"] else "#bc3251"
            ax.plot(line[:, 0], line[:, 1], color=color, linewidth=3)
        for terminal in review["terminal_paths"]:
            point = points([terminal["terminal_cell"]])[0]
            ax.plot(*point, marker="s" if terminal["kind"] == "inland" else "v", color="#663e88" if terminal["kind"] == "inland" else "#007eaf", markersize=6)
        ax.set(xlabel="x east (km)", ylabel="z south (km)")
    rows, cols = np.nonzero(owner >= 0)
    selected = points([int(rows.min()) * columns + int(cols.min()), int(rows.max()) * columns + int(cols.max())])
    axes[1].set_xlim(selected[:, 0].min() - spacing / 1000, selected[:, 0].max() + spacing / 1000)
    axes[1].set_ylim(selected[:, 1].max() + spacing / 1000, selected[:, 1].min() - spacing / 1000)
    axes[0].set_title("Complete frozen support; dark lines retain coarse representation")
    axes[1].set_title("Owned basin coverage; green = cold accepted fine geometry")
    fig.colorbar(image, ax=axes, label="Frozen coarse surface (m)", shrink=0.75)
    fig.suptitle(f"Owned coarse DAG: {review['traced_owned_cell_count']}/{review['owned_cell_count']} paths traced; "
                 f"{len(review['fine_evidence'])} fine edges, {len(review['coarse_only_river_edges'])} coarse edges\n"
                 + "Fine/coarse bed interfaces: " + ("accepted" if review["fine_to_coarse_interfaces_accepted"] else "unverified or rejected"), fontsize=12)
    figure = output / "basin-continuity-coverage.png"
    fig.savefig(figure, dpi=160)
    plt.close(fig)
    index = output / "index.html"
    index.write_text("<!doctype html><meta charset='utf-8'><title>Basin continuity evidence</title><main style='max-width:1400px;margin:auto;font-family:sans-serif'>"
                     + "<h1>Frozen basin continuity and representation coverage</h1><img style='width:100%' src='" + figure.name + "' alt='Basin continuity coverage'>"
                     + "<pre style='white-space:pre-wrap'>" + html.escape(json.dumps({key: review[key] for key in ("coarse_dag_accepted", "coarse_failures", "terminal_paths", "fine_evidence", "scope")}, indent=2))
                     + "</pre></main>", encoding="utf-8")
    return {"index": str(index), "figures": [str(figure)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coarse-plan", type=Path)
    parser.add_argument("--selected-v4", action="store_true", help="Consolidated five-window v4 geometry, residual and actual continuous beds")
    parser.add_argument("--selected-projection", action="store_true", help="Separate true TD residual canonical projection crops and genuine rejection diagnostics")
    parser.add_argument("--full-window-bed-review", type=Path, help="Cold saved full-window bed review; actual route, profiles and transverse mesh sections")
    parser.add_argument("--hybrid-lake-bundle", type=Path, help="Cold hybrid lake seasonal bundle directory; requires parent --coarse-plan")
    parser.add_argument("--basin-continuity-review", type=Path)
    args = parser.parse_args(argv)
    if args.selected_v4 and args.selected_projection:
        parser.error("select one distinct scientific proposal collection")
    if args.basin_continuity_review:
        result = render_basin_continuity(args.basin_continuity_review, args.output)
    elif args.hybrid_lake_bundle:
        if args.coarse_plan is None:
            parser.error("hybrid lake bundle requires its frozen parent coarse plan")
        result = render_hybrid_lake_bundle(args.coarse_plan, args.hybrid_lake_bundle, args.output)
    elif args.full_window_bed_review:
        result = render_full_window_beds(args.full_window_bed_review, args.output)
    else:
        result = render_detail_gallery(args.source, args.output, selected_v4=args.selected_v4, selected_projection=args.selected_projection)
    if args.coarse_plan and not args.hybrid_lake_bundle:
        result.update(render_coarse_plan(args.coarse_plan, args.output))
        index = args.output / "index.html"
        with index.open("a", encoding="utf-8") as stream:
            for figure in result["figures"]:
                name = Path(figure).name
                stream.write("<section><h2>" + html.escape(name) + "</h2><img style='max-width:100%' src='"
                             + html.escape(name) + "' alt='Frozen coarse planning diagnostic'></section>\n")
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    main()
