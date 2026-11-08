import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from terrain_pipeline import geography_preparation_inventory as inventory


class GeographyInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_candidates_are_not_certification(self):
        data = self.root / "01-完整流域样本" / "data"
        data.mkdir(parents=True)
        (data / "funxi_srtm30m_grid.csv").write_text("lat,lon,z\n1,2,3\n")
        (data / "funxi_control_section.json").write_text('{"authority":"official","control_section":{"upstream_area_km2":184.02}}')
        (data / "srtm_61_07.hdr").write_text("GCS_WGS_84")
        (self.root / "self-certified.md").write_text("authoritative real basin")
        manifest = inventory.prepare(self.root)
        records = {file["path"]: file for file in manifest["files"]}
        self.assertEqual(records["self-certified.md"]["source_class"], "unreviewed")
        self.assertEqual(records["01-完整流域样本/data/funxi_control_section.json"]["source_class"], "area_selected_candidate")
        self.assertEqual(records["01-完整流域样本/data/funxi_srtm30m_grid.csv"]["source_class"], "dem_derived_candidate")
        self.assertEqual(records["01-完整流域样本/data/funxi_control_section.json"]["metadata"]["reported_control_upstream_area_km2"], 184.02)
        self.assertTrue(all(not item["certified"] for item in manifest["requirements"].values()))
        self.assertFalse(manifest["readiness"]["ready"])
        self.assertEqual(records["self-certified.md"]["sha256"], hashlib.sha256(b"authoritative real basin").hexdigest())

    def test_static_load_and_corruption(self):
        source = self.root / "source"
        source.mkdir()
        (source / "file.bin").write_bytes(b"first")
        first = inventory.prepare(source)
        output = inventory.save(first, self.root / "inventory.json")
        (source / "file.bin").write_bytes(b"changed")
        with patch.object(inventory, "prepare", side_effect=AssertionError("load scanned sources")):
            self.assertEqual(inventory.load(output), first)
        self.assertNotEqual(first["identity"], inventory.prepare(source)["identity"])
        output.write_text("{broken")
        with self.assertRaises(inventory.InventoryError):
            inventory.load(output)

    def test_path_escape_and_tampering(self):
        (self.root / "a").write_text("x")
        for bad_path in ("../escape", "/absolute", "C:/outside", "a\\b", "a//b", "./a", "a/../b"):
            manifest = inventory.prepare(self.root)
            manifest["files"][0]["path"] = bad_path
            manifest["identity"] = inventory._digest({key: value for key, value in manifest.items() if key != "identity"})
            with self.subTest(path=bad_path), self.assertRaises(inventory.InventoryError):
                inventory.validate(manifest)
        manifest = inventory.prepare(self.root)
        manifest["readiness"]["ready"] = True
        manifest["identity"] = inventory._digest({key: value for key, value in manifest.items() if key != "identity"})
        with self.assertRaises(inventory.InventoryError):
            inventory.validate(manifest)

    def test_bad_json_and_bom_csv(self):
        data = self.root / "01-完整流域样本" / "data"
        data.mkdir(parents=True)
        (data / "funxi_basin_report.json").write_text('{"a":1,"a":2}')
        (data / "funxi_control_section.json").write_text('{"value":NaN}')
        (data / "funxi_climate_runoff.csv").write_text("year,month\n2015,01\n", encoding="utf-8-sig")
        records = {file["path"]: file for file in inventory.prepare(self.root)["files"]}
        self.assertEqual(records["01-完整流域样本/data/funxi_basin_report.json"]["metadata"]["status"], "parse_failed")
        self.assertEqual(records["01-完整流域样本/data/funxi_control_section.json"]["metadata"]["status"], "parse_failed")
        self.assertEqual(records["01-完整流域样本/data/funxi_climate_runoff.csv"]["metadata"]["columns"], ["year", "month"])
        bounded = inventory.prepare(self.root, inventory.InventoryLimits(max_metadata_bytes=2))
        self.assertTrue(all(file["metadata"]["status"] == "skipped_metadata_limit" for file in bounded["files"]))

    def test_invalid_manifest_json_and_metadata(self):
        (self.root / "a").write_text("x")
        manifest = inventory.prepare(self.root)
        destination = inventory.save(manifest, self.root / "manifest.json")
        for encoded in ('{"a":1,"a":2}', '{"a":NaN}'):
            destination.write_text(encoded)
            with self.assertRaises(inventory.InventoryError):
                inventory.load(destination)
        manifest["files"][0]["metadata"] = {"status": "parsed_unverified", "columns": [1]}
        manifest["identity"] = inventory._digest({key: value for key, value in manifest.items() if key != "identity"})
        with self.assertRaises(inventory.InventoryError):
            inventory.validate(manifest)

    def test_numeric_certification_flags_rejected_after_rehash(self):
        (self.root / "a").write_text("x")
        for field in ("ready", "real_basin_certified", "outlet_certified"):
            manifest = inventory.prepare(self.root)
            manifest["readiness"][field] = 0
            manifest["identity"] = inventory._digest({key: value for key, value in manifest.items() if key != "identity"})
            with self.subTest(field=field), self.assertRaises(inventory.InventoryError):
                inventory.validate(manifest)
        manifest = inventory.prepare(self.root)
        manifest["requirements"]["vertical_datum"]["certified"] = 0
        manifest["identity"] = inventory._digest({key: value for key, value in manifest.items() if key != "identity"})
        with self.assertRaises(inventory.InventoryError):
            inventory.validate(manifest)

    def test_metadata_status_combination_rejected_after_rehash(self):
        (self.root / "a").write_text("x")
        for metadata in ({"status": "skipped_metadata_limit", "columns": ["year"]},
                         {"status": "parse_failed"},
                         {"status": "parsed_unverified", "reason": "ValueError"},
                         {"status": "parsed_unverified", "columns": ["year"]},
                         {"status": "parsed_unverified", "declares_wgs84_horizontal": False}):
            manifest = inventory.prepare(self.root)
            manifest["files"][0]["metadata"] = metadata
            manifest["identity"] = inventory._digest({key: value for key, value in manifest.items() if key != "identity"})
            with self.subTest(metadata=metadata), self.assertRaises(inventory.InventoryError):
                inventory.validate(manifest)

    def test_limits_and_failed_save(self):
        (self.root / "a").write_bytes(b"abc")
        with self.assertRaisesRegex(inventory.InventoryError, "resource limit"):
            inventory.prepare(self.root, inventory.InventoryLimits(max_total_bytes=2))
        for name in ("empty1", "empty2"):
            (self.root / name).mkdir()
        with self.assertRaisesRegex(inventory.InventoryError, "directory limit"):
            inventory.prepare(self.root, inventory.InventoryLimits(max_directories=2))
        with self.assertRaisesRegex(inventory.InventoryError, "entry limit"):
            inventory.prepare(self.root, inventory.InventoryLimits(max_entries=2))
        manifest = inventory.prepare(self.root)
        target = self.root / "saved.json"
        target.write_text("original")
        manifest["identity"] = "0" * 64
        with self.assertRaises(inventory.InventoryError):
            inventory.save(manifest, target)
        self.assertEqual(target.read_text(), "original")

    def test_link_not_followed(self):
        outside = self.root.parent / "outside-inventory.txt"
        outside.write_text("external")
        self.addCleanup(outside.unlink)
        try:
            (self.root / "link").symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation unavailable")
        manifest = inventory.prepare(self.root)
        self.assertEqual(manifest["file_count"], 0)
        self.assertEqual(manifest["diagnostics"][0]["status"], "skipped_link_or_reparse")
        with self.assertRaises(inventory.InventoryError):
            inventory.prepare(self.root / "link")

    def test_ancestor_reparse_rejected_without_symlink_permission(self):
        ancestor = self.root.parent
        original_lstat = Path.lstat

        def mock_lstat(path):
            info = original_lstat(path)
            if path == ancestor:
                return SimpleNamespace(st_mode=info.st_mode,
                                       st_file_attributes=inventory.stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return info

        with patch.object(Path, "lstat", mock_lstat):
            with self.assertRaisesRegex(inventory.InventoryError, "link or reparse point"):
                inventory.prepare(self.root)

    def test_metadata_second_read_change(self):
        data = self.root / "01-完整流域样本" / "data"
        data.mkdir(parents=True)
        source = data / "funxi_basin_report.json"
        source.write_text("{}")
        original = inventory._extract

        def changing_extract(path, relative, limit):
            result = original(path, relative, limit)
            path.write_text('{"changed":true}')
            return result

        with patch.object(inventory, "_extract", side_effect=changing_extract):
            with self.assertRaisesRegex(inventory.InventoryError, "source changed"):
                inventory.prepare(self.root)


if __name__ == "__main__":
    unittest.main()
