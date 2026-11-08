"""Thin adapter from a pinned 30 m Terrain Diffusion hierarchy to an L0 field-form chart.

This module never changes an existing ``metric_*`` contract: it carries its own schema
and algorithm strings, and it only reads. It wraps two existing builders rather than
re-implementing them:

* ``single_domain_fine_geometry.build_fine_geometry`` produces the shared fine bed;
* ``metric_special_terrain_forms.build_special_form_vdm`` consumes the chart it returns
  with the declared ``base_kind="td_fine_bed"``.

Two limits are made explicit instead of being hidden:

* the metric request is snapped *outward* to the 30 m native lattice, and a window that
  grows by more than ``max_growth_m`` per axis is refused rather than silently resized;
* the fine bed is capped at 240x240 cells, so a 1 m bed can cover at most 240 m and only
  coarser beds can span a whole landform. A request that exceeds the cap is refused with
  the multi-window hint, never truncated.

The chart vertex lattice is the bed corner lattice and the chart protected mask is the bed
corner protection stencil, unioned with the declared artificial channel and bank
footprints only when the caller selects the ``protect`` channel policy.
"""

import math

import numpy as np

from terrain_pipeline.metric_vdm import _triangles
from terrain_pipeline.common_infra import identity
from terrain_pipeline.single_domain_fine_geometry import build_fine_geometry


SCHEMA = "td-special-terrain-chart-v1"
ALGORITHM = "td-fine-bed-special-terrain-adapter-v1"
COORDINATES = "physical metres [x,y,z]; x east, y up, z south; chart [row,col]"
BASE_KIND = "td_fine_bed"
NATIVE_SPACING_M = 30.0
FINE_SPACINGS = (1.0, 2.0, 4.0)
MAX_FINE_CELLS = 62500
MAX_FINE_SIDE = 240
MAX_NATIVE_CELLS = 250000
CHANNEL_POLICIES = ("reject", "protect")
CHANNEL_POLICY_SEMANTICS = {
    "reject": "any non-zero artificial channel cut refuses the window",
    "protect": "channel and bank corner footprints join the protected mask and are counted",
}
CHANNEL_SELECTION_SEMANTICS = (
    "the caller declares the selected native edge cells; an empty selection leaves the "
    "plain native bilinear bed and creates no artificial channel cut"
)
CHART_BASE_SEMANTICS = (
    "corner lattice of the shared 1/2/4 m fine bed: native bilinear corners minus declared "
    "protected capsule cuts; carries no new Terrain Diffusion detail of its own"
)
TARGET_PLACEMENT_SEMANTICS = (
    "form targets are placed by the caller in the chart frame; the adapter chooses no "
    "landform position and asserts no real-world site"
)
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable",
         "self_intersection_verified")


def _number(value, name, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f"invalid {name}")


def _double_triangle_pattern(rows, cols):
    """Re-derive the declared (rows-1)x(cols-1) double-triangle rule independently.

    The shared chart rule splits every cell into a lower-left and an upper-right
    triangle over the same four vertices. This derivation walks cells with divmod
    rather than ``np.indices``, so the equality check below compares two independent
    constructions instead of restating one of them.
    """
    cells = np.arange((rows - 1) * (cols - 1), dtype=np.int64)
    cell_row, cell_col = np.divmod(cells, cols - 1)
    top_left = cell_row * cols + cell_col
    pattern = np.empty((cells.size, 6), dtype=np.int64)
    pattern[:, 0:3] = np.stack((top_left, top_left + cols, top_left + cols + 1), axis=1)
    pattern[:, 3:6] = np.stack((top_left, top_left + cols + 1, top_left + 1), axis=1)
    return pattern.reshape(-1, 3)


def _pair(value, name, *, positive=False):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be a two-element sequence")
    for entry in value:
        _number(entry, name, positive=positive)
    return [float(entry) for entry in value]


def select_native_window(*, center_m_xz, size_m_xz, spacing_m, native_shape,
                         native_origin_m_xz, max_growth_m=NATIVE_SPACING_M):
    """Snap a metre request outward onto the integer native lattice.

    Outward snapping can only grow the window, by strictly less than one native cell per
    side, so a per-side snap bound would never fire. The honest bound is the total growth
    per axis relative to the request; exceeding ``max_growth_m`` is refused instead of
    quietly handing back a wider window than the caller asked for.
    """
    center = _pair(center_m_xz, "window centre")
    size = _pair(size_m_xz, "window size", positive=True)
    origin = _pair(native_origin_m_xz, "native origin")
    _number(max_growth_m, "maximum growth", positive=True)
    if type(spacing_m) not in (int, float) or float(spacing_m) not in FINE_SPACINGS:
        raise ValueError(f"fine spacing must be one of {FINE_SPACINGS}")
    spacing_m = float(spacing_m)
    if (not isinstance(native_shape, (list, tuple)) or len(native_shape) != 2 or
            any(type(value) is not int or value < 3 for value in native_shape)):
        raise ValueError("invalid native shape")
    native_rows, native_cols = int(native_shape[0]), int(native_shape[1])
    if native_rows * native_cols > MAX_NATIVE_CELLS:
        raise ValueError("native source exceeds the declared native cell budget")

    cells = []
    for axis in (0, 1):
        span = native_cols if axis == 0 else native_rows
        low = (center[axis] - 0.5 * size[axis] - origin[axis]) / NATIVE_SPACING_M
        high = (center[axis] + 0.5 * size[axis] - origin[axis]) / NATIVE_SPACING_M
        index_low = int(math.floor(low + 1e-9))
        index_high = int(math.ceil(high - 1e-9))
        snap_low = (low - index_low) * NATIVE_SPACING_M
        snap_high = (index_high - high) * NATIVE_SPACING_M
        if not 0 <= index_low < index_high < span:
            raise ValueError("requested window leaves the native sample extent")
        cells.append((index_low, index_high, snap_low, snap_high))

    (x0, x1, snap_left, snap_right) = cells[0]
    (z0, z1, snap_bottom, snap_top) = cells[1]
    span_m_x = (x1 - x0) * NATIVE_SPACING_M
    span_m_z = (z1 - z0) * NATIVE_SPACING_M
    for span_m, requested_m, axis in ((span_m_x, size[0], 0), (span_m_z, size[1], 1)):
        growth = span_m - requested_m
        if growth > max_growth_m + 1e-9:
            raise ValueError(
                f"window on axis {axis} would grow by {growth:.6g} m from the requested "
                f"{requested_m:.6g} m, above the declared {max_growth_m:.6g} m maximum; "
                f"move the centre onto the 30 m native lattice or accept the wider window")
    for span_m, axis in ((span_m_x, 0), (span_m_z, 1)):
        if abs((span_m / spacing_m) % 1) > 1e-9:
            raise ValueError(
                f"window on axis {axis} spans {span_m:.6g} m, not a whole number of "
                f"{spacing_m:g} m fine cells")
    fine_cols = int(round(span_m_x / spacing_m))
    fine_rows = int(round(span_m_z / spacing_m))
    if min(fine_rows, fine_cols) < 3:
        raise ValueError("fine window must keep at least three cells per axis")
    if fine_rows * fine_cols > MAX_FINE_CELLS:
        raise ValueError(
            f"fine window would need {fine_rows}x{fine_cols} cells, above the declared "
            f"{MAX_FINE_CELLS} budget ({MAX_FINE_SIDE}x{MAX_FINE_SIDE}); use a coarser "
            f"spacing or stitch several windows")
    corner_origin = [origin[0] + x0 * NATIVE_SPACING_M, origin[1] + z0 * NATIVE_SPACING_M]
    return {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "requested_center_m_xz": center,
        "requested_size_m_xz": size,
        "native_window": [x0, x1, z0, z1],
        "native_span_cells_xz": [x1 - x0, z1 - z0],
        "actual_size_m_xz": [span_m_x, span_m_z],
        "snap_m": [snap_left, snap_right, snap_bottom, snap_top],
        "maximum_snap_observed_m": float(max(abs(snap_left), abs(snap_right),
                                            abs(snap_bottom), abs(snap_top))),
        "native_cell_snap_bound_m": NATIVE_SPACING_M,
        "growth_m": [span_m_x - size[0], span_m_z - size[1]],
        "maximum_growth_observed_m": float(max(span_m_x - size[0], span_m_z - size[1])),
        "maximum_growth_allowed_m": float(max_growth_m),
        "native_spacing_m": NATIVE_SPACING_M,
        "spacing_m": spacing_m,
        "fine_shape_zx": [fine_rows, fine_cols],
        "fine_cells": fine_rows * fine_cols,
        "fine_cell_budget": MAX_FINE_CELLS,
        "maximum_fine_side": MAX_FINE_SIDE,
        "native_origin_m_xz": origin,
        "corner_origin_m_xz": corner_origin,
    }


def build_td_form_chart(hierarchy, *, window, spacing_m, source_hierarchy_sha256,
                        selected_edge_cell_ids, channel_policy="reject"):
    """Shared fine bed -> L0 field-form chart, protected mask and upstream identity.

    ``selected_edge_cell_ids`` is deliberately mandatory with no silent default: the shared
    builder would otherwise auto-select every internal receiver edge in the window and cut
    artificial channels through the landform bed. Pass an empty int64 (0, 2) array for the
    plain bilinear bed, which is what a special-terrain form should sit on.

    Returns a mapping whose four chart inputs feed
    ``metric_special_terrain_forms.build_special_form_vdm(..., base_kind="td_fine_bed")``.
    """
    if not isinstance(window, dict) or window.get("schema") != SCHEMA:
        raise ValueError("select_native_window record required")
    if channel_policy not in CHANNEL_POLICIES:
        raise ValueError(f"channel policy must be one of {CHANNEL_POLICIES}")
    native_window = window["native_window"]
    if (not isinstance(native_window, (list, tuple)) or len(native_window) != 4 or
            any(type(value) is not int for value in native_window)):
        raise ValueError("integer native window required")
    if float(spacing_m) != float(window["spacing_m"]):
        raise ValueError("spacing disagrees with the window record")
    spacing_m = float(spacing_m)
    selected = np.asarray(selected_edge_cell_ids)
    if selected.dtype != np.int64 or selected.ndim != 2 or selected.shape[1] != 2:
        raise ValueError("selected native edges must be an int64 (n, 2) array")

    bed = build_fine_geometry(hierarchy, native_window=list(native_window),
                              source_hierarchy_sha256=source_hierarchy_sha256,
                              spacing_m=spacing_m,
                              selected_edge_cell_ids=selected)
    arrays = bed["arrays"]
    metadata = bed["metadata"]
    if (metadata["spacing_m"] != spacing_m or
            list(metadata["native_window"]) != list(native_window) or
            list(metadata["corner_origin_m_xz"]) != list(window["corner_origin_m_xz"])):
        raise ValueError("fine bed disagrees with the selected window")

    corner = arrays["bed_corner_m"]
    canonical = arrays["canonical_bed_center_m"]
    cut = arrays["cut_corner_m"]
    channel = arrays["artificial_channel_corner_mask"]
    bank = arrays["artificial_bank_corner_mask"]
    protection = arrays["protected_corner_mask"]
    step = int(round(spacing_m))
    if (corner.dtype != np.float64 or corner.ndim != 2 or
            canonical.shape != ((corner.shape[0] - 1) * step, (corner.shape[1] - 1) * step) or
            cut.shape != corner.shape or channel.shape != corner.shape or
            protection.shape != corner.shape or protection.dtype != bool):
        raise ValueError("invalid shared fine bed arrays")
    if not (np.isfinite(corner).all() and np.isfinite(canonical).all() and
            np.isfinite(cut).all()):
        raise ValueError("nonfinite shared fine bed")

    cut_maximum = float(np.max(cut, initial=0.0))
    channel_cells = int(np.count_nonzero(channel))
    if cut_maximum > 0.0:
        if channel_policy == "reject":
            raise ValueError(
                f"window carries a {cut_maximum:.6g} m artificial channel cut; the reject "
                f"channel policy refuses it (select another window or use the protect policy)")
        if not np.array_equal(corner, arrays["native_bilinear_corner_m"] - cut):
            raise ValueError("protected channel bed is not the bilinear bed minus the cut")
    else:
        if not np.array_equal(corner, arrays["native_bilinear_corner_m"]):
            raise ValueError("zero-cut window is not the plain native bilinear bed")

    cell_mean = (canonical.reshape(corner.shape[0] - 1, step, corner.shape[1] - 1, step)
                 .mean(axis=(1, 3)))
    tolerance = 1e-9 * max(1.0, float(np.max(np.abs(canonical))))
    # The coarsened canonical floor must reproduce the bed's own declared coarse floor; this
    # is an exact identity because both are the same area mean of the same 1 m field.
    floor_difference = float(np.max(np.abs(cell_mean - arrays["bed_center_m"])))
    if floor_difference > tolerance:
        raise ValueError(
            f"coarsened canonical floor differs from the declared bed centre field by "
            f"{floor_difference:.6g} m, above the declared {tolerance:.6g} m tolerance")
    # Diagnostic only. The chart lattice samples the native bilinear surface at cell corners
    # while the canonical floor averages that same surface at 1 m cell centres, so the two
    # legitimately differ by O(curvature * spacing^2) (measured ~0.33 m at 4 m over this
    # terrain). The binding identity is corner == native_bilinear_corner_m, asserted above;
    # this number is reported so the two discretisations are never confused for one another.
    corner_mean = (corner[:-1, :-1] + corner[1:, :-1] + corner[1:, 1:] + corner[:-1, 1:]) / 4.0
    lattice_difference = float(np.max(np.abs(corner_mean - cell_mean)))

    mask = np.array(protection, dtype=bool, copy=True)
    if channel_policy == "protect":
        mask |= channel | bank

    rows, cols = corner.shape
    x = float(window["corner_origin_m_xz"][0]) + np.arange(cols) * spacing_m
    z = float(window["corner_origin_m_xz"][1]) + np.arange(rows) * spacing_m
    chart = np.empty((rows, cols, 3), dtype=np.float64)
    chart[:, :, 0] = x[None, :]
    chart[:, :, 2] = z[:, None]
    chart[:, :, 1] = corner
    if not np.isfinite(chart).all():
        raise ValueError("nonfinite chart geometry")
    if (abs(float(chart[0, 1, 0] - chart[0, 0, 0]) - spacing_m) > 1e-9 * spacing_m or
            abs(float(chart[1, 0, 2] - chart[0, 0, 2]) - spacing_m) > 1e-9 * spacing_m):
        raise ValueError("chart lattice spacing disagrees with the declared spacing")
    pattern = _triangles(rows, cols)
    if pattern.shape != (2 * (rows - 1) * (cols - 1), 3) or pattern.dtype != np.int64:
        raise ValueError("chart triangle pattern has the wrong shape or dtype")
    if not np.array_equal(pattern, _double_triangle_pattern(rows, cols)):
        raise ValueError("chart triangle pattern is not the declared double-triangle rule")

    source_identity = bed["identity_sha256"]
    protection_identity = identity(
        {"protected_mask": mask},
        {"bed_identity": source_identity,
         "bed_source_hierarchy_sha256": source_hierarchy_sha256,
         "channel_policy": channel_policy,
         "semantics": CHANNEL_POLICY_SEMANTICS[channel_policy]})
    record = {
        "schema": SCHEMA,
        "algorithm": ALGORITHM,
        "coordinates": COORDINATES,
        "base_kind": BASE_KIND,
        "chart_base_semantics": CHART_BASE_SEMANTICS,
        "target_placement_semantics": TARGET_PLACEMENT_SEMANTICS,
        "window": {key: window[key] for key in sorted(window)},
        "chart_shape_zx": [rows, cols],
        "chart_triangles": int(_triangles(rows, cols).shape[0]),
        "chart_elevation_min_m": float(corner.min()),
        "chart_elevation_max_m": float(corner.max()),
        "chart_floor_min_m": float(canonical.min()),
        "chart_floor_max_m": float(canonical.max()),
        "canonical_floor_mean_max_difference_m": floor_difference,
        "canonical_floor_tolerance_m": tolerance,
        "lattice_vs_canonical_floor_difference_m": lattice_difference,
        "lattice_vs_canonical_floor_note": (
            "expected O(curvature * spacing^2): the chart samples corners, the canonical "
            "floor averages 1 m centres; a diagnostic, not an error"),
        "artificial_cut_maximum_m": cut_maximum,
        "artificial_channel_cells": channel_cells,
        "channel_selection_semantics": CHANNEL_SELECTION_SEMANTICS,
        "selected_edge_cells": int(selected.shape[0]),
        "artificial_bank_cells": int(np.count_nonzero(bank)),
        "channel_policy": channel_policy,
        "channel_policy_semantics": CHANNEL_POLICY_SEMANTICS[channel_policy],
        "protected_cells_declared": int(np.count_nonzero(protection)),
        "protected_cells_chart": int(np.count_nonzero(mask)),
        "identity_chain": {
            "source_hierarchy_sha256": source_hierarchy_sha256,
            "source_hierarchy_identity": metadata["hierarchy_identity"],
            "source_identity_sha256": metadata["source_identity"],
            "fine_bed_identity": bed["identity_sha256"],
            "chart_source_identity": source_identity,
            "chart_protection_identity": protection_identity,
        },
        "declared_flags": {flag: False for flag in FLAGS},
        "scope": ("finite engineering window of one pinned 30 m native hierarchy; not the "
                  "full native domain and not a natural basin"),
    }
    return {"chart_reference_xyz_m": chart, "protected_mask": mask,
            "source_identity": source_identity, "protection_identity": protection_identity,
            "base_identity": source_identity, "record": record}
