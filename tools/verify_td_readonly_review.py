"""Verify saved review identity, interaction and failed-read state lifetime."""

import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright


def audit(url, output):
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "checks": {}, "pageerrors": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for name, width, height in [("desktop", 1440, 900), ("mobile", 390, 844)]:
                page = browser.new_page(viewport={"width": width, "height": height}, accept_downloads=True)
                page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
                page.goto(url + "/?workspace=release", wait_until="networkidle")
                page.wait_for_function("surfaceReview.reviewRecord()?.caseId==='valley-4'")
                page.select_option("#resultLayer", "original")
                page.select_option("#resultSection", "0")
                before = page.evaluate("surfaceReview.reviewRecord()")
                ledger = page.locator("#ledger").inner_text()
                selection = page.locator("#selection").inner_text()
                with page.expect_download() as download:
                    page.locator("#exportReview").click()
                artifact = output / (name + "-export.json")
                download.value.save_as(artifact)
                exported = json.loads(artifact.read_text(encoding="utf-8"))
                assert exported["identity"] == before["identity"]
                assert exported["layer"] == "original" and exported["section"] == 0
                assert exported["publishable"] is False
                page.reload(wait_until="networkidle")
                page.wait_for_function("surfaceReview.reviewRecord()?.caseId==='valley-4'")
                page.select_option("#resultLayer", "original")
                page.select_option("#resultSection", "0")
                after = page.evaluate("surfaceReview.reviewRecord()")
                for key in ["caseId", "identity", "source", "metadata", "layer", "section", "status"]:
                    assert before[key] == after[key], key
                assert ledger == page.locator("#ledger").inner_text()
                assert selection == page.locator("#selection").inner_text()
                page.locator("#surface").screenshot(path=str(output / (name + "-geometry.png")))
                pixels = np.asarray(Image.open(output / (name + "-geometry.png")).convert("RGB"))
                assert len(np.unique(pixels.reshape(-1, 3), axis=0)) > 100
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

                # Reject both an HTTP failure and a malformed successful response.
                for response in [{"status": 503, "body": '{"error":"forced unavailable"}'},
                                 {"status": 200, "body": '{}'}]:
                    page.route("**/api/river-results/case/*", lambda route, request, response=response:
                               route.fulfill(content_type="application/json", **response))
                    page.locator("#resultCase").dispatch_event("change")
                    page.wait_for_function("!document.getElementById('error').classList.contains('hidden')")
                    assert page.evaluate("surfaceReview.reviewRecord() === null")
                    assert page.evaluate("riverResults.reviewRecord() === null")
                    assert page.evaluate("surfaceRenderer.state.case === null")
                    assert page.locator("#ledger").inner_text() == ""
                    assert page.locator("#exportReview").is_disabled()
                    page.unroute("**/api/river-results/case/*")
                    page.locator("#resultCase").dispatch_event("change")
                    page.wait_for_function("surfaceReview.reviewRecord()?.caseId==='valley-4'")
                    assert page.locator("#error").is_hidden()

                # Force the existing timeout signal to expire without spending a minute.
                page.evaluate("""() => {
                    window.reviewOriginalFetch=window.fetch;
                    window.reviewOriginalTimeout=AbortSignal.timeout;
                    AbortSignal.timeout=() => reviewOriginalTimeout(40);
                    window.fetch=(url,options) => String(url).includes('/api/river-results/case/')
                        ? new Promise((resolve,reject) => options.signal.addEventListener('abort',
                            () => reject(options.signal.reason), {once:true}))
                        : reviewOriginalFetch(url,options);
                }""")
                page.locator("#resultCase").dispatch_event("change")
                page.wait_for_function("!document.getElementById('error').classList.contains('hidden')")
                assert page.evaluate("surfaceReview.reviewRecord() === null && surfaceRenderer.state.case === null")
                page.evaluate("window.fetch=reviewOriginalFetch;AbortSignal.timeout=reviewOriginalTimeout")
                page.evaluate("surfaceReview.navigate('release')")
                page.wait_for_function("surfaceReview.reviewRecord()?.caseId==='valley-4'")

                # A late successful read must not replace the new workspace.
                payload = page.request.get(url + "/api/river-results/case/valley-4").json()
                page.evaluate("""() => {
                    window.fetch=(url,options) => String(url).includes('/api/river-results/case/')
                        ? new Promise(resolve => window.finishOldReview=resolve)
                        : reviewOriginalFetch(url,options);
                }""")
                page.locator("#resultCase").dispatch_event("change")
                page.evaluate("surfaceReview.navigate('global')")
                page.wait_for_function("surfaceReview.reviewRecord()?.schema==='global-valley-review-v1'")
                page.evaluate("payload => finishOldReview(new Response(JSON.stringify(payload), {status:200}))", payload)
                page.wait_for_timeout(250)
                assert page.evaluate("surfaceRenderer.state.case.kind === 'global-geometry'")
                assert page.evaluate("riverResults.reviewRecord() === null")
                page.evaluate("window.fetch=reviewOriginalFetch")
                page.select_option("#globalEdge", "0")
                assert page.evaluate("surfaceReview.getSelection().type") == "excludedEdge"
                page.locator("#globalExcluded").uncheck()
                global_before = page.evaluate("surfaceReview.reviewRecord()")
                global_ledger = page.locator("#ledger").inner_text()
                page.reload(wait_until="networkidle")
                page.evaluate("surfaceReview.navigate('global')")
                page.wait_for_function("surfaceReview.reviewRecord()?.schema==='global-valley-review-v1'")
                page.select_option("#globalEdge", "0")
                page.locator("#globalExcluded").uncheck()
                global_after = page.evaluate("surfaceReview.reviewRecord()")
                assert global_before == global_after
                assert global_ledger == page.locator("#ledger").inner_text()
                if name == "desktop":
                    page.evaluate("surfaceReview.navigate('saved')")
                    page.wait_for_function("surfaceReview.reviewRecord()?.schema==='saved-surface-review-v1'", timeout=90000)
                    saved_before = page.evaluate("surfaceReview.reviewRecord()")
                    saved_ledger = page.locator("#ledger").inner_text()
                    page.evaluate("surfaceReview.navigate('global')")
                    page.wait_for_function("surfaceReview.reviewRecord()?.schema==='global-valley-review-v1'")
                    page.evaluate("surfaceReview.navigate('saved')")
                    page.wait_for_function("surfaceReview.reviewRecord()?.schema==='saved-surface-review-v1'", timeout=90000)
                    saved_after = page.evaluate("surfaceReview.reviewRecord()")
                    for key in ["caseId", "source", "timeIndex", "timeSeconds", "status"]:
                        assert saved_before[key] == saved_after[key], key
                    assert saved_ledger == page.locator("#ledger").inner_text()
                    page.locator("#view3d").click()
                    page.locator("#savedSurface").screenshot(path=str(output / "saved-frame-before.png"))
                    page.route("**/api/saved/frame/**", lambda route: route.fulfill(
                        status=503, content_type="application/json", body='{"error":"forced frame failure"}'))
                    page.evaluate("savedSurface.setTime(1).catch(showError)")
                    page.wait_for_function("!document.getElementById('error').classList.contains('hidden')")
                    assert page.evaluate("surfaceReview.reviewRecord()===null && savedSurface.reviewRecord()===null")
                    assert page.locator("#ledger").inner_text() == ""
                    assert page.locator("#exportReview").is_disabled()
                    page.locator("#savedSurface").screenshot(path=str(output / "saved-frame-failed.png"))
                    canvas_bytes = page.locator("#savedSurface").evaluate("canvas => canvas.toDataURL().split(',')[1]")
                    failed_pixels = np.asarray(Image.open(io.BytesIO(base64.b64decode(canvas_bytes))).convert("RGB"))
                    assert len(np.unique(failed_pixels.reshape(-1, 3), axis=0)) < 5
                    page.unroute("**/api/saved/frame/**")
                    report["checks"]["saved_frames"] = {"cold_read": True, "failed_frame_cleared": True}
                report["checks"][name] = {"cold_read_interaction_export": True,
                                         "http_failure": True, "malformed_payload": True,
                                         "timeout": True, "late_workspace_response": True,
                                         "nonblank_geometry": True, "global_cold_read": True}
                page.close()
            browser.close()
        assert not report["pageerrors"], report["pageerrors"]
        report["status"] = "passed"
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def audit_partial_response(url, output):
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "running", "checks": {}, "pageerrors": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
            page.goto(url + "/?workspace=release", wait_until="networkidle")
            page.wait_for_function("surfaceReview.reviewRecord()?.caseId==='valley-4'")
            partial = {"global_geometry": {}, "scope_exclusion": {"artifact": {"sha256": "invalid"}},
                       "case_id": "partial-success-response", "label": "invalid partial geometry"}
            page.route("**/api/river-results/global", lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(partial)))
            page.evaluate("surfaceReview.navigate('global')")
            page.wait_for_function("!document.getElementById('error').classList.contains('hidden')")
            assert page.evaluate("surfaceRenderer.state.case===null && surfaceReview.reviewRecord()===null")
            assert page.locator("#ledger").inner_text() == ""
            assert page.locator("#exportReview").is_disabled()
            assert page.evaluate("surfaceReview.getSelection()===null")
            page.unroute("**/api/river-results/global")
            page.evaluate("surfaceReview.navigate('release')")
            page.wait_for_function("surfaceReview.reviewRecord()?.caseId==='valley-4'")
            assert page.locator("#error").is_hidden()
            browser.close()
        assert not report["pageerrors"], report["pageerrors"]
        report["status"] = "passed"
        report["checks"]["partial_nonrelease_payload_cleared"] = True
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--partial-failure-only", action="store_true")
    arguments = parser.parse_args()
    verifier = audit_partial_response if arguments.partial_failure_only else audit
    print(json.dumps(verifier(arguments.url, arguments.output)))
