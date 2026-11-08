"""Independent browser interaction checks on externally pinned saved TD reviews."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_review import load_basin_review


def audit_browser(directory, manifest_sha256, output):
    from playwright.sync_api import sync_playwright

    directory = Path(directory).resolve(strict=True)
    review = load_basin_review(directory, expected_manifest_sha256=manifest_sha256)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["inputs"].values():
        if file_sha256(record["path"]) != record["expected_sha256"]:
            raise ValueError("saved input pin mismatch")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    errors = []
    requests = []
    evidence = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True, args=["--disable-gpu"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.goto((directory / "review.html").as_uri(), wait_until="load")
        page.wait_for_function("document.querySelector('#details').textContent.length > 0")
        data_shape = page.evaluate("data.native_shape")
        if data_shape != review["shape"]:
            raise ValueError("browser native grid mismatch")
        maximum = len(review["water"]["time_s"]) - 1 if review["water"] else 0
        if int(page.locator("#time").get_attribute("max")) != maximum:
            raise ValueError("saved frame range mismatch")
        for mode in ("2D", "3D"):
            page.select_option("#view", mode)
            for frame in sorted({0, maximum // 2, maximum}):
                page.locator("#time").evaluate("(control,frame)=>{control.value=frame;control.dispatchEvent(new Event('input'))}", frame)
                metrics = page.evaluate("()=>{const timings=[];for(let count=0;count<12;count++){const start=performance.now();draw();timings.push(performance.now()-start)}return {timings_ms:timings,visible_cells:screenCells.length,frame:Number(time.value),stamp:document.querySelector('#stamp').textContent}}")
                expected_time = review["water"]["time_s"][frame] if review["water"] else None
                if expected_time is not None and (not metrics["stamp"].endswith(" s") or float(metrics["stamp"][:-2]) != expected_time):
                    raise ValueError("physical time display mismatch")
                metrics["p95_ms"] = sorted(metrics["timings_ms"])[-2]
                metrics["mode"] = mode
                evidence.append(metrics)
            page.screenshot(path=str(output / (mode + ".png")), full_page=True)
        page.select_option("#view", "2D")
        page.select_option("#layer", "bed")
        cell = page.evaluate("screenCells[Math.floor(screenCells.length/2)]")
        page.locator("#canvas").click(position={"x": cell["point"][0], "y": cell["point"][1]})
        picked = json.loads(page.locator("#details").inner_text())["picked_cell"]
        if picked is None:
            raise ValueError("native cell picking failed")
        row, column = picked["row"], picked["col"]
        for key, field in (("H0_m", "H0_m"), ("erodibility", "erodibility"), ("basin_owner", "basin_owner")):
            if picked[key] != review["fields"][field][row][column]:
                raise ValueError("picked saved field mismatch")
        if review["water"] and picked["water_depth_m"] != review["water"]["depth_m"][maximum][row][column]:
            raise ValueError("picked saved water mismatch")
        camera_before = page.evaluate("({yaw,pitch,zoom})")
        for layer in ("H0_m", "delta", "erodibility", "erodible_thickness_m", "weak_path_preference", "basin_owner"):
            page.select_option("#layer", layer)
        if camera_before != page.evaluate("({yaw,pitch,zoom})"):
            raise ValueError("layer selection changes camera")
        page.select_option("#layer", "bed")
        image_before = page.locator("#canvas").screenshot()
        page.check("#saddle")
        image_after = page.locator("#canvas").screenshot()
        saddle_count = page.evaluate("data.saddle_overlay.length")
        if saddle_count and image_before == image_after:
            raise ValueError("saddle overlay control has no visible effect")
        page.uncheck("#saddle")
        water_before = page.locator("#canvas").screenshot()
        page.uncheck("#water")
        water_after = page.locator("#canvas").screenshot()
        water_pixels_changed = water_before != water_after
        page.check("#water")
        if review["water"]:
            page.locator("#time").evaluate("control=>{control.value=0;control.dispatchEvent(new Event('input'))}")
            page.click("#play")
            page.wait_for_function("Number(time.value)>0", timeout=5000)
            page.click("#play")
            stopped = int(page.locator("#time").input_value())
            page.wait_for_timeout(650)
            if int(page.locator("#time").input_value()) != stopped:
                raise ValueError("pause failed to freeze saved time")
        page.select_option("#view", "3D")
        rectangle = page.locator("#canvas").bounding_box()
        start_x, start_y = rectangle["x"] + 300, rectangle["y"] + 200
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x + 100, start_y + 25, steps=5)
        page.mouse.up()
        camera_drag = page.evaluate("({yaw,pitch,zoom})")
        if camera_drag == camera_before:
            raise ValueError("rotation failed")
        page.mouse.wheel(0, -150)
        page.wait_for_function("zoom>1")
        page.click("#fit")
        if page.evaluate("({yaw,pitch,zoom})") != {"yaw": -0.6, "pitch": 0.7, "zoom": 1}:
            raise ValueError("camera reset failed")
        page.screenshot(path=str(output / "interactions.png"), full_page=True)
        threshold_evidence = []
        if review["water"] and page.locator("#waterThreshold").count():
            page.locator("#time").evaluate("control=>{control.value=control.max;control.dispatchEvent(new Event('input'))}")
            stride = review["render_lod"]["stride"]
            depth = review["water"]["depth_m"][maximum]
            total_volume = sum(sum(row) for row in depth) * review["spacing_m"] ** 2
            for threshold in (0., .05, 1.):
                page.locator("#waterThreshold").fill(str(threshold))
                page.locator("#waterThreshold").dispatch_event("input")
                omission = page.evaluate("data.display_omission")
                expected_hidden = 0.0
                shown = 0.0
                wet_threshold = review["water"]["flags"]["parameters"]["wet_threshold_m"]
                for row in range(0, review["shape"][0], stride):
                    for column in range(0, review["shape"][1], stride):
                        if review["fields"]["valid_mask"][row][column]:
                            volume = depth[row][column] * review["spacing_m"] ** 2
                            if depth[row][column] <= max(threshold, wet_threshold):
                                expected_hidden += volume
                            else:
                                shown += volume
                if abs(omission["threshold_hidden_sampled_water_m3"] - expected_hidden) > 1e-7:
                    raise ValueError("display threshold hidden water differs from native samples")
                omitted_lod = review["render_lod"]["omitted_water_volume_m3_by_frame"][maximum]
                if abs(expected_hidden + omitted_lod + shown - total_volume) > 1e-6 + total_volume * 1e-10:
                    raise ValueError("sampled/displayed/omitted water does not account for full volume")
                threshold_evidence.append({"threshold_m": threshold, "hidden_native_sample_m3": expected_hidden,
                                           "lod_omitted_m3": omitted_lod, "displayed_native_volume_m3": shown,
                                           "full_saved_volume_m3": total_volume})
        browser.close()
    if errors or any(url.startswith(("http://", "https://")) for url in requests):
        raise ValueError("offline review browser error or network dependency")
    report = {"schema": "td-basin-independent-browser-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
              "input_directory": str(directory), "manifest_sha256": manifest_sha256,
              "auditor_sha256": file_sha256(__file__), "page_errors": errors, "requests": requests,
              "frames": evidence, "picked_cell": picked, "saddle_overlay_faces": saddle_count,
              "water_control_changes_pixels": water_pixels_changed, "camera_rotation_zoom_reset": True,
              "play_pause_checked": review["water"] is not None,
              "display_threshold_volume_checks": threshold_evidence,
              "scope": "saved sampled cell surface display; no hydraulic or finite-width channel certification",
              "screenshots": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.glob("*.png")}}
    publish_bytes(output / "report.json", json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_browser(args.directory, args.manifest_sha256, args.output)
    print(json.dumps({"output": str(args.output), "page_errors": report["page_errors"], "frames": len(report["frames"])}))


if __name__ == "__main__":
    main()
