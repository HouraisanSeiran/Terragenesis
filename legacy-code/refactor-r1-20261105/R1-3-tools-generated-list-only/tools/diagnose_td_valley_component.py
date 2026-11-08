"""Read-only diagnostic for one failed TD sparse valley component."""

import argparse
import json
from pathlib import Path

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.surface_rivers.metric_channel_geometry import GeometryConfig, _footprint, _sample
from terrain_pipeline.surface_rivers.metric_network_geometry import load_network_geometry_plan
from terrain_pipeline.surface_rivers.metric_product import load_diagnostic_product
from terrain_pipeline.surface_rivers.metric_valley_incision import _profile, _profile_cut
from terrain_pipeline.surface_rivers.metric_valley_union import (
    _sparse_cells, _sparse_mesh, _mesh_height, _sparse_slope,
)
from terrain_pipeline.surface_rivers.metric_monotone_union import (
    build_monotone_union, load_monotone_union, save_monotone_union,
)
from tools.audit_td_river_geometry_sediment import independent_continuous_bed
from tools.verify_td_river_geometry import TD_DIRECTORY, TD_PRODUCT_SHA, TD_PRODUCT_ID, terrain_from_product
from tools.verify_td_valley_network_union import PARENT, connected_components


def diagnose(component_index, close=False, output=None):
    parent = json.loads((PARENT / "acceptance.json").read_text())
    source = load_diagnostic_product(TD_DIRECTORY / "product.npz", expected_sha256=TD_PRODUCT_SHA,
                                     expected_identity=TD_PRODUCT_ID)
    terrain = terrain_from_product(source)
    pin = parent["plan"]
    plan = load_network_geometry_plan(PARENT / pin["path"], expected_sha256=pin["sha256"])
    a = plan["arrays"]
    receiver = a["graph_receiver"]
    selected = a["selected_edge_source_ids"]
    owner = a["terminal_owner"].reshape(terrain.elevation_m.shape)
    q = a["contributing_area_m2"] / 1000. / 3600.
    widths = np.maximum(6., 4. * np.sqrt(q))
    depths = np.maximum(.25, .2 * np.cbrt(q))
    eligible = []
    for cell in selected:
        ids = np.array([cell, receiver[cell]], np.int64)
        points = np.array([terrain.world_xz(int(v)) for v in ids])
        rec = np.array([1, -1], np.int64)
        try:
            _profile(points, rec, depths[ids], terrain, 4.)
            _footprint(points, rec, widths[ids], np.full(2, 4.), terrain, owner,
                       np.ones(owner.shape, bool), np.zeros(owner.shape, bool),
                       owner.ravel()[ids], .5)
            eligible.append(int(cell))
        except ValueError:
            pass
    components = connected_components(eligible, receiver)
    ids = components[component_index]
    eligible_set = set(eligible)
    mapping = {int(cell): i for i, cell in enumerate(ids)}
    rec = np.array([mapping[int(receiver[cell])] if int(cell) in eligible_set else -1
                    for cell in ids], np.int64)
    points = np.array([terrain.world_xz(int(v)) for v in ids])
    config = GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0)
    profile = _profile(points, rec, depths[ids], terrain, 4.)
    cells = _sparse_cells(points, rec, widths[ids], profile, config, terrain)
    vertices, triangles = _sparse_mesh(cells, terrain, .5, config.max_vertices)
    source_height = _sample(terrain.elevation_m, vertices, terrain)[0]
    cut = _profile_cut(points, rec, widths[ids], profile, vertices, terrain,
                       np.zeros(owner.shape, bool))
    bed = source_height - cut
    lookup = {tuple(cell): index for index, cell in enumerate(cells)}
    origin = np.array([terrain.x0_m, terrain.z0_m])
    worst = None
    for i, j in enumerate(rec):
        if j < 0:
            continue
        start, end = points[i], points[j]
        delta = end - start
        count = max(1, int(np.linalg.norm(delta) / .125))
        sample_t = np.linspace(0., 1., count + 1)
        sampled = []
        for t in sample_t:
            position = start + t * delta
            key = tuple(np.floor((position - origin) / .5 - 1e-10).astype(int))
            cell = lookup.get(key)
            if cell is None:
                continue
            sampled.append((t, _mesh_height(position, cell, vertices, triangles, bed)))
        for (t0, h0), (t1, h1) in zip(sampled[:-1], sampled[1:]):
            rise = h1 - h0
            if worst is None or rise > worst["rise_m"]:
                middle = start + (t0 + t1) / 2. * delta
                worst = dict(source_cell_id=int(ids[i]), receiver_cell_id=int(ids[j]),
                             t0=float(t0), t1=float(t1), h0=float(h0), h1=float(h1),
                             rise_m=float(rise), middle_xz_m=middle.tolist())
    if worst is not None:
        i = mapping[worst["source_cell_id"]]
        j = rec[i]
        sample_t = np.array([worst["t0"], worst["t1"]])
        sample_xz = points[i] + sample_t[:, None] * (points[j] - points[i])
        source_pair = _sample(terrain.elevation_m, sample_xz, terrain)[0]
        edge_profiles = []
        edge_index = 0
        for e, target in enumerate(rec):
            if target < 0:
                continue
            lo, hi = profile[0][edge_index:edge_index + 2]
            one = (np.array([0, hi - lo], np.int64), profile[1][lo:hi],
                   profile[2][lo:hi], profile[3][lo:hi])
            contribution = _profile_cut(points[[e, target]], np.array([1, -1], np.int64),
                                        widths[ids[[e, target]]], one, sample_xz, terrain,
                                        np.zeros(owner.shape, bool))
            if np.max(contribution) > .001:
                edge_profiles.append(dict(edge_source=int(ids[e]), edge_target=int(ids[target]),
                                          cut_depth_m=contribution.tolist()))
            edge_index += 1
        worst["original_source_m"] = source_pair.tolist()
        worst["contributors"] = sorted(edge_profiles, key=lambda row: -max(row["cut_depth_m"]))[:8]
    report = dict(component_index=component_index, node_count=len(ids),
                  edge_count=int(np.count_nonzero(rec >= 0)),
                  first_ids=ids[:10].tolist(), worst_sampled=worst)
    if close:
        destination = Path(output).resolve() if output is not None else None
        if destination is not None:
            destination.mkdir(parents=True, exist_ok=False)
        products = {}
        for label, spacing in (("coarse", .5), ("fine", .25)):
            config = GeometryConfig(fine_spacing_m=spacing, smoothing_iterations=0)
            product = build_monotone_union(
                terrain, ids, rec, widths[ids], depths[ids], owner_grid=owner,
                corridor_mask=np.ones(owner.shape, bool), lake_mask=np.zeros(owner.shape, bool),
                source_plan_identity_sha256=plan["identity_sha256"], config=config)
            b = product["arrays"]
            _sparse_slope(b["node_xz_m"], b["receiver"], b["sparse_cell_xy"],
                          b["vertices_xz_m"], b["triangles"], b["bed_elevation_m"],
                          spacing, terrain)
            independent = independent_continuous_bed(product)
            record = dict(identity_sha256=product["identity_sha256"],
                          closure=product["metadata"]["closure"],
                          cut_volume_m3=product["metadata"]["cut_volume_m3"],
                          independent_PL=independent)
            if destination is not None:
                path = destination / f"component-{component_index:03d}-{label}.npz"
                save_monotone_union(path, product)
                sha = file_sha256(path)
                cold = load_monotone_union(path, expected_sha256=sha,
                                           expected_identity=product["identity_sha256"])
                independent_continuous_bed(cold)
                record.update(path=path.name, sha256=sha)
            products[label] = record
        relative = abs(products["coarse"]["cut_volume_m3"] - products["fine"]["cut_volume_m3"]) / max(
            products["fine"]["cut_volume_m3"], 1e-12)
        if relative > .02:
            raise ValueError("monotone union spatial refinement exceeds 2% gate")
        report["products"] = products
        report["spatial_refinement_relative"] = relative
        report["source_plan_identity_sha256"] = plan["identity_sha256"]
        report["code_sha256"] = {
            str(path): file_sha256(path) for path in (
                Path(__file__).resolve().parents[1] / "terrain_pipeline/surface_rivers/metric_monotone_union.py",
                Path(__file__).resolve().parents[1] / "terrain_pipeline/surface_rivers/metric_valley_union.py",
                Path(__file__).resolve().parents[1] / "terrain_pipeline/surface_rivers/metric_valley_incision.py",
                Path(__file__).resolve())}
        if destination is not None:
            publish_bytes(destination / "acceptance.json", json.dumps(report, indent=2,
                          allow_nan=False).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("component", type=int)
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.component, args.close, args.output), indent=2))
