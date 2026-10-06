import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform

from terrain_pipeline.artifacts.contracts import digest
from terrain_pipeline.dem_domain import _seal, prepare_dem_candidate
from terrain_pipeline.real_dem_outlet_classification import (
    _validate_crs, build_outlet_classification, classification_geojson, validate_outlet_classification,
)
from terrain_pipeline.real_dem_surface_network import build_real_dem_network
from tools.audit_hydrovector_evidence import topology_diagnostics


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "verification/hydrovector-evidence/run-20260930T060422593821Z"


class OutletClassificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source = Path(temporary.name) / "dem.tif"
        with rasterio.open(source, "w", driver="GTiff", width=160, height=160, count=1,
                           dtype="float32", crs="EPSG:4326", nodata=-32768.,
                           transform=from_origin(121.35, 29.47, .001, .001)) as output:
            output.write(np.full((160, 160), 10., np.float32), 1)
        self.candidate = prepare_dem_candidate(
            source, [121.40, 29.40, 121.42, 29.42], target_crs="EPSG:32651", spacing_m=90.,
            halo_m=180., sea_level_m=0., sea_datum="unknown zero",
            source_declaration="synthetic elevation assumed metres")
        self.vectors = json.loads((EVIDENCE / "selected_vectors.json").read_text(encoding="utf8"))
        self.audit = json.loads((EVIDENCE / "report.json").read_text(encoding="utf8"))
        bbox = self.candidate["manifest"]["identity"]["recipe"]["bbox_epsg4326"]
        halo = [bbox[0] - .05, bbox[1] - .05, bbox[2] + .05, bbox[3] + .05]
        for document in (self.vectors, self.audit):
            document["candidate_bbox_lon_lat"] = bbox
            document["halo_bbox_lon_lat"] = halo
        template = copy.deepcopy(self.vectors["rivers"][0])
        template["attributes"].update(HYRIV_ID=20, NEXT_DOWN=0, MAIN_RIV=20)
        self.vectors["rivers"] = [template]
        grid = self.candidate["manifest"]["identity"]["grid"]
        row, col = np.asarray(self.candidate["arrays"]["height_m"].shape) // 2
        self.center_cell = int(row * self.candidate["arrays"]["height_m"].shape[1] + col)
        self.center = np.array([grid["origin_x_m"] + col * 90, -(grid["origin_z_m"] + row * 90)])
        self.set_projected_parts([np.array([self.center + [-700, 45], self.center + [700, 45]])])

    def refresh_audit(self):
        rivers = self.vectors["rivers"]
        active = {river["attributes"]["HYRIV_ID"] for river in rivers}
        active.update(river["attributes"]["NEXT_DOWN"] for river in rivers)
        self.audit["topology"] = topology_diagnostics(rivers, active)
        self.audit["topology"]["upstream_selected"] = {
            str(key): value for key, value in self.audit["topology"]["upstream_selected"].items()}
        self.audit["selection_counts"] = {"river_total": len(rivers), "candidate": len(rivers), "halo_only": 0}

    def set_projected_parts(self, parts):
        river = self.vectors["rivers"][0]
        geographic = []
        for part in parts:
            longitude, latitude = transform("EPSG:32651", "EPSG:4326", part[:, 0], part[:, 1])
            geographic.append(np.column_stack((longitude, latitude)).tolist())
        points = np.concatenate(geographic)
        river.update(parts_lon_lat=geographic,
                     bbox_lon_lat=np.r_[points.min(axis=0), points.max(axis=0)].tolist(),
                     part_endpoints_lon_lat=[[part[0], part[-1]] for part in geographic],
                     vertex_count=len(points), selection="candidate_intersection")
        self.refresh_audit()

    def reseal(self, height):
        arrays = {name: value.copy() for name, value in self.candidate["arrays"].items()}
        arrays["height_m"] = height
        arrays["valid_mask"] = np.isfinite(height)
        arrays["unknown_mask"] = ~arrays["valid_mask"]
        self.candidate = _seal(self.candidate["manifest"]["identity"], arrays)

    def build(self, **options):
        return build_outlet_classification(self.candidate, self.vectors, self.audit, **options)

    def validate(self, report):
        return validate_outlet_classification(report, self.candidate, self.vectors, self.audit)

    def test_flat_conservation_precedence_and_geojson(self):
        height = self.candidate["arrays"]["height_m"].copy()
        height[0, 1] = np.nan
        self.reseal(height)
        report = self.build()
        summary = report["summary"]
        self.assertEqual(summary["contributing_cells_sum"], np.isfinite(height).sum())
        self.assertEqual(summary["terminal_cells"], np.isfinite(height).sum())
        self.assertEqual(sum(summary["category_counts"].values()), summary["terminal_cells"])
        corner = report["outlets"][0]
        self.assertEqual(corner["classification"], "unknown_adjacent")
        self.assertTrue(corner["is_boundary_clip"])
        self.assertTrue(corner["is_unknown_adjacent"])
        internal = next(item for item in report["outlets"] if item["cell_id"] == self.center_cell)
        self.assertEqual(internal["classification"], "internal_sink")
        self.assertFalse(internal["natural_outlet_verified"])
        self.assertTrue(self.validate(report)["verified"])
        geojson = classification_geojson(report)
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(geojson["features"][0]["geometry"]["coordinates"], corner["lon_lat"])
        self.assertFalse(geojson["features"][0]["properties"]["ocean_outlet_certified"])

    def test_segment_midpoint_projected_distance_not_vertex_distance(self):
        report = self.build(match_distance_m=46.)
        outlet = next(item for item in report["outlets"] if item["cell_id"] == self.center_cell)
        np.testing.assert_allclose(outlet["projected_xy_m"], self.center, atol=1e-8)
        self.assertAlmostEqual(outlet["nearest_hydrovector"]["distance_m"], 45., places=6)
        self.assertTrue(outlet["nearest_hydrovector"]["matched"])
        self.assertTrue(outlet["nearest_hydrovector"]["product_terminal"])
        longitude, latitude = transform("EPSG:32651", "EPSG:4326", [self.center[0]], [self.center[1]])
        np.testing.assert_allclose(outlet["lon_lat"], [longitude[0], latitude[0]])
        self.assertFalse(next(item for item in self.build(match_distance_m=44.)["outlets"]
                              if item["cell_id"] == self.center_cell)["nearest_hydrovector"]["matched"])

    def test_zero_length_segment_and_smallest_id_tie(self):
        self.set_projected_parts([np.array([self.center, self.center])])
        smaller = copy.deepcopy(self.vectors["rivers"][0])
        smaller["record_index"] += 1
        smaller["attributes"].update(HYRIV_ID=10, MAIN_RIV=10)
        self.vectors["rivers"].append(smaller)
        self.refresh_audit()
        report = self.build()
        self.assertTrue(all(item["nearest_hydrovector"]["HYRIV_ID"] == 10 for item in report["outlets"]))
        outlet = next(item for item in report["outlets"] if item["cell_id"] == self.center_cell)
        self.assertLess(outlet["nearest_hydrovector"]["distance_m"], 1e-7)

    def test_downhill_terminal_contributions(self):
        rows, cols = np.indices(self.candidate["arrays"]["height_m"].shape)
        self.reseal((rows + cols).astype(float))
        report = self.build()
        self.assertEqual(len(report["outlets"]), 1)
        self.assertEqual(report["outlets"][0]["contributing_cells"], rows.size)

    def test_downstream_scopes_use_audit_not_geometry_orientation(self):
        second = copy.deepcopy(self.vectors["rivers"][0])
        second["record_index"] += 1
        second["attributes"].update(HYRIV_ID=30, NEXT_DOWN=999, MAIN_RIV=30)
        self.vectors["rivers"][0]["attributes"]["NEXT_DOWN"] = 30
        self.vectors["rivers"].append(second)
        self.refresh_audit()
        report = self.build()
        self.assertTrue(all(item["nearest_hydrovector"]["downstream_scope"] == "within_selected_vectors"
                            for item in report["outlets"]))
        self.audit["topology"]["adjacency"][0]["NEXT_DOWN"] = 888
        with self.assertRaises(ValueError):
            self.build()

    def test_invalid_thresholds(self):
        for threshold in (True, 0, -1, float("nan"), float("inf"), "180"):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                self.build(match_distance_m=threshold)

    def test_vector_schema_flags_ids_crs_coordinates_and_archive_rejected(self):
        original = copy.deepcopy(self.vectors)
        mutations = [lambda value: value.update(units="metres"),
                     lambda value: value.update(coordinate_order="latitude,longitude"),
                     lambda value: value.update(crs="EPSG:32651"),
                     lambda value: value.update(source_archive_sha256="0" * 64),
                     lambda value: value["policy"].update(independent_coastline=True),
                     lambda value: value["rivers"].append(copy.deepcopy(value["rivers"][0])),
                     lambda value: value["rivers"][0]["attributes"].update(NEXT_DOWN=True),
                     lambda value: value["rivers"][0]["parts_lon_lat"][0][0].__setitem__(0, 181.),
                     lambda value: value["rivers"][0]["parts_lon_lat"][0][0].__setitem__(1, float("nan")),
                     lambda value: value.update(extra=True)]
        for mutation in mutations:
            self.vectors = copy.deepcopy(original)
            mutation(self.vectors)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.build()

    def test_rehashed_false_natural_source_classification_distance_and_id_rejected(self):
        original = self.build()
        mutations = [lambda value: value.update(natural_outlet_verified=True),
                     lambda value: value["outlets"][0].update(ocean_outlet_certified=True),
                     lambda value: value["identity"].update(vectors_sha256="0" * 64),
                     lambda value: value["outlets"][0].update(classification="internal_sink"),
                     lambda value: value["outlets"][0]["nearest_hydrovector"].update(distance_m=123456.),
                     lambda value: value["outlets"][0]["nearest_hydrovector"].update(HYRIV_ID=999),
                     lambda value: value["summary"].update(contributing_cells_sum=0)]
        for mutation in mutations:
            report = copy.deepcopy(original)
            mutation(report)
            report["identity_sha256"] = digest(report["identity"])
            report["content_sha256"] = digest({key: value for key, value in report.items() if key != "content_sha256"})
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.validate(report)

    def test_invalid_rehashed_candidate_resolution_and_coordinates(self):
        original = self.candidate
        for name, value in (("spacing_x_m", -90.), ("origin_x_m", float("inf"))):
            self.candidate = copy.deepcopy(original)
            manifest = self.candidate["manifest"]
            manifest["identity"]["grid"][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.build()

    def test_strict_network_validation_rejects_order_receiver_accumulation(self):
        height = self.candidate["arrays"]["height_m"]
        valid = self.candidate["arrays"]["valid_mask"]
        for field in ("receiver", "order", "accumulation_cells"):
            network = build_real_dem_network(height, valid)
            if field == "receiver":
                network.receiver.flat[0] = height.size
            elif field == "order":
                network.order[0] = network.order[1]
            else:
                network.accumulation_cells.flat[0] = 2
            with patch("terrain_pipeline.real_dem_outlet_classification.build_real_dem_network", return_value=network):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.build()

    def test_deterministic_json_roundtrip(self):
        first = self.build()
        self.assertEqual(first, self.build())
        self.assertTrue(self.validate(json.loads(json.dumps(first, allow_nan=False)))["verified"])

    def test_frozen_esri_wgs84_prj_and_explicit_axis_order(self):
        frozen = json.loads((EVIDENCE / "report.json").read_text(encoding="utf8"))
        _validate_crs(frozen["crs"])
        for basin in frozen["basins"]:
            _validate_crs(basin["crs"])
        altered = copy.deepcopy(frozen["crs"])
        altered["coordinate_order"] = "latitude,longitude"
        with self.assertRaises(ValueError):
            _validate_crs(altered)

    def test_basins_bbox_references_and_coast_never_certify(self):
        report = self.build()
        references = report["basins_reference"]
        self.assertEqual([item["HYBAS_ID"] for item in references["selected"]], [4040009890, 4060010380])
        self.assertEqual([item["SUB_AREA"] for item in references["selected"]], [212335.4, 29366.5])
        self.assertFalse(references["level10_archive"]["usable"])
        self.assertTrue(all(item["selection_method"] == "conservative_polygon_bbox_overlap"
                            for item in references["selected"]))
        self.assertTrue(all(item["COAST"] == 1 and not item["natural_outlet_verified"]
                            for item in references["selected"]))
        self.audit["basins"][0]["selected"][0]["attributes"]["COAST"] = 0
        self.assertFalse(self.build()["natural_outlet_verified"])
        self.audit["basins"][0]["selected"][0]["attributes"]["COAST"] = True
        with self.assertRaises(ValueError):
            self.build()

    def test_rehashed_basins_independence_and_false_level10_rejected(self):
        report = self.build()
        report["basins_reference"]["selected"][0]["independent_observation"] = True
        report["content_sha256"] = digest({key: value for key, value in report.items() if key != "content_sha256"})
        with self.assertRaises(ValueError):
            self.validate(report)
        self.audit["basins"][0]["selected"][0]["independent_observation"] = True
        with self.assertRaises(ValueError):
            self.build()
        self.audit["basins"][0]["selected"][0]["independent_observation"] = False
        self.audit["level10_archive"]["usable"] = True
        with self.assertRaises(ValueError):
            self.build()


if __name__ == "__main__":
    unittest.main()
