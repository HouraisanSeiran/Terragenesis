import json
from pathlib import Path
import tempfile
import unittest

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_native_water_surface import build_water_surface, save_water_surface
from tests.test_td_native_channel_geometry import fixture
from tools.plot_td_native_water_surface import plot, read_record


class NativeWaterPlotTests(unittest.TestCase):
    def _snapshot(self, directory):
        _, page = fixture()
        source = Path(directory) / "source.npz"
        obj = Path(directory) / "surface.obj"
        publish_bytes(source, b"synthetic source pin")
        publish_bytes(obj, b"synthetic OBJ pin")
        surface = build_water_surface(page, source_sha256=file_sha256(source), wet_threshold_m=.01)
        path = Path(directory) / "surface.npz"
        save_water_surface(path, surface)
        report = dict(schema="td-native-water-surface-prototype-v1",
                      source_page=dict(path=str(source), expected_sha256=file_sha256(source),
                                       expected_identity=page["identity_sha256"]),
                      surface=dict(path=str(path), expected_sha256=file_sha256(path),
                                   expected_identity=surface["identity_sha256"]),
                      obj=dict(path=str(obj), expected_sha256=file_sha256(obj)),
                      metadata=surface["metadata"], vertex_count=len(surface["arrays"]["vertex_cell_ids"]),
                      triangle_count=len(surface["arrays"]["triangles"]))
        return report, surface

    def test_saved_source_plot_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            report, surface = self._snapshot(directory)
            report_path = Path(directory) / "report.json"
            publish_bytes(report_path, json.dumps(report).encode("utf-8"))
            output = Path(directory) / "figure"
            result = plot(report_path, file_sha256(report_path), output)
            self.assertTrue((output / "native-water-coverage.png").is_file())
            self.assertEqual(result["grid_water_volume_m3"], surface["metadata"]["grid_water_volume_m3"])
            self.assertEqual(result["undrawn_wet_cell_count"], surface["metadata"]["undrawn_wet_cell_count"])
            with self.assertRaises(FileExistsError):
                plot(report_path, file_sha256(report_path), output)

    def test_wrong_report_pin_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.json"
            publish_bytes(report_path, b"{}")
            with self.assertRaisesRegex(ValueError, "external SHA"):
                read_record(report_path, "0" * 64)
            with self.assertRaises(ValueError):
                read_record(report_path, file_sha256(report_path))

    def test_wrong_saved_source_pin_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            report, _ = self._snapshot(directory)
            report["surface"]["expected_sha256"] = "0" * 64
            report_path = Path(directory) / "report.json"
            publish_bytes(report_path, json.dumps(report).encode("utf-8"))
            with self.assertRaisesRegex(ValueError, "source file pin"):
                read_record(report_path, file_sha256(report_path))


if __name__ == "__main__":
    unittest.main()
