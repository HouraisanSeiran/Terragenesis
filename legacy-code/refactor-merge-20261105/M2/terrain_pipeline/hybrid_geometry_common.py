"""Shared frame, saved-solid, resource and record duties; no face generator."""
import math
import numpy as np
import psutil
from shapely.geometry import LineString, Polygon
from terrain_pipeline.hybrid_river_graph import identity


MAX_BYTES = 64 * 1024**2


MAX_RSS = 1024**3


TOLERANCE_M = 1e-8


AREA_TOLERANCE_M2 = 1e-8


MAX_TRIANGLES = 200000


def seal(record):
    record.pop("identity_sha256", None)
    record["identity_sha256"] = identity(record)
    return record


def guard():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, "peak_wset", 0))
    if peak > MAX_RSS:
        raise MemoryError("whole_face_package_1GiB_budget_exceeded")
    return peak


def plane_frame(origin_world, flow_xz, common_origin):
    origin_world, common_origin = np.asarray(origin_world, float), np.asarray(common_origin, float)
    flow = np.asarray(flow_xz, float)
    if (origin_world.shape != (3,) or common_origin.shape != (3,) or flow.shape != (2,)
            or not all(np.isfinite(value).all() for value in (origin_world, common_origin, flow))
            or np.linalg.norm(flow) <= TOLERANCE_M):
        raise ValueError("unknown_or_invalid_face_plane")
    flow /= np.linalg.norm(flow)
    normal = np.array([flow[0], 0., flow[1]])
    transverse = np.array([flow[1], 0., -flow[0]])
    return {"origin_world_xyz_m": origin_world.tolist(), "origin_local_xyz_m": (origin_world - common_origin).tolist(),
        "common_local_origin_xyz_m": common_origin.tolist(), "normal_local_xyz": normal.tolist(),
        "transverse_unit_xyz": transverse.tolist(), "transverse_unit_xz": transverse[[0, 2]].tolist(),
        "vertical_unit_xyz": [0., 1., 0.], "coordinate_convention": "u_metres_Ylocal_metres_not_floor_relative",
        "positive_normal": "from_cell_to_cell_actual_horizontal_route"}


def project(vertices_local, frame):
    points = np.asarray(vertices_local, float)
    relative = points - np.array(frame["origin_local_xyz_m"])
    return np.column_stack((relative @ np.array(frame["transverse_unit_xyz"]), points[:, 1]))


def unproject(points_uv, frame):
    points = np.asarray(points_uv, float)
    origin = np.array(frame["origin_local_xyz_m"])
    result = origin + points[:, :1] * np.array(frame["transverse_unit_xyz"])
    result[:, 1] = points[:, 1]
    return result


def solid_from_mesh(record, common_origin):
    import manifold3d as manifold
    points = np.array(record["vertices_local_xyz_m"], dtype=np.float64, order="C", copy=True)
    triangles = np.array(record["triangles"], dtype=np.uint64, order="C", copy=True)
    if (points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all()
            or triangles.ndim != 2 or triangles.shape[1] != 3 or not 0 < len(triangles) <= MAX_TRIANGLES
            or triangles.max() >= len(points)):
        raise ValueError("invalid_or_unbounded_saved_solid_mesh")
    origin = np.asarray(record["local_origin_xyz_m"], float)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("invalid_saved_solid_origin")
    points += origin - common_origin
    solid = manifold.Manifold(manifold.Mesh64(points, triangles))
    if solid.status() != manifold.Error.NoError or solid.is_empty() or solid.volume() <= 0:
        raise ValueError("saved_solid_not_positive_closed_manifold")
    return solid, points, triangles


def support_indices(line, slice_record):
    result = {item["triangle_index"] for item in slice_record["triangle_segments"]
        if LineString(item["points_uv_m"]).distance(line) <= TOLERANCE_M
        and LineString(item["points_uv_m"]).intersection(line.buffer(TOLERANCE_M)).length > TOLERANCE_M}
    result.update(item["triangle_index"] for item in slice_record["coplanar_triangle_supports"]
        if Polygon(item["polygon_uv_m"]).distance(line) <= TOLERANCE_M)
    return sorted(result)


def canonical_floor(port, frame):
    floor = []
    if port["status"] != "candidate" or port["rejection_reasons"]:
        raise ValueError("unknown_refused_canonical_port")
    for segment in port["profile"]["profile_segments"]:
        for piece in segment["native_pieces"]:
            coefficients = piece["source"]["source_coefficients_m_t012"]
            cut = piece["depth_coefficients_m_t01"]
            if coefficients[2] != 0. or min(cut[0], cut[0] + cut[1]) < 0 or max(cut[0], cut[0] + cut[1]) > 4:
                raise ValueError("unknown_unsupported_canonical_native_function")
            for fraction, point in ((0., piece["start_xz_m"]), (1., piece["end_xz_m"])):
                world = np.array([point[0], coefficients[0] + fraction * coefficients[1] - cut[0] - fraction * cut[1], point[1]])
                local = world - np.array(frame["common_local_origin_xyz_m"])
                if abs(float((local - frame["origin_local_xyz_m"]) @ frame["normal_local_xyz"])) > TOLERANCE_M:
                    raise ValueError("canonical_floor_not_in_shared_plane")
                uv = project([local], frame)[0].tolist()
                if not floor or math.dist(uv, floor[-1]) > TOLERANCE_M:
                    floor.append(uv)
    floor.sort(key=lambda point: point[0])
    if len(floor) < 4:
        raise ValueError("incomplete_canonical_four_point_profile")
    return floor
