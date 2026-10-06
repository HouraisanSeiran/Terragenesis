"""Constrained node smoothing for a shared metric D8 channel plan."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.metric_channel_plan import _validate_route


VERSION = "channel-centerline-v1"


@dataclass(frozen=True)
class SmoothingRecipe:
    strength: float = .2
    max_offset_m: float = 5.
    min_separation_m: float = 0.

    def __post_init__(self):
        for name in ("strength", "max_offset_m", "min_separation_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.strength > .5:
            raise ValueError("strength must not exceed .5")


def _point_segment_distance(point, start, end):
    vector = end - start
    fraction = np.clip(np.dot(point - start, vector) / np.dot(vector, vector), 0., 1.)
    return float(np.linalg.norm(point - start - fraction * vector))


def _orientation(a, b, c):
    ab = b - a
    ac = c - a
    return float(ab[0] * ac[1] - ab[1] * ac[0])


def _segments_cross(a, b, c, d):
    o1, o2 = _orientation(a, b, c), _orientation(a, b, d)
    o3, o4 = _orientation(c, d, a), _orientation(c, d, b)
    if o1 * o2 < -1e-12 and o3 * o4 < -1e-12:
        return True
    for point, start, end, orientation in ((c, a, b, o1), (d, a, b, o2),
                                           (a, c, d, o3), (b, c, d, o4)):
        if (abs(orientation) <= 1e-9 and
                min(start[0], end[0]) - 1e-9 <= point[0] <= max(start[0], end[0]) + 1e-9 and
                min(start[1], end[1]) - 1e-9 <= point[1] <= max(start[1], end[1]) + 1e-9):
            return True
    return False


def _shared_edge_overlap(a, b, c, d, shared):
    other_a = b if np.array_equal(a, shared) else a
    other_b = d if np.array_equal(c, shared) else c
    if abs(_orientation(shared, other_a, other_b)) > 1e-9:
        return False
    return np.dot(other_a - shared, other_b - shared) > 1e-9


def _sample_height(height, position, params):
    x = (position[0] - params["origin_x_m"]) / params["spacing_x_m"]
    z = (position[1] - params["origin_z_m"]) / params["spacing_z_m"]
    if x < 0 or z < 0 or x > height.shape[1] - 1 or z > height.shape[0] - 1:
        raise ValueError("smoothed node leaves source height grid")
    x0, z0 = math.floor(x), math.floor(z)
    x1, z1 = min(x0 + 1, height.shape[1] - 1), min(z0 + 1, height.shape[0] - 1)
    tx, tz = x - x0, z - z0
    return float((1 - tx) * (1 - tz) * height[z0, x0] +
                 tx * (1 - tz) * height[z0, x1] +
                 (1 - tx) * tz * height[z1, x0] + tx * tz * height[z1, x1])


def build_centerline(plan, recipe: SmoothingRecipe):
    """Keep graph topology and node bed/width values; move degree-2 bends only."""
    if not isinstance(recipe, SmoothingRecipe) or plan.get("status") != "diagnostic_not_publishable":
        raise ValueError("diagnostic plan and smoothing recipe required")
    identity = ArtifactIdentity(**plan["identity"])
    if identity.sha256 != plan["identity_sha256"] or identity.algorithm != "metric-channel-plan":
        raise ValueError("invalid plan identity")
    arrays = plan["arrays"]
    params = identity.record()["parameters"]
    height = arrays["source_height_m"]
    receiver, order = _validate_route(arrays["receiver"], arrays["order"],
                                      height.shape, arrays["outlet_mask"])
    for name, field in (("source_height_m", "source_height_sha256"),
                        ("discharge_m3_s", "source_discharge_sha256"),
                        ("receiver", "source_route_sha256"),
                        ("order", "source_order_sha256"),
                        ("outlet_mask", "source_outlet_sha256")):
        if array_hash(np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError("plan source differs from identity")
    active = np.asarray(arrays["channel_mask"])
    bed = np.asarray(arrays["target_bed_m"])
    width = np.asarray(arrays["nominal_width_m"])
    if (active.shape != height.shape or active.dtype != bool or bed.shape != height.shape or
            width.shape != height.shape or not np.isfinite(bed).all() or
            not np.isfinite(width).all() or np.any(width[active] <= 0)):
        raise ValueError("invalid plan geometry")
    cols = height.shape[1]
    nodes = np.flatnonzero(active.ravel())
    if nodes.size == 0:
        raise ValueError("centerline requires an active channel")
    coords = np.column_stack((params["origin_x_m"] + nodes % cols * params["spacing_x_m"],
                              params["origin_z_m"] + nodes // cols * params["spacing_z_m"]))
    original = np.full((height.size, 2), np.nan)
    original[nodes] = coords
    moved = original.copy()
    donors = np.full(height.size, -1, dtype=np.int64)
    donor_count = np.zeros(height.size, dtype=np.int16)
    edges = []
    for cell in nodes:
        target = int(receiver[cell])
        if target >= 0 and active.flat[target]:
            edges.append((int(cell), target))
            donors[target] = cell
            donor_count[target] += 1
    anchors = np.zeros(height.size, dtype=bool)
    anchors[nodes] = donor_count[nodes] != 1
    anchors[nodes] |= receiver[nodes] < 0
    for cell in nodes:
        target = int(receiver[cell])
        if target < 0 or donor_count[cell] != 1:
            continue
        donor = int(donors[cell])
        suggested = original[cell] + recipe.strength * (
            (original[donor] + original[target]) / 2 - original[cell])
        offset = float(np.linalg.norm(suggested - original[cell]))
        if offset > recipe.max_offset_m + 1e-9:
            raise ValueError("smoothed node exceeds original route corridor")
        moved[cell] = suggested
    # Spatial buckets avoid all-pairs checks on large saved windows.
    bucket_size = max(params["spacing_x_m"], params["spacing_z_m"])
    buckets = {}
    for edge_index, (cell, target) in enumerate(edges):
        a, b = moved[cell], moved[target]
        margin = recipe.min_separation_m
        x0, x1 = math.floor((min(a[0], b[0]) - margin) / bucket_size), math.floor((max(a[0], b[0]) + margin) / bucket_size)
        z0, z1 = math.floor((min(a[1], b[1]) - margin) / bucket_size), math.floor((max(a[1], b[1]) + margin) / bucket_size)
        nearby = set()
        for bx in range(x0, x1 + 1):
            for bz in range(z0, z1 + 1):
                nearby.update(buckets.get((bx, bz), ()))
        for other_index in nearby:
            other_cell, other_target = edges[other_index]
            c, d = moved[other_cell], moved[other_target]
            shared = {cell, target} & {other_cell, other_target}
            if shared:
                if _shared_edge_overlap(a, b, c, d, moved[next(iter(shared))]):
                    raise ValueError("smoothing overlaps adjacent channel edges")
                continue
            if _segments_cross(a, b, c, d):
                raise ValueError("smoothing introduces a channel crossing")
            if recipe.min_separation_m > 0 and min(
                    _point_segment_distance(a, c, d), _point_segment_distance(b, c, d),
                    _point_segment_distance(c, a, b), _point_segment_distance(d, a, b)) < recipe.min_separation_m:
                raise ValueError("smoothing violates channel separation")
        for bx in range(x0, x1 + 1):
            for bz in range(z0, z1 + 1):
                buckets.setdefault((bx, bz), []).append(edge_index)
    slope_failed = np.zeros(height.size, dtype=bool)
    for cell, target in edges:
        distance = float(np.linalg.norm(moved[cell] - moved[target]))
        if bed.flat[cell] - bed.flat[target] + 1e-9 < params["min_bed_slope_m_per_m"] * distance:
            slope_failed[cell] = True
    local_budget_failed = np.zeros(height.size, dtype=bool)
    for cell in nodes:
        local_budget_failed[cell] = (_sample_height(height, moved[cell], params) - bed.flat[cell] >
                                     params["max_cut_m"] + 1e-9)
    geometry_hash = digest({name: array_hash(np.ascontiguousarray(arrays[name]))
                            for name in ("target_bed_m", "nominal_width_m", "channel_mask")})
    result_arrays = {"node_world_xz_m": moved[nodes].copy(), "original_world_xz_m": original[nodes].copy(),
                     "node_flat_index": nodes.astype(np.int64), "edge_donor_flat_index": np.array([e[0] for e in edges], dtype=np.int64),
                     "edge_target_flat_index": np.array([e[1] for e in edges], dtype=np.int64),
                     "node_bed_m": bed.ravel()[nodes].copy(), "node_width_m": width.ravel()[nodes].copy(),
                     "anchor_mask": anchors[nodes].copy(), "slope_failed_donor_mask": slope_failed[nodes].copy(),
                     "local_budget_failed_mask": local_budget_failed[nodes].copy()}
    result_geometry_hash = digest({name: array_hash(np.ascontiguousarray(value))
                                   for name, value in result_arrays.items()})
    result_identity = ArtifactIdentity("Terragenesis", "channel-centerline", VERSION, 0,
                                       {**asdict(recipe), "plan_identity_sha256": plan["identity_sha256"],
                                        "plan_geometry_sha256": geometry_hash,
                                        "result_geometry_sha256": result_geometry_hash})
    for value in result_arrays.values():
        value.flags.writeable = False
    return {"identity": result_identity.record(), "identity_sha256": result_identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": result_arrays,
            "summary": {"nodes": len(nodes), "edges": len(edges),
                        "moved_nodes": int(np.count_nonzero(np.linalg.norm(moved[nodes] - original[nodes], axis=1) > 1e-9)),
                        "max_offset_m": float(np.max(np.linalg.norm(moved[nodes] - original[nodes], axis=1))) if len(nodes) else 0.,
                        "slope_failed_edges": int(np.count_nonzero(slope_failed)),
                        "local_budget_failed_nodes": int(np.count_nonzero(local_budget_failed))}}


def save_centerline(result, path):
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ("identity", "identity_sha256", "status", "summary")}
    record["format_version"] = 1
    record["array_sha256"] = {key: array_hash(value) for key, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=f".{destination.name}-",
                                         suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_centerline(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_centerline(path):
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        arrays = {name: archive[name].copy() for name in record["array_sha256"]}
        expected = {"node_world_xz_m", "original_world_xz_m", "node_flat_index",
                    "edge_donor_flat_index", "edge_target_flat_index", "node_bed_m",
                    "node_width_m", "anchor_mask", "slope_failed_donor_mask",
                    "local_budget_failed_mask"}
        if set(arrays) != expected or set(archive.files) != expected | {"manifest"}:
            raise ValueError("invalid centerline arrays")
    identity = ArtifactIdentity(**record["identity"])
    if (identity.sha256 != record["identity_sha256"] or record["format_version"] != 1 or
            record["status"] != "diagnostic_not_publishable" or
            any(array_hash(arrays[name]) != expected for name, expected in record["array_sha256"].items())):
        raise ValueError("invalid centerline identity or hashes")
    if identity.algorithm != "channel-centerline" or identity.algorithm_version != VERSION:
        raise ValueError("wrong centerline algorithm")
    params = identity.record()["parameters"]
    SmoothingRecipe(params["strength"], params["max_offset_m"], params["min_separation_m"])
    if digest({name: array_hash(np.ascontiguousarray(value)) for name, value in arrays.items()}) != params["result_geometry_sha256"]:
        raise ValueError("centerline geometry differs from identity")
    node_count = arrays["node_flat_index"].size
    edge_count = arrays["edge_donor_flat_index"].size
    if (node_count == 0 or arrays["node_flat_index"].shape != (node_count,) or
            arrays["edge_target_flat_index"].shape != (edge_count,) or
            arrays["node_world_xz_m"].shape != (node_count, 2) or
            arrays["original_world_xz_m"].shape != (node_count, 2) or
            any(arrays[name].shape != (node_count,) for name in
                ("node_bed_m", "node_width_m", "anchor_mask", "slope_failed_donor_mask",
                 "local_budget_failed_mask"))):
        raise ValueError("invalid centerline array shapes")
    for name in ("node_world_xz_m", "original_world_xz_m", "node_bed_m", "node_width_m"):
        if arrays[name].dtype != np.float64 or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid centerline finite geometry")
    for name in ("node_flat_index", "edge_donor_flat_index", "edge_target_flat_index"):
        if arrays[name].dtype != np.int64:
            raise ValueError("invalid centerline index dtype")
    for name in ("anchor_mask", "slope_failed_donor_mask", "local_budget_failed_mask"):
        if arrays[name].dtype != bool:
            raise ValueError("invalid centerline mask dtype")
    nodes = arrays["node_flat_index"]
    if (not np.array_equal(nodes, np.unique(nodes)) or
            not set(arrays["edge_donor_flat_index"]).issubset(set(nodes)) or
            not set(arrays["edge_target_flat_index"]).issubset(set(nodes)) or
            np.any(arrays["node_width_m"] <= 0) or
            np.any(arrays["anchor_mask"] & np.any(
                arrays["node_world_xz_m"] != arrays["original_world_xz_m"], axis=1)) or
            np.any(np.linalg.norm(arrays["node_world_xz_m"] - arrays["original_world_xz_m"], axis=1) >
                   params["max_offset_m"] + 1e-9)):
        raise ValueError("invalid centerline topology or corridor")
    if (record["summary"]["nodes"] != node_count or record["summary"]["edges"] != edge_count or
            record["summary"]["slope_failed_edges"] != int(np.count_nonzero(arrays["slope_failed_donor_mask"])) or
            record["summary"]["local_budget_failed_nodes"] != int(np.count_nonzero(arrays["local_budget_failed_mask"]))):
        raise ValueError("centerline summary mismatch")
    for value in arrays.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": record["status"], "arrays": arrays, "summary": record["summary"]}


def validate_centerline_for_plan(centerline, plan):
    """Reject a centerline from another plan or with changed graph/geometry arrays."""
    identity = ArtifactIdentity(**centerline["identity"])
    if (identity.sha256 != centerline["identity_sha256"] or
            identity.algorithm != "channel-centerline" or
            centerline.get("status") != "diagnostic_not_publishable"):
        raise ValueError("invalid centerline identity")
    params = identity.record()["parameters"]
    if digest({name: array_hash(np.ascontiguousarray(value))
               for name, value in centerline["arrays"].items()}) != params["result_geometry_sha256"]:
        raise ValueError("centerline result differs from identity")
    arrays = plan["arrays"]
    geometry_hash = digest({name: array_hash(np.ascontiguousarray(arrays[name]))
                            for name in ("target_bed_m", "nominal_width_m", "channel_mask")})
    if (params["plan_identity_sha256"] != plan["identity_sha256"] or
            params["plan_geometry_sha256"] != geometry_hash):
        raise ValueError("centerline source plan mismatch")
    result = centerline["arrays"]
    nodes = result["node_flat_index"]
    expected_nodes = np.flatnonzero(arrays["channel_mask"].ravel())
    if nodes.dtype != np.int64 or not np.array_equal(nodes, expected_nodes):
        raise ValueError("centerline node set differs from plan")
    index = {int(cell): pos for pos, cell in enumerate(nodes)}
    expected_edges = [(int(cell), int(arrays["receiver"][cell])) for cell in nodes
                      if arrays["receiver"][cell] >= 0 and
                      arrays["channel_mask"].flat[arrays["receiver"][cell]]]
    edges = list(zip(result["edge_donor_flat_index"], result["edge_target_flat_index"]))
    if edges != expected_edges:
        raise ValueError("centerline edge set differs from plan")
    positions = result["node_world_xz_m"]
    if positions.shape != (len(nodes), 2) or not np.isfinite(positions).all():
        raise ValueError("invalid centerline positions")
    source = result["original_world_xz_m"]
    if source.shape != positions.shape or not np.isfinite(source).all():
        raise ValueError("invalid original positions")
    base = plan["identity"]["parameters"]
    cols = arrays["source_height_m"].shape[1]
    expected_source = np.column_stack((base["origin_x_m"] + nodes % cols * base["spacing_x_m"],
                                       base["origin_z_m"] + nodes // cols * base["spacing_z_m"]))
    if not np.array_equal(source, expected_source):
        raise ValueError("centerline original geometry differs from plan")
    donor_counts = np.zeros(arrays["source_height_m"].size, dtype=np.int32)
    for _, target in expected_edges:
        donor_counts[target] += 1
    expected_anchors = np.array([donor_counts[cell] != 1 or arrays["receiver"][cell] < 0
                                 for cell in nodes], dtype=bool)
    if not np.array_equal(result["anchor_mask"], expected_anchors):
        raise ValueError("centerline anchors differ from plan topology")
    for cell, pos in index.items():
        if (result["anchor_mask"][pos] and not np.array_equal(positions[pos], source[pos]) or
                np.linalg.norm(positions[pos] - source[pos]) > params["max_offset_m"] + 1e-9):
            raise ValueError("centerline anchor or corridor violation")
    if (not np.array_equal(result["node_bed_m"], arrays["target_bed_m"].ravel()[nodes]) or
            not np.array_equal(result["node_width_m"], arrays["nominal_width_m"].ravel()[nodes])):
        raise ValueError("centerline bed or width differs from plan")
    return True
