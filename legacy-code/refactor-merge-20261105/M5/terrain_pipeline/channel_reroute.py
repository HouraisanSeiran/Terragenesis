"""Bounded irregular-graph reroute with conservative discharge recomputation."""

from dataclasses import dataclass
import heapq
import math

import numpy as np
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import masked_mesh as masked_mesh

from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel, _validate_route
from terrain_pipeline.network_valley import _validated_source_plan


@dataclass(frozen=True)
class RerouteRecipe:
    max_path_cells: int = 200
    max_expansions: int = 10000
    max_extra_cut_m: float = 4.
    max_cells: int = 250000

    def __post_init__(self):
        if (type(self.max_path_cells) is not int or not 0 < self.max_path_cells <= 1000000 or
                type(self.max_expansions) is not int or not 0 < self.max_expansions <= 1000000 or
                type(self.max_cells) is not int or not 0 < self.max_cells <= 1000000 or
                isinstance(self.max_extra_cut_m, bool) or
                not math.isfinite(self.max_extra_cut_m) or self.max_extra_cut_m < 0):
            raise ValueError("invalid reroute bounds")


def _integer_pair(value):
    if (not isinstance(value, (tuple, list, np.ndarray)) or len(value) != 2 or
            any(isinstance(item, (bool, np.bool_)) or not isinstance(item, (int, np.integer))
                for item in value)):
        raise ValueError("reroute endpoints must be integer pairs")
    return tuple(int(item) for item in value)


def _local_discharge(plan):
    arrays = plan["arrays"]
    discharge = arrays["discharge_m3_s"].ravel()
    local = discharge.copy()
    receiver = arrays["receiver"]
    donors = np.flatnonzero(receiver >= 0)
    np.subtract.at(local, receiver[donors], discharge[donors])
    if np.any(local < -1e-8):
        raise ValueError("source discharge is not conservative")
    local = np.maximum(local, 0.)
    total = float(discharge[receiver < 0].sum())
    if not math.isclose(float(local.sum()), total, rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("outlet discharge is not conservative")
    return local, total


def reroute_channel(plan, source_grid_zx, downstream_anchor_grid_zx, domain_mask,
                    protected_mask, recipe=RerouteRecipe()):
    """Search an explicit local path, replace one receiver edge, then replan Q/bed."""
    if not isinstance(recipe, RerouteRecipe):
        raise ValueError("reroute recipe required")
    if np.asarray(plan["arrays"]["source_height_m"]).size > recipe.max_cells:
        raise ValueError("reroute exceeds cell bound")
    plan = _validated_source_plan(plan)
    arrays = plan["arrays"]
    params = plan["identity"]["parameters"]
    if recipe.max_extra_cut_m > params["max_cut_m"]:
        raise ValueError("reroute extra cut exceeds original bed limit")
    local_q, outlet_total = _local_discharge(plan)
    height = arrays["source_height_m"]
    shape = height.shape
    domain, protected = np.asarray(domain_mask), np.asarray(protected_mask)
    if domain.shape != shape or protected.shape != shape or domain.dtype != bool or protected.dtype != bool:
        raise ValueError("invalid reroute masks")
    start = _integer_pair(source_grid_zx)
    anchor = _integer_pair(downstream_anchor_grid_zx)
    if any(not (0 <= point[0] < shape[0] and 0 <= point[1] < shape[1]) for point in (start, anchor)):
        raise ValueError("reroute endpoints outside grid")
    if not arrays["channel_mask"][start] or not arrays["channel_mask"][anchor] or start == anchor:
        raise ValueError("reroute endpoints must be distinct active nodes")
    receiver = arrays["receiver"].copy()
    start_id = np.ravel_multi_index(start, shape); anchor_id = np.ravel_multi_index(anchor, shape)
    old_chain = set()
    cell = start_id
    while cell >= 0 and cell not in old_chain:
        old_chain.add(cell); cell = int(receiver[cell])
    if anchor_id not in old_chain: raise ValueError("anchor must be downstream of source")
    allowed = domain & ~protected
    old_upstream = np.zeros(height.size, bool)
    upstream = [[] for _ in range(receiver.size)]
    for donor, target in enumerate(receiver):
        if target >= 0:
            upstream[int(target)].append(donor)
    stack = [start_id]
    while stack:
        current = stack.pop()
        if old_upstream[current]: continue
        old_upstream[current] = True
        stack.extend(upstream[current])
    allowed.ravel()[old_upstream] = False
    allowed[start] = domain[start] and not protected[start]
    allowed[anchor] = domain[anchor] and not protected[anchor]
    if not allowed[start] or not allowed[anchor]: raise ValueError("reroute endpoint blocked")
    spacing = plan["identity"]["parameters"]
    mesh = grid_mesh(shape, x0_m=spacing["origin_x_m"], z0_m=spacing["origin_z_m"],
        dx_m=spacing["spacing_x_m"], dz_m=spacing["spacing_z_m"], world_seed=spacing.get("world_seed", 20261020))
    mesh = masked_mesh(mesh, allowed)
    distances = {start: 0.0}; previous = {start: None}; heap = [(0.0, start)]
    expansions = 0
    while heap:
        cost, cell = heapq.heappop(heap)
        if cost != distances[cell]: continue
        expansions += 1
        if expansions > recipe.max_expansions: raise ValueError("reroute search exceeds expansion bound")
        if cell == anchor: break
        current_id = cell[0] * shape[1] + cell[1]
        for edge in range(mesh.indptr[current_id], mesh.indptr[current_id + 1]):
            target_id = int(mesh.indices[edge])
            nxt = divmod(target_id, shape[1])
            if (nxt != anchor and arrays["outlet_mask"][nxt] and
                    arrays["discharge_m3_s"][nxt] > 0): continue
            distance = float(mesh.edge_length_m[edge])
            required_cut = max(0., height[nxt] - height[cell] + spacing["min_bed_slope_m_per_m"] * distance)
            if required_cut > recipe.max_extra_cut_m + 1e-9: continue
            next_cost = cost + distance + required_cut * distance
            if next_cost < distances.get(nxt, math.inf):
                distances[nxt] = next_cost; previous[nxt] = cell
                heapq.heappush(heap, (next_cost, nxt))
    if anchor not in previous: raise ValueError("no bounded legal reroute")
    path = []; cell = anchor
    while cell is not None: path.append(cell); cell = previous[cell]
    path.reverse()
    if len(path) > recipe.max_path_cells: raise ValueError("reroute exceeds path bound")
    for current, nxt in zip(path, path[1:]):
        receiver[np.ravel_multi_index(current, shape)] = np.ravel_multi_index(nxt, shape)
    order = []
    seen = np.zeros(receiver.size, np.int8)
    for start_cell in range(receiver.size):
        chain = []
        cell = start_cell
        while cell >= 0 and seen[cell] == 0:
            seen[cell] = 1; chain.append(cell); cell = int(receiver[cell])
        if cell >= 0 and seen[cell] == 1: raise ValueError("reroute creates a cycle")
        for cell in reversed(chain):
            seen[cell] = 2; order.append(cell)
    order = np.array(order, dtype=np.int64)
    outlets = (receiver == -1).reshape(shape)
    route_mesh = grid_mesh(shape, x0_m=spacing["origin_x_m"], z0_m=spacing["origin_z_m"],
        dx_m=spacing["spacing_x_m"], dz_m=spacing["spacing_z_m"], world_seed=spacing.get("world_seed", 20261020))
    _validate_route(receiver, order, shape, outlets, route_mesh)
    q = local_q.copy()
    for cell in order[::-1]:
        target = receiver[cell]
        if target >= 0: q[target] += q[cell]
    if not math.isclose(float(q[receiver < 0].sum()), outlet_total,
                        rel_tol=1e-10, abs_tol=1e-8):
        raise ValueError("rerouted outlet discharge is not conservative")
    channel_recipe = ChannelRecipe(**{name: spacing[name] for name in ChannelRecipe.__dataclass_fields__})
    replanned = plan_channel(height, receiver, order, outlets, q.reshape(shape),
        spacing["spacing_x_m"], spacing["spacing_z_m"], spacing["origin_x_m"], spacing["origin_z_m"],
        spacing["sea_level_elevation_m"], plan["identity_sha256"], channel_recipe)
    if np.any(replanned["arrays"]["channel_mask"] & ~domain) or np.any(replanned["arrays"]["channel_mask"] & protected):
        raise ValueError("rerouted channel violates domain or protection")
    feasible = not bool(np.any(replanned["arrays"]["over_budget_mask"] |
                               replanned["arrays"]["failed_slope_edge_donor_mask"]))
    return {"status": "diagnostic_not_publishable", "path_grid_zx": [list(cell) for cell in path],
            "source_plan_sha256": plan["identity_sha256"], "plan": replanned,
            "summary": {"path_cells": len(path), "new_plan_over_budget_nodes": int(replanned["arrays"]["over_budget_mask"].sum()),
                        "new_failed_slope_edges": int(replanned["arrays"]["failed_slope_edge_donor_mask"].sum()),
                        "bed_plan_feasible": feasible, "search_expansions": expansions}}
