import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import Affine, from_origin
from rasterio.warp import transform

from terrain_pipeline.artifacts.contracts import array_hash, digest
from terrain_pipeline.td_source import file_sha256, load_dem_candidate, prepare_dem_candidate, route_dem_candidate, save_dem_candidate, validate_dem_candidate


class DemDomainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.tif"
        self.write_source(np.full((160, 160), 10., np.float32))
        self.bbox = (121.40, 29.40, 121.42, 29.42)

    def write_source(self, height, *, nodata=-32768., crs="EPSG:4326", affine=None,
                     scale=1., offset=0., unit=None):
        if affine is None:
            affine = from_origin(121.35, 29.47, .001, .001)
        with rasterio.open(self.source, "w", driver="GTiff", width=height.shape[1],
                           height=height.shape[0], count=1, dtype=height.dtype,
                           crs=crs, transform=affine, nodata=nodata) as output:
            output.write(height, 1)
            output.scales = (scale,)
            output.offsets = (offset,)
            if unit is not None:
                output.set_band_unit(1, unit)

    def prepare(self, **options):
        parameters = {"target_crs": "EPSG:32651", "spacing_m": 90., "halo_m": 180.,
                      "sea_level_m": 0., "sea_datum": "unknown numeric zero",
                      "source_declaration": "synthetic test elevation assumed metres; local research only"}
        parameters.update(options)
        bbox = parameters.pop("bbox", self.bbox)
        return prepare_dem_candidate(self.source, bbox, **parameters)

    def test_missouri_utm15_source_and_cold_replay(self):
        self.write_source(np.full((160, 160), 125., np.float32),
                          affine=from_origin(-94.35, 39.17, .001, .001), unit="m")
        candidate = self.prepare(bbox=(-94.30, 39.10, -94.28, 39.12), target_crs="EPSG:32615")
        self.assertEqual(candidate["manifest"]["identity"]["recipe"]["target_crs"], "EPSG:32615")
        self.assertTrue(np.all(candidate["arrays"]["height_m"][candidate["arrays"]["valid_mask"]] == 125.))
        path = self.root / "missouri.npz"
        save_dem_candidate(candidate, path)
        cold = load_dem_candidate(path, verify_source=True)
        self.assertEqual(cold["manifest"]["identity_sha256"], candidate["manifest"]["identity_sha256"])
        with self.assertRaisesRegex(ValueError, "inside its explicit"):
            self.prepare(bbox=(-94.30, 39.10, -94.28, 39.12), target_crs="EPSG:32651")
        with self.assertRaisesRegex(ValueError, "inside its explicit"):
            self.prepare(bbox=(-96.01, 39.10, -95.99, 39.12), target_crs="EPSG:32615")

    def rehash(self, candidate):
        manifest = candidate["manifest"]
        manifest["identity_sha256"] = digest(manifest["identity"])
        manifest["array_hashes"] = {name: array_hash(value) for name, value in candidate["arrays"].items()}
        manifest["content_sha256"] = digest({name: value for name, value in manifest.items() if name != "content_sha256"})

    def write_package(self, candidate, name="tampered.npz"):
        path = self.root / name
        np.savez_compressed(path, manifest=json.dumps(candidate["manifest"]), **candidate["arrays"])
        return path

    def test_metric_crs_grid_pixel_centers_and_negative_northing(self):
        candidate = self.prepare()
        identity = candidate["manifest"]["identity"]
        grid = identity["grid"]
        self.assertEqual(identity["recipe"]["target_crs"], "EPSG:32651")
        self.assertEqual(grid["spacing_x_m"], 90)
        self.assertEqual(grid["spacing_z_m"], 90)
        affine = Affine(*grid["target_transform"])
        for row, col in ((0, 0), (2, 3)):
            easting, northing = affine * (col + .5, row + .5)
            self.assertEqual(grid["origin_x_m"] + col * 90, easting)
            self.assertEqual(grid["origin_z_m"] + row * 90, -northing)
        self.assertLess(grid["origin_z_m"], 0)
        self.assertEqual(identity["source"]["pixel_center_offset_col_row"], [.5, .5])
        self.assertEqual(identity["source"]["area_or_point"], "Area")
        self.assertTrue(candidate["arrays"]["core_mask"].any())
        self.assertTrue((~candidate["arrays"]["core_mask"]).any())

    def test_nearest_samples_actual_source_centers_not_old_node_indices(self):
        values = np.arange(160 * 160, dtype=np.float32).reshape(160, 160)
        self.write_source(values)
        candidate = self.prepare()
        grid = candidate["manifest"]["identity"]["grid"]
        rows, cols = np.indices(candidate["arrays"]["height_m"].shape)
        longitude, latitude = transform("EPSG:32651", "EPSG:4326",
            (grid["origin_x_m"] + cols.ravel() * 90).tolist(),
            (-(grid["origin_z_m"] + rows.ravel() * 90)).tolist())
        with rasterio.open(self.source) as source:
            expected = np.asarray([sample[0] for sample in source.sample(zip(longitude, latitude))])
        np.testing.assert_array_equal(candidate["arrays"]["height_m"], expected.reshape(rows.shape))

    def test_large_domain_centers_exactly_match_source_sample(self):
        rows, cols = np.indices((900, 900))
        values = (rows * 1000 + cols).astype(np.float32)
        values[200:240, 300:360] = -32768.
        self.write_source(values, affine=from_origin(121.1, 29.8, 1 / 1200, 1 / 1200))
        candidate = self.prepare(bbox=(121.25, 29.15, 121.65, 29.65), halo_m=900.)
        grid = candidate["manifest"]["identity"]["grid"]
        height = candidate["arrays"]["height_m"]
        indices = np.linspace(0, height.size - 1, 251, dtype=int)
        row_indices, col_indices = np.divmod(indices, height.shape[1])
        longitude, latitude = transform("EPSG:32651", "EPSG:4326",
            (grid["origin_x_m"] + col_indices * 90).tolist(),
            (-(grid["origin_z_m"] + row_indices * 90)).tolist())
        with rasterio.open(self.source) as source:
            expected = np.asarray([np.nan if np.ma.is_masked(sample[0]) else float(sample[0])
                                   for sample in source.sample(zip(longitude, latitude), masked=True)])
        np.testing.assert_array_equal(height.ravel()[indices], expected)
        np.testing.assert_array_equal(candidate["arrays"]["valid_mask"].ravel()[indices], np.isfinite(expected))
        self.assertLessEqual(candidate["manifest"]["identity"]["source"]["read_cells"], 599999)
        self.assertEqual(candidate["manifest"]["format"], "dem-domain-candidate-v2")
        self.assertEqual(candidate["manifest"]["identity"]["recipe"]["sampling"],
                         "exact_inverse_target_pixel_center_source_affine_floor")

    def test_v1_package_not_silently_loaded_as_exact_v2(self):
        candidate = copy.deepcopy(self.prepare())
        candidate["manifest"]["format"] = "dem-domain-candidate-v1"
        candidate["manifest"]["identity"]["algorithm"] = "bounded-nearest-dem-projection-v1"
        self.rehash(candidate)
        with self.assertRaises(ValueError):
            load_dem_candidate(self.write_package(candidate), verify_source=False)

    def test_large_domain_exact_sampling_is_chunk_bounded(self):
        from terrain_pipeline.td_source import _target_center_blocks
        grid = {"shape_zx": [642, 460], "origin_x_m": 328905., "origin_z_m": -3282165.,
                "spacing_x_m": 90., "spacing_z_m": 90.}
        total = 0
        for start, end, eastings, northings in _target_center_blocks(grid):
            self.assertLessEqual(end - start, 32)
            self.assertEqual(eastings.size, (end - start) * 460)
            self.assertEqual(northings.size, eastings.size)
            self.assertEqual(northings[0], -(grid["origin_z_m"] + start * 90))
            total += eastings.size
        self.assertEqual(total, 642 * 460)

    def test_nodata_candidate_preserved_and_routing_rejected_before_route(self):
        values = np.full((160, 160), 10., np.float32)
        values[50:60, 50:60] = -32768.
        self.write_source(values)
        before = file_sha256(self.source)
        candidate = self.prepare()
        unknown = candidate["arrays"]["unknown_mask"]
        self.assertTrue(unknown.any())
        self.assertTrue(np.isnan(candidate["arrays"]["height_m"][unknown]).all())
        self.assertFalse(candidate["manifest"]["summary"]["publishable"])
        package = save_dem_candidate(candidate, self.root / "candidate.npz")
        loaded = load_dem_candidate(package)
        np.testing.assert_array_equal(loaded["arrays"]["unknown_mask"], unknown)
        with patch('terrain_pipeline.td_source.route') as drainage:
            with self.assertRaisesRegex(ValueError, "unknown coverage"):
                route_dem_candidate(loaded)
            drainage.assert_not_called()
        self.assertEqual(before, file_sha256(self.source))

    def test_all_nodata_is_rejected_not_ocean(self):
        self.write_source(np.full((160, 160), -32768., np.float32))
        with self.assertRaisesRegex(ValueError, "no coverage"):
            self.prepare()

    def test_unmasked_nonfinite_source_rejected(self):
        for bad in (np.nan, np.inf, -np.inf):
            with self.subTest(bad=bad):
                values = np.full((160, 160), bad, np.float32)
                self.write_source(values)
                with self.assertRaisesRegex(ValueError, "nonfinite"):
                    self.prepare()

    def test_declared_nan_nodata_preserved(self):
        values = np.full((160, 160), 10., np.float32)
        values[50:60, 50:60] = np.nan
        self.write_source(values, nodata=np.nan)
        candidate = self.prepare()
        self.assertTrue(candidate["arrays"]["unknown_mask"].any())
        save_dem_candidate(candidate, self.root / "nan-nodata.npz")

    def test_uncovered_bbox_and_halo_early_rejected(self):
        for bbox in ((121.30, 29.4, 121.42, 29.42), (121.35, 29.4, 121.36, 29.42)):
            with self.subTest(bbox=bbox), self.assertRaisesRegex(ValueError, "not covered"):
                self.prepare(bbox=bbox)

    def test_resource_limits_before_raster_read(self):
        for options, message in (({"max_cells": 1}, "max_cells"),
                                 ({"max_source_cells": 1}, "max_source_cells"),
                                 ({"max_source_cells": 600000}, "max_source_cells")):
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, message):
                self.prepare(**options)

    def test_nondefault_band_scale_and_offset_early_rejected(self):
        for scale, offset in ((2., 0.), (.1, 0.), (1., 10.), (1., -10.)):
            with self.subTest(scale=scale, offset=offset):
                self.write_source(np.full((160, 160), 10., np.float32), scale=scale, offset=offset)
                with patch('terrain_pipeline.td_source._exact_sample') as projection:
                    with self.assertRaisesRegex(ValueError, "band_scale=1 and band_offset=0"):
                        self.prepare()
                    projection.assert_not_called()

    def test_explicit_nonmetre_band_units_early_rejected(self):
        for unit in ("ft", "feet", "US survey foot", "cm", "km", "degrees"):
            with self.subTest(unit=unit):
                self.write_source(np.full((160, 160), 10., np.float32), unit=unit)
                with patch('terrain_pipeline.td_source._exact_sample') as projection:
                    with self.assertRaisesRegex(ValueError, "non-metre"):
                        self.prepare()
                    projection.assert_not_called()

    def test_unknown_band_unit_requires_explicit_metres_assumption(self):
        with self.assertRaisesRegex(ValueError, "elevation assumed metres"):
            self.prepare(source_declaration="local research only; metres not independently established")
        candidate = self.prepare()
        self.assertIsNone(candidate["manifest"]["identity"]["source"]["band_unit"])
        self.assertIn("elevation assumed metres", candidate["manifest"]["identity"]["recipe"]["source_declaration"])

    def test_explicit_metre_band_units_accepted_without_assumption(self):
        for unit in ("m", "metre", "meters"):
            with self.subTest(unit=unit):
                self.write_source(np.full((160, 160), 10., np.float32), unit=unit)
                candidate = self.prepare(source_declaration="synthetic metres declared by band unit; local research only")
                self.assertEqual(candidate["manifest"]["identity"]["source"]["band_unit"], unit)
                self.assertTrue(np.all(candidate["arrays"]["height_m"] == 10.))

    def test_offline_rehashed_nonmetric_source_header_rejected(self):
        for name, value in (("band_scale", 2.), ("band_offset", 10.), ("band_unit", "ft")):
            changed = copy.deepcopy(self.prepare())
            changed["manifest"]["identity"]["source"][name] = value
            self.rehash(changed)
            with self.subTest(name=name), self.assertRaises(ValueError):
                load_dem_candidate(self.write_package(changed), verify_source=False)

    def test_invalid_crs_spacing_bbox_sea_and_datum_rejected(self):
        cases = ({"target_crs": "EPSG:4326"}, {"spacing_m": 30.}, {"sea_level_m": 126.},
                 {"bbox": (121.4, np.nan, 121.42, 29.42)}, {"halo_m": 0.},
                 {"vertical_datum_status": "EGM96_verified"}, {"source_declaration": ""})
        for options in cases:
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.prepare(**options)

    def test_roundtrip_no_overwrite_and_read_only(self):
        candidate = self.prepare()
        path = save_dem_candidate(candidate, self.root / "candidate.npz")
        before = file_sha256(path)
        loaded = load_dem_candidate(path)
        self.assertEqual(candidate["manifest"], loaded["manifest"])
        for name in candidate["arrays"]:
            np.testing.assert_array_equal(candidate["arrays"][name], loaded["arrays"][name])
            self.assertFalse(loaded["arrays"][name].flags.writeable)
        with self.assertRaises(FileExistsError):
            save_dem_candidate(candidate, path)
        self.assertEqual(before, file_sha256(path))

    def test_array_and_identity_tamper_rejected(self):
        candidate = self.prepare()
        for field in ("height", "identity"):
            changed = copy.deepcopy(candidate)
            if field == "height":
                changed["arrays"]["height_m"][0, 0] += 1
            else:
                changed["manifest"]["identity"]["recipe"]["bbox_epsg4326"][0] += .001
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_dem_candidate(self.write_package(changed))

    def test_rehashed_false_evidence_and_publication_rejected(self):
        candidate = self.prepare()
        for key in ("publishable", "default_world_eligible", "natural_outlet_verified",
                    "river_independently_verified", "closed_observed_candidate"):
            changed = copy.deepcopy(candidate)
            changed["manifest"]["summary"][key] = True
            self.rehash(changed)
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "cannot publish"):
                load_dem_candidate(self.write_package(changed))

    def test_rehashed_infinite_height_and_false_center_rejected(self):
        candidate = self.prepare()
        for field in ("height", "center"):
            changed = copy.deepcopy(candidate)
            if field == "height":
                changed["arrays"]["height_m"][0, 0] = np.inf
            else:
                changed["manifest"]["identity"]["grid"]["origin_z_m"] *= -1
            self.rehash(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                load_dem_candidate(self.write_package(changed))

    def test_source_changed_rejected(self):
        candidate = self.prepare()
        path = save_dem_candidate(candidate, self.root / "candidate.npz")
        self.write_source(np.full((160, 160), 20., np.float32))
        with self.assertRaisesRegex(ValueError, "source hash"):
            load_dem_candidate(path)

    def test_different_bbox_identity(self):
        first = self.prepare()
        second = self.prepare(bbox=(121.401, 29.4, 121.42, 29.42))
        self.assertNotEqual(first["manifest"]["identity_sha256"], second["manifest"]["identity_sha256"])
        self.assertNotEqual(first["manifest"]["identity"]["recipe_sha256"], second["manifest"]["identity"]["recipe_sha256"])

    def test_atomic_save_failure_cleans_temporary_without_product(self):
        candidate = self.prepare()
        destination = self.root / "candidate.npz"
        with patch('terrain_pipeline.td_source.os.link', side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                save_dem_candidate(candidate, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob(".candidate.npz-*")), [])

    def test_atomic_destination_race_does_not_overwrite(self):
        candidate = self.prepare()
        destination = self.root / "candidate.npz"
        import os
        real_link = os.link

        def racing_link(temporary, target):
            Path(target).write_bytes(b"competing-writer")
            return real_link(temporary, target)

        with patch('terrain_pipeline.td_source.os.link', side_effect=racing_link):
            with self.assertRaises(FileExistsError):
                save_dem_candidate(candidate, destination)
        self.assertEqual(destination.read_bytes(), b"competing-writer")
        self.assertEqual(list(self.root.glob(".candidate.npz-*")), [])

    def test_no_artificial_outlet_fallback(self):
        candidate = self.prepare()
        self.assertFalse(candidate["arrays"]["unknown_mask"].any())
        with self.assertRaisesRegex(ValueError, "no artificial outlet"):
            route_dem_candidate(candidate)

    def test_complete_explicit_outlet_routing_still_not_publishable(self):
        values = np.tile(np.linspace(20, -5, 160, dtype=np.float32), (160, 1))
        self.write_source(values)
        candidate = self.prepare(bbox=(121.465, 29.4, 121.49, 29.42))
        outlets = np.zeros(candidate["arrays"]["height_m"].shape, bool)
        outlets[-1, -1] = True
        routed = route_dem_candidate(candidate, outlets)
        self.assertFalse(routed["publishable"])
        self.assertTrue(routed["outlet_candidates"])
        self.assertTrue(all(not entry["natural_mouth_verified"] for entry in routed["outlet_candidates"]))
        self.assertTrue(all(not entry["river_independently_verified"] for entry in routed["outlet_candidates"]))
        self.assertEqual(candidate["manifest"]["identity"]["recipe"]["vertical_datum_status"], "unknown")
        validate_dem_candidate(candidate)

    def test_explicit_outlets_required_even_when_low_proxy_exists(self):
        self.write_source(np.full((160, 160), -1., np.float32))
        candidate = self.prepare()
        for outlets in (None, np.zeros(candidate["arrays"]["height_m"].shape, bool),
                        np.ones(candidate["arrays"]["height_m"].shape, int), np.ones((1, 1), bool)):
            with self.subTest(outlets=type(outlets)), self.assertRaises(ValueError):
                route_dem_candidate(candidate, outlets)

    def test_rehashed_source_coordinate_metadata_rejected(self):
        candidate = self.prepare()
        changes = {"transform": [1., 0., 0., 0., -1., 1.],
                   "read_transform": [1., 0., 0., 0., -1., 1.], "crs": "EPSG:32651",
                   "read_window_col_row_width_height": [0, 0, 2, 2],
                   "nodata": -9999., "area_or_point": "Point", "band_count": 2,
                   "band_scale": 2., "band_unit": "ft"}
        for name, value in changes.items():
            changed = copy.deepcopy(candidate)
            changed["manifest"]["identity"]["source"][name] = value
            self.rehash(changed)
            with self.subTest(name=name), self.assertRaises(ValueError):
                load_dem_candidate(self.write_package(changed))

    def test_offline_internal_transform_inconsistency_rejected(self):
        candidate = copy.deepcopy(self.prepare())
        candidate["manifest"]["identity"]["source"]["read_transform"][2] += .001
        self.rehash(candidate)
        with self.assertRaisesRegex(ValueError, "semantics"):
            load_dem_candidate(self.write_package(candidate), verify_source=False)

    def test_rehashed_coherent_but_false_header_rejected_by_replay(self):
        from terrain_pipeline.td_source import _window
        from rasterio.warp import transform_bounds
        from types import SimpleNamespace
        candidate = copy.deepcopy(self.prepare())
        identity = candidate["manifest"]["identity"]
        source = identity["source"]
        affine = Affine(*source["transform"])
        affine = Affine(affine.a, 0., affine.c - .00001, 0., affine.e, affine.f)
        source["transform"] = list(affine)[:6]
        rows, cols = source["shape_zx"]
        source["extent"] = [affine.c, affine.f + rows * affine.e, affine.c + cols * affine.a, affine.f]
        header = SimpleNamespace(transform=affine, width=cols, height=rows)
        bounds = transform_bounds("EPSG:32651", source["crs"], *identity["grid"]["target_bounds_en_m"], densify_pts=41)
        window = _window(bounds, header)
        core_window = _window(self.bbox, header)
        source["read_window_col_row_width_height"] = list(window.flatten())
        source["read_transform"] = list(affine * Affine.translation(window.col_off, window.row_off))[:6]
        source["read_shape_zx"] = [int(window.height), int(window.width)]
        source["read_cells"] = int(window.height * window.width)
        source["requested_window_shape_zx"] = [int(core_window.height), int(core_window.width)]
        self.rehash(candidate)
        path = self.write_package(candidate)
        load_dem_candidate(path, verify_source=False)
        with self.assertRaisesRegex(ValueError, "provenance replay mismatch"):
            load_dem_candidate(path)

    def test_rehashed_nodata_to_zero_cannot_forge_coverage(self):
        values = np.full((160, 160), 10., np.float32)
        values[50:60, 50:60] = -32768.
        self.write_source(values)
        candidate = copy.deepcopy(self.prepare())
        arrays = candidate["arrays"]
        arrays["height_m"][arrays["unknown_mask"]] = 0.
        arrays["valid_mask"][:] = True
        arrays["unknown_mask"][:] = False
        from terrain_pipeline.td_source import _summary
        candidate["manifest"]["summary"] = _summary(arrays)
        self.rehash(candidate)
        forged = self.write_package(candidate)
        load_dem_candidate(forged, verify_source=False)
        with self.assertRaisesRegex(ValueError, "replay mismatch"):
            load_dem_candidate(forged)
        with self.assertRaises(ValueError):
            save_dem_candidate(candidate, self.root / "forged.npz")
        with self.assertRaises(ValueError):
            route_dem_candidate(candidate, np.ones(arrays["height_m"].shape, bool))


if __name__ == "__main__":
    unittest.main()
