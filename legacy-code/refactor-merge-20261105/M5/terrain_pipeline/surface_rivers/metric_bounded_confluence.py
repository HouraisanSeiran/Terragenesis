"""Bounded routing work surfaces inside frozen owner domains, never terrain edits."""

import hashlib
from pathlib import Path

import numpy as np
from scipy.ndimage import label, find_objects

from terrain_pipeline.common_infra import identity
from terrain_pipeline.common_infra import RoutingGraph
from dataclasses import replace
from collections import deque
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import masked_mesh as masked_mesh
from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
from terrain_pipeline.drainage import segments_clear as segments_clear
from terrain_pipeline.drainage import route_graph as route_graph

TERMINAL_STATUS_CODES = {
    "inactive": 0, "interior": 1, "unresolved_closed_domain": 2,
    "unresolved_domain_boundary": 3, "unknown_boundary": 4,
    "frozen_outlet_candidate": 5, "unresolved_deep_depression": 6,
    "unresolved_fill_budget": 7, "unresolved_unknown_owner": 8,
}


def _terrain_mesh(terrain):
    return masked_mesh(grid_mesh(terrain.valid_mask.shape, x0_m=terrain.x0_m, z0_m=terrain.z0_m,
        dx_m=terrain.dx_m, dz_m=terrain.dz_m,
        world_seed=terrain.generation_seed if terrain.generation_seed is not None else 20261020),
        terrain.valid_mask)


class _GraphAnalysis:
    def __init__(self, receiver, order):
        self.receiver, self.order = receiver, order

    def accuflux(self, local, nodata=None):
        flow = np.asarray(local, np.float64).ravel().copy()
        for cell in self.order[::-1]:
            target = self.receiver[cell]
            if target >= 0:
                flow[target] += flow[cell]
        return flow.reshape(np.asarray(local).shape)


def _routing(backend, terrain, receiver):
    """Analyze arbitrary graph edges without encoding raster direction codes."""
    valid = terrain.valid_mask.ravel()
    donors = [[] for _ in range(receiver.size)]
    pending = deque()
    for node in np.flatnonzero(valid):
        target = int(receiver[node])
        if target < 0:
            pending.append(int(node))
        else:
            donors[target].append(int(node))
    order = []
    while pending:
        node = pending.popleft()
        order.append(node)
        pending.extend(donors[node])
    if len(order) != int(valid.sum()):
        raise ValueError("candidate receiver contains a cycle or missing valid cells")
    order = np.asarray(order, np.int64)
    return _GraphAnalysis(receiver, order), order


def _check_receiver(receiver, valid, owner, mesh):
    size = valid.size
    if (not isinstance(receiver, np.ndarray) or receiver.dtype != np.int64
            or receiver.shape != (size,) or np.any(receiver < -1)
            or np.any(receiver >= size) or np.any(receiver[~valid.ravel()] != -1)):
        raise ValueError("baseline_receiver must be int64 [N] inside valid terrain")
    sources = np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    if np.any(~valid.ravel()[targets]) or not receiver_edges_valid(receiver, mesh):
        raise ValueError("baseline receiver must join valid irregular graph neighbors")
    return sources[owner[sources] != owner[targets]]


def _restore_steepest_descent(terrain, owner_grid, receiver, work, eligible, mesh=None):
    mesh = _terrain_mesh(terrain) if mesh is None else mesh
    original = receiver.copy()
    owner = owner_grid.ravel()
    for node in np.flatnonzero(eligible.ravel() & (receiver >= 0)):
        best = 0.
        for edge in range(mesh.indptr[node], mesh.indptr[node + 1]):
            target = mesh.indices[edge]
            if owner[target] != owner[node]:
                continue
            slope = (work[node] - work[target]) / mesh.edge_length_m[edge]
            if slope > best:
                receiver[node], best = target, slope
    return int(np.count_nonzero(receiver != original))


def bounded_confluence_candidate(terrain, boundary, frozen_owner_domain_id, *,
                                 baseline_receiver=None, frozen_outlet_mask=None,
                                 max_fill_depth_m=4.0, local_q_m3_s=None):
    """Return graph, work surface, metadata and an explicit unresolved-state ledger.

    Only existing cross-owner contacts, original unknown-boundary terminals and
    explicitly supplied frozen outlets seed the library. Other owner boundaries
    are walls. Components without a seed retain their restricted baseline DAG.
    Negative owner labels remain distinct routing regions without outlet claims.
    """
    if (isinstance(max_fill_depth_m, (bool, np.bool_))
            or not isinstance(max_fill_depth_m, (int, float, np.integer, np.floating))
            or not np.isfinite(max_fill_depth_m) or max_fill_depth_m <= 0):
        raise ValueError("positive finite max_fill_depth_m required")
    height, valid = terrain.elevation_m, terrain.valid_mask
    if height.shape != boundary.kind.shape or terrain.dx_m != terrain.dz_m:
        raise ValueError("matching boundary and square metric cells required")
    owner_grid = np.asarray(frozen_owner_domain_id)
    if owner_grid.shape != height.shape or owner_grid.dtype.kind not in "iu":
        raise ValueError("frozen_owner_domain_id must be a matching integer grid")
    owner = owner_grid.ravel()
    if frozen_outlet_mask is None:
        frozen_outlet_mask = np.zeros(height.shape, bool)
    if (not isinstance(frozen_outlet_mask, np.ndarray) or frozen_outlet_mask.dtype != bool
            or frozen_outlet_mask.shape != height.shape
            or np.any(frozen_outlet_mask & ~valid)):
        raise ValueError("frozen_outlet_mask must select valid cells")
    if local_q_m3_s is not None:
        local_q_m3_s = np.asarray(local_q_m3_s, np.float64)
        if (local_q_m3_s.size != height.size or local_q_m3_s.shape not in (height.shape, (height.size,))
                or not np.isfinite(local_q_m3_s).all() or np.any(local_q_m3_s < 0)
                or np.any(local_q_m3_s.ravel()[~valid.ravel()] != 0)):
            raise ValueError("finite nonnegative local discharge on valid cells required")
    if baseline_receiver is None:
        from terrain_pipeline.drainage import route_diagnostic as route_diagnostic
        baseline_receiver = route_diagnostic(
            terrain, boundary, flat_distance_strategy="metric_distance").receiver
    mesh = _terrain_mesh(terrain)
    crossings = _check_receiver(baseline_receiver, valid, owner, mesh)
    backend = None

    # Validate the supplied baseline DAG before truncating its cross-domain edges.
    _routing(backend, terrain, baseline_receiver)
    receiver = baseline_receiver.copy()
    receiver[crossings] = -1
    status = np.full(height.size, TERMINAL_STATUS_CODES["interior"], dtype=np.uint8)
    status[~valid.ravel()] = TERMINAL_STATUS_CODES["inactive"]
    status[valid.ravel() & (receiver < 0)] = TERMINAL_STATUS_CODES["unresolved_closed_domain"]
    status[crossings] = TERMINAL_STATUS_CODES["unresolved_domain_boundary"]
    unknown_boundary = ((boundary.kind.ravel() == "unknown_boundary")
                        & valid.ravel() & (baseline_receiver < 0))
    status[unknown_boundary] = TERMINAL_STATUS_CODES["unknown_boundary"]
    status[frozen_outlet_mask.ravel()] = TERMINAL_STATUS_CODES["frozen_outlet_candidate"]
    seeds = np.zeros(height.size, bool)
    seeds[crossings] = True
    seeds |= unknown_boundary | frozen_outlet_mask.ravel()
    receiver[seeds] = -1
    descent_eligible = np.zeros(height.shape, bool)
    component_records = []
    source_nodes = np.repeat(np.arange(height.size), np.diff(mesh.indptr))
    keep = (owner[source_nodes] == owner[mesh.indices]) & valid.ravel()[source_nodes] & valid.ravel()[mesh.indices]
    for label in np.unique(owner[valid.ravel()]):
        positions = np.flatnonzero(keep & (owner[source_nodes] == label))
        keep[positions] &= segments_clear(source_nodes[positions], mesh.indices[positions],
                                         valid & (owner_grid == label))
    counts = np.bincount(source_nodes[keep], minlength=height.size)
    domain_mesh = replace(mesh, indptr=np.r_[0, np.cumsum(counts)],
        indices=mesh.indices[keep], edge_length_m=mesh.edge_length_m[keep])
    adjacency = csr_matrix((np.ones(domain_mesh.indices.size), domain_mesh.indices, domain_mesh.indptr),
                           shape=(height.size, height.size))
    _, components = connected_components(adjacency, directed=False)
    for component_id in np.unique(components[valid.ravel()]):
        global_ids = np.flatnonzero((components == component_id) & valid.ravel())
        component_seeds = seeds[global_ids]
        record = dict(owner_domain_id=int(owner[global_ids[0]]), cell_count=int(global_ids.size),
                      seed_count=int(component_seeds.sum()))
        if not component_seeds.any():
            record["policy"] = "restricted_baseline_no_fill_no_invented_outlet"
            component_records.append(record)
            continue
        descent_eligible.ravel()[global_ids] = True
        lookup = np.full(height.size, -1, np.int64)
        lookup[global_ids] = np.arange(global_ids.size)
        edge_ids = np.concatenate([np.arange(domain_mesh.indptr[node], domain_mesh.indptr[node + 1])
                                   for node in global_ids])
        degree = np.diff(domain_mesh.indptr)[global_ids]
        local_mesh = replace(domain_mesh, shape=(1, global_ids.size),
            node_x_m=mesh.node_x_m[global_ids], node_z_m=mesh.node_z_m[global_ids],
            indptr=np.r_[0, np.cumsum(degree)], indices=lookup[domain_mesh.indices[edge_ids]],
            edge_length_m=domain_mesh.edge_length_m[edge_ids])
        local_height = height.ravel()[global_ids].reshape(1, -1)
        local_outlets = component_seeds.reshape(1, -1).copy()
        while True:
            routed = route_graph(local_height, local_outlets, local_mesh)
            deep = (routed.filled - local_height) >= max_fill_depth_m
            added = deep & ~local_outlets
            if not added.any():
                break
            local_outlets |= added
        local_receiver = routed.receiver
        terminal = local_receiver < 0
        receiver[global_ids] = np.where(terminal, -1, global_ids[np.maximum(local_receiver, 0)])
        status[global_ids] = TERMINAL_STATUS_CODES["interior"]
        status[global_ids[terminal]] = TERMINAL_STATUS_CODES["unresolved_deep_depression"]
        record["policy"] = "shared_irregular_graph_explicit_contact_seeds"
        component_records.append(record)
    receiver[seeds] = -1
    status[crossings] = TERMINAL_STATUS_CODES["unresolved_domain_boundary"]
    status[unknown_boundary] = TERMINAL_STATUS_CODES["unknown_boundary"]
    status[frozen_outlet_mask.ravel()] = TERMINAL_STATUS_CODES["frozen_outlet_candidate"]

    sources = np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    columns = height.shape[1]
    blocked = np.zeros(sources.size, bool)
    _, order = _routing(backend, terrain, receiver)
    # Reconstruct the minimum monotone surface in float64. The library queue is
    # float32; accepting its raw delv can exceed the stated fill cap by rounding.
    work = height.ravel().copy()
    budget_cut_count = 0
    for cell in order:
        target = receiver[cell]
        if target < 0:
            continue
        required = max(work[cell], work[target])
        if required - height.ravel()[cell] > max_fill_depth_m:
            receiver[cell] = -1
            status[cell] = TERMINAL_STATUS_CODES["unresolved_fill_budget"]
            budget_cut_count += 1
        else:
            work[cell] = required
    # A priority-flood spanning tree organizes flats, but its uphill visitation
    # order is not a terrain descent rule on ordinary slopes. Strictly lower
    # replacements remain acyclic alongside the retained equal-height DAG.
    descent_changed_count = _restore_steepest_descent(
        terrain, owner_grid, receiver, work, descent_eligible, domain_mesh)
    routing, order = _routing(backend, terrain, receiver)
    terminal = valid.ravel() & (receiver < 0)
    kinds = np.full(height.size, "interior", dtype="U16")
    kinds[~valid.ravel()] = "inactive"
    kinds[terminal] = "lake_preserved"
    unresolved_port = np.isin(status, [TERMINAL_STATUS_CODES["unresolved_domain_boundary"],
                                     TERMINAL_STATUS_CODES["frozen_outlet_candidate"]])
    kinds[terminal & ((owner < 0) | unknown_boundary | unresolved_port)] = "unknown_boundary"
    terminal_owner = np.full(height.size, -1, np.int64)
    for cell in order:
        terminal_owner[cell] = cell if receiver[cell] < 0 else terminal_owner[receiver[cell]]
    lake_id = np.full(height.size, -1, np.int64)
    terminal_is_internal = kinds[terminal_owner[valid.ravel()]] == "lake_preserved"
    active_cells = np.flatnonzero(valid)
    lake_id[active_cells[terminal_is_internal]] = terminal_owner[active_cells[terminal_is_internal]]
    sources = np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    length, slope = np.zeros(height.size), np.zeros(height.size)
    length[sources] = np.hypot(mesh.node_z_m[targets] - mesh.node_z_m[sources],
                               mesh.node_x_m[targets] - mesh.node_x_m[sources])
    slope[sources] = (work[sources] - work[targets]) / length[sources]
    graph = RoutingGraph(receiver, order, valid, length, slope, kinds, lake_id,
                         terrain.identity_sha256, boundary.identity_sha256,
                         policy="frozen_owner_bounded_confluence_candidate_v3_irregular")
    area = np.asarray(routing.accuflux(valid.astype(np.float64) * terrain.cell_area_m2,
                                      nodata=-9999.), np.float64).ravel()
    area[~valid.ravel()] = 0
    raises = (work - height.ravel()).reshape(height.shape)
    audit_arrays = dict(terminal_status=status, terminal_owner=terminal_owner,
                        terminal_owner_known=terminal & (owner >= 0),
                        contributing_area_m2=area, working_raise_m=raises,
                        baseline_cross_owner_source_ids=crossings,
                        frozen_seed_mask=seeds.reshape(height.shape))
    if local_q_m3_s is not None:
        discharge = np.asarray(routing.accuflux(local_q_m3_s.reshape(height.shape),
                                               nodata=-9999.), np.float64).ravel()
        discharge[~valid.ravel()] = 0
        audit_arrays["routed_q_m3_s"] = discharge
    metadata = dict(
        schema="bounded-confluence-candidate-v2",
        algorithm="frozen_owner_bounded_confluence_candidate_v3_irregular",
        backend="irregular_graph", version="1",
        max_fill_depth_m=float(max_fill_depth_m), maximum_fill_m=float(raises.max()),
        filled_volume_m3=float(raises.sum() * terrain.cell_area_m2),
        raised_cell_count=int(np.count_nonzero(raises)), budget_rejected_edge_count=budget_cut_count,
        baseline_receiver_identity_sha256=identity({"receiver": baseline_receiver}, {}),
        frozen_owner_identity_sha256=identity({"frozen_owner_domain_id": owner_grid}, {}),
        original_boundary_identity_sha256=boundary.identity_sha256,
        baseline_cross_owner_contact_count=int(crossings.size),
        blocked_diagonal_contact_count=int(blocked.sum()), component_records=component_records,
        steepest_descent_changed_edge_count=descent_changed_count,
        descent_policy="seeded components only: strictly lower same-owner graph neighbor with maximum drop/distance; ties by cell ID; equal-height spill receiver retained; terminals frozen",
        terminal_status_counts={name: int(np.count_nonzero(status[terminal] == code))
                                for name, code in TERMINAL_STATUS_CODES.items()
                                if np.any(status[terminal] == code)},
        terminal_status_codes=TERMINAL_STATUS_CODES,
        unknown_owner_terminal_count=int(np.count_nonzero(terminal & (owner < 0))),
        seed_policy="original cross-owner upstream contacts and original unknown-boundary terminals; optional explicit frozen outlet candidates",
        owner_boundary_policy="closed except explicit seeds; all owner labels isolated including negative labels",
        no_seed_policy="restricted original receiver retained; no fill or invented outlet",
        unknown_owner_policy="negative owner IDs remain separate; all their terminals uncertified, never inferred sea",
        fill_policy="float64 minimum monotone receiver surface; over-budget edges terminate unresolved",
        graph_lake_preserved_semantics="compatibility placeholder for unresolved terminal; no accepted lake or wet footprint",
        budget_semantics="routing-only shallow fill cap; independent of any bed-cut budget",
        work_surface_only=True, natural_outlet_verified=False, hydraulic_ready=False, publishable=False,
    )
    validate_bounded_confluence(terrain, owner_grid, graph, work.reshape(height.shape),
                               audit_arrays, max_fill_depth_m=max_fill_depth_m)
    return graph, work.reshape(height.shape), metadata, audit_arrays


def validate_bounded_confluence(terrain, frozen_owner_domain_id, graph, work, audit_arrays, *,
                                max_fill_depth_m=4.0):
    """Check owner isolation, actual fill, terminal ledger and full area closure."""
    owner = np.asarray(frozen_owner_domain_id).ravel()
    sources = np.flatnonzero(graph.receiver >= 0)
    targets = graph.receiver[sources]
    if np.any(owner[sources] != owner[targets]):
        raise ValueError("candidate receiver crosses frozen owner domains")
    raises = work - terrain.elevation_m
    if not np.isfinite(work).all() or np.any(raises < 0) or np.any(raises > max_fill_depth_m):
        raise ValueError("actual routing fill outside declared budget")
    if np.any(work.ravel()[sources] < work.ravel()[targets]):
        raise ValueError("working receiver edge is uphill")
    if not np.array_equal(raises, audit_arrays["working_raise_m"]):
        raise ValueError("routing fill ledger differs from actual work surface")
    area = audit_arrays["contributing_area_m2"]
    expected = terrain.valid_mask.ravel() * terrain.cell_area_m2 + np.bincount(
        targets, weights=area[sources], minlength=graph.receiver.size)
    if not np.allclose(area, expected, rtol=1e-10, atol=1e-8):
        raise ValueError("contributing area does not close at every node")
    terminal = terrain.valid_mask.ravel() & (graph.receiver < 0)
    if np.any(audit_arrays["terminal_status"][terminal] == TERMINAL_STATUS_CODES["interior"]):
        raise ValueError("candidate terminal lacks an explicit classification")
    if not np.isclose(area[terminal].sum(), terrain.valid_mask.sum() * terrain.cell_area_m2):
        raise ValueError("terminal area does not cover valid source terrain")
