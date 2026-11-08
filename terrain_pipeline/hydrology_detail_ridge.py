"""Global wide-support ridge proposals, never narrow walls or acceptance claims."""

import numpy as np
import hashlib

from terrain_pipeline.hydrology_detail import _coordinates, _interpolate, derive_detail, _digest


def transformed_coarse_plan(plan, lake_level_m):
    """One monotone world elevation map, with sea and certified stage fixed.

    This is a geometric proposal, not a revalidated seasonal lake geometry.
    The cube root expands low coastal relief without any window-local offset.
    """
    if not np.isfinite(lake_level_m) or lake_level_m <= 0:
        raise ValueError("positive verified lake stage required")
    height = stage_fixed_transform(np.asarray(plan["height_m"], dtype=np.float64), lake_level_m)
    knots = np.linspace(0.0, lake_level_m, 17)
    return dict(plan, height_m=height, path_reference_height_m=np.asarray(plan["height_m"]),
                path_height_map={"knots_m": knots.tolist(), "values_m": (lake_level_m * np.cbrt(knots / lake_level_m)).tolist()})


def stage_fixed_transform(height, stage):
    """Fixed sixteen-segment monotone relief map; finite coastal derivative."""
    knots = np.linspace(0.0, stage, 17)
    transformed = np.interp(height, knots, stage * np.cbrt(knots / stage))
    return np.where((height > 0) & (height < stage), transformed, height)


def continuous_macro_field(plan, x, z, *, validate_query_support_only=False):
    """Continuous eight-triangle fans around globally fixed coarse centers.

    Shared faces and corners have one elevation independent of the querying
    owner. Real frozen diagonal river edges constrain their shared corner;
    incompatible overlapping graph segments are rejected explicitly.
    """
    h = np.asarray(plan["height_m"], dtype=np.float64)
    owner = np.asarray(plan["owner_domain_id"])
    rows, cols = h.shape
    if validate_query_support_only:
        nearest_x, nearest_z = np.rint(x).astype(int), np.rint(z).astype(int)
        neighbor_x = np.clip(nearest_x + np.where(x - nearest_x >= 0, 1, -1), 0, cols - 1)
        neighbor_z = np.clip(nearest_z + np.where(z - nearest_z >= 0, 1, -1), 0, rows - 1)
        query_corners = set(zip(np.clip(np.minimum(nearest_z, neighbor_z), 0, rows - 2).ravel(),
                                np.clip(np.minimum(nearest_x, neighbor_x), 0, cols - 2).ravel()))
    corners = np.empty((rows - 1, cols - 1), dtype=np.float64)
    for cz in range(rows - 1):
        for cx in range(cols - 1):
            patch = h[cz:cz + 2, cx:cx + 2]
            labels = owner[cz:cz + 2, cx:cx + 2]
            corners[cz, cx] = patch.max() + max(1.0, float(np.ptp(patch))) if len(set(labels.ravel()) - {-1}) > 1 else patch.mean()
    receivers = np.asarray(plan["receiver"]).ravel()
    river = np.asarray(plan.get("river_mask", np.zeros(h.shape, bool))).ravel()
    intervals = {}
    for first in np.flatnonzero(river & (receivers >= 0)):
        second = int(receivers[first])
        az, ax = divmod(int(first), cols)
        bz, bx = divmod(second, cols)
        if abs(ax - bx) == abs(az - bz) == 1:
            key = (min(az, bz), min(ax, bx))
            lower, upper = sorted((float(h.ravel()[first]), float(h.ravel()[second])))
            previous = intervals.get(key, (-np.inf, np.inf))
            intervals[key] = (max(lower, previous[0]), min(upper, previous[1]))
    for key, (lower, upper) in intervals.items():
        if validate_query_support_only and key not in query_corners:
            continue
        if lower >= upper:
            raise ValueError("frozen diagonal rivers have incompatible continuous crossing heights")
        if len(set(owner[key[0]:key[0] + 2, key[1]:key[1] + 2].ravel()) - {-1}) > 1:
            raise ValueError("frozen diagonal river touches a mixed-owner corner")
        corners[key] = (lower + upper) / 2
    nx, nz = np.rint(x).astype(int), np.rint(z).astype(int)
    dx, dz = x - nx, z - nz
    sx, sz = np.where(dx >= 0, 1, -1), np.where(dz >= 0, 1, -1)
    tx, tz = np.clip(nx + sx, 0, cols - 1), np.clip(nz + sz, 0, rows - 1)
    horizontal = np.abs(dx) >= np.abs(dz)
    fx, fz = np.where(horizontal, tx, nx), np.where(horizontal, nz, tz)
    center, neighbor = h[nz, nx], h[fz, fx]
    mixed = (owner[nz, nx] >= 0) & (owner[fz, fx] >= 0) & (owner[nz, nx] != owner[fz, fx])
    face = (center + neighbor) / 2
    face[mixed] = np.maximum(center[mixed], neighbor[mixed]) + np.maximum(1.0, np.abs(center[mixed] - neighbor[mixed]))
    corner = corners[np.clip(np.minimum(nz, tz), 0, rows - 2), np.clip(np.minimum(nx, tx), 0, cols - 2)]
    corner_weight = 2 * np.minimum(np.abs(dx), np.abs(dz))
    face_weight = 2 * np.abs(np.abs(dx) - np.abs(dz))
    return (1 - corner_weight - face_weight) * center + face_weight * face + corner_weight * corner


def derive_global_macro(plan, detail, *, lake_level_m, budget=None, residual_fraction=0.0):
    """Audit a deterministic global fan geometry against immutable true TD."""
    meta, arrays = detail["metadata"], detail["arrays"]
    raw = arrays["original_td_m"]
    transformed = transformed_coarse_plan(plan, lake_level_m)
    x, z = _coordinates(plan, meta["origin_xz_m"], raw.shape, meta["spacing_m"])
    # Transform the continuous field itself: its sea and lake level sets must
    # stay fixed, unlike interpolation of independently transformed vertices.
    proposal = stage_fixed_transform(continuous_macro_field(plan, x, z), lake_level_m)
    if residual_fraction not in (0.0, 0.05):
        raise ValueError("one declared global residual fraction required; no candidate search")
    retained = np.full(raw.shape, residual_fraction)
    if residual_fraction:
        baseline = np.asarray(plan["original_height_m"], dtype=np.float64).copy()
        nodes = meta.get("baseline_node_provenance", {})
        if not nodes:
            raise ValueError("pinned canonical TD coarse anchors required for global residual")
        for key, record in nodes.items():
            cz, cx = (int(value) for value in key.split(":"))
            baseline[cz, cx] = record["elevation_m"]
        px = meta["origin_xz_m"][0] + np.arange(raw.shape[1])[None, :] * meta["spacing_m"]
        pz = meta["origin_xz_m"][1] + np.arange(raw.shape[0])[:, None] * meta["spacing_m"]
        distance = np.full(raw.shape, np.inf)
        for first, second in np.asarray(plan["shared_boundary_edges"]):
            az, ax = divmod(int(first), baseline.shape[1])
            bz, bx = divmod(int(second), baseline.shape[1])
            if abs(ax - bx) + abs(az - bz) != 1:
                continue
            middle = np.asarray(plan["origin_xz_m"]) + np.array([(ax + bx) / 2, (az + bz) / 2]) * plan["spacing_m"]
            if ax != bx:
                dx, dz = np.abs(px - middle[0]), np.maximum(np.abs(pz - middle[1]) - plan["spacing_m"] / 2, 0)
            else:
                dx, dz = np.maximum(np.abs(px - middle[0]) - plan["spacing_m"] / 2, 0), np.abs(pz - middle[1])
            distance = np.minimum(distance, np.hypot(dx, dz))
        fraction = np.clip((distance - 2 * meta["spacing_m"]) / (plan["spacing_m"] / 2), 0.0, 1.0)
        retained *= fraction * fraction * (3 - 2 * fraction)
        receivers = np.asarray(plan["receiver"]).ravel()
        river = np.asarray(plan["river_mask"]).ravel()
        corridor_distance = np.full(raw.shape, np.inf)
        for first in np.flatnonzero(river & (receivers >= 0)):
            second = int(receivers[first])
            az, ax = divmod(int(first), baseline.shape[1])
            bz, bx = divmod(second, baseline.shape[1])
            start = np.asarray(plan["origin_xz_m"]) + np.array([ax, az]) * plan["spacing_m"]
            vector = np.array([bx - ax, bz - az]) * plan["spacing_m"]
            along = np.clip(((px - start[0]) * vector[0] + (pz - start[1]) * vector[1]) / np.dot(vector, vector), 0, 1)
            corridor_distance = np.minimum(corridor_distance, np.hypot(px - start[0] - along * vector[0], pz - start[1] - along * vector[1]))
        fraction = np.clip((corridor_distance - plan["spacing_m"] / 2) / (plan["spacing_m"] / 2), 0, 1)
        retained *= fraction * fraction * (3 - 2 * fraction)
        # The same global stage band applies to every inland shoreline,
        # independent of which diagnostic window intersects it.
        inland_ids = [domain["domain_id"] for domain in plan["domains"] if domain["kind"] == "inland"]
        inland_support = _interpolate(np.isin(plan["owner_domain_id"], inland_ids).astype(float), x, z) > 0
        stage_distance = np.abs(proposal - lake_level_m)
        fraction = np.clip((stage_distance - lake_level_m / 16) / (lake_level_m / 16), 0, 1)
        shore_retention = fraction * fraction * (3 - 2 * fraction)
        retained *= np.where(inland_support, shore_retention, 1.0)
        proposal += retained * (raw - _interpolate(baseline, x, z))
    from scipy.ndimage import distance_transform_edt, label
    coarse_owners = np.asarray(plan["owner_domain_id"])
    nearest_x, nearest_z = np.rint(x).astype(int), np.rint(z).astype(int)
    fine_owners = coarse_owners[nearest_z, nearest_x].copy()
    coastal_ids = {domain["domain_id"] for domain in plan["domains"] if domain["kind"] == "coastal"}
    coastal = np.isin(coarse_owners, list(coastal_ids))
    nearest_land = distance_transform_edt(~coastal, return_distances=False, return_indices=True)
    extended_coastal = coarse_owners[nearest_land[0], nearest_land[1]][nearest_z, nearest_x]
    ocean_stencil = _interpolate(np.asarray(plan["ocean_mask"], dtype=float), x, z) > 0
    actual_ocean = ocean_stencil & (proposal < 0)
    fine_owners[(fine_owners == -1) & ~actual_ocean] = extended_coastal[(fine_owners == -1) & ~actual_ocean]
    fine_owners[actual_ocean] = -1
    fine_support = {"algorithm": "frozen-ocean-support-continuous-zero-isoline-v1", "owner_domain_id": fine_owners,
        "ocean_mask": actual_ocean, "definition": "negative continuous macro within frozen ocean interpolation stencil; positive ocean-label support extends nearest frozen coastal land owner globally"}
    lake_support = None
    if meta["window_kind"] == "lake_shore":
        from terrain_pipeline.runoff import LakeGeometry as LakeGeometry
        inland = [domain for domain in plan["domains"] if domain["kind"] == "inland"]
        if len(inland) != 1:
            raise ValueError("shore proposal requires one explicit verified inland lake")
        lake = LakeGeometry(plan["height_m"], coarse_owners, inland[0], plan["spacing_m"] ** 2)
        basin = _interpolate(lake.mask.astype(float), x, z) > 0
        wet = basin & (proposal < lake_level_m) & (fine_owners == inland[0]["domain_id"])
        anchors = wet & (np.asarray(plan["height_m"])[nearest_z, nearest_x] < lake_level_m)
        boundary = np.zeros(raw.shape, bool)
        boundary[[0, -1], :] = True
        boundary[:, [0, -1]] = True
        components, _ = label(wet)
        accepted_components = np.unique(components[anchors & boundary])
        accepted_components = accepted_components[accepted_components > 0]
        connected = np.isin(components, accepted_components)
        lake_support = {"connected_wet_mask": connected, "level_m": lake_level_m,
            "coarse_basin_mask_sha256": hashlib.sha256(lake.mask.tobytes()).hexdigest(),
            "local_connectivity": "D4 wet component contacts finite-window boundary inside verified coarse wet basin; fine outside-window connectivity unverified",
            "local_wet_area_m2": int(connected.sum()) * meta["spacing_m"] ** 2,
            "fine_basin_seasonal_revalidated": False}
    provenance = {"artifact_kind": "derived_terrain_diffusion_macro_geometry", "td_inference_run": False,
        "parent_archive_sha256": meta["raw_provenance"]["archive_sha256"],
        "proposal_array_sha256": hashlib.sha256(proposal.tobytes()).hexdigest(),
        "derivation": "global sea/lake-fixed sixteen-segment monotone map of continuous coarse fan with declared canonical TD residual fraction"}
    result = derive_detail(transformed, raw, origin_xz_m=meta["origin_xz_m"], spacing_m=meta["spacing_m"],
        raw_provenance=meta["raw_provenance"], window_kind=meta["window_kind"], budget=budget,
        candidate_height_m=proposal, candidate_provenance=provenance, fine_support=fine_support, lake_support=lake_support)
    result["arrays"]["td_residual_retention"] = retained
    result["metadata"].update({"proposal_algorithm": "global-stage-fixed-fan-v4", "fixed_lake_level_m": lake_level_m,
        "fine_basin_seasonal_revalidated": False, "hydrologic_naturalness_verified": False,
        "td_residual_fraction": residual_fraction,
        "global_residual_support": "5 percent maximum; zero within 2 native divide pixels, half-coarse-spacing river corridors, stage/16 inland shore band; C1 global transitions",
        "td_residual_suppression": "complete macro feasibility baseline" if not residual_fraction else "95 percent residual loss; further C1 shared divide attenuation; naturalness unverified",
        "original_frozen_plan_identity": plan["identity"] if "identity" in plan else meta.get("plan_identity")})
    result["metadata"].pop("identity")
    result["metadata"]["identity"] = _digest({"metadata": result["metadata"], "arrays": {
        name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in sorted(result["arrays"].items())}})
    return result


def derive_wide_ridge(plan, detail, *, width_m=None, ridge_margin_m=1.0, budget=None):
    """One bounded macro proposal per frozen face; far-field TD stays untouched.

    Each face spans one coarse cell tangentially. A C1 envelope decays over at
    least half a coarse spacing on either side and at segment endpoints. The
    proposal is a visibly testable macro edit, not a hydrological proof.
    """
    meta, arrays = detail["metadata"], detail["arrays"]
    raw = arrays["original_td_m"]
    width_m = plan["spacing_m"] / 2 if width_m is None else width_m
    if not np.isfinite(width_m) or not plan["spacing_m"] / 2 <= width_m <= plan["spacing_m"]:
        raise ValueError("wide ridge support must span half to one coarse spacing")
    if not np.isfinite(ridge_margin_m) or not 0 < ridge_margin_m <= 10:
        raise ValueError("explicit ridge margin must be 0..10m")
    x, z = _coordinates(plan, meta["origin_xz_m"], raw.shape, meta["spacing_m"])
    coarse = np.asarray(plan["height_m"])
    target = _interpolate(coarse, x, z)
    px = meta["origin_xz_m"][0] + np.arange(raw.shape[1])[None, :] * meta["spacing_m"]
    pz = meta["origin_xz_m"][1] + np.arange(raw.shape[0])[:, None] * meta["spacing_m"]
    retained = np.ones(raw.shape)
    raise_field = np.zeros(raw.shape)
    for first, second in np.asarray(plan["shared_boundary_edges"]):
        az, ax = divmod(int(first), coarse.shape[1])
        bz, bx = divmod(int(second), coarse.shape[1])
        if abs(ax - bx) + abs(az - bz) != 1:
            continue
        midpoint = np.array(plan["origin_xz_m"]) + np.array([(ax + bx) / 2, (az + bz) / 2]) * plan["spacing_m"]
        if ax != bx:
            dx = np.abs(px - midpoint[0])
            dz = np.maximum(np.abs(pz - midpoint[1]) - plan["spacing_m"] / 2, 0)
        else:
            dx = np.maximum(np.abs(px - midpoint[0]) - plan["spacing_m"] / 2, 0)
            dz = np.abs(pz - midpoint[1])
        normalized = np.minimum(np.hypot(dx, dz) / width_m, 1.0)
        weight = 1 - normalized * normalized * (3 - 2 * normalized)
        cap = max(coarse.ravel()[first], coarse.ravel()[second]) + ridge_margin_m
        raise_field = np.maximum(raise_field, np.maximum(cap - target, 0) * weight)
        retained = np.minimum(retained, 1 - weight)
    # Residual relative to the already-audited macro target is retained away
    # from the global face support. Every lost metre remains in total change.
    existing_macro = arrays["derived_height_m"]
    proposal = target + raise_field + retained * (existing_macro - target)
    candidate_provenance = {"artifact_kind": "derived_terrain_diffusion_macro_geometry", "td_inference_run": False,
        "parent_archive_sha256": meta["raw_provenance"]["archive_sha256"],
        "proposal_array_sha256": hashlib.sha256(proposal.tobytes()).hexdigest(),
        "derivation": "explicit global wide ridge edit of genuine TD; not new model inference"}
    result = derive_detail(plan, raw, origin_xz_m=meta["origin_xz_m"], spacing_m=meta["spacing_m"],
        raw_provenance=meta["raw_provenance"], window_kind="ridge", budget=budget,
        candidate_height_m=proposal, candidate_provenance=candidate_provenance)
    result["arrays"]["wide_ridge_raise_m"] = raise_field
    result["arrays"]["td_residual_retention"] = retained
    result["metadata"]["macro_edit_semantics"] = "explicit globally continuous wide-support ridge proposal; actual D8 acceptance still required"
    result["metadata"]["wide_ridge_width_m"] = width_m
    result["metadata"]["wide_ridge_margin_m"] = ridge_margin_m
    result["metadata"]["hydrologic_naturalness_verified"] = False
    result["metadata"].pop("identity")
    result["metadata"]["identity"] = _digest({"metadata": result["metadata"], "arrays": {
        name: hashlib.sha256(value.tobytes()).hexdigest() for name, value in sorted(result["arrays"].items())}})
    return result
