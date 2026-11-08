"""Original saved-mesh inside/hole witnesses shared by rational slicing."""
import numpy as np
from shapely.geometry import Polygon


def _polygons(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape]
    if shape.geom_type == "MultiPolygon":
        return list(shape.geoms)
    raise ValueError("unknown_nonpolygon_exact_slice_domain")


def _occupancy(solid, shape, cap_shape, frame, points, coplanar):
    witnesses = []
    extent = float(np.linalg.norm(np.ptp(points, axis=0))) * 4. + 1.
    queries = [(polygon.representative_point(), 1, "retained_polygon") for polygon in _polygons(shape)]
    for polygon in _polygons(shape):
        for hole in polygon.interiors:
            void = Polygon(hole).difference(shape)
            if not void.is_empty:
                queries.append((void.representative_point(), 0, "excluded_hole"))
    for query, expected, region in queries:
        uv = [query.x, query.y]
        local = np.asarray(frame["origin_local_xyz_m"]) + query.x * np.asarray(frame["transverse_unit_xyz"])
        local[1] = query.y
        if cap_shape.covers(query):
            if not expected:
                raise ValueError("coplanar_facet_in_declared_slice_hole")
            witnesses.append({"point_uv_m": uv, "point_local_xyz_m": local.tolist(),
                "classification": "original_oriented_coplanar_boundary_facet", "region": region,
                "coplanar_triangle_indices": [item["triangle_index"] for item in coplanar
                    if Polygon(item["polygon_uv_m"]).covers(query)]})
            continue
        parities = []
        for direction in ([1., .3713906763541037, .5291502622129182], [.239, 1., .617]):
            vector = np.asarray(direction)
            vector /= np.linalg.norm(vector)
            hits = solid.ray_cast(local.tolist(), (local + extent * vector).tolist())
            distances = sorted(set(float(hit.distance) for hit in hits if hit.distance > 0.))
            parities.append(len(distances) % 2)
        if parities != [expected, expected]:
            raise ValueError("exact_slice_3D_occupancy_not_certified")
        witnesses.append({"point_uv_m": uv, "point_local_xyz_m": local.tolist(),
            "classification": "original_Mesh64_interior_two_ray_parities" if expected else "original_Mesh64_void_two_ray_parities",
            "region": region, "ray_parities": parities})
    return witnesses
