"""Read-only real-TD morphology candidate package for the local review UI."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrain_pipeline.common_infra import load_bundle
from terrain_pipeline.surface_rivers.metric_delta_product import load_delta_candidate_product
from terrain_pipeline.channel_geometry import load_cutoff_material_candidate
from terrain_pipeline.surface_rivers.metric_morphology_product import load_morphology_proposal
from tools.prepare_td_stage_review import supplemental_summary

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "verification/td-morphology-candidates/td256-20261010-01"
MAX_BYTES = 128 * 1024 * 1024
STAGE_MANIFEST = ROOT / "web-preview/data/natural-stage-review-v1/manifest.json"


def _stage_review():
    if not STAGE_MANIFEST.exists():
        return None
    manifest = _json(STAGE_MANIFEST)
    if manifest.get("schema") != "td-natural-stage-review-pin-v1" or manifest.get("publishable") is not False:
        raise ValueError("invalid stage review manifest")
    products = {}
    for name, pin in manifest["artifacts"].items():
        path = (ROOT / pin["path"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or path.stat().st_size > MAX_BYTES or _sha256(path) != pin["sha256"]:
            raise ValueError("stage review evidence pin mismatch: " + name)
        products[name] = load_cutoff_material_candidate(path, expected_sha256=pin["sha256"]) if name == "cutoff" else _json(path)
    cutoff = products["cutoff"]
    if cutoff["identity_sha256"] != manifest["artifacts"]["cutoff"]["identity_sha256"]:
        raise ValueError("stage cutoff identity mismatch")
    if products["stage3"].get("schema") != "td-stage3-native-morphology-evidence-v1" or products["stage3"].get("status") != "accepted_candidate_contracts":
        raise ValueError("stage3 review schema/status mismatch")
    if products["stage4"].get("schema") != "td-stage4-falsification-v1" or not products["stage4"].get("status", "").startswith("completed_bounded"):
        raise ValueError("stage4 review schema/status mismatch")
    stage3_path = ROOT / manifest["artifacts"]["stage3"]["path"]
    bound = products["stage3"]["artifacts"]["cutoff_material"]
    if (stage3_path.parent / bound["path"]).resolve() != (ROOT / manifest["artifacts"]["cutoff"]["path"]).resolve() or bound["sha256"] != manifest["artifacts"]["cutoff"]["sha256"]:
        raise ValueError("stage3 report and cutoff pin disagree")
    supplements = {}
    for name, pin in manifest.get("supplemental_reports", {}).items():
        path = (ROOT / pin["path"]).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or path.stat().st_size > MAX_BYTES or _sha256(path) != pin["sha256"]:
            raise ValueError("supplemental report pin mismatch: " + name)
        report = _json(path)
        if not isinstance(report, dict) or report.get("schema") != pin["schema"] or report.get("status") != pin["status"]:
            raise ValueError("supplemental report schema/status mismatch: " + name)
        if supplemental_summary(report) != pin.get("summary"):
            raise ValueError("supplemental report summary mismatch: " + name)
        supplements[name] = {"pin": pin, "report": report,
                             "semantics": "independent saved evidence; no candidate capability promotion"}
    products["supplemental_reports"] = supplements
    products["proposals"] = {}
    products["independent_evidence"] = {}
    for name, evidence in products["stage3"].get("linked_evidence", {}).items():
        report_path = Path(evidence["report_path"]).resolve()
        if not report_path.is_relative_to(ROOT) or _sha256(report_path) != evidence["report_sha256"]:
            raise ValueError("linked stage report pin changed: " + name)
        pins = evidence.get("products", [])
        if "product_path" in evidence:
            pins = [*pins, {"path": evidence["product_path"], "sha256": evidence["product_sha256"]}]
        for pin in pins:
            path = Path(pin["path"]).resolve()
            if not path.is_relative_to(ROOT) or _sha256(path) != pin["sha256"]:
                raise ValueError("linked stage product pin changed: " + name)
        products["independent_evidence"][name] = {"scope": evidence["scope"], "pins": evidence,
                                                  "report": _json(report_path)}
    for kind in ("delta", "cutoff", "bank_pointbar", "braided", "alluvial_fan", "floodplain"):
        for suffix in ("", "_rejected"):
            name = kind + suffix
            pin = products["stage3"]["artifacts"][name]
            path = (stage3_path.parent / pin["path"]).resolve()
            if not path.is_relative_to(ROOT):
                raise ValueError("stage morphology proposal outside workspace")
            proposal = load_morphology_proposal(path, expected_sha256=pin["sha256"])
            if proposal["identity_sha256"] != pin["identity_sha256"]:
                raise ValueError("stage morphology proposal identity mismatch")
            products["proposals"][name] = proposal
    return {"manifest": manifest, **products}


def _review_summary(value):
    if isinstance(value, dict):
        return {key: _review_summary(item) for key, item in value.items()}
    if isinstance(value, list):
        if len(value) > 16 and all(isinstance(item, (int, float, bool)) for item in value):
            return {"saved_count": len(value), "first_values": [_review_summary(item) for item in value[:5]],
                    "last_values": [_review_summary(item) for item in value[-5:]],
                    "semantics": "display excerpt; full observations remain in pinned report"}
        return [_review_summary(item) for item in value]
    return value


def _stage_case(stage):
    product = stage["cutoff"]
    arrays, metadata = product["arrays"], product["metadata"]
    terrain = metadata["terrain_metadata"]
    source_path = Path(terrain["source_path"]).resolve()
    if not source_path.is_relative_to(ROOT) or _sha256(source_path) != terrain["source_sha256"]:
        raise ValueError("stage cutoff TD source pin changed")
    if terrain["dx_m"] != terrain["dz_m"]:
        raise ValueError("morphology display requires saved square grid spacing")
    candidates = {}
    candidate = {"status": metadata["status"], "event": metadata["event_record"],
                 "capabilities": metadata["capabilities"], "material_ledger": metadata.get("material_ledger"),
                 "failure_reason": metadata.get("failure_reason"), "revalidation_required": metadata["revalidation_required"]}
    if metadata["status"] == "candidate":
        candidate.update(height_delta_m=(arrays["after_bed_m"] - arrays["terrain_elevation_m"]).tolist(),
                         after_bed_m=arrays["after_bed_m"].tolist(),
                         shortcut_xz_m=arrays["shortcut_xz_m"].tolist(), loop_xz_m=arrays["loop_xz_m"].tolist(),
                         deposit_mask=(arrays["fill_bulk_m3"] > 0).tolist(), erosion_mask=(arrays["cut_depth_m"] > 0).tolist())
    candidates["cutoff"] = candidate
    failure_cases = {}
    for kind, proposal in stage["proposals"].items():
        pa, pm = proposal["arrays"], proposal["metadata"]
        if kind.endswith("_rejected"):
            failure_cases[kind] = {"identity_sha256": proposal["identity_sha256"], "metadata": pm}
            continue
        if pm["terrain_identity_sha256"] != metadata["terrain_identity_sha256"]:
            raise ValueError("different morphology terrain cannot share display grid")
        if kind == "cutoff":
            continue
        result = dict(pm["result"])
        for name, value in pa.items():
            if name.startswith("result_"):
                result[name.removeprefix("result_")] = value.tolist()
        result.update(status=pm["status"], event=pm["result"].get("event_record"),
                      material_ledger=pm["result"].get("event_record", {}).get("material_ledger"),
                      capabilities=pm["capabilities"], parent_graph_identity_sha256=pm["parent_graph_identity_sha256"],
                      parent_geometry_identity_sha256=pm["parent_geometry_identity_sha256"],
                      identity_sha256=proposal["identity_sha256"])
        if "height_delta_m" in result:
            result["after_bed_m"] = (pa["terrain_elevation_m"] + pa["result_height_delta_m"]).tolist()
        candidates[{"bank_pointbar": "bank", "alluvial_fan": "fan"}.get(kind, kind)] = result
    stocks = {name: arrays[name].tolist() for name in arrays if name.endswith("_m3") or "hypsometry" in name}
    source = {"path": terrain.get("source_path"), "sha256": terrain["source_sha256"],
              "identity": terrain["source_id"], "vertical_datum": terrain["vertical_datum"]}
    displayed_stage4 = _review_summary(stage["stage4"])
    full_stage4 = stage["stage4"]
    if stage.get("supplemental_reports"):
        full_stage4 = {**full_stage4, "supplemental_reports": stage["supplemental_reports"]}
        displayed_stage4 = {**displayed_stage4, "supplemental_reports": {
            name: {"pin": {key: item["pin"][key] for key in ("path", "sha256", "schema", "status")},
                   "summary": _review_summary(item["pin"]["summary"]), "semantics": item["semantics"]}
            for name, item in stage["supplemental_reports"].items()}}
    review = {"schema": "td-natural-stage-review-v1", "pins": stage["manifest"]["artifacts"],
              "stage3": stage["stage3"], "stage4": displayed_stage4, "cutoff_metadata": metadata,
              "stage4_full_report": full_stage4,
              "failure_cases": failure_cases,
              "independent_evidence": stage["independent_evidence"],
              "stocks": stocks, "time_semantics": "static saved proposal; no physical time advancement",
              "display_geometry": "saved native before/after arrays; candidate not written to RoutingGraph",
              "water_semantics": "residual stocks and level-pool proposal; no certified water surface"}
    if stage["manifest"].get("supplemental_reports"):
        review["supplemental_report_pins"] = stage["manifest"]["supplemental_reports"]
    return {"schema": "td-real-morphology-frontend-v1", "status": metadata["status"],
            "summary_body_sha256": product["identity_sha256"], "source": source,
            "terrain": {"height_m": arrays["terrain_elevation_m"].tolist(), "valid_mask": arrays["terrain_valid_mask"].tolist(),
                        "origin_x_m": terrain["x0_m"], "origin_z_m": terrain["z0_m"],
                        "spacing_m": terrain["dx_m"], "coordinates": "X east/Y up/Z south; metres; cells[z,x]"},
            "parent_graph_identity_sha256": metadata["parent_graph_identity_sha256"],
            "parent_geometry_identity_sha256": metadata["parent_geometry_identity_sha256"],
            "terrain_identity_sha256": metadata["terrain_identity_sha256"],
            "interpretation": "阶段3截弯库存候选；显式旧槽与材料情景，未写回拓扑，水面和自然出口未认证",
            "capabilities": metadata["capabilities"], "candidates": candidates, "stage_review": review}


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _path(name):
    path = (BASE / name).resolve()
    if not path.is_relative_to(BASE) or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("morphology artifact outside fixed package")
    return path


def _read_bundle(name, pin):
    path = _path(name)
    if _sha256(path) != pin["sha256"]:
        raise ValueError("morphology artifact SHA256 mismatch: " + name)
    return load_bundle(path, expected_sha256=pin["sha256"], validator=lambda value: None)


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _generic(name, summary):
    return _read_bundle(summary["artifacts"][name]["path"], summary["artifacts"][name])


def _event(metadata):
    return _plain(metadata.get("event_record"))


def catalog():
    stage = _stage_review()
    if stage is not None:
        payload = _stage_case(stage)
        return {key: payload[key] for key in ("schema", "status", "source", "summary_body_sha256",
                "parent_graph_identity_sha256", "parent_geometry_identity_sha256", "terrain_identity_sha256",
                "interpretation", "capabilities")} | {"candidates": list(payload["candidates"]), "package": str(STAGE_MANIFEST.relative_to(ROOT))}
    summary = _json(BASE / "summary.json")
    body = dict(summary)
    expected_body_sha = body.pop("summary_body_sha256", None)
    actual_body_sha = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                               indent=2, allow_nan=False).encode("utf-8")).hexdigest()
    if expected_body_sha != actual_body_sha or summary.get("schema") != "td-real-morphology-candidate-set-v1":
        raise ValueError("morphology summary identity mismatch")
    source = Path(summary["source"]["path"]).resolve()
    if not source.is_relative_to(ROOT) or _sha256(source) != summary["source"]["sha256"]:
        raise ValueError("TD source pin changed")
    return {
        "schema": "td-real-morphology-catalog-v1",
        "status": summary["status"],
        "package": "verification/td-morphology-candidates/td256-20261010-01",
        "source": summary["source"],
        "summary_body_sha256": expected_body_sha,
        "parent_graph_identity_sha256": summary["parent_graph_identity_sha256"],
        "parent_geometry_identity_sha256": summary["parent_geometry_identity_sha256"],
        "terrain_identity_sha256": summary["terrain_identity_sha256"],
        "interpretation": summary["interpretation"],
        "capabilities": summary["capabilities"],
        "candidates": ["delta", "cutoff", "bank_pointbar", "braided", "alluvial_fan", "floodplain"],
    }


def _candidate_paths(arrays, metadata):
    encoded = arrays["candidate_polylines"]
    lengths = arrays["candidate_lengths"]
    edge_ids = metadata["candidate_edge_ids"]
    return [{"edge_id": edge_ids[index], "polyline": encoded[index, :int(lengths[index])].tolist()}
            for index in range(len(edge_ids))]


def saved_case():
    stage = _stage_review()
    if stage is not None:
        return _stage_case(stage)
    summary_path = BASE / "summary.json"
    summary = _json(summary_path)
    body = dict(summary)
    expected_body_sha = body.pop("summary_body_sha256", None)
    actual_body_sha = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                               indent=2, allow_nan=False).encode("utf-8")).hexdigest()
    if expected_body_sha != actual_body_sha or summary.get("schema") != "td-real-morphology-candidate-set-v1":
        raise ValueError("morphology summary identity mismatch")
    source = Path(summary["source"]["path"]).resolve()
    if not source.is_relative_to(ROOT) or _sha256(source) != summary["source"]["sha256"]:
        raise ValueError("TD source pin changed")
    inputs = _generic("inputs", summary)
    input_arrays, input_metadata = inputs["arrays"], inputs["metadata"]
    candidates = {}
    delta_pin = summary["artifacts"]["delta"]
    delta = load_delta_candidate_product(_path(delta_pin["path"]), expected_sha256=delta_pin["sha256"])
    if delta["identity_sha256"] != delta_pin["identity_sha256"]:
        raise ValueError("delta candidate identity mismatch")
    delta_arrays, delta_metadata = delta["arrays"], delta["metadata"]
    candidates["delta"] = {
        "status": delta_metadata["status"], "height_delta_m": delta_arrays["height_delta_m"].tolist(),
        "deposit_mask": delta_arrays["deposit_mask"].tolist(),
        "water_component_mask": delta_arrays["water_component_mask"].tolist(),
        "distributary_candidates": _candidate_paths(delta_arrays, delta_metadata),
        "event": _plain(delta_metadata["event_record"]),
        "material_ledger": _plain(delta_metadata["material_ledger"]),
    }
    for name, output_name, array_names in (
        ("cutoff", "cutoff", ("shortcut_xz_m", "loop_xz_m")),
        ("bank_pointbar", "bank", ("height_delta_m", "erosion_mask", "deposit_mask")),
        ("braided", "braided", ("bar_mask", "height_delta_m", "flow_split")),
        ("alluvial_fan", "fan", ("height_delta_m", "deposit_mask", "footprint")),
        ("floodplain", "floodplain", ("inundation_mask", "height_delta_m")),
    ):
        bundle = _generic(name, summary)
        arrays, metadata = bundle["arrays"], bundle["metadata"]
        value = {"status": metadata["status"], "event": _event(metadata),
                 "capabilities": _plain(metadata.get("capabilities", {}))}
        for array_name in array_names:
            value[array_name] = arrays[array_name].tolist()
        for metadata_name in ("material_ledger", "storage_proxy_m3", "candidate_paths", "solid_ledger"):
            if metadata_name in metadata:
                value[metadata_name] = _plain(metadata[metadata_name])
        candidates[output_name] = value
    return {
        "schema": "td-real-morphology-frontend-v1", "status": summary["status"],
        "summary_body_sha256": expected_body_sha, "source": summary["source"],
        "terrain": {"height_m": input_arrays["terrain_elevation_m"].tolist(),
                     "valid_mask": input_arrays["terrain_valid_mask"].tolist(),
                     "origin_x_m": input_metadata["origin_x_m"], "origin_z_m": input_metadata["origin_z_m"],
                     "spacing_m": input_metadata["spacing_m"], "coordinates": input_metadata["coordinates"]},
        "land_mask": input_arrays["land_mask"].tolist(), "water_mask": input_arrays["water_mask"].tolist(),
        "delta_path_cells": input_arrays["delta_path_cells"].tolist(),
        "centerline_xz_m": input_arrays["centerline_xz_m"].tolist(),
        "parent_graph_identity_sha256": summary["parent_graph_identity_sha256"],
        "parent_geometry_identity_sha256": summary["parent_geometry_identity_sha256"],
        "terrain_identity_sha256": summary["terrain_identity_sha256"],
        "interpretation": summary["interpretation"], "capabilities": summary["capabilities"],
        "candidates": candidates,
    }
