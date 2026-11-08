"""Static basin storage and legal-spill water-balance diagnostic."""

from dataclasses import dataclass
import math

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash
from terrain_pipeline.irregular_grid import grid_mesh, segments_clear


VERSION = "lake-balance-irregular-v2"


@dataclass(frozen=True)
class LakeBalanceRecipe:
    duration_s: float
    inflow_m3_s: float
    loss_m3_s: float
    initial_stage_m: float
    spill_stage_m: float
    max_outflow_m3_s: float

    def __post_init__(self):
        if any(isinstance(v, bool) or not math.isfinite(v) for v in self.__dict__.values()):
            raise ValueError("lake balance values must be finite")
        if (self.duration_s <= 0 or self.inflow_m3_s < 0 or self.loss_m3_s < 0 or
                self.max_outflow_m3_s < 0 or self.spill_stage_m < self.initial_stage_m):
            raise ValueError("invalid lake balance bounds")


def evaluate_lake_balance(height_m, basin_mask, legal_spill_grid_zx, spacing_x_m,
                          spacing_z_m, source_identity, recipe: LakeBalanceRecipe,
                          downstream_path_grid_zx=None, domain_mask=None, protected_mask=None,
                          legal_outlet_mask=None, *, origin_xz_m=(0., 0.), world_seed=20261020):
    """Integrate explicit constant fluxes against measured basin capacity."""
    terrain = np.asarray(height_m, dtype=np.float64)
    basin = np.asarray(basin_mask)
    if (terrain.ndim != 2 or basin.shape != terrain.shape or basin.dtype != bool or
            not np.isfinite(terrain).all() or not basin.any() or
            not math.isfinite(spacing_x_m) or not math.isfinite(spacing_z_m) or
            spacing_x_m <= 0 or spacing_z_m <= 0 or not source_identity):
        raise ValueError("invalid lake terrain or basin")
    spill = tuple(map(int, legal_spill_grid_zx))
    if (len(spill) != 2 or not (0 <= spill[0] < terrain.shape[0] and 0 <= spill[1] < terrain.shape[1]) or
            basin[spill] or abs(terrain[spill] - recipe.spill_stage_m) > 1e-6):
        raise ValueError("spill must be an explicit non-basin saddle at spill stage")
    mesh = grid_mesh(terrain.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
        dx_m=spacing_x_m, dz_m=spacing_z_m, world_seed=world_seed)
    spill_id = int(np.ravel_multi_index(spill, terrain.shape))
    adjacent_spill = mesh.indices[mesh.indptr[spill_id]:mesh.indptr[spill_id + 1]]
    if not basin.ravel()[adjacent_spill].any():
        raise ValueError("spill does not touch basin")
    seen = np.zeros(basin.shape, bool)
    stack = [tuple(np.argwhere(basin)[0])]
    while stack:
        z, x = stack.pop()
        if seen[z, x]: continue
        seen[z, x] = True
        cell_id = z * terrain.shape[1] + x
        for target in mesh.indices[mesh.indptr[cell_id]:mesh.indptr[cell_id + 1]]:
            nz, nx = divmod(int(target), terrain.shape[1])
            if basin[nz,nx] and not seen[nz,nx]:
                stack.append((nz,nx))
    if not np.array_equal(seen, basin): raise ValueError("lake basin is disconnected")
    if downstream_path_grid_zx is None or domain_mask is None or protected_mask is None or legal_outlet_mask is None:
        raise ValueError("explicit downstream path, domain and protection required")
    downstream = np.asarray(downstream_path_grid_zx, dtype=np.int64)
    domain = np.asarray(domain_mask)
    protected = np.asarray(protected_mask)
    legal = np.asarray(legal_outlet_mask)
    if (downstream.ndim != 2 or downstream.shape[1] != 2 or len(downstream) < 2 or
            tuple(downstream[0]) != spill or
            np.any(downstream[:,0] < 0) or np.any(downstream[:,0] >= terrain.shape[0]) or
            np.any(downstream[:,1] < 0) or np.any(downstream[:,1] >= terrain.shape[1]) or
            domain.shape != terrain.shape or
            protected.shape != terrain.shape or legal.shape != terrain.shape or
            domain.dtype != bool or protected.dtype != bool or legal.dtype != bool):
        raise ValueError("invalid downstream spill path or masks")
    if not legal[tuple(downstream[-1])]: raise ValueError("spill path has no legal outlet")
    if (np.any(basin & ~domain) or np.any(basin & protected) or
            np.any(basin[0, :]) or np.any(basin[-1, :]) or
            np.any(basin[:, 0]) or np.any(basin[:, -1])):
        raise ValueError("basin leaves domain, crosses protection or touches grid boundary")
    submerged = basin & (terrain < recipe.spill_stage_m)
    if not np.array_equal(submerged, basin):
        raise ValueError("basin includes cells above spill stage")
    if not domain[spill] or protected[spill]: raise ValueError("spill is outside legal domain")
    for current, nxt in zip(downstream, downstream[1:]):
        z, x = map(int, nxt)
        current_id = int(np.ravel_multi_index(tuple(current), terrain.shape))
        target_id = z * terrain.shape[1] + x
        adjacent = mesh.indices[mesh.indptr[current_id]:mesh.indptr[current_id + 1]]
        if (not (0 <= z < terrain.shape[0] and 0 <= x < terrain.shape[1]) or
                not domain[z, x] or protected[z, x] or basin[z, x] or
                target_id not in adjacent or
                not segments_clear(np.asarray([current_id]), np.asarray([target_id]), domain & ~protected)[0] or
                terrain[z, x] > terrain[tuple(current)] + 1e-9):
            raise ValueError("spill path violates domain, protection or irregular graph adjacency")
    if len({tuple(point) for point in downstream}) != len(downstream):
        raise ValueError("spill path contains a cycle")
    if terrain[tuple(downstream[-1])] > recipe.spill_stage_m + 1e-9:
        raise ValueError("spill path does not reach a lower receiver")
    for z, x in np.argwhere(basin):
        cell_id = z * terrain.shape[1] + x
        for target in mesh.indices[mesh.indptr[cell_id]:mesh.indptr[cell_id + 1]]:
            nz, nx = divmod(int(target), terrain.shape[1])
            if not basin[nz,nx]:
                if (nz,nx) != spill and terrain[nz,nx] < recipe.spill_stage_m - 1e-9:
                    raise ValueError("basin has a lower unmodeled spill")
    area = spacing_x_m * spacing_z_m
    initial_volume = float(np.sum(np.maximum(0., recipe.initial_stage_m - terrain[basin])) * area)
    capacity = float(np.sum(np.maximum(0., recipe.spill_stage_m - terrain[basin])) * area)
    net = (recipe.inflow_m3_s - recipe.loss_m3_s) * recipe.duration_s
    before_spill = initial_volume + net
    overflow = max(0., before_spill - capacity)
    net_rate = recipe.inflow_m3_s - recipe.loss_m3_s
    time_to_spill = ((capacity - initial_volume) / net_rate if net_rate > 0 else math.inf)
    spill_duration = max(0., recipe.duration_s - max(0., time_to_spill))
    outflow = overflow / spill_duration if spill_duration > 0 else 0.
    balance_valid = before_spill >= -1e-9 and outflow <= recipe.max_outflow_m3_s + 1e-9
    final_volume = max(0., min(before_spill, capacity))
    residual = initial_volume + net - overflow - final_volume
    levels = np.unique(np.r_[terrain[basin], recipe.spill_stage_m])
    final_stage = float(levels[0])
    if final_volume >= capacity - 1e-9:
        final_stage = recipe.spill_stage_m
    else:
        cumulative = 0.
        for lower, upper in zip(levels[:-1], levels[1:]):
            wetted = int(np.count_nonzero(terrain[basin] <= lower))
            next_volume = cumulative + wetted * area * (upper - lower)
            if final_volume <= next_volume + 1e-9:
                final_stage = float(lower + (final_volume - cumulative) / (wetted * area))
                break
            cumulative = next_volume
    identity = ArtifactIdentity("Terragenesis", "lake-balance", VERSION, 0,
        {"source_identity": source_identity, "height_sha256": array_hash(terrain),
         "basin_sha256": array_hash(basin), "spill_grid_zx": list(spill),
         "downstream_path_sha256": array_hash(downstream), "domain_sha256": array_hash(domain),
         "protected_sha256": array_hash(protected),
         "legal_outlet_sha256": array_hash(legal),
         "spacing_x_m": float(spacing_x_m), "spacing_z_m": float(spacing_z_m),
         "origin_xz_m": list(map(float, origin_xz_m)), "world_seed": int(world_seed),
         **recipe.__dict__})
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "summary": {
                "initial_volume_m3": initial_volume, "spill_capacity_m3": capacity,
                "final_volume_m3": final_volume, "spill_outflow_m3_s": outflow,
                "final_stage_m": final_stage, "spill_duration_s": spill_duration,
                "balance_residual_m3": residual,
                "balance_valid": balance_valid,
                "limitation": "finite-duration constant supplied fluxes with idealized capped spill; no outlet rating curve or dynamic hydraulics"}}
