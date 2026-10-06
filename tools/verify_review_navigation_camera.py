"""Check three-category navigation and matching orbit gestures in both viewers."""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright


def drag(page, selector, dx, dy, button="left"):
    box = page.locator(selector).bounding_box()
    start_x = box["x"]+box["width"]*.5
    start_y = box["y"]+box["height"]*.3
    page.mouse.move(start_x,start_y)
    page.mouse.down(button=button)
    page.mouse.move(start_x+dx,start_y+dy,steps=15)
    page.mouse.up(button=button)


def orbit_angles(record):
    position = record["camera"]["position"]
    target = record["camera"]["target"]
    offset = [first-second for first,second in zip(position,target)]
    return math.atan2(offset[0],offset[2]), math.atan2(offset[1],math.hypot(offset[0],offset[2]))


def screenshot(canvas, path):
    canvas.screenshot(path=str(path))
    pixels = np.asarray(Image.open(path).convert("RGB"))
    colors, counts = np.unique(pixels.reshape(-1,3),axis=0,return_counts=True)
    non_background = int(pixels.shape[0]*pixels.shape[1]-counts.max())
    if len(colors)<30 or non_background<pixels.shape[0]*pixels.shape[1]*.02:
        raise AssertionError("blank or incorrectly framed terrain canvas")
    return dict(path=path.name,distinct_colors=len(colors),non_background_pixels=non_background)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",default="http://127.0.0.1:8765/?workspace=saved")
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    errors, checks, images = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge",headless=True)
        page = browser.new_page(viewport={"width":1440,"height":1000},device_scale_factor=1)
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(args.url,wait_until="networkidle")
        page.wait_for_function("window.savedSurface?.reviewRecord() && !window.savedSurface.isLoading()")
        if page.locator("[data-category]").all_text_contents()!=["地形输入","VDM 算法","河网算法"]:
            raise AssertionError("top-level algorithm categories changed")
        if page.input_value("#reviewProject")!="saved":
            raise AssertionError("river category does not default to saved AMR")
        page.click("#view3d")
        page.wait_for_timeout(500)
        read = lambda:page.evaluate("window.surfaceReview.reviewRecord()")
        before = orbit_angles(read())
        drag(page,"#savedSurface",70,0)
        after = orbit_angles(read())
        if after[0]<=before[0] or abs(after[1]-before[1])>1e-7:
            raise AssertionError("saved horizontal orbit direction or axis incorrect")
        page.click("#reset")
        before = orbit_angles(read())
        drag(page,"#savedSurface",0,70)
        after = orbit_angles(read())
        if after[1]>=before[1] or abs(after[0]-before[0])>1e-7:
            raise AssertionError("saved vertical orbit direction or axis incorrect")
        before = read()
        drag(page,"#savedSurface",40,35,button="right")
        after = read()
        if before["camera"]["target"]==after["camera"]["target"] or not np.allclose(orbit_angles(before),orbit_angles(after),atol=1e-7):
            raise AssertionError("saved right drag did not pan without rotating")
        page.click("#reset")
        drag(page,"#savedSurface",0,160)
        if orbit_angles(read())[1]>=0:
            raise AssertionError("saved orbit cannot inspect underside")
        images.append(screenshot(page.locator("#savedSurface"),args.output / "amr-underside-desktop.png"))
        checks.append("saved right/down axis signs, pan without rotation, underside orbit")
        page.click("#reset")
        page.select_option("#reviewProject","mosaic")
        page.wait_for_function("!window.savedSurface.isLoading() && document.querySelector('#savedPartition').value === 'mixed' && window.savedSurface.reviewRecord()")
        if page.input_value("#savedField")!="leaf" or read()["workspace"]!="mosaic" or read()["category"]!="rivers":
            raise AssertionError("shared-boundary project not scoped to rivers")
        with page.expect_download() as downloaded:
            page.click("#exportReview")
        exported_path = args.output / "mosaic-review.json"
        downloaded.value.save_as(str(exported_path))
        exported = json.loads(exported_path.read_text(encoding="utf-8"))
        if exported["workspace"]!="mosaic" or exported["category"]!="rivers" or exported["source"]["manifest_sha256"]!="170060df9b7e2ef08fed9cc1c54f586731c3644639ea0fb94444c007fc86e078":
            raise AssertionError("mosaic export lost category or original source identity")
        page.set_viewport_size({"width":390,"height":844})
        page.locator("#savedSurface").scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        images.append(screenshot(page.locator("#savedSurface"),args.output / "mosaic-mobile.png"))
        page.screenshot(path=str(args.output / "navigation-mobile.png"),full_page=True)
        if page.evaluate("document.documentElement.scrollWidth > innerWidth+1"):
            raise AssertionError("mobile navigation has horizontal overflow")
        page.set_viewport_size({"width":1440,"height":1000})
        page.click('[data-category="terrain"]')
        page.wait_for_function("window.surfaceRenderer.state.case?.kind === 'legacy'")
        if read()["terrainVariant"]!="raw" or len(page.locator("#caseSelect option").all())!=3:
            raise AssertionError("base terrain contains river cases or starts with processed terrain")
        if any(not value.startswith("legacy:") for value in page.locator("#caseSelect option").evaluate_all("options=>options.map(option=>option.value)")):
            raise AssertionError("base terrain selector contains unrelated cases")
        page.select_option("#terrainVariant","processed")
        page.wait_for_function("window.surfaceRenderer.state.case?.legacyMode === 'processed'")
        if len(read()["source"]["sha256"])!=64 or read()["source"]["scope"]!="saved_preview_only":
            raise AssertionError("terrain input export lacks actual preview artifact identity")
        page.click("#view3d")
        images.append(screenshot(page.locator("#surface"),args.output / "td-terrain-desktop.png"))
        before = read()["camera"]
        drag(page,"#surface",70,0)
        after = read()["camera"]
        if after["yaw"]<=before["yaw"] or after["pitch"]!=before["pitch"]:
            raise AssertionError("legacy orbit does not match saved horizontal direction")
        drag(page,"#surface",0,70)
        if read()["camera"]["pitch"]>=after["pitch"]:
            raise AssertionError("legacy orbit does not match saved vertical direction")
        before = read()["camera"]
        drag(page,"#surface",35,25,button="right")
        after = read()["camera"]
        if after["yaw"]!=before["yaw"] or after["pitch"]!=before["pitch"] or after["panX"]==before["panX"]:
            raise AssertionError("legacy right pan changes orbit angles")
        page.select_option("#reviewProject","dem")
        page.wait_for_function("window.surfaceRenderer.state.case?.kind === 'dem'")
        if len(page.locator("#caseSelect option").all())!=1 or read()["category"]!="terrain":
            raise AssertionError("DEM candidate not isolated in terrain diagnostics")
        page.click('[data-category="vdm"]')
        page.wait_for_function("window.surfaceRenderer.state.case?.caseId.startsWith('vdm-')")
        if read()["source"]["sha256"]!=read()["source"]["dependencies"]["vdm"]["sha256"] or not read()["source"]["identity"]:
            raise AssertionError("VDM export replaces source identity with an unrelated digest")
        page.click("#view3d")
        page.click("#reset")
        vectors = page.locator('[data-layer="displacement"]')
        if vectors.is_checked() or read()["layers"]["displacement"]:
            raise AssertionError("VDM displacement overlay should default to hidden")
        source_before = read()["source"]
        images.append(screenshot(page.locator("#surface"),args.output / "vdm-vectors-hidden.png"))
        hidden_pixels = np.asarray(Image.open(args.output / "vdm-vectors-hidden.png").convert("RGB"))
        vectors.check()
        if not read()["layers"]["displacement"] or read()["source"]!=source_before:
            raise AssertionError("VDM overlay toggle changes source or fails to export layer state")
        images.append(screenshot(page.locator("#surface"),args.output / "vdm-vectors-visible.png"))
        shown_pixels = np.asarray(Image.open(args.output / "vdm-vectors-visible.png").convert("RGB"))
        if np.count_nonzero(np.any(shown_pixels!=hidden_pixels,axis=2))<100:
            raise AssertionError("VDM displacement checkbox does not render overlay")
        vectors.uncheck()
        page.locator("#surface").screenshot(path=str(args.output / "vdm-vectors-restored.png"))
        restored_pixels = np.asarray(Image.open(args.output / "vdm-vectors-restored.png").convert("RGB"))
        if not np.array_equal(restored_pixels,hidden_pixels) or read()["layers"]["displacement"]:
            raise AssertionError("VDM overlay cannot restore uncluttered geometry")
        checks.append("VDM displacement vectors hidden by default, explicit toggle changes pixels only and exports layer state")
        drag(page,"#surface",0,160)
        if read()["camera"]["pitch"]>=0:
            raise AssertionError("VDM cannot inspect overhang underside")
        images.append(screenshot(page.locator("#surface"),args.output / "vdm-underside-desktop.png"))
        page.select_option("#reviewProject","fault")
        if not page.locator("#faultControls").is_visible() or not page.locator("#view3d").is_disabled():
            raise AssertionError("fault draft has fake render controls")
        if read()["status"]!="backend-pending" or read()["geometry_generated"] or "slip_m" not in read()["draft"]:
            raise AssertionError("fault draft export misrepresents geometry or pending status")
        page.click('[data-category="rivers"]')
        page.select_option("#reviewProject","surface")
        page.wait_for_function("window.surfaceRenderer.state.case?.caseId === 'two-domain-mosaic'")
        if len(page.locator("#caseSelect option").all())!=12 or any("DEM" in label or "dem-candidate" in label for label in page.locator("#caseSelect option").all_text_contents()):
            raise AssertionError("river historical selector includes base terrain")
        if read()["source"]["sha256"]!=read()["evidence"]["source"]["sha256"] or read()["source"]["render_artifact"]["sha256"]==read()["source"]["sha256"]:
            raise AssertionError("historical export mixes source NPZ and render JSON identities")
        page.select_option("#reviewProject","basin")
        if not page.locator("#basinControls").is_visible() or page.locator("#stats").inner_text():
            raise AssertionError("basin shows stale terrain statistics")
        if read()["status"]!="diagnostic_candidate" or len(read()["source"]["sha256"])!=64:
            raise AssertionError("basin review does not export the actual diagnostic source")
        page.select_option("#reviewProject","td")
        page.wait_for_function("window.surfaceRenderer.state.case?.kind === 'td'")
        if not page.locator("#view3d").is_disabled():
            raise AssertionError("2D-only hourly display falsely presents 3D capability")
        if read()["source"]["sha256"]!=read()["source"]["dependencies"]["storage"]["sha256"] or read()["timeSeconds"]!=0:
            raise AssertionError("TD export loses current storage source or time")
        page.click('[data-category="vdm"]')
        page.select_option("#reviewProject","vdm")
        page.wait_for_function("window.surfaceRenderer.state.case?.kind==='mesh' && !document.querySelector('#exportReview').disabled")
        intercepted=[]
        page.route("**/api/vdm/preview",lambda route:intercepted.append(route))
        page.click("#vdmPreview")
        page.wait_for_timeout(100)
        if not intercepted or not page.locator("#exportReview").is_disabled():
            raise AssertionError("loading VDM preview still permits review export")
        page.click('[data-category="rivers"]')
        page.select_option("#reviewProject","saved")
        page.wait_for_function("!window.savedSurface.isLoading() && window.savedSurface.reviewRecord()")
        page.click("#play")
        intercepted[0].fulfill(status=400,content_type="application/json",body='{"error":"delayed obsolete preview failure"}')
        page.wait_for_timeout(300)
        if page.locator("#error").is_visible() or not page.evaluate("window.surfaceReview.isPlaying()"):
            raise AssertionError("stale VDM failure altered current river page")
        page.click("#play")
        page.unroute("**/api/vdm/preview")
        checks.append("source SHA/identity distinction, pending draft, diagnostic export, export disabled while loading, stale preview failure ignored")
        checks.append("all nine projects, isolated cases, raw/processed switch, no stale geometry on draft/evidence views")
        if errors:
            raise AssertionError(errors)
        browser.close()
    report = dict(schema="review-navigation-camera-verification-v1",status="passed",url=args.url,
        categories=["terrain","vdm","rivers"],checks=checks,images=images,page_errors=errors,solver_advanced=False)
    (args.output / "report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(dict(status="passed",output=str(args.output),checks=checks)))


if __name__ == "__main__":
    main()
