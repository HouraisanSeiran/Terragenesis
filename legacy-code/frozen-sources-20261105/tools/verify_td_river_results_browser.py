"""Actual M8 saved-result downloads, bed layers and desktop/mobile WebGL audit."""

import argparse
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_surface_review_browser import BRIDGE

CASES = {"main", "bend", "sediment", "valley-0", "valley-1", "valley-4"}


def snapshot(locator, destination):
    locator.screenshot(path=str(destination))
    pixels = np.asarray(Image.open(destination).convert("RGB"))
    colors = len(np.unique(pixels.reshape(-1, 3)[::7], axis=0))
    assert colors > 20, {"canvas": str(destination), "colors": colors}
    return pixels, {"width": pixels.shape[1], "height": pixels.shape[0], "sampled_colors": colors,
                    "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}


def difference(first, second):
    assert first.shape == second.shape, "comparison canvas dimensions moved"
    count = int(np.count_nonzero(np.any(first != second, axis=-1)))
    assert count > 100, {"changed_pixels": count}
    return count


def download_record(page, directory, name):
    with page.expect_download() as event:
        page.evaluate("ui.exportReview.click()")
    path = directory / f"{name}-review-record.json"
    event.value.save_as(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    current = page.evaluate("()=>{const r=surfaceRenderer.state.case.results;return {identity:r.identity,source:r.source,metadata:r.metadata}}")
    assert record["identity"] == current["identity"]
    assert record["source"]["sha256"] == current["source"]["sha256"]
    assert record["source"]["path"] == current["source"]["path"]
    assert record["publishable"] is False
    assert record["status"] and record["metadata"]["algorithm"] == current["metadata"]["algorithm"]
    assert record["metadata"]["config"] == current["metadata"]["config"]
    assert len(record["release"]["identity_sha256"]) == 64
    active = json.loads((ROOT / "web-preview/data/river-product-v1/manifest.json").read_text(encoding="utf-8"))["product"]
    assert record["release"]["identity_sha256"] == active["identity_sha256"]
    assert record["release"]["case"]["id"] == record["caseId"]
    assert record["release"]["case"]["geometry"]["identity_sha256"] == record["identity"]
    assert record["release"]["publishable"] is False
    return record


def audit(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    server = ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    report = {"schema": "td-m8-saved-results-browser-audit-v1", "status": "running", "checks": {}, "pageerrors": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for name, viewport in (("desktop", {"width": 1600, "height": 1000}),
                                   ("mobile", {"width": 390, "height": 844})):
                context = browser.new_context(viewport=viewport, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="networkidle")
                page.wait_for_function("window.surfaceRenderer?.state.case?.results?.id==='valley-4'", timeout=90000)
                assert page.locator("#resultCase").input_value() == "valley-4"
                assert set(page.locator("#resultCase option").evaluate_all("a=>a.map(x=>x.value)")) == CASES
                checks = {"default_case": "valley-4", "case_ids": sorted(CASES)}
                layers = {}
                positions = []
                for layer in ("original", "bed", "cut"):
                    page.select_option("#resultLayer", layer)
                    page.evaluate("surfaceRenderer.render()")
                    pixels, measure = snapshot(page.locator("#surface"), directory / f"{name}-{layer}-2d.png")
                    layers[layer] = pixels
                    positions.append(page.locator("#surface").bounding_box())
                    checks[f"{layer}_canvas"] = measure
                checks["original_bed_changed_pixels"] = difference(layers["original"], layers["bed"])
                checks["bed_cut_changed_pixels"] = difference(layers["bed"], layers["cut"])
                checks["same_canvas_position"] = page.locator("#surface").bounding_box()
                assert positions[0] == positions[1] == positions[2], positions
                checks["sections"] = page.evaluate("""()=>{const r=surfaceRenderer.state.case.results;return r.sections.map(s=>({
                    label:s.label,points:s.offset_m.length,method:s.method,
                    maxCut:Math.max(...s.original_m.map((v,i)=>v-s.bed_m[i]))}))}""")
                assert checks["sections"] and all(s["points"] > 10 and s["maxCut"] > 0 and
                    "triangle" in s["method"] for s in checks["sections"])
                for case_id in sorted(CASES):
                    page.select_option("#resultCase", case_id)
                    page.wait_for_function("id=>surfaceRenderer.state.case?.results?.id===id", arg=case_id, timeout=90000)
                    assert page.evaluate("surfaceRenderer.state.case.results.sections.length") > 0
                    assert page.evaluate("surfaceRenderer.state.case.results.mesh.triangles.length") > 0
                    if case_id == "sediment":
                        page.locator("#resultTime").evaluate("e=>{e.value=e.max;e.dispatchEvent(new Event('input'))}")
                        record = download_record(page, directory, f"{name}-sediment")
                        assert record["timeSeconds"] == 900
                        assert abs(record["bedDeltaMm"][-1] + .026177451672992902) < 1e-9
                        checks["sediment_final"] = {"time_seconds": record["timeSeconds"], "bed_delta_mm": record["bedDeltaMm"],
                                                    "sediment_source": record["sedimentSource"]}
                page.select_option("#resultCase", "valley-4")
                page.wait_for_function("surfaceRenderer.state.case?.results?.id==='valley-4'", timeout=90000)
                page.evaluate("ui.view3d.click()")
                canvas = page.locator("#riverResult3d")
                canvas.wait_for(state="visible")
                pixels, measure = snapshot(canvas, directory / f"{name}-3d-before.png")
                checks["webgl_canvas"] = measure
                assert page.evaluate("()=>{const c=document.querySelector('#riverResult3d');return !!(c.getContext('webgl2')||c.getContext('webgl'))}")
                camera_before = page.evaluate("riverResultScene.reviewCamera()")
                box = canvas.bounding_box()
                page.mouse.move(box["x"] + box["width"] * .45, box["y"] + box["height"] * .5)
                page.mouse.down()
                page.mouse.move(box["x"] + box["width"] * .7, box["y"] + box["height"] * .6, steps=12)
                page.mouse.up()
                rotated, rotated_measure = snapshot(canvas, directory / f"{name}-3d-rotated.png")
                assert camera_before != page.evaluate("riverResultScene.reviewCamera()")
                checks["rotation_changed_pixels"] = difference(pixels, rotated)
                checks["rotated_canvas"] = rotated_measure
                record = download_record(page, directory, f"{name}-valley")
                assert record["caseId"] == "valley-4"
                checks["download"] = {"identity": record["identity"], "release": record["release"],
                                      "source": record["source"], "status": record["status"], "parameters": record["metadata"]["config"]}
                page.evaluate("surfaceReview.navigate('diagnostic')")
                page.wait_for_function("surfaceRenderer.state.case?.caseId==='m8-river-product'", timeout=90000)
                assert canvas.is_hidden(), "old WebGL surface covers diagnostic workspace"
                assert page.evaluate("getComputedStyle(document.querySelector('#surface')).visibility==='visible'")
                snapshot(page.locator("#surface"), directory / f"{name}-diagnostic-return.png")
                page.screenshot(path=str(directory / f"{name}-diagnostic-page.png"), full_page=True)
                checks["diagnostic_unobstructed"] = True
                report["checks"][name] = checks
                assert not report["pageerrors"], report["pageerrors"]
                context.close()
            browser.close()
        report["status"] = "passed"
        return report
    except Exception as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
        report["files_sha256"] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            "tools/verify_td_river_results_browser.py", "web-preview/river-results.js", "web-preview/river-results-3d.js",
            "web-preview/river_results.py", "web-preview/app.js", "web-preview/bridge.py",
            "web-preview/data/river-product-v1/manifest.json")}
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/td-river-release/m8-final-20261010-01")
    args = parser.parse_args()
    result = audit(args.output)
    print(json.dumps({"status": result["status"], "directory": str(args.output)}))
