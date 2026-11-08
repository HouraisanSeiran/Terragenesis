"""Check the actual saved stage review on desktop and mobile."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright


def audit(url, output):
    if output.exists():
        if any(output.iterdir()):
            raise FileExistsError(output)
    else:
        output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "checks": {}, "pageerrors": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for name, width, height in [("desktop", 1440, 900), ("mobile", 390, 844)]:
                page = browser.new_page(viewport={"width": width, "height": height}, accept_downloads=True)
                page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
                page.goto(url + "/?workspace=morphology", wait_until="networkidle")
                page.wait_for_function("surfaceReview.reviewRecord()?.morphologyReview?.stage_review", timeout=90000)
                payload = page.request.get(url + "/api/morphology/case").json()
                assert payload["capabilities"]["publishable"] is False
                for feature in ["delta", "cutoff", "bank", "braided", "fan", "floodplain"]:
                    page.select_option("#morphologyFeature", feature)
                    assert page.evaluate("surfaceReview.reviewRecord().morphologyReview.feature") == feature
                    displayed = json.loads(page.locator("#ledger").inner_text())
                    assert displayed["candidate"] == feature
                    assert displayed["candidates"][feature]["status"] == payload["candidates"][feature]["status"]
                page.select_option("#morphologyFeature", "cutoff")
                assert "stage4" in page.locator("#ledger").inner_text()
                displayed_stage = json.loads(page.locator("#ledger").inner_text())["stage_review"]["stage4"]
                supplements = payload["stage_review"].get("supplemental_report_pins", {})
                for supplement_name, pin in supplements.items():
                    shown = displayed_stage["supplemental_reports"][supplement_name]
                    assert shown["summary"] == payload["stage_review"]["stage4"]["supplemental_reports"][supplement_name]["summary"]
                    assert shown["pin"]["sha256"] == pin["sha256"]
                assert page.locator("#morphologyFeature").input_value() == "cutoff"
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=str(output / (name + "-viewport.png")), full_page=False)
                if name == "desktop":
                    assert page.locator("#surface").bounding_box()["height"] < height
                canvas = page.locator("#surface")
                canvas.screenshot(path=str(output / (name + "-before.png")))
                before_pixels = np.asarray(Image.open(output / (name + "-before.png")).convert("RGB"))
                page.select_option("#morphologyLayer", "candidate")
                page.screenshot(path=str(output / (name + "-candidate-viewport.png")), full_page=False)
                canvas.screenshot(path=str(output / (name + "-after.png")))
                after_pixels = np.asarray(Image.open(output / (name + "-after.png")).convert("RGB"))
                assert len(np.unique(after_pixels.reshape(-1, 3), axis=0)) > 100
                changed = int(np.count_nonzero(np.any(before_pixels != after_pixels, axis=-1)))
                assert changed > 0, "saved before/after terrain must affect actual pixels"
                point = page.evaluate("surfaceRenderer.state.plot.p[Math.floor(surfaceRenderer.state.plot.p.length/2)]")
                page.evaluate("point => surfaceReview.selectAt({offsetX:point[0],offsetY:point[1]})", point)
                record = page.evaluate("surfaceReview.reviewRecord()")
                assert record["selection"]["type"] == "morphology-native-cell"
                assert record["selection"]["publishable"] is False
                assert record["morphologyReview"]["layer"] == "candidate"
                ledger = page.locator("#ledger").inner_text()
                with page.expect_download() as downloaded:
                    page.locator("#exportReview").click()
                artifact = output / (name + "-export.json")
                downloaded.value.save_as(artifact)
                exported = json.loads(artifact.read_text(encoding="utf-8"))
                assert exported["morphologyReview"] == record["morphologyReview"]
                assert exported["selection"] == record["selection"]
                exported_stage = exported["morphologyReview"]["stage_review"]
                assert exported_stage.get("supplemental_report_pins", {}) == supplements
                for supplement_name, pin in supplements.items():
                    full = exported_stage["stage4_full_report"]["supplemental_reports"][supplement_name]
                    assert full["pin"] == pin
                    source_path = Path(__file__).resolve().parents[1] / pin["path"]
                    assert full["report"] == json.loads(source_path.read_text(encoding="utf-8"))
                page.reload(wait_until="networkidle")
                page.wait_for_function("surfaceReview.reviewRecord()?.morphologyReview?.stage_review", timeout=90000)
                page.select_option("#morphologyLayer", "candidate")
                point = page.evaluate("surfaceRenderer.state.plot.p[Math.floor(surfaceRenderer.state.plot.p.length/2)]")
                page.evaluate("point => surfaceReview.selectAt({offsetX:point[0],offsetY:point[1]})", point)
                cold = page.evaluate("surfaceReview.reviewRecord()")
                assert cold["morphologyReview"]["identity_sha256"] == record["morphologyReview"]["identity_sha256"]
                assert cold["morphologyReview"] == record["morphologyReview"]
                assert cold["selection"] == record["selection"]
                assert page.locator("#ledger").inner_text() == ledger
                page.locator("#view3d").click()
                canvas.screenshot(path=str(output / (name + "-3d.png")))
                pixels = np.asarray(Image.open(output / (name + "-3d.png")).convert("RGB"))
                assert len(np.unique(pixels.reshape(-1, 3), axis=0)) > 100
                box = canvas.bounding_box()
                page.mouse.move(box["x"] + box["width"] * .5, box["y"] + box["height"] * .5)
                page.mouse.down()
                page.mouse.move(box["x"] + box["width"] * .65, box["y"] + box["height"] * .55, steps=8)
                page.mouse.up()
                canvas.screenshot(path=str(output / (name + "-3d-rotated.png")))
                rotated = np.asarray(Image.open(output / (name + "-3d-rotated.png")).convert("RGB"))
                rotation_changed = int(np.count_nonzero(np.any(pixels != rotated, axis=-1)))
                assert rotation_changed > 100
                page.route("**/api/morphology/case", lambda route: route.fulfill(
                    status=503, content_type="application/json", body='{"error":"forced stage failure"}'))
                page.evaluate("surfaceReview.navigate('morphology')")
                page.wait_for_function("!document.getElementById('error').classList.contains('hidden')")
                assert page.evaluate("surfaceReview.reviewRecord()===null && surfaceRenderer.state.case===null")
                assert page.locator("#ledger").inner_text() == ""
                assert page.locator("#exportReview").is_disabled()
                page.unroute("**/api/morphology/case")
                malformed = dict(payload)
                malformed["terrain"] = {**payload["terrain"], "valid_mask": None}
                page.route("**/api/morphology/case", lambda route: route.fulfill(
                    status=200, content_type="application/json", body=json.dumps(malformed)))
                page.evaluate("surfaceReview.navigate('morphology')")
                page.wait_for_function("!document.getElementById('error').classList.contains('hidden')")
                assert page.evaluate("surfaceReview.reviewRecord()===null && surfaceRenderer.state.case===null")
                assert page.locator("#ledger").inner_text() == ""
                page.unroute("**/api/morphology/case")
                page.evaluate("surfaceReview.navigate('morphology')")
                page.wait_for_function("surfaceReview.reviewRecord()?.morphologyReview?.stage_review", timeout=90000)
                page.evaluate("""() => {
                    window.stageOriginalFetch=window.fetch;
                    window.stageOriginalTimeout=AbortSignal.timeout;
                    AbortSignal.timeout=() => stageOriginalTimeout(40);
                    window.fetch=(url,options) => String(url).includes('/api/morphology/case')
                        ? new Promise((resolve,reject) => options.signal.addEventListener('abort',
                            () => reject(options.signal.reason),{once:true})) : stageOriginalFetch(url,options);
                }""")
                page.evaluate("surfaceReview.navigate('morphology')")
                page.wait_for_function("!document.getElementById('error').classList.contains('hidden')")
                assert page.evaluate("surfaceReview.reviewRecord()===null && surfaceRenderer.state.case===null")
                page.evaluate("window.fetch=stageOriginalFetch;AbortSignal.timeout=stageOriginalTimeout")
                page.evaluate("""() => { window.fetch=(url,options) => String(url).includes('/api/morphology/case')
                    ? new Promise(resolve => window.finishStageReview=resolve) : stageOriginalFetch(url,options) }""")
                page.evaluate("surfaceReview.navigate('morphology')")
                page.evaluate("surfaceReview.navigate('release')")
                page.wait_for_function("surfaceReview.reviewRecord()?.caseId==='valley-4'", timeout=90000)
                page.evaluate("payload => finishStageReview(new Response(JSON.stringify(payload),{status:200}))", payload)
                page.wait_for_timeout(150)
                assert page.evaluate("surfaceReview.reviewRecord().caseId==='valley-4'")
                page.evaluate("window.fetch=stageOriginalFetch")
                report["checks"][name] = {"native_before_after_changed_pixels": changed,
                                         "cold_selection_layers_ledger_export": True, "nonblank_3d": True,
                                         "rotation_changed_pixels": rotation_changed, "all_six_candidate_selection": True,
                                         "candidate_capabilities_preserved": True, "failed_load_cleared": True,
                                         "timeout_cleared": True, "late_workspace_response_discarded": True}
                page.close()
            browser.close()
        assert not report["pageerrors"], report["pageerrors"]
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["reason"] = repr(error)
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def audit_layout(url, output):
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "functional_evidence": "stage5-browser-20261011-02/report.json", "checks": {}}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for name, width, height in [("desktop", 1440, 900), ("mobile", 390, 844)]:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(url + "/?workspace=morphology", wait_until="networkidle")
                page.wait_for_function("surfaceRenderer.state.case?.morphology?.stage_review", timeout=90000)
                page.screenshot(path=str(output / (name + "-viewport.png")), full_page=False)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                canvas = page.locator("#surface")
                canvas.scroll_into_view_if_needed()
                page.select_option("#morphologyLayer", "candidate")
                page.screenshot(path=str(output / (name + "-canvas-viewport.png")), full_page=False)
                if name == "desktop":
                    assert canvas.bounding_box()["height"] < height
                page.locator("#view3d").click()
                canvas.scroll_into_view_if_needed()
                canvas.screenshot(path=str(output / (name + "-3d.png")))
                original = np.asarray(Image.open(output / (name + "-3d.png")).convert("RGB"))
                assert len(np.unique(original.reshape(-1, 3), axis=0)) > 100
                box = canvas.bounding_box()
                page.mouse.move(box["x"] + box["width"] * .5, box["y"] + box["height"] * .5)
                page.mouse.down()
                page.mouse.move(box["x"] + box["width"] * .65, box["y"] + box["height"] * .55, steps=8)
                page.mouse.up()
                canvas.screenshot(path=str(output / (name + "-3d-rotated.png")))
                rotated = np.asarray(Image.open(output / (name + "-3d-rotated.png")).convert("RGB"))
                changed = int(np.count_nonzero(np.any(original != rotated, axis=-1)))
                assert changed > 100
                report["checks"][name] = {"viewport": [width, height], "canvas": canvas.bounding_box(),
                                         "rotation_changed_pixels": changed, "no_horizontal_overflow": True}
                page.close()
            browser.close()
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", reason=repr(error))
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layout-only", action="store_true")
    arguments = parser.parse_args()
    verifier = audit_layout if arguments.layout_only else audit
    print(json.dumps(verifier(arguments.url, arguments.output)))
