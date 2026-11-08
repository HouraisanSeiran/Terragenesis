"""Read-only views of pinned M5 geometry and its actual M6 sediment replay."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
M5 = ROOT / "verification/td-river-geometry/m5-20261008-06"
M6 = ROOT / "verification/td-river-sediment/m6-20261008-03"
VALLEY = ROOT / "verification/td-shaped-valley/td1024-20261010-01/manifest.json"
RELEASE_MANIFEST = ROOT / "web-preview/data/river-product-v1/manifest.json"
CASES = {"main": (M5, "td_fine", "TD1024 · 主段河槽"),
         "bend": (M5, "td_bend_fine", "TD1024 · 弯道河槽"),
         "sediment": (M5, "td_fine", "同一主段 · 侵蚀沉积 0–900 s")}


def catalog():
    product = saved_release()
    return {"cases": [{"id": c["id"], "label": c["label"]} for c in product["bounded_results"]["cases"]],
            "release": {"version": product["version"], "identity_sha256": product["identity_sha256"], "publishable": False}}


def saved_release():
    return _saved_release()[1]


def _saved_release():
    from terrain_pipeline.surface_rivers.metric_river_release import load_release
    pin = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))["product"]
    path = RELEASE_MANIFEST.parent / pin["path"]
    return path, load_release(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])


def release_manifest():
    """Pinned M8 bounded geometry/sediment references consumed by cold reads."""
    product = saved_release()
    entries = []
    for case in product["bounded_results"]["cases"]:
        pin = case["geometry"]
        entry = {"id": case["id"], "label": case["label"], "kind": case["kind"],
                 "path": pin["path"], "sha256": pin["sha256"], "identity_sha256": pin.get("identity_sha256")}
        if case["kind"] == "shaped_valley_component":
            entry["manifest_sha256"] = case["manifest"]["sha256"]
        entries.append(entry)
    return {"schema": "terragenesis-m8-bounded-results-v1", "version": product["version"], "publishable": False,
            "natural_outlet_verified": False, "hydraulic_ready": False,
            "limitations": ["bounded local geometry and frozen-water sediment replay", "global geometry remains 623/673 accepted edges", "natural outlet, CRS, lake/backwater and recoupling unresolved"],
            "cases": entries}


def pinned(directory, name):
    report = json.loads((directory / "acceptance.json").read_text(encoding="utf-8"))
    pin = report["artifacts"][name]
    path = directory / pin["path"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != pin["sha256"]:
        raise ValueError("Saved evidence checksum mismatch")
    return path, pin


@lru_cache(maxsize=6)
def saved_case(case_id):
    from terrain_pipeline.channel_geometry import load_channel_geometry
    from terrain_pipeline.surface_rivers.metric_river_release import resolve_release_pin
    release_path, product = _saved_release()
    entry = next(c for c in product["bounded_results"]["cases"] if c["id"] == case_id)
    pin = entry["geometry"]
    path, label = resolve_release_pin(release_path, product, pin), entry["label"]
    if case_id.startswith("valley-"):
        from terrain_pipeline.channel_geometry import load_monotone_union
        record = entry["comparison"]
        manifest_sha256 = entry["manifest"]["sha256"]
        bundle = load_monotone_union(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    elif case_id not in CASES:
        raise ValueError("Unknown saved river result")
    else:
        bundle = load_channel_geometry(path, expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    a, meta = bundle["arrays"], bundle["metadata"]
    xz = a["vertices_xz_m"]
    # Sample the represented piecewise-linear mesh, never an analytic channel sketch.
    import matplotlib.tri as tri
    triangulation = tri.Triangulation(xz[:, 0], xz[:, 1], a["triangles"])
    original = tri.LinearTriInterpolator(triangulation, a["source_elevation_m"])
    bed = tri.LinearTriInterpolator(triangulation, a["bed_elevation_m"])
    terrain = meta["terrain_metadata"]
    from scipy.ndimage import map_coordinates
    low, high = xz.min(0) - 30., xz.max(0) + 30.
    gx, gz = np.meshgrid(np.linspace(low[0], high[0], 65), np.linspace(low[1], high[1], 97))
    context_xz = np.column_stack((gx.ravel(), gz.ravel()))
    context_original = map_coordinates(a["source_height_m"], [(context_xz[:, 1] - terrain["z0_m"]) / terrain["dz_m"],
                                                            (context_xz[:, 0] - terrain["x0_m"]) / terrain["dx_m"]], order=1)
    native_bed = bed(context_xz[:, 0], context_xz[:, 1])
    context_bed = np.where(np.ma.getmaskarray(native_bed), context_original, np.asarray(native_bed))
    context_triangles = []
    for row in range(96):
        for column in range(64):
            index = row * 65 + column
            ids = [index, index + 1, index + 65, index + 66]
            # Keep the actual fine mesh in charge inside its support footprint.
            if any(not np.ma.getmaskarray(native_bed)[i] for i in ids):
                continue
            context_triangles.extend([[index, index + 1, index + 66], [index, index + 66, index + 65]])
    sections = []
    for i, target in enumerate(a["receiver"]):
        if target < 0:
            continue
        start, end = a["node_xz_m"][[i, target]]
        midpoint = (start + end) / 2
        direction = end - start
        normal = np.array([-direction[1], direction[0]]) / np.linalg.norm(direction)
        span = (a["width_m"][i] + a["width_m"][target]) / 4 + float(np.max(a["cut_depth_m"])) * meta.get("bank_slope_h_per_v", 2.)
        offsets = np.linspace(-span, span, 121)
        points = midpoint + offsets[:, None] * normal
        h0, h1 = original(points[:, 0], points[:, 1]), bed(points[:, 0], points[:, 1])
        valid = ~(np.ma.getmaskarray(h0) | np.ma.getmaskarray(h1))
        sections.append({"label": f"河段 {i + 1} 横断面", "offset_m": offsets[valid].tolist(),
                         "original_m": np.asarray(h0)[valid].tolist(), "bed_m": np.asarray(h1)[valid].tolist(),
                         "center_xz_m": midpoint.tolist(), "endpoints_xz_m": points[valid][[0, -1]].tolist(), "method": "saved mesh triangle linear interpolation"})
    result = {"id": case_id, "label": label, "identity": bundle["identity_sha256"],
              "source": {**pin,
                         "terrain": meta["terrain_metadata"], "bounds_xz_m": [xz.min(0).tolist(), xz.max(0).tolist()]},
              "metadata": meta, "mesh": {"xz": xz.tolist(), "triangles": a["triangles"].tolist(),
              "original_m": a["source_elevation_m"].tolist(), "bed_m": a["bed_elevation_m"].tolist(),
              "cut_m": a["cut_depth_m"].tolist()}, "sections": sections,
              "nodes_xz_m": a["node_xz_m"].tolist(), "original_nodes_xz_m": a.get("original_node_xz_m", a["node_xz_m"]).tolist(), "receiver": a["receiver"].tolist(), "sediment": None,
              "comparison": record if case_id.startswith("valley-") else None}
    if case_id.startswith("valley-"):
        result["source"]["manifest_path"] = entry["manifest"]["path"]
        result["source"]["manifest_sha256"] = manifest_sha256
    result["context"] = {"xz": context_xz.tolist(), "original_m": context_original.tolist(),
                         "bed_m": context_bed.tolist(), "triangles": context_triangles,
                         "sampling": "Same raw TD source, bilinear display sampling; fine channel mesh overrides its footprint"}
    if case_id == "sediment":
        from terrain_pipeline.surface_rivers.metric_sediment import load_sediment
        sediment_pin = entry["sediment"]
        sediment_path = resolve_release_pin(release_path, product, sediment_pin)
        sediment = load_sediment(sediment_path, expected_sha256=sediment_pin["sha256"])
        if sediment["metadata"]["geometry_identity_sha256"] != bundle["identity_sha256"]:
            raise ValueError("Sediment does not belong to the displayed geometry")
        s = sediment["arrays"]
        indices = np.unique(np.r_[np.arange(0, len(s["trace_time_seconds"]), 60), len(s["trace_time_seconds"]) - 1])
        cumulative = lambda key: np.r_[0., np.cumsum(s[key].sum(axis=1))][indices].tolist()
        result["sediment"] = {"source": {**sediment_pin},
            "metadata": sediment["metadata"], "time_seconds": s["trace_time_seconds"][indices].tolist(),
            "bed_delta_mm": ((s["trace_bed_elevation_m"][indices] - s["domain_bed_elevation_m"]) * 1000).tolist(),
            "eroded_solid_m3": cumulative("step_eroded_loose_solid_m3"),
            "eroded_rock_m3": cumulative("step_eroded_rock_m3"),
            "deposited_solid_m3": cumulative("step_deposited_solid_m3"),
            "exported_solid_m3": s["cumulative_exported_solid_m3"][indices].tolist(),
            "display": "Exact saved node changes in millimetres; no extrapolation to M5 mesh"}
    result["release"] = {"version": product["version"], "identity_sha256": product["identity_sha256"], "publishable": False,
                         "gates": product["gates"]["unresolved"], "case": entry}
    return result
