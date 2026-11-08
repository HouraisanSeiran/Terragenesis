"""Local strike-slip cuts of the deformed VDM, with exact edge provenance."""

from dataclasses import asdict
import math

import numpy as np

from terrain_pipeline.metric_vdm import _check_mesh
from terrain_pipeline.metric_vdm_fault import FaultRecipe, _selection_weights
from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle

SCHEMA = "metric-vdm-fault-v2"
ALGORITHM = "local-deformed-vdm-edge-cut-strike-slip-v2"
ARRAY_KEYS = {"reference_xyz_m", "source_vertices_xyz_m", "source_triangles", "vertices_xyz_m",
              "triangles", "vertex_side", "transition_weight", "applied_displacement_xyz_m",
              "vertex_source_index", "triangle_source_index", "seam_edges", "protected_mask",
              "vertex_source_edge", "vertex_source_fraction"}


def apply_fault(source_vdm, *, recipe, selection_mask):
    if not isinstance(recipe, FaultRecipe):
        raise ValueError("FaultRecipe required")
    recipe.__post_init__()
    source = source_vdm["arrays"]
    chart = source["reference_xyz_m"]
    points = source["vertices_xyz_m"]
    triangles = source["triangles"]
    protected = source["protected_mask"]
    selection = np.asarray(selection_mask)
    if (chart.ndim != 3 or chart.shape[-1] != 3 or points.shape != (chart.shape[0] * chart.shape[1], 3)
            or points.dtype != np.float64 or not np.isfinite(points).all()
            or len(points) > 100_000 or selection.dtype != bool or selection.shape != chart.shape[:2]
            or not selection.any() or np.any(selection & protected)
            or source_vdm["identity_sha256"] != identity(source, source_vdm["metadata"])):
        raise ValueError("invalid deformed VDM source, identity, or selection")
    _check_mesh(points, triangles)
    weights = _selection_weights(chart, selection, recipe.transition_width_m)
    influenced = np.any(weights[triangles] > 0., axis=1)
    if np.any(protected.ravel()[triangles[influenced]]):
        raise ValueError("fault influence intersects protected VDM area")
    angle = math.radians(recipe.strike_degrees)
    tangent = np.array([math.cos(angle), 0., math.sin(angle)])
    normal = np.array([-math.sin(angle), 0., math.cos(angle)])
    signed = (points - np.array([recipe.plane_origin_xz_m[0], 0., recipe.plane_origin_xz_m[1]])) @ normal
    signs = np.where(signed >= 0., 1, -1).astype(np.int8)
    cut = influenced & (signed[triangles].min(axis=1) <= 0.) & (signed[triangles].max(axis=1) >= 0.)
    vertices = points.tolist()
    sides = signs.tolist()
    vertex_weights = weights.tolist()
    edges = [[index, index] for index in range(len(points))]
    fractions = [0.] * len(points)
    vertex_sources = list(range(len(points)))
    output = triangles[~cut].tolist()
    provenance = np.flatnonzero(~cut).tolist()
    lookup = {}
    seam = set()

    def vertex(barycentric, source_face, side):
        support = np.flatnonzero(barycentric > 1e-12)
        if len(support) == 1:
            source_index = int(source_face[support[0]])
            if abs(signed[source_index]) > 1e-10:
                return source_index
            edge = (source_index, source_index)
            fraction = 0.
        else:
            edge = tuple(sorted(int(source_face[index]) for index in support))
            if len(edge) != 2:
                raise ValueError("cut vertex must lie on an original edge")
            fraction = float(barycentric[np.flatnonzero(source_face == edge[1])[0]])
            source_index = -1
        key = (edge, side)
        if key not in lookup:
            lookup[key] = len(vertices)
            vertices.append((barycentric @ points[source_face]).tolist())
            sides.append(side)
            vertex_weights.append(float(barycentric @ weights[source_face]))
            edges.append(list(edge))
            fractions.append(fraction)
            vertex_sources.append(source_index)
        return lookup[key]

    for face_index in np.flatnonzero(cut):
        source_face = triangles[face_index]
        distances = signed[source_face]
        for side in (1, -1):
            polygon = []
            for index in range(3):
                previous = (index - 1) % 3
                inside = side * distances[index] >= 0.
                prior_inside = side * distances[previous] >= 0.
                if inside != prior_inside:
                    fraction = distances[previous] / (distances[previous] - distances[index])
                    barycentric = np.zeros(3)
                    barycentric[previous] = 1. - fraction
                    barycentric[index] = fraction
                    polygon.append(vertex(barycentric, source_face, side))
                if inside:
                    polygon.append(vertex(np.eye(3)[index], source_face, side))
            polygon = list(dict.fromkeys(polygon))
            for index in range(1, len(polygon) - 1):
                face = [polygon[0], polygon[index], polygon[index + 1]]
                trial = np.asarray([vertices[value] for value in face])
                if np.linalg.norm(np.cross(trial[1] - trial[0], trial[2] - trial[0])) <= 1e-12:
                    continue
                output.append(face)
                provenance.append(int(face_index))
                for first, second in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                    if abs(float(np.dot(np.asarray(vertices[first]) - points[source_face[0]], normal)) + distances[0]) < 1e-8 and abs(float(np.dot(np.asarray(vertices[second]) - points[source_face[0]], normal)) + distances[0]) < 1e-8:
                        seam.add(tuple(sorted((first, second))))
    output_array = np.asarray(output, np.int64)
    used = np.unique(output_array)
    remap = np.full(len(vertices), -1, np.int64)
    remap[used] = np.arange(len(used))
    before = np.asarray(vertices, np.float64)[used]
    side_array = np.asarray(sides, np.int8)[used]
    weight_array = np.asarray(vertex_weights, np.float64)[used]
    displacement = weight_array[:, None] * tangent * recipe.slip_m
    moving_side = 1 if recipe.moving_side == "positive" else -1
    displacement[side_array != moving_side] = 0.
    actual_faces = remap[output_array]
    moving_faces = actual_faces[np.any(np.linalg.norm(displacement[actual_faces], axis=2) > 0., axis=1)]
    protected_positions = chart[:, :, (0, 2)][protected]
    if len(protected_positions) and len(moving_faces):
        chart_xz = chart[:, :, (0, 2)]
        spacing = np.median(np.concatenate((np.linalg.norm(np.diff(chart_xz, axis=0), axis=2).ravel(),
                                            np.linalg.norm(np.diff(chart_xz, axis=1), axis=2).ravel())))
        for face in moving_faces:
            swept = np.concatenate((before[face][:, (0, 2)], (before + displacement)[face][:, (0, 2)]))
            lower, upper = swept.min(axis=0) - spacing / 2., swept.max(axis=0) + spacing / 2.
            if np.any(np.all((protected_positions >= lower) & (protected_positions <= upper), axis=1)):
                raise ValueError("conservative swept fault patch intersects protected source cell")
    arrays = {"reference_xyz_m": chart.copy(), "source_vertices_xyz_m": points.copy(),
              "source_triangles": triangles.copy(), "vertices_xyz_m": before + displacement,
              "triangles": remap[output_array], "vertex_side": side_array,
              "transition_weight": weight_array, "applied_displacement_xyz_m": displacement,
              "vertex_source_index": np.asarray(vertex_sources, np.int64)[used],
              "triangle_source_index": np.asarray(provenance, np.int64),
              "seam_edges": remap[np.asarray(sorted(seam), np.int64).reshape(-1, 2)],
              "protected_mask": protected.copy(), "vertex_source_edge": np.asarray(edges, np.int64)[used],
              "vertex_source_fraction": np.asarray(fractions, np.float64)[used]}
    metadata = {"schema": SCHEMA, "algorithm": ALGORITHM, **asdict(recipe),
                "source_identity": source_vdm["identity_sha256"],
                "protection_identity": source_vdm["metadata"].get("protection_identity", ""),
                "coordinates": "xyz metres; X east, Y up, Z south", "slip_axis": "horizontal_strike",
                "reference_semantics": "original input chart; source_vertices are the already deformed VDM",
                "cut_semantics": "only triangles touching nonzero local selection influence are split",
                "protection_semantics": "source influence exclusion plus conservative swept XZ triangle bounding boxes against protected chart cells",
                "cut_source_triangle_count": int(cut.sum()), "selection_shape_zx": list(selection.shape),
                "selection_cell_count": int(selection.sum()), "source_triangle_count": len(triangles),
                "output_triangle_count": len(output), "seam_edge_count": len(seam),
                "closed_surface": False, "hydraulic_ready": False, "natural_outlet_verified": False,
                "publishable": False, "self_intersection_verified": False,
                "overlap_diagnostic": "not_verified"}
    result = {"arrays": {key: readonly(value) for key, value in arrays.items()}, "metadata": metadata}
    result["identity_sha256"] = identity(result["arrays"], metadata)
    validate_fault(result)
    return result


def validate_fault(result):
    arrays, metadata = result["arrays"], result["metadata"]
    if set(arrays) != ARRAY_KEYS or metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM:
        raise ValueError("invalid v2 fault fields")
    for flag in ("closed_surface", "hydraulic_ready", "natural_outlet_verified", "publishable", "self_intersection_verified"):
        if metadata.get(flag) is not False:
            raise ValueError("fault certification flags must remain false")
    for value in arrays.values():
        if not np.isfinite(value).all():
            raise ValueError("nonfinite fault array")
    points, displacement = arrays["vertices_xyz_m"], arrays["applied_displacement_xyz_m"]
    edges, fractions = arrays["vertex_source_edge"], arrays["vertex_source_fraction"]
    source = arrays["source_vertices_xyz_m"]
    triangles = arrays["triangles"]
    weights, sides = arrays["transition_weight"], arrays["vertex_side"]
    if (points.dtype != np.float64 or points.ndim != 2 or points.shape[1] != 3
            or displacement.shape != points.shape or edges.shape != (len(points), 2)
            or edges.dtype != np.int64 or np.any(edges < 0) or np.any(edges >= len(source))
            or fractions.shape != (len(points),) or np.any(fractions < 0.) or np.any(fractions > 1.)
            or weights.shape != (len(points),) or np.any(weights < 0.) or np.any(weights > 1.)
            or sides.shape != (len(points),) or not np.isin(sides, (-1, 1)).all()):
        raise ValueError("invalid fault edge provenance or shapes")
    before = source[edges[:, 0]] * (1. - fractions[:, None]) + source[edges[:, 1]] * fractions[:, None]
    if not np.allclose(points - displacement, before, rtol=0., atol=1e-8):
        raise ValueError("fault erased source VDM geometry or changed edge interpolation")
    angle = math.radians(metadata["strike_degrees"])
    expected = weights[:, None] * np.array([math.cos(angle), 0., math.sin(angle)]) * metadata["slip_m"]
    expected[sides != (1 if metadata["moving_side"] == "positive" else -1)] = 0.
    if not np.allclose(displacement, expected, rtol=0., atol=1e-10):
        raise ValueError("fault displacement differs from signed horizontal slip")
    source_index = arrays["vertex_source_index"]
    face_source = arrays["triangle_source_index"]
    original_faces = arrays["source_triangles"]
    seam = arrays["seam_edges"]
    if (source_index.shape != (len(points),) or source_index.dtype != np.int64
            or np.any(source_index < -1) or np.any(source_index >= len(source))
            or face_source.shape != (len(triangles),) or face_source.dtype != np.int64
            or np.any(face_source < 0) or np.any(face_source >= len(original_faces))
            or seam.dtype != np.int64 or seam.ndim != 2 or seam.shape[1] != 2
            or np.any(seam < 0) or np.any(seam >= len(points))):
        raise ValueError("invalid source indices or seam edges")
    _check_mesh(source, original_faces)
    exact = source_index >= 0
    if not np.allclose(before[exact], source[source_index[exact]], rtol=0., atol=1e-8):
        raise ValueError("exact source vertex mapping mismatch")
    support = edges[triangles]
    owners = original_faces[face_source]
    if not np.all(np.any(support[..., None] == owners[:, None, None, :], axis=-1)):
        raise ValueError("output triangle provenance leaves original triangle")
    if np.any(arrays["protected_mask"].ravel()[edges[np.linalg.norm(displacement, axis=1) > 0.]]):
        raise ValueError("protected source vertices displaced")
    _check_mesh(points, triangles)
    influenced = np.any(weights[triangles] > 0., axis=1)
    if np.any(np.ptp(sides[triangles[influenced]], axis=1) != 0):
        raise ValueError("influenced triangle crosses fault seam")
    if result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("fault identity mismatch")
    return True


def save_fault(path, result):
    save_bundle(path, result, validator=validate_fault)


def load_fault(path, *, expected_sha256, expected_identity):
    def headers(values):
        if set(values) != ARRAY_KEYS | {"manifest"}:
            raise ValueError("unexpected v2 fault archive fields")
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_fault, header_validator=headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external fault identity mismatch")
    return result
