"""Read-only, standard-library vector evidence audit, not outlet certification."""

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import tempfile
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

ALGORITHM = "hydrovector-evidence-v1"
DEFAULT_BBOX = (121.25, 29.15, 121.65, 29.65)
MAX_RECORD_BYTES = 64 * 1024 * 1024


class EvidenceError(ValueError):
    pass


def read_exact(stream, size, label):
    payload = stream.read(size)
    if len(payload) != size:
        raise EvidenceError(f"truncated {label}: expected {size}, got {len(payload)}")
    return payload


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_bbox(bbox):
    if (len(bbox) != 4 or not all(math.isfinite(value) for value in bbox)
            or not -180 <= bbox[0] <= bbox[2] <= 180
            or not -90 <= bbox[1] <= bbox[3] <= 90):
        raise EvidenceError(f"invalid WGS84 bbox: {bbox}")
    return tuple(bbox)


def contains_bbox(outer, inner):
    return (outer[0] - 1e-9 <= inner[0] and outer[1] - 1e-9 <= inner[1]
            and outer[2] + 1e-9 >= inner[2] and outer[3] + 1e-9 >= inner[3])


def overlaps(first, second):
    return (first[0] <= second[2] and second[0] <= first[2]
            and first[1] <= second[3] and second[1] <= first[3])


def validate_wgs84(payload):
    try:
        text = payload.decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise EvidenceError("non-ASCII CRS") from error
    checks = (
        re.match(r'^GEOGCS\s*\[\s*"(?:GCS_WGS_1984|WGS ?84)"', text, re.I),
        re.search(r'DATUM\s*\[\s*"(?:D_WGS_1984|WGS_1984)"', text, re.I),
        re.search(r'SPHEROID\s*\[\s*"(?:WGS_1984|WGS 84)"\s*,\s*6378137(?:\.0*)?\s*,\s*298\.257223563\s*\]', text, re.I),
        re.search(r'PRIMEM\s*\[\s*"Greenwich"\s*,\s*0(?:\.0*)?\s*\]', text, re.I),
        re.search(r'UNIT\s*\[\s*"Degree"\s*,\s*0\.0174532925199433\s*\]', text, re.I),
    )
    if not all(checks) or re.search(r'PROJCS|PROJECTION|AXIS|TOWGS84', text, re.I):
        raise EvidenceError("unsupported CRS; require geographic WGS84 longitude/latitude degrees")
    return {"datum": "WGS84", "coordinate_order": "longitude,latitude", "units": "degrees", "prj": text}


def parse_dbf_value(raw, field):
    name, kind, width, decimals = field
    try:
        text = raw.decode("latin1" if kind == "C" else "ascii").strip()
    except UnicodeDecodeError as error:
        raise EvidenceError(f"non-ASCII DBF {name}") from error
    if not text:
        return None
    if kind in "NF":
        integer = kind == "N" and decimals == 0
        pattern = r"[+-]?\d+" if integer else r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        if not re.fullmatch(pattern, text):
            raise EvidenceError(f"invalid DBF numeric {name}: {text!r}")
        value = int(text) if integer else float(text)
        if not math.isfinite(value):
            raise EvidenceError(f"nonfinite DBF numeric {name}")
        return value
    if kind == "L":
        if text.upper() not in ("T", "Y", "F", "N", "?"):
            raise EvidenceError(f"invalid DBF logical {name}")
        return None if text == "?" else text.upper() in ("T", "Y")
    if kind == "D":
        try:
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        except ValueError as error:
            raise EvidenceError(f"invalid DBF date {name}") from error
    return text


class DbfReader:
    def __init__(self, stream, byte_size):
        self.stream = stream
        header = read_exact(stream, 32, "DBF header")
        if header[0] != 3:
            raise EvidenceError("unsupported DBF version")
        self.count, header_size, self.record_size = struct.unpack_from("<IHH", header, 4)
        if header_size < 33 or (header_size - 33) % 32 or self.count > 20_000_000:
            raise EvidenceError("invalid DBF header/count")
        expected_size = header_size + self.count * self.record_size
        if byte_size not in (expected_size, expected_size + 1):
            raise EvidenceError("DBF size/count mismatch or truncated DBF")
        self.has_eof = byte_size == expected_size + 1
        descriptors = read_exact(stream, header_size - 32, "DBF descriptors")
        if descriptors[-1:] != b"\r":
            raise EvidenceError("invalid DBF descriptor terminator")
        self.fields, names = [], set()
        for offset in range(0, len(descriptors) - 1, 32):
            descriptor = descriptors[offset:offset + 32]
            try:
                name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
            except UnicodeDecodeError as error:
                raise EvidenceError("invalid DBF field name") from error
            kind, width, decimals = chr(descriptor[11]), descriptor[16], descriptor[17]
            if (not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,10}", name)
                    or name in names or kind not in "NCFLD" or width == 0 or decimals > width
                    or (kind == "D" and width != 8) or (kind == "L" and width != 1)):
                raise EvidenceError(f"unsafe DBF field descriptor: {name!r}")
            names.add(name)
            self.fields.append((name, kind, width, decimals))
        if 1 + sum(field[2] for field in self.fields) != self.record_size:
            raise EvidenceError("DBF record width/fields mismatch")
        self.index = 0

    def read_record(self):
        if self.index >= self.count:
            raise EvidenceError("DBF record alignment overflow")
        payload = read_exact(self.stream, self.record_size, "DBF record")
        self.index += 1
        if payload[:1] not in (b" ", b"*"):
            raise EvidenceError("invalid DBF deletion marker")
        if payload[:1] == b"*":
            return self.index, True, None
        attributes, offset = {}, 1
        for field in self.fields:
            end = offset + field[2]
            attributes[field[0]] = parse_dbf_value(payload[offset:end], field)
            offset = end
        return self.index, False, attributes

    def finish(self):
        if self.index != self.count:
            raise EvidenceError("SHP/DBF record count alignment mismatch")
        if self.has_eof and read_exact(self.stream, 1, "DBF EOF") != b"\x1a":
            raise EvidenceError("invalid DBF EOF marker")
        if self.stream.read(1):
            raise EvidenceError("DBF trailing bytes")


def read_shape_header(stream, byte_size, label, allowed_types):
    header = read_exact(stream, 100, f"{label} header")
    declared_size = struct.unpack_from(">i", header, 24)[0] * 2
    version, kind = struct.unpack_from("<ii", header, 28)
    if (struct.unpack_from(">i", header)[0] != 9994 or version != 1000
            or declared_size != byte_size or declared_size < 100
            or kind not in allowed_types or any(header[4:24])):
        raise EvidenceError(f"invalid {label} header/size/type")
    bbox = validate_bbox(struct.unpack_from("<4d", header, 36))
    if not all(math.isfinite(value) for value in struct.unpack_from("<4d", header, 68)):
        raise EvidenceError(f"nonfinite {label} Z/M range")
    return kind, bbox


def parse_shape(payload, header_kind, header_bbox):
    if len(payload) < 4:
        raise EvidenceError("truncated SHP shape type")
    kind = struct.unpack_from("<i", payload)[0]
    if kind == 0:
        if len(payload) != 4:
            raise EvidenceError("invalid null shape length")
        return {"shape_type": 0, "bbox": None, "parts": [], "points": []}
    if kind != header_kind or len(payload) < 44:
        raise EvidenceError("SHP type mismatch or truncated geometry")
    bbox = validate_bbox(struct.unpack_from("<4d", payload, 4))
    if not contains_bbox(header_bbox, bbox):
        raise EvidenceError("SHP bbox outside header bbox")
    part_count, point_count = struct.unpack_from("<ii", payload, 36)
    point_offset = 44 + part_count * 4
    xy_end = point_offset + point_count * 16
    if part_count <= 0 or point_count < part_count * 2 or xy_end > len(payload):
        raise EvidenceError("invalid SHP parts/points or truncated coordinates")
    parts = list(struct.unpack_from(f"<{part_count}i", payload, 44))
    if parts[0] != 0 or any(start >= end for start, end in zip(parts, parts[1:] + [point_count])):
        raise EvidenceError("invalid SHP part index alignment")
    points = list(struct.iter_unpack("<dd", payload[point_offset:xy_end]))
    if any(not math.isfinite(lon) or not math.isfinite(lat) or not -180 <= lon <= 180 or not -90 <= lat <= 90 for lon, lat in points):
        raise EvidenceError("invalid SHP coordinate range")
    actual_bbox = (min(point[0] for point in points), min(point[1] for point in points),
                   max(point[0] for point in points), max(point[1] for point in points))
    if any(abs(actual - stored) > 1e-9 for actual, stored in zip(actual_bbox, bbox)):
        raise EvidenceError("SHP bbox does not match coordinates")
    minimum = 4 if kind in (5, 15, 25) else 2
    if any(end - start < minimum for start, end in zip(parts, parts[1:] + [point_count])):
        raise EvidenceError("undersized SHP part")
    trailing, block_size = payload[xy_end:], 16 + point_count * 8
    allowed = {block_size} if kind in (13, 15, 23, 25) else {0}
    if kind in (13, 15):
        allowed.add(block_size * 2)
    if len(trailing) not in allowed:
        raise EvidenceError("invalid or truncated SHP Z/M payload")
    for offset in range(0, len(trailing), block_size):
        values = struct.unpack_from(f"<{point_count + 2}d", trailing, offset)
        if (not all(math.isfinite(value) for value in values) or values[0] > values[1]
                or any(value < values[0] - 1e-9 or value > values[1] + 1e-9 for value in values[2:])):
            raise EvidenceError("invalid SHP Z/M range")
    return {"shape_type": kind, "bbox": bbox, "parts": parts, "points": points}


def iter_shapes(stream, byte_size, allowed_types=(3, 13, 23), shx_stream=None, shx_size=None):
    kind, header_bbox = read_shape_header(stream, byte_size, "SHP", allowed_types)
    if shx_stream is not None:
        shx_kind, shx_bbox = read_shape_header(shx_stream, shx_size, "SHX", allowed_types)
        if kind != shx_kind or header_bbox != shx_bbox or (shx_size - 100) % 8:
            raise EvidenceError("SHP/SHX header alignment mismatch")
    offset, index = 100, 0
    while offset < byte_size:
        record_number, words = struct.unpack(">ii", read_exact(stream, 8, "SHP record header"))
        content_size = words * 2
        index += 1
        if record_number != index:
            raise EvidenceError("SHP record index alignment mismatch")
        if content_size < 4 or content_size > MAX_RECORD_BYTES or offset + 8 + content_size > byte_size:
            raise EvidenceError("invalid SHP record length/truncation")
        if shx_stream is not None:
            indexed_offset, indexed_words = struct.unpack(">ii", read_exact(shx_stream, 8, "SHX entry"))
            if indexed_offset * 2 != offset or indexed_words != words:
                raise EvidenceError("SHP/SHX record alignment mismatch")
        shape = parse_shape(read_exact(stream, content_size, "SHP record"), kind, header_bbox)
        shape["record_index"] = index
        offset += 8 + content_size
        yield shape
    if offset != byte_size or stream.read(1):
        raise EvidenceError("SHP trailing bytes")
    if shx_stream is not None and (shx_size != 100 + index * 8 or shx_stream.read(1)):
        raise EvidenceError("SHP/SHX count alignment mismatch")


def segment_intersects_bbox(first, last, bbox):
    lower, upper = 0.0, 1.0
    delta_lon, delta_lat = last[0] - first[0], last[1] - first[1]
    for direction, distance in ((-delta_lon, first[0] - bbox[0]),
                                (delta_lon, bbox[2] - first[0]),
                                (-delta_lat, first[1] - bbox[1]),
                                (delta_lat, bbox[3] - first[1])):
        if direction == 0:
            if distance < 0:
                return False
        elif direction < 0:
            lower = max(lower, distance / direction)
        else:
            upper = min(upper, distance / direction)
        if lower > upper:
            return False
    return True


def shape_intersects_bbox(shape, bbox):
    if shape["bbox"] is None or not overlaps(shape["bbox"], bbox):
        return False
    if shape["shape_type"] in (5, 15, 25):
        return True
    for start, end in zip(shape["parts"], shape["parts"][1:] + [len(shape["points"])]):
        if any(segment_intersects_bbox(first, last, bbox) for first, last in
               zip(shape["points"][start:end - 1], shape["points"][start + 1:end])):
            return True
    return False


def validate_river_attributes(attributes):
    for name in ("HYRIV_ID", "NEXT_DOWN", "MAIN_RIV"):
        value = attributes.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value < (0 if name == "NEXT_DOWN" else 1):
            raise EvidenceError(f"invalid river ID/range: {name}")
    for name in ("UPLAND_SKM", "LENGTH_KM", "DIS_AV_CMS", "CATCH_SKM", "DIST_UP_KM", "DIST_DN_KM"):
        if name in attributes:
            value = attributes[name]
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(value) or value < 0):
                raise EvidenceError(f"invalid river attribute type/range: {name}")
    if "ORD_STRA" in attributes and (not isinstance(attributes["ORD_STRA"], int) or not 1 <= attributes["ORD_STRA"] <= 127):
        raise EvidenceError("invalid ORD_STRA range")
    if "ENDORHEIC" in attributes and (not isinstance(attributes["ENDORHEIC"], int)
                                       or isinstance(attributes["ENDORHEIC"], bool)
                                       or attributes["ENDORHEIC"] not in (0, 1)):
        raise EvidenceError("invalid ENDORHEIC range")


def select_records(shp_stream, shp_size, dbf_stream, dbf_size, bbox, halo_bbox,
                   river=True, shx_stream=None, shx_size=None):
    validate_bbox(bbox)
    validate_bbox(halo_bbox)
    if not contains_bbox(halo_bbox, bbox):
        raise EvidenceError("halo bbox must contain candidate bbox")
    table = DbfReader(dbf_stream, dbf_size)
    if river and not {"HYRIV_ID", "NEXT_DOWN", "MAIN_RIV"} <= {field[0] for field in table.fields}:
        raise EvidenceError("missing mandatory river DBF fields")
    integer_fields = {"HYRIV_ID", "NEXT_DOWN", "MAIN_RIV", "ORD_STRA", "ENDORHEIC", "HYBAS_L12"}
    numeric_fields = integer_fields | {"UPLAND_SKM", "LENGTH_KM", "DIS_AV_CMS", "CATCH_SKM", "DIST_UP_KM", "DIST_DN_KM"}
    if river:
        for name, kind, width, decimals in table.fields:
            if name in numeric_fields and (kind not in "NF" or (name in integer_fields and (kind != "N" or decimals != 0))):
                raise EvidenceError(f"invalid river DBF field type: {name}")
    selected, active_ids, null_ids = [], set(), set()
    deleted_count, null_count, count = 0, 0, 0
    types = (3, 13, 23) if river else (5, 15, 25)
    for shape in iter_shapes(shp_stream, shp_size, types, shx_stream, shx_size):
        count += 1
        row_index, deleted, attributes = table.read_record()
        if row_index != shape["record_index"]:
            raise EvidenceError("SHP/DBF record index alignment mismatch")
        if deleted:
            deleted_count += 1
            continue
        if river:
            validate_river_attributes(attributes)
            river_id = attributes["HYRIV_ID"]
            if river_id in active_ids:
                raise EvidenceError(f"duplicate HYRIV_ID: {river_id}")
            active_ids.add(river_id)
            if shape["shape_type"] == 0:
                null_ids.add(river_id)
        if shape["shape_type"] == 0:
            null_count += 1
            continue
        if not shape_intersects_bbox(shape, halo_bbox):
            continue
        parts = [shape["points"][start:end] for start, end in
                 zip(shape["parts"], shape["parts"][1:] + [len(shape["points"])])]
        selected.append({"record_index": row_index, "shape_type": shape["shape_type"],
                         "bbox_lon_lat": shape["bbox"], "attributes": attributes,
                         "selection": ("candidate_intersection" if river else "candidate_bbox_only") if shape_intersects_bbox(shape, bbox) else ("halo_only" if river else "halo_bbox_only"),
                         "selection_method": "segment_rectangle_intersection" if river else "conservative_polygon_bbox_overlap",
                         "parts_lon_lat": parts if river else None,
                         "part_endpoints_lon_lat": [[part[0], part[-1]] for part in parts] if river else None,
                         "vertex_count": len(shape["points"]), "geometry_clipped": False,
                         "independent_observation": False, "ocean_outlet_certified": False})
    table.finish()
    return {"selected": selected, "fields": [{"name": name, "type": kind, "width": width, "decimals": decimals}
                                             for name, kind, width, decimals in table.fields],
            "record_count": count, "deleted_record_count": deleted_count,
            "null_shape_count": null_count, "active_ids": active_ids, "null_ids": null_ids}


def endpoint_distance_m(first, last):
    lon_delta, lat_delta = math.radians(last[0] - first[0]), math.radians(last[1] - first[1])
    haversine = (math.sin(lat_delta / 2) ** 2 + math.cos(math.radians(first[1]))
                 * math.cos(math.radians(last[1])) * math.sin(lon_delta / 2) ** 2)
    return 2 * 6371008.8 * math.asin(min(1.0, math.sqrt(haversine)))


def topology_diagnostics(selected, active_ids, null_ids=()):
    by_id = {record["attributes"]["HYRIV_ID"]: record for record in selected}
    if len(by_id) != len(selected):
        raise EvidenceError("duplicate selected HYRIV_ID")
    adjacency, endpoints, missing, terminals = [], [], [], []
    upstream = {river_id: [] for river_id in by_id}
    for river_id, record in by_id.items():
        part_endpoints = record.get("part_endpoints_lon_lat")
        if (not isinstance(part_endpoints, (list, tuple)) or not part_endpoints
                or any(not isinstance(part, (list, tuple)) or len(part) != 2
                       or any(not isinstance(point, (list, tuple)) or len(point) != 2
                              or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in point)
                              for point in part) for part in part_endpoints)):
            raise EvidenceError(f"missing or invalid selected endpoints: {river_id}; cannot certify ocean")
        downstream = record["attributes"]["NEXT_DOWN"]
        endpoints.append({"HYRIV_ID": river_id, "part_endpoints_lon_lat": record["part_endpoints_lon_lat"],
                          "first_last_flow_orientation": "not_verified", "ocean_outlet_certified": False,
                          "dem_validity": "not_sampled_by_this_audit",
                          "coastline_evidence": "missing_independent_coastline_or_outlet_coordinates"})
        if downstream == 0:
            terminals.append({"HYRIV_ID": river_id, "ENDORHEIC": record["attributes"].get("ENDORHEIC"),
                              "meaning": "dataset_terminal_ocean_or_inland_sink_not_certified",
                              "ocean_outlet_certified": False})
        elif downstream not in by_id:
            status = "outside_spatial_selection" if downstream in active_ids else "absent_or_deleted_in_source"
            if downstream in null_ids:
                status = "null_geometry_in_source"
            missing.append({"HYRIV_ID": river_id, "NEXT_DOWN": downstream, "status": status,
                            "ocean_outlet_certified": False})
        else:
            upstream[downstream].append(river_id)
            first_ends = [point for part in record["part_endpoints_lon_lat"] for point in part]
            last_ends = [point for part in by_id[downstream]["part_endpoints_lon_lat"] for point in part]
            gap = min(endpoint_distance_m(first, last) for first in first_ends for last in last_ends)
            adjacency.append({"HYRIV_ID": river_id, "NEXT_DOWN": downstream,
                              "minimum_endpoint_gap_m": gap,
                              "endpoint_pairing": "minimum_over_all_part_ends_not_flow_orientation"})
    cycles, completed = [], set()
    for river_id in by_id:
        path, positions, current = [], {}, river_id
        while current in by_id and current not in completed:
            if current in positions:
                cycles.append(path[positions[current]:])
                break
            positions[current] = len(path)
            path.append(current)
            current = by_id[current]["attributes"]["NEXT_DOWN"]
        completed.update(path)
    return {"adjacency": adjacency, "upstream_selected": upstream, "endpoints": endpoints,
            "missing_downstream": missing, "terminals": terminals, "selected_cycles": cycles,
            "endpoint_gaps_over_1m": [edge for edge in adjacency if edge["minimum_endpoint_gap_m"] > 1],
            "certified_ocean_outlet_count": 0,
            "route_extent": "candidate_plus_halo_only_not_complete_basin",
            "nodata_policy": "unknown_not_ocean; DEM-invalid endpoints require independent coast/outlet evidence"}


def verify_zip_members(archive):
    entries = archive.infolist()
    if len({entry.filename for entry in entries}) != len(entries):
        raise EvidenceError("duplicate ZIP member names")
    manifest = []
    for entry in entries:
        if entry.flag_bits & 1:
            raise EvidenceError("encrypted ZIP member")
        digest, crc, byte_count = hashlib.sha256(), 0, 0
        with archive.open(entry, "r") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                crc = zlib.crc32(block, crc)
                byte_count += len(block)
        if byte_count != entry.file_size or crc != entry.CRC:
            raise EvidenceError(f"ZIP size/CRC mismatch: {entry.filename}")
        manifest.append({"name": entry.filename, "bytes": byte_count, "compressed_bytes": entry.compress_size,
                         "crc32_expected": f"{entry.CRC:08x}", "crc32_observed": f"{crc:08x}",
                         "crc_verified": True, "sha256": digest.hexdigest()})
    return manifest


def evidence_policy():
    return {"status": "diagnostic_candidate_only_not_engineering_acceptance",
            "river_provenance": "HydroSHEDS_SRTM_DEM_derived_15_arcsecond",
            "basins_provenance": "HydroSHEDS_DEM_derived_not_independent_of_HydroRIVERS",
            "discharge": {"field": "DIS_AV_CMS", "units": "m3/s", "kind": "modelled_long_term_mean",
                          "period": "1971-2000", "model": "WaterGAP_2.2_as_of_2014_downscaled",
                          "contemporaneous_measured_Q": False, "reference": "HydroRIVERS_TechDoc_v10.pdf pp.3,6"},
            "independent_centerline": False, "independent_coastline": False,
            "ocean_outlet_certified": False, "dem_nodata_is_ocean": False, "dem_validity_sampled": False,
            "rights": "local_research_only; redistribution_permission_not_verified; CIAT_SRTM_readme_is_separate",
            "limitations": ["No DEM sampling or shoreline inference performed here.",
                            "NEXT_DOWN=0 means ocean OR inland sink, not observed coastline evidence.",
                            "Missing selected downstream reaches are not certified terminals.",
                            "DEM-derived product agreement is external cross-reference, not independent measurement.",
                            "No bathymetry, dam position, reservoir footprint, or synchronous measured Q supplied.",
                            "No legal redistribution clearance inferred from technical documentation summaries."]}


def audit_sources(source_root, bbox=DEFAULT_BBOX, halo_degrees=0.05):
    bbox = validate_bbox(bbox)
    if not math.isfinite(halo_degrees) or not 0 <= halo_degrees <= 5:
        raise EvidenceError("invalid halo degrees")
    halo_bbox = validate_bbox((bbox[0] - halo_degrees, bbox[1] - halo_degrees,
                               bbox[2] + halo_degrees, bbox[3] + halo_degrees))
    root = Path(source_root).resolve()
    archives = list(root.rglob("HydroRIVERS_v10_as_shp.zip"))
    if len(archives) != 1:
        raise EvidenceError("expected exactly one HydroRIVERS Asia archive")
    archive_path = archives[0]
    basin_paths = []
    for level in (4, 6):
        paths = list(root.rglob(f"hybas_as_lev{level:02d}_v1c.shp"))
        if len(paths) != 1:
            raise EvidenceError(f"expected exactly one level {level} basin shapefile")
        basin_paths.append(paths[0])
    level10_paths = list(root.rglob("hybas_as_lev10_v1c.zip"))
    if len(level10_paths) > 1:
        raise EvidenceError("ambiguous level 10 archive")
    source_paths = [archive_path] + level10_paths
    for path in basin_paths:
        source_paths.extend(path.with_suffix(extension) for extension in (".shp", ".dbf", ".prj", ".shx"))
    for name in ("HydroBASINS_TechDoc_v1c.pdf", "readme.txt"):
        source_paths.extend(root.rglob(name))
    sources = [{"path": str(path), "bytes": path.stat().st_size, "sha256_before": sha256_file(path)}
               for path in source_paths]
    with zipfile.ZipFile(archive_path, "r") as archive:
        members = verify_zip_members(archive)
        candidates = [name for name in archive.namelist() if name.endswith(".shp")]
        if len(candidates) != 1:
            raise EvidenceError("ambiguous river SHP ZIP member")
        shp_name = candidates[0]
        prefix = shp_name[:-4]
        crs = validate_wgs84(archive.read(prefix + ".prj"))
        with archive.open(shp_name) as shp, archive.open(prefix + ".dbf") as dbf, archive.open(prefix + ".shx") as shx:
            river_result = select_records(shp, archive.getinfo(shp_name).file_size,
                                          dbf, archive.getinfo(prefix + ".dbf").file_size,
                                          bbox, halo_bbox, shx_stream=shx,
                                          shx_size=archive.getinfo(prefix + ".shx").file_size)
    topology = topology_diagnostics(river_result["selected"], river_result["active_ids"], river_result["null_ids"])
    basin_results = []
    for path in basin_paths:
        basin_crs = validate_wgs84(path.with_suffix(".prj").read_bytes())
        with path.open("rb") as shp, path.with_suffix(".dbf").open("rb") as dbf, path.with_suffix(".shx").open("rb") as shx:
            result = select_records(shp, path.stat().st_size, dbf, path.with_suffix(".dbf").stat().st_size,
                                    bbox, halo_bbox, river=False, shx_stream=shx,
                                    shx_size=path.with_suffix(".shx").stat().st_size)
        basin_results.append({"path": str(path), "crs": basin_crs,
                              **{name: value for name, value in result.items() if name not in ("active_ids", "null_ids")}})
    level10 = {"status": "not_present", "usable": False}
    if level10_paths:
        try:
            with zipfile.ZipFile(level10_paths[0]) as archive:
                level10 = {"status": "central_directory_readable_not_used", "usable": False,
                           "member_count": len(archive.infolist())}
        except zipfile.BadZipFile as error:
            level10 = {"status": "BadZipFile", "usable": False, "reason": str(error)}
        level10["path"] = str(level10_paths[0])
    for source in sources:
        source["sha256_after"] = sha256_file(source["path"])
        source["unchanged"] = source["sha256_before"] == source["sha256_after"]
        if not source["unchanged"]:
            raise EvidenceError(f"source hash changed during audit: {source['path']}")
    selected = river_result["selected"]
    created = datetime.now(timezone.utc).isoformat()
    report = {"schema_version": 1, "algorithm": ALGORITHM, "created_utc": created,
              "candidate_bbox_lon_lat": bbox, "halo_degrees": halo_degrees, "halo_bbox_lon_lat": halo_bbox,
              "sources": sources, "zip_members": members, "crs": crs, "river_fields": river_result["fields"],
              "river_scan": {name: value for name, value in river_result.items() if name not in ("selected", "active_ids", "null_ids")},
              "selection_counts": {"river_total": len(selected), "candidate": sum(record["selection"] == "candidate_intersection" for record in selected),
                                   "halo_only": sum(record["selection"] == "halo_only" for record in selected)},
              "topology": topology, "basins": basin_results, "level10_archive": level10,
              "policy": evidence_policy(), "source_readonly_verified": True}
    vectors = {"schema_version": 1, "algorithm": ALGORITHM, "created_utc": created,
               "coordinate_order": "longitude,latitude", "crs": "WGS84", "units": "degrees",
               "geometry_policy": "full_selected_reaches_not_clipped; no_all_Asia_geometry_written",
               "candidate_bbox_lon_lat": bbox, "halo_bbox_lon_lat": halo_bbox,
               "source_archive_sha256": sources[0]["sha256_before"], "policy": evidence_policy(), "rivers": selected}
    return report, vectors


def publish_results(report, vectors, output_root):
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    with tempfile.TemporaryDirectory(prefix=".hydrovector-staging-", dir=output_root) as staging:
        staging_path = Path(staging)
        for name, payload in (("report.json", report), ("selected_vectors.json", vectors)):
            (staging_path / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        staging_path.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("D:/geography"))
    parser.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX,
                        metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--halo-degrees", type=float, default=0.05)
    args = parser.parse_args()
    output_root = Path(__file__).resolve().parents[1] / "verification" / "hydrovector-evidence"
    if output_root.resolve().is_relative_to(args.source_root.resolve()):
        parser.error("output must not be inside read-only source root")
    try:
        report, vectors = audit_sources(args.source_root, tuple(args.bbox), args.halo_degrees)
        target = publish_results(report, vectors, output_root)
    except (EvidenceError, OSError, zipfile.BadZipFile, RuntimeError, KeyError) as error:
        print(f"Hydrovector audit rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"result_path": str(target), "selected": report["selection_counts"],
                      "ocean_outlet_certified": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
