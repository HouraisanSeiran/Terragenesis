"""Associate original local-bed certificates with exact design-depth supports."""
import numpy as np

from .metric_local_design_bed import build_local, assess_local


def design_support_edges(point, points, receiver, width, depth, spacing,
                         lower_cut, source_padding):
    """Return every edge attaining this vertex's original design cut lower bound."""
    edges = np.flatnonzero(receiver >= 0)
    if not len(edges) or lower_cut <= 0.:
        return []
    delta = points[receiver[edges]] - points[edges]
    t = np.clip(np.sum((point - points[edges]) * delta, axis=1)
                / np.sum(delta * delta, axis=1), 0., 1.)
    distance = np.linalg.norm(point - (points[edges] + t[:, None] * delta), axis=1)
    design = np.maximum(depth[edges], depth[receiver[edges]])
    half = np.maximum(width[edges], width[receiver[edges]]) / 2. + np.sqrt(2.) * spacing
    amount = np.minimum(design, np.maximum(0., (half + 2. * design - distance) / 2.))
    maximum = float(np.max(amount, initial=0.))
    if maximum <= 0. or abs(maximum + source_padding - lower_cut) > 1e-8:
        return []
    return [(int(source), int(receiver[source]), float(amount[index]))
            for index, source in enumerate(edges) if abs(amount[index] - maximum) <= 1e-10]


def assess_local_bed(points, receiver, width, depth, profile, terrain, window, *,
                     spacing, max_cut, bottom_slope, minimum_slope,
                     time_limit=120., feasibility_tolerance=1e-9):
    """Build and assess the actual local relaxation without a second LP layer.

    A clear result permits route search only. The complete bed solver remains
    responsible for global feasibility and final acceptance.
    """
    model = build_local(points, receiver, width, depth, profile, terrain, window,
        spacing=spacing, max_cut=max_cut, bottom_slope=bottom_slope,
        minimum_slope=minimum_slope)
    result = assess_local(model, time_limit=time_limit,
                          feasibility_tolerance=feasibility_tolerance)
    assessment = dict(status=result["outcome"], solver_status=result["status"],
        message=result["message"], variables=result["variable_count"], rows=result["row_count"],
        solver_calls=result.get("solver_calls", 1),
        radius_policy=model["transverse_radius_policy"],
        boundary_policy=model["boundary_policy"])
    for name in ("maximum_row_residual_m", "maximum_bound_residual_m"):
        if name in result:
            assessment[name] = result[name]
    extra = result.get("extra_cut")
    if assessment["status"] != "infeasible" or extra is None or not extra.get("certificate_valid", False):
        return assessment
    assessment["extra_cut"] = extra["minimum_extra_ceiling_m"]
    contributions, roots = {}, []
    for position, vertex in enumerate(extra["root_vertex_indices"]):
        vertex = int(vertex)
        dual = float(extra["root_lower_bound_duals"][position])
        supporting = design_support_edges(model["vertices"][vertex], points, receiver,
            width, depth, spacing, model["bounds"][vertex, 0], model["source_padding"][vertex])
        roots.append(dict(vertex_xz_m=model["vertices"][vertex].tolist(), dual=dual,
                          lower_cut_m=float(model["bounds"][vertex, 0]),
                          source_padding_m=float(model["source_padding"][vertex]),
                          supporting_edges=[[source, target] for source, target, _ in supporting]))
        for source, target, amount in supporting:
            edge = (source, target)
            contributions[edge] = contributions.get(edge, 0.) + dual * amount
    assessment["dual_roots"] = roots
    assessment["contributing_edges"] = sorted(contributions,
        key=lambda edge: (-contributions[edge], edge))
    return assessment
