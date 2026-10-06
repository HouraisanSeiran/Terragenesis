import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_native_channel_surface_review import export_surface_review


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "verification/td-native-channel-surface/A-prototype-20261002T172124835240Z/report.json"


class SurfaceReviewTests(unittest.TestCase):
    def test_real_browser_render_and_controls(self):
        report_sha = file_sha256(REPORT)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.html"
            export_surface_review(REPORT, expected_report_sha256=report_sha, output_path=output)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
                page = browser.new_page(viewport={"width": 1200, "height": 800})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(output.as_uri())
                self.assertEqual(errors, [])
                self.assertTrue(page.locator("#candidate").get_attribute("class") == "active")
                self.assertTrue(page.locator("#view").evaluate("canvas => canvas.width > 0 && !!canvas.getContext('webgl2')"))
                page.locator("#native").click()
                self.assertEqual(page.locator("#native").get_attribute("class"), "active")
                page.locator("#cut").click()
                self.assertIn("on", page.locator("#cut").inner_text())
                page.locator("#view").hover()
                page.mouse.wheel(0, 300)
                page.locator("#reset").click()
                page.locator("#candidate").click()
                self.assertEqual(errors, [])
                browser.close()

    def test_actual_cold_export_and_pins(self):
        report_sha = file_sha256(REPORT)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.html"
            with patch("terrain_pipeline.td_native_channel_surface.build_channel_surface", side_effect=AssertionError("generated")), \
                    patch("terrain_pipeline.td_native_channel_tiles.build_channel_tile", side_effect=AssertionError("generated")):
                pins = export_surface_review(REPORT, expected_report_sha256=report_sha, output_path=output)
            html = output.read_text(encoding="utf-8")
            self.assertIn('"count":65025', html)
            self.assertIn('"triangle_count":129032', html)
            self.assertIn(pins["surface"]["expected_sha256"], html)
            self.assertIn("Original sampled bed", html)
            self.assertIn("Cut coloring", html)
            self.assertIn("no water surface", html)
            with self.assertRaises(FileExistsError):
                export_surface_review(REPORT, expected_report_sha256=report_sha, output_path=output)

    def test_bad_report_and_source_pins_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.html"
            with self.assertRaisesRegex(ValueError, "report external SHA"):
                export_surface_review(REPORT, expected_report_sha256="0" * 64, output_path=output)
            report = json.loads(REPORT.read_text(encoding="utf-8"))
            report["surface"]["expected_sha256"] = "0" * 64
            forged = Path(directory) / "report.json"
            forged.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(ValueError):
                export_surface_review(forged, expected_report_sha256=file_sha256(forged), output_path=output)
            report = json.loads(REPORT.read_text(encoding="utf-8"))
            report["tiles"][0]["expected_sha256"] = "0" * 64
            forged.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source file SHA"):
                export_surface_review(forged, expected_report_sha256=file_sha256(forged), output_path=output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
