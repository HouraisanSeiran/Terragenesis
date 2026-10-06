import io
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.audit_hydrovector_evidence import (
    DbfReader, EvidenceError, audit_sources, evidence_policy, iter_shapes,
    parse_shape, publish_results, select_records, sha256_file,
    topology_diagnostics, validate_bbox, validate_river_attributes,
    validate_wgs84, verify_zip_members,
)


PRJ = b'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
BBOX = (121.25, 29.15, 121.65, 29.65)
POINTS = [(121.3, 29.3), (121.4, 29.4)]
FIELDS = [("HYRIV_ID", "N", 9, 0), ("NEXT_DOWN", "N", 9, 0),
          ("MAIN_RIV", "N", 9, 0), ("DIS_AV_CMS", "N", 10, 3)]


def shape_payload(points=POINTS, kind=3, parts=(0,)):
    bbox = (min(point[0] for point in points), min(point[1] for point in points),
            max(point[0] for point in points), max(point[1] for point in points))
    payload = struct.pack("<i4dii", kind, *bbox, len(parts), len(points))
    payload += struct.pack(f"<{len(parts)}i", *parts)
    payload += b"".join(struct.pack("<dd", *point) for point in points)
    if kind in (13, 15):
        payload += struct.pack(f"<{len(points) + 2}d", 10, 10, *([10] * len(points)))
    return payload


def shape_files(payloads, kind=3, bbox=(-180, -90, 180, 90)):
    header = bytearray(100)
    struct.pack_into(">i", header, 0, 9994)
    struct.pack_into("<ii4d", header, 28, 1000, kind, *bbox)
    shp_body, shx_body, offset = b"", b"", 100
    for record_index, payload in enumerate(payloads, 1):
        shp_body += struct.pack(">ii", record_index, len(payload) // 2) + payload
        shx_body += struct.pack(">ii", offset // 2, len(payload) // 2)
        offset += 8 + len(payload)
    shp_header, shx_header = bytearray(header), bytearray(header)
    struct.pack_into(">i", shp_header, 24, (100 + len(shp_body)) // 2)
    struct.pack_into(">i", shx_header, 24, (100 + len(shx_body)) // 2)
    return bytes(shp_header) + shp_body, bytes(shx_header) + shx_body


def dbf_bytes(rows, fields=FIELDS, deleted=()):
    header_size, record_size = 33 + 32 * len(fields), 1 + sum(field[2] for field in fields)
    header = bytearray(32)
    header[0] = 3
    struct.pack_into("<IHH", header, 4, len(rows), header_size, record_size)
    descriptors = b""
    for name, kind, width, decimals in fields:
        descriptor = bytearray(32)
        descriptor[:len(name)] = name.encode("ascii")
        descriptor[11], descriptor[16], descriptor[17] = ord(kind), width, decimals
        descriptors += descriptor
    payload = bytes(header) + descriptors + b"\r"
    for index, row in enumerate(rows, 1):
        payload += b"*" if index in deleted else b" "
        for value, field in zip(row, fields):
            payload += str(value).rjust(field[2]).encode("ascii")
    return payload + b"\x1a"


def selected_fixture(payloads=None, rows=None, fields=FIELDS, deleted=()):
    shp, shx = shape_files(payloads or [shape_payload()])
    dbf = dbf_bytes(rows or [(1, 0, 1, "0.125")], fields, deleted)
    return select_records(io.BytesIO(shp), len(shp), io.BytesIO(dbf), len(dbf), BBOX, BBOX,
                          shx_stream=io.BytesIO(shx), shx_size=len(shx))


class HydrovectorEvidenceTests(unittest.TestCase):
    def test_polyline3_and_attributes(self):
        result = selected_fixture()
        self.assertEqual(result["selected"][0]["parts_lon_lat"], [POINTS])
        self.assertEqual(result["selected"][0]["attributes"]["DIS_AV_CMS"], 0.125)

    def test_polyline_z_and_m(self):
        payload = shape_payload(kind=13)
        shp, shx = shape_files([payload], kind=13)
        parsed = list(iter_shapes(io.BytesIO(shp), len(shp)))[0]
        self.assertEqual(parsed["points"], POINTS)
        measure = struct.pack("<4d", -1e39, -1e39, -1e39, -1e39)
        self.assertEqual(parse_shape(payload + measure, 13, (-180, -90, 180, 90))["points"], POINTS)

    def test_truncated_shp_header_and_record(self):
        shp, shx = shape_files([shape_payload()])
        for cut in (20, 99, 103, len(shp) - 1):
            with self.subTest(cut=cut), self.assertRaises(EvidenceError):
                list(iter_shapes(io.BytesIO(shp[:cut]), len(shp)))

    def test_shp_declared_size_and_index(self):
        shp, shx = shape_files([shape_payload()])
        invalid = bytearray(shp)
        struct.pack_into(">i", invalid, 100, 2)
        with self.assertRaisesRegex(EvidenceError, "index alignment"):
            list(iter_shapes(io.BytesIO(invalid), len(invalid)))
        with self.assertRaises(EvidenceError):
            list(iter_shapes(io.BytesIO(shp), len(shp) - 2))

    def test_shx_offset_and_count_alignment(self):
        shp, shx = shape_files([shape_payload()])
        invalid = bytearray(shx)
        struct.pack_into(">i", invalid, 100, 51)
        with self.assertRaisesRegex(EvidenceError, "alignment"):
            list(iter_shapes(io.BytesIO(shp), len(shp), shx_stream=io.BytesIO(invalid), shx_size=len(invalid)))

    def test_deleted_dbf_records_do_not_shift_geometry(self):
        second_points = [(121.5, 29.5), (121.6, 29.6)]
        result = selected_fixture([shape_payload(), shape_payload(second_points)],
                                  [(1, 0, 1, "0.125"), (2, 0, 2, "0.250")], deleted=(1,))
        self.assertEqual(result["deleted_record_count"], 1)
        self.assertEqual(result["selected"][0]["record_index"], 2)
        self.assertEqual(result["selected"][0]["attributes"]["HYRIV_ID"], 2)
        self.assertEqual(result["selected"][0]["parts_lon_lat"], [second_points])

    def test_null_records_preserve_dbf_alignment(self):
        result = selected_fixture([struct.pack("<i", 0), shape_payload()],
                                  [(1, 0, 1, "0.125"), (2, 0, 2, "0.250")])
        self.assertEqual(result["selected"][0]["record_index"], 2)
        self.assertEqual(result["null_ids"], {1})

    def test_dbf_alignment_both_directions(self):
        for payloads, rows in (([shape_payload()], [(1, 0, 1, 1), (2, 0, 2, 1)]),
                               ([shape_payload(), shape_payload()], [(1, 0, 1, 1)])):
            with self.subTest(rows=len(rows)), self.assertRaisesRegex(EvidenceError, "alignment"):
                selected_fixture(payloads, rows)

    def test_truncated_dbf_header_descriptors_and_records(self):
        dbf = dbf_bytes([(1, 0, 1, "0.125")])
        for cut in (20, 60, len(dbf) - 3):
            with self.subTest(cut=cut), self.assertRaises(EvidenceError):
                table = DbfReader(io.BytesIO(dbf[:cut]), len(dbf))
                table.read_record()

    def test_dbf_width_deletion_marker_and_terminator(self):
        original = dbf_bytes([(1, 0, 1, "0.125")])
        header_size = struct.unpack_from("<H", original, 8)[0]
        for offset, value in ((10, 1), (header_size - 1, 0), (header_size, ord("!")), (len(original) - 1, 0)):
            invalid = bytearray(original)
            invalid[offset] = value
            with self.subTest(offset=offset), self.assertRaises(EvidenceError):
                table = DbfReader(io.BytesIO(invalid), len(invalid))
                table.read_record()
                table.finish()

    def test_dbf_numeric_and_field_types_rejected(self):
        for text in ("NaN", "********", "1e999"):
            with self.subTest(text=text), self.assertRaises(EvidenceError):
                selected_fixture(rows=[(1, 0, 1, text)])
        fields = FIELDS[:3] + [("DIS_AV_CMS", "C", 10, 0)]
        with self.assertRaisesRegex(EvidenceError, "field type"):
            selected_fixture(fields=fields)
        with self.assertRaises(EvidenceError):
            validate_river_attributes({"HYRIV_ID": 1, "NEXT_DOWN": 0, "MAIN_RIV": 1, "LENGTH_KM": "broken"})

    def test_invalid_bbox_field_and_coordinate_range(self):
        payload = bytearray(shape_payload())
        struct.pack_into("<d", payload, 4, 121.0)
        with self.assertRaisesRegex(EvidenceError, "bbox"):
            parse_shape(payload, 3, (-180, -90, 180, 90))
        for bbox in ((122, 29, 121, 30), (181, 29, 182, 30), (121, float("nan"), 122, 30)):
            with self.subTest(bbox=bbox), self.assertRaises(EvidenceError):
                validate_bbox(bbox)
        payload = bytearray(shape_payload())
        struct.pack_into("<d", payload, 48, float("nan"))
        with self.assertRaisesRegex(EvidenceError, "coordinate"):
            parse_shape(payload, 3, (-180, -90, 180, 90))

    def test_invalid_part_and_z_payload(self):
        payload = bytearray(shape_payload())
        struct.pack_into("<i", payload, 44, 1)
        with self.assertRaisesRegex(EvidenceError, "part index"):
            parse_shape(payload, 3, (-180, -90, 180, 90))
        with self.assertRaisesRegex(EvidenceError, "Z/M"):
            parse_shape(shape_payload(kind=13)[:-8], 13, (-180, -90, 180, 90))

    def test_bbox_overlap_not_sufficient_for_line_selection(self):
        points = [(121.1, 29.6), (121.3, 29.8)]
        result = selected_fixture([shape_payload(points)])
        self.assertEqual(result["selected"], [])

    def test_crossing_segment_selected_without_vertex_inside(self):
        result = selected_fixture([shape_payload([(121.0, 29.4), (121.9, 29.4)])])
        self.assertEqual(len(result["selected"]), 1)
        self.assertFalse(result["selected"][0]["geometry_clipped"])

    def test_polygon_selection_is_bbox_only(self):
        polygon = shape_payload([(121.1, 29.6), (121.3, 29.8), (121.1, 29.8), (121.1, 29.6)], kind=5)
        shp, shx = shape_files([polygon], kind=5)
        dbf = dbf_bytes([(1,)], [("HYBAS_ID", "N", 10, 0)])
        result = select_records(io.BytesIO(shp), len(shp), io.BytesIO(dbf), len(dbf), BBOX, BBOX, river=False)
        self.assertEqual(result["selected"][0]["selection"], "candidate_bbox_only")
        self.assertEqual(result["selected"][0]["selection_method"], "conservative_polygon_bbox_overlap")

    def test_wgs84_verified_not_inferred_from_coordinates(self):
        self.assertEqual(validate_wgs84(PRJ)["datum"], "WGS84")
        for bad in (PRJ.replace(b"WGS_1984", b"CGCS2000"), PRJ.replace(b"6378137.0", b"6370000.0"), b'PROJCS["WGS84"]'):
            with self.subTest(prj=bad), self.assertRaises(EvidenceError):
                validate_wgs84(bad)

    def test_terminal_missing_and_null_downstream_never_certify_ocean(self):
        selected = selected_fixture(rows=[(1, 9, 1, "0.125")])["selected"]
        for ids, nulls, expected in (({1, 9}, set(), "outside_spatial_selection"),
                                     ({1}, set(), "absent_or_deleted_in_source"),
                                     ({1, 9}, {9}, "null_geometry_in_source")):
            result = topology_diagnostics(selected, ids, nulls)
            self.assertEqual(result["missing_downstream"][0]["status"], expected)
            self.assertEqual(result["certified_ocean_outlet_count"], 0)
        selected[0]["attributes"]["NEXT_DOWN"] = 0
        result = topology_diagnostics(selected, {1})
        self.assertFalse(result["terminals"][0]["ocean_outlet_certified"])
        self.assertEqual(result["endpoints"][0]["dem_validity"], "not_sampled_by_this_audit")
        self.assertFalse(evidence_policy()["dem_nodata_is_ocean"])

    def test_adjacency_gaps_and_cycles_are_diagnostic(self):
        result = selected_fixture([shape_payload(), shape_payload([(121.5, 29.5), (121.6, 29.6)])],
                                  [(1, 2, 1, "0.125"), (2, 1, 1, "0.250")])
        topology = topology_diagnostics(result["selected"], result["active_ids"])
        self.assertEqual(topology["selected_cycles"], [[1, 2]])
        self.assertEqual(len(topology["endpoint_gaps_over_1m"]), 2)

    def test_missing_endpoint_rejected_not_ocean_terminal(self):
        selected = selected_fixture()["selected"]
        for endpoints in (None, [], [[None, POINTS[1]]]):
            selected[0]["part_endpoints_lon_lat"] = endpoints
            with self.subTest(endpoints=endpoints), self.assertRaisesRegex(EvidenceError, "cannot certify ocean"):
                topology_diagnostics(selected, {1})

    def test_crc_all_members_and_corrupt_member_rejection(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("directory/", b"")
            archive.writestr("member", b"abc")
        with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as archive:
            self.assertTrue(all(entry["crc_verified"] for entry in verify_zip_members(archive)))
            entry = archive.getinfo("member")
            offset = entry.header_offset + 30 + len(entry.filename)
        invalid = bytearray(stream.getvalue())
        invalid[offset] ^= 1
        with zipfile.ZipFile(io.BytesIO(invalid)) as archive, self.assertRaises(zipfile.BadZipFile):
            verify_zip_members(archive)

    def test_end_to_end_source_hashes_and_failed_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            shp, shx = shape_files([shape_payload()])
            with zipfile.ZipFile(root / "HydroRIVERS_v10_as_shp.zip", "w") as archive:
                for extension, data in (("shp", shp), ("shx", shx), ("dbf", dbf_bytes([(1, 0, 1, "0.125")])), ("prj", PRJ)):
                    archive.writestr("river." + extension, data)
                archive.writestr("HydroRIVERS_TechDoc_v10.pdf", b"synthetic-test-only")
            polygon = shape_payload([(121.3, 29.3), (121.4, 29.3), (121.4, 29.4), (121.3, 29.3)], kind=5)
            shp, shx = shape_files([polygon], kind=5)
            for level in (4, 6):
                for extension, data in (("shp", shp), ("shx", shx), ("dbf", dbf_bytes([(1,)], [("HYBAS_ID", "N", 10, 0)])), ("prj", PRJ)):
                    (root / f"hybas_as_lev{level:02d}_v1c.{extension}").write_bytes(data)
            (root / "hybas_as_lev10_v1c.zip").write_bytes(b"broken-central-directory")
            before = {path.name: sha256_file(path) for path in root.iterdir()}
            report, vectors = audit_sources(root)
            after = {path.name: sha256_file(path) for path in root.iterdir()}
            self.assertEqual(before, after)
            self.assertTrue(all(source["unchanged"] for source in report["sources"]))
            self.assertEqual(report["level10_archive"]["status"], "BadZipFile")
            target = publish_results(report, vectors, Path(directory) / "output")
            self.assertEqual(json.loads((target / "selected_vectors.json").read_text())["rivers"][0]["attributes"]["HYRIV_ID"], 1)
            with self.assertRaises(ValueError):
                publish_results({"bad": float("nan")}, vectors, Path(directory) / "failed")
            self.assertEqual(list((Path(directory) / "failed").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
