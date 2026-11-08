"""Actual desktop/mobile saved M8 consumer and the six renderer review contracts."""
import json
import hashlib
from pathlib import Path

from playwright.sync_api import sync_playwright

from tools.verify_surface_review_browser import ROOT, BRIDGE
from http.server import ThreadingHTTPServer
import threading


def audit(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), BRIDGE.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    report = {"status": "running", "checks": {}, "pageerrors": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            for name, viewport in (("desktop", {"width": 1440, "height": 1000}), ("mobile", {"width": 390, "height": 844})):
                context = browser.new_context(viewport=viewport, accept_downloads=True)
                page = context.new_page()
                page.on("pageerror", lambda error: report["pageerrors"].append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/?workspace=diagnostic", wait_until="networkidle")
                page.wait_for_function("surfaceRenderer.state.case?.caseId==='m8-river-product'")
                state = page.evaluate("()=>{const c=surfaceRenderer.state.case;return {identity:c.identity,source:c.release.source.kind,m7:c.release.gates.m7,steps:c.timeseries.committedSteps,interval:surfaceRenderer.flowInterval(c)}}")
                assert state["m7"] is not None
                assert state["interval"]["index"] == 0
                assert state["interval"]["qUnits"] == "m3/s"
                assert page.evaluate("JSON.stringify(surfaceRenderer.flowInterval())===JSON.stringify(surfaceRenderer.flowInterval(surfaceRenderer.state.case))")
                assert page.evaluate("()=>{const saved=surfaceRenderer.state.case;surfaceRenderer.state.case=null;const result=surfaceRenderer.flowInterval();surfaceRenderer.state.case=saved;return result===null}")
                assert page.locator('#tdScenario').is_hidden() and page.locator('#tdLayer').is_hidden()
                if name == "desktop":
                    page.evaluate("surfaceReview.navigate('td')")
                    page.wait_for_function("surfaceRenderer.state.case?.kind==='td'")
                    assert page.locator('#tdScenario').is_visible()
                    page.evaluate("surfaceReview.navigate('diagnostic')")
                    page.wait_for_function("surfaceRenderer.state.case?.caseId==='m8-river-product'")
                    assert page.locator('#tdScenario').is_hidden()
                    assert page.evaluate("surfaceRenderer.state.time") == 0
                    assert page.locator('#timeSeconds').inner_text() == 't = 0 s'
                page.evaluate("setTime(1)")
                assert page.evaluate("surfaceRenderer.flowInterval().index") == 0
                page.evaluate("setTime(Number(ui.timeRange.max))")
                assert page.evaluate("surfaceRenderer.flowInterval().index") == state["steps"] - 1
                page.evaluate("()=>{ui.pickMode.value='edge';const state=surfaceRenderer.state,p=state.plot.points,e=state.case.graph.edges[0];state.moved=false;surfaceReview.selectAt({offsetX:(p[e[0]][0]+p[e[1]][0])/2,offsetY:(p[e[0]][1]+p[e[1]][1])/2})}")
                assert page.evaluate("surfaceReview.getSelection().index") == 0
                page.evaluate("()=>{ui.view3d.click();ui.verticalScale.value='5';ui.verticalScale.oninput();ui.pickMode.value='edge';const state=surfaceRenderer.state,p=state.plot.points,edge=state.case.graph.edges[0],a=p[edge[0]],b=p[edge[1]];state.moved=false;surfaceReview.selectAt({offsetX:(a[0]+b[0])/2,offsetY:(a[1]+b[1])/2})}")
                selected = page.evaluate("surfaceReview.getSelection()")
                assert selected["type"] == "edge" and selected["index"] == 0, selected
                assert selected["qM3S"] == page.evaluate("surfaceRenderer.flowInterval(surfaceRenderer.state.case).row[0]")
                assert page.evaluate("surfaceRenderer.state.plot.overlaySemantics.includes('not a fine-grid instantaneous water surface')")
                page.evaluate("()=>{ui.pickMode.value='graph';const state=surfaceRenderer.state,p=state.plot.p[10];state.moved=false;surfaceReview.selectAt({offsetX:p[0],offsetY:p[1]})}")
                assert page.evaluate("surfaceReview.getSelection().type") == "graphNode"
                # Turning graph and saved-stage layers off and back on must keep the saved case identity.
                for layer in ('edges', 'water'):
                    page.locator(f'input[data-layer="{layer}"]').uncheck()
                    page.locator(f'input[data-layer="{layer}"]').check()
                assert page.evaluate("surfaceRenderer.state.case.identity") == state["identity"]
                with page.expect_download() as download:
                    page.evaluate("ui.exportReview.click()")
                exported = directory / (name + "-review-record.json")
                download.value.save_as(exported)
                record = json.loads(exported.read_text(encoding="utf-8"))
                assert record["riverProduct"]["identity_sha256"] == state["identity"]
                assert record["riverProduct"]["gates"]["publishable"] is False
                assert record["riverProduct"]["m7_comparison"] is not None
                assert record["dynamicRiverOverlay"]["semantics"].startswith("graph edges are drawn on the bed")
                assert record["selection"]["timeSeconds"] == record["timeSeconds"]
                page.evaluate("()=>{ui.view2d.click();setTime(0)}")
                assert page.evaluate("surfaceReview.getSelection()") is None
                assert page.evaluate("surfaceReview.reviewRecord().selection") is None
                pixels = page.evaluate("()=>{const c=document.querySelector('#surface'),v=c.getContext('2d').getImageData(0,0,c.width,c.height).data,colors=new Set();for(let i=0;i<v.length;i+=64)colors.add(`${v[i]},${v[i+1]},${v[i+2]}`);return {colors:colors.size,width:c.width,height:c.height,cssWidth:c.clientWidth,cssHeight:c.clientHeight}}")
                assert pixels["colors"] > 20 and pixels["width"] > 100 and pixels["height"] > 100, pixels
                if name == "desktop":
                    assert pixels["height"] < viewport["height"], pixels
                page.screenshot(path=str(directory / (name + "-2d.png")), full_page=True)
                page.evaluate("ui.view3d.click()")
                page.screenshot(path=str(directory / (name + "-3d.png")), full_page=True)
                report["checks"][name] = {**state, "edge_selection": selected, "canvas": pixels, "export": str(exported.relative_to(ROOT))}
                if name == "desktop":
                    arrows = page.evaluate("""()=>{const data={graph:{coords:[[0,0],[10,0]],bed:[0,0],edges:[[0,1]],boundary:[false,false]},timeseries:{timeSeconds:[0,1],stages:[[1,1],[1,1]],signedEdgeQ:[[1]],signedEdgeQUnits:'m3/s'}};const tips=[];const helpers={state:{view:'2d',time:0,layers:{edges:true}},bounds:()=>[0,10,0,1],fit:()=>1,project:p=>[p[0],p[2]],camera3d:()=>null,drawLine:()=>{},drawTriangle:p=>tips.push(p[0]),context:{setLineDash:()=>{}}};const results=[];for(const q of [1,-1,0]){tips.length=0;data.timeseries.signedEdgeQ[0][0]=q;riverRenderer.render(data,100,100,null,helpers);results.push({q,tips:[...tips]})}return results}""")
                    assert arrows == [{"q": 1, "tips": [[10, 0]]}, {"q": -1, "tips": [[0, 0]]}, {"q": 0, "tips": []}], arrows
                    report["checks"]["signed_arrows"] = arrows
                    page.evaluate("surfaceReview.navigate('surface')")
                    page.wait_for_function("surfaceRenderer.state.case != null && ui.loading.classList.contains('hidden')")
                    page.evaluate("surfaceReview.load('version-20260930T205649.463430Z/two-domain-engineering.json')")
                    page.wait_for_function("surfaceRenderer.state.case?.caseId==='two-domain-engineering'")
                    page.evaluate("ui.view3d.click()")
                    assert page.evaluate("surfaceRenderer.state.plot.graphOverlaySemantics.includes('does not represent a fine-grid instantaneous water surface')")
                    assert page.evaluate("surfaceReview.reviewRecord().dynamicRiverOverlay.semantics.includes('do not represent a fine-grid instantaneous water surface')")
                    report['checks']['engineering_3d_annotation'] = True
                context.close()
            browser.close()
        assert not report["pageerrors"], report["pageerrors"]
        report["status"] = "passed"
        report["six_item_review"] = {"render_only": "river-renderer consumes saved arrays, no solver or certification", "signed_q": "positive/negative/zero endpoint arrow replay passed", "interval": "0->0, 1->0, final->committedSteps-1 passed", "3d": "bed topology diagnostic annotation retained in display/export", "facade_and_picking": "flowInterval and bed edge/stage node projection passed desktop/mobile", "split": "existing renderer boundary retained; edge selection now explicitly uses renderer.points, no extra module needed for this data model"}
        return report
    except Exception as error:
        report.update(status="failed", error=repr(error))
        raise
    finally:
        server.shutdown(); server.server_close(); worker.join(timeout=5)
        report['files_sha256'] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in
            [ROOT / 'web-preview' / name for name in ('app.js','renderer.js','river-renderer.js','style.css','bridge.py')] + [ROOT / 'tools/verify_td_river_release_browser.py']}
        report['release_manifest'] = json.loads((ROOT / 'web-preview/data/river-product-v1/manifest.json').read_text(encoding='utf-8'))
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    result = audit(ROOT / "verification/td-river-release/m8-20261010-01")
    print(json.dumps({"status":result["status"], "directory":"verification/td-river-release/m8-20261010-01"}))
