"""Inspect actual saved fault geometry, orbit interaction and explicit preview."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def screenshot(canvas, path):
    canvas.screenshot(path=str(path))
    pixels = np.asarray(Image.open(path).convert("RGB"))
    colors, counts = np.unique(pixels.reshape(-1, 3), axis=0, return_counts=True)
    varied = int(pixels.shape[0] * pixels.shape[1] - counts.max())
    if len(colors) < 30 or varied < pixels.shape[0] * pixels.shape[1] * .02:
        raise AssertionError("fault canvas is blank or incorrectly framed")
    return {"path": path.name, "distinct_colors": len(colors), "non_background_pixels": varied}


def ready(page):
    page.wait_for_function("window.faultSurface?.reviewRecord() && !window.faultSurface.isLoading()", timeout=120000)


def read(page):
    return page.evaluate("window.faultSurface.reviewRecord()")


def drag(page, canvas, dx, dy):
    box = canvas.bounding_box()
    start_x = box["x"] + box["width"] * .5
    start_y = box["y"] + box["height"] * .35
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x + dx, start_y + dy, steps=12)
    page.mouse.up()


def verify(url, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    errors, images = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width":1440, "height":1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="networkidle")
        ready(page)
        if page.locator("#reviewProject").input_value() != "fault":
            raise AssertionError("fault URL does not select the fault workspace")
        page.click("#view3d")
        canvas = page.locator("#faultSurface")
        canvas.wait_for(state="visible")
        page.wait_for_timeout(500)
        saved = read(page)
        if saved["identity"] != "fc2b93362b2b454363a7ca10ae8f1063d536678fded9ad9e72c03afe5c6d9a89":
            raise AssertionError("browser is not consuming the final deformed-wall fault evidence")
        images.append(screenshot(canvas, output / "fault-desktop-after.png"))
        before_drag = canvas.screenshot()
        before_camera = read(page)["camera"]
        drag(page, canvas, 70, 35)
        page.wait_for_timeout(300)
        if canvas.screenshot() == before_drag or read(page)["camera"] == before_camera:
            raise AssertionError("fault orbit gesture did not move the scene")
        page.click("#reset")
        page.select_option("#faultMode", "before")
        page.wait_for_timeout(300)
        images.append(screenshot(canvas, output / "fault-desktop-before.png"))
        page.select_option("#faultMode", "compare")
        page.wait_for_timeout(300)
        images.append(screenshot(canvas, output / "fault-desktop-compare.png"))
        seam = page.locator('[data-layer="faultSeam"]')
        if seam.is_checked():
            raise AssertionError("fault seam overlay should default off")
        seam.check()
        page.wait_for_timeout(200)
        seam.uncheck()
        page.fill("#faultSlip", "-4")
        page.click("#faultPreview")
        page.wait_for_function("document.querySelector('#faultStatus').textContent.includes('预览')", timeout=120000)
        ready(page)
        page.wait_for_function("window.faultSurface.reviewRecord()?.identity !== " + json.dumps(saved["identity"]), timeout=120000)
        preview = read(page)
        images.append(screenshot(canvas, output / "fault-negative-slip.png"))
        page.fill("#faultSlip", "999")
        page.click("#faultPreview")
        page.wait_for_function("!window.faultSurface.isLoading()", timeout=120000)
        page.wait_for_function("document.querySelector('#faultStatus').textContent.includes('失败') || document.querySelector('#faultStatus').textContent.includes('范围')", timeout=120000)
        page.click("#faultSaved")
        ready(page)
        page.wait_for_function("window.faultSurface.reviewRecord()?.identity === " + json.dumps(saved["identity"]), timeout=120000)
        for size, label in (({"width":390, "height":844}, "mobile"), ({"width":1920, "height":1080}, "wide")):
            page.set_viewport_size(size)
            canvas.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            images.append(screenshot(canvas, output / f"fault-{label}.png"))
            if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                raise AssertionError("fault workspace overflows the viewport horizontally")
        page.set_viewport_size({"width":1440, "height":1000})
        page.click('[data-category="rivers"]')
        page.wait_for_function("window.savedSurface?.reviewRecord() && !window.savedSurface.isLoading()", timeout=120000)
        page.click('[data-category="vdm"]')
        page.select_option("#reviewProject", "fault")
        ready(page)
        if errors:
            raise AssertionError("browser errors: " + "; ".join(errors))
        report = {"schema":"fault-preview-browser-verification-v1", "status":"passed", "url":url,
                  "saved":saved, "negative_slip_preview":preview, "screenshots":images,
                  "checks":["actual geometry", "desktop/mobile/wide pixels", "orbit motion", "before/after/compare",
                            "optional seams", "negative slip", "invalid request rejected", "saved reload", "river navigation"],
                  "page_errors":errors, "hydraulic_ready":False, "publishable":False}
        browser.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/?workspace=fault")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.url, args.output)
    from terrain_pipeline.mountain_source_adapter import publish_bytes
    publish_bytes(args.output / "report.json", json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    print(json.dumps({"status":report["status"], "screenshots":len(report["screenshots"])}, ensure_ascii=False))
