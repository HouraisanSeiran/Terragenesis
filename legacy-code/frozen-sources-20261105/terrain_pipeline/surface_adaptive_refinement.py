"""Pre-step refinement tags and conservative parent-to-child transfers."""

import numpy as np
from scipy.ndimage import maximum_filter

from terrain_pipeline.surface_adaptive_geometry import build_adaptive_geometry
from terrain_pipeline.surface_adaptive_hydraulics import canonical_inventory


def anticipated_spacing_map(canonical_depth_m, *, max_leaf_spacing_m=4, halo_m=8,
                            activity_depth_m=1e-8, canonical_forcing_m3_s=None, forcing_prediction_dt_s=.025,
                            boundary_kind=None, tailwater_m=None, canonical_bed_m=None,
                            prescribed_mask=None):
    if max_leaf_spacing_m not in (1, 2, 4) or type(halo_m) is not int or halo_m < 2 or activity_depth_m <= 0:
        raise ValueError("explicit leaf spacing, at-least-two-meter halo and positive activity threshold required")
    depth = np.asarray(canonical_depth_m)
    if depth.ndim != 2 or not np.isfinite(depth).all() or np.any(depth < 0):
        raise ValueError("finite nonnegative canonical tagging depth required")
    active = depth > activity_depth_m
    if canonical_forcing_m3_s is not None:
        forcing = np.asarray(canonical_forcing_m3_s)
        if forcing.shape != depth.shape or not np.isfinite(forcing).all() or np.any(forcing < 0):
            raise ValueError("complete finite nonnegative forcing tag required")
        active |= forcing*forcing_prediction_dt_s > activity_depth_m
    if prescribed_mask is not None:
        mask = np.asarray(prescribed_mask)
        if mask.dtype != bool or mask.shape != depth.shape:
            raise ValueError("explicit canonical initial refinement mask required")
        active |= mask
    if boundary_kind is not None:
        rows, columns = depth.shape
        kinds, tail, bed = np.asarray(boundary_kind), np.asarray(tailwater_m), np.asarray(canonical_bed_m)
        if kinds.shape != (2*(rows+columns),) or tail.shape != kinds.shape or bed.shape != depth.shape:
            raise ValueError("complete canonical reservoir pretag data required")
        potential = (kinds == 2)&(tail > np.r_[bed[:, 0], bed[:, -1], bed[0], bed[-1]])
        active[:, 0] |= potential[:rows]
        active[:, -1] |= potential[rows:2*rows]
        active[0] |= potential[2*rows:2*rows+columns]
        active[-1] |= potential[2*rows+columns:]
    buffered = maximum_filter(active.astype(np.uint8), size=2*halo_m+1, mode="constant") > 0
    requested = np.full(depth.shape, max_leaf_spacing_m, np.int64)
    requested[buffered] = 1
    return requested


def refine_adaptive_state(geometry, state, requested_spacing_m):
    """Refine only; transfer the represented stage/velocity and preserve means."""
    a, meta = geometry["arrays"], geometry["metadata"]
    actual = a["leaf_spacing_m"][a["canonical_owner"]]
    request = np.minimum(actual, np.asarray(requested_spacing_m))
    if np.array_equal(request, actual):
        return geometry, state, None
    next_geometry = build_adaptive_geometry(a["canonical_bed_m"], request, origin_m_xz=meta["origin_m_xz"],
        boundary_kind=a["boundary_kind"], boundary_crest_m=a["boundary_crest_m"])
    next_a = next_geometry["arrays"]
    h, momentum = canonical_inventory(geometry, state)
    parent = a["canonical_owner"][next_a["leaf_row"], next_a["leaf_column"]]
    next_state = np.empty((len(parent), 3))
    unchanged = next_a["leaf_spacing_m"] == a["leaf_spacing_m"][parent]
    next_state[unchanged] = state[parent[unchanged]]
    for child in np.flatnonzero(~unchanged):
        row, column, size = next_a["leaf_row"][child], next_a["leaf_column"][child], next_a["leaf_spacing_m"][child]
        patch = (slice(row, row+size), slice(column, column+size))
        next_state[child, 0] = h[patch].mean()
        next_state[child, 1:] = momentum[patch].mean(axis=(0, 1))
    before = state*a["leaf_area_m2"][:, None]
    after = next_state*next_a["leaf_area_m2"][:, None]
    grouped = np.zeros_like(before)
    np.add.at(grouped, parent, after)
    residual = grouped-before
    tolerance = 2e-11*np.maximum(1., abs(before))
    if np.any(abs(residual) > tolerance):
        raise RuntimeError("adaptive refinement does not conserve represented water and momentum")
    changed_parent = np.unique(parent[~unchanged])
    changed_child = np.flatnonzero(~unchanged)
    witness = dict(before_geometry_identity=geometry["identity_sha256"], after_geometry_identity=next_geometry["identity_sha256"],
        unchanged_parent_leaf_id=parent[unchanged], unchanged_child_leaf_id=np.flatnonzero(unchanged),
        parent_leaf_id=parent[changed_child], refined_parent_leaf_id=changed_parent, refined_child_leaf_id=changed_child,
        parent_inventory_m3_m4_s=before[changed_parent], child_inventory_m3_m4_s=after[changed_child],
        parent_grouped_residual=residual[changed_parent], refined_parent_count=int(len(changed_parent)),
        added_leaf_count=len(parent)-len(state), maximum_inventory_residual=float(abs(residual).max(initial=0)))
    return next_geometry, next_state, witness
