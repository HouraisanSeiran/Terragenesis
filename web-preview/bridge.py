"""Local read-only bridge plus explicit VDM preview/export endpoints.

The bridge never runs hydrology replay, GPU inference, world writing, or cave generation.
It reads fixed, hashed evidence roots and only permits the explicit local geometry preview.
"""
from __future__ import annotations

import hashlib
import json
import math
import mimetypes
import re
import threading
import os
import sys
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web-preview"
DATA = WEB / "data"
VDM_FORMS = ROOT / "verification/metric-vdm-forms/run-20261003T101709799064Z/gallery.json"
VDM_CONTROLS = ROOT / "verification/metric-vdm-controls/final-20261003T131348175Z/gallery.json"
TD_CONFIG = ROOT / ".scratch/metric-vdm/td-channel-example.json"
TD_ACCEPTANCE = ROOT / "verification/td-weather-refinement/independent-final-20261002T232545211593Z/acceptance-index.json"
TD_EXECUTION = ROOT / "verification/td-weather-refinement/followup-20261002T201334385533Z/execution/index.json"
TD_WATER_SURFACE = ROOT / "verification/td-native-water-surface/185307-eastward-hour00-threshold1mm-final/report.json"
TD_CHANNEL_PATHS = ROOT / "verification/td-native-channel-valley-paths/prototype-20261003-window-19-29-104-114-v2-conservative/report.json"
BASIN_COMPARISON = ROOT / "verification/td-basin-treatment-comparison/run-20261003T-next-01/comparison.json"
SURFACE_MANIFEST = DATA / "surface-review-v1/manifest.json"
LEGACY_MANIFEST = DATA / "manifest.json"
_TD_INDEX_LOCK = threading.Lock()


def pinned_path(record: dict, *, allowed: tuple[str, ...] = ("verification/", ".scratch/")) -> Path:
    """Resolve only project-root records, never client-supplied paths."""
    raw = record["path"].replace("\\", "/")
    prefix = "D:/codexwork/山川形意Terragenesis/"
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    elif raw.startswith("/") or ":" in raw:
        raise ValueError("source outside pinned project root")
    if not raw.startswith(allowed) or ".." in Path(raw).parts:
        raise ValueError("source outside fixed evidence roots")
    path = (ROOT / raw).resolve()
    if ROOT not in path.parents:
        raise ValueError("source escapes project root")
    return path


def pinned_json(path: Path, schema: str, expected: str | None = None) -> dict:
    verify_entry(path, expected)
    result = read_json(path)
    if result.get("schema") != schema:
        raise ValueError(f"incompatible schema: {root_relative(path)}")
    return result


def execution_index():
    acceptance = pinned_json(TD_ACCEPTANCE, "td-independent-final-temporal-refinement-v1")
    record = acceptance["run_records"]["index"]
    if pinned_path(record) != TD_EXECUTION:
        raise ValueError("accepted TD execution index does not match fixed source")
    return pinned_json(TD_EXECUTION, "td-v10-temporal-refinement-index-v1", record["expected_sha256"])


def vdm_gallery():
    gallery = pinned_json(VDM_FORMS, "metric-vdm-forms-gallery-v1")
    pinned_json(VDM_CONTROLS, "metric-vdm-forms-gallery-v1")
    verify_entry(TD_CONFIG, gallery["configuration"]["expected_sha256"])
    return gallery


def bounded_form(body: dict):
    from terrain_pipeline.metric_vdm_forms import FormRecipe
    if not isinstance(body, dict) or set(body) - {"kind", "amplitude_m", "wavelength_m", "seed", "surface_curvature_m", "end_elevation_difference_m", "extension_direction_degrees"}:
        raise ValueError("invalid VDM form fields")
    kind = body.get("kind", "layered_ledge")
    if kind not in {v["kind"] for v in vdm_gallery()["variants"]}:
        raise ValueError("unknown VDM form")
    numeric = {}
    for key, default in (("amplitude_m", 1.5), ("wavelength_m", 6.), ("surface_curvature_m", 0.), ("end_elevation_difference_m", 0.)):
        value = body.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
        numeric[key] = float(value)
    seed = body.get("seed", 7)
    if type(seed) is not int or not 0 <= seed <= 2 ** 32 - 1:
        raise ValueError("seed must be an unsigned 32-bit integer")
    direction = body.get("extension_direction_degrees")
    if direction is not None and (type(direction) not in (int, float) or not math.isfinite(direction) or not 0 <= direction < 360):
        raise ValueError("extension direction must be between 0 and 360 degrees")
    if not 0 < numeric["amplitude_m"] <= 1.5 or not 4 <= numeric["wavelength_m"] <= 100 or abs(numeric["surface_curvature_m"]) > numeric["wavelength_m"] / 2 or abs(numeric["end_elevation_difference_m"]) > 8:
        raise ValueError("VDM geometry constraints exceeded; parameters were not clamped")
    return FormRecipe(kind=kind, seed=seed, extension_direction_degrees=direction, **numeric)


def mesh_window(arrays: dict, *, pad: int = 8):
    """A contiguous local XYZ chart; topology is the original chart's local submesh."""
    import numpy as np
    ref = arrays["reference_xyz_m"]
    disp = arrays["displacement_xyz_m"]
    mask = arrays["protected_mask"]
    changed = np.any(np.abs(disp) > 1e-9, axis=2)
    rows, cols = ref.shape[:2]
    if changed.any():
        rr, cc = np.where(changed)
        r0, r1 = max(0, int(rr.min())-pad), min(rows, int(rr.max())+pad+1)
        c0, c1 = max(0, int(cc.min())-pad), min(cols, int(cc.max())+pad+1)
    else:
        r0, r1, c0, c1 = 0, rows, 0, cols
    if (r1-r0)*(c1-c0) > 25000:
        raise ValueError("local VDM chart exceeds preview budget")
    indices = np.arange(rows*cols).reshape(rows, cols)[r0:r1, c0:c1].ravel()
    inverse = np.full(rows*cols, -1, dtype=np.int64)
    inverse[indices] = np.arange(len(indices))
    triangles = inverse[np.asarray(arrays["triangles"], dtype=np.int64)]
    triangles = triangles[np.all(triangles >= 0, axis=1)]
    reference = ref[r0:r1, c0:c1].reshape(-1, 3)
    delta = disp[r0:r1, c0:c1].reshape(-1, 3)
    return {"vertices": (reference+delta).tolist(), "reference": reference.tolist(), "displacement": delta.tolist(), "protected": mask[r0:r1, c0:c1].ravel().tolist(), "triangles": triangles.tolist(), "sourceChart": {"rows": rows, "columns": cols, "window": [r0, r1, c0, c1], "fullVertices": rows*cols, "fullTriangles": len(arrays["triangles"]), "scope": "contiguous local chart; source triangle indices remapped without interpolation"}}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def root_relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def verify_entry(path: Path, expected: str | None = None):
    if not path.is_file():
        raise FileNotFoundError(root_relative(path))
    actual = sha256(path)
    if expected and actual != expected:
        raise ValueError(f"fixed source hash mismatch: {root_relative(path)}")
    return {"path": root_relative(path), "sha256": actual, "bytes": path.stat().st_size}


def fixed_catalog():
    import fault_preview
    fault = fault_preview.catalog()
    forms = vdm_gallery()
    controls = pinned_json(VDM_CONTROLS, "metric-vdm-forms-gallery-v1")
    execution_index()
    pinned_json(BASIN_COMPARISON, "td-basin-treatment-comparison-v1")
    pinned_json(TD_WATER_SURFACE, "td-native-water-surface-prototype-v1")
    pinned_json(TD_CHANNEL_PATHS, "td-native-channel-valley-paths-prototype-v1")
    surface = read_json(SURFACE_MANIFEST)
    if surface.get("schemaVersion") != "surface-review-v1" or not surface.get("generatedFromFixedAllowlist"):
        raise ValueError("surface review manifest schema/allowlist mismatch")
    return {
        "schema": "river-vdm-catalog-v1",
        "generatedFrom": [verify_entry(VDM_FORMS), verify_entry(VDM_CONTROLS), verify_entry(SURFACE_MANIFEST), verify_entry(LEGACY_MANIFEST)],
        "workspaces": [
            {"id": "vdm", "label": "VDM 岩壁工作台", "status": "interactive-preview"},
            {"id": "td", "label": "TD 降雨河网", "status": "saved-dynamic-review"},
            {"id": "basin", "label": "盆地证据", "status": "diagnostic-not-certified"},
            {"id": "fault", "label": "水平走滑断层", "status": "diagnostic-real-cut", "defaults": fault["defaults"], "geometry": fault["geometry"]},
            {"id": "surface", "label": "既有地表案例", "status": "legacy-preserved"},
        ],
        "vdm": {
            "forms": forms,
            "controls": controls,
            "baseConfig": verify_entry(TD_CONFIG),
            "constraints": {
                "amplitude": "0 < amplitude ≤ min(height/4, wall_half_width/2)",
                "wavelength": "wavelength ≥ 4 × maximum adjacent XZ sample distance",
                "curvature": "abs(curvature) ≤ wavelength/2",
                "endDifference": "abs(end difference) ≤ height; non-zero requires interior end fade",
                "direction": "0° east, 90° south; null inherits recipe direction",
            },
        },
        "td": {
            "sources": [verify_entry(TD_ACCEPTANCE), verify_entry(TD_EXECUTION), verify_entry(TD_WATER_SURFACE), verify_entry(TD_CHANNEL_PATHS)],
            "directions": ["eastward", "westward"],
            "nativeGrid": {"rows": 256, "columns": 256, "spacing_m": 30},
            "statesPerDirection": 25,
            "status": "saved states only; no solver replay",
            "semantics": {
                "rainfall": "forcing input; not a water-depth measurement",
                "storage": "saved water volume in m³",
                "signedEdgeQ": "saved face forward/reverse are hourly accumulated volumes in m³; derived net Q is the page mean in m³/s",
                "stage": "water-surface elevation in metres",
            },
        },
        "basin": {
            "source": verify_entry(BASIN_COMPARISON),
            "comparison": read_json(BASIN_COMPARISON),
            "status": "diagnostic; natural outlet not certified",
        },
        "fault": fault,
        "limitations": [
            "VDM preview is a saved/explicit local geometry operation, not natural-outlet certification.",
            "VDM water_generated=false and hydraulic_ready=false in the fixed gallery.",
            "TD charts read saved records; they do not recompute hydrology.",
            "Fault preview performs an explicit real cut in memory; open surface only, no water or solver response.",
        ],
    }


def obj_payload(path: Path):
    vertices, faces = [], []
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "v" and len(fields) >= 4:
            vertices.append([float(x) for x in fields[1:4]])
        elif fields[0] == "f" and len(fields) >= 4:
            faces.append([int(token.split("/")[0]) - 1 for token in fields[1:4]])
    return {"vertices": vertices, "triangles": faces}


def vdm_variant(kind: str, gallery: dict):
    for item in gallery.get("variants", []):
        if item.get("kind") == kind:
            return item
    raise KeyError(f"unknown VDM variant: {kind}")


def vdm_case(kind: str):
    gallery = vdm_gallery()
    variant = vdm_variant(kind, gallery)
    record = variant["vdm"]
    directory = pinned_path(record)
    verify_entry(directory, record["expected_sha256"])
    report_record = variant["report"]
    report_path = pinned_path(report_record)
    report = pinned_json(report_path, "td-channel-vdm-preparation-v1", report_record["expected_sha256"])
    sys.path.insert(0, str(ROOT))
    from terrain_pipeline.metric_vdm_forms import load_formed_vdm
    result = load_formed_vdm(directory, expected_sha256=record["expected_sha256"], expected_identity=record["expected_identity"])
    return {
        "schema": "vdm-case-v1", "kind": kind, "label": variant.get("label", kind),
        "source": {"gallery": verify_entry(VDM_FORMS), "vdm": verify_entry(directory, record["expected_sha256"]), "report": verify_entry(report_path, report_record["expected_sha256"])},
        "identity": result["identity_sha256"], "report": report,
        "mesh": mesh_window(result["arrays"]), "variant": variant, "metadata": result["metadata"],
        "editable": False,
    }


def preview_vdm(body: dict):
    """Build a geometry preview through the protected channel entry point."""
    sys.path.insert(0, str(ROOT))
    import numpy as np
    from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
    from terrain_pipeline.td_native_channel_surface import load_channel_surface
    from terrain_pipeline.metric_vdm import CliffRecipe
    from terrain_pipeline.metric_vdm_forms import FormRecipe
    from terrain_pipeline.td_channel_vdm import build_channel_vdm

    config = read_json(TD_CONFIG)
    verify_entry(TD_CONFIG, vdm_gallery()["configuration"]["expected_sha256"])
    surface_record = config["surface"]
    hierarchy_record = config["hierarchy"]
    surface = load_channel_surface(pinned_path(surface_record), expected_sha256=surface_record["expected_sha256"], expected_identity=surface_record["expected_identity"])
    hierarchy = load_basin_hierarchy(pinned_path(hierarchy_record), expected_sha256=hierarchy_record["expected_sha256"], expected_identity=hierarchy_record["expected_identity"])
    if not isinstance(body, dict) or set(body) != {"form"}:
        raise ValueError("VDM preview requires only a form object")
    form = bounded_form(body["form"])
    recipe_data = dict(config["recipe"])
    recipe = CliffRecipe(center_xz_m=tuple(recipe_data["center_xz_m"]), outward_xz=tuple(recipe_data["outward_xz"]), height_m=recipe_data["height_m"], half_length_m=recipe_data["half_length_m"], half_depth_m=recipe_data["half_depth_m"], wall_half_width_m=recipe_data["wall_half_width_m"], end_fade_m=recipe_data["end_fade_m"], angle_degrees=recipe_data["angle_degrees"], lean=recipe_data["lean"])
    result = build_channel_vdm(surface, hierarchy, recipe=recipe, form=form)
    return {"schema": "vdm-preview-v1", "identity": result["identity_sha256"], "metadata": result["metadata"], "mesh": mesh_window(result["arrays"]), "source": {"surface": surface["identity_sha256"], "hierarchy": hierarchy["identity_sha256"]}, "form": asdict(form)}


def td_page(direction: str, hour: int):
    if direction not in {"eastward", "westward"} or type(hour) is not int or not 0 <= hour < 24:
        raise ValueError("TD direction/hour outside fixed page allowlist")
    index = execution_index()
    scenario = index.get("scenarios", {}).get(direction, {})
    pages = scenario.get("pages", [])
    if len(pages) != 24 or pages[hour].get("hour") != hour:
        raise ValueError("fixed TD page index is incomplete")
    page = pages[hour]
    storage = page["storage"]
    checkpoint = page.get("checkpoint")
    storage_path = pinned_path(storage)
    checkpoint_path = pinned_path(checkpoint) if checkpoint else None
    verify_entry(storage_path, storage["expected_sha256"])
    if checkpoint_path: verify_entry(checkpoint_path, checkpoint["expected_sha256"])
    sys.path.insert(0, str(ROOT))
    import numpy as np
    from terrain_pipeline.td_basin_storage_v10_io import load_storage
    loaded = load_storage(storage_path, expected_sha256=storage["expected_sha256"], expected_identity=storage["expected_identity"])
    arrays, metadata = loaded["arrays"], loaded["metadata"]
    height = arrays["height_m"]
    valid = arrays["valid_mask"]
    if height.shape != (256, 256) or metadata["spacing_m"] != 30:
        raise ValueError("TD native grid contract mismatch")
    depth = arrays["depth_m"].reshape(2, 256, 256)
    rain = arrays["rain_mm_h"].reshape(256, 256)
    faces = arrays["face_cells"]
    forward, reverse = arrays["face_forward_m3"], arrays["face_reverse_m3"]
    duration = metadata["end_s"] - metadata["start_s"]
    # A bounded, regular display sample; totals below always use the full valid native grid.
    stride = 4
    sample = lambda matrix: matrix[::stride, ::stride].tolist()
    cell_area = metadata["spacing_m"] ** 2
    totals = {name: float(np.sum(arrays[name])) for name in ("rain_volume_m3", "rain_infiltration_m3", "rain_excess_m3", "boundary_outflow_m3", "balance_residual_m3")}
    totals.update(surface_water_m3=float(np.sum(depth[1][valid]) * cell_area), soil_water_m3=float(np.sum(arrays["soil_mm"][1].reshape(256, 256)[valid]) * cell_area / 1000), fast_water_m3=float(np.sum(arrays["fast_mm"][1].reshape(256, 256)[valid]) * cell_area / 1000), slow_water_m3=float(np.sum(arrays["slow_mm"][1].reshape(256, 256)[valid]) * cell_area / 1000), forward_m3=float(np.sum(forward)), reverse_m3=float(np.sum(reverse)), net_hourly_mean_q_m3_s=float((np.sum(forward)-np.sum(reverse))/duration), native_wet_cells=int(np.count_nonzero((depth[1] >= .001) & valid)))
    return {"schema": "td-page-v1", "direction": direction, "hour": hour, "source": {"storage": verify_entry(storage_path, storage["expected_sha256"]), "identity": loaded["identity_sha256"], "checkpoint": {"path": root_relative(checkpoint_path), "sha256": checkpoint["expected_sha256"], "identity": checkpoint["expected_identity"]} if checkpoint_path else None, "forcing_identity": page["forcing_identity"]}, "metadata": {"start_s": metadata["start_s"], "end_s": metadata["end_s"], "origin_m_xz": metadata["origin_m_xz"], "spacing_m": metadata["spacing_m"], "grid_shape": [256, 256], "face_count": len(faces)}, "display": {"stride": stride, "spacing_m": 120, "threshold_m": .001, "sample_semantics": "every fourth native cell for drawing only; unsampled cells are not dry", "height_m": sample(height), "valid_mask": sample(valid), "start_depth_m": sample(depth[0]), "end_depth_m": sample(depth[1]), "rain_mm_h": sample(rain)}, "totals": totals, "flux": {"semantics": "full native face forward/reverse volumes accumulated over this hour; net Q is hourly mean, not instantaneous", "forward_m3": totals["forward_m3"], "reverse_m3": totals["reverse_m3"], "net_hourly_mean_q_m3_s": totals["net_hourly_mean_q_m3_s"]}, "status": "accepted temporal refinement in bounded scope; display sampling only; no fine-bed hydraulics or natural outlet certification"}


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "TerragenesisBridge/1.0"

    def send_json(self, value, status=200):
        data = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            path = urlparse(self.path).path
            if path == "/api/fault/case":
                if urlparse(self.path).query:
                    return self.send_json({"error": "fault case accepts no client parameters"}, 400)
                import fault_preview
                return self.send_json(fault_preview.fault_case())
            if path == "/api/saved/catalog":
                import saved_surface
                return self.send_json(saved_surface.catalog())
            if path.startswith("/api/saved/"):
                import saved_surface
                match = re.fullmatch(r"/api/saved/(frame|array)/(amr|native|uniform)/([a-z0-9-]+)/(\d{1,2})(?:/([a-z_]+))?", path)
                if not match:
                    return self.send_json({"error": "unknown saved route"}, 404)
                action, package, scenario, index, name = match.groups()
                if action == "frame" and name is None:
                    return self.send_json(saved_surface.descriptor(package, scenario, int(index)))
                if action != "array" or name is None:
                    return self.send_json({"error": "unknown saved route"}, 404)
                data = saved_surface.binary(package, scenario, int(index), name)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return self.wfile.write(data)
            if path == "/api/catalog":
                return self.send_json(fixed_catalog())
            if path.startswith("/api/vdm/case/"):
                kind = path.rsplit("/", 1)[-1]
                if not re.fullmatch(r"[a-z_]+", kind):
                    return self.send_json({"error": "invalid VDM case name"}, 400)
                return self.send_json(vdm_case(kind))
            if path == "/api/vdm/gallery":
                return self.send_json(vdm_gallery())
            if path == "/api/td/catalog":
                return self.send_json(fixed_catalog()["td"])
            if path.startswith("/api/td/page/"):
                match = re.fullmatch(r"/api/td/page/(eastward|westward)/(\d{1,2})", path)
                if not match:
                    return self.send_json({"error": "TD direction/hour outside fixed allowlist"}, 400)
                return self.send_json(td_page(match.group(1), int(match.group(2))))
            if path == "/api/basin/comparison":
                return self.send_json(fixed_catalog()["basin"])
            return self.static(path)
        except Exception as error:
            return self.send_json({"error": str(error), "type": type(error).__name__}, 500)

    def do_POST(self):
        try:
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            if path == "/api/fault/preview" and not 0 <= length <= 16 * 1024:
                raise ValueError("request body budget exceeded")
            body = json.loads(self.rfile.read(length) or b"{}")
            if path == "/api/vdm/preview":
                return self.send_json(preview_vdm(body))
            if path == "/api/fault/preview":
                if urlparse(self.path).query:
                    raise ValueError("fault preview accepts no query parameters")
                import fault_preview
                return self.send_json(fault_preview.preview_fault(body))
            if path == "/api/fault/draft":
                draft = {"schema": "strike-slip-fault-draft-v1", "status": "deprecated-legacy-draft", "deprecated": True, "draft": body, "limitations": ["Legacy draft only; use /api/fault/case and /api/fault/preview for real cuts", "No mesh cut performed by this endpoint", "Water is not moved"]}
                return self.send_json(draft)
            if path == "/api/export":
                return self.send_json({"schema": "surface-review-export-v2", "status": "client-download-only", "record": body})
            return self.send_json({"error": "unknown endpoint"}, 404)
        except Exception as error:
            return self.send_json({"error": str(error), "type": type(error).__name__}, 400)

    def static(self, request_path):
        relative = request_path.lstrip("/") or "index.html"
        allowed = {"index.html", "app.js", "renderer.js", "style.css", "saved-surface.js", "fault-surface.js",
            "vendor/node_modules/three/build/three.module.js", "vendor/node_modules/three/build/three.core.js",
            "vendor/node_modules/three/examples/jsm/controls/OrbitControls.js"}
        if relative.startswith("data/surface-review-v1/"):
            manifest = read_json(SURFACE_MANIFEST)
            allowed |= {"data/surface-review-v1/" + item["file"] for item in manifest["cases"]}
            allowed.add("data/surface-review-v1/manifest.json")
        if relative.startswith("data/"):
            legacy = read_json(LEGACY_MANIFEST)
            if isinstance(legacy, list):
                allowed |= {"data/" + item["file"] for item in legacy}
            allowed.add("data/manifest.json")
        if relative not in allowed:
            return self.send_json({"error": "resource not allowlisted"}, 403)
        target = (WEB / relative).resolve()
        if WEB not in target.parents and target != WEB:
            return self.send_json({"error": "forbidden"}, 403)
        if not target.is_file():
            return self.send_json({"error": "not found"}, 404)
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        print(f"{self.address_string()} - {format % args}", flush=True)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Terragenesis bridge: http://127.0.0.1:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
