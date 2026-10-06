"""Exercise a pinned offline saved-bed review in a real browser."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes


def audit(html_path, expected_sha256):
    from playwright.sync_api import sync_playwright
    html_path = Path(html_path).resolve(strict=True)
    if file_sha256(html_path) != expected_sha256 or html_path.stat().st_size > 16 * 1024 ** 2:
        raise ValueError("browser HTML pin/budget mismatch")
    errors, requests = [], []
    destination = ROOT / "verification/td-native-channel-surface" / ("independent-browser-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    destination.mkdir(parents=True, exist_ok=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True,
                                            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 950})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request.url))
            page.goto(html_path.as_uri(), wait_until="load")
            if errors:
                raise ValueError("saved bed browser page errors: " + repr(errors))
            page.wait_for_function("typeof gl !== 'undefined' && gl !== null", timeout=10000)
            data = page.evaluate("({count:data.count,triangle_count:data.triangle_count,pins:data.pins,window:data.window})")
            if data["count"] != 65025 or data["triangle_count"] != 129032:
                raise ValueError("actual review prototype mesh counts differ")
            candidate = page.locator("#view").screenshot()
            page.click("#native")
            native = page.locator("#view").screenshot()
            if page.evaluate("nativeMode") != 1 or candidate == native:
                raise ValueError("native-bed toggle does not change rendered geometry")
            page.click("#candidate")
            page.click("#cut")
            colored = page.locator("#view").screenshot()
            if page.evaluate("cutMode") != 1 or candidate == colored:
                raise ValueError("incision-color toggle does not change rendered output")
            before = page.evaluate("({yaw,pitch,zoom})")
            canvas = page.locator("#view").bounding_box()
            page.mouse.move(canvas["x"] + 200, canvas["y"] + 200)
            page.mouse.down()
            page.mouse.move(canvas["x"] + 320, canvas["y"] + 240, steps=5)
            page.mouse.up()
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(100)
            if before == page.evaluate("({yaw,pitch,zoom})"):
                raise ValueError("bed camera drag/zoom has no effect")
            page.click("#reset")
            if before != page.evaluate("({yaw,pitch,zoom})"):
                raise ValueError("bed camera reset differs from initial view")
            error_code = page.evaluate("gl.getError()")
            if error_code != 0 or errors or any(not request.startswith(("file:", "data:")) for request in requests):
                raise ValueError("browser GL/page error or external network request")
            page.screenshot(path=str(destination / "review.png"), full_page=True)
        finally:
            browser.close()
    if file_sha256(html_path) != expected_sha256:
        raise ValueError("browser HTML changed during audit")
    result = dict(schema="td-independent-channel-bed-browser-v1", accepted=True,
        html_record=dict(path=str(html_path), expected_sha256=expected_sha256), saved_mesh=data,
        native_toggle_visible=True, cut_toggle_visible=True, camera_drag_zoom_reset_passed=True,
        pageerrors=errors, external_requests=[], webgl_error_code=0,
        screenshot_record=dict(path=str(destination / "review.png"), expected_sha256=file_sha256(destination / "review.png")),
        water_generated=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False,
        scope="saved derived bed rendering and controls only; source lineage audited separately")
    publish_bytes(destination / "report.json", json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return dict(path=str(destination / "report.json"), expected_sha256=file_sha256(destination / "report.json"), screenshot=str(destination / "review.png"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--html-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.html, args.html_sha256)))


if __name__ == "__main__":
    main()
