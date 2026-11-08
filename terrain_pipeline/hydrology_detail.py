"""Bounded, auditable physical TD derivation from a frozen global drainage plan.

This module never generates terrain. Local certificates do not establish global
hydraulic connectivity; rejected TD windows remain useful calibration evidence.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import strict_receivers as strict_receivers

from terrain_pipeline.common_infra import file_sha256, load_physical_source, checked_archive


ALGORITHM = "frozen-hydrology-td-detail-v4-irregular"
ASSESSMENT_ALGORITHM = "frozen-river-path-assessment-v2-exact-continuous-route"
DIRECTIONS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass(frozen=True)
class DetailBudget:
    """Initial calibration candidate; callers must freeze this before acceptance."""

    macro_max_abs_m: float = 80.0
    total_max_abs_m: float = 84.0
    macro_absolute_volume_m3: float = 300_000_000.0
    total_absolute_volume_m3: float = 310_000_000.0
    channel_max_cut_m: float = 4.0

    def __post_init__(self):
        if any(not np.isfinite(value) or value <= 0 for value in asdict(self).values()):
            raise ValueError("positive finite frozen detail budgets required")
        if self.channel_max_cut_m > 4.0:
            raise ValueError("local channel budget cannot exceed 4 m")


def _digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load_raw_td(path, expected_sha256):
    """Require a pinned physical-backend archive, not a procedural stand-in."""
    arrays = checked_archive(path, expected_sha256=expected_sha256)
    metadata = json.loads(str(arrays["metadata_json"].item()))
    if metadata.get("schema") == "hydrology-canonical-td-window-v1":
        from terrain_pipeline.td_source import load_canonical_window
        return load_canonical_window(path, expected_sha256)
    source = load_physical_source(path, expected_sha256=expected_sha256,
        boundary={"policy": "explicit", "halo_cells": 0, "upstream_contribution": "excluded_finite_experiment"})
    metadata = source["metadata"]
    return source, metadata


def _coordinates(plan, origin_xz_m, shape, spacing_m):
    if not np.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("positive physical spacing required")
    if len(shape) != 2 or min(shape) < 3 or np.prod(shape) > 250_000:
        raise ValueError("bounded two-dimensional detail window required")
    origin = np.asarray(origin_xz_m, dtype=np.float64)
    coarse_origin = np.asarray(plan["origin_xz_m"], dtype=np.float64)
    coarse_spacing = float(plan["spacing_m"])
    if origin.shape != (2,) or coarse_origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("finite x east/z south origin required")
    if not np.isfinite(coarse_spacing) or coarse_spacing <= 0:
        raise ValueError("invalid coarse spacing")
    x = (origin[0] + np.arange(shape[1]) * spacing_m - coarse_origin[0]) / coarse_spacing
    z = (origin[1] + np.arange(shape[0]) * spacing_m - coarse_origin[1]) / coarse_spacing
    coarse_shape = np.asarray(plan["height_m"]).shape
    if min(x.min(), z.min()) < 0 or x.max() > coarse_shape[1] - 1 or z.max() > coarse_shape[0] - 1:
        raise ValueError("detail window outside finite frozen planning extent")
    return np.meshgrid(x, z)


def _interpolate(values, x, z):
    values = np.asarray(values)
    x0, z0 = np.floor(x).astype(int), np.floor(z).astype(int)
    x1, z1 = np.minimum(x0 + 1, values.shape[1] - 1), np.minimum(z0 + 1, values.shape[0] - 1)
    wx, wz = x - x0, z - z0
    return ((1 - wz) * ((1 - wx) * values[z0, x0] + wx * values[z0, x1])
            + wz * ((1 - wx) * values[z1, x0] + wx * values[z1, x1]))


def required_td_nodes(plan, window):
    """Global coarse-node IDs required by this window's bilinear stencil."""
    x, z = _coordinates(plan, window["origin_xz_m"], window["shape"], window["spacing_m"])
    rows, cols = np.asarray(plan["height_m"]).shape
    nodes = set()
    for cx, cz in zip(np.floor(x).astype(int).ravel(), np.floor(z).astype(int).ravel()):
        nodes.update((min(cz + dz, rows - 1), min(cx + dx, cols - 1)) for dz in (0, 1) for dx in (0, 1))
    return sorted(nodes)


def _steepest_receivers(height, spacing_m, *, origin_xz_m=(0., 0.), world_seed=20261020):
    """Strict original-bed graph routing; unresolved flats remain sinks."""
    mesh = grid_mesh(height.shape, x0_m=origin_xz_m[0], z0_m=origin_xz_m[1],
                     dx_m=spacing_m, world_seed=world_seed)
    return strict_receivers(height, mesh)[0].reshape(height.shape)


def _paths(plan, origin, shape, spacing, *, source_edges=None):
    """Rasterize complete frozen edges in absolute coordinates, then crop.

    Coordinates and bed targets are global: window traversal cannot change them.
    Only explicitly selected river cells are engraved, not all hillslope edges.
    """
    h = np.asarray(plan.get("path_reference_height_m", plan["height_m"]))
    receivers = np.asarray(plan["receiver"]).ravel()
    owners = np.asarray(plan["owner_domain_id"]).ravel()
    river = np.asarray(plan.get("river_mask", np.zeros(h.shape, dtype=bool))).ravel()
    paths = []
    edges = ([(int(cell), int(receivers[cell])) for cell in np.flatnonzero(river & (receivers >= 0))]
             if source_edges is None else source_edges)
    for cell, target in edges:
        cell, target = int(cell), int(target)
        if owners[cell] != owners[target] and owners[target] != -1:
            raise ValueError("frozen river crosses domain ownership")
        az, ax = divmod(int(cell), h.shape[1])
        bz, bx = divmod(target, h.shape[1])
        start = np.array([ax, az]) * plan["spacing_m"] + plan["origin_xz_m"]
        finish = np.array([bx, bz]) * plan["spacing_m"] + plan["origin_xz_m"]
        # Skip distant edges before fine raster allocation.
        maximum = np.asarray(origin) + (np.array(shape)[::-1] - 1) * spacing
        if np.any(np.maximum(start, finish) < origin) or np.any(np.minimum(start, finish) > maximum):
            continue
        steps = max(1, int(np.ceil(np.max(np.abs(finish - start)) / spacing)))
        t = np.linspace(0, 1, steps + 1)
        coordinates = np.rint((start[None, :] + t[:, None] * (finish - start) - origin) / spacing).astype(int)
        targets = h.ravel()[cell] + t * (h.ravel()[target] - h.ravel()[cell])
        height_map = plan.get("path_height_map")
        if height_map:
            knots, values = height_map["knots_m"], height_map["values_m"]
            targets = np.where((targets > knots[0]) & (targets < knots[-1]), np.interp(targets, knots, values), targets)
        valid = ((coordinates[:, 0] >= 0) & (coordinates[:, 0] < shape[1])
                 & (coordinates[:, 1] >= 0) & (coordinates[:, 1] < shape[0]))
        coordinates, targets = coordinates[valid], targets[valid]
        if len(coordinates):
            unique = np.r_[True, np.any(coordinates[1:] != coordinates[:-1], axis=1)]
            paths.append((coordinates[unique], targets[unique]))
    return paths


def _shared_face_distance_m(plan, origin_xz_m, shape, spacing_m):
    px = origin_xz_m[0] + np.arange(shape[1])[None, :] * spacing_m
    pz = origin_xz_m[1] + np.arange(shape[0])[:, None] * spacing_m
    distance = np.full(shape, np.inf)
    coarse_spacing = plan["spacing_m"]
    for first, second in np.asarray(plan["shared_boundary_edges"]):
        az, ax = divmod(int(first), np.asarray(plan["height_m"]).shape[1])
        bz, bx = divmod(int(second), np.asarray(plan["height_m"]).shape[1])
        if abs(ax - bx) + abs(az - bz) != 1:
            continue
        midpoint = np.asarray(plan["origin_xz_m"]) + np.array([(ax + bx) / 2, (az + bz) / 2]) * coarse_spacing
        if ax != bx:
            dx, dz = np.abs(px - midpoint[0]), np.maximum(np.abs(pz - midpoint[1]) - coarse_spacing / 2, 0)
        else:
            dx, dz = np.maximum(np.abs(px - midpoint[0]) - coarse_spacing / 2, 0), np.abs(pz - midpoint[1])
        distance = np.minimum(distance, np.hypot(dx, dz))
    return distance


def derive_detail(plan, raw_height_m, *, origin_xz_m, spacing_m, raw_provenance,
                  budget=None, window_kind="unspecified", divide_taper_width_m=0.0,
                  candidate_height_m=None, candidate_provenance=None, fine_support=None, lake_support=None,
                  tributary_declaration=None, highest_lake_level_m=None, lake_mask=None,
                  tributary_validation_plan=None, d8_owned_mask=None, shared_boundary_protection_m=None):
    """Preserve raw TD; propose finite changes and report explicit refusals."""
    budget = DetailBudget() if budget is None else budget
    tributary_validation = None
    source_edges = None
    if tributary_declaration is not None:
        from terrain_pipeline.hydrology_detail_tributaries import validate_local_tributary_source_edges
        authority = plan if tributary_validation_plan is None else tributary_validation_plan
        declared_edges = [record["source_edge"] for record in tributary_declaration["edges"]]
        tributary_validation = validate_local_tributary_source_edges(authority, tributary_declaration, declared_edges,
            highest_lake_level_m=highest_lake_level_m, lake_mask=lake_mask)
        if (authority["identity_sha256"] != plan["identity_sha256"]
                or not np.array_equal(authority["receiver"], plan["receiver"])
                or not np.array_equal(authority["river_mask"], plan["river_mask"])):
            raise ValueError("tributary observer authority must retain the same frozen graph and parent identity")
        receiver = np.asarray(plan["receiver"]).ravel()
        river = np.asarray(plan["river_mask"]).ravel()
        source_edges = sorted({(int(cell), int(receiver[cell])) for cell in np.flatnonzero(river & (receiver >= 0))}
                              | {tuple(edge) for edge in declared_edges})
    raw = np.asarray(raw_height_m, dtype=np.float64)
    if (raw.ndim != 2 or not np.isfinite(raw).all()
            or raw_provenance.get("artifact_kind") != "terrain_diffusion_output"
            or raw_provenance.get("td_inference_run") is not True
            or len(raw_provenance.get("archive_sha256", "")) != 64):
        raise ValueError("finite genuine pinned TD source required")
    h = np.asarray(plan["height_m"], dtype=np.float64)
    original = np.asarray(plan["original_height_m"], dtype=np.float64)
    if original.shape != h.shape or not np.isfinite(h).all() or not np.isfinite(original).all():
        raise ValueError("finite frozen original and derived coarse geometry required")
    candidate = None
    candidate_kind = None
    if candidate_height_m is not None:
        candidate = np.asarray(candidate_height_m, dtype=np.float64)
        candidate_kind = candidate_provenance.get("artifact_kind") if candidate_provenance else None
        genuine_candidate = (candidate_kind == "terrain_diffusion_output" and candidate_provenance.get("td_inference_run") is True
                             and len(candidate_provenance.get("archive_sha256", "")) == 64)
        derived_candidate = (candidate_kind == "derived_terrain_diffusion_macro_geometry"
                             and candidate_provenance.get("td_inference_run") is False
                             and candidate_provenance.get("parent_archive_sha256") == raw_provenance["archive_sha256"])
        if (candidate.shape != raw.shape or not np.isfinite(candidate).all() or not candidate_provenance
                or not (genuine_candidate or derived_candidate) or divide_taper_width_m):
            raise ValueError("aligned genuine pinned TD candidate required; audit cannot apply an extra taper")
    x, z = _coordinates(plan, origin_xz_m, raw.shape, spacing_m)
    nearest_x, nearest_z = np.rint(x).astype(int), np.rint(z).astype(int)
    owners = np.asarray(plan["owner_domain_id"])[nearest_z, nearest_x]
    ocean = np.asarray(plan["ocean_mask"])[nearest_z, nearest_x]
    if fine_support is not None:
        if candidate is None or fine_support.get("algorithm") != "frozen-ocean-support-continuous-zero-isoline-v1":
            raise ValueError("explicit derived continuous coast support required")
        owners = np.asarray(fine_support["owner_domain_id"])
        ocean = np.asarray(fine_support["ocean_mask"])
        if owners.shape != raw.shape or ocean.shape != raw.shape or ocean.dtype != bool:
            raise ValueError("aligned continuous coast support required")
    baseline = np.asarray(plan.get("frozen_td_lowpass_m", original), dtype=np.float64).copy()
    sparse = plan.get("frozen_td_baseline_nodes", {})
    if sparse:
        for cz, cx in required_td_nodes(plan, {"origin_xz_m": origin_xz_m, "shape": raw.shape, "spacing_m": spacing_m}):
            key = str(cz) + ":" + str(cx)
            if key not in sparse:
                raise ValueError("missing globally pinned TD interpolation node: " + key)
            baseline[cz, cx] = sparse[key]["elevation_m"]
    if baseline.shape != h.shape or not np.isfinite(baseline).all():
        raise ValueError("finite globally frozen TD lowpass field required")
    macro_delta = _interpolate(h - baseline, x, z) if candidate is None else candidate - raw
    residual_retention = np.ones(raw.shape, dtype=np.float64)
    if not np.isfinite(divide_taper_width_m) or not 0 <= divide_taper_width_m <= plan["spacing_m"] / 4:
        raise ValueError("divide taper must be bounded to one quarter coarse spacing")
    if divide_taper_width_m:
        # Canonical Voronoi faces of the sampled global owner field. At a D4
        # owner boundary, interpolate no TD residual; the rest of the window
        # retains real TD residual, with no window-local smoothing operation.
        px = origin_xz_m[0] + np.arange(raw.shape[1])[None, :] * spacing_m
        pz = origin_xz_m[1] + np.arange(raw.shape[0])[:, None] * spacing_m
        distance = np.full(raw.shape, np.inf)
        for first, second in np.asarray(plan["shared_boundary_edges"]):
            az, ax = divmod(int(first), h.shape[1])
            bz, bx = divmod(int(second), h.shape[1])
            if abs(ax - bx) + abs(az - bz) != 1:
                continue
            midpoint = np.asarray(plan["origin_xz_m"]) + np.array([(ax + bx) / 2, (az + bz) / 2]) * plan["spacing_m"]
            if ax != bx:
                dx, dz = np.abs(px - midpoint[0]), np.maximum(np.abs(pz - midpoint[1]) - plan["spacing_m"] / 2, 0)
            else:
                dx, dz = np.maximum(np.abs(px - midpoint[0]) - plan["spacing_m"] / 2, 0), np.abs(pz - midpoint[1])
            distance = np.minimum(distance, np.hypot(dx, dz))
        normalized = np.minimum(distance / divide_taper_width_m, 1.0)
        residual_retention = normalized * normalized * (3 - 2 * normalized)
        macro_delta += (residual_retention - 1.0) * (raw - _interpolate(baseline, x, z))
    macro_height = raw + macro_delta
    protected = np.zeros(raw.shape, dtype=bool)
    if shared_boundary_protection_m is not None:
        if not np.isfinite(shared_boundary_protection_m) or shared_boundary_protection_m <= 0:
            raise ValueError("positive finite shared-face protection width required")
        protected = (owners >= 0) & (_shared_face_distance_m(plan, origin_xz_m, raw.shape, spacing_m) <= shared_boundary_protection_m)
    else:
        for dz, dx in DIRECTIONS:
            neighbor_x = np.clip(nearest_x + dx, 0, h.shape[1] - 1)
            neighbor_z = np.clip(nearest_z + dz, 0, h.shape[0] - 1)
            neighbor = np.asarray(plan["owner_domain_id"])[neighbor_z, neighbor_x]
            protected |= (owners >= 0) & (neighbor >= 0) & (owners != neighbor)
    local_delta = np.zeros(raw.shape, dtype=np.float64)
    paths = _paths(plan, np.asarray(origin_xz_m), raw.shape, spacing_m, source_edges=source_edges)
    wet_path_mask = np.zeros(raw.shape, bool) if lake_support is None else np.asarray(lake_support["connected_wet_mask"])
    if wet_path_mask.shape != raw.shape or wet_path_mask.dtype != bool:
        raise ValueError("aligned registered wet lake support required")
    dry_path_samples = 0
    submerged_path_samples = 0
    required_cut = 0.0
    linear_reference_cut = 0.0
    for coordinates, targets in paths:
        cx, cz = coordinates.T
        source = macro_height[cz, cx]
        distance = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(coordinates, axis=0), axis=1) * spacing_m)]
        # Frozen heights define the coarse DAG, not a mandatory straight bed.
        # A shared finite terrain profile supplies the continuous-bed request.
        bed = np.minimum.accumulate(source + 0.001 * distance) - 0.001 * distance - 0.5
        desired = bed - source
        submerged_path_samples += int(wet_path_mask[cz, cx].sum())
        active_path = ~wet_path_mask[cz, cx] & ~ocean[cz, cx]
        dry_path_samples += int(active_path.sum())
        desired[~active_path] = 0
        linear_reference_cut = max(linear_reference_cut, float(np.maximum(source[active_path] - targets[active_path], 0).max(initial=0)))
        required_cut = max(required_cut, float(-desired.min()))
        permitted = (-desired <= budget.channel_max_cut_m) & ~protected[cz, cx]
        local_delta[cz[permitted], cx[permitted]] = np.minimum(local_delta[cz[permitted], cx[permitted]], desired[permitted])
    from terrain_pipeline.channel_geometry import frozen_window_profiles
    continuous_profiles = frozen_window_profiles(plan, macro_height, origin_xz_m, spacing_m, source_edges=source_edges)
    required_cut = 0.0
    continuous_sample_count = 0
    for profile in continuous_profiles:
        indices = np.rint((profile["points_xz_m"] - origin_xz_m) / spacing_m).astype(int)
        cx, cz = indices.T
        active = ~wet_path_mask[cz, cx] & ~ocean[cz, cx]
        continuous_sample_count += int(active.sum())
        required_cut = max(required_cut, float((profile["source_m"][active] - profile["bed_m"][active]).max(initial=0)))
    requested_local_delta = local_delta.copy()
    # A one-pixel native-grid line is only a feasibility probe. Real channels
    # use the continuous finite-width bed adapter, never this raster slot.
    local_delta[:] = 0.0
    derived = macro_height + local_delta
    total = derived - raw
    receiver = _steepest_receivers(derived, spacing_m, origin_xz_m=origin_xz_m, world_seed=plan.get("seed", 20261020))
    owned = np.ones(raw.shape,bool) if d8_owned_mask is None else np.asarray(d8_owned_mask)
    expected_owned = np.zeros(raw.shape,bool)
    expected_owned[2:-2,2:-2] = True
    if (owned.shape != raw.shape or owned.dtype != bool or not owned.any()
            or (d8_owned_mask is not None and not np.array_equal(owned,expected_owned))):
        raise ValueError("explicit owned irregular-graph mask requires genuine two-cell computational halo")
    flat_owner, flat_ocean, flat_receiver = owners.ravel(), ocean.ravel(), receiver.ravel()
    active = flat_receiver >= 0
    destination = np.maximum(flat_receiver, 0)
    crossing = owned.ravel() & active & (flat_owner >= 0) & (flat_owner[destination] != -1) & (flat_owner != flat_owner[destination])
    # Frozen terminal support does not invent a lake at each new TD sink.
    terminal_cells = {int(cell) for domain in plan["domains"] for cell in domain["terminal_indices"]}
    coarse_ids = nearest_z * h.shape[1] + nearest_x
    allowed_terminal = np.isin(coarse_ids, list(terminal_cells)) | ocean
    connected_wet = np.zeros(raw.shape, bool)
    if lake_support is not None:
        connected_wet = np.asarray(lake_support["connected_wet_mask"])
        stage = lake_support["level_m"]
        if (candidate is None or connected_wet.shape != raw.shape or connected_wet.dtype != bool
                or not np.isfinite(stage) or np.any(connected_wet & (derived >= stage))
                or not lake_support.get("coarse_basin_mask_sha256")):
            raise ValueError("verified connected wet support must lie below its explicit lake stage")
        allowed_terminal = connected_wet | ocean
    interior = np.ones(raw.shape, dtype=bool)
    interior[[0, -1], :] = False
    interior[:, [0, -1]] = False
    unexpected_sink = (receiver < 0) & interior & ~allowed_terminal & owned
    raster_uphill_paths = 0
    for coordinates, _ in paths:
        cx, cz = coordinates.T
        active_path = ~wet_path_mask[cz, cx] & ~ocean[cz, cx]
        raster_uphill_paths += int(np.count_nonzero((np.diff(derived[cz, cx]) >= 0) & active_path[:-1] & active_path[1:]))
    continuous_source_uphill_paths = 0
    uphill_paths = 0
    minimum_bed_grade = np.inf
    for profile in continuous_profiles:
        indices = np.rint((profile["points_xz_m"] - origin_xz_m) / spacing_m).astype(int)
        cx, cz = indices.T
        active = ~wet_path_mask[cz, cx] & ~ocean[cz, cx]
        active_pairs = active[:-1] & active[1:]
        distance = np.linalg.norm(np.diff(profile["points_xz_m"], axis=0), axis=1)
        continuous_source_uphill_paths += int(np.count_nonzero((np.diff(profile["source_m"]) >= 0) & active_pairs))
        grade = -np.diff(profile["bed_m"]) / distance
        uphill_paths += int(np.count_nonzero((grade < 0.001 - 1e-8) & active_pairs))
        if active_pairs.any():
            minimum_bed_grade = min(minimum_bed_grade, float(grade[active_pairs].min()))
    ledger = {"macro_max_abs_m": float(np.abs(macro_delta).max()),
              "macro_absolute_volume_m3": float(np.abs(macro_delta).sum() * spacing_m ** 2),
              "total_max_abs_m": float(np.abs(total).max()),
              "total_absolute_volume_m3": float(np.abs(total).sum() * spacing_m ** 2),
              "channel_max_cut_m": float(-local_delta.min()),
              "required_channel_cut_m": required_cut,
              "linear_coarse_reference_required_cut_m": linear_reference_cut,
              "channel_cut_volume_m3": float(-local_delta.sum() * spacing_m ** 2)}
    reasons = [name + "_exceeded" for name in ("macro_max_abs_m", "macro_absolute_volume_m3", "total_max_abs_m", "total_absolute_volume_m3")
               if ledger[name] > getattr(budget, name)]
    if candidate is None and "frozen_td_lowpass_m" not in plan and not sparse:
        reasons.append("no_matched_globally_frozen_td_lowpass_baseline")
    if required_cut > budget.channel_max_cut_m:
        reasons.append("required_channel_cut_exceeds_4m")
    if crossing.any():
        reasons.append("actual_d8_crosses_frozen_domain")
    if unexpected_sink.any():
        reasons.append("actual_d8_has_unplanned_interior_sinks")
    if uphill_paths:
        reasons.append("frozen_river_path_not_strictly_downhill")
    if window_kind in ("river", "confluence", "mouth") and not paths:
        reasons.append("no_explicit_frozen_river_in_window")
    if window_kind in ("river", "confluence", "mouth"):
        reasons.append("continuous_fine_bed_not_certified")
    if window_kind in ("river", "confluence") and paths and not dry_path_samples and submerged_path_samples:
        reasons.append("frozen_river_component_is_submerged_in_verified_lake")
    if window_kind == "lake_shore":
        if lake_support is None:
            reasons.append("continuous_connected_lake_shore_not_certified")
        elif not connected_wet.any() or not (derived >= lake_support["level_m"]).any():
            reasons.append("verified_lake_stage_does_not_cross_window")
    if np.any(ocean & (derived >= 0)):
        reasons.append("frozen_ocean_not_below_sea_datum")
    arrays = {"original_td_m": raw.copy(), "macro_delta_m": macro_delta, "local_channel_delta_m": local_delta,
              "total_delta_m": total, "derived_height_m": derived, "actual_receiver": receiver,
              "owner_domain_id": owners, "ocean_mask": ocean, "shared_boundary_protected": protected,
              "cross_owner_d8_mask": crossing.reshape(raw.shape), "unplanned_sink_mask": unexpected_sink}
    if d8_owned_mask is not None:
        arrays["d8_owned_mask"] = owned.copy()
    arrays["requested_channel_diagnostic_delta_m"] = requested_local_delta
    arrays["td_residual_retention"] = residual_retention
    if lake_support is not None:
        arrays["connected_lake_wet_mask"] = connected_wet
    if candidate is not None:
        arrays["planned_conditioned_td_m" if candidate_kind == "terrain_diffusion_output" else "proposed_macro_height_m"] = candidate.copy()
    metadata = {"algorithm": ALGORITHM, "assessment_algorithm": ASSESSMENT_ALGORITHM,
                "window_kind": window_kind, "origin_xz_m": list(origin_xz_m),
                "spacing_m": float(spacing_m), "shape": list(raw.shape), "budget": asdict(budget),
                "raw_provenance": raw_provenance, "plan_identity": plan.get("identity", plan.get("identity_sha256")),
                "ledger": ledger, "rejection_reasons": reasons,
                "status": "rejected" if reasons else "local_compatible_global_unverified",
                "global_hydrology_certified": False, "publishable": False,
                "cross_domain_d8_count": int(crossing.sum()), "unplanned_interior_sink_count": int(unexpected_sink.sum()),
                "non_downhill_channel_steps": uphill_paths,
                "native_raster_non_downhill_channel_steps": raster_uphill_paths,
                "continuous_source_non_downhill_channel_steps": continuous_source_uphill_paths,
                "continuous_bed_target_minimum_grade_m_per_m": None if not np.isfinite(minimum_bed_grade) else minimum_bed_grade,
                "river_path_acceptance_semantics": "exact world frozen-edge terrain-following target grade and original 4m cut gate; rounded native probe separately diagnostic; represented continuous bed still requires independent certification",
                "dry_frozen_river_path_samples": dry_path_samples,
                "terrain_following_profile_sample_spacing_m": 1.0,
                "dry_continuous_frozen_river_profile_samples": continuous_sample_count,
                "represented_frozen_edge_profiles": [{"source_edge": profile["source_edge"],
                    "edge_fraction_interval": profile["fractions"][[0, -1]].tolist(),
                    "represented_length_m": profile["length_m"],
                    "full_coarse_edge_length_m": profile["full_coarse_edge_length_m"]} for profile in continuous_profiles],
                "submerged_frozen_river_path_samples": submerged_path_samples,
                "boundary_policy": "unknown outside window; no invented outlet", "flat_rule": "unresolved sink",
                "climate_semantics": "TD five climate channels; no watershed conditioning channel",
                "channel_semantics": "entire represented frozen path terrain-following 0.5m depth and 0.001 grade; native diagnostic only, continuous full-window bed remains uncertified",
                "channel_profile_boundary_policy": "finite represented source; no full coarse edge or outside-window continuation certificate",
                "interpolation": "global bilinear frozen macro difference; no window-local filter"}
    metadata["macro_baseline"] = ("immutable_original_td_for_genuine_conditioned_candidate" if candidate is not None
        else "global_sparse_td_node_interpolation_residual_not_lowpass" if sparse
        else "globally_frozen_td_lowpass" if "frozen_td_lowpass_m" in plan else "unmatched_procedural_coarse_diagnostic_only")
    metadata["baseline_node_provenance"] = sparse
    if shared_boundary_protection_m is not None:
        metadata["shared_boundary_protection"] = {"algorithm": "frozen-d4-shared-face-segment-distance-v1",
            "width_m": float(shared_boundary_protection_m), "inclusive": True}
    if d8_owned_mask is not None:
        metadata["algorithm"] = ALGORITHM + "-rectangular-owned-d8-halo2-v1"
        metadata["d8_boundary_halo_cells"] = 2
        metadata["d8_acceptance_scope"] = "entire rectangular support interior excluding two computational boundary rows"
    metadata["divide_taper_width_m"] = divide_taper_width_m
    metadata["residual_loss_scope"] = "bounded global owner-face band; loss fully in macro and total deltas"
    if tributary_validation is not None:
        metadata["algorithm"] = ALGORITHM + "-local-tributary-v1"
        metadata["local_tributary_sidecar_validation"] = tributary_validation
        metadata["local_tributary_sidecar_identity"] = tributary_declaration["identity_sha256"]
    if fine_support is not None:
        metadata["fine_coast_support"] = {key: value for key, value in fine_support.items() if key not in ("owner_domain_id", "ocean_mask")}
    if lake_support is not None:
        metadata["fine_lake_support"] = {key: value for key, value in lake_support.items() if key != "connected_wet_mask"}
    if candidate is not None:
        metadata["candidate_provenance"] = candidate_provenance
        metadata["interpolation"] = "none; genuine planned TD minus immutable original TD"
        if candidate_kind != "terrain_diffusion_output":
            metadata["macro_baseline"] = "immutable_original_td_for_explicit_derived_macro_proposal"
            metadata["interpolation"] = "explicit derived macro proposal minus immutable original TD; no new inference"
    metadata["identity"] = _digest({"metadata": metadata, "arrays": {
        name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in sorted(arrays.items())}})
    return {"arrays": arrays, "metadata": metadata}


def save_detail(path, result):
    """Save only a new artifact, never overwrite immutable raw TD."""
    with Path(path).open("xb") as output:
        np.savez_compressed(output, **result["arrays"], metadata_json=np.array(json.dumps(result["metadata"], allow_nan=False)))


def select_key_windows(plan, *, size=97, spacing_m=30.0, lake_level_m=None, lake_mask=None, ridge_index=0):
    """Select five key locations deterministically, before any TD inference."""
    h = np.asarray(plan["height_m"])
    receiver = np.asarray(plan["receiver"]).ravel()
    owners = np.asarray(plan["owner_domain_id"]).ravel()
    ocean = np.asarray(plan["ocean_mask"]).ravel()
    river = np.asarray(plan.get("river_mask", np.zeros(h.shape, dtype=bool))).ravel()
    wet_lake = np.zeros(h.size, bool)
    if lake_level_m is not None and lake_mask is not None:
        mask = np.asarray(lake_mask)
        if not np.isfinite(lake_level_m) or mask.shape != h.shape or mask.dtype != bool:
            raise ValueError("verified finite stage and connected coarse basin mask required")
        wet_lake = mask.ravel() & (h.ravel() < lake_level_m)
    land_edges = np.flatnonzero(river & (owners >= 0) & (receiver >= 0))
    downstream = receiver[land_edges]
    same_land = (owners[downstream] == owners[land_edges]) & (owners[downstream] >= 0)
    dry_land = same_land & ~wet_lake[land_edges] & ~wet_lake[downstream]
    indegree = np.bincount(downstream[dry_land], minlength=h.size)
    confluence_eligible = ((indegree >= 2) & river & (owners >= 0) & (receiver >= 0)
                          & (owners[np.maximum(receiver, 0)] == owners) & ~wet_lake
                          & ~wet_lake[np.maximum(receiver, 0)])
    confluence_cell = int(np.argmax(np.where(confluence_eligible, indegree, -1))) if confluence_eligible.any() else None
    internal = land_edges[~ocean[downstream] & ~wet_lake[land_edges] & ~wet_lake[downstream]]
    mouths = land_edges[ocean[downstream]]
    edges = np.asarray(plan["shared_boundary_edges"])
    if type(ridge_index) is not int or ridge_index < 0 or (edges.size and ridge_index >= len(edges)):
        raise ValueError("explicit ridge index outside immutable shared-edge list")
    candidates = {"ridge": int(edges[ridge_index, 0]) if edges.size else None,
                  "river": int(internal[len(internal) // 2]) if len(internal) else None,
                  "confluence": confluence_cell,
                  "mouth": int(mouths[0]) if len(mouths) else None,
                  "lake_shore": None}
    shore_pair = None
    if lake_level_m is not None and lake_mask is not None:
        if not np.isfinite(lake_level_m):
            raise ValueError("finite explicitly certified lake level required")
        lake_mask = np.asarray(lake_mask)
        if lake_mask.shape != h.shape or lake_mask.dtype != bool:
            raise ValueError("validated connected lake basin mask required")
        for cell in np.flatnonzero(lake_mask.ravel() & (h.ravel() < lake_level_m)):
            cz, cx = divmod(int(cell), h.shape[1])
            for dz, dx in DIRECTIONS:
                nz, nx = cz + dz, cx + dx
                if 0 <= nz < h.shape[0] and 0 <= nx < h.shape[1]:
                    other = nz * h.shape[1] + nx
                    if owners[other] == owners[cell] and h.ravel()[other] > lake_level_m:
                        shore_pair = [int(cell), int(other)]
                        candidates["lake_shore"] = int(cell)
                        break
            if shore_pair is not None:
                break
    records = []
    if type(size) is not int or not 3 <= size <= 513:
        raise ValueError("native TD window size must be 3..513")
    for kind, cell in candidates.items():
        if cell is None:
            records.append({"kind": kind, "status": "missing_verified_wet_lake_shoreline" if kind == "lake_shore" else "missing_planned_location"})
            continue
        cz, cx = divmod(cell, h.shape[1])
        center = np.array(plan["origin_xz_m"]) + np.array([cx, cz]) * plan["spacing_m"]
        selected_pair = None
        if kind == "ridge":
            selected_pair = [int(value) for value in edges[ridge_index]]
            bz, bx = divmod(selected_pair[1], h.shape[1])
            center = np.array(plan["origin_xz_m"]) + np.array([(cx + bx) / 2, (cz + bz) / 2]) * plan["spacing_m"]
        if kind == "river":
            selected_pair = [cell, int(receiver[cell])]
            bz, bx = divmod(selected_pair[1], h.shape[1])
            center = np.array(plan["origin_xz_m"]) + np.array([(cx + bx) / 2, (cz + bz) / 2]) * plan["spacing_m"]
        if kind in ("mouth", "lake_shore"):
            selected_pair = [cell, int(receiver[cell])] if kind == "mouth" else shore_pair
            bz, bx = divmod(selected_pair[1], h.shape[1])
            level = 0.0 if kind == "mouth" else lake_level_m
            start_height, end_height = h.ravel()[selected_pair]
            if (start_height - level) * (end_height - level) > 0 or start_height == end_height:
                records.append({"kind": kind, "status": "no_real_level_crossing"})
                continue
            fraction = (level - start_height) / (end_height - start_height)
            center = np.array(plan["origin_xz_m"]) + np.array([cx + fraction * (bx - cx), cz + fraction * (bz - cz)]) * plan["spacing_m"]
        native_origin = np.floor(center / spacing_m).astype(int) - size // 2
        records.append({"kind": kind, "status": "planned", "coarse_cell": cell,
                        "native_origin_xz": native_origin.tolist(), "shape": [size, size],
                        "origin_xz_m": (native_origin * spacing_m).tolist(), "spacing_m": spacing_m})
        records[-1]["selection_edge_cell_ids"] = selected_pair
        records[-1]["selection_algorithm"] = "frozen-key-window-seasonal-wet-lake-exclusion-v2"
        if kind in ("river", "confluence"):
            records[-1]["river_selection_semantics"] = "frozen graph nodes and receivers outside verified highest-stage wet lake"
        if kind == "ridge":
            records[-1]["ridge_index"] = ridge_index
        if kind == "lake_shore":
            records[-1]["shoreline_level_m"] = lake_level_m
            records[-1]["connected_coarse_lake_mask_sha256"] = hashlib.sha256(lake_mask.tobytes()).hexdigest()
            records[-1]["shoreline_semantics"] = "verified seasonal wet connected coarse basin; fine water connectivity unverified"
    return records
