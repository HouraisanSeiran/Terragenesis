"""Replay read-only review contracts in installed Playwright and Edge."""

from datetime import datetime, timezone
import hashlib
from http.server import ThreadingHTTPServer
import json
import importlib.util
import statistics
from pathlib import Path
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

BRIDGE_SPEC = importlib.util.spec_from_file_location("terrgenesis_review_bridge", ROOT / "web-preview/bridge.py")
BRIDGE = importlib.util.module_from_spec(BRIDGE_SPEC)
BRIDGE_SPEC.loader.exec_module(BRIDGE)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(directory):
    server = ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    report = {"status": "running", "checks": {}, "cases": {}, "pageerrors": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
            page = context.new_page()
            page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?workspace=surface", wait_until="networkidle")
            page.wait_for_function("window.surfaceRenderer?.state.case != null")
            dimensions = page.evaluate("({width:canvas.width,height:canvas.height,cssWidth:canvas.clientWidth,cssHeight:canvas.clientHeight,dpr:devicePixelRatio})")
            assert dimensions["width"] == round(dimensions["cssWidth"] * dimensions["dpr"])
            assert dimensions["height"] == round(dimensions["cssHeight"] * dimensions["dpr"])
            report["checks"]["initial_canvas_dpr"] = dimensions
            options = []
            for project in ("surface","dem","terrain"):
                page.evaluate("project=>surfaceReview.navigate(project)",project)
                page.wait_for_function("surfaceRenderer.state.case != null && document.querySelector('#loading').classList.contains('hidden')")
                records = page.locator("#caseSelect option").evaluate_all("options=>options.map(option=>({file:option.value,label:option.textContent}))")
                options.extend(dict(record,project=project) for record in records)
            for option in options:
                if page.input_value("#reviewProject") != option["project"]:
                    page.evaluate("project=>surfaceReview.navigate(project)",option["project"])
                page.select_option("#caseSelect", option["file"])
                if option["file"].startswith("legacy:"):
                    page.wait_for_function("surfaceRenderer.state.case?.kind==='legacy' && document.querySelector('#loading').classList.contains('hidden')")
                    page.wait_for_load_state("networkidle")
                else:
                    page.wait_for_function("expected=>surfaceRenderer.state.case?.caseId===expected && document.querySelector('#loading').classList.contains('hidden')", arg=option["file"].split("/")[-1].removesuffix(".json"))
                page.click("#view3d")
                measured = page.evaluate("()=>{const times=[];for(let index=0;index<3;index++){surfaceRenderer.render();times.push(surfaceRenderer.state.lastRenderMs)}return times}")
                case = page.evaluate("()=>{const c=surfaceRenderer.state.case;return {caseId:c.caseId,kind:c.kind,identity:c.evidence.artifactIdentity||null,status:c.evidence.status,interval:surfaceRenderer.flowInterval(c.timeseries?c:{timeseries:{signedEdgeQ:[]}})}}")
                case["render_ms"] = measured
                if case["kind"] in ("mesh","engineering"):
                    assert page.evaluate("()=>{const state=surfaceRenderer.state,mesh=state.case.mesh,heights=state.layers.h0?mesh.h0:mesh.bed;return state.sharedBoundaryNodeIds.every((index,position)=>{const vertex=mesh.vertices[index],actual=state.plot.camera.projection([vertex[0],heights[index],vertex[2]]),saved=state.sharedBoundaryProjected[position];return Math.abs(actual[0]-saved[0])<1e-9&&Math.abs(actual[1]-saved[1])<1e-9})}")
                    case["shared_boundary_matches_actual_mesh_nodes"] = True
                target = 250 if case["caseId"] == "two-domain-mosaic" or case["kind"] == "engineering" else 1000
                case["render_target_ms"] = target
                case["render_median_ms"] = statistics.median(measured)
                assert case["render_median_ms"] < target, measured
                if case["kind"] in ("dynamic", "engineering"):
                    depth = page.evaluate("()=>{const p=surfaceRenderer.state.plot.graphPlot||surfaceRenderer.state.plot;return p.bed.some((point,index)=>Math.abs(point[1]-p.water[index][1])>0.01)}")
                    assert depth
                    page.select_option("#pickMode", "graph")
                    page.evaluate("()=>{surfaceRenderer.state.moved=false;const p=(surfaceRenderer.state.plot.graphPlot||surfaceRenderer.state.plot).p[0];canvas.dispatchEvent(new MouseEvent('click',{clientX:canvas.getBoundingClientRect().left+p[0],clientY:canvas.getBoundingClientRect().top+p[1],bubbles:true}))}")
                    assert page.evaluate("surfaceReview.getSelection().type") == "graphNode"
                    for metric in ("stage", "storage", "q", "vh"):
                        page.select_option("#chartMetric", metric)
                    page.evaluate("()=>{ui.timeRange.value=ui.timeRange.max;ui.timeRange.oninput()}")
                    interval = page.evaluate("surfaceRenderer.flowInterval(surfaceRenderer.state.case)")
                    steps = page.evaluate("surfaceRenderer.state.case.timeseries.committedSteps")
                    if steps:
                        assert interval["index"] == steps - 1
                        page.select_option("#pickMode", "edge")
                        page.evaluate("()=>{surfaceRenderer.state.moved=false;const p=(surfaceRenderer.state.plot.graphPlot||surfaceRenderer.state.plot).p,edge=surfaceRenderer.state.case.graph.edges[0],a=p[edge[0]],b=p[edge[1]];canvas.dispatchEvent(new MouseEvent('click',{clientX:canvas.getBoundingClientRect().left+(a[0]+b[0])/2,clientY:canvas.getBoundingClientRect().top+(a[1]+b[1])/2,bubbles:true}))}")
                        assert page.evaluate("surfaceReview.getSelection().savedInterval") == [interval["start"], interval["end"]]
                    else:
                        assert interval is None
                    case["final_q_interval"] = interval
                    if case["kind"]=="engineering":
                        visible=page.evaluate("()=>{const c=surfaceRenderer.state.case,projection=surfaceRenderer.state.plot.camera.projection;return c.outlets.every(outlet=>outlet.mesh.bedVertices.every(vertex=>{const p=projection(vertex);return p[0]>=0&&p[0]<=canvas.clientWidth&&p[1]>=0&&p[1]<=canvas.clientHeight}))}")
                        assert visible
                        case["all_outlet_vertices_in_canvas"] = True
                        page.select_option("#pickMode","node")
                        for outlet_index in (0,1):
                            page.evaluate("index=>{const p=surfaceRenderer.state.plot.outletPlots[index].p.at(-1);surfaceRenderer.state.moved=false;selectAt({offsetX:p[0],offsetY:p[1]})}",outlet_index)
                            selected=page.evaluate("surfaceReview.getSelection()")
                            assert selected["type"]=="outletNode" and selected["outletIndex"]==outlet_index
                            assert selected["xyz"][2]==90 and len(selected["outletIdentity"])==64
                            assert selected["domain"]==outlet_index+1
                            assert "mesh" not in selected["attachment"]
                            assert page.evaluate("()=>{const c=surfaceRenderer.state.case,selection=surfaceReview.getSelection(),profile=chartSeries(c),points=c.outlets[selection.outletIndex].mesh.centerline;return profile.y.length===points.length&&profile.y.every((height,index)=>height===points[index][1])&&profile.x[0]===0&&profile.x.at(-1)===points.at(-1)[2]-points[0][2]}")
                            page.screenshot(path=str(directory / (case["caseId"]+f"-outlet-{outlet_index}.png")))
                        case["both_outlet_node_picking"] = True
                        if case["caseId"]=="land-footprint-engineering":
                            assert page.evaluate("surfaceRenderer.state.plot.waterFaceCount")==1412+180
                            case["saved_cell_water_faces"]={"land":1412,"outside":180}
                            page.select_option("#pickMode","node")
                            page.evaluate("()=>{surfaceRenderer.state.moved=false;const p=surfaceRenderer.state.plot.p[0];selectAt({offsetX:p[0],offsetY:p[1]})}")
                            selected=page.evaluate("surfaceReview.getSelection()")
                            assert selected["sourceAudit"][0]["clampedXZ"] == [10,10]
                            case["land_source_audit_picking"]=True
                if case["kind"] == "mesh":
                    page.select_option("#pickMode", "cell")
                    page.evaluate("()=>{surfaceRenderer.state.moved=false;const cell=surfaceRenderer.state.case.mesh.cells[0],p=surfaceRenderer.state.plot.p,center=cell.map(index=>p[index]).reduce((sum,point)=>[sum[0]+point[0]/4,sum[1]+point[1]/4],[0,0]);canvas.dispatchEvent(new MouseEvent('click',{clientX:canvas.getBoundingClientRect().left+center[0],clientY:canvas.getBoundingClientRect().top+center[1],bubbles:true}))}")
                    selected = page.evaluate("surfaceReview.getSelection()")
                    assert selected["type"] == "cell" and selected["sourceContributors"][0] is not None
                    assert all(type(value) is bool for value in selected["wetCells"])
                if case["kind"] == "dem":
                    page.click("#view2d")
                    page.select_option("#pickMode", "node")
                    page.evaluate("()=>{const c=surfaceRenderer.state.case,points=surfaceRenderer.state.plot.p,flags=c.display.unknown.flat(),index=flags.findIndex((flag,index)=>flag&&points[index][0]>10&&points[index][0]<canvas.clientWidth-10&&points[index][1]>10&&points[index][1]<canvas.clientHeight-10),p=points[index];surfaceRenderer.state.moved=false;selectAt({offsetX:p[0],offsetY:p[1]})}")
                    selected = page.evaluate("surfaceReview.getSelection()")
                    assert selected["unknown"] and selected["heightM"] is None
                    assert selected["savedCandidateRow"] == selected["displayRow"] * 2
                    case["unknown_selection"] = selected
                    for view in ("2d","3d"):
                        page.click("#view"+view)
                        page.locator("input[data-layer='bed']").check()
                        before=page.evaluate("canvas.toDataURL()")
                        page.locator("input[data-layer='bed']").uncheck()
                        assert page.evaluate("canvas.toDataURL()")!=before
                        page.locator("input[data-layer='bed']").check()
                    case["dem_bed_layer_both_views"] = True
                page.screenshot(path=str(directory / (case["caseId"] + ".png")))
                report["cases"][case["caseId"]] = case
            first = options[0]["file"]
            page.evaluate("surfaceReview.navigate('surface')")
            page.evaluate("file=>surfaceReview.load(file)", first)
            page.click("#view2d")
            box = page.locator("#surface").bounding_box()
            page.mouse.move(box["x"]+100,box["y"]+100)
            page.mouse.down();page.mouse.move(box["x"]+130,box["y"]+120);page.mouse.up()
            assert page.evaluate("surfaceRenderer.state.panX") != 0
            page.mouse.wheel(0, -100)
            assert page.evaluate("surfaceRenderer.state.zoom") > 1
            report["checks"]["pan_zoom"] = True
            page.click("#view3d")
            original_yaw=page.evaluate("surfaceRenderer.state.yaw")
            page.mouse.move(box["x"]+150,box["y"]+150);page.mouse.down()
            page.mouse.move(box["x"]+180,box["y"]+160);page.mouse.up()
            assert page.evaluate("surfaceRenderer.state.yaw") != original_yaw
            report["checks"]["rotate_3d"] = True
            visible_hash=page.evaluate("canvas.toDataURL()")
            for layer in ("bed","water","wet","domains","footprint"):
                page.locator(f"input[data-layer='{layer}']").uncheck()
            assert page.evaluate("canvas.toDataURL()")!=visible_hash
            report["checks"]["layers_change_actual_render"] = True
            assert page.evaluate("surfaceRenderer.range(Array.from({length:300000},(_,index)=>index))[1]")==299999
            report["checks"]["large_range_no_spread"] = True
            await_files = [option["file"] for option in options if "variable-pulse" in option["file"]]
            page.evaluate("file=>surfaceReview.load(file)", await_files[0])
            page.click("#play")
            page.evaluate("file=>surfaceReview.load(file)", first)
            assert not page.evaluate("surfaceReview.isPlaying()") and page.evaluate("surfaceReview.getSelection()") is None
            report["checks"]["switch_stops_timer_clears_selection"] = True
            page.evaluate("async files=>{await Promise.all(files.map(file=>surfaceReview.load(file)))}", [first,await_files[0],first])
            assert page.evaluate("surfaceRenderer.state.case.caseId") == "two-domain-mosaic"
            report["checks"]["async_latest_request_wins"] = True
            review = page.evaluate("surfaceReview.reviewRecord()")
            assert "vertical" in review["camera"] and len(review["source"]["sha256"]) == 64
            with page.expect_download() as download:
                page.click("#exportReview")
            download.value.save_as(str(directory / "selection-review.json"))
            report["checks"]["structured_download"] = True
            page.set_viewport_size({"width":600,"height":850})
            page.wait_for_timeout(100)
            dimensions=page.evaluate("({width:canvas.width,height:canvas.height,cssWidth:canvas.clientWidth,cssHeight:canvas.clientHeight,dpr:devicePixelRatio})")
            assert dimensions["width"]==round(dimensions["cssWidth"]*dimensions["dpr"])
            assert dimensions["height"]==round(dimensions["cssHeight"]*dimensions["dpr"])
            report["checks"]["small_viewport_dpr"]=dimensions
            page.evaluate("()=>surfaceReview.load('missing-case.json')")
            assert page.locator("#error").is_visible()
            report["checks"]["visible_load_error"] = True
            assert not report["pageerrors"], report["pageerrors"]
            browser.close()
        report["status"] = "passed"
        return report
    finally:
        server.shutdown();server.server_close();worker.join(timeout=5)


def main():
    directory=ROOT / "verification/surface-review-browser" / ("run-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"))
    directory.mkdir(parents=True,exist_ok=False)
    report={"status":"failed"}
    try:
        report=audit(directory)
    except Exception as error:
        report["error"]=repr(error)
        raise
    finally:
        report["files_sha256"]={str(path.relative_to(ROOT)):sha256(path) for path in [ROOT / "web-preview" / name for name in ("app.js","renderer.js","index.html","style.css","build_surface_review_data.py")]}
        report["files_sha256"].update({str(path.relative_to(ROOT)):sha256(path) for path in
            [ROOT / name for name in ("tests/test_surface_review_export.py","tests/test_surface_review_browser.py",
                                      "tools/verify_surface_review_browser.py","docs/surface-review-viewer.md")]})
        report["manifest_sha256"]=sha256(ROOT / "web-preview/data/surface-review-v1/manifest.json")
        report["finished_utc"]=datetime.now(timezone.utc).isoformat()
        (directory / "report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf8")
        print(str(directory.resolve()))


if __name__=="__main__":
    main()
