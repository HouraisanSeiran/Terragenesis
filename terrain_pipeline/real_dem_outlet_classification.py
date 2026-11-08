"""Diagnostic DEM terminals and DEM-derived river cross-references, not mouths."""

import re

import numpy as np
from rasterio.crs import CRS
from rasterio.warp import transform

from terrain_pipeline.artifacts.contracts import canonical_json, digest, finite_number
from terrain_pipeline.td_source import validate_dem_candidate
from terrain_pipeline.drainage import build_real_dem_network as build_real_dem_network
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
from terrain_pipeline.drainage import segments_clear as segments_clear


ALGORITHM = "real-dem-irregular-outlet-classification-v2"
FORMAT = "real-dem-outlet-classification-report-v1"
VECTOR_ALGORITHM = "hydrovector-evidence-v1"
VECTOR_FIELDS = {"schema_version", "algorithm", "created_utc", "coordinate_order", "crs",
                 "units", "geometry_policy", "candidate_bbox_lon_lat", "halo_bbox_lon_lat",
                 "source_archive_sha256", "policy", "rivers"}
RIVER_FIELDS = {"record_index", "shape_type", "bbox_lon_lat", "attributes", "selection",
                "selection_method", "parts_lon_lat", "part_endpoints_lon_lat", "vertex_count",
                "geometry_clipped", "independent_observation", "ocean_outlet_certified"}
AUDIT_FIELDS = {"schema_version", "algorithm", "created_utc", "candidate_bbox_lon_lat",
                "halo_degrees", "halo_bbox_lon_lat", "sources", "zip_members", "crs",
                "river_fields", "river_scan", "selection_counts", "topology", "basins",
                "level10_archive", "policy", "source_readonly_verified"}
CLASSES = ("unknown_adjacent", "boundary_clip", "internal_sink")


def _sha(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("invalid source SHA256")
    return value


def _bbox(value, *, geometry=False):
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("invalid geographic bbox")
    for item in value:
        finite_number(item, "bbox")
    west, south, east, north = value
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("invalid geographic bbox range")
    if not geometry and (west == east or south == north):
        raise ValueError("empty geographic bbox")
    return value


def _false_flags(value):
    if isinstance(value, dict):
        for name, child in value.items():
            if name in {"ocean_outlet_certified", "natural_outlet_verified", "independent_observation",
                        "independent_centerline", "independent_coastline", "dem_nodata_is_ocean",
                        "dem_validity_sampled", "contemporaneous_measured_Q"} and child is not False:
                raise ValueError("natural/independent evidence flags must be false")
            _false_flags(child)
    elif isinstance(value, list):
        for child in value:
            _false_flags(child)


def _intersects(parts, bbox):
    lower = np.asarray(bbox[:2])
    upper = np.asarray(bbox[2:])
    for part in parts:
        start = np.asarray(part[:-1], float)
        delta = np.asarray(part[1:], float) - start
        moving = delta != 0
        safe_delta = np.where(moving, delta, 1.)
        first = (lower - start) / safe_delta
        last = (upper - start) / safe_delta
        enter = np.where(moving, np.minimum(first, last), -np.inf).max(axis=1)
        leave = np.where(moving, np.maximum(first, last), np.inf).min(axis=1)
        stationary_inside = np.all(moving | ((start >= lower) & (start <= upper)), axis=1)
        if np.any(stationary_inside & (np.maximum(enter, 0) <= np.minimum(leave, 1))):
            return True
    return False


def _indexed(records, label):
    result = {}
    if not isinstance(records, list):
        raise ValueError(f"invalid {label} table")
    for record in records:
        river_id = record.get("HYRIV_ID")
        if type(river_id) is not int or river_id < 1 or river_id in result:
            raise ValueError(f"duplicate or invalid {label} ID")
        result[river_id] = record
    return result


def _validate_crs(crs):
    if (set(crs) != {"datum", "coordinate_order", "units", "prj"}
            or crs["datum"] != "WGS84" or crs["coordinate_order"] != "longitude,latitude"
            or crs["units"] != "degrees" or CRS.from_wkt(crs["prj"]).to_epsg() != 4326):
        raise ValueError("audit CRS/order/units mismatch")


def _overlaps(first, second):
    return first[0] <= second[2] and first[2] >= second[0] and first[1] <= second[3] and first[3] >= second[1]


def _basins_reference(audit, bbox, halo):
    references = []
    ids = set()
    if not isinstance(audit["basins"], list):
        raise ValueError("invalid basins table")
    for basin in audit["basins"]:
        if set(basin) != {"path", "crs", "selected", "fields", "record_count", "deleted_record_count", "null_shape_count"}:
            raise ValueError("invalid basin schema")
        _validate_crs(basin["crs"])
        for polygon in basin["selected"]:
            if set(polygon) != RIVER_FIELDS or type(polygon["shape_type"]) is not int or polygon["shape_type"] not in (5, 15, 25):
                raise ValueError("invalid selected polygon schema")
            attributes = polygon["attributes"]
            basin_id = attributes.get("HYBAS_ID")
            if type(basin_id) is not int or basin_id <= 0 or basin_id in ids:
                raise ValueError("duplicate/invalid HYBAS_ID")
            ids.add(basin_id)
            area = finite_number(attributes.get("SUB_AREA"), "SUB_AREA", positive=True)
            if type(attributes.get("COAST")) is not int or attributes["COAST"] not in (0, 1):
                raise ValueError("invalid COAST flag")
            polygon_bbox = _bbox(polygon["bbox_lon_lat"])
            if (not _overlaps(polygon_bbox, halo)
                    or polygon["selection"] != ("candidate_bbox_only" if _overlaps(polygon_bbox, bbox) else "halo_bbox_only")
                    or polygon["selection_method"] != "conservative_polygon_bbox_overlap"
                    or polygon["parts_lon_lat"] is not None or polygon["part_endpoints_lon_lat"] is not None
                    or type(polygon["vertex_count"]) is not int or polygon["vertex_count"] < 3
                    or type(polygon["record_index"]) is not int or polygon["record_index"] < 0):
                raise ValueError("polygon bbox-only reference semantics mismatch")
            for flag in ("geometry_clipped", "independent_observation", "ocean_outlet_certified"):
                if polygon[flag] is not False:
                    raise ValueError("basin evidence flags must be false")
            references.append({"HYBAS_ID": basin_id, "SUB_AREA": area, "SUB_AREA_units": "km2",
                               "COAST": attributes["COAST"], "source_path": basin["path"],
                               "bbox_lon_lat": list(polygon_bbox), "selection": polygon["selection"],
                               "selection_method": polygon["selection_method"],
                               "independent_observation": False, "natural_outlet_verified": False,
                               "ocean_outlet_certified": False})
    level10 = audit["level10_archive"]
    if (set(level10) != {"status", "usable", "reason", "path"} or level10["usable"] is not False
            or level10["status"] != "BadZipFile" or not isinstance(level10["reason"], str)):
        raise ValueError("level10 archive must remain unusable, not inferred evidence")
    return {"selected": sorted(references, key=lambda item: item["HYBAS_ID"]),
            "level10_archive": dict(level10), "evidence_scope": "bbox_only_not_basin_membership_or_coastline"}


def _validate_vectors(vectors, audit, candidate):
    canonical_json(vectors)
    canonical_json(audit)
    if set(vectors) != VECTOR_FIELDS or set(audit) != AUDIT_FIELDS:
        raise ValueError("invalid vector/audit schema")
    for document in (vectors, audit):
        if type(document["schema_version"]) is not int or document["schema_version"] != 1 or document["algorithm"] != VECTOR_ALGORITHM:
            raise ValueError("unsupported vector/audit version")
        _false_flags(document)
    if (vectors["coordinate_order"] != "longitude,latitude" or vectors["crs"] != "WGS84"
            or vectors["units"] != "degrees"
            or vectors["geometry_policy"] != "full_selected_reaches_not_clipped; no_all_Asia_geometry_written"):
        raise ValueError("vector CRS/order/units/geometry policy mismatch")
    _validate_crs(audit["crs"])
    if vectors["policy"] != audit["policy"] or vectors["created_utc"] != audit["created_utc"]:
        raise ValueError("vector/audit policy or run mismatch")
    policy = vectors["policy"]
    for flag in ("independent_centerline", "independent_coastline", "ocean_outlet_certified",
                 "dem_nodata_is_ocean", "dem_validity_sampled"):
        if policy.get(flag) is not False:
            raise ValueError("policy flags must be false")
    if (policy.get("status") != "diagnostic_candidate_only_not_engineering_acceptance"
            or policy.get("river_provenance") != "HydroSHEDS_SRTM_DEM_derived_15_arcsecond"
            or policy.get("basins_provenance") != "HydroSHEDS_DEM_derived_not_independent_of_HydroRIVERS"
            or policy.get("discharge", {}).get("contemporaneous_measured_Q") is not False):
        raise ValueError("invalid diagnostic evidence policy")
    bbox = _bbox(vectors["candidate_bbox_lon_lat"])
    halo = _bbox(vectors["halo_bbox_lon_lat"])
    halo_degrees = finite_number(audit["halo_degrees"], "halo_degrees")
    expected_halo = [bbox[0] - halo_degrees, bbox[1] - halo_degrees,
                     bbox[2] + halo_degrees, bbox[3] + halo_degrees]
    if (not 0 <= halo_degrees <= 5 or halo != expected_halo
            or bbox != audit["candidate_bbox_lon_lat"] or halo != audit["halo_bbox_lon_lat"]
            or bbox != candidate["manifest"]["identity"]["recipe"]["bbox_epsg4326"]):
        raise ValueError("candidate/vector/audit bbox binding mismatch")
    archive_sha = _sha(vectors["source_archive_sha256"])
    if audit["source_readonly_verified"] is not True or not audit["sources"]:
        raise ValueError("source audit must be read-only verified")
    for source in audit["sources"]:
        if (source.get("unchanged") is not True or _sha(source["sha256_before"]) != _sha(source["sha256_after"])
                or type(source["bytes"]) is not int or source["bytes"] <= 0):
            raise ValueError("invalid audited source")
    if audit["sources"][0]["sha256_before"] != archive_sha:
        raise ValueError("source archive binding mismatch")
    if not audit["zip_members"]:
        raise ValueError("missing archive member evidence")
    for member in audit["zip_members"]:
        if member.get("crc_verified") is not True or member["crc32_expected"] != member["crc32_observed"]:
            raise ValueError("archive member CRC mismatch")
        _sha(member["sha256"])
    rivers = vectors["rivers"]
    if not isinstance(rivers, list) or not rivers:
        raise ValueError("selected rivers must be nonempty")
    by_id = {}
    record_ids = set()
    for river in rivers:
        if set(river) != RIVER_FIELDS:
            raise ValueError("invalid river schema")
        attributes = river["attributes"]
        for name in ("HYRIV_ID", "NEXT_DOWN", "MAIN_RIV"):
            value = attributes.get(name)
            if type(value) is not int or value < (0 if name == "NEXT_DOWN" else 1):
                raise ValueError("invalid river ID/NEXT_DOWN")
        river_id = attributes["HYRIV_ID"]
        if river_id in by_id:
            raise ValueError("duplicate HYRIV_ID")
        by_id[river_id] = river
        if type(river["record_index"]) is not int or river["record_index"] < 0 or river["record_index"] in record_ids:
            raise ValueError("invalid or duplicate record_index")
        record_ids.add(river["record_index"])
        if river["shape_type"] not in (3, 13, 23) or type(river["shape_type"]) is not int:
            raise ValueError("river must be polyline")
        for flag in ("geometry_clipped", "independent_observation", "ocean_outlet_certified"):
            if river[flag] is not False:
                raise ValueError("river evidence flags must be false")
        parts = river["parts_lon_lat"]
        if not isinstance(parts, list) or not parts:
            raise ValueError("missing polyline parts")
        for part in parts:
            if not isinstance(part, list) or len(part) < 2:
                raise ValueError("polyline part requires two points")
            for point in part:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("invalid lon/lat point")
                longitude = finite_number(point[0], "longitude")
                latitude = finite_number(point[1], "latitude")
                if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                    raise ValueError("geometry outside geographic range")
        points = np.concatenate([np.asarray(part) for part in parts])
        river_bbox = _bbox(river["bbox_lon_lat"], geometry=True)
        if (np.any(points < np.asarray(river_bbox[:2]) - 1e-10)
                or np.any(points > np.asarray(river_bbox[2:]) + 1e-10)
                or not np.allclose(np.r_[points.min(axis=0), points.max(axis=0)], river_bbox, rtol=0, atol=1e-10)):
            raise ValueError("river bbox does not bound geometry")
        if (type(river["vertex_count"]) is not int or river["vertex_count"] != len(points)
                or river["part_endpoints_lon_lat"] != [[part[0], part[-1]] for part in parts]
                or river["selection_method"] != "segment_rectangle_intersection"
                or not _intersects(parts, halo)
                or river["selection"] != ("candidate_intersection" if _intersects(parts, bbox) else "halo_only")):
            raise ValueError("river geometry/selection semantics mismatch")
    counts = {"river_total": len(rivers), "candidate": sum(river["selection"] == "candidate_intersection" for river in rivers),
              "halo_only": sum(river["selection"] == "halo_only" for river in rivers)}
    if audit["selection_counts"] != counts:
        raise ValueError("selection counts mismatch")
    topology = audit["topology"]
    terminals = _indexed(topology["terminals"], "terminal")
    missing = _indexed(topology["missing_downstream"], "missing downstream")
    adjacency = _indexed(topology["adjacency"], "adjacency")
    endpoints = _indexed(topology["endpoints"], "endpoint")
    upstream = {str(river_id): [] for river_id in by_id}
    expected_terminal, expected_missing, expected_edges = set(), set(), set()
    scopes = {}
    for river_id, river in by_id.items():
        downstream = river["attributes"]["NEXT_DOWN"]
        expected_endpoint = {"HYRIV_ID": river_id, "part_endpoints_lon_lat": river["part_endpoints_lon_lat"],
                             "first_last_flow_orientation": "not_verified", "ocean_outlet_certified": False,
                             "dem_validity": "not_sampled_by_this_audit",
                             "coastline_evidence": "missing_independent_coastline_or_outlet_coordinates"}
        if endpoints.get(river_id) != expected_endpoint:
            raise ValueError("audit endpoint mismatch")
        if downstream == 0:
            expected_terminal.add(river_id)
            expected = {"HYRIV_ID": river_id, "ENDORHEIC": river["attributes"].get("ENDORHEIC"),
                        "meaning": "dataset_terminal_ocean_or_inland_sink_not_certified", "ocean_outlet_certified": False}
            if terminals.get(river_id) != expected:
                raise ValueError("audit product terminal mismatch")
            scopes[river_id] = "product_terminal_ocean_or_inland_sink_not_certified"
        elif downstream in by_id:
            expected_edges.add(river_id)
            edge = adjacency.get(river_id, {})
            if (edge.get("NEXT_DOWN") != downstream
                    or edge.get("endpoint_pairing") != "minimum_over_all_part_ends_not_flow_orientation"
                    or finite_number(edge.get("minimum_endpoint_gap_m"), "endpoint gap") < 0):
                raise ValueError("audit selected downstream mismatch")
            upstream[str(downstream)].append(river_id)
            scopes[river_id] = "within_selected_vectors"
        else:
            expected_missing.add(river_id)
            edge = missing.get(river_id, {})
            if edge.get("NEXT_DOWN") != downstream or edge.get("status") not in {
                    "outside_spatial_selection", "absent_or_deleted_in_source", "null_geometry_in_source"}:
                raise ValueError("audit missing downstream mismatch")
            scopes[river_id] = edge["status"]
    if (set(terminals) != expected_terminal or set(missing) != expected_missing or set(adjacency) != expected_edges
            or set(endpoints) != set(by_id)
            or {key: sorted(value) for key, value in topology["upstream_selected"].items()} !=
               {key: sorted(value) for key, value in upstream.items()}
            or topology["certified_ocean_outlet_count"] != 0
            or topology["route_extent"] != "candidate_plus_halo_only_not_complete_basin"
            or topology["selected_cycles"] != []):
        raise ValueError("audit topology mismatch")
    completed = set()
    for river_id in by_id:
        path = set()
        current = river_id
        while current in by_id and current not in completed:
            if current in path:
                raise ValueError("selected downstream cycle")
            path.add(current)
            current = by_id[current]["attributes"]["NEXT_DOWN"]
        completed.update(path)
    return by_id, scopes, _basins_reference(audit, bbox, halo)


def _network(height, valid, mesh=None):
    network = build_real_dem_network(height, valid, mesh=mesh)
    receiver = np.asarray(network.receiver)
    order = np.asarray(network.order)
    valid_ids = np.flatnonzero(valid.ravel())
    if (receiver.shape != height.shape or receiver.dtype.kind not in "iu" or order.ndim != 1
            or order.dtype.kind not in "iu" or not np.array_equal(np.sort(order), valid_ids)
            or np.any(receiver[~valid] != -1)):
        raise ValueError("invalid receiver/order")
    targets = receiver.ravel()[valid_ids]
    if np.any((targets < -1) | (targets >= height.size)):
        raise ValueError("receiver outside grid")
    routed = targets >= 0
    sources = valid_ids[routed]
    destinations = targets[routed]
    if (np.any(~valid.ravel()[destinations])
            or np.any(height.ravel()[destinations] >= height.ravel()[sources])):
        raise ValueError("receiver must be valid and strictly downhill")
    mesh = (network.mesh if network.mesh is not None else grid_mesh(height.shape, dx_m=90.)) if mesh is None else mesh
    if not receiver_edges_valid(receiver, mesh) or not segments_clear(sources, destinations, valid).all():
        raise ValueError("receiver must use an unobstructed irregular graph edge")
    positions = np.full(height.size, -1, np.int64)
    positions[order] = np.arange(order.size)
    if np.any(positions[sources] >= positions[destinations]):
        raise ValueError("order is not upstream first")
    accumulation = np.zeros(height.size, np.float64)
    accumulation[valid_ids] = 1
    for source in order:
        target = receiver.ravel()[source]
        if target >= 0:
            accumulation[target] += accumulation[source]
    if (network.accumulation_cells.shape != height.shape
            or not np.array_equal(network.accumulation_cells.ravel(), accumulation)):
        raise ValueError("accumulation mismatch")
    terminals = valid_ids[targets == -1]
    if accumulation[terminals].sum() != len(valid_ids):
        raise ValueError("terminal contribution conservation failed")
    return terminals, accumulation


def _nearest(points, by_id):
    starts, ends, owners = [], [], []
    sorted_ids = sorted(by_id)
    for owner, river_id in enumerate(sorted_ids):
        for part in by_id[river_id]["parts_lon_lat"]:
            geographic = np.asarray(part)
            east, north = transform("EPSG:4326", "EPSG:32651", geographic[:, 0], geographic[:, 1])
            projected = np.column_stack((east, north))
            if not np.isfinite(projected).all():
                raise ValueError("nonfinite projected vector geometry")
            starts.extend(projected[:-1])
            ends.extend(projected[1:])
            owners.extend([owner] * (len(projected) - 1))
    starts = np.asarray(starts)
    delta = np.asarray(ends) - starts
    owners = np.asarray(owners)
    squared_length = np.einsum("ij,ij->i", delta, delta)
    safe_length = np.where(squared_length == 0, 1., squared_length)
    result_ids = np.empty(len(points), np.int64)
    result_distance = np.empty(len(points), float)
    for point_start in range(0, len(points), 256):
        block = points[point_start:point_start + 256]
        best = np.full(len(block), np.inf)
        best_owner = np.full(len(block), len(sorted_ids), np.int64)
        for segment_start in range(0, len(starts), 1024):
            segment_slice = slice(segment_start, segment_start + 1024)
            offset = block[:, None, :] - starts[None, segment_slice, :]
            fraction = np.clip(np.einsum("psd,sd->ps", offset, delta[segment_slice]) /
                               safe_length[segment_slice], 0., 1.)
            residual = offset - fraction[:, :, None] * delta[None, segment_slice, :]
            distance_sq = np.einsum("psd,psd->ps", residual, residual)
            index = distance_sq.argmin(axis=1)
            local_best = distance_sq[np.arange(len(block)), index]
            local_owner = owners[segment_slice][index]
            replace = (local_best < best) | ((local_best == best) & (local_owner < best_owner))
            best[replace] = local_best[replace]
            best_owner[replace] = local_owner[replace]
        result_ids[point_start:point_start + len(block)] = np.asarray(sorted_ids)[best_owner]
        result_distance[point_start:point_start + len(block)] = np.sqrt(best)
    return result_ids, result_distance


def build_outlet_classification(candidate, vectors, audit, *, match_distance_m=180.0):
    """Rebuild strict metric graph and cross-reference every terminal in metres."""
    threshold = finite_number(match_distance_m, "match_distance_m", positive=True)
    validate_dem_candidate(candidate, verify_source=False)
    by_id, scopes, basins_reference = _validate_vectors(vectors, audit, candidate)
    arrays = candidate["arrays"]
    height, valid = arrays["height_m"], arrays["valid_mask"]
    grid = candidate["manifest"]["identity"]["grid"]
    mesh = grid_mesh(height.shape, x0_m=grid["origin_x_m"], z0_m=grid["origin_z_m"],
        dx_m=grid["spacing_x_m"], dz_m=grid["spacing_z_m"])
    terminals, accumulation = _network(height, valid, mesh)
    rows, cols = np.divmod(terminals, height.shape[1])
    points = np.column_stack((mesh.node_x_m[terminals], -mesh.node_z_m[terminals]))
    longitude, latitude = transform("EPSG:32651", "EPSG:4326", points[:, 0], points[:, 1])
    lonlat = np.column_stack((longitude, latitude))
    if not np.isfinite(points).all() or not np.isfinite(lonlat).all():
        raise ValueError("invalid terminal coordinates")
    nearest_ids, distances = _nearest(points, by_id)
    outlets = []
    for index, cell_id in enumerate(terminals):
        row, col = int(rows[index]), int(cols[index])
        boundary = row in (0, height.shape[0] - 1) or col in (0, height.shape[1] - 1)
        adjacent = mesh.indices[mesh.indptr[cell_id]:mesh.indptr[cell_id + 1]]
        unknown = bool(np.any(~valid.ravel()[adjacent]))
        classification = "internal_sink"
        if boundary:
            classification = "boundary_clip"
        if unknown:
            classification = "unknown_adjacent"
        river_id = int(nearest_ids[index])
        downstream = by_id[river_id]["attributes"]["NEXT_DOWN"]
        outlets.append({"cell_id": int(cell_id), "row_col": [row, col],
                        "projected_xy_m": points[index].tolist(), "lon_lat": lonlat[index].tolist(),
                        "height_m": float(height[row, col]), "contributing_cells": int(accumulation[cell_id]),
                        "classification": classification, "is_boundary_clip": boundary,
                        "is_unknown_adjacent": unknown, "natural_outlet_verified": False,
                        "ocean_outlet_certified": False,
                        "nearest_hydrovector": {"HYRIV_ID": river_id, "NEXT_DOWN": downstream,
                                                "distance_m": float(distances[index]),
                                                "matched": bool(distances[index] <= threshold),
                                                "product_terminal": downstream == 0,
                                                "downstream_scope": scopes[river_id]}})
    parameters = {"match_distance_m": threshold, "topology": "irregular_Delaunay", "projected_crs": "EPSG:32651",
                  "distance": "nearest_projected_polyline_segment", "tie_break": "minimum_HYRIV_ID",
                  "routing": "strict_downhill_maximum_metric_slope_no_flat_resolution"}
    identity = {"algorithm": ALGORITHM, "parameters": parameters, "parameters_sha256": digest(parameters),
                "candidate_content_sha256": candidate["manifest"]["content_sha256"],
                "candidate_array_hashes": dict(candidate["manifest"]["array_hashes"]),
                "vectors_sha256": digest(vectors), "audit_sha256": digest(audit),
                "source_archive_sha256": vectors["source_archive_sha256"],
                "candidate_bbox_lon_lat": list(vectors["candidate_bbox_lon_lat"])}
    summary = {"valid_cells": int(valid.sum()), "unknown_cells": int((~valid).sum()),
               "terminal_cells": len(outlets), "contributing_cells": sum(item["contributing_cells"] for item in outlets),
               "classification_counts": {name: sum(item["classification"] == name for item in outlets) for name in CLASSES},
               "boundary_clip_risks": sum(item["is_boundary_clip"] for item in outlets),
               "unknown_adjacent_risks": sum(item["is_unknown_adjacent"] for item in outlets),
               "matched_hydrovector_terminals": sum(item["nearest_hydrovector"]["matched"] for item in outlets),
               "natural_outlet_verified": False, "ocean_outlet_certified": False}
    summary["category_counts"] = dict(summary["classification_counts"])
    summary["matched_terminal_count"] = summary["matched_hydrovector_terminals"]
    summary["contributing_cells_sum"] = summary["contributing_cells"]
    summary["unknown_and_boundary_count"] = sum(item["is_unknown_adjacent"] and item["is_boundary_clip"] for item in outlets)
    report = {"format": FORMAT, "status": "diagnostic_candidate_not_publishable", "publishable": False,
              "natural_outlet_verified": False, "ocean_outlet_certified": False,
              "identity": identity, "identity_sha256": digest(identity), "summary": summary,
              "outlets": outlets, "basins_reference": basins_reference,
              "evidence": {"hydrorivers": "DEM_derived_cross_reference_not_independent",
                                              "hydrobasins": "bbox_reference_only_COAST_not_certification",
                                              "coastline": "no_independent_input",
                                              "internal_sink": "unresolved_raw_flat_or_sink_not_natural_depression"}}
    report["content_sha256"] = digest(report)
    return report


def validate_outlet_classification(report, candidate, vectors, audit):
    """Replay semantics, not just hashes; source-path authentication is CLI-owned."""
    canonical_json(report)
    try:
        threshold = report["identity"]["parameters"]["match_distance_m"]
        expected = build_outlet_classification(candidate, vectors, audit, match_distance_m=threshold)
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError("invalid outlet classification schema") from error
    if canonical_json(report) != canonical_json(expected):
        raise ValueError("outlet classification source/semantic/hash mismatch")
    return {"verified": True, "algorithm": ALGORITHM, "content_sha256": report["content_sha256"],
            "summary": dict(expected["summary"]), "natural_outlet_verified": False,
            "ocean_outlet_certified": False, "source_paths_verified": False}


def classification_geojson(report):
    """Render diagnostic terminals as WGS84 points without certifying evidence."""
    canonical_json(report)
    _false_flags(report)
    if report.get("format") != FORMAT or report.get("content_sha256") != digest({
            name: value for name, value in report.items() if name != "content_sha256"}):
        raise ValueError("invalid outlet report hash/format")
    features = []
    for outlet in report["outlets"]:
        if outlet["classification"] not in CLASSES:
            raise ValueError("invalid outlet classification")
        longitude, latitude = outlet["lon_lat"]
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("invalid outlet lon/lat")
        properties = {name: value for name, value in outlet.items() if name != "lon_lat"}
        features.append({"type": "Feature", "id": outlet["cell_id"],
                         "geometry": {"type": "Point", "coordinates": list(outlet["lon_lat"])},
                         "properties": properties})
    return {"type": "FeatureCollection", "features": features}
