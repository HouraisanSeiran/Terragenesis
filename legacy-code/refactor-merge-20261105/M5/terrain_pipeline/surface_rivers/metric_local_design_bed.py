"""Local original-row relaxations used by generated river route repair.

A local infeasible result excludes the full model; local feasibility does not
certify a complete bed. No artificial window boundary is fixed to zero.
"""
from types import SimpleNamespace

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, hstack, vstack

from .metric_channel_geometry import _sample
from .metric_design_bed import (
    bed_constraints,
    design_cut_bounds,
    interior_support_boundary_vertices,
    transverse_bed_constraints,
)
from .metric_valley_union import _sparse_cells, _sparse_mesh


def _row_inside(ids, weights, retained):
    unique, inverse = np.unique(ids, return_inverse=True)
    combined = np.bincount(inverse, weights=weights)
    return bool(np.all(retained[unique[combined != 0.0]]))


def build_local(points, receiver, width, depth, profile, terrain, window, *,
                spacing, max_cut, bottom_slope, minimum_slope, maximum_depth=None):
    """Build original constraints whose combined support lies in a square.

    Bounds use the complete topology and all incident source cells. The default
    transverse radius is a lower witness of the full maximum upper cut, so it
    only omits full rows. ``maximum_depth`` may instead supply that exact full
    maximum, when already known; an arbitrary larger value is not a relaxation.
    """
    center, side = np.asarray(window["center_xz_m"]), window["side_m"]
    edges = np.flatnonzero(receiver >= 0)
    radius = (np.maximum(width[edges], width[receiver[edges]]) / 2.0
              + (np.sqrt(2.0) + 1.0) * spacing + 2.0 * max_cut)
    # Complete influencing edge support also covers every retained incident cell.
    lo = np.minimum(points[edges], points[receiver[edges]]) - radius[:, None]
    hi = np.maximum(points[edges], points[receiver[edges]]) + radius[:, None]
    selected = np.all((hi >= center - side / 2.0 - 2.0 * spacing)
                      & (lo <= center + side / 2.0 + 2.0 * spacing), axis=1)
    partial_receiver = receiver.copy()
    partial_receiver[edges[~selected]] = -1
    offsets = np.r_[0, np.cumsum(np.diff(profile[0])[selected])]
    subset_profile = [offsets]
    for values in profile[1:]:
        parts = [values[profile[0][k]:profile[0][k + 1]] for k in np.flatnonzero(selected)]
        subset_profile.append(np.concatenate(parts) if parts else values[:0])
    subset_profile = tuple(subset_profile)
    options = SimpleNamespace(fine_spacing_m=spacing, max_vertices=8_000_000)
    cells = _sparse_cells(points, partial_receiver, width, subset_profile, options,
                          terrain, support_radius_m=radius[selected])
    vertices, triangles = _sparse_mesh(cells, terrain, spacing, options.max_vertices)
    source = _sample(terrain.elevation_m, vertices, terrain)[0]
    lower, upper, padding = design_cut_bounds(
        points, receiver, width, depth, cells, vertices, triangles, terrain, spacing, max_cut)
    retained = np.all(np.abs(vertices - center) <= side / 2.0, axis=1)
    partial_boundary = interior_support_boundary_vertices(cells, vertices, terrain, spacing)
    interior_retained = retained.copy()
    interior_retained[partial_boundary] = False
    radius_policy = "explicit full-model maximum upper"
    if maximum_depth is None:
        maximum_depth = float(np.max(upper[interior_retained], initial=0.0))
        radius_policy = "maximum upper of non-boundary retained vertices; omission relaxation"
    base = bed_constraints(points, partial_receiver, cells, vertices, triangles, source,
                           terrain, spacing, subset_profile, minimum_slope)
    node_mask = np.zeros(len(receiver), bool)
    node_mask[edges[selected]] = True
    terminal = receiver < 0
    node_mask[terminal] = np.all(np.abs(points[terminal] - center)
                               <= side / 2.0 + np.max(radius, initial=0.0), axis=1)
    # Full topology keeps all incident away directions in exterior-node caps.
    transverse = transverse_bed_constraints(
        points, receiver, width, cells, vertices, triangles, source, terrain,
        spacing, np.array([maximum_depth]), node_mask, bottom_slope)
    row_ids, columns, coefficients, limits, kinds = [], [], [], [], []

    def append(ids, weights, limit, kind):
        if not _row_inside(ids, weights, retained):
            return
        row_ids.extend([len(limits)] * len(ids))
        columns.extend(ids)
        coefficients.extend(weights)
        limits.append(limit)
        kinds.append(kind)

    for ids, weights, limit, kind in base:
        append(ids, weights, limit, kind)
    strip_count = len(transverse[2]) - transverse[3]
    for row, (ids, weights, limit) in enumerate(zip(*transverse[:3])):
        append(ids, weights, limit, "strip" if row < strip_count else "cap")
    matrix = coo_matrix((coefficients, (row_ids, columns)),
                        shape=(len(limits), len(vertices))).tocsr()
    matrix.eliminate_zeros()
    active = np.unique(matrix.indices)
    return dict(matrix=matrix[:, active], limits=np.asarray(limits), kinds=np.asarray(kinds),
                vertices=vertices[active], source=source[active],
                bounds=np.column_stack((lower[active], upper[active])),
                source_padding=padding[active], selected_edges=int(selected.sum()),
                construction_vertices=len(vertices), transverse_maximum_depth=maximum_depth,
                transverse_radius_policy=radius_policy,
                boundary_policy="window boundary never locked; true full boundary upper=0 may be relaxed")


def assess_local(model, *, time_limit=120.0, feasibility_tolerance=1e-9):
    """Solve only the supplied local relaxation; time limits remain unknown."""
    variables = model["matrix"].shape[1]
    matrix, limits, bounds = model["matrix"], model["limits"], model["bounds"]
    if (limits.shape != (matrix.shape[0],) or bounds.shape != (variables, 2)
            or not all(np.all(np.isfinite(value)) for value in (matrix.data, limits, bounds))
            or np.any(bounds[:, 0] > bounds[:, 1])):
        raise ValueError("local assessment needs finite consistent rows and bounds")
    options = dict(time_limit=time_limit, primal_feasibility_tolerance=feasibility_tolerance,
                   dual_feasibility_tolerance=feasibility_tolerance)
    result = linprog(np.zeros(variables), A_ub=matrix, b_ub=limits,
                     bounds=bounds, method="highs", options=options)
    outcome = "infeasible" if result.status == 2 else "clear" if result.status == 0 else "unknown"
    assessment = dict(status=int(result.status), outcome=outcome, message=result.message,
                      variable_count=variables, row_count=matrix.shape[0], solver_calls=1,
                      interpretation="clear is local feasibility only; unknown excludes no path")
    if result.status == 0:
        solution = getattr(result, "x", None)
        if solution is None or np.shape(solution) != (variables,) or not np.all(np.isfinite(solution)):
            assessment.update(outcome="unknown", primal_valid=False)
            return assessment
        residual = max(float(np.max(matrix @ solution - limits, initial=0.0)),
                       float(np.max(bounds[:, 0] - solution, initial=0.0)),
                       float(np.max(solution - bounds[:, 1], initial=0.0)))
        assessment.update(primal_valid=residual <= 1e-8, primal_residual_m=residual)
        if residual > 1e-8:
            assessment["outcome"] = "unknown"
    if result.status != 2:
        return assessment
    # Relax only upper cut ceilings, preserving zero support boundaries.
    boundary = bounds[:, 1] == 0.0
    adjustable = np.flatnonzero(~boundary)
    ceilings = coo_matrix((np.r_[np.ones(variables), -np.ones(len(adjustable))],
                           (np.r_[np.arange(variables), adjustable],
                            np.r_[np.arange(variables), np.full(len(adjustable), variables)])),
                          shape=(variables, variables + 1)).tocsr()
    relaxed_matrix = vstack((hstack((matrix, coo_matrix((matrix.shape[0], 1)))), ceilings), format="csr")
    relaxed_limits = np.r_[limits, bounds[:, 1]]
    relaxed_bounds = np.column_stack((bounds[:, 0], np.full(variables, np.inf)))
    relaxed_bounds[boundary, 1] = 0.0
    relaxed_bounds = np.vstack((relaxed_bounds, [0.0, np.inf]))
    objective = np.r_[np.zeros(variables), 1.0]
    relaxed = linprog(objective, A_ub=relaxed_matrix, b_ub=relaxed_limits,
                      bounds=relaxed_bounds, method="highs", options=options)
    assessment["solver_calls"] = 2
    extra = dict(status=int(relaxed.status), message=relaxed.message,
                 certificate_valid=False, dual_finite=False)
    assessment["extra_cut"] = extra
    if relaxed.status != 0:
        return assessment
    row_duals = relaxed.ineqlin.marginals
    lower_duals, upper_duals = relaxed.lower.marginals, relaxed.upper.marginals
    dual_finite = all(np.all(np.isfinite(value)) for value in (row_duals, lower_duals, upper_duals))
    primal_finite = bool(np.all(np.isfinite(relaxed.x)))
    extra["dual_finite"] = dual_finite
    if not dual_finite or not primal_finite:
        return assessment
    finite_upper = np.isfinite(relaxed_bounds[:, 1])
    primal_residual = max(float(np.max(relaxed_matrix @ relaxed.x - relaxed_limits, initial=0.0)),
                          float(np.max(relaxed_bounds[:, 0] - relaxed.x, initial=0.0)),
                          float(np.max(relaxed.x[finite_upper] - relaxed_bounds[finite_upper, 1], initial=0.0)))
    stationarity = objective - relaxed_matrix.T @ row_duals - lower_duals - upper_duals
    dual_value = float(relaxed_limits @ row_duals + relaxed_bounds[:, 0] @ lower_duals
                       + relaxed_bounds[finite_upper, 1] @ upper_duals[finite_upper])
    dual_residual = max(float(np.max(np.abs(stationarity), initial=0.0)),
                        float(np.max(row_duals, initial=0.0)),
                        float(np.max(-lower_duals, initial=0.0)),
                        float(np.max(upper_duals, initial=0.0)),
                        float(np.max(np.abs(upper_duals[~finite_upper]), initial=0.0)))
    gap = abs(float(relaxed.x[-1]) - dual_value)
    valid = primal_residual <= 1e-8 and dual_residual <= 1e-8 and gap <= 1e-8
    extra.update(certificate_valid=valid, primal_residual_m=primal_residual,
                 dual_residual=dual_residual, primal_dual_gap_m=gap)
    if valid:
        roots = np.flatnonzero(lower_duals[:variables] > 1e-9)
        extra.update(minimum_extra_ceiling_m=float(relaxed.x[-1]),
                     root_vertex_indices=roots.tolist(),
                     root_lower_bound_duals=lower_duals[roots].tolist(),
                     root_vertices_xz_m=model["vertices"][roots].tolist())
        extra["root_records"] = [dict(index=int(index), xz_m=model["vertices"][index].tolist(),
                                      lower_bound_dual=float(lower_duals[index]),
                                      lower_cut_m=float(bounds[index, 0]),
                                      source_padding_m=float(model["source_padding"][index]))
                                 for index in roots]
    return assessment
