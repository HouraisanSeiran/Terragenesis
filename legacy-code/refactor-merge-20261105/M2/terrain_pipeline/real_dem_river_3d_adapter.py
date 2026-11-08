"""Illustrative shared-bank bed ribbons, not observed channels or water bodies."""

import numpy as np

from terrain_pipeline.artifacts.contracts import array_hash, canonical_json, digest, finite_number
from terrain_pipeline.drainage import validate_flat_routing as validate_flat_routing
from terrain_pipeline.drainage import arrays_from_candidate as _arrays
from terrain_pipeline.drainage import require_positive_integer as _positive_integer


ALGORITHM = "real-dem-shared-bank-illustrative-bed-ribbon-v1"
MAX_BYTES = 512 * 1024 * 1024
ARRAY_NAMES = {"node_ids", "node_xyz", "edge_ids", "edges", "donor_count", "heads", "junctions",
               "terminals", "component_id", "touches_boundary", "touches_unknown", "cross_sections",
               "vertices", "faces", "degenerate_face_ids"}


def _context(candidate, flat_result, threshold, width, depth, tile_size):
    _positive_integer(tile_size, "tile_size", 1024)
    threshold = finite_number(threshold, "min_contributing_cells", positive=True)
    width = finite_number(width, "width_m", positive=True)
    depth = finite_number(depth, "depth_m", positive=True)
    if width > 1e6 or depth > 1e6 or threshold > 500000:
        raise ValueError("geometry parameters exceed resource/range budget")
    height, valid = _arrays(candidate)
    validate_flat_routing(candidate, flat_result)
    identity = candidate.get("manifest", {}).get("identity", {})
    grid = identity.get("grid", candidate.get("grid"))
    if not isinstance(grid, dict):
        raise ValueError("explicit projected metric grid required")
    if not identity and (grid.get("crs") != "EPSG:32651" or grid.get("units") != "metres"):
        raise ValueError("fixture grid must declare EPSG:32651 metres")
    for name in ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m"):
        finite_number(grid.get(name), name, positive=name.startswith("spacing"))
    source = {"candidate_content_sha256": candidate.get("manifest", {}).get("content_sha256"),
              "height_sha256": array_hash(height), "valid_mask_sha256": array_hash(valid),
              "flat_graph_sha256": digest({name: array_hash(getattr(flat_result["network"], name)) for name in
                                           ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal")}),
              "flat_components_sha256": digest(flat_result["components"]), "grid": dict(grid)}
    return height, valid, grid, threshold, width, depth, source


def _topology(height, valid, grid, flat, threshold):
    network = flat["network"]
    ids = np.flatnonzero(valid.ravel() & (network.accumulation_cells.ravel() >= threshold))
    receiver = network.receiver.ravel()[ids]
    routed = receiver >= 0
    targets = receiver[routed]
    if not np.isin(targets, ids).all():
        raise ValueError("selected graph lacks downstream closure")
    edges = np.column_stack((ids[routed], targets)).astype(np.int64)
    row, col = np.divmod(ids, height.shape[1])
    xyz = np.column_stack((grid["origin_x_m"] + col * grid["spacing_x_m"], height.ravel()[ids],
                           grid["origin_z_m"] + row * grid["spacing_z_m"]))
    if not np.isfinite(xyz).all():
        raise ValueError("nonfinite projected node coordinates")
    donors = np.bincount(np.searchsorted(ids, targets), minlength=len(ids)).astype(np.int64)
    component = flat["component_id"].ravel()[ids]
    records = {item["component_id"]: item for item in flat["components"]}
    return {"node_ids": ids, "node_xyz": xyz, "edge_ids": ids[routed].copy(), "edges": edges,
            "donor_count": donors, "heads": donors == 0, "junctions": donors > 1, "terminals": ~routed,
            "component_id": component.copy(),
            "touches_boundary": np.array([records[int(value)]["touches_boundary"] for value in component], bool),
            "touches_unknown": np.array([records[int(value)]["touches_unknown"] for value in component], bool)}


def _banks(topology, width, depth):
    ids, xyz, edges = topology["node_ids"], topology["node_xyz"], topology["edges"]
    source = np.searchsorted(ids, edges[:, 0])
    target = np.searchsorted(ids, edges[:, 1])
    delta = xyz[target][:, [0, 2]] - xyz[source][:, [0, 2]]
    lengths = np.linalg.norm(delta, axis=1)
    if np.any(lengths <= 0) or not np.isfinite(lengths).all():
        raise ValueError("zero/nonfinite horizontal edge length")
    direction = delta / lengths[:, None]
    tangent = np.zeros((len(ids), 2))
    np.add.at(tangent, target, direction)
    tangent[source] = direction
    magnitude = np.linalg.norm(tangent, axis=1)
    fallback = magnitude <= 1e-12
    tangent[fallback] = [1., 0.]
    tangent[~fallback] /= magnitude[~fallback, None]
    normal = np.column_stack((-tangent[:, 1], tangent[:, 0]))
    vertices = np.repeat(xyz, 2, axis=0)
    vertices[:, 1] -= depth
    vertices[0::2, 0] += normal[:, 0] * width / 2
    vertices[0::2, 2] += normal[:, 1] * width / 2
    vertices[1::2, 0] -= normal[:, 0] * width / 2
    vertices[1::2, 2] -= normal[:, 1] * width / 2
    if not np.isfinite(vertices).all():
        raise ValueError("nonfinite bank vertices")
    faces = np.empty((2 * len(edges), 3), np.int64)
    faces[0::2] = np.column_stack((2 * source, 2 * source + 1, 2 * target))
    faces[1::2] = np.column_stack((2 * source + 1, 2 * target + 1, 2 * target))
    triangles = vertices[faces]
    double_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    bad = np.flatnonzero(double_area <= 1e-10)
    profile = np.tile(np.array([width, depth, width * depth]), (len(ids), 1))
    return profile, vertices, faces, bad, int(fallback.sum())


def _metadata(source, threshold, width, depth, topology, bad, fallback):
    return {"algorithm": ALGORITHM, "source": source,
            "parameters": {"min_contributing_cells": threshold, "width_m": width, "depth_m": depth},
            "coordinates": "X=easting_m; Y=raw_DEM_height_m; Z=-northing_m; pixel_centers",
            "cross_section_columns": ["illustrative_width_m", "illustrative_depth_m", "illustrative_area_m2"],
            "bed_elevation": "raw_DEM_height_minus_explicit_illustrative_depth_not_observed_channel",
            "node_id": "global_cell_id", "edge_id": "donor_global_cell_id", "banks": "two_shared_vertices_per_node",
            "tangent": "downstream_unit_direction_else_mean_upstream_unit_direction_else_positive_X",
            "status": "topology_sections_only_mesh_degenerate" if len(bad) else "illustrative_shared_bank_ribbon_prototype",
            "mesh_accepted": not bool(len(bad)), "degenerate_face_count": len(bad),
            "tangent_fallback_node_count": fallback,
            "junction_count": int(topology["junctions"].sum()),
            "junction_mesh": "shared_banks_but_sharp_overlapping_nonmanifold_junctions_not_hydraulic_ready",
            "intersection_check": "not_performed_crossings_possible",
            "limitations": "90m_DEM_does_not_resolve_real_fine_channels; no_water_surface_ocean_or_Minecraft",
            "engineering_parameters": True, "source_height_unchanged": True,
            "hydraulic_ready": False, "continuous_water_body_verified": False,
            "natural_outlet_verified": False, "ocean_outlet_certified": False, "publishable": False}


def _seal(result):
    result["array_hashes"] = {name: array_hash(result[name]) for name in sorted(ARRAY_NAMES)}
    result["metadata_sha256"] = digest(result["metadata"])
    result["content_sha256"] = digest({"array_hashes": result["array_hashes"], "metadata_sha256": result["metadata_sha256"]})


def build_river_geometry(candidate, flat_result, *, min_contributing_cells=100, width_m=20., depth_m=1., tile_size=256) -> dict:
    height, valid, grid, threshold, width, depth, source = _context(
        candidate, flat_result, min_contributing_cells, width_m, depth_m, tile_size)
    result = _topology(height, valid, grid, flat_result, threshold)
    if len(result["node_ids"]) * 300 > MAX_BYTES:
        raise ValueError("geometry retained array resource budget exceeded")
    profile, vertices, faces, bad, fallback = _banks(result, width, depth)
    result.update(cross_sections=profile, vertices=vertices, faces=faces, degenerate_face_ids=bad)
    result["metadata"] = _metadata(source, threshold, width, depth, result, bad, fallback)
    if array_hash(height) != source["height_sha256"]:
        raise ValueError("source height changed")
    _seal(result)
    return result


def validate_river_geometry(candidate, flat_result, result) -> dict:
    """Audit source topology, coordinates, shared cross-sections and mesh faces."""
    if not isinstance(result, dict) or set(result) != ARRAY_NAMES | {"metadata", "array_hashes", "metadata_sha256", "content_sha256"}:
        raise ValueError("invalid geometry schema")
    try:
        parameters = result["metadata"]["parameters"]
        height, valid, grid, threshold, width, depth, source = _context(candidate, flat_result,
            parameters["min_contributing_cells"], parameters["width_m"], parameters["depth_m"], 256)
    except (KeyError, TypeError) as error:
        raise ValueError("invalid geometry metadata") from error
    topology = _topology(height, valid, grid, flat_result, threshold)
    for name, expected in topology.items():
        actual = result[name]
        if (not isinstance(actual, np.ndarray) or actual.dtype != expected.dtype or actual.shape != expected.shape
                or not np.array_equal(actual, expected)):
            raise ValueError(f"geometry topology/coordinate/class/risk mismatch: {name}")
    ids, xyz, edges = result["node_ids"], result["node_xyz"], result["edges"]
    if not np.isfinite(xyz).all():
        raise ValueError("nonfinite node coordinates")
    if len(edges) and np.any(xyz[np.searchsorted(ids, edges[:, 1]), 1] > xyz[np.searchsorted(ids, edges[:, 0]), 1]):
        raise ValueError("reference edge uphill")
    profile, vertices, faces, bad, fallback = _banks(topology, width, depth)
    for name, expected in (("cross_sections", profile), ("vertices", vertices), ("faces", faces), ("degenerate_face_ids", bad)):
        actual = result[name]
        if (not isinstance(actual, np.ndarray) or actual.dtype != expected.dtype or actual.shape != expected.shape
                or not np.isfinite(actual).all() or not np.array_equal(actual, expected)):
            raise ValueError(f"geometry section/shared mesh mismatch: {name}")
    if np.any(faces < 0) or np.any(faces >= len(vertices)) or sum(result[name].nbytes for name in ARRAY_NAMES) > MAX_BYTES:
        raise ValueError("face indices/resource budget mismatch")
    expected_metadata = _metadata(source, threshold, width, depth, topology, bad, fallback)
    if canonical_json(result["metadata"]) != canonical_json(expected_metadata):
        raise ValueError("geometry metadata source/claims mismatch")
    hashes = {name: array_hash(result[name]) for name in sorted(ARRAY_NAMES)}
    metadata_hash = digest(expected_metadata)
    if (result["array_hashes"] != hashes or result["metadata_sha256"] != metadata_hash
            or result["content_sha256"] != digest({"array_hashes": hashes, "metadata_sha256": metadata_hash})):
        raise ValueError("geometry hash mismatch")
    return {"verified": True, "mesh_accepted": not bool(len(bad)), "node_count": len(ids), "edge_count": len(edges),
            "degenerate_face_count": len(bad), "hydraulic_ready": False, "publishable": False,
            "natural_outlet_verified": False, "ocean_outlet_certified": False}
