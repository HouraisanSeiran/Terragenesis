"""Bounded tiled export of one canonical shared valley bed.

The complete profile, source envelope, and monotone closure are solved before
cells are partitioned.  Tiles are an export representation; they never solve
an independent bed or move a source node.
"""

from dataclasses import asdict, dataclass
from types import SimpleNamespace
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_channel_geometry import GeometryConfig, _footprint, _mesh_volume, _sample, _route_crossings
from .metric_contracts import TerrainGrid
from .metric_monotone_union import _close_bed, _line_constraints
from .metric_valley_incision import _check_inputs, _metadata_terrain, _profile, _profile_cut
from .metric_valley_union import (
    _cut_source_constraints, _sparse_cells, _sparse_mesh, _sparse_ports, _sparse_slope,
)


SCHEMA = "terragenesis-tiled-shared-valley-union-v1"
ALGORITHM = "whole-component-profile-envelope-monotone-closure-tiled-v1"
MAX_BYTES = 128 * 1024 * 1024
MAX_GLOBAL_CELLS = 8_000_000


@dataclass(frozen=True)
class TileBudget:
    max_cells: int = 32768
    max_vertices: int = 262144
    max_bytes: int = MAX_BYTES

    def __post_init__(self):
        if (type(self.max_cells) is not int or self.max_cells < 1
                or type(self.max_vertices) is not int or self.max_vertices < 5
                or type(self.max_bytes) is not int or self.max_bytes < 1):
            raise ValueError("invalid tiled valley resource budget")
        if self.max_vertices > 262144 or self.max_bytes > MAX_BYTES:
            raise ValueError("tiled valley resource budget exceeds fixed limit")


def _large_config(config, spacing):
    """Duck-typed config for the sparse field helpers, with no global tile cap."""
    limit = min(MAX_GLOBAL_CELLS * 5, 40_000_000)
    return SimpleNamespace(fine_spacing_m=float(spacing), max_vertices=limit,
                           max_cut_m=float(config.max_cut_m))


def _expected_arrays():
    return {
        "source_height_m", "source_valid_mask", "owner_grid", "corridor_mask", "lake_mask",
        "source_node_cell_ids", "receiver", "node_xz_m", "width_m", "base_depth_m",
        "profile_offsets", "profile_t", "profile_source_m", "profile_center_bed_m",
        "global_cell_xy", "global_vertex_xz_m", "global_source_elevation_m",
        "global_source_cell_ids", "global_cut_depth_m", "global_bed_elevation_m",
        "global_triangles", "tile_offsets", "tile_vertex_offsets", "tile_triangle_offsets",
        "tile_cell_global_index", "tile_cell_xy", "tile_vertices_xz_m",
        "tile_source_elevation_m", "tile_source_cell_ids", "tile_cut_depth_m",
        "tile_bed_elevation_m", "tile_triangles", "port_edge_node_indices", "port_xz_m",
        "port_profile_xz_m", "port_triangle_ids", "port_barycentric", "port_cut_depth_m",
    }


def _tile_bytes(arrays, lo_cell, hi_cell, lo_vertex, hi_vertex, lo_tri, hi_tri):
    fields = (
        ("tile_cell_xy", lo_cell, hi_cell), ("tile_cell_global_index", lo_cell, hi_cell),
        ("tile_vertices_xz_m", lo_vertex, hi_vertex),
        ("tile_source_elevation_m", lo_vertex, hi_vertex),
        ("tile_source_cell_ids", lo_vertex, hi_vertex),
        ("tile_cut_depth_m", lo_vertex, hi_vertex),
        ("tile_bed_elevation_m", lo_vertex, hi_vertex),
        ("tile_triangles", lo_tri, hi_tri),
    )
    total = 0
    for name, low, high in fields:
        value = arrays.get(name)
        if value is None:
            continue
        total += int(value[low:high].nbytes)
    return total


def _tile_from_cells(cell_indices, global_arrays, tile_id, source_plan, budget):
    cells = global_arrays["global_cell_xy"][cell_indices]
    triangles = global_arrays["global_triangles"][np.concatenate(
        [np.arange(4 * index, 4 * index + 4, dtype=np.int64) for index in cell_indices])]
    vertex_ids = np.unique(triangles.reshape(-1))
    local_map = np.full(len(global_arrays["global_vertex_xz_m"]), -1, np.int64)
    local_map[vertex_ids] = np.arange(len(vertex_ids), dtype=np.int64)
    local_triangles = local_map[triangles]
    arrays = {
        "tile_cell_xy": cells.copy(), "tile_cell_global_index": cell_indices.copy(),
        "tile_vertices_xz_m": global_arrays["global_vertex_xz_m"][vertex_ids].copy(),
        "tile_source_elevation_m": global_arrays["global_source_elevation_m"][vertex_ids].copy(),
        "tile_source_cell_ids": global_arrays["global_source_cell_ids"][vertex_ids].copy(),
        "tile_cut_depth_m": global_arrays["global_cut_depth_m"][vertex_ids].copy(),
        "tile_bed_elevation_m": global_arrays["global_bed_elevation_m"][vertex_ids].copy(),
        "tile_triangles": local_triangles.copy(),
    }
    arrays = {key: readonly(value) for key, value in arrays.items()}
    tile_meta = {
        "schema": SCHEMA + ".tile", "algorithm": ALGORITHM, "tile_id": int(tile_id),
        "source_plan_identity_sha256": source_plan, "cell_count": int(len(cells)),
        "vertex_count": int(len(vertex_ids)), "triangle_count": int(len(local_triangles)),
        "global_cell_index_start": int(cell_indices[0]),
        "global_cell_index_stop": int(cell_indices[-1]) + 1,
        "byte_count": int(sum(value.nbytes for value in arrays.values())),
        "budget": asdict(budget),
    }
    if tile_meta["cell_count"] > budget.max_cells:
        raise ValueError("tiled valley cell budget exceeded")
    if tile_meta["vertex_count"] > budget.max_vertices:
        raise ValueError("tiled valley vertex budget exceeded")
    if tile_meta["byte_count"] > budget.max_bytes:
        raise ValueError("tiled valley byte budget exceeded")
    tile_meta["identity_sha256"] = identity(arrays, tile_meta)
    return arrays, tile_meta


def _partition(global_arrays, budget):
    cells = global_arrays["global_cell_xy"]
    total = len(cells)
    chunks = []
    start = 0
    while start < total:
        end = start
        corner_ids = set()
        while end < total:
            x, z = map(int, cells[end])
            candidate = corner_ids | {(x, z), (x + 1, z), (x + 1, z + 1), (x, z + 1)}
            candidate_vertices = len(candidate) + (end - start + 1)
            if end > start and (end - start + 1 > budget.max_cells
                                or candidate_vertices > budget.max_vertices):
                break
            corners = candidate
            if end - start + 1 > budget.max_cells or candidate_vertices > budget.max_vertices:
                raise ValueError("single tiled valley cell exceeds resource budget")
            end += 1
            corner_ids = corners
        chunks.append(np.arange(start, end, dtype=np.int64))
        start = end
    return chunks


def _prepare_field(terrain, node_cell_ids, receiver, width_m, base_depth_m,
                   owner_grid, corridor_mask, lake_mask, config, spacing):
    local = _large_config(config, spacing)
    cols = terrain.elevation_m.shape[1]
    points = np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m,
                              terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, base_depth_m, terrain, local.max_cut_m)
    _footprint(points, receiver, width_m, np.full(len(points), local.max_cut_m), terrain,
               owner_grid, corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids], spacing)
    from .metric_valley_incision import _profile_overlap
    _profile_overlap(points, receiver, width_m, profile, terrain)
    cells = _sparse_cells(points, receiver, width_m, profile, local, terrain)
    if len(cells) > MAX_GLOBAL_CELLS:
        raise ValueError("whole-component shared field exceeds global cell budget")
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, local.max_vertices)
    source, source_cells = _sample(terrain.elevation_m, vertices, terrain)
    base_cut = _profile_cut(points, receiver, width_m, profile, vertices, terrain, lake_mask)
    return local, points, profile, cells, vertices, triangles, source, source_cells, base_cut


def _build_field(terrain, node_cell_ids, receiver, width_m, base_depth_m,
                 owner_grid, corridor_mask, lake_mask, source_plan, config, spacing):
    local, points, profile, cells, vertices, triangles, source, source_cells, base_cut = _prepare_field(
        terrain, node_cell_ids, receiver, width_m, base_depth_m, owner_grid,
        corridor_mask, lake_mask, config, spacing)
    cut, closure = _close_bed(points, receiver, cells, vertices, triangles, source,
                               original_cut=base_cut, terrain=terrain, spacing=spacing,
                               max_cut_m=local.max_cut_m)
    _cut_source_constraints(vertices, source_cells, cut, terrain, owner_grid,
                            corridor_mask, lake_mask, owner_grid.ravel()[node_cell_ids[0]])
    _sparse_slope(points, receiver, cells, vertices, triangles, source - cut, spacing, terrain)
    ports = _sparse_ports(points, receiver, width_m, profile, cells, vertices, triangles,
                          cut, spacing, terrain)
    return profile, cells, vertices, triangles, source, source_cells, base_cut, cut, closure, ports


def build_tiled_monotone_union(terrain, node_cell_ids, receiver, width_m, base_depth_m, *,
                               owner_grid, corridor_mask, lake_mask,
                               source_plan_identity_sha256, config=None, budget=None):
    """Build one shared field, then export deterministic bounded tiles."""
    config = config or GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0)
    budget = budget or TileBudget()
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m,
                  owner_grid, corridor_mask, lake_mask, config)
    if (not isinstance(source_plan_identity_sha256, str)
            or len(source_plan_identity_sha256) != 64
            or any(c not in "0123456789abcdef" for c in source_plan_identity_sha256)):
        raise ValueError("source network plan identity required")
    if np.unique(owner_grid.ravel()[node_cell_ids]).size != 1:
        raise ValueError("shared component spans original source owners")
    result = _build_field(terrain, np.asarray(node_cell_ids, np.int64),
                          np.asarray(receiver, np.int64), np.asarray(width_m, np.float64),
                          np.asarray(base_depth_m, np.float64), owner_grid, corridor_mask,
                          lake_mask, source_plan_identity_sha256, config, config.fine_spacing_m)
    profile, cells, vertices, triangles, source, source_cells, base_cut, cut, closure, ports = result
    global_arrays = {
        "global_cell_xy": cells, "global_vertex_xz_m": vertices,
        "global_source_elevation_m": source, "global_source_cell_ids": source_cells,
        "global_cut_depth_m": cut, "global_bed_elevation_m": source - cut,
        "global_triangles": triangles,
    }
    chunks = _partition(global_arrays, budget)
    tile_arrays, tile_records = [], []
    for tile_id, chunk in enumerate(chunks):
        arrays, record = _tile_from_cells(chunk, global_arrays, tile_id,
                                           source_plan_identity_sha256, budget)
        tile_arrays.append(arrays)
        tile_records.append(record)
    cat = {}
    for key in tile_arrays[0]:
        cat[key] = readonly(np.concatenate([part[key] for part in tile_arrays], axis=0))
    cell_offsets = np.cumsum([0] + [record["cell_count"] for record in tile_records], dtype=np.int64)
    vertex_offsets = np.cumsum([0] + [record["vertex_count"] for record in tile_records], dtype=np.int64)
    tri_offsets = np.cumsum([0] + [record["triangle_count"] for record in tile_records], dtype=np.int64)
    arrays = {
        "source_height_m": readonly(np.asarray(terrain.elevation_m, np.float64)),
        "source_valid_mask": readonly(np.asarray(terrain.valid_mask, bool)),
        "owner_grid": readonly(np.asarray(owner_grid, np.int64)),
        "corridor_mask": readonly(np.asarray(corridor_mask, bool)),
        "lake_mask": readonly(np.asarray(lake_mask, bool)),
        "source_node_cell_ids": readonly(np.asarray(node_cell_ids, np.int64)),
        "receiver": readonly(np.asarray(receiver, np.int64)),
        "node_xz_m": readonly(np.column_stack((terrain.x0_m + node_cell_ids % terrain.elevation_m.shape[1] * terrain.dx_m,
                                                terrain.z0_m + node_cell_ids // terrain.elevation_m.shape[1] * terrain.dz_m))),
        "width_m": readonly(np.asarray(width_m, np.float64)),
        "base_depth_m": readonly(np.asarray(base_depth_m, np.float64)),
        "profile_offsets": readonly(profile[0]), "profile_t": readonly(profile[1]),
        "profile_source_m": readonly(profile[2]), "profile_center_bed_m": readonly(profile[3]),
        **{key: readonly(value) for key, value in global_arrays.items()},
        "tile_offsets": cell_offsets, "tile_vertex_offsets": vertex_offsets,
        "tile_triangle_offsets": tri_offsets, **cat,
        "port_edge_node_indices": readonly(ports[0]), "port_xz_m": readonly(ports[1]),
        "port_profile_xz_m": readonly(ports[2]), "port_triangle_ids": readonly(ports[3]),
        "port_barycentric": readonly(ports[4]), "port_cut_depth_m": readonly(ports[5]),
    }
    metadata = {
        "schema": SCHEMA, "algorithm": ALGORITHM,
        "terrain_metadata": _metadata_terrain(terrain),
        "source_identity_sha256": terrain.identity_sha256,
        "source_plan_identity_sha256": source_plan_identity_sha256,
        "config": asdict(config), "budget": asdict(budget), "closure": closure,
        "base_cut_volume_m3": _mesh_volume(vertices, triangles, base_cut),
        "cut_volume_m3": _mesh_volume(vertices, triangles, cut),
        "tile_records": tile_records, "tile_count": len(tile_records),
        "rejections": [], "budget_refusals": [], "unresolved_coverage": [],
        "global_cell_count": len(cells), "global_vertex_count": len(vertices),
        "cross_tile_centerline_validated": True, "global_unique_cell_ownership": True,
        "spatial_refinement_relative": None, "hydraulic_ready": False,
        "natural_outlet_verified": False, "publishable": False,
    }
    bundle = {"arrays": arrays, "metadata": metadata,
              "identity_sha256": identity(arrays, metadata)}
    validate_tiled_monotone_union(bundle)
    return bundle


def build_tiled_refinement_pair(*args, **kwargs):
    """Build .5/.25 shared fields and apply the unchanged two percent gate."""
    base_config = kwargs.pop("config", None) or GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0)
    coarse_config = GeometryConfig(**{**asdict(base_config), "fine_spacing_m": .5})
    fine_config = GeometryConfig(**{**asdict(base_config), "fine_spacing_m": .25})
    coarse = build_tiled_monotone_union(*args, config=coarse_config, **kwargs)
    fine = build_tiled_monotone_union(*args, config=fine_config, **kwargs)
    relative = abs(coarse["metadata"]["cut_volume_m3"] - fine["metadata"]["cut_volume_m3"])
    relative /= max(fine["metadata"]["cut_volume_m3"], 1e-12)
    if relative > .02:
        raise ValueError("tiled shared-field spatial refinement exceeds fixed 2% gate")
    coarse["metadata"]["spatial_refinement_relative"] = float(relative)
    fine["metadata"]["spatial_refinement_relative"] = float(relative)
    coarse["identity_sha256"] = identity(coarse["arrays"], coarse["metadata"])
    fine["identity_sha256"] = identity(fine["arrays"], fine["metadata"])
    return {"coarse": coarse, "fine": fine, "spatial_refinement_relative": float(relative)}


def _check_tile(bundle, index):
    a, m = bundle["arrays"], bundle["metadata"]
    rec = m["tile_records"][index]
    expected_record = {"schema", "algorithm", "tile_id", "source_plan_identity_sha256",
                       "cell_count", "vertex_count", "triangle_count", "global_cell_index_start",
                       "global_cell_index_stop", "byte_count", "budget", "identity_sha256"}
    if set(rec) != expected_record or rec["source_plan_identity_sha256"] != m["source_plan_identity_sha256"]:
        raise ValueError("tiled valley tile manifest mismatch")
    c0, c1 = map(int, a["tile_offsets"][index:index + 2])
    v0, v1 = map(int, a["tile_vertex_offsets"][index:index + 2])
    t0, t1 = map(int, a["tile_triangle_offsets"][index:index + 2])
    arrays = {key: readonly(a[key][low:high]) for key, low, high in (
        ("tile_cell_xy", c0, c1), ("tile_cell_global_index", c0, c1),
        ("tile_vertices_xz_m", v0, v1), ("tile_source_elevation_m", v0, v1),
        ("tile_source_cell_ids", v0, v1), ("tile_cut_depth_m", v0, v1),
        ("tile_bed_elevation_m", v0, v1), ("tile_triangles", t0, t1))}
    if rec["identity_sha256"] != identity(arrays, {key: rec[key] for key in (
            "schema", "algorithm", "tile_id", "source_plan_identity_sha256", "cell_count",
            "vertex_count", "triangle_count", "global_cell_index_start",
            "global_cell_index_stop", "byte_count", "budget")}):
        raise ValueError("tiled valley tile identity mismatch")
    if rec["byte_count"] != sum(value.nbytes for value in arrays.values()):
        raise ValueError("tiled valley tile byte ledger mismatch")
    if rec["byte_count"] > int(m["budget"]["max_bytes"]):
        raise ValueError("tiled valley tile byte budget mismatch")
    return c0, c1, v0, v1, t0, t1, arrays, rec


def validate_tiled_monotone_union(bundle):
    """Cold validator. It recomputes profiles, source/cut envelopes and PL guards."""
    if (not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}
            or bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"])):
        raise ValueError("tiled valley identity mismatch")
    a, m = bundle["arrays"], bundle["metadata"]
    expected_meta = {"schema", "algorithm", "terrain_metadata", "source_identity_sha256",
                     "source_plan_identity_sha256", "config", "budget", "closure",
                     "base_cut_volume_m3", "cut_volume_m3", "tile_records", "tile_count",
                     "rejections", "budget_refusals", "unresolved_coverage", "global_cell_count",
                     "global_vertex_count", "cross_tile_centerline_validated",
                     "global_unique_cell_ownership", "spatial_refinement_relative",
                     "hydraulic_ready", "natural_outlet_verified", "publishable"}
    if (set(a) != _expected_arrays() or set(m) != expected_meta
            or m.get("schema") != SCHEMA or m.get("algorithm") != ALGORITHM):
        raise ValueError("tiled valley schema mismatch")
    if not (1 <= int(m["tile_count"]) == len(m["tile_records"])):
        raise ValueError("tiled valley tile manifest mismatch")
    terrain = TerrainGrid(a["source_height_m"], a["source_valid_mask"], **m["terrain_metadata"])
    if terrain.identity_sha256 != m["source_identity_sha256"]:
        raise ValueError("tiled valley source identity mismatch")
    config = GeometryConfig(**m["config"])
    budget = TileBudget(**m["budget"])
    source_plan = m["source_plan_identity_sha256"]
    if (not isinstance(source_plan, str) or len(source_plan) != 64
            or any(char not in "0123456789abcdef" for char in source_plan)
            or m["cross_tile_centerline_validated"] is not True
            or m["global_unique_cell_ownership"] is not True
            or any(m[key] is not False for key in ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or m["rejections"] != [] or m["budget_refusals"] != []
            or m["unresolved_coverage"] != []):
        raise ValueError("tiled valley scope or refusal ledger mismatch")
    ids, receiver, width, depth = (a[key] for key in (
        "source_node_cell_ids", "receiver", "width_m", "base_depth_m"))
    float_fields = {"source_height_m", "node_xz_m", "width_m", "base_depth_m", "profile_t",
                    "profile_source_m", "profile_center_bed_m", "global_vertex_xz_m",
                    "global_source_elevation_m", "global_cut_depth_m", "global_bed_elevation_m",
                    "tile_vertices_xz_m", "tile_source_elevation_m", "tile_cut_depth_m",
                    "tile_bed_elevation_m", "port_xz_m", "port_profile_xz_m",
                    "port_barycentric", "port_cut_depth_m"}
    int_fields = {"owner_grid", "source_node_cell_ids", "receiver", "profile_offsets",
                  "global_cell_xy", "global_source_cell_ids", "global_triangles", "tile_offsets",
                  "tile_vertex_offsets", "tile_triangle_offsets", "tile_cell_global_index",
                  "tile_cell_xy", "tile_source_cell_ids", "tile_triangles", "port_edge_node_indices",
                  "port_triangle_ids"}
    bool_fields = {"source_valid_mask", "corridor_mask", "lake_mask"}
    if (any(a[key].dtype != np.float64 for key in float_fields)
            or any(a[key].dtype != np.int64 for key in int_fields)
            or any(a[key].dtype != bool for key in bool_fields)):
        raise ValueError("tiled valley array dtype mismatch")
    _check_inputs(terrain, ids, receiver, width, depth, a["owner_grid"],
                  a["corridor_mask"], a["lake_mask"], config)
    if np.unique(a["owner_grid"].ravel()[ids]).size != 1:
        raise ValueError("tiled valley component spans source owners")
    _, points, profile, cells, vertices, triangles, source, source_cells, base_cut = _prepare_field(
        terrain, ids, receiver, width, depth, a["owner_grid"], a["corridor_mask"],
        a["lake_mask"], config, config.fine_spacing_m)
    if not np.array_equal(a["node_xz_m"], points):
        raise ValueError("tiled valley fixed source node mismatch")
    cut = a["global_cut_depth_m"]
    _cut_source_constraints(vertices, source_cells, cut, terrain, a["owner_grid"],
                            a["corridor_mask"], a["lake_mask"], a["owner_grid"].ravel()[ids[0]])
    _sparse_slope(np.asarray(a["node_xz_m"]), receiver, cells, vertices, triangles,
                  source - cut, config.fine_spacing_m, terrain)
    ports = _sparse_ports(np.asarray(a["node_xz_m"]), receiver, width, profile,
                          cells, vertices, triangles, cut, config.fine_spacing_m, terrain)
    for key, value in (("global_cell_xy", cells), ("global_vertex_xz_m", vertices),
                       ("global_source_elevation_m", source), ("global_source_cell_ids", source_cells),
                       ("global_cut_depth_m", cut), ("global_bed_elevation_m", source - cut),
                       ("global_triangles", triangles)):
        if not np.array_equal(a[key], value):
            raise ValueError("tiled valley global field mismatch: " + key)
    for key, value in zip(("profile_offsets", "profile_t", "profile_source_m", "profile_center_bed_m"), profile):
        if not np.array_equal(a[key], value):
            raise ValueError("tiled valley profile mismatch")
    for key, value in zip(("port_edge_node_indices", "port_xz_m", "port_profile_xz_m",
                           "port_triangle_ids", "port_barycentric", "port_cut_depth_m"), ports):
        if not np.allclose(a[key], value, rtol=0., atol=1e-9):
            raise ValueError("tiled valley port mismatch")
    if np.any(cut < base_cut - 1e-9) or np.any(cut > config.max_cut_m + 1e-8):
        raise ValueError("tiled valley cut envelope mismatch")
    closure = m["closure"]
    extra = cut - base_cut
    if (set(closure) != {"extra_cut_vertices", "extra_cut_sum_m",
                         "maximum_constraint_residual_m", "centerline_segments"}
            or closure["extra_cut_vertices"] != int(np.count_nonzero(extra > 1e-9))
            or not math.isclose(closure["extra_cut_sum_m"], float(np.sum(extra)), abs_tol=1e-8)):
        raise ValueError("tiled valley closure ledger mismatch")
    segments = _line_constraints(np.asarray(a["node_xz_m"]), receiver, cells, vertices,
                                 triangles, terrain, config.fine_spacing_m)
    if closure["centerline_segments"] != len(segments):
        raise ValueError("tiled valley centerline ledger mismatch")
    bed = source - cut
    residuals = []
    for start, end, dt, _, _ in segments:
        h0 = float(start[1] @ bed[start[0]])
        h1 = float(end[1] @ bed[end[0]])
        residuals.append(h1 - h0 + 1e-7 * dt)
    residual = float(max(residuals, default=0.))
    if (not math.isfinite(residual)
            or residual > 1e-7
            or not math.isclose(closure["maximum_constraint_residual_m"], residual, abs_tol=1e-7)):
        raise ValueError("tiled valley monotone closure residual mismatch")
    if not math.isclose(m["cut_volume_m3"], _mesh_volume(vertices, triangles, cut),
                        rel_tol=1e-10, abs_tol=1e-7):
        raise ValueError("tiled valley volume ledger mismatch")
    if (m["global_cell_count"] != len(cells) or m["global_vertex_count"] != len(vertices)
            or int(a["tile_offsets"][-1]) != len(cells) or int(a["tile_vertex_offsets"][-1]) != sum(
            record["vertex_count"] for record in m["tile_records"])
            or int(a["tile_triangle_offsets"][-1]) != sum(
            record["triangle_count"] for record in m["tile_records"])):
        raise ValueError("tiled valley offset ledger mismatch")
    if (not math.isclose(m["base_cut_volume_m3"], _mesh_volume(vertices, triangles, base_cut),
                         rel_tol=1e-10, abs_tol=1e-7)):
        raise ValueError("tiled valley base material ledger mismatch")
    seen = []
    for index in range(m["tile_count"]):
        c0, c1, v0, v1, t0, t1, ta, rec = _check_tile(bundle, index)
        if (rec["tile_id"] != index or rec["cell_count"] != c1 - c0
                or rec["vertex_count"] != v1 - v0 or rec["triangle_count"] != t1 - t0
                or rec["global_cell_index_start"] != c0
                or rec["global_cell_index_stop"] != c1):
            raise ValueError("tiled valley tile shape mismatch")
        if rec["cell_count"] > budget.max_cells or rec["vertex_count"] > budget.max_vertices:
            raise ValueError("tiled valley tile budget mismatch")
        if np.any(ta["tile_triangles"] < 0) or np.any(ta["tile_triangles"] >= rec["vertex_count"]):
            raise ValueError("tiled valley local triangle range mismatch")
        global_ids = ta["tile_cell_global_index"]
        if not np.array_equal(ta["tile_cell_xy"], cells[global_ids]):
            raise ValueError("tiled valley tile cell mismatch")
        expected_ids = np.unique(triangles[np.concatenate(
            [np.arange(4 * int(value), 4 * int(value) + 4, dtype=np.int64) for value in global_ids])])
        if not np.array_equal(ta["tile_vertices_xz_m"], vertices[expected_ids]):
            raise ValueError("tiled valley shared corner mismatch")
        seen.extend(global_ids.tolist())
    if not np.array_equal(np.asarray(seen, np.int64), np.arange(len(cells), dtype=np.int64)):
        raise ValueError("tiled valley global cell ownership is not unique")
    return True


def save_tiled_monotone_union(path, bundle):
    save_bundle(path, bundle, validator=validate_tiled_monotone_union)


def load_tiled_monotone_union(path, *, expected_sha256, expected_identity):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_tiled_monotone_union, max_bytes=MAX_BYTES * 4)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external tiled valley identity mismatch")
    return bundle


# Short aliases used by verification tools.
build_tiled_shared_field = build_tiled_monotone_union
validate_tiled_shared_field = validate_tiled_monotone_union
save_tiled_shared_field = save_tiled_monotone_union
load_tiled_shared_field = load_tiled_monotone_union
