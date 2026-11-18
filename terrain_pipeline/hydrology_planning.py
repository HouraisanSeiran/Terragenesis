"""Bounded physical conditioning and experimental frozen catchment products.

The existing continuous physical source supplies all landforms, not Terrain
Diffusion output. Perturbed sites organize finite candidates only. Acceptance
uses unmasked actual irregular-graph; labels never act as impermeable routing barriers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import copy
import hashlib
import heapq
import json
from pathlib import Path

import numpy as np
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers
from terrain_pipeline.drainage import route_graph as route_graph
from diffusion.geography_physical import sample_physical
from diffusion.physical_config import PhysicalGenerationConfig

ALGORITHM_VERSION = "physical-canonical-catchments-v6-irregular"
FORMAT_VERSION = 1

# Single authority for the engineering assumption "deep enough to certify the
# ocean". The old bounded product used a bare `- 100` here and
# `metric_domain_closure` kept a second copy; both now read this default through
# `PlanningConfig.marine_depth_m`. The number has no observational or literature
# source -- it is a declared engineering assumption, not part of the definition
# of sea level.
MARINE_DEPTH_M = 100.0


class PlanningError(ValueError):
    """Finite planning attempt failed; no independent product is published."""


@dataclass(frozen=True)
class PlanningConfig:
    macro_span_m: float = 320_000.0
    samples_per_span: int = 32
    max_grid_cells: int = 70_000
    minimum_lake_depth_m: float = 160.0
    maximum_raise_m: float = 320.0
    maximum_affected_support_fraction: float = 1.0
    maximum_absolute_volume_per_support_area_m: float = 320.0
    ridge_width_fraction: float = 0.17
    sea_level_m: float = 0.0
    marine_depth_m: float = MARINE_DEPTH_M

    def validate(self):
        if not np.isfinite(self.macro_span_m) or self.macro_span_m <= 0:
            raise ValueError("macro_span_m must be finite and positive")
        if not 12 <= self.samples_per_span <= 64:
            raise ValueError("samples_per_span must be 12..64")
        if (4 * self.samples_per_span + 1) ** 2 > self.max_grid_cells:
            raise PlanningError("fixed grid work budget exceeded")
        if not 0.08 <= self.ridge_width_fraction <= 0.3:
            raise ValueError("ridge width must describe a broad landform")
        if not np.isfinite([self.minimum_lake_depth_m, self.maximum_raise_m, self.sea_level_m]).all():
            raise ValueError("nonfinite planning budget")
        if not np.isfinite(self.marine_depth_m) or self.marine_depth_m <= 0:
            raise ValueError("marine_depth_m must be finite and positive")
        if self.minimum_lake_depth_m <= 0 or self.maximum_raise_m < 0:
            raise ValueError("invalid lake/raise budget")
        if not np.isfinite([self.maximum_affected_support_fraction, self.maximum_absolute_volume_per_support_area_m]).all():
            raise ValueError("nonfinite area/volume budget")
        if not 0 <= self.maximum_affected_support_fraction <= 1 or self.maximum_absolute_volume_per_support_area_m < 0:
            raise ValueError("invalid area/volume budget")


def _hash01(seed, cell_x, cell_z, salt):
    with np.errstate(over="ignore"):
        value = np.asarray(cell_x, dtype=np.int64).astype(np.uint64) * np.uint64(0x9E3779B185EBCA87)
        value = value ^ (np.asarray(cell_z, dtype=np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F))
        value = value ^ np.uint64((int(seed) + salt * 104729) & ((1 << 64) - 1))
        value ^= value >> np.uint64(30)
        value *= np.uint64(0xBF58476D1CE4E5B9)
        value ^= value >> np.uint64(27)
        value *= np.uint64(0x94D049BB133111EB)
        value ^= value >> np.uint64(31)
    return (value >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def coarse_condition_field(seed, x_m, z_m, config=None):
    """Return world-coordinate height and nearest macro-cell coordinates.

    Nearest TWO sites use exactly 7x7 candidates. In warped coordinates two
    sites (own grid square and its nearest axial neighbor) lie within 2.32 L;
    omitted sites are >=2.84 L away along one axis. Warp <=.04 L/axis,
    jitter <=.16 L/axis. Thus both nearest sites are in this fixed search.
    """
    config = config or PlanningConfig()
    config.validate()
    span = config.macro_span_m
    x, z = np.broadcast_arrays(np.asarray(x_m, float) / span, np.asarray(z_m, float) / span)
    phase = float(_hash01(seed, 0, 0, 9)) * 2 * np.pi
    wx = x + 0.04 * np.sin(1.1 * z + phase)
    wz = z + 0.04 * np.sin(0.9 * x - phase)
    gx, gz = np.floor(wx).astype(np.int64), np.floor(wz).astype(np.int64)
    first = np.full(x.shape, np.inf)
    second = first.copy()
    owner_x, owner_z = gx.copy(), gz.copy()
    for dz in range(-3, 4):
        for dx in range(-3, 4):
            cx, cz = gx + dx, gz + dz
            sx = cx + 0.5 + 0.32 * (_hash01(seed, cx, cz, 1) - 0.5)
            sz = cz + 0.5 + 0.32 * (_hash01(seed, cx, cz, 2) - 0.5)
            distance = np.hypot(wx - sx, wz - sz)
            nearer = distance < first
            second = np.where(nearer, first, np.minimum(second, distance))
            first = np.minimum(first, distance)
            owner_x = np.where(nearer, cx, owner_x)
            owner_z = np.where(nearer, cz, owner_z)
    # Sites organize bounded candidate lookup only. They never change terrain.
    height = sample_physical(np.asarray(x_m), np.asarray(z_m), int(seed))[0].astype(np.float64)
    height += config.sea_level_m
    return height, owner_x, owner_z


def _flood(height, seeds, mesh=None):
    mesh = grid_mesh(height.shape) if mesh is None else mesh
    outlets = np.zeros(height.shape, bool)
    outlets.ravel()[np.asarray(list(seeds), np.int64)] = True
    try:
        routed = route_graph(height, outlets, mesh)
    except ValueError as error:
        raise PlanningError("no legal terminal within fixed planning support") from error
    working = routed.filled.copy()
    # Explicit tiny working-surface gradient permits strict raw-bed verification.
    working.ravel()[~outlets.ravel()] += routed.rank[~outlets.ravel()] * 1e-7
    receiver, _, _ = strict_receivers(working, mesh, outlet_mask=outlets)
    return working, receiver, list(routed.order)


def _steepest_receivers(height, ocean, lake_seeds, mesh=None):
    mesh = grid_mesh(height.shape) if mesh is None else mesh
    outlets = np.asarray(ocean, bool).copy()
    outlets.ravel()[np.asarray(list(lake_seeds), np.int64)] = True
    return strict_receivers(height, mesh, outlet_mask=outlets)[0]


def _product_mesh(product):
    return grid_mesh(product["height_m"].shape,
        x0_m=product["origin_xz_m"][0], z0_m=product["origin_xz_m"][1],
        dx_m=product["spacing_m"], world_seed=product.get("seed", 20261020))


def _adjacent_nodes(mesh, node):
    return mesh.indices[mesh.indptr[node]:mesh.indptr[node + 1]]


def plan_macro_cell(seed, cell_x=0, cell_z=0, config=None, *, general=False):
    """Plan a complete adjacent pair inside one canonical 4L x 4L support.

    Outside accepted land is -2 (not ocean). Ocean is -1; accepted land
    is grouped by legal coastal versus inland terminal into domains 0 and 1.
    The coastal domain can contain multiple COMPLETE small watersheds.
    """
    config = config or PlanningConfig()
    config.validate()
    span, samples = config.macro_span_m, config.samples_per_span
    spacing = span / samples
    # Center of the nominal grid square; extent +-2L covers the full warped
    # target: own-site distance <=1.641L + site displacement .16L + warp .04L.
    origin = ((cell_x + 0.5 - 2) * span, (cell_z + 0.5 - 2) * span)
    axis = np.arange(4 * samples + 1) * spacing
    x, z = np.meshgrid(origin[0] + axis, origin[1] + axis)
    original, macro_x, macro_z = coarse_condition_field(seed, x, z, config)
    mesh = grid_mesh(original.shape, x0_m=origin[0], z0_m=origin[1], dx_m=spacing, world_seed=int(seed))
    negative = original <= config.sea_level_m
    ocean = np.zeros(original.shape, bool)
    # The physical source defines negative continental shore as an ocean
    # condition, not as a measured inland depression below a geoid.
    # The threshold is read from the config, not the module constant, so the
    # parameter and the answer cannot drift apart.
    certified_sea = original < config.sea_level_m - config.marine_depth_m
    # World continental-field ocean core certifies sea, not support edges.
    # An isolated negative-elevation depression remains an inland candidate.
    pending = [tuple(index) for index in np.argwhere(certified_sea)]
    while pending:
        row, column = pending.pop()
        if ocean[row, column]:
            continue
        ocean[row, column] = True
        for neighbor in _adjacent_nodes(mesh, row * original.shape[1] + column):
            rr, cc = divmod(int(neighbor), original.shape[1])
            if negative[rr, cc] and not ocean[rr, cc]:
                pending.append((rr, cc))
    target = (macro_x == cell_x) & (macro_z == cell_z) & ~ocean
    if not target.any():
        raise PlanningError("macro cell contains no land")
    border = np.zeros(original.shape, bool)
    border[[0, -1], :] = True
    border[:, [0, -1]] = True
    ocean_seeds = np.flatnonzero(ocean)
    if not ocean_seeds.size:
        raise PlanningError("fixed support contains no certified ocean")
    filled_sea, _, _ = _flood(original, ocean_seeds, mesh)
    depth = filled_sea - original
    lake_seeds = []
    lake_spills = {}
    # One terminal per complete physical depression, not per organizing site.
    # A single connected basin can cross many candidate-site cells.
    remaining = (depth > 1e-4) & ~ocean
    for first_index in np.flatnonzero(remaining):
        first_row, first_column = divmod(int(first_index), original.shape[1])
        if not remaining[first_row, first_column]:
            continue
        pending = [(first_row, first_column)]
        component = []
        touches_border = False
        while pending:
            row, column = pending.pop()
            if not remaining[row, column]:
                continue
            remaining[row, column] = False
            component.append(row * original.shape[1] + column)
            touches_border |= bool(border[row, column])
            for neighbor in _adjacent_nodes(mesh, row * original.shape[1] + column):
                rr, cc = divmod(int(neighbor), original.shape[1])
                if remaining[rr, cc]:
                    pending.append((rr, cc))
        indices = np.asarray(component, np.int64)
        if not touches_border and depth.reshape(-1)[indices].max() >= config.minimum_lake_depth_m:
            index = int(indices[np.argmin(original.reshape(-1)[indices])])
            lake_seeds.append(index)
            lake_spills[index] = float(filled_sea.reshape(-1)[index])
    height, receiver, order = _flood(original, list(ocean_seeds) + lake_seeds, mesh)
    # Actual steepest-slope irregular-graph, independent of the priority-flood parent tree.
    receiver = _steepest_receivers(height, ocean, lake_seeds, mesh)
    target_flat = target.reshape(-1)
    ocean_flat = ocean.reshape(-1)
    own_lakes = [i for i in lake_seeds if target_flat[i]]
    if not general and len(own_lakes) != 1:
        raise PlanningError("development pair requires exactly one complete inland lake; found %d" % len(own_lakes))
    lake = own_lakes[0] if own_lakes else None
    terminals = np.full(original.size, -1, np.int64)
    for index in np.argsort(height.reshape(-1), kind="stable"):
        downstream = receiver[index]
        terminals[index] = index if downstream < 0 else terminals[downstream]
    inland = terminals == lake if lake is not None else np.zeros(original.size, bool)
    coastal_terminals = set()
    columns = original.shape[1]
    for index in np.flatnonzero(inland):
        row, column = divmod(int(index), columns)
        for neighbor in _adjacent_nodes(mesh, int(index)):
            terminal = int(terminals[neighbor])
            if terminal >= 0 and ocean_flat[terminal] and not ocean_flat[neighbor]:
                coastal_terminals.add(terminal)
    coastal = np.isin(terminals, sorted(coastal_terminals)) & ~ocean_flat
    selected_terminals = None
    if general:
        selected_terminals = sorted(set(terminals[target_flat].tolist()))
        certified = set(lake_seeds) | set(np.flatnonzero(ocean_flat).tolist())
        selected_terminals = [terminal for terminal in selected_terminals if terminal in certified
                              and not np.any((terminals == terminal) & ~ocean_flat & border.reshape(-1))]
        accepted = np.isin(terminals, selected_terminals) & ~ocean_flat
    else:
        accepted = inland | coastal
    if np.any(accepted & border.reshape(-1)):
        raise PlanningError("complete catchment touches unknown canonical support boundary")
    if not accepted.any():
        raise PlanningError("no complete legal catchment within canonical support")
    if not general and not coastal.any():
        raise PlanningError("no complete adjacent coastal/inland development pair")
    change = height - original
    if float(change.reshape(-1)[accepted].max()) > config.maximum_raise_m:
        raise PlanningError("derived planning terrain exceeds frozen raise budget")
    affected_area = float(np.count_nonzero(change.reshape(-1)[accepted] > 1e-5) * spacing ** 2)
    absolute_volume = float(np.abs(change.reshape(-1)[accepted]).sum() * spacing ** 2)
    support_area = (4 * span) ** 2
    maximum_affected_area = support_area * config.maximum_affected_support_fraction
    maximum_absolute_volume = support_area * config.maximum_absolute_volume_per_support_area_m
    if affected_area > maximum_affected_area or absolute_volume > maximum_absolute_volume:
        raise PlanningError("derived planning terrain exceeds frozen area/volume budget")
    owner = np.full(original.size, -2, np.int32)
    owner[ocean_flat] = -1
    if general:
        for domain_id, terminal in enumerate(selected_terminals):
            owner[accepted & (terminals == terminal)] = domain_id
    else:
        owner[coastal] = 0
        owner[inland] = 1
    target = accepted.reshape(original.shape)
    # Halo corrections are never published as world height.
    height = np.where(target | ocean, height, original)
    receiver = _steepest_receivers(height, ocean, lake_seeds, mesh)
    for index in np.flatnonzero(accepted):
        downstream = receiver[index]
        if downstream >= 0 and not ocean_flat[downstream] and owner[downstream] != owner[index]:
            raise PlanningError("final published terrain drains outside its frozen domain")
    for index in np.flatnonzero(~accepted & ~ocean_flat):
        downstream = receiver[index]
        if downstream >= 0 and accepted[downstream]:
            raise PlanningError("unknown halo contributes inflow to frozen domain")
    edges = []
    columns = original.shape[1]
    for index in np.flatnonzero(owner >= 0):
        row, column = divmod(int(index), columns)
        for dr, dc in ((0, 1), (1, 0)):
            rr, cc = row + dr, column + dc
            if rr < original.shape[0] and cc < columns:
                neighbor = rr * columns + cc
                if owner[neighbor] >= 0 and owner[index] != owner[neighbor]:
                    edges.append((int(index), neighbor))
    if not general and not edges:
        raise PlanningError("coastal and inland domains do not share a divide")
    domains = []
    descriptions = [(domain_id, "inland" if terminal in lake_spills else "coastal", terminal)
                    for domain_id, terminal in enumerate(selected_terminals)] if general else [(0, "coastal", None), (1, "inland", lake)]
    for domain_id, kind, lake_terminal in descriptions:
        indices = np.flatnonzero(owner == domain_id)
        high_sources = indices[np.argsort(original.reshape(-1)[indices])[-3:]]
        domains.append({"domain_id": domain_id, "kind": kind,
                        "terminal_indices": sorted(set(terminals[indices].tolist())),
                        "lake_terminal_index": lake_terminal if kind == "inland" else None,
                        "lake_spill_elevation_m": lake_spills[lake_terminal] if kind == "inland" else None,
                        "area_m2": float(indices.size * spacing ** 2),
                        "source_indices": high_sources.tolist()})
    accumulation_m2 = np.where(accepted, spacing ** 2, 0.0)
    for index in np.argsort(height.reshape(-1))[::-1]:
        downstream = receiver[index]
        if downstream >= 0 and accepted[index] and accepted[downstream]:
            accumulation_m2[downstream] += accumulation_m2[index]
    river_threshold_m2 = 25 * spacing ** 2
    catchments = []
    catchment_index = np.full(original.size, -1, np.int32)
    for terminal in sorted(set(terminals[accepted].tolist())):
        indices = np.flatnonzero(accepted & (terminals == terminal))
        tr, tc = divmod(int(terminal), original.shape[1])
        terminal_world = [origin[0] + tc * spacing, origin[1] + tr * spacing]
        rr, cc = np.divmod(indices, original.shape[1])
        coordinates = np.column_stack((origin[0] + cc * spacing, origin[1] + rr * spacing))
        digest = hashlib.sha256(np.ascontiguousarray(coordinates).tobytes())
        digest.update(np.ascontiguousarray(height.reshape(-1)[indices]).tobytes())
        # Geometry identity is translation independent across canonical supports.
        stable_id = hashlib.sha256(json.dumps([int(seed), ALGORITHM_VERSION, spacing, terminal_world]).encode()).hexdigest()
        catchment_index[indices] = len(catchments)
        catchments.append({"catchment_id": stable_id, "terminal_world_xz_m": terminal_world,
                           "geometry_sha256": digest.hexdigest(), "area_m2": float(indices.size * spacing ** 2),
                           "kind": "inland" if terminal in lake_spills else "coastal"})
    product = {"algorithm_version": ALGORITHM_VERSION, "format_version": FORMAT_VERSION,
               "seed": int(seed), "macro_cell": [int(cell_x), int(cell_z)],
               "canonical_support_id": f"{seed}:{cell_x}:{cell_z}:{ALGORITHM_VERSION}:{'general' if general else 'pair'}",
               "planning_mode": "general" if general else "development_pair",
               "status": "finite_canonical_support" if general else "finite_canonical_pair",
               "origin_xz_m": list(origin), "spacing_m": spacing, "config": asdict(config),
               "height_m": height, "original_height_m": original, "ocean_mask": ocean,
               "owner_domain_id": owner.reshape(original.shape), "receiver": receiver.reshape(original.shape),
               "shared_boundary_edges": np.asarray(edges, np.int64).reshape(-1, 2), "domains": domains,
               "accumulation_area_m2": accumulation_m2.reshape(original.shape),
               "river_mask": (accepted & (accumulation_m2 >= river_threshold_m2)).reshape(original.shape),
               "river_threshold_area_m2": river_threshold_m2,
               "catchments": catchments, "catchment_index": catchment_index.reshape(original.shape),
               "source": {"kind": "geography_physical_v1", "terrain_diffusion": False,
                          "vertical_datum": "synthetic sea datum",
                          "physical_config": PhysicalGenerationConfig().record(),
                          "ocean_identity": ("geography_physical negative shore marine condition, connected to "
                              "depth below -%gm" % config.marine_depth_m), "sea_level_m": config.sea_level_m},
               "budget": {"query_site_candidates": 49, "grid_cells": int(original.size),
                          "flood_passes": 2, "maximum_adjustment_passes": 1,
                          "maximum_dependency_radius_m": 2 * span,
                          "complete_world_coverage": False,
                          "maximum_raise_m": float(change[target].max()),
                          "allowed_maximum_raise_m": config.maximum_raise_m,
                          "allowed_maximum_affected_area_m2": maximum_affected_area,
                          "allowed_maximum_absolute_volume_m3": maximum_absolute_volume,
                          "area_volume_budget_basis": "fixed 4L support structural ceiling; not calibrated naturalness",
                          "absolute_volume_change_m3": float(np.sum(np.abs(change[target])) * spacing ** 2),
                          "affected_area_m2": float(np.count_nonzero(change[target] > 1e-5) * spacing ** 2),
                          "boundary_movement_m": 0.0},
               "limitations": ["physical coarse condition; visual naturalness requires review",
                               "surface coarse drainage only; no underground independence claim",
                               "partial canonical-support pair only; infinite coverage and adjacent canonical products not certified"]}
    validate_plan(product)
    product["identity_sha256"] = _identity(product)
    return product


def plan_canonical_support(seed, cell_x=0, cell_z=0, config=None):
    """Prepare all complete terminal catchments intersecting a candidate cell.

    Unlike development-pair selection, pure coast and multiple inland lakes
    are legitimate products. Unknown/open catchments are excluded explicitly.
    Physical conflicts or insufficient budgets reject the fixed attempt.
    """
    return plan_macro_cell(seed, cell_x, cell_z, config, general=True)


def select_development_pair(support, lake_domain_id=None):
    """Read-only view of adjacent complete coastal and inland catchments.

    The canonical terrain stays unchanged, including all derived support
    corrections and their full budget. This selection changes presentation
    grouping only; it never cuts rivers, invents outlets or reshapes terrain.
    """
    validate_plan(support)
    owner = support["owner_domain_id"].reshape(-1)
    candidate_lakes = [domain["domain_id"] for domain in support["domains"] if domain["kind"] == "inland"]
    if lake_domain_id is not None:
        candidate_lakes = [int(lake_domain_id)] if int(lake_domain_id) in candidate_lakes else []
    coastal_ids = {domain["domain_id"] for domain in support["domains"] if domain["kind"] == "coastal"}
    selected_lake, adjacent = None, set()
    for lake_id in candidate_lakes:
        neighbors = set()
        for first, second in support["shared_boundary_edges"]:
            a, b = int(owner[first]), int(owner[second])
            if a == lake_id and b in coastal_ids:
                neighbors.add(b)
            if b == lake_id and a in coastal_ids:
                neighbors.add(a)
        if neighbors:
            selected_lake, adjacent = lake_id, neighbors
            break
    if selected_lake is None:
        raise PlanningError("general support has no complete adjacent coastal/inland pair")
    result = copy.deepcopy(support)
    result.pop("identity_sha256", None)
    new_owner = np.full(owner.shape, -2, np.int32)
    new_owner[owner == -1] = -1
    new_owner[np.isin(owner, sorted(adjacent))] = 0
    new_owner[owner == selected_lake] = 1
    result["owner_domain_id"] = new_owner.reshape(support["owner_domain_id"].shape)
    coast = [domain for domain in support["domains"] if domain["domain_id"] in adjacent]
    lake = copy.deepcopy(support["domains"][selected_lake])
    lake["domain_id"] = 1
    result["domains"] = [{"domain_id": 0, "kind": "coastal",
                          "terminal_indices": sorted({index for domain in coast for index in domain["terminal_indices"]}),
                          "lake_terminal_index": None, "lake_spill_elevation_m": None,
                          "area_m2": sum(domain["area_m2"] for domain in coast),
                          "source_indices": [index for domain in coast for index in domain["source_indices"]]}, lake]
    indices = support["catchment_index"].reshape(-1)
    new_index = np.full(indices.shape, -1, np.int32)
    result["catchments"] = []
    for previous in sorted(set(indices[new_owner >= 0].tolist())):
        new_index[(indices == previous) & (new_owner >= 0)] = len(result["catchments"])
        result["catchments"].append(copy.deepcopy(support["catchments"][previous]))
    result["catchment_index"] = new_index.reshape(result["owner_domain_id"].shape)
    edges = [tuple(edge) for edge in support["shared_boundary_edges"]
             if new_owner[edge[0]] >= 0 and new_owner[edge[1]] >= 0 and new_owner[edge[0]] != new_owner[edge[1]]]
    result["shared_boundary_edges"] = np.asarray(edges, np.int64).reshape(-1, 2)
    result["river_mask"] &= result["owner_domain_id"] >= 0
    result["status"] = "finite_canonical_pair_view"
    result["selection"] = {"parent_identity": support["identity_sha256"], "lake_domain_id": selected_lake,
                           "terrain_changed": False, "budget_scope": "entire_parent_support"}
    validate_plan(result)
    result["identity_sha256"] = _identity(result)
    return result


ARRAY_KEYS = ("height_m", "original_height_m", "ocean_mask", "owner_domain_id", "receiver", "shared_boundary_edges", "accumulation_area_m2", "river_mask", "catchment_index")


def _identity(product):
    metadata = {k: v for k, v in product.items() if k not in ARRAY_KEYS and k != "identity_sha256"}
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
    for key in ARRAY_KEYS:
        if key not in product:
            continue
        array = np.ascontiguousarray(product[key])
        digest.update(key.encode())
        digest.update(str(array.dtype).encode())
        digest.update(str(array.shape).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def validate_plan(product):
    height = np.asarray(product["height_m"])
    original = np.asarray(product["original_height_m"])
    owner = np.asarray(product["owner_domain_id"]).reshape(-1)
    receiver = np.asarray(product["receiver"]).reshape(-1)
    ocean = np.asarray(product["ocean_mask"]).reshape(-1)
    if height.shape != original.shape or height.ndim != 2 or not np.isfinite(height).all():
        raise ValueError("invalid frozen height")
    if any(np.asarray(product[key]).shape != height.shape for key in ("ocean_mask", "owner_domain_id", "receiver")):
        raise ValueError("inconsistent planning shapes")
    flat = height.reshape(-1)
    lakes = [domain["lake_terminal_index"] for domain in product["domains"]
             if domain["lake_terminal_index"] is not None]
    actual = _steepest_receivers(height, np.asarray(product["ocean_mask"]), lakes, _product_mesh(product))
    if np.any(receiver[owner >= 0] != actual[owner >= 0]):
        raise ValueError("frozen receiver differs from actual steepest irregular-graph")
    for index in np.flatnonzero(owner >= 0):
        downstream = int(receiver[index])
        if downstream >= 0:
            if downstream >= flat.size or flat[downstream] >= flat[index]:
                raise ValueError("receiver must be strictly downhill")
            if not ocean[downstream] and owner[downstream] != owner[index]:
                raise ValueError("cross-domain land drainage")
        elif index not in product["domains"][int(owner[index])]["terminal_indices"]:
            raise ValueError("uncertified terminal")
    if "identity_sha256" in product and product["identity_sha256"] != _identity(product):
        raise ValueError("frozen planning identity mismatch")
    return True


def query_macro_cell(seed, x_m, z_m, config=None):
    """Return a bounded candidate site, not finalized world ownership.

    Frozen catchments can cross this site's Voronoi organizing boundary.
    Infinite-world ownership and adjacent canonical support reconciliation
    are deliberately not certified by this experimental pair planner.
    """
    if not np.isfinite([x_m, z_m]).all():
        raise ValueError("query coordinates must be finite")
    _, cx, cz = coarse_condition_field(seed, x_m, z_m, config)
    return int(cx), int(cz)


def query_frozen_domain(product, x_m, z_m):
    """Read-only sampled ownership. Ocean=-1, outside prepared land=-2."""
    x0, z0 = product["origin_xz_m"]
    spacing = product["spacing_m"]
    column, row = int(np.floor((x_m - x0) / spacing + 0.5)), int(np.floor((z_m - z0) / spacing + 0.5))
    shape = product["height_m"].shape
    if not (0 <= row < shape[0] and 0 <= column < shape[1]):
        raise ValueError("outside fixed prepared support")
    return int(product["owner_domain_id"][row, column])


def edit_domain_height(product, domain_id, delta_height_m):
    """Apply an explicit bounded interior edit or reject drainage changes.

    All eight-neighbor external boundary cells and all terminal cells remain
    frozen. Outside-domain height, ownership and sources stay byte-identical.
    The returned product records a new identity; the input stays immutable.
    """
    validate_plan(product)
    if domain_id not in {domain["domain_id"] for domain in product["domains"]}:
        raise ValueError("unknown domain")
    delta = np.asarray(delta_height_m, dtype=np.float64)
    if delta.shape != product["height_m"].shape or not np.isfinite(delta).all():
        raise ValueError("invalid edit shape or nonfinite values")
    owner = product["owner_domain_id"]
    domain = owner == domain_id
    interior = domain.copy()
    rows, columns = domain.shape
    mesh = _product_mesh(product)
    for index in np.flatnonzero(domain.ravel()):
        if not np.all(domain.ravel()[_adjacent_nodes(mesh, int(index))]):
            interior.ravel()[index] = False
    interior[[0, -1], :] = False
    interior[:, [0, -1]] = False
    for index in product["domains"][domain_id]["terminal_indices"]:
        interior.reshape(-1)[index] = False
    if np.any(delta[~interior] != 0):
        raise PlanningError("edit changes a frozen boundary or another domain")
    edited = copy.deepcopy(product)
    edited.pop("identity_sha256", None)
    edited["height_m"] = product["height_m"] + delta
    change = edited["height_m"] - product["original_height_m"]
    accepted = owner >= 0
    if np.max(np.abs(change[accepted])) > product["config"]["maximum_raise_m"]:
        raise PlanningError("edit exceeds frozen total terrain adjustment budget")
    absolute_volume = float(np.abs(change[accepted]).sum() * product["spacing_m"] ** 2)
    affected_area = float(np.count_nonzero(np.abs(change[accepted]) > 1e-5) * product["spacing_m"] ** 2)
    if absolute_volume > product["budget"].get("allowed_maximum_absolute_volume_m3", np.inf) or affected_area > product["budget"].get("allowed_maximum_affected_area_m2", np.inf):
        raise PlanningError("edit exceeds frozen total area/volume budget")
    lakes = [item["lake_terminal_index"] for item in product["domains"]
             if item["lake_terminal_index"] is not None]
    actual = _steepest_receivers(edited["height_m"], product["ocean_mask"], lakes, _product_mesh(product))
    receiver = product["receiver"].copy().reshape(-1)
    receiver[domain.reshape(-1)] = actual[domain.reshape(-1)]
    # Editing A must not change actual irregular-graph of B or unknown halo.
    other = ~domain.reshape(-1)
    previous_actual = _steepest_receivers(product["height_m"], product["ocean_mask"], lakes, _product_mesh(product))
    if np.any(actual[other] != previous_actual[other]):
        raise PlanningError("edit changes neighboring drainage")
    original_terminals = np.full(owner.size, -1, np.int64)
    edited_terminals = np.full(owner.size, -1, np.int64)
    for index in np.argsort(product["height_m"], axis=None, kind="stable"):
        downstream = previous_actual[index]
        original_terminals[index] = index if downstream < 0 else original_terminals[downstream]
    for index in np.argsort(edited["height_m"], axis=None, kind="stable"):
        downstream = actual[index]
        edited_terminals[index] = index if downstream < 0 else edited_terminals[downstream]
    if np.any(original_terminals[domain.reshape(-1)] != edited_terminals[domain.reshape(-1)]):
        raise PlanningError("edit changes frozen terminal catchment ownership")
    edited["receiver"] = receiver.reshape(owner.shape)
    if "catchments" in edited:
        columns = owner.shape[1]
        x0, z0 = product["origin_xz_m"]
        spacing = product["spacing_m"]
        for catchment_number, catchment in enumerate(edited["catchments"]):
            indices = np.flatnonzero(product["catchment_index"].reshape(-1) == catchment_number)
            rr, cc = np.divmod(indices, columns)
            coordinates = np.column_stack((x0 + cc * spacing, z0 + rr * spacing))
            geometry = hashlib.sha256(np.ascontiguousarray(coordinates).tobytes())
            geometry.update(np.ascontiguousarray(edited["height_m"].reshape(-1)[indices]).tobytes())
            catchment["geometry_sha256"] = geometry.hexdigest()
        accumulation = np.where(owner.reshape(-1) >= 0, spacing ** 2, 0.0)
        for index in np.argsort(edited["height_m"], axis=None)[::-1]:
            downstream = receiver[index]
            if downstream >= 0 and owner.reshape(-1)[index] >= 0 and owner.reshape(-1)[downstream] >= 0:
                accumulation[downstream] += accumulation[index]
        edited["accumulation_area_m2"] = accumulation.reshape(owner.shape)
        edited["river_mask"] = (owner >= 0) & (edited["accumulation_area_m2"] >= product["river_threshold_area_m2"])
    edited["edit"] = {"domain_id": domain_id, "parent_identity": product["identity_sha256"],
                      "maximum_absolute_delta_m": float(np.max(np.abs(delta)))}
    edited["budget"]["absolute_volume_change_m3"] = float(np.abs(change[accepted]).sum() * product["spacing_m"] ** 2)
    edited["budget"]["maximum_raise_m"] = float(change[accepted].max())
    edited["budget"]["affected_area_m2"] = float(np.count_nonzero(np.abs(change[accepted]) > 1e-5) * product["spacing_m"] ** 2)
    validate_plan(edited)
    edited["identity_sha256"] = _identity(edited)
    return edited


class FrozenPlanningCatalog:
    """Explicit prepared-product catalog; queries never generate terrain.

    Each product owns only sampled catchment footprints in its canonical
    support. A continuous point samples the globally aligned nearest grid
    center. Exactly 25 possible nominal supports cover that point; unknown
    and conflicting land remain explicit failure states. This is a partial
    world registry, not a claim that all coordinates are already planned.
    """

    def __init__(self, seed, config=None):
        self.seed = int(seed)
        self.config = config or PlanningConfig()
        self.config.validate()
        self._products = {}
        self._rejections = {}
        self._conflicts = {}

    def register(self, product):
        validate_plan(product)
        if product["algorithm_version"] != ALGORITHM_VERSION or "catchments" not in product:
            raise ValueError("catalog requires current canonical catchment algorithm")
        if product["seed"] != self.seed or product["config"] != asdict(self.config):
            raise ValueError("catalog seed/config identity mismatch")
        cell = tuple(product["macro_cell"])
        existing = self._products.get(cell)
        if existing is not None and existing["identity_sha256"] != product["identity_sha256"]:
            raise PlanningError("canonical support already registered with another identity")
        # Snapshot arrays so editing a caller's local copy cannot change queries.
        frozen = copy.deepcopy(product)
        for value in frozen.values():
            if isinstance(value, np.ndarray):
                value.setflags(write=False)
        if cell in self._rejections:
            raise PlanningError("canonical support has a frozen failed attempt")
        for dz in range(-3, 4):
            for dx in range(-3, 4):
                other_cell = (cell[0] + dx, cell[1] + dz)
                other = self._products.get(other_cell)
                if other is None or other_cell == cell:
                    continue
                reason = _support_pair_conflict(frozen, other)
                if reason is not None:
                    pair = tuple(sorted((cell, other_cell)))
                    self._conflicts[pair] = reason
        self._products[cell] = frozen

    def register_rejection(self, cell_x, cell_z, reason):
        """Freeze a bounded failed attempt in this algorithm/config revision."""
        cell = (int(cell_x), int(cell_z))
        if cell in self._products:
            raise PlanningError("cannot replace a prepared canonical support by rejection")
        self._rejections[cell] = str(reason)

    def prepare_query_candidates(self, x_m, z_m):
        """Explicitly attempt all 25 supports once, including frozen failures.

        Query itself is read-only. This is a bounded partial preparation:
        rejected cells leave land unplanned; success is never forced by merge.
        """
        span = self.config.macro_span_m
        cell_x, cell_z = int(np.floor(x_m / span)), int(np.floor(z_m / span))
        for dz in range(-2, 3):
            for dx in range(-2, 3):
                cell = (cell_x + dx, cell_z + dz)
                if cell in self._products or cell in self._rejections:
                    continue
                try:
                    product = plan_canonical_support(self.seed, *cell, self.config)
                except PlanningError as failure:
                    self.register_rejection(*cell, str(failure))
                else:
                    self.register(product)
        # A claim can conflict with any support whose 4L rectangle overlaps it.
        # Resolve those fixed 7x7 support neighborhoods before accepting it.
        query = self.query(x_m, z_m)
        for cell in query["missing_compatibility_candidates"]:
            cell = tuple(cell)
            try:
                product = plan_canonical_support(self.seed, *cell, self.config)
            except PlanningError as failure:
                self.register_rejection(*cell, str(failure))
            else:
                self.register(product)
        return self.query(x_m, z_m)

    def query(self, x_m, z_m):
        if not np.isfinite([x_m, z_m]).all():
            raise ValueError("query coordinates must be finite")
        span = self.config.macro_span_m
        cell_x, cell_z = int(np.floor(x_m / span)), int(np.floor(z_m / span))
        candidates = [(cell_x + dx, cell_z + dz)
                      for dz in range(-2, 3) for dx in range(-2, 3)]
        claims = []
        claimed_cells = []
        ocean_seen = False
        for cell in candidates:
            product = self._products.get(cell)
            if product is None:
                continue
            try:
                domain_id = query_frozen_domain(product, x_m, z_m)
            except ValueError:
                continue
            if domain_id >= 0:
                claimed_cells.append(cell)
                x0, z0 = product["origin_xz_m"]
                column = int(np.floor((x_m - x0) / product["spacing_m"] + 0.5))
                row = int(np.floor((z_m - z0) / product["spacing_m"] + 0.5))
                catchment = product["catchments"][int(product["catchment_index"][row, column])]
                claims.append({"canonical_support_id": product["canonical_support_id"],
                               "identity_sha256": product["identity_sha256"],
                               "catchment_id": catchment["catchment_id"],
                               "geometry_sha256": catchment["geometry_sha256"],
                               "domain_id": domain_id})
            ocean_seen |= domain_id == -1
        # Without all potential overlapping products, a land claim is provisional.
        missing = [list(cell) for cell in candidates
                   if cell not in self._products and cell not in self._rejections]
        compatibility_candidates = set()
        for cx, cz in claimed_cells:
            compatibility_candidates.update((cx + dx, cz + dz)
                                            for dz in range(-3, 4) for dx in range(-3, 4))
        missing_compatibility = [list(cell) for cell in sorted(compatibility_candidates)
                                 if cell not in self._products and cell not in self._rejections]
        unique_claims = set((claim["catchment_id"], claim["geometry_sha256"]) for claim in claims)
        status = "conflict" if len(unique_claims) > 1 else "unprepared"
        if len(unique_claims) == 1:
            status = "provisional" if missing or missing_compatibility else "owned"
        elif not claims and ocean_seen:
            status = "provisional_ocean" if missing else "ocean"
        if claims and ocean_seen:
            status = "conflict"
        relevant_conflicts = []
        local_pairs = set()
        for cx, cz in claimed_cells:
            for dz in range(-3, 4):
                for dx in range(-3, 4):
                    other_cell = (cx + dx, cz + dz)
                    if other_cell != (cx, cz):
                        local_pairs.add(tuple(sorted(((cx, cz), other_cell))))
        for pair in sorted(local_pairs):
            reason = self._conflicts.get(pair)
            if reason is not None:
                relevant_conflicts.append({"macro_cells": [list(cell) for cell in pair], "reason": reason})
        if relevant_conflicts:
            status = "conflict"
        return {"status": status, "claims": claims, "missing_candidates": missing,
                "owner_catchment_id": next(iter(unique_claims))[0] if len(unique_claims) == 1 else None,
                "missing_compatibility_candidates": missing_compatibility,
                "compatibility_candidate_count": len(compatibility_candidates),
                "maximum_preparation_candidates": 121,
                "support_conflicts": relevant_conflicts,
                "rejected_candidates": [{"macro_cell": list(cell), "reason": self._rejections[cell]}
                                        for cell in candidates if cell in self._rejections],
                "candidate_count": 25, "complete_world_coverage": False}


def _support_pair_conflict(first, second):
    """Symmetric local physical compatibility of two globally aligned products."""
    spacing = first["spacing_m"]
    ax, az = first["origin_xz_m"]
    bx, bz = second["origin_xz_m"]
    dx, dz = int(round((bx - ax) / spacing)), int(round((bz - az) / spacing))
    rows, columns = first["height_m"].shape
    x0, z0 = max(0, dx), max(0, dz)
    x1, z1 = min(columns, dx + columns), min(rows, dz + rows)
    if x1 <= x0 or z1 <= z0:
        return None
    sa = (slice(z0, z1), slice(x0, x1))
    sb = (slice(z0 - dz, z1 - dz), slice(x0 - dx, x1 - dx))
    if not np.array_equal(first["original_height_m"][sa], second["original_height_m"][sb]):
        return "shared source-height mismatch"
    own_a = first["owner_domain_id"][sa] >= 0
    own_b = second["owner_domain_id"][sb] >= 0
    if np.any(own_a & second["ocean_mask"][sb]) or np.any(own_b & first["ocean_mask"][sa]):
        return "inconsistent land versus certified ocean identity"
    for row, column in np.argwhere(own_a & own_b):
        ca = first["catchments"][int(first["catchment_index"][sa][row, column])]
        cb = second["catchments"][int(second["catchment_index"][sb][row, column])]
        if ca["catchment_id"] != cb["catchment_id"]:
            return "different terminal catchments claim the same land"
        if ca["geometry_sha256"] != cb["geometry_sha256"]:
            return "same terminal has inconsistent complete footprint or geometry"
    if not own_a.any() or not own_b.any():
        return None
    common = first["original_height_m"][sa].copy()
    common[own_a] = first["height_m"][sa][own_a]
    common[own_b] = second["height_m"][sb][own_b]
    sea = first["ocean_mask"][sa] | second["ocean_mask"][sb]
    common_origin = [first["origin_xz_m"][0] + x0 * first["spacing_m"],
                     first["origin_xz_m"][1] + z0 * first["spacing_m"]]
    joint_mesh = grid_mesh(common.shape, x0_m=common_origin[0], z0_m=common_origin[1],
        dx_m=first["spacing_m"], world_seed=first["seed"])
    joint_receiver = strict_receivers(common, joint_mesh, outlet_mask=sea)[0]
    # Compare actual irregular-graph slopes on overlap interior; outside it neither support's
    # derived footprint can affect the other's graph routing.
    for row, column in np.argwhere(own_a | own_b):
        if row == 0 or column == 0 or row == common.shape[0] - 1 or column == common.shape[1] - 1:
            continue
        product = first if own_a[row, column] else second
        pr, pc = (row + z0, column + x0) if product is first else (row + z0 - dz, column + x0 - dx)
        index = pr * columns + pc
        downstream = int(product["receiver"].reshape(-1)[index])
        if downstream < 0:
            continue
        candidate = int(joint_receiver[row * common.shape[1] + column])
        chosen = divmod(candidate, common.shape[1]) if candidate >= 0 else (-1, -1)
        rr, cc = divmod(downstream, columns)
        expected = (rr - z0, cc - x0) if product is first else (rr - z0 + dz, cc - x0 + dx)
        if chosen != expected:
            return "joint derived terrain changes frozen actual irregular-graph"
    return None


def save_plan(product, path):
    validate_plan(product)
    path = Path(path)
    metadata = {k: v for k, v in product.items() if k not in ARRAY_KEYS}
    if path.exists():
        raise FileExistsError(path)
    temporary = path.with_name(path.name + ".tmp")
    try:
        with temporary.open("wb") as stream:
            np.savez_compressed(stream, metadata=np.array(json.dumps(metadata, sort_keys=True)),
                                **{key: product[key] for key in ARRAY_KEYS if key in product})
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_plan(path):
    with np.load(path, allow_pickle=False) as archive:
        product = json.loads(str(archive["metadata"].item()))
        product.update({key: archive[key].copy() for key in ARRAY_KEYS if key in archive})
    validate_plan(product)
    return product
