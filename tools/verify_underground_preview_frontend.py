"""Focused Edge screenshots, canvas pixels, and underground view interactions."""

import argparse
from collections import Counter
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web-preview"))
SPEC = importlib.util.spec_from_file_location("underground_review_bridge", ROOT / "web-preview/bridge.py")
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


def canvas_pixels(path):
    with Image.open(path) as bitmap:
        pixels = list(bitmap.convert("RGB").getdata())
        counts = Counter(pixels)
        background, count = counts.most_common(1)[0]
        varied = sum(abs(red-background[0]) + abs(green-background[1]) + abs(blue-background[2]) > 35
                     for red, green, blue in pixels)
        if len(counts) < 25 or varied < len(pixels) * .008:
            raise AssertionError("underground canvas is blank or nearly blank")
        return {"colors": len(counts), "nonbackground_pixels": varied, "pixels": len(pixels)}


def audit(directory, *, saved_only=False):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    report = {"status": "running", "pageerrors": [], "checks": {}, "saved_only": saved_only}
    url = f"http://127.0.0.1:{server.server_port}/?workspace=underground"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 960}, device_scale_factor=1)
            page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("window.undergroundSurface?.reviewRecord() != null", timeout=30000)
            assert page.input_value("#reviewProject") == "underground"
            record = page.evaluate("undergroundSurface.reviewRecord()")
            report["initial"] = record
            canvas = page.locator("#undergroundSurface")
            canvas.screenshot(path=str(directory / "desktop-canvas.png"))
            report["checks"]["desktop_pixels"] = canvas_pixels(directory / "desktop-canvas.png")
            page.screenshot(path=str(directory / "desktop.png"), full_page=True)
            camera_before = page.evaluate("undergroundSurface.reviewRecord().camera")
            box = canvas.bounding_box()
            page.mouse.move(box["x"] + box["width"] * .45, box["y"] + box["height"] * .5)
            page.mouse.down()
            page.mouse.move(box["x"] + box["width"] * .65, box["y"] + box["height"] * .65, steps=12)
            page.mouse.up()
            camera_after = page.evaluate("undergroundSurface.reviewRecord().camera")
            assert camera_before != camera_after, "orbit drag did not move camera"
            report["checks"]["orbit_changes_camera"] = True
            canvas.screenshot(path=str(directory / "orbit-canvas.png"))
            report["checks"]["orbit_pixels"] = canvas_pixels(directory / "orbit-canvas.png")
            page.click("#view2d")
            canvas.screenshot(path=str(directory / "map-canvas.png"))
            report["checks"]["map_pixels"] = canvas_pixels(directory / "map-canvas.png")
            page.click("#view3d")
            page.click("#reset")
            layers = page.locator("#layers input[type=checkbox]")
            assert layers.count() >= 4
            first = layers.nth(0)
            was_checked = first.is_checked()
            first.set_checked(not was_checked)
            assert first.is_checked() != was_checked
            first.set_checked(was_checked)
            report["checks"]["layer_toggle"] = True
            assert record["layers"]["centerline"] is False
            page.locator("#undergroundStation").fill("8")
            page.locator("#undergroundStation").dispatch_event("input")
            selection = page.evaluate("undergroundSurface.reviewRecord().selection")
            assert selection["station_world_xyz_m"] == [value + origin for value, origin in
                    zip(selection["origin_local_xyz_m"], selection["crop_origin_xyz_m"])]
            page.check("#undergroundClip")
            canvas.screenshot(path=str(directory / "section-canvas.png"))
            report["checks"]["section_pixels"] = canvas_pixels(directory / "section-canvas.png")
            assert page.evaluate("undergroundSurface.reviewRecord().clip.enabled")
            page.uncheck("#undergroundClip")
            report["checks"]["station_world_coordinates_and_clipping"] = True
            rejected = page.request.post(f"http://127.0.0.1:{server.server_port}/api/underground/generate",
                                         data={"seed": True})
            assert rejected.status == 400
            report["checks"]["invalid_generation_rejected_without_recompute"] = True
            page.evaluate("surfaceReview.navigate('fault')")
            page.wait_for_function("window.faultSurface?.reviewRecord() != null")
            assert not page.evaluate("undergroundSurface.isActive()")
            page.evaluate("surfaceReview.navigate('underground')")
            page.wait_for_function("undergroundSurface.reviewRecord() != null")
            assert page.evaluate("undergroundSurface.reviewRecord().identity") == record["identity"]
            report["checks"]["navigation_isolated"] = True
            if not saved_only:
                page.locator("#undergroundSeed").fill("18")
                page.locator("#undergroundSeed").dispatch_event("input")
                assert page.evaluate("undergroundSurface.reviewRecord().parameters.seed") == 17
                page.click("#undergroundGenerate")
                page.wait_for_function("undergroundSurface.reviewRecord()?.parameters.seed === 18", timeout=70000)
                variant = page.evaluate("undergroundSurface.reviewRecord()")
                assert variant["identity"] != record["identity"]
                assert variant["metrics"] != record["metrics"]
                assert variant["capabilities"] == record["capabilities"]
                report["variant"] = variant
                canvas.screenshot(path=str(directory / "variant-canvas.png"))
                report["checks"]["variant_pixels"] = canvas_pixels(directory / "variant-canvas.png")
                page.click("#undergroundSaved")
                page.wait_for_function("undergroundSurface.reviewRecord()?.parameters.seed === 17")
                assert page.evaluate("undergroundSurface.reviewRecord().identity") == record["identity"]
                report["checks"]["explicit_variant_generation_and_immutable_saved_reload"] = True
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(200)
            canvas.scroll_into_view_if_needed()
            canvas.screenshot(path=str(directory / "mobile-canvas.png"))
            report["checks"]["mobile_pixels"] = canvas_pixels(directory / "mobile-canvas.png")
            page.screenshot(path=str(directory / "mobile.png"), full_page=True)
            overflow = page.evaluate("document.documentElement.scrollWidth > innerWidth + 1")
            assert not overflow, "mobile page overflows horizontally"
            assert not report["pageerrors"], report["pageerrors"]
            report.update(status="passed", url=url)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        (directory / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--saved-only", action="store_true")
    args = parser.parse_args()
    result = audit(args.output, saved_only=args.saved_only)
    print(json.dumps({"status": result["status"], "checks": result["checks"]}))


if __name__ == "__main__":
    main()
