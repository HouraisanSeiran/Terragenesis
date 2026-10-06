"""Exercise pinned saved geometry in the actual local review frontend."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765/")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    errors, cases = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width":1440,"height":1000}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_function("window.savedSurface !== undefined")
        page.wait_for_function("!window.savedSurface.isLoading() && window.savedSurface.reviewRecord()?.caseId === 'amr-tailwater-rise-root4'")
        page.click("#view3d")
        page.wait_for_timeout(1500)
        page.check('[data-layer="domains"]')
        page.select_option("#savedPartition","mixed")
        canvas = page.locator("#savedSurface")
        for label in ("desktop", "mobile"):
            if label == "mobile":
                page.set_viewport_size({"width":390,"height":844})
                canvas.scroll_into_view_if_needed()
                page.wait_for_timeout(800)
            path = args.output / f"amr-3d-{label}.png"
            canvas.screenshot(path=str(path))
            pixels = np.asarray(Image.open(path).convert("RGB"))
            colors, counts = np.unique(pixels.reshape(-1,3), axis=0, return_counts=True)
            varied = int(pixels.shape[0]*pixels.shape[1]-counts.max())
            if varied < pixels.shape[0]*pixels.shape[1]*.03 or len(colors) < 30:
                raise AssertionError("blank or incorrectly framed saved WebGL canvas")
            cases.append(dict(viewport=label,distinct_colors=len(colors),non_background_pixels=varied))
        page.set_viewport_size({"width":1440,"height":1000})
        page.locator("#savedSurface").scroll_into_view_if_needed()
        before = page.locator("#savedSurface").screenshot()
        box = canvas.bounding_box()
        page.mouse.move(box["x"]+box["width"]*.5,box["y"]+box["height"]*.5)
        page.mouse.down()
        page.mouse.move(box["x"]+box["width"]*.65,box["y"]+box["height"]*.55,steps=8)
        page.mouse.up()
        if before == page.locator("#savedSurface").screenshot():
            raise AssertionError("orbit camera did not move rendered geometry")
        before_zoom = page.evaluate("window.savedSurface.reviewRecord().camera.position")
        page.mouse.wheel(0,-180)
        page.wait_for_timeout(400)
        if before_zoom == page.evaluate("window.savedSurface.reviewRecord().camera.position"):
            raise AssertionError("saved orbit zoom was blocked")
        page.locator("#savedSurface").click()
        if page.evaluate("window.savedSurface.reviewRecord().selection") is None:
            raise AssertionError("saved 3D geometry could not be selected")
        page.click("#play")
        page.wait_for_function("window.savedSurface.reviewRecord()?.timeSeconds >= 30")
        page.click("#play")
        if page.evaluate("window.surfaceReview.isPlaying()"):
            raise AssertionError("saved time playback did not pause")
        page.evaluate("window.savedSurface.setTime(4)")
        page.wait_for_function("window.savedSurface.reviewRecord()?.timeSeconds === 120")
        page.screenshot(path=str(args.output / "amr-last-desktop.png"))
        page.click("#view2d")
        page.select_option("#savedField", "leaf")
        page.locator("#savedMap").click(position={"x":200,"y":200})
        with page.expect_download() as download:
            page.click("#exportReview")
        export_path = args.output / "review.json"
        download.value.save_as(str(export_path))
        record = json.loads(export_path.read_text(encoding="utf-8"))
        if record["timeSeconds"] != 120 or record["source"]["manifest_sha256"] != "170060df9b7e2ef08fed9cc1c54f586731c3644639ea0fb94444c007fc86e078":
            raise AssertionError("review export contains stale source or time")
        for package, scenario, time_s in (("native","eastward",86400),("uniform","tailwater-rise-4m",120)):
            page.select_option("#savedPackage",package)
            page.wait_for_function("([p])=>!window.savedSurface.isLoading() && window.savedSurface.reviewRecord()?.caseId.startsWith(p+'-')",arg=[package])
            page.select_option("#savedScenario",scenario)
            page.wait_for_function("([p,s])=>!window.savedSurface.isLoading() && window.savedSurface.reviewRecord()?.caseId === p+'-'+s",arg=[package,scenario])
            await_index = 24 if package == "native" else 4
            page.evaluate("index=>window.savedSurface.setTime(index)",await_index)
            page.wait_for_function("time=>window.savedSurface.reviewRecord()?.timeSeconds === time",arg=time_s)
            page.select_option("#savedField","bed")
            page.locator("#savedMap").screenshot(path=str(args.output / f"{package}-2d.png"))
            page.click("#view3d")
            page.locator("#savedSurface").screenshot(path=str(args.output / f"{package}-3d.png"))
            page.click("#view2d")
        page.click('[data-category="vdm"]')
        page.wait_for_function("document.querySelector('#vdmStatus').textContent.includes('已读取固定形态')")
        if not page.locator("#savedSurface").is_hidden() or page.locator("#surface").is_hidden():
            raise AssertionError("saved workspace overlay survived workspace change")
        if errors:
            raise AssertionError(errors)
        browser.close()
    (args.output / "report.json").write_text(json.dumps(dict(schema="saved-surface-frontend-review-v1",status="passed",
        url=args.url,cases=cases,page_errors=errors,orbit_interaction_verified=True,
        actual_source_export_verified=True,three_dimensional_selection_verified=True,
        zoom_interaction_verified=True,time_playback_verified=True,solver_advanced=False),indent=2),encoding="utf-8")
    print(json.dumps(dict(status="passed",output=str(args.output),cases=cases)))


if __name__ == "__main__":
    main()
