"""First version of an open-surface, horizontal strike-slip VDM fault.

The operation deliberately creates a new mesh.  It never changes the fixed
topology or saved identity of ``metric_vdm``.  The cutting plane is vertical;
the signed displacement is horizontal and follows its strike.  A selection
mask controls where the moving block fades back to the source surface.
"""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.metric_vdm import _check_mesh
from terrain_pipeline.mountain_source_adapter import (
    MAX_CELLS, identity, load_bundle, readonly, save_bundle,
)


SCHEMA = "metric-vdm-fault-v1"
ALGORITHM = "vertical-plane-horizontal-strike-slip-v1"
ARRAY_KEYS = {
    "reference_xyz_m", "vertices_xyz_m", "triangles", "vertex_side",
    "transition_weight", "applied_displacement_xyz_m", "vertex_source_index",
    "triangle_source_index", "seam_edges", "protected_mask",
}


def _finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class FaultRecipe:
    plane_origin_xz_m: tuple
    strike_degrees: float
    slip_m: float
    moving_side: str
    transition_width_m: float

    def __post_init__(self):
        if not isinstance(self.plane_origin_xz_m, tuple) or len(self.plane_origin_xz_m) != 2:
            raise ValueError("invalid plane origin")
        for value in self.plane_origin_xz_m:
            _finite(value, "plane origin")
        _finite(self.strike_degrees, "strike")
        _finite(self.slip_m, "slip")
        if self.moving_side not in ("positive", "negative"):
            raise ValueError("moving_side must be positive or negative")
        _finite(self.transition_width_m, "transition width")
        if self.transition_width_m <= 0:
            raise ValueError("transition width must be positive")


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3. - 2. * value)


def _selection_weights(reference, selection, width):
    """Approximate a metric distance-to-mask-boundary without SciPy."""
    rows, columns = selection.shape
    distances = np.full(selection.shape, np.inf, np.float64)
    outside = np.argwhere(~selection)
    if len(outside):
        inside = np.argwhere(selection)
        for row, column in inside:
            distances[row, column] = np.min(np.hypot(outside[:, 0] - row, outside[:, 1] - column))
    spacing = []
    horizontal = reference[:, :, (0, 2)]
    if rows > 1:
        spacing.extend(np.linalg.norm(np.diff(horizontal, axis=0), axis=2).ravel().tolist())
    if columns > 1:
        spacing.extend(np.linalg.norm(np.diff(horizontal, axis=1), axis=2).ravel().tolist())
    metre_spacing = float(np.median(spacing)) if spacing else 1.
    weights = np.where(selection, _smooth(distances * metre_spacing / width), 0.)
    return weights.reshape(-1)


def _clip_polygon(points, values, positive):
    result = []
    for index, point in enumerate(points):
        previous = points[index - 1]
        previous_value = values[index - 1]
        current_value = values[index]
        previous_inside = previous_value >= -1e-12 if positive else previous_value <= 1e-12
        current_inside = current_value >= -1e-12 if positive else current_value <= 1e-12
        if current_inside != previous_inside:
            denominator = previous_value - current_value
            fraction = 0.5 if abs(denominator) <= 1e-15 else previous_value / denominator
            result.append(previous + fraction * (point - previous))
        if current_inside:
            result.append(point)
    return result


def _polygon_side_vertices(points, side):
    if len(points) < 3:
        return []
    output = []
    for point in points:
        if not output or np.linalg.norm(point - output[-1]) > 1e-10:
            output.append(point)
    if len(output) > 1 and np.linalg.norm(output[0] - output[-1]) <= 1e-10:
        output.pop()
    return [(point, side) for point in output]


def apply_fault(source_vdm, *, recipe, selection_mask):
    if not isinstance(recipe, FaultRecipe):
        raise ValueError("FaultRecipe required")
    if not isinstance(source_vdm, dict) or not isinstance(source_vdm.get("arrays"), dict):
        raise ValueError("validated VDM source required")
    source = source_vdm["arrays"]
    reference = np.asarray(source.get("reference_xyz_m"))
    triangles = np.asarray(source.get("triangles"))
    protected = np.asarray(source.get("protected_mask"))
    if (reference.ndim != 3 or reference.shape[2] != 3 or reference.dtype != np.float64 or
            reference.shape[0] * reference.shape[1] > MAX_CELLS or
            triangles.ndim != 2 or triangles.shape[1] != 3 or triangles.dtype != np.int64 or
            protected.shape != reference.shape[:2] or protected.dtype != bool):
        raise ValueError("invalid source VDM geometry")
    selection = np.asarray(selection_mask)
    if selection.shape != reference.shape[:2] or selection.dtype != bool or not selection.any():
        raise ValueError("nonempty selection mask required")
    if np.any(protected & selection):
        raise ValueError("fault influence intersects protected VDM area")
    if not np.isfinite(reference).all():
        raise ValueError("nonfinite source geometry")

    strike = math.radians(recipe.strike_degrees)
    tangent = np.array([math.cos(strike), math.sin(strike)], np.float64)
    normal = np.array([-math.sin(strike), math.cos(strike)], np.float64)
    origin = np.asarray(recipe.plane_origin_xz_m, np.float64)
    flat = reference.reshape(-1, 3)
    signed = (flat[:, (0, 2)] - origin) @ normal
    source_weights = _selection_weights(reference, selection, recipe.transition_width_m)
    move_sign = 1 if recipe.moving_side == "positive" else -1
    displacement_vector = np.array([tangent[0], 0., tangent[1]]) * recipe.slip_m
    vertices = []
    vertex_sides = []
    vertex_weights = []
    vertex_sources = []
    output_triangles = []
    output_sources = []
    vertex_lookup = {}

    def add_vertex(point, side, weight, source_index=-1):
        key = (side, source_index, tuple(np.round(point, 12)))
        if key not in vertex_lookup:
            vertex_lookup[key] = len(vertices)
            vertices.append(point.copy())
            vertex_sides.append(side)
            vertex_weights.append(float(np.clip(weight, 0., 1.)))
            vertex_sources.append(source_index)
        return vertex_lookup[key]

    for source_triangle_index, triangle in enumerate(triangles):
        points = flat[triangle]
        values = signed[triangle]
        weights = source_weights[triangle]
        for positive in (True, False):
            clipped = _clip_polygon(points, values, positive)
            polygon = _polygon_side_vertices(clipped, 1 if positive else -1)
            if len(polygon) < 3:
                continue
            ids = []
            for point, side in polygon:
                distances = np.linalg.norm(points - point, axis=1)
                nearest = int(np.argmin(distances))
                source_index = int(triangle[nearest]) if distances[nearest] <= 1e-9 else -1
                weight = float(weights[nearest]) if source_index >= 0 else float(np.interp(
                    0., values, weights))
                ids.append(add_vertex(point, side, weight, source_index))
            for local in range(1, len(ids) - 1):
                candidate = (ids[0], ids[local], ids[local + 1])
                trial = np.asarray([vertices[index] for index in candidate])
                cross = np.cross(trial[1] - trial[0], trial[2] - trial[0])
                if np.linalg.norm(cross) <= 1e-12:
                    continue
                output_triangles.append(candidate)
                output_sources.append(source_triangle_index)

    if not output_triangles:
        raise ValueError("fault plane produced no surface triangles")
    vertices = np.asarray(vertices, np.float64)
    sides = np.asarray(vertex_sides, np.int8)
    weights = np.asarray(vertex_weights, np.float64)
    moving = sides == move_sign
    displacement = np.zeros_like(vertices)
    displacement[moving] = weights[moving, None] * displacement_vector
    displaced = vertices + displacement
    output_triangles = np.asarray(output_triangles, np.int64)
    output_sources = np.asarray(output_sources, np.int64)
    # Reject a swept moved patch that enters protected/unknown source cells.
    # The source protected chart is the only available protection contract in
    # this standalone API; callers with a river stencil must merge it before
    # invoking apply_fault.
    source_points = reference.reshape(-1, 3)
    influenced_triangles = triangles[np.any(source_weights[triangles] > 0., axis=1)]
    moved_source = np.unique(influenced_triangles.ravel()) if len(influenced_triangles) else np.empty(0, np.int64)
    if len(moved_source) and np.any(protected.reshape(-1)[moved_source]):
        raise ValueError("fault influence intersects protected VDM area")
    _check_mesh(displaced, output_triangles)
    seam_edges = []
    edge_counts = {}
    for triangle in output_triangles:
        for first, second in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            edge = tuple(sorted((int(first), int(second))))
            edge_counts[edge] = edge_counts.get(edge, 0) + 1
    # A seam is represented by the two open boundary copies.  Its endpoints
    # lie on the cutting plane; the copies intentionally have the same side
    # label within each triangle and therefore cannot be detected by looking
    # for a mixed-side triangle edge.
    # Retain all explicit clipped vertices whose source position lies on the
    # plane; these are the two copies that form the open seam.
    for edge in edge_counts:
        endpoints = np.asarray([vertices[index] for index in edge]) if len(vertices) else np.empty((0, 3))
        if len(endpoints) and np.all(np.abs((endpoints[:, (0, 2)] - origin) @ normal) <= 1e-8):
            seam_edges.append(edge)
    arrays = {
        "reference_xyz_m": readonly(reference.copy()),
        "vertices_xyz_m": readonly(displaced),
        "triangles": readonly(output_triangles),
        "vertex_side": readonly(sides),
        "transition_weight": readonly(weights),
        "applied_displacement_xyz_m": readonly(displacement),
        "vertex_source_index": readonly(np.asarray(vertex_sources, np.int64)),
        "triangle_source_index": readonly(output_sources),
        "seam_edges": readonly(np.asarray(seam_edges, np.int64).reshape(-1, 2)),
        "protected_mask": readonly(protected.copy()),
    }
    metadata = {
        "schema": SCHEMA, "algorithm": ALGORITHM, "coordinates": "xyz metres; X east, Y up, Z south",
        "source_identity": source_vdm.get("identity_sha256", ""),
        "protection_identity": source_vdm.get("metadata", {}).get("protection_identity", ""),
        "plane_origin_xz_m": list(recipe.plane_origin_xz_m), "strike_degrees": recipe.strike_degrees,
        "slip_m": recipe.slip_m, "moving_side": recipe.moving_side,
        "transition_width_m": recipe.transition_width_m, "slip_axis": "horizontal_strike",
        "closed_surface": False, "selection_shape_zx": list(selection.shape),
        "selection_cell_count": int(selection.sum()), "source_triangle_count": int(len(triangles)),
        "output_triangle_count": int(len(output_triangles)), "seam_edge_count": int(len(seam_edges)),
        "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
        "self_intersection_verified": False, "overlap_diagnostic": "not_verified",
    }
    if not metadata["source_identity"]:
        raise ValueError("source VDM identity required")
    result = {"arrays": arrays, "metadata": metadata,
              "identity_sha256": identity(arrays, metadata)}
    validate_fault(result)
    return result


def validate_fault(result):
    if not isinstance(result, dict) or set(result) != {"arrays", "metadata", "identity_sha256"}:
        raise ValueError("invalid fault bundle")
    arrays, metadata = result["arrays"], result["metadata"]
    if set(arrays) != ARRAY_KEYS or metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM:
        raise ValueError("invalid fault fields")
    for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable", "self_intersection_verified"):
        if metadata.get(flag) is not False:
            raise ValueError("fault certification flags must remain false")
    vertices = arrays["vertices_xyz_m"]
    triangles = arrays["triangles"]
    sides = arrays["vertex_side"]
    if (vertices.dtype != np.float64 or vertices.ndim != 2 or vertices.shape[1] != 3 or
            triangles.dtype != np.int64 or triangles.ndim != 2 or triangles.shape[1] != 3 or
            np.any(triangles < 0) or np.any(triangles >= len(vertices)) or
            sides.dtype != np.int8 or sides.shape != (len(vertices),) or
            not np.isin(sides, (-1, 1)).all() or
            arrays["transition_weight"].shape != (len(vertices),) or
            arrays["applied_displacement_xyz_m"].shape != vertices.shape or
            arrays["vertex_source_index"].shape != (len(vertices),) or
            arrays["triangle_source_index"].shape != (len(triangles),) or
            arrays["seam_edges"].ndim != 2 or arrays["seam_edges"].shape[1] != 2 or
            not np.isfinite(vertices).all() or not np.isfinite(arrays["transition_weight"]).all() or
            np.any(arrays["transition_weight"] < 0) or np.any(arrays["transition_weight"] > 1)):
        raise ValueError("invalid fault array shape or values")
    triangle_sides = sides[triangles]
    if np.any((triangle_sides.min(axis=1) < 0) & (triangle_sides.max(axis=1) > 0)):
        raise ValueError("triangle crosses open fault seam")
    _check_mesh(vertices, triangles)
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("fault identity mismatch")
    return True


def _headers(headers):
    if set(headers) != ARRAY_KEYS | {"manifest"}:
        raise ValueError("unexpected fault archive fields")


def save_fault(path, result):
    save_bundle(path, result, validator=validate_fault)


def load_fault(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_fault,
                         header_validator=_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external fault identity mismatch")
    return result
