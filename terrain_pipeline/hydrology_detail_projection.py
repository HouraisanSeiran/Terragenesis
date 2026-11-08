"""Canonical finite TD-preserving macro projection; CPU only.

The LP retains the full actual TD residual as its interior target. A fixed
world interface transition replaces query-specific fitting. Missing source,
incompatible interfaces and unsatisfied drainage constraints fail explicitly.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import warnings

import numpy as np
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers
from scipy import sparse
from scipy.optimize import OptimizeWarning, linprog
from scipy.ndimage import distance_transform_edt

from terrain_pipeline.hydrology_detail import DIRECTIONS, _coordinates, _interpolate, _steepest_receivers, required_td_nodes
from terrain_pipeline.hydrology_detail_ridge import continuous_macro_field, stage_fixed_transform
from terrain_pipeline.td_source import CORE, QUERY_SIZE, HYDROLOGY_TD_ALGORITHM as SOURCE_ALGORITHM
from terrain_pipeline.common_infra import checked_archive


ALGORITHM = "canonical-td-full-residual-constrained-projection-v5-irregular"
TARGET_WITNESS_ALGORITHM = "td-full-residual-constrained-projection-v5-irregular-target-witness"
MACRO_WITNESS_POLICY = "macro-steepest-v1"
TARGET_WITNESS_POLICY = "target-steepest-macro-decreasing-v1"
LOCAL_TRIBUTARY_ALGORITHM = ALGORITHM + "-local-tributary-v1"
FROZEN_RIVER_GRADE_M_PER_M = 0.001
HALO = 2
SUPPORT = CORE + 2 * HALO
REFERENCE_ACCEPTANCE_SIDE = 97
REFERENCE_ACCEPTANCE_VOLUME_M3 = 4_500_000_000.0
FULL_SUPPORT_VOLUME_M3 = REFERENCE_ACCEPTANCE_VOLUME_M3 * SUPPORT ** 2 / REFERENCE_ACCEPTANCE_SIDE ** 2
COASTAL_SUFFIX_MAX_STEPS = 2 * HALO + 1


class ProjectionError(ValueError):
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = {"reason": message, **(diagnostics or {})}


@dataclass(frozen=True)
class ProjectionConfig:
    macro_max_abs_m: float = 512.0
    macro_absolute_volume_m3: float = FULL_SUPPORT_VOLUME_M3
    transition_width_m: float = 1000.0
    min_drop_m: float = 1e-5
    cross_slope_margin: float = 1e-7
    max_slope_m_per_m: float = 0.75
    time_limit_s: float = 60.0
    max_nodes: int = SUPPORT * SUPPORT
    max_constraints: int = 1_000_000
    max_nonzeros: int = 4_000_000

    def __post_init__(self):
        values = asdict(self)
        if any(not np.isfinite(value) or value <= 0 for value in values.values()):
            raise ValueError("positive finite projection budgets required")
        if self.transition_width_m < 1000:
            raise ValueError("global interface transition must be at least 1000 m")


def _digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _identity(metadata, arrays):
    return _digest({"metadata": {key: value for key, value in metadata.items() if key != "identity"},
                    "arrays": {key: hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
                               for key, value in sorted(arrays.items())}})


def load_cached_support(generation_metadata, *, tile_x, tile_z):
    """Read exactly the existing nine source cores; never instantiate a backend."""
    if type(tile_x) is not int or type(tile_z) is not int:
        raise ValueError("integer canonical core coordinates required")
    contract = generation_metadata.get("canonical_source_contract", {})
    if (contract.get("algorithm") != SOURCE_ALGORITHM or contract.get("core_size") != CORE
            or contract.get("inference_query_size") != QUERY_SIZE
            or generation_metadata.get("artifact_kind") != "terrain_diffusion_output"
            or generation_metadata.get("identity") != _digest(contract)):
        raise ProjectionError("original canonical TD source contract required")
    seed = str(int(generation_metadata["seed"]) & ((1 << 64) - 1))
    root = Path(generation_metadata["canonical_cache_root"]) / generation_metadata["identity"] / seed
    origin = (tile_x * CORE - HALO, tile_z * CORE - HALO)
    raw = np.empty((SUPPORT, SUPPORT), np.float64)
    records = []
    missing = []
    for tz in range(tile_z - 1, tile_z + 2):
        for tx in range(tile_x - 1, tile_x + 2):
            path = root / f"tile-x{tx}-z{tz}.npz"
            pin = path.with_suffix(".sha256")
            if not path.is_file() or not pin.is_file():
                missing.append(str(path))
                continue
            sha = pin.read_text(encoding="ascii").strip()
            arrays = checked_archive(path, expected_sha256=sha)
            if set(arrays) != {"elevation_m", "climate", "metadata_json"}:
                raise ProjectionError("cached TD component archive fields mismatch", {"path": str(path)})
            meta = json.loads(str(arrays["metadata_json"].item()))
            elevation = np.asarray(arrays["elevation_m"])
            climate = np.asarray(arrays["climate"])
            base_record = {key: value for key, value in meta.items() if key not in {
                "identity", "seed", "native_origin", "shape", "native_resolution_m", "artifact_kind", "seconds"}}
            if (meta.get("identity") != contract["base_generation_identity"]
                    or _digest(base_record) != meta.get("identity")
                    or str(meta.get("seed")) != seed or meta.get("native_origin") != [tx * CORE, tz * CORE]
                    or meta.get("shape") != [QUERY_SIZE, QUERY_SIZE]
                    or meta.get("artifact_kind") != "terrain_diffusion_output"
                    or meta.get("native_resolution_m") != 30.0
                    or elevation.shape != (QUERY_SIZE, QUERY_SIZE) or not np.isfinite(elevation).all()
                    or climate.shape != (5, QUERY_SIZE, QUERY_SIZE) or not np.isfinite(climate).all()):
                raise ProjectionError("cached TD component contract mismatch", {"path": str(path)})
            left, right = max(origin[0], tx * CORE), min(origin[0] + SUPPORT, (tx + 1) * CORE)
            top, bottom = max(origin[1], tz * CORE), min(origin[1] + SUPPORT, (tz + 1) * CORE)
            raw[top - origin[1]:bottom - origin[1], left - origin[0]:right - origin[0]] = elevation[
                top - tz * CORE:bottom - tz * CORE, left - tx * CORE:right - tx * CORE]
            records.append({"tile_xz": [tx, tz], "path": str(path), "sha256": sha})
    if missing:
        raise ProjectionError("canonical support source is not prepared", {"status": "source_unprepared", "missing_tiles": missing, "maximum_source_tiles": 9})
    return raw, {"canonical_source_identity": generation_metadata["identity"], "seed": seed,
                 "native_origin": list(origin), "shape": [SUPPORT, SUPPORT],
                 "native_resolution_m": 30.0, "artifact_kind": "terrain_diffusion_output",
                 "tile_assembly": records, "maximum_source_tiles": 9, "td_inference_run": False}


def _witness(macro, owners, ocean, terminal, core, spacing, *, target=None, pinned=None,
             policy=MACRO_WITNESS_POLICY, min_drop_m=1e-5, mesh=None):
    """Select a legal strictly descending edge on the shared graph."""
    mesh = grid_mesh(macro.shape, dx_m=spacing) if mesh is None else mesh
    receiver = np.full(macro.size, -1, np.int64)
    for node in range(macro.size):
        if terminal.ravel()[node]:
            continue
        edges = np.arange(mesh.indptr[node], mesh.indptr[node + 1])
        nodes = mesh.indices[edges]
        legal = (owners.ravel()[nodes] == owners.ravel()[node]) | ocean.ravel()[nodes]
        slopes = (macro.ravel()[node] - macro.ravel()[nodes]) / mesh.edge_length_m[edges]
        candidates = np.flatnonzero(legal & (slopes > 0.))
        if candidates.size:
            best = min(candidates, key=lambda k: (-slopes[k], nodes[k]))
            receiver[node] = nodes[best]
    missing = core.ravel() & ~terminal.ravel() & (receiver < 0)
    if missing.any():
        raise ProjectionError("global macro has no legal downhill graph witness",
                              {"unresolved_core_cells": int(missing.sum())})
    if policy == MACRO_WITNESS_POLICY:
        return receiver.reshape(macro.shape)
    if policy != TARGET_WITNESS_POLICY:
        raise ValueError("explicit supported projection witness policy required")
    target, pinned = np.asarray(target, float), np.asarray(pinned, bool)
    if target.shape != macro.shape or pinned.shape != macro.shape or not np.isfinite(target).all():
        raise ValueError("target witness requires aligned finite target and pinned mask")
    eligible = (core.ravel() & ~terminal.ravel() & ~pinned.ravel()
                & ~pinned.ravel()[np.maximum(receiver, 0)])
    for node in np.flatnonzero(eligible):
        edges = np.arange(mesh.indptr[node], mesh.indptr[node + 1])
        nodes = mesh.indices[edges]
        drop = target.ravel()[node] - target.ravel()[nodes]
        legal = ((owners.ravel()[nodes] == owners.ravel()[node]) | ocean.ravel()[nodes])
        legal &= (~pinned.ravel()[nodes] & (macro.ravel()[node] > macro.ravel()[nodes])
                  & (drop >= min_drop_m))
        candidates = np.flatnonzero(legal)
        if candidates.size:
            slopes = drop / mesh.edge_length_m[edges]
            receiver[node] = nodes[min(candidates, key=lambda k: (-slopes[k], nodes[k]))]
    return receiver.reshape(macro.shape)


def _fixed_neighbor_receivers(macro, pinned, spacing, mesh=None):
    mesh = grid_mesh(macro.shape, dx_m=spacing) if mesh is None else mesh
    return strict_receivers(macro, mesh, valid_mask=pinned)[0].reshape(macro.shape)


def frozen_river_derivative_constraints(plan, shape, origin_xz_m, spacing_m, terminal_mask, *, additional_source_edges=None):
    """Exact continuous downhill rows for frozen coarse lines in native cells.

    Along a straight line, each bilinear cell has a quadratic height profile.
    Its derivative is linear, so checking both ends proves the whole segment.
    Geometry comes from complete world-defined frozen edges, independent of a
    detail query. Only the canonical source rectangle clips their support.
    """
    rows, columns = shape
    origin = np.asarray(origin_xz_m, dtype=float)
    maximum = origin + (np.array(shape)[::-1] - 1) * spacing_m
    terminal = np.asarray(terminal_mask, dtype=bool)
    if terminal.shape != tuple(shape) or not np.isfinite(origin).all() or spacing_m <= 0:
        raise ValueError("aligned frozen river constraint support required")
    coarse_shape = np.asarray(plan["height_m"]).shape
    receiver = np.asarray(plan["receiver"]).ravel()
    river = np.asarray(plan.get("river_mask", np.zeros(coarse_shape, bool))).ravel()
    owner = np.asarray(plan["owner_domain_id"]).ravel()
    index_parts, coefficient_parts, point_parts, edge_parts = [], [], [], []
    segment_count, excluded_segments, represented_length, excluded_length = 0, 0, 0.0, 0.0
    source_edges = {(int(first), int(receiver[first])) for first in np.flatnonzero(river & (receiver >= 0))}
    if additional_source_edges is not None:
        for first, second in additional_source_edges:
            if not 0 <= first < receiver.size or not 0 <= second < receiver.size or receiver[first] != second:
                raise ProjectionError("additional valley line is not an actual frozen receiver edge")
            source_edges.add((int(first), int(second)))
    for first, second in sorted(source_edges):
        if owner[first] != owner[second] and owner[second] != -1:
            raise ProjectionError("frozen river edge crosses registered domain ownership")
        start = np.asarray(plan["origin_xz_m"]) + np.array([first % coarse_shape[1], first // coarse_shape[1]]) * plan["spacing_m"]
        finish = np.asarray(plan["origin_xz_m"]) + np.array([second % coarse_shape[1], second // coarse_shape[1]]) * plan["spacing_m"]
        vector = finish - start
        edge_length = float(np.linalg.norm(vector))
        if edge_length <= 0:
            raise ProjectionError("frozen river edge has zero length")
        lo, hi = 0.0, 1.0
        for axis in range(2):
            if vector[axis] == 0:
                if not origin[axis] <= start[axis] <= maximum[axis]:
                    hi = -1.0
                    break
            else:
                limits = sorted(((origin[axis] - start[axis]) / vector[axis], (maximum[axis] - start[axis]) / vector[axis]))
                lo, hi = max(lo, limits[0]), min(hi, limits[1])
        if hi <= lo:
            continue
        # Native grid intersections are world-defined, not interval subdivisions
        # rescaled by the query length. Both shared cores see the same cell rows.
        breaks = [lo, hi]
        for axis in range(2):
            if vector[axis] == 0:
                continue
            lower, upper = sorted((start[axis] + lo * vector[axis], start[axis] + hi * vector[axis]))
            grid = np.arange(int(np.ceil(lower / spacing_m)), int(np.floor(upper / spacing_m)) + 1) * spacing_m
            breaks.extend(((grid - start[axis]) / vector[axis]).tolist())
        breaks = np.unique(np.clip(breaks, lo, hi))
        direction = vector / edge_length
        for a, b in zip(breaks[:-1], breaks[1:]):
            length = (b - a) * edge_length
            if length <= 1e-8:
                continue
            midpoint = start + (a + b) / 2 * vector
            cx, cz = np.floor((midpoint - origin) / spacing_m).astype(int)
            cx, cz = min(max(cx, 0), columns - 2), min(max(cz, 0), rows - 2)
            indices = np.array([cz * columns + cx, cz * columns + cx + 1,
                                (cz + 1) * columns + cx, (cz + 1) * columns + cx + 1])
            if terminal.ravel()[indices].any():
                excluded_segments += 1
                excluded_length += length
                continue
            points = start + np.array([a, b])[:, None] * vector
            local = (points - (origin + np.array([cx, cz]) * spacing_m)) / spacing_m
            coefficients = []
            for x, z in local:
                dx = np.array([-(1 - z), 1 - z, -z, z])
                dz = np.array([-(1 - x), -x, 1 - x, x])
                coefficients.append((direction[0] * dx + direction[1] * dz) / spacing_m)
            index_parts.append(np.broadcast_to(indices, (2, 4)))
            coefficient_parts.append(np.asarray(coefficients))
            point_parts.append(points)
            edge_parts.append(np.tile([int(first), second], (2, 1)))
            segment_count += 1
            represented_length += length
    indices = np.concatenate(index_parts) if index_parts else np.empty((0, 4), dtype=np.int64)
    coefficients = np.concatenate(coefficient_parts) if coefficient_parts else np.empty((0, 4), dtype=float)
    return {"columns": indices, "coefficients": coefficients,
            "rhs": np.full(len(indices), -FROZEN_RIVER_GRADE_M_PER_M),
            "world_xz_m": np.concatenate(point_parts) if point_parts else np.empty((0, 2)),
            "source_edges": np.concatenate(edge_parts) if edge_parts else np.empty((0, 2), dtype=np.int64),
            "metadata": {"algorithm": "continuous-bilinear-frozen-edge-cell-end-derivatives-v1",
                         "minimum_grade_m_per_m": FROZEN_RIVER_GRADE_M_PER_M,
                         "derivative_rows": len(indices), "nonzero_coefficients": int(np.count_nonzero(coefficients)),
                         "native_cell_segments": segment_count, "dry_constrained_length_m": represented_length,
                         "registered_terminal_stencil_excluded_segments": excluded_segments,
                         "registered_terminal_stencil_excluded_length_m": excluded_length,
                         "scope": "full frozen world edge lines clipped to canonical support; wet/ocean native cells excluded",
                         "pin_policy": "fixed elevations remain exact; no frozen river row waiver",
                         "continuous_proof": "bilinear height along each straight native-cell segment is quadratic; both endpoint derivatives bound its linear derivative"}}


def frozen_river_valley_floor_constraints(plan, shape, origin_xz_m, spacing_m, terminal_mask, *, source_edges):
    """Sampled macro valley floor: center cannot exceed either 15m bank.

    These macro rows prepare the cross slope before the separate 4m fine cut.
    They are not a continuous fine triangle floor certificate.
    """
    origin = np.asarray(origin_xz_m, float)
    rows, columns = shape
    maximum = origin + (np.array(shape)[::-1] - 1) * spacing_m
    coarse_columns = np.asarray(plan["height_m"]).shape[1]
    indices, coefficients, points = [], [], []

    def weights(point):
        local = (point - origin) / spacing_m
        cx, cz = np.minimum(np.floor(local).astype(int), [columns-2, rows-2])
        x, z = local - [cx, cz]
        ids = [cz*columns+cx, cz*columns+cx+1, (cz+1)*columns+cx, (cz+1)*columns+cx+1]
        return ids, [(1-x)*(1-z), x*(1-z), (1-x)*z, x*z]

    for first, second in source_edges:
        start = np.asarray(plan["origin_xz_m"]) + np.array([first % coarse_columns, first // coarse_columns])*plan["spacing_m"]
        finish = np.asarray(plan["origin_xz_m"]) + np.array([second % coarse_columns, second // coarse_columns])*plan["spacing_m"]
        vector = finish-start
        length = np.linalg.norm(vector)
        normal = np.array([-vector[1], vector[0]])/length
        for fraction in np.linspace(0,1,int(np.ceil(length/15))+1):
            center = start+fraction*vector
            for side in (-1,1):
                bank = center+side*15*normal
                if np.any(center<origin) or np.any(center>maximum) or np.any(bank<origin) or np.any(bank>maximum):
                    continue
                ci,cw=weights(center)
                bi,bw=weights(bank)
                if terminal_mask.ravel()[ci+bi].any():
                    continue
                indices.append(ci+bi)
                coefficients.append(cw+[-value for value in bw])
                points.append(center.tolist())
    return {"columns":np.asarray(indices,np.int64).reshape(-1,8),
            "coefficients":np.asarray(coefficients,float).reshape(-1,8),
            "rhs":np.zeros(len(indices)), "world_xz_m":points,
            "metadata":{"algorithm":"sampled-macro-center-below-15m-banks-v1", "sample_spacing_m":15.,
                        "bank_offset_m":15., "scope":"macro preparation rows; independent fine continuous floor still required"}}


def audit_neighbor_slopes(height, pinned, spacing_m, *, maximum_modifiable_slope=.75,
                          origin_xz_m=(0., 0.), world_seed=20261020):
    """Cold-check all modifiable neighbor pairs and observe immutable world pairs."""
    height = np.asarray(height, float)
    pinned = np.asarray(pinned, bool)
    if height.ndim != 2 or pinned.shape != height.shape or not np.isfinite(height).all():
        raise ValueError("aligned finite height and pinned mask required")
    mesh = grid_mesh(height.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                     dx_m=spacing_m, world_seed=world_seed)
    source = np.repeat(np.arange(height.size), np.diff(mesh.indptr))
    selected = source < mesh.indices
    source, destination = source[selected], mesh.indices[selected]
    immutable = pinned.ravel()[source] & pinned.ravel()[destination]
    slopes = np.abs(height.ravel()[source] - height.ravel()[destination]) / mesh.edge_length_m[selected]
    maximum = float(slopes[~immutable].max(initial=0))
    fixed = [{"edge_set": "irregular_graph",
              "maximum_actual_fixed_slope_m_per_m": float(slopes[immutable].max(initial=0)),
              "fixed_pair_above_internal_limit_count": int(np.sum(immutable & (slopes > maximum_modifiable_slope + 1e-12)))}]
    if maximum > maximum_modifiable_slope + 1e-8:
        raise ValueError("modifiable neighbor slope exceeds frozen bound")
    return {"maximum_modifiable_neighbor_slope_m_per_m":maximum,
            "fixed_world_boundary_actual_slope_diagnostics":fixed}


def project_arrays(original_td_m, target_height_m, macro_height_m, owner_domain_id, ocean_mask,
                   terminal_mask, core_mask, pinned_mask, *, spacing_m, config=None,
                   lower_height_m=None, upper_height_m=None, frozen_river_constraints=None,
                   fixed_boundary_slope_policy="strict", frozen_valley_constraints=None,
                   witness_policy=MACRO_WITNESS_POLICY, frozen_channel_constraints=None,
                   gradient_policy=None, origin_xz_m=(0., 0.), world_seed=20261020):
    """Bounded sparse LP engine. Array fixtures do not claim genuine TD provenance."""
    config = config or ProjectionConfig()
    if fixed_boundary_slope_policy not in ("strict", "diagnostic_only"):
        raise ValueError("explicit fixed-boundary slope policy required")
    original, target, macro = [np.asarray(value, np.float64) for value in (original_td_m, target_height_m, macro_height_m)]
    shape = original.shape
    if len(shape) != 2 or min(shape) < 3 or original.size > config.max_nodes:
        raise ProjectionError("projection node work budget exceeded")
    owners = np.asarray(owner_domain_id, np.int32)
    ocean, terminal, core, pinned = [np.asarray(value, bool) for value in (ocean_mask, terminal_mask, core_mask, pinned_mask)]
    if any(value.shape != shape for value in (target, macro, owners, ocean, terminal, core, pinned)):
        raise ValueError("aligned finite projection arrays required")
    if not all(np.isfinite(value).all() for value in (original, target, macro)) or not np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("finite projection elevations and positive spacing required")
    if np.any(owners < -1) or np.any(core[[0, -1], :]) or np.any(core[:, [0, -1]]):
        raise ProjectionError("core requires fully known ownership and a fixed halo")
    low, high = original - config.macro_max_abs_m, original + config.macro_max_abs_m
    if lower_height_m is not None:
        low = np.maximum(low, np.asarray(lower_height_m, float))
    if upper_height_m is not None:
        high = np.minimum(high, np.asarray(upper_height_m, float))
    high[ocean] = np.minimum(high[ocean], -1e-6)
    incompatible = pinned & ((macro < low) | (macro > high))
    if incompatible.any() or np.any(low > high):
        raise ProjectionError("shared macro interface exceeds frozen elevation or water bounds",
                              {"incompatible_pins": int(incompatible.sum()), "maximum_pinned_change_m": float(np.abs(macro[pinned] - original[pinned]).max(initial=0))})
    low[pinned], high[pinned] = macro[pinned], macro[pinned]
    mesh = grid_mesh(shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1], dx_m=spacing_m, world_seed=world_seed)
    witness = _witness(macro, owners, ocean, terminal, core, spacing_m,
                       target=target, pinned=pinned, policy=witness_policy, min_drop_m=config.min_drop_m, mesh=mesh)
    fixed_receiver = _fixed_neighbor_receivers(macro, pinned, spacing_m, mesh).ravel()
    fixed_destination = np.maximum(fixed_receiver, 0)
    fixed_legal = (fixed_receiver >= 0) & ((owners.ravel() == owners.ravel()[fixed_destination]) | ocean.ravel()[fixed_destination])
    fixed_competition_waivers = []
    n = original.size
    ids = np.arange(n).reshape(shape)
    row_parts, col_parts, data_parts, rhs_parts = [], [], [], []
    count = 0
    fixed_slope_diagnostics = []

    def add(columns, coefficients, rhs):
        nonlocal count
        rhs = np.atleast_1d(np.asarray(rhs, float))
        length = rhs.size
        row = np.arange(count, count + length, dtype=np.int64)
        for column, coefficient in zip(columns, coefficients):
            row_parts.append(row)
            col_parts.append(np.broadcast_to(np.asarray(column, np.int64), (length,)))
            data_parts.append(np.broadcast_to(np.asarray(coefficient, float), (length,)))
        rhs_parts.append(rhs)
        count += length

    flat = np.arange(n)
    add((flat, n + flat), (1., -1.), target.ravel())
    add((flat, n + flat), (-1., -1.), -target.ravel())
    add((flat, 2 * n + flat), (1., -1.), original.ravel())
    add((flat, 2 * n + flat), (-1., -1.), -original.ravel())
    active = np.flatnonzero((core & ~terminal).ravel())
    q = witness.ravel()[active]
    add((q, active), (1., -1.), np.full(active.size, -config.min_drop_m))
    rows, cols = shape
    source_nodes = np.repeat(np.arange(n), np.diff(mesh.indptr))
    target_nodes = mesh.indices
    neighbor_lengths = mesh.edge_length_m
    safe_witness = np.maximum(witness.ravel(), 0)
    lengths = np.hypot(mesh.node_x_m - mesh.node_x_m[safe_witness],
                       mesh.node_z_m - mesh.node_z_m[safe_witness])
    crossing = (core.ravel()[source_nodes] & ~terminal.ravel()[source_nodes]
                & ~ocean.ravel()[target_nodes]
                & (owners.ravel()[source_nodes] != owners.ravel()[target_nodes]))
    i, j = source_nodes[crossing], target_nodes[crossing]
    neighbor_length = neighbor_lengths[crossing]
    qi = witness.ravel()[i]
    own_length = lengths[i]
    coefficient = 1 / neighbor_length - 1 / own_length
    fixed = pinned.ravel()[i] & pinned.ravel()[j] & pinned.ravel()[qi]
    fixed_lhs = (coefficient * macro.ravel()[i] - macro.ravel()[j] / neighbor_length
                 + macro.ravel()[qi] / own_length)
    waive = fixed & fixed_legal[i] & (fixed_lhs > -config.cross_slope_margin)
    for source, competitor, witness_index in zip(i[waive], j[waive], qi[waive]):
        fixed_competition_waivers.append({"source_index": int(source), "competitor_index": int(competitor),
            "witness_index": int(witness_index), "fixed_actual_receiver": int(fixed_receiver[source]),
            "reason": "constant elevations certify legal actual graph receiver"})
    keep = ~waive
    i, j, qi = i[keep], j[keep], qi[keep]
    own_length, coefficient, neighbor_length = own_length[keep], coefficient[keep], neighbor_length[keep]
    add((i, j, qi), (coefficient, -1 / neighbor_length, 1 / own_length),
        np.full(i.size, -config.cross_slope_margin))
    unique = source_nodes < target_nodes
    i, j = source_nodes[unique], target_nodes[unique]
    neighbor_length = neighbor_lengths[unique]
    bound = config.max_slope_m_per_m * neighbor_length
    fixed = pinned.ravel()[i] & pinned.ravel()[j]
    actual_fixed = np.abs(macro.ravel()[i] - macro.ravel()[j]) / neighbor_length
    fixed_slope_diagnostics.append({"edge_set": "irregular_graph", "fixed_pair_count": int(fixed.sum()),
        "maximum_actual_fixed_slope_m_per_m": float(actual_fixed[fixed].max(initial=0)),
        "fixed_pair_above_internal_limit_count": int(np.sum(fixed & (actual_fixed > config.max_slope_m_per_m + 1e-12)))})
    if fixed_boundary_slope_policy == "diagnostic_only":
        i, j, bound = i[~fixed], j[~fixed], bound[~fixed]
    add((i, j), (1., -1.), bound)
    add((i, j), (-1., 1.), bound)
    river_residual = 0.0
    if frozen_river_constraints is not None:
        river_columns = np.asarray(frozen_river_constraints["columns"], np.int64)
        river_coefficients = np.asarray(frozen_river_constraints["coefficients"], float)
        river_rhs = np.asarray(frozen_river_constraints["rhs"], float)
        if (river_columns.shape != (len(river_rhs), 4) or river_coefficients.shape != river_columns.shape
                or np.any(river_columns < 0) or np.any(river_columns >= n)
                or not np.isfinite(river_coefficients).all() or not np.isfinite(river_rhs).all()):
            raise ValueError("finite sparse frozen river derivative rows required")
        fixed_rows = np.all(pinned.ravel()[river_columns] | (river_coefficients == 0), axis=1)
        fixed_residual = np.sum(river_coefficients * macro.ravel()[river_columns], axis=1) - river_rhs
        incompatible_rows = fixed_rows & (fixed_residual > 1e-9)
        if incompatible_rows.any():
            raise ProjectionError("fixed interface cannot satisfy frozen river continuous descent",
                {"incompatible_river_rows": int(incompatible_rows.sum()),
                 "maximum_fixed_river_derivative_residual_m_per_m": float(fixed_residual[incompatible_rows].max()),
                 "river_constraints": frozen_river_constraints["metadata"]})
        add(tuple(river_columns.T), tuple(river_coefficients.T), river_rhs)
    # One hard full-support volume gate, including interface and halo changes.
    if frozen_valley_constraints is not None:
        valley_columns = np.asarray(frozen_valley_constraints["columns"], np.int64)
        valley_coefficients = np.asarray(frozen_valley_constraints["coefficients"], float)
        valley_rhs = np.asarray(frozen_valley_constraints["rhs"], float)
        if (valley_columns.shape != (len(valley_rhs),8) or valley_coefficients.shape != valley_columns.shape
                or np.any(valley_columns < 0) or np.any(valley_columns >= n)
                or not np.isfinite(valley_coefficients).all() or not np.isfinite(valley_rhs).all()):
            raise ValueError("macro valley rows require eight bilinear sample coefficients")
        add(tuple(valley_columns.T), tuple(valley_coefficients.T), valley_rhs)
    if gradient_policy not in (None, "target-neighbor-gradient-l1-v1"):
        raise ValueError("explicit projection gradient policy required")
    gradient_first, gradient_second = [], []
    if gradient_policy is not None:
        for first, second in ((ids[:-1, :], ids[1:, :]), (ids[:, :-1], ids[:, 1:])):
            keep = ~(pinned.ravel()[first] & pinned.ravel()[second])
            gradient_first.append(first[keep])
            gradient_second.append(second[keep])
        gradient_first = np.concatenate(gradient_first)
        gradient_second = np.concatenate(gradient_second)
        gradient_target = target.ravel()[gradient_second] - target.ravel()[gradient_first]
        gradient_variables = 3*n + np.arange(len(gradient_first))
        add((gradient_second, gradient_first, gradient_variables), (1., -1., -1.), gradient_target)
        add((gradient_second, gradient_first, gradient_variables), (-1., 1., -1.), -gradient_target)
    gradient_count = len(gradient_first) if gradient_policy is not None else 0
    variable_count = 3*n + gradient_count
    channel_residual = 0.0
    if frozen_channel_constraints is not None:
        channel_columns = np.asarray(frozen_channel_constraints["columns"], np.int64)
        channel_coefficients = np.asarray(frozen_channel_constraints["coefficients"], float)
        channel_rhs = np.asarray(frozen_channel_constraints["rhs"], float)
        if (channel_columns.shape != (len(channel_rhs), 8) or channel_coefficients.shape != channel_columns.shape
                or np.any(channel_columns < 0) or np.any(channel_columns >= n)
                or not np.isfinite(channel_coefficients).all() or not np.isfinite(channel_rhs).all()):
            raise ValueError("frozen channel feasibility rows require eight finite bilinear coefficients")
        fixed = np.all(pinned.ravel()[channel_columns] | (channel_coefficients == 0), axis=1)
        fixed_residual = np.sum(channel_coefficients * macro.ravel()[channel_columns], axis=1) - channel_rhs
        incompatible = fixed & (fixed_residual > 1e-9)
        if incompatible.any():
            raise ProjectionError("fixed interface cannot satisfy frozen channel feasibility",
                {"incompatible_channel_rows": int(incompatible.sum()),
                 "maximum_fixed_channel_residual_m": float(fixed_residual[incompatible].max())})
        add(tuple(channel_columns.T), tuple(channel_coefficients.T), channel_rhs)
    row_parts.append(np.full(n, count, np.int64))
    col_parts.append(2 * n + flat)
    data_parts.append(np.full(n, spacing_m ** 2))
    rhs_parts.append(np.array([config.macro_absolute_volume_m3]))
    count += 1
    nonzeros = sum(part.size for part in data_parts)
    if count > config.max_constraints or nonzeros > config.max_nonzeros:
        raise ProjectionError("projection sparse work budget exceeded", {"constraints": count, "nonzeros": nonzeros})
    matrix = sparse.coo_matrix((np.concatenate(data_parts), (np.concatenate(row_parts), np.concatenate(col_parts))),
                              shape=(count, variable_count)).tocsr()
    matrix.eliminate_zeros()
    objective = np.r_[np.zeros(n), np.ones(n), np.zeros(n), np.ones(gradient_count)]
    bounds = np.column_stack((np.r_[low.ravel(), np.zeros(2*n+gradient_count)], np.r_[high.ravel(), np.full(2*n+gradient_count, np.inf)]))
    # SciPy forwards these supported HiGHS execution options verbatim.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Unrecognized options detected:.*threads.*parallel.*", category=OptimizeWarning)
        solution = linprog(objective, A_ub=matrix, b_ub=np.concatenate(rhs_parts), bounds=bounds,
                           method="highs", options={"time_limit": config.time_limit_s, "presolve": True,
                                                    "primal_feasibility_tolerance": 1e-9,
                                                    "dual_feasibility_tolerance": 1e-9,
                                                    "threads": 1, "parallel": False})
    if not solution.success:
        raise ProjectionError("canonical projection constraints not solved", {"solver_status": int(solution.status),
                              "solver_message": str(solution.message), "constraints": count, "nonzeros": nonzeros})
    height = solution.x[:n].reshape(shape)
    if frozen_valley_constraints is not None:
        residual = np.sum(valley_coefficients * height.ravel()[valley_columns],axis=1)-valley_rhs
        if residual.max(initial=0) > 1e-7:
            raise ProjectionError("LP solution failed independent macro valley floor acceptance")
    if frozen_river_constraints is not None:
        river_residual = float((np.sum(river_coefficients * height.ravel()[river_columns], axis=1) - river_rhs).max(initial=0))
        if river_residual > 1e-7:
            raise ProjectionError("LP solution failed independent frozen river continuous descent",
                {"maximum_river_derivative_residual_m_per_m": river_residual})
    if frozen_channel_constraints is not None:
        channel_residual = float((np.sum(channel_coefficients * height.ravel()[channel_columns], axis=1) - channel_rhs).max(initial=0))
        if channel_residual > 1e-7:
            raise ProjectionError("LP solution failed independent frozen channel feasibility",
                {"maximum_channel_residual_m": channel_residual})
    actual = _steepest_receivers(height, spacing_m, origin_xz_m=origin_xz_m, world_seed=world_seed)
    actual_flat = actual.ravel()
    destination = np.maximum(actual_flat, 0)
    cross = core.ravel() & ~terminal.ravel() & (actual_flat >= 0) & ~ocean.ravel()[destination] & (owners.ravel() != owners.ravel()[destination])
    sinks = core & ~terminal & (actual < 0)
    if cross.any() or sinks.any():
        raise ProjectionError("LP solution failed independent actual irregular-graph acceptance", {"crossing_count": int(cross.sum()), "sink_count": int(sinks.sum())})
    delta = height - original
    absolute_volume = float(np.abs(delta).sum() * spacing_m ** 2)
    if (np.abs(delta).max() > config.macro_max_abs_m + 1e-6
            or absolute_volume > config.macro_absolute_volume_m3 + 1e-6
            or np.max(np.abs(height[pinned] - macro[pinned]), initial=0) > 1e-8):
        raise ProjectionError("LP solution failed independent frozen budget or interface acceptance")
    ledger = {"macro_max_abs_m": float(np.abs(delta).max()),
              "macro_absolute_volume_m3": absolute_volume,
              "core_absolute_volume_m3": float(np.abs(delta[core]).sum() * spacing_m ** 2),
              "target_l1_change_m": float(np.abs(height - target).sum()),
              "target_unchanged_core_fraction": float(np.mean(np.abs(height[core] - target[core]) <= 1e-6)),
              "maximum_frozen_river_derivative_residual_m_per_m": river_residual,
              "cross_domain_d8_count": 0, "unplanned_interior_sink_count": 0}
    if frozen_channel_constraints is not None:
        ledger["maximum_frozen_channel_feasibility_residual_m"] = channel_residual
    if gradient_policy is not None:
        ledger["target_neighbor_gradient_l1_change_m"] = float(np.abs(height.ravel()[gradient_second]-height.ravel()[gradient_first]-gradient_target).sum())
    return {"arrays": {"original_td_m": original.copy(), "target_height_m": target.copy(),
                       "macro_height_m": macro.copy(), "projection_height_m": height,
                       "macro_delta_m": delta, "owner_domain_id": owners.copy(), "ocean_mask": ocean.copy(),
                       "terminal_mask": terminal.copy(), "core_mask": core.copy(), "pinned_mask": pinned.copy(),
                       "witness_receiver": witness, "actual_receiver": actual},
            "metadata": {"algorithm": ("canonical-td-target-gradient-preserving-projection-v5" if gradient_policy is not None else "canonical-td-frozen-channel-feasibility-projection-v4" if frozen_channel_constraints is not None
                                       else ALGORITHM if witness_policy == MACRO_WITNESS_POLICY else TARGET_WITNESS_ALGORITHM),
                         **({"gradient_policy": gradient_policy, "gradient_objective": {"neighbor_directions": [[1,0],[0,1]], "fixed_fixed_pairs": "excluded", "relation_weight": 1.0, "height_weight": 1.0, "units": "m", "pairs": gradient_count}} if gradient_policy is not None else {}),
                         **({"frozen_channel_feasibility_constraints": frozen_channel_constraints["metadata"]} if frozen_channel_constraints is not None else {}),
                         **({"witness_policy": witness_policy} if witness_policy != MACRO_WITNESS_POLICY else {}),
                         "status": "accepted_canonical_projection", "world_seed": world_seed,
                         "routing_origin_xz_m": list(origin_xz_m), "routing_spacing_m": spacing_m,
                         "config": asdict(config), "ledger": ledger, "solver": "scipy.optimize.linprog/highs",
                         "nodes": n, "constraints": count, "nonzeros": nonzeros,
                         "fixed_competition_waivers": fixed_competition_waivers,
                         "fixed_boundary_slope_policy": fixed_boundary_slope_policy,
                         "fixed_boundary_actual_slope_diagnostics": fixed_slope_diagnostics,
                         "macro_valley_floor_constraints": None if frozen_valley_constraints is None else frozen_valley_constraints["metadata"],
                         "frozen_river_constraints": None if frozen_river_constraints is None else frozen_river_constraints["metadata"],
                         "scope": "exported core only; halo is fixed interface support",
                         "global_hydrology_certified": False}}


def _coarse_terminal_certificate(plan):
    height = np.asarray(plan["height_m"]).ravel()
    owner = np.asarray(plan["owner_domain_id"]).ravel()
    receiver = np.asarray(plan["receiver"]).ravel()
    ocean = np.asarray(plan["ocean_mask"]).ravel()
    terminals = np.full(height.size, -1, np.int64)
    ranks = np.zeros(height.size, np.int64)
    registered = {int(index) for domain in plan["domains"] for index in domain["terminal_indices"]}
    for index in np.argsort(height, kind="stable"):
        if ocean[index]:
            terminals[index] = index
        elif owner[index] >= 0:
            q = int(receiver[index])
            if q < 0:
                if index not in registered:
                    raise ProjectionError("unregistered coarse terminal")
                terminals[index] = index
            else:
                if q >= height.size or height[q] >= height[index] or (not ocean[q] and owner[q] != owner[index]) or terminals[q] < 0:
                    raise ProjectionError("coarse continuation DAG is not certified")
                terminals[index] = terminals[q]
                ranks[index] = ranks[q] + 1
    return terminals, ranks


def _coarse_port_progress(receiver, terminals, ranks, source, destination):
    """Certified finite progress; the continuous fan may join another branch."""
    if terminals[source] < 0 or terminals[destination] != terminals[source]:
        raise ProjectionError("halo continuation changes the certified coarse terminal")
    if source != destination and ranks[destination] >= ranks[source]:
        raise ProjectionError("halo continuation does not decrease certified coarse rank")
    return {"coarse_progress": "within_same_coarse_cell" if source == destination else "same_terminal_lower_rank",
            "coarse_rank_drop": int(ranks[source] - ranks[destination]),
            "halo_coarse_receiver": int(receiver[destination]),
            "halo_coarse_remaining_receiver_steps": int(ranks[destination])}


def _coastal_suffix(plan, native_start_xz, terminal_index, domain_id, *, spacing_m, lake_level_m,
                    nearest_coastal_indices):
    """Trace a bounded actual irregular-graph suffix whose complete neighborhoods are pinned."""
    native_x, native_z = map(int, native_start_xz)
    columns = np.asarray(plan["height_m"]).shape[1]
    trace = []
    radius = 6
    diameter = 2 * radius + 1
    for step in range(COASTAL_SUFFIX_MAX_STEPS + 1):
        world_origin = [(native_x - radius) * spacing_m, (native_z - radius) * spacing_m]
        try:
            x, z = _coordinates(plan, world_origin, (diameter, diameter), spacing_m)
        except ValueError as error:
            raise ProjectionError("coastal continuation exceeds frozen world support") from error
        macro = stage_fixed_transform(continuous_macro_field(plan, x, z), lake_level_m)
        cx, cz = np.rint(x).astype(int), np.rint(z).astype(int)
        coarse_index = int(cz[radius, radius] * columns + cx[radius, radius])
        ocean = (_interpolate(np.asarray(plan["ocean_mask"], float), x, z) > 0) & (macro < 0)
        trace.append({"native_xz": [native_x, native_z], "world_xz_m": [native_x * spacing_m, native_z * spacing_m],
                      "height_m": float(macro[radius, radius]), "coarse_cell": coarse_index})
        nx, nz = np.meshgrid(native_x + np.arange(-radius, radius + 1), native_z + np.arange(-radius, radius + 1))
        rem_x, rem_z = np.mod(nx, CORE), np.mod(nz, CORE)
        distance = np.minimum(np.minimum(rem_x, CORE - rem_x), np.minimum(rem_z, CORE - rem_z))
        if distance[radius, radius] > HALO:
            raise ProjectionError("coastal continuation requires unpinned world elevations")
        if ocean[radius, radius]:
            registered_support = np.zeros(np.asarray(plan["height_m"]).shape, float)
            registered_support.ravel()[terminal_index] = 1.0
            if _interpolate(registered_support, x, z)[radius, radius] <= 0:
                raise ProjectionError("coastal continuation reaches a different registered marine terminal")
            return {"kind": "registered_coastal_extension_continuation_not_outlet",
                    "registered_marine_terminal": int(terminal_index), "macro_suffix": trace,
                    "macro_suffix_steps": step, "maximum_macro_suffix_steps": COASTAL_SUFFIX_MAX_STEPS,
                    "coarse_progress": "bounded_globally_pinned_actual_graph_suffix_to_registered_marine_terminal"}
        coarse_owner = np.asarray(plan["owner_domain_id"])
        owners = coarse_owner[cz, cx].copy()
        extension = (owners == -1) & ~ocean
        nearest_owner = coarse_owner[nearest_coastal_indices[0], nearest_coastal_indices[1]][cz, cx]
        owners[extension] = nearest_owner[extension]
        if owners[radius, radius] != domain_id:
            raise ProjectionError("coastal continuation changes the registered coastal owner")
        mesh = grid_mesh(macro.shape, x0_m=world_origin[0], z0_m=world_origin[1],
                         dx_m=spacing_m, world_seed=plan.get("seed", 20261020))
        center = radius * diameter + radius
        neighbors = mesh.indices[mesh.indptr[center]:mesh.indptr[center + 1]]
        if np.any(distance.ravel()[neighbors] > HALO):
            raise ProjectionError("coastal continuation requires unpinned world elevations")
        q = int(_steepest_receivers(macro, spacing_m, origin_xz_m=world_origin,
                                   world_seed=plan.get("seed", 20261020))[radius, radius])
        if q < 0:
            raise ProjectionError("coastal continuation has an unregistered fixed macro sink")
        row, col = divmod(q, diameter)
        if not ocean[row, col] and owners[row, col] != domain_id:
            raise ProjectionError("coastal continuation leaves its registered coastal owner")
        if macro[row, col] >= macro[radius, radius]:
            raise ProjectionError("coastal continuation does not strictly decrease fixed macro height")
        native_x += col - radius
        native_z += row - radius
    raise ProjectionError("coastal continuation exceeds its frozen finite step budget")


def _validate_port(plan, result, coarse_ids, terminals, ranks, source, destination, *, coastal_context=None):
    arrays = result["arrays"]
    height, macro, pinned, owner, ocean = [arrays[key].ravel() for key in (
        "projection_height_m", "macro_height_m", "pinned_mask", "owner_domain_id", "ocean_mask")]
    if (not pinned[source] or not pinned[destination]
            or abs(height[source] - macro[source]) > 1e-8
            or abs(height[destination] - macro[destination]) > 1e-8
            or macro[destination] >= macro[source]):
        raise ProjectionError("core to halo continuation does not follow the fixed downhill macro interface")
    source_cell = int(coarse_ids.ravel()[source])
    destination_cell = int(coarse_ids.ravel()[destination])
    if ocean[destination]:
        coastal = {domain["domain_id"] for domain in plan["domains"] if domain["kind"] == "coastal"}
        source_reference = source_cell
        if coastal_context is not None and coastal_context["extension_mask"].ravel()[source]:
            source_reference = int(coastal_context["nearest_coastal_cell"].ravel()[source])
        terminal = int(terminals[source_reference])
        registered = {int(index) for domain in plan["domains"] if domain["domain_id"] == owner[source]
                      for index in domain["terminal_indices"]}
        if (owner[source] not in coastal or macro[destination] >= 0 or terminal < 0
                or terminal not in registered or not np.asarray(plan["ocean_mask"]).ravel()[terminal]):
            raise ProjectionError("halo marine entry lacks a registered coastal terminal")
        if coastal_context is not None:
            row, col = divmod(destination, arrays["projection_height_m"].shape[1])
            origin = coastal_context["native_origin_xz"]
            certificate = _coastal_suffix(plan, [origin[0] + col, origin[1] + row], terminal, int(owner[source]),
                spacing_m=coastal_context["spacing_m"], lake_level_m=coastal_context["lake_level_m"],
                nearest_coastal_indices=coastal_context["nearest_coastal_indices"])
            certificate["kind"] = "registered_marine_entry"
            certificate["coastal_reference_cells"] = [source_reference]
            certificate["coarse_terminal"] = terminal
            certificate["coarse_rank"] = int(ranks[source_reference])
            return certificate
        return {"kind": "registered_marine_entry", "coarse_progress": "registered_marine_terminal",
                "registered_marine_terminal": terminal}
    if owner[source] != owner[destination] or owner[source] < 0:
        raise ProjectionError("halo continuation changes frozen domain ownership")
    if coastal_context is not None:
        extension = coastal_context["extension_mask"].ravel()
        if extension[source] or extension[destination]:
            reference = coastal_context["nearest_coastal_cell"].ravel()
            source_terminal = int(terminals[reference[source]])
            destination_terminal = int(terminals[reference[destination]])
            domain = next((domain for domain in plan["domains"] if domain["domain_id"] == owner[source]), None)
            if (domain is None or domain["kind"] != "coastal" or source_terminal != destination_terminal
                    or destination_terminal not in domain["terminal_indices"]
                    or not np.asarray(plan["ocean_mask"]).ravel()[destination_terminal]):
                raise ProjectionError("coastal extension lacks one selected registered marine terminal")
            reference_certificate = {
                "coastal_reference_cells": [int(reference[source]), int(reference[destination])],
                "coastal_reference_ranks": [int(ranks[reference[source]]), int(ranks[reference[destination]])],
                "coarse_terminal": source_terminal, "halo_coarse_terminal": destination_terminal,
                "coarse_rank": int(ranks[reference[source]]), "halo_coarse_rank": int(ranks[reference[destination]])}
            if source_cell == destination_cell and reference[source] == reference[destination]:
                progress = _coarse_port_progress(np.asarray(plan["receiver"]).ravel(), terminals, ranks,
                                                int(reference[source]), int(reference[destination]))
                progress["coarse_progress"] = "within_same_actual_coarse_cell_and_registered_coastal_reference"
                return {"kind": "same_domain_computational_continuation_not_outlet",
                        "registered_marine_terminal": destination_terminal, **progress, **reference_certificate}
            row, col = divmod(destination, arrays["projection_height_m"].shape[1])
            origin = coastal_context["native_origin_xz"]
            certificate = _coastal_suffix(plan, [origin[0] + col, origin[1] + row], destination_terminal, int(owner[source]),
                spacing_m=coastal_context["spacing_m"], lake_level_m=coastal_context["lake_level_m"],
                nearest_coastal_indices=coastal_context["nearest_coastal_indices"])
            certificate.update(reference_certificate)
            return certificate
    progress = _coarse_port_progress(np.asarray(plan["receiver"]).ravel(), terminals, ranks, source_cell, destination_cell)
    return {"kind": "same_domain_computational_continuation_not_outlet", **progress}


def prepare_cached_projection(plan, generation_metadata, baseline_node_provenance, *, tile_x, tile_z,
                              lake_level_m, config=None, tributary_declaration=None, highest_lake_level_m=None, lake_mask=None):
    """Prepare one exact canonical core from cached TD and globally frozen inputs."""
    config = config or ProjectionConfig()
    tributary_validation = None
    additional_edges = None
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
        if highest_lake_level_m != lake_level_m:
            raise ValueError("local tributary projection requires the same frozen highest lake stage")
        additional_edges = [record["source_edge"] for record in tributary_declaration["edges"]]
        tributary_validation = validate_local_tributary_source_edges(plan, tributary_declaration, additional_edges,
            highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
    raw, provenance = load_cached_support(generation_metadata, tile_x=tile_x, tile_z=tile_z)
    spacing = provenance["native_resolution_m"]
    native_origin = provenance["native_origin"]
    origin = [coordinate * spacing for coordinate in native_origin]
    x, z = _coordinates(plan, origin, raw.shape, spacing)
    window = {"origin_xz_m": origin, "shape": raw.shape, "spacing_m": spacing}
    nodes = required_td_nodes(plan, window)
    baseline = np.asarray(plan["original_height_m"], float).copy()
    missing = [f"{cz}:{cx}" for cz, cx in nodes if f"{cz}:{cx}" not in baseline_node_provenance]
    if missing:
        raise ProjectionError("full canonical support TD anchors are not prepared", {"status": "source_unprepared", "missing_anchor_keys": missing})
    frozen_nodes = {}
    for cz, cx in nodes:
        key = f"{cz}:{cx}"
        record = baseline_node_provenance[key]
        value = float(record["elevation_m"])
        if not np.isfinite(value):
            raise ProjectionError("nonfinite canonical TD anchor")
        baseline[cz, cx] = value
        frozen_nodes[key] = record
    macro = stage_fixed_transform(continuous_macro_field(plan, x, z), float(lake_level_m))
    coarse_owner = np.asarray(plan["owner_domain_id"])
    nx, nz = np.rint(x).astype(int), np.rint(z).astype(int)
    owner = coarse_owner[nz, nx].copy()
    coastal_ids = [domain["domain_id"] for domain in plan["domains"] if domain["kind"] == "coastal"]
    coastal = np.isin(coarse_owner, coastal_ids)
    if not coastal.any():
        raise ProjectionError("projection requires explicit frozen marine continuation")
    nearest_land = distance_transform_edt(~coastal, return_distances=False, return_indices=True)
    extended = coarse_owner[nearest_land[0], nearest_land[1]][nz, nx]
    ocean_stencil = _interpolate(np.asarray(plan["ocean_mask"], float), x, z) > 0
    ocean = ocean_stencil & (macro < 0)
    extension_mask = (owner == -1) & ~ocean
    owner[extension_mask] = extended[extension_mask]
    owner[ocean] = -1
    core = np.zeros(raw.shape, bool)
    core[HALO:HALO + CORE, HALO:HALO + CORE] = True
    native_x, native_z = np.meshgrid(native_origin[0] + np.arange(SUPPORT), native_origin[1] + np.arange(SUPPORT))
    rem_x, rem_z = np.mod(native_x, CORE), np.mod(native_z, CORE)
    distance = np.minimum(np.minimum(rem_x, CORE - rem_x), np.minimum(rem_z, CORE - rem_z)) * spacing
    pinned = distance <= HALO * spacing
    fraction = np.clip((distance - HALO * spacing) / (config.transition_width_m - HALO * spacing), 0, 1)
    retained = fraction * fraction * (3 - 2 * fraction)
    target = macro + retained * (raw - _interpolate(baseline, x, z))
    terminal = ocean.copy()
    low, high = np.full(raw.shape, -np.inf), np.full(raw.shape, np.inf)
    low[ocean_stencil & ~ocean] = 0.0
    coarse_terminals, ranks = _coarse_terminal_certificate(plan)
    columns = coarse_owner.shape[1]
    coarse_ids = nz * columns + nx
    nearest_coastal_cell = nearest_land[0][nz, nx] * columns + nearest_land[1][nz, nx]
    nearest_coastal_cell[~extension_mask] = coarse_ids[~extension_mask]
    coastal_context = {"extension_mask": extension_mask, "nearest_coastal_cell": nearest_coastal_cell,
                       "nearest_coastal_indices": nearest_land, "native_origin_xz": native_origin,
                       "spacing_m": spacing, "lake_level_m": float(lake_level_m)}
    # Lake wet pixels are explicit samples of the already registered basin,
    # not new TD depressions. Fine capacity remains a separate validation.
    inland = [domain for domain in plan["domains"] if domain["kind"] == "inland"]
    if len(inland) > 1:
        raise ProjectionError("one explicitly verified lake stage required for this projection")
    if inland:
        from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
        lake = LakeGeometry(plan["height_m"], coarse_owner, inland[0], plan["spacing_m"] ** 2)
        basin = (_interpolate(lake.mask.astype(float), x, z) > 0) & (owner == inland[0]["domain_id"])
        wet = basin & (macro < lake_level_m)
        terminal |= wet
        high[wet] = float(lake_level_m) - 1e-6
        low[basin & ~wet] = float(lake_level_m)
    river_constraints = frozen_river_derivative_constraints(plan, raw.shape, origin, spacing, terminal,
        additional_source_edges=additional_edges)
    if tributary_validation is not None:
        river_constraints["metadata"]["local_tributary_sidecar_identity_sha256"] = tributary_declaration["identity_sha256"]
    result = project_arrays(raw, target, macro, owner, ocean, terminal, core, pinned, spacing_m=spacing,
        origin_xz_m=origin, world_seed=plan["seed"],
                            config=config, lower_height_m=low, upper_height_m=high,
                            frozen_river_constraints=river_constraints)
    result["arrays"].update({"frozen_river_derivative_columns": river_constraints["columns"],
        "frozen_river_derivative_coefficients": river_constraints["coefficients"],
        "frozen_river_derivative_rhs": river_constraints["rhs"],
        "frozen_river_derivative_world_xz_m": river_constraints["world_xz_m"],
        "frozen_river_derivative_source_edges": river_constraints["source_edges"]})
    witness = result["arrays"]["witness_receiver"].ravel()
    actual = result["arrays"]["actual_receiver"].ravel()
    ports = []
    for index in np.flatnonzero((core & ~terminal).ravel()):
        q = int(actual[index])
        if not core.ravel()[q]:
            coarse_id = int(coarse_ids.ravel()[index])
            halo_coarse_id = int(coarse_ids.ravel()[q])
            try:
                certificate = _validate_port(plan, result, coarse_ids, coarse_terminals, ranks, int(index), q,
                                             coastal_context=coastal_context)
            except ProjectionError as error:
                source_row, source_column = divmod(int(index), SUPPORT)
                halo_row, halo_column = divmod(q, SUPPORT)
                raise ProjectionError(str(error), {**error.diagnostics,
                    "source_index": int(index), "destination_index": q,
                    "source_coarse_cell": coarse_id, "destination_coarse_cell": halo_coarse_id,
                    "source_coastal_reference": int(nearest_coastal_cell.ravel()[index]),
                    "destination_coastal_reference": int(nearest_coastal_cell.ravel()[q]),
                    "source_world_xz_m": [origin[0] + source_column * spacing, origin[1] + source_row * spacing],
                    "destination_world_xz_m": [origin[0] + halo_column * spacing, origin[1] + halo_row * spacing]}) from error
            row, column = divmod(q, SUPPORT)
            ports.append({"source_index": int(index), "halo_index": q,
                          "macro_witness_index": int(witness[index]),
                          "world_xz_m": [origin[0] + column * spacing, origin[1] + row * spacing],
                          "coarse_cell": coarse_id, "coarse_receiver": int(np.asarray(plan["receiver"]).ravel()[coarse_id]),
                          "coarse_terminal": int(coarse_terminals[coarse_id]), "coarse_rank": int(ranks[coarse_id]),
                          "halo_coarse_cell": halo_coarse_id, "halo_coarse_terminal": int(coarse_terminals[halo_coarse_id]),
                          "halo_coarse_rank": int(ranks[halo_coarse_id]),
                          **certificate})
    result["arrays"]["td_residual_retention"] = retained
    result["metadata"].update({"plan_identity": plan.get("identity_sha256", plan.get("identity")),
                               "native_origin_xz": native_origin, "core_native_origin_xz": [tile_x * CORE, tile_z * CORE],
                               "core_shape": [CORE, CORE], "halo_cells": HALO,
                               "origin_xz_m": origin, "spacing_m": spacing, "shape": [SUPPORT, SUPPORT],
                               "raw_provenance": provenance, "baseline_node_provenance": frozen_nodes,
                               "fixed_lake_level_m": float(lake_level_m), "continuation_ports": ports,
                               "source_residual_fraction": 1.0, "interface_transition_width_m": config.transition_width_m,
                               "interface_contract": "global core256 lines; shared fan values pinned within two native cells; C1 residual target attenuation over fixed >=1000m",
                               "budget_scope": "entire260 support, including non-exported halo; independent97 crop acceptance retains original frozen gates",
                               "full_support_volume_budget_derivation": {
                                   "reference_side_cells": REFERENCE_ACCEPTANCE_SIDE,
                                   "reference_spacing_m": spacing,
                                   "reference_volume_m3": REFERENCE_ACCEPTANCE_VOLUME_M3,
                                   "reference_area_m2": REFERENCE_ACCEPTANCE_SIDE ** 2 * spacing ** 2,
                                   "support_side_cells": SUPPORT,
                                   "support_area_m2": SUPPORT ** 2 * spacing ** 2,
                                   "volume_density_m3_per_m2": REFERENCE_ACCEPTANCE_VOLUME_M3 / (REFERENCE_ACCEPTANCE_SIDE ** 2 * spacing ** 2),
                                   "frozen_support_volume_m3": FULL_SUPPORT_VOLUME_M3,
                                   "formula": "4500000000 * (260 * 260 * 30 * 30) / (97 * 97 * 30 * 30)",
                                   "crop_gates_changed": False},
                               "fine_basin_seasonal_revalidated": False,
                               "source_core_source_max_tiles": 9,
                               "coarse_terminal_semantics": "registered marine or verified coarse basin; not arbitrary patch edges"})
    result["metadata"]["maximum_coastal_suffix_steps"] = COASTAL_SUFFIX_MAX_STEPS
    if tributary_validation is not None:
        result["metadata"]["algorithm"] = LOCAL_TRIBUTARY_ALGORITHM
        result["metadata"]["local_tributary_sidecar_validation"] = tributary_validation
        result["metadata"]["local_tributary_sidecar_identity_sha256"] = tributary_declaration["identity_sha256"]
    result["metadata"]["coastal_continuation_policy"] = "same actual coarse cell and registered coastal reference permits interior continuation; cross-cell or marine entry requires bounded globally pinned suffix"
    result["metadata"]["identity"] = _identity(result["metadata"], result["arrays"])
    return result


def crop_projection(result, origin_native_xz, shape):
    """Crop only owned pixels; a multi-core request must stitch owning cores."""
    metadata, arrays = result["metadata"], result["arrays"]
    x, z = origin_native_xz
    core_x, core_z = metadata["core_native_origin_xz"]
    rows, columns = shape
    if rows <= 0 or columns <= 0 or x < core_x or z < core_z or x + columns > core_x + CORE or z + rows > core_z + CORE:
        raise ValueError("crop must stay within this canonical owned core")
    native_x, native_z = metadata["native_origin_xz"]
    region = (slice(z - native_z, z - native_z + rows), slice(x - native_x, x - native_x + columns))
    crop = {key: value[region].copy() for key, value in arrays.items()
            if not key.startswith("frozen_river_derivative_")}
    delta = crop["projection_height_m"] - crop["original_td_m"]
    return {"arrays": crop, "metadata": {"parent_identity": metadata["identity"],
            "origin_native_xz": [int(x), int(z)], "shape": [int(rows), int(columns)],
            "parent_frozen_river_constraints": metadata.get("frozen_river_constraints"),
            "ledger": {"macro_max_abs_m": float(np.abs(delta).max()),
                       "macro_absolute_volume_m3": float(np.abs(delta).sum() * metadata["spacing_m"] ** 2)},
            "semantics": "exact owned-core crop; receiver indices still refer to parent support"}}


def save_projection(result, path):
    metadata, arrays = result["metadata"], result["arrays"]
    if metadata.get("identity") != _identity(metadata, arrays):
        raise ValueError("projection identity mismatch")
    with Path(path).open("xb") as stream:
        np.savez_compressed(stream, metadata_json=np.array(json.dumps(metadata, sort_keys=True, allow_nan=False)), **arrays)


def load_projection(path):
    with np.load(path, allow_pickle=False) as archive:
        metadata = json.loads(str(archive["metadata_json"].item()))
        arrays = {key: archive[key].copy() for key in archive.files if key != "metadata_json"}
    if metadata.get("identity") != _identity(metadata, arrays):
        raise ValueError("projection identity mismatch")
    return {"metadata": metadata, "arrays": arrays}
