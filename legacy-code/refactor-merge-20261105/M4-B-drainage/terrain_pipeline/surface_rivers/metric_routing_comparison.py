"""Independent diagnostic routing policies with replayable cold geometry checks."""

from collections import deque
import heapq
import math

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle

from terrain_pipeline.common_infra import BoundaryGrid, RoutingGraph, TerrainGrid
from .metric_drainage import diagnostic_mesh, route_diagnostic, unknown_contacts
from terrain_pipeline.irregular_grid import receiver_edges_valid


SCHEMA = "terragenesis-metric-routing-comparison-v2"
POLICIES = ("original_bed_irregular", "priority_flood_irregular", "metric_flat_irregular")
KINDS = ("interior", "inactive", "open_outflow", "closed_wall", "prescribed_stage",
         "prescribed_discharge", "unknown_boundary", "lake_preserved")
_CODES = {name: index for index, name in enumerate(KINDS)}
_KNOWN_OUTLETS = ("open_outflow", "prescribed_stage", "prescribed_discharge")
_EXPLICIT = _KNOWN_OUTLETS + ("unknown_boundary",)
def _neighbors(cell, mesh):
    for edge in range(mesh.indptr[cell], mesh.indptr[cell + 1]):
        yield int(mesh.indices[edge]), float(mesh.edge_length_m[edge])


def route_priority_flood(terrain: TerrainGrid, boundary: BoundaryGrid) -> dict:
    """Fill only a working surface toward known outlets, then diagnose its irregular graph."""
    original = route_diagnostic(terrain, boundary)
    mesh = diagnostic_mesh(terrain)
    raw = terrain.elevation_m
    valid = terrain.valid_mask
    working = raw.copy()
    visited = np.zeros(valid.size, bool)
    unknown_catchment = np.zeros(valid.size, bool)
    for cell in original.order_downstream_first:
        target = original.receiver[cell]
        unknown_catchment[cell] = (original.outlet_kind[cell] == "unknown_boundary"
                                   if target < 0 else unknown_catchment[target])
    heap = []
    for cell in np.flatnonzero(valid.ravel() & np.isin(boundary.kind.ravel(), _KNOWN_OUTLETS)):
        visited[cell] = True
        heapq.heappush(heap, (float(raw.ravel()[cell]), int(cell)))
    flat = working.ravel()
    while heap:
        level, cell = heapq.heappop(heap)
        for target, _ in _neighbors(cell, mesh):
            if visited[target] or unknown_catchment[target]:
                continue
            visited[target] = True
            flat[target] = max(float(flat[target]), level)
            heapq.heappush(heap, (float(flat[target]), target))
    # Unvisited components lack a known exit. Their original beds remain intact.
    revised = TerrainGrid(working, valid, **{name: getattr(terrain, name)
                           for name in TerrainGrid.__dataclass_fields__
                           if name not in ("elevation_m", "valid_mask")})
    graph = route_diagnostic(revised, boundary)
    graph = RoutingGraph(graph.receiver, graph.order_downstream_first, graph.valid_mask,
                         graph.edge_length_m, graph.edge_slope, graph.outlet_kind, graph.lake_id,
                         terrain.identity_sha256, boundary.identity_sha256,
                         policy="priority_flood_working_bed_irregular_v2")
    fill = working - raw
    return {"working_elevation_m": readonly(working), "fill_depth_m": readonly(fill),
            "flood_reached_mask": readonly(visited.reshape(valid.shape)),
            "unknown_catchment_excluded_mask": readonly(unknown_catchment.reshape(valid.shape)),
            "graph": graph,
            "metadata": {"policy": graph.policy,
                         "original_bed_graph_identity_sha256": original.identity_sha256,
                         "terrain_identity_sha256": terrain.identity_sha256,
                         "boundary_identity_sha256": boundary.identity_sha256,
                         "flood_reached_valid_cells": int(visited.sum()),
                         "unreached_valid_cells": int(valid.sum() - visited.sum()),
                         "unknown_catchment_excluded_cells": int(unknown_catchment.sum()),
                         "unknown_catchment_policy": "preserve_original_bed_and_exclude_from_known_outlet_flood",
                         "filled_cell_count": int(np.count_nonzero(fill > 0.)),
                         "maximum_fill_m": float(fill.max()),
                         "filled_volume_m3": float(np.sum(fill[valid], dtype=np.float64)
                                                   * terrain.cell_area_m2),
                         "work_surface_only": True, "natural_outlet_verified": False}}


def _route_metric_flat(terrain, boundary):
    """Original bed with metric shortest-path plateau routing on the same graph."""
    return route_diagnostic(terrain, boundary, flat_distance_strategy="metric_distance")

def _encode(kinds):
    if not np.isin(kinds, KINDS).all():
        raise ValueError("unsupported boundary or outlet kind")
    return np.fromiter((_CODES[str(value)] for value in kinds.ravel()),
                       dtype=np.uint8, count=kinds.size).reshape(kinds.shape)


def _decode(codes):
    if codes.dtype != np.uint8 or np.any(codes >= len(KINDS)):
        raise ValueError("invalid kind codes")
    return np.asarray(KINDS, dtype="U24")[codes]


def _graph_arrays(prefix, graph):
    receiver = graph.receiver
    donor_ids = np.flatnonzero(receiver >= 0).astype(np.int64)
    donor_ids = donor_ids[np.argsort(receiver[donor_ids], kind="stable")]
    offsets = np.zeros(receiver.size + 1, np.int64)
    offsets[1:] = np.cumsum(np.bincount(receiver[donor_ids], minlength=receiver.size))
    return {prefix + "_receiver": receiver,
            prefix + "_order": graph.order_downstream_first,
            prefix + "_edge_length_m": graph.edge_length_m,
            prefix + "_edge_slope": graph.edge_slope,
            prefix + "_outlet_kind_code": _encode(graph.outlet_kind),
            prefix + "_lake_id": graph.lake_id,
            prefix + "_donor_offsets": offsets,
            prefix + "_donor_ids": donor_ids}


def _summary(graph):
    kinds = graph.outlet_kind
    return {name: int(np.count_nonzero(kinds == name)) for name in
            ("open_outflow", "prescribed_stage", "prescribed_discharge",
             "unknown_boundary", "lake_preserved")}


def compare_routing_policies(terrain: TerrainGrid, boundary: BoundaryGrid) -> dict:
    """Save raw-bed, flood working-bed, and metric plateau irregular routing."""
    original = route_diagnostic(terrain, boundary)
    flooded = route_priority_flood(terrain, boundary)
    graphs = {"original_bed_irregular": original, "priority_flood_irregular": flooded["graph"],
              "metric_flat_irregular": _route_metric_flat(terrain, boundary)}
    arrays = {"elevation_m": terrain.elevation_m, "valid_mask": terrain.valid_mask,
              "boundary_kind_code": _encode(boundary.kind),
              "boundary_allow_inflow": boundary.allow_inflow,
              "working_elevation_m": flooded["working_elevation_m"],
              "fill_depth_m": flooded["fill_depth_m"],
              "flood_reached_mask": flooded["flood_reached_mask"],
              "unknown_catchment_excluded_mask": flooded["unknown_catchment_excluded_mask"]}
    for field in ("stage_m", "discharge_m3_s"):
        value = getattr(boundary, field)
        if value is not None:
            arrays["boundary_" + field] = value
    for name, graph in graphs.items():
        arrays.update(_graph_arrays(name, graph))
    policies = {name: {"policy": graph.policy,
                       "graph_identity_sha256": graph.identity_sha256,
                       "terminal_counts": _summary(graph),
                       "tie_break": "steepest_metric_slope_then_cell_id; plateau_bfs_distance_then_cell_id"
                       if name != "metric_flat_irregular" else
                       "steepest_metric_slope_then_cell_id; plateau_metric_distance_then_cell_id",
                       "adjacency": "restricted_Delaunay_unknown_supercover" if name == "metric_flat_irregular"
                       else "restricted_Delaunay_unknown_supercover",
                       "relation_to_frozen_td_d4":
                       "independent_metric_plateau_not_frozen_td_hierarchy" if name == "metric_flat_irregular"
                       else "independent_diagnostic"} for name, graph in graphs.items()}
    metadata = {"schema": SCHEMA, "terrain": terrain.metadata(),
                "terrain_identity_sha256": terrain.identity_sha256,
                "boundary": {"source_id": boundary.source_id,
                             "source_sha256": boundary.source_sha256},
                "boundary_identity_sha256": boundary.identity_sha256,
                "policies": policies, "flood": flooded["metadata"],
                "flood_heap_tie_break": "working_height_then_cell_id",
                "fill_is_working_surface_only": True,
                "lake_id_semantics": "contributing_catchment_not_wet_lake_footprint",
                "hydraulic_ready": False, "natural_outlet_verified": False,
                "publishable": False}
    return {"arrays": arrays, "metadata": metadata,
            "identity_sha256": identity(arrays, metadata)}


def _terrain_boundary(bundle):
    arrays, meta = bundle["arrays"], bundle["metadata"]
    terrain = TerrainGrid(arrays["elevation_m"], arrays["valid_mask"], **{
        key: value for key, value in meta["terrain"].items()
        if key in TerrainGrid.__dataclass_fields__ and key not in ("elevation_m", "valid_mask")})
    boundary = BoundaryGrid(_decode(arrays["boundary_kind_code"]),
                            arrays["boundary_allow_inflow"], meta["boundary"]["source_id"],
                            meta["boundary"]["source_sha256"],
                            stage_m=arrays.get("boundary_stage_m"),
                            discharge_m3_s=arrays.get("boundary_discharge_m3_s"))
    return terrain, boundary


def decode_routing_comparison(bundle) -> dict[str, RoutingGraph]:
    """Reconstruct pinned graphs without running any routing algorithm."""
    arrays, meta = bundle["arrays"], bundle["metadata"]
    terrain, boundary = _terrain_boundary(bundle)
    result = {}
    for name in POLICIES:
        policy = meta["policies"][name]
        graph = RoutingGraph(arrays[name + "_receiver"], arrays[name + "_order"],
                             arrays["valid_mask"], arrays[name + "_edge_length_m"],
                             arrays[name + "_edge_slope"],
                             _decode(arrays[name + "_outlet_kind_code"]),
                             arrays[name + "_lake_id"], terrain.identity_sha256,
                             boundary.identity_sha256, policy=policy["policy"])
        if graph.identity_sha256 != policy["graph_identity_sha256"]:
            raise ValueError("saved graph identity mismatch: " + name)
        result[name] = graph
    return result


def validate_routing_comparison(bundle):
    arrays, meta = bundle["arrays"], bundle["metadata"]
    metadata_keys = {"schema", "terrain", "terrain_identity_sha256", "boundary",
                     "boundary_identity_sha256", "policies", "flood", "flood_heap_tie_break",
                     "fill_is_working_surface_only", "lake_id_semantics", "hydraulic_ready",
                     "natural_outlet_verified", "publishable"}
    required = {"elevation_m", "valid_mask", "boundary_kind_code",
                "boundary_allow_inflow", "working_elevation_m", "fill_depth_m",
                "flood_reached_mask", "unknown_catchment_excluded_mask"}
    for name in POLICIES:
        required.update(name + "_" + field for field in
                        ("receiver", "order", "edge_length_m", "edge_slope",
                         "outlet_kind_code", "lake_id", "donor_offsets", "donor_ids"))
    optional = {"boundary_stage_m", "boundary_discharge_m3_s"}
    if (set(meta) != metadata_keys or meta.get("schema") != SCHEMA
            or set(meta.get("policies", {})) != set(POLICIES)
            or not required.issubset(arrays) or set(arrays) - required - optional
            or any(meta.get(key) is not False for key in
                   ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or meta.get("fill_is_working_surface_only") is not True
            or meta.get("lake_id_semantics") != "contributing_catchment_not_wet_lake_footprint"
            or meta.get("flood_heap_tie_break") != "working_height_then_cell_id"
            or bundle["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("routing comparison metadata or identity mismatch")
    terrain, boundary = _terrain_boundary(bundle)
    if (meta["terrain_identity_sha256"] != terrain.identity_sha256
            or meta["boundary_identity_sha256"] != boundary.identity_sha256
            or meta["terrain"] != terrain.metadata()):
        raise ValueError("routing comparison terrain or boundary linkage mismatch")
    working, fill = arrays["working_elevation_m"], arrays["fill_depth_m"]
    reached = arrays["flood_reached_mask"]
    excluded = arrays["unknown_catchment_excluded_mask"]
    if (working.shape != terrain.elevation_m.shape or working.dtype != np.float64
            or fill.shape != working.shape or fill.dtype != np.float64
            or reached.shape != working.shape or reached.dtype != bool
            or excluded.shape != working.shape or excluded.dtype != bool
            or not np.isfinite(working).all() or not np.isfinite(fill).all()
            or np.any(fill < 0.) or not np.allclose(fill, working - terrain.elevation_m,
                                                   rtol=0., atol=1e-10)
            or np.any(reached & ~terrain.valid_mask)
            or np.any(reached & excluded)
            or np.any(excluded & ~terrain.valid_mask)
            or np.any(reached & (boundary.kind == "unknown_boundary"))
            or np.any(fill[~reached] != 0.)):
        raise ValueError("working surface or fill depth differs from original bed")
    known = terrain.valid_mask & np.isin(boundary.kind, _KNOWN_OUTLETS)
    flood = meta["flood"]
    if (np.any(known & ~reached)
            or flood.get("policy") != "priority_flood_working_bed_irregular_v2"
            or flood.get("terrain_identity_sha256") != terrain.identity_sha256
            or flood.get("boundary_identity_sha256") != boundary.identity_sha256
            or flood.get("flood_reached_valid_cells") != int(reached.sum())
            or flood.get("unreached_valid_cells") != int(terrain.valid_mask.sum() - reached.sum())
            or flood.get("unknown_catchment_excluded_cells") != int(excluded.sum())
            or flood.get("unknown_catchment_policy")
            != "preserve_original_bed_and_exclude_from_known_outlet_flood"
            or flood.get("filled_cell_count") != int(np.count_nonzero(fill > 0.))
            or flood.get("maximum_fill_m") != float(fill.max())
            or not math.isclose(flood.get("filled_volume_m3", float("nan")),
                                float(np.sum(fill[terrain.valid_mask], dtype=np.float64)
                                      * terrain.cell_area_m2), rel_tol=1e-12, abs_tol=1e-9)
            or flood.get("work_surface_only") is not True
            or flood.get("natural_outlet_verified") is not False):
        raise ValueError("saved flood reachability or fill accounting differs")
    graphs = decode_routing_comparison(bundle)
    mesh = diagnostic_mesh(terrain)
    contact = unknown_contacts(terrain.valid_mask, diagnostic_mesh(terrain, unmasked=True)).ravel()
    original = graphs["original_bed_irregular"]
    if flood.get("original_bed_graph_identity_sha256") != original.identity_sha256:
        raise ValueError("flood original-bed policy identity differs")
    expected_excluded = np.zeros(original.receiver.size, bool)
    for cell in original.order_downstream_first:
        target = original.receiver[cell]
        expected_excluded[cell] = (original.outlet_kind[cell] == "unknown_boundary"
                                   if target < 0 else expected_excluded[target])
    if not np.array_equal(excluded.ravel(), expected_excluded):
        raise ValueError("unknown catchment exclusion differs from original-bed graph")
    valid = terrain.valid_mask.ravel()
    explicit = valid & np.isin(boundary.kind.ravel(), _EXPLICIT)
    for name, graph in graphs.items():
        prefix = name + "_"
        policy = meta["policies"][name]
        expected_policy = ("original_bed_irregular_plateau_bfs_v2" if name == "original_bed_irregular"
                           else "priority_flood_working_bed_irregular_v2" if name == "priority_flood_irregular"
                           else "original_bed_irregular_plateau_metric_distance_v2")
        expected_tie = ("steepest_metric_slope_then_cell_id; plateau_metric_distance_then_cell_id"
                        if name == "metric_flat_irregular" else
                        "steepest_metric_slope_then_cell_id; plateau_bfs_distance_then_cell_id")
        if (policy["policy"] != expected_policy or policy.get("tie_break") != expected_tie
                or policy.get("adjacency") != ("restricted_Delaunay_unknown_supercover" if name == "metric_flat_irregular"
                                                  else "restricted_Delaunay_unknown_supercover")):
            raise ValueError("saved routing policy declaration differs")
        donor_ids = arrays[prefix + "donor_ids"]
        offsets = arrays[prefix + "donor_offsets"]
        expected = _graph_arrays(name, graph)
        if (donor_ids.dtype != np.int64 or offsets.dtype != np.int64
                or not np.array_equal(donor_ids, expected[prefix + "donor_ids"])
                or not np.array_equal(offsets, expected[prefix + "donor_offsets"])
                or _summary(graph) != meta["policies"][name]["terminal_counts"]):
            raise ValueError("saved donor CSR or terminal counts differ")
        if (np.any(graph.receiver[explicit] != -1)
                or np.any(graph.outlet_kind[explicit] != boundary.kind.ravel()[explicit])):
            raise ValueError("explicit boundary terminal differs")
        terminal = valid & (graph.receiver < 0)
        implicit = np.flatnonzero(terminal & ~explicit)
        rows, cols = terrain.elevation_m.shape
        valid_grid = terrain.valid_mask
        for cell in implicit:
            if graph.outlet_kind[cell] not in ("lake_preserved", "unknown_boundary"):
                raise ValueError("implicit terminal claims open outflow")
            if graph.outlet_kind[cell] == "unknown_boundary":
                touching = bool(contact[cell])
                if not touching:
                    raise ValueError("unknown terminal has no unknown terrain contact")
        lake_terminals = implicit[graph.outlet_kind[implicit] == "lake_preserved"]
        if (np.any(graph.lake_id[lake_terminals] != lake_terminals)
                or np.any(graph.lake_id[terminal & (graph.outlet_kind != "lake_preserved")] != -1)):
            raise ValueError("lake terminal ID differs from contributing basin")
        donors = np.flatnonzero(graph.receiver >= 0)
        targets = graph.receiver[donors]
        if np.any(graph.lake_id[donors] != graph.lake_id[targets]):
            raise ValueError("lake catchment ID differs from downstream terminal")
        if not receiver_edges_valid(graph.receiver, mesh):
            raise ValueError("saved routing edge is absent from the masked irregular graph")
        bed = working.ravel() if name == "priority_flood_irregular" else terrain.elevation_m.ravel()
        distance = np.hypot(mesh.node_x_m[targets] - mesh.node_x_m[donors],
                            mesh.node_z_m[targets] - mesh.node_z_m[donors])
        drop = bed[donors] - bed[targets]
        if (np.any(drop < -1e-10)
                or not np.allclose(graph.edge_length_m[donors], distance, rtol=0., atol=1e-10)
                or not np.allclose(graph.edge_slope[donors], drop / distance,
                                   rtol=1e-12, atol=1e-12)):
            raise ValueError("saved graph disagrees with its declared bed geometry")
    if (meta["policies"]["metric_flat_irregular"]["relation_to_frozen_td_d4"]
            != "independent_metric_plateau_not_frozen_td_hierarchy"):
        raise ValueError("metric plateau policy falsely claims frozen hierarchy identity")


def save_routing_comparison(path, bundle):
    save_bundle(path, bundle, validator=validate_routing_comparison)


def load_routing_comparison(path, *, expected_sha256, expected_identity=None):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_routing_comparison, max_bytes=512 * 1024 * 1024)
    if expected_identity is not None and bundle["identity_sha256"] != expected_identity:
        raise ValueError("routing comparison identity differs from external pin")
    return bundle
