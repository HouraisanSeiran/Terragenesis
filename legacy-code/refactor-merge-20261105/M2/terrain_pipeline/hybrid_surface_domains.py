"""Lossless saved polygon/hole/line/point domains for portal evidence."""


def _domain(shape):
    polygons, lines, points = [], [], []
    pending = [shape]
    while pending:
        item = pending.pop()
        if item.is_empty:
            continue
        if item.geom_type == "Polygon":
            polygons.append(item)
        elif item.geom_type in ("LineString", "LinearRing"):
            lines.append(list(map(list, item.coords)))
        elif item.geom_type == "Point":
            points.append(list(item.coords[0]))
        elif item.geom_type in ("MultiPolygon", "MultiLineString", "MultiPoint", "GeometryCollection"):
            pending.extend(reversed(list(item.geoms)))
        else:
            raise ValueError("unsupported_port_domain_geometry:" + item.geom_type)
    return {"polygons_uv_m": [list(map(list, polygon.exterior.coords))[:-1] for polygon in polygons],
        "holes_uv_m": [[list(map(list, hole.coords))[:-1] for hole in polygon.interiors] for polygon in polygons],
        "contact_lines_uv_m": lines, "contact_points_uv_m": points,
        "area_m2": float(shape.area)}
