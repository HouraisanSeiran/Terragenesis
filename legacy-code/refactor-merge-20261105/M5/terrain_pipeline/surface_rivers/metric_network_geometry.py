"""Source-bound whole-domain river selection and edge-disjoint patch planning.

This is a catalogue, not a claim that every selected source edge has a valid bed.
Every selected edge is assigned exactly once; downstream closures and rejected
patches remain explicit. Native cell area is the contributing-area basis.
"""

from dataclasses import asdict, dataclass

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.common_infra import RoutingGraph, TerrainGrid


SCHEMA = "terragenesis-network-geometry-plan-v1"
ALGORITHM = "native-area-edge-disjoint-patches-v1"


@dataclass(frozen=True)
class NetworkGeometryConfig:
    min_contributing_area_m2: float = 1_000_000.
    max_patch_edges: int = 6
    design_runoff_mm_h: float = 1.
    minimum_width_m: float = 6.
    width_coefficient_m_per_sqrt_cms: float = 4.
    minimum_depth_m: float = .25
    depth_coefficient_m_per_cuberoot_cms: float = .2

    def __post_init__(self):
        for name in ("min_contributing_area_m2", "design_runoff_mm_h", "minimum_width_m",
                     "width_coefficient_m_per_sqrt_cms", "minimum_depth_m",
                     "depth_coefficient_m_per_cuberoot_cms"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not np.isscalar(value) or not np.isfinite(value) or value <= 0.:
                raise ValueError(name + " must be finite positive")
        if type(self.max_patch_edges) is not int or not 1 <= self.max_patch_edges <= 32:
            raise ValueError("max_patch_edges outside bounded patch budget")


def _catalogue(terrain, graph, config):
    if not isinstance(terrain, TerrainGrid) or not isinstance(graph, RoutingGraph):
        raise ValueError("TerrainGrid and RoutingGraph required")
    if graph.terrain_identity_sha256 != terrain.identity_sha256:
        raise ValueError("graph terrain identity must match the original source")
    if (graph.valid_mask.shape != terrain.valid_mask.shape
            or not np.array_equal(graph.valid_mask, terrain.valid_mask)):
        raise ValueError("graph must cover the exact original terrain validity")
    if "irregular" in graph.policy:
        from terrain_pipeline.drainage import diagnostic_mesh as diagnostic_mesh
        from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
        mesh = diagnostic_mesh(terrain)
        if not receiver_edges_valid(graph.receiver, mesh):
            raise ValueError("receiver is not an edge of the declared metric irregular graph")
        sources = np.flatnonzero(graph.receiver >= 0)
        targets = graph.receiver[sources]
        lengths = np.hypot(mesh.node_x_m[targets] - mesh.node_x_m[sources],
                           mesh.node_z_m[targets] - mesh.node_z_m[sources])
        if not np.allclose(graph.edge_length_m[sources], lengths, rtol=1e-12, atol=1e-12):
            raise ValueError("graph lengths disagree with continuous metric node positions")
    rec = graph.receiver
    area = np.zeros(rec.size, np.float64)
    area[terrain.valid_mask.ravel()] = terrain.cell_area_m2
    owner = np.full(rec.size, -1, np.int64)
    for cell in graph.order_downstream_first:
        target = rec[cell]
        owner[cell] = cell if target < 0 else owner[target]
    for cell in graph.order_downstream_first[::-1]:
        if rec[cell] >= 0:
            area[rec[cell]] += area[cell]
    selected = (area >= config.min_contributing_area_m2) & (rec >= 0)
    ids = np.flatnonzero(selected)
    donors = np.bincount(rec[ids], minlength=rec.size)
    patch_owner = np.full(rec.size, -1, np.int64)
    patch_edges = []
    # Each chain starts at a source or confluence; split only on explicit size.
    starts = ids[donors[ids] != 1]
    for first in starts:
        cell = int(first)
        while selected[cell] and patch_owner[cell] < 0:
            edges = []
            while selected[cell] and patch_owner[cell] < 0:
                edges.append(cell)
                patch_owner[cell] = len(patch_edges)
                target = int(rec[cell])
                if (len(edges) == config.max_patch_edges or not selected[target]
                        or donors[target] != 1):
                    break
                cell = target
            patch_edges.append(edges)
            cell = target
    if np.any(patch_owner[ids] < 0):
        raise ValueError("selected source graph is not an acyclic downstream catalogue")
    offsets = np.r_[0, np.cumsum([len(edges) for edges in patch_edges])].astype(np.int64)
    edge_ids = np.concatenate([np.asarray(edges, np.int64) for edges in patch_edges]) if patch_edges else np.empty(0, np.int64)
    design_q = area * config.design_runoff_mm_h / 1000. / 3600.
    widths = np.maximum(config.minimum_width_m,
                        config.width_coefficient_m_per_sqrt_cms * np.sqrt(design_q))
    depths = np.maximum(config.minimum_depth_m,
                        config.depth_coefficient_m_per_cuberoot_cms * np.cbrt(design_q))
    return dict(contributing_area_m2=area, terminal_owner=owner,
                selected_edge_source_ids=ids, selected_edge_target_ids=rec[ids],
                patch_offsets=offsets, patch_edge_source_ids=edge_ids,
                edge_patch_id=patch_owner[ids], selected_design_q_m3_s=design_q[ids],
                selected_width_m=widths[ids], selected_depth_m=depths[ids])


def build_network_geometry_plan(terrain, graph, config=None):
    config = config or NetworkGeometryConfig()
    if not isinstance(config, NetworkGeometryConfig):
        raise ValueError("NetworkGeometryConfig required")
    catalogue = _catalogue(terrain, graph, config)
    arrays = {"source_elevation_m": terrain.elevation_m,
              "source_valid_mask": terrain.valid_mask,
              **{"graph_" + name: getattr(graph, name) for name in (
                  "receiver", "order_downstream_first", "valid_mask", "edge_length_m",
                  "edge_slope", "outlet_kind", "lake_id")}, **catalogue}
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, config=asdict(config),
                    terrain_metadata={key: getattr(terrain, key) for key in terrain.__dataclass_fields__
                                      if key not in ("elevation_m", "valid_mask")},
                    terrain_identity_sha256=terrain.identity_sha256,
                    graph_metadata={"terrain_identity_sha256": graph.terrain_identity_sha256,
                                    "boundary_identity_sha256": graph.boundary_identity_sha256,
                                    "policy": graph.policy},
                    graph_identity_sha256=graph.identity_sha256,
                    selection="original_graph_edges_above_native_contributing_area_threshold",
                    section_policy="explicit_uncalibrated_monotone_design_discharge_scenario",
                    source_assignment="native_local_sources_require_upstream_aggregation_once",
                    status="complete_selection_catalogue_geometry_pending",
                    geometry_verified=False, hydraulic_ready=False,
                    natural_outlet_verified=False, publishable=False)
    arrays = {key: readonly(value) for key, value in arrays.items()}
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
    validate_network_geometry_plan(result)
    return result


def validate_network_geometry_plan(bundle):
    a, m = bundle["arrays"], bundle["metadata"]
    if (m.get("schema") != SCHEMA or m.get("algorithm") != ALGORITHM
            or identity(a, m) != bundle["identity_sha256"]):
        raise ValueError("network plan schema or identity mismatch")
    terrain = TerrainGrid(a["source_elevation_m"], a["source_valid_mask"], **m["terrain_metadata"])
    graph = RoutingGraph(**{name: a["graph_" + name] for name in (
        "receiver", "order_downstream_first", "valid_mask", "edge_length_m", "edge_slope",
        "outlet_kind", "lake_id")}, **m["graph_metadata"])
    if terrain.identity_sha256 != m["terrain_identity_sha256"] or graph.identity_sha256 != m["graph_identity_sha256"]:
        raise ValueError("network source identities mismatch")
    expected = _catalogue(terrain, graph, NetworkGeometryConfig(**m["config"]))
    for key, value in expected.items():
        if not np.array_equal(a[key], value):
            raise ValueError("network catalogue mismatch: " + key)
    ids = a["selected_edge_source_ids"]
    if not np.array_equal(np.sort(a["patch_edge_source_ids"]), ids):
        raise ValueError("patches duplicate or omit selected edges")
    if any(m.get(key) is not False for key in ("geometry_verified", "hydraulic_ready", "natural_outlet_verified", "publishable")):
        raise ValueError("catalogue cannot certify geometry or hydraulics")
    return True


def save_network_geometry_plan(path, bundle):
    return save_bundle(path, bundle, validator=validate_network_geometry_plan)


def load_network_geometry_plan(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_network_geometry_plan,
                       max_bytes=512 * 1024 * 1024)
