"""Build fixed, offline surface-review data from accepted saved bundles.

The browser never imports NPZ files or invokes a prepare/recovery/advance path.
Only the explicitly listed evidence bundles below are allowed.
"""
from __future__ import annotations

import hashlib
import argparse
from datetime import datetime, timezone
import json
import math
import sys
import os
import tempfile
from functools import lru_cache
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.dem_domain import load_dem_candidate
from terrain_pipeline.surface_coast_drop import load_coast_drop
from terrain_pipeline.surface_domain_mosaic import load_domain_mosaic
from terrain_pipeline.surface_multidomain_dynamic import load_surface_multidomain_dynamic
from terrain_pipeline.surface_variable_storage import load_surface_variable_storage
from terrain_pipeline.surface_engineering_prepare import load_surface_engineering, query_surface_engineering
from terrain_pipeline.surface_fine_mosaic import load_fine_mosaic
from terrain_pipeline.surface_land_coverage import load_surface_land_coverage, query_surface_land_coverage

OUT = Path(__file__).resolve().parent / "data" / "surface-review-v1"

FIXED = {
    "mosaic": ROOT / "verification/surface-domain-mosaic/run-20260930T170535.835312Z/two-domain-dry-extension.npz",
    "pulse": ROOT / "verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/pulse.npz",
    "tailwater": ROOT / "verification/surface-multidomain-dynamic/run-20260930T170705.875509Z/domain2-tailwater-rise.npz",
    "coast": ROOT / "verification/surface-coast-drop/run-20260930T125523.932019Z/actual-river-engineering-coast.npz",
    "dem": ROOT / "verification/dem-domain/run-20260930T062026836139Z/dem-candidate.npz",
}
VARIABLE_RUN = ROOT / "verification/surface-variable-storage/run-20260930T192708.659151Z"
ENGINEERING = ROOT / "verification/surface-engineering-prepare/run-20260930T193214454541Z/two-domain-engineering.npz"
SEAM = ROOT / "verification/surface-fine-mosaic/run-20260930T123659.258177Z/wet-cross-precision.npz"
LAND = ROOT / "verification/surface-land-coverage/run-20260930T200657434780Z/two-domain-land-coverage.npz"
EXPECTED = {
    FIXED["mosaic"]: "c1a39c6f6fee25c631e26548e49799004bbdec9ba457f2f66b6ce879d6f9df65",
    FIXED["pulse"]: "c85e8ef84b896df2f2f3e48d2c062bc9b9c0ddd66d4cf0b56320ef6cc6ea16cd",
    FIXED["tailwater"]: "5256af08a0b8d1c5dc7963a4a873dbfdf0c105c70fca82fbe5562bf4940a967c",
    FIXED["coast"]: "0e896c7832b36d79d4596d7a4b8894b67f5f92fcf6b252c8735943e5e3115313",
    FIXED["dem"]: "d081ff6439a4d8bd57add2e6316096009a57b197f27e4ad7a93608f1bcd605b3",
    ENGINEERING: "30f011385e72d346475ec1f6f0c71f74da216a238f38628c4b0668741628097e",
    SEAM: "6195a9bffcf464924e562a74a83650085b570bad8a38b1c0aaf42c37f58b840c",
    LAND: "3867c0f04aab78fe8e0abd8fda6ed409fa599dc7f1b217ac021987223632eba1",
    **{VARIABLE_RUN / name: digest for name, digest in {
        "baseline.npz": "f903945978b69756c0a7b429c4a596e4b4d504ff1dd7b66d0f9226ce609f0916",
        "pulse.npz": "392ea3fad66827fa8a3acd43301627b86ca6a4a186ea9994a2d34b32322e6c63",
        "domain2-tailwater-rise.npz": "e2684b14c01c8554e27ad035243ed0f874de8c0326b5a99825920ac14b5f848c",
        "failed-prefix.npz": "ed22c413554ac5ff08704804c4f952ba323920b5ab5fea65fabe3240b2caa96a",
        "cancelled-prefix.npz": "7433612d5b71bda363a845c3ed8224e1b37a66aed95b547e8df6a2dfaa0b57fa"}.items()}}


def saved(path):
    if sha256(path) != EXPECTED[path]:
        raise ValueError("fixed source hash mismatch: " + str(path))
    return _saved(path)


@lru_cache(maxsize=16)
def _saved(path):
    loader = (load_surface_variable_storage if path.parent == VARIABLE_RUN else
              load_surface_land_coverage if path == LAND else
              load_surface_engineering if path == ENGINEERING else
              load_fine_mosaic if path == SEAM else
              load_domain_mosaic if path == FIXED["mosaic"] else
              load_coast_drop if path == FIXED["coast"] else load_surface_multidomain_dynamic)
    return loader(path)


def checked_evidence(path, identity, *, diagnostic=False):
    report_path, review_path = path.parent / "report.json", path.parent / "independent-review.json"
    report = read_json(report_path)
    if report.get("status") not in ("passed", "diagnostic", "prepared") and path != FIXED["dem"]:
        raise ValueError("source verifier has not passed")
    matches = []
    def visit(value):
        if isinstance(value, dict):
            if (value.get("identity_sha256") == identity and
                    value.get("file_sha256", value.get("bundle_file_sha256")) == EXPECTED[path]):
                referenced = value.get("path", value.get("bundle"))
                if referenced is not None and Path(referenced).name != path.name:
                    raise ValueError("report binds different bundle path")
                matches.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(report)
    review = read_json(review_path) if review_path.exists() else {}
    if diagnostic and (report.get("package_sha256") != EXPECTED[path] or
                       report.get("manifest", {}).get("identity_sha256") != identity):
        raise ValueError("diagnostic report identity/hash mismatch")
    if not diagnostic and not matches:
        raise ValueError("report does not bind bundle hash and identity")
    for name in ("bundle_sha256", "bundle_file_sha256"):
        claimed = review.get(name)
        if isinstance(claimed, dict):
            claimed = claimed.get(path.name)
        if claimed is not None and claimed != EXPECTED[path]:
            raise ValueError("review bundle hash mismatch")
    claimed_identity = review.get("bundle_identity_sha256", review.get("identity_sha256"))
    if claimed_identity is not None and claimed_identity != identity:
        raise ValueError("review identity mismatch")
    if review.get("report_file_sha256") not in (None, sha256(report_path)):
        raise ValueError("review report hash mismatch")
    if review.get("artifact_sha256", {}).get(path.name, EXPECTED[path]) != EXPECTED[path]:
        raise ValueError("diagnostic review bundle hash mismatch")
    if path == ENGINEERING:
        display = path.parent / "engineering-review.json"
        if (sha256(display) != "b0b80285d003e348538078ee3dc2ccb2804897f561eaad55e14b7d5074f01230" or
                report.get("display", {}).get("file_sha256") != sha256(display) or
                read_json(display).get("identity_sha256") != identity):
            raise ValueError("engineering display evidence mismatch")
    accepted = review.get("status", "").startswith("accepted") or review.get("accepted") is True
    return {"status": "diagnostic_candidate" if diagnostic else "accepted_bounded_scope" if accepted else "pending_review",
            "reportFiles": [source(item) for item in (report_path, review_path) if item.exists()],
            "reports": [report, review]}
REPORTS = {
    "mosaic": FIXED["mosaic"].parent / "report.json",
    "mosaicReview": FIXED["mosaic"].parent / "independent-review.json",
    "dynamic": FIXED["pulse"].parent / "report.json",
    "dynamicReview": FIXED["pulse"].parent / "independent-review.json",
    "coast": FIXED["coast"].parent / "report.json",
    "coastReview": FIXED["coast"].parent / "independent-review.json",
    "dem": FIXED["dem"].parent / "report.json",
    "demReview": FIXED["dem"].parent / "independent-review.json",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def scalar(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    return value


def array(value: np.ndarray, *, stride: int = 1, null_nonfinite: bool = False) -> Any:
    value = np.asarray(value)
    if stride > 1 and value.ndim >= 2:
        value = value[::stride, ::stride]
    if value.dtype.kind in "biu":
        return value.tolist()
    result = value.tolist()
    if null_nonfinite:
        def clean(item):
            if isinstance(item, list):
                return [clean(child) for child in item]
            if isinstance(item, float) and not math.isfinite(item):
                return None
            return item
        return clean(result)
    return result


def plain(value: Any, *, stride: int = 1, null_nonfinite: bool = False) -> Any:
    if isinstance(value, np.ndarray):
        return array(value, stride=stride, null_nonfinite=null_nonfinite)
    if isinstance(value, Mapping):
        return {str(k): plain(v, stride=stride, null_nonfinite=null_nonfinite) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v, stride=stride, null_nonfinite=null_nonfinite) for v in value]
    return scalar(value)


def source(path: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path), "bytes": path.stat().st_size}


def evidence(case: str, algorithm: str, status: str, scope: str, reports: list[str], **extra: Any) -> dict[str, Any]:
    resolved = []
    for name in reports:
        path = REPORTS[name]
        if not path.is_file() and "Review" in name:
            continue
        if not path.is_file():
            raise FileNotFoundError(f"missing evidence report: {path}")
        try:
            resolved.append(plain(read_json(path)))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid evidence report: {path}") from error
    source_path = ROOT / extra["source"]["path"]
    if sha256(source_path) != EXPECTED[source_path]:
        raise ValueError("source hash mismatch")
    return {"caseId": case, "algorithm": algorithm, "scope": scope,
            **extra, **checked_evidence(source_path, extra["artifactIdentity"], diagnostic=status=="diagnostic_candidate")}


def build_mosaic() -> dict[str, Any]:
    record = saved(FIXED["mosaic"])
    nodes = record["nodes"]
    rows, cols = record["grid"]["shape_cells_zx"]
    mesh = {"vertices": [[float(x), float(h), float(z)] for x, h, z in zip(nodes["x_m"], nodes["h0_m"], nodes["z_m"])],
            "h0": array(nodes["h0_m"]), "bed": array(nodes["h2_m"]), "water": array(nodes["water_surface_m"]),
            "wet": array(nodes["wet_mask"]), "protected": array(nodes["protected_mask"]),
            "cells": array(record["cells"]), "triangles": array(record["triangles"]),
            "wetCells": array(record["wet_cells"]), "hydrologicOwner": array(record["hydrologic_domain_owner"]),
            "cellOwner": array(record["cell_owner"]),
            "contributors": plain(record["contributors"]),
            "grid": plain(record["grid"]), "rows": rows, "columns": cols,
            "sourceKinds": plain(record["source_kinds"]), "extensionCellCount": int(record["extension_cell_count"])}
    return {"schemaVersion": "surface-review-v1", "caseId": "two-domain-mosaic", "kind": "mesh",
            "evidence": evidence("two-domain-mosaic", "surface-domain-mosaic-v1", "accepted_bounded_scope",
                                  "declared rectangular node envelope; 600 dry unchanged-H0 extension cells; not complete physical footprint",
                                  ["mosaic", "mosaicReview"], source=source(FIXED["mosaic"]), artifactIdentity=record.get("identity_sha256"),
                                  coordinates={"system": "metric-xz-m", "axes": "x,height,z", "datum": "local metre datum", "units": "m"},
                                  bounds=plain(record["grid"]["bbox_xz_m"]), summary=plain(record["summary"])), "mesh": mesh,
            "overlay": {"candidateFootprint": [5, 145, 5, 75], "mosaicEnvelope": [10, 140, 10, 70], "missingOuterAreaM2": 2000,
                        "sharedBoundaryX": 75, "coastOverlapZ": [70, 75]}}


def dynamic_case(path: Path, case_id: str, label: str) -> dict[str, Any]:
    record = saved(path)
    dynamic = record["dynamic"]
    inputs = dynamic["inputs"]
    return {"schemaVersion": "surface-review-v1", "caseId": case_id, "kind": "dynamic",
            "label": label, "evidence": evidence(case_id, "surface-multidomain-dynamic-v1", "accepted_bounded_scope",
            "two independent graph components; saved committed prefix only; lumped graph state, not fine-grid dynamic water surface",
            ["dynamic", "dynamicReview"], source=source(path), artifactIdentity=record.get("identity_sha256"),
            coordinates={"system": "metric-xz-m", "axes": "x,height,z", "datum": "candidate vertical datum", "units": "m"},
            limitations=["fixed area A0", "linear K", "no momentum, V(h), tides, or natural outlet certification"]),
            "graph": {"nodeKeys": array(record["node_keys"]), "coords": array(inputs["coords_m"]), "bed": array(inputs["bed_m"]),
                      "edges": array(record["edges"]), "boundary": array(inputs["boundary_mask"]), "domainIds": plain(record["domain_ids"]),
                      "nodeOffsets": array(record["node_offsets"]), "edgeOffsets": array(record["edge_offsets"])},
            "timeseries": {"timeSeconds": array(dynamic["time_s"]), "stages": array(dynamic["stage_m"]),
                           "storages": array(dynamic["storage_m3"]), "signedEdgeQ": array(dynamic["qedges_m3_s"]),
                           "globalLedger": array(dynamic["ledger_m3"]), "domainLedgers": array(record["domain_ledger_m3"]),
                           "committedSteps": int(dynamic["committed_steps"]), "dtSeconds": float(inputs["dt_s"]),
                           "ledgerColumns": ["before", "local", "boundary inward", "after", "change", "residual"]}}


def build_coast() -> dict[str, Any]:
    record = saved(FIXED["coast"])
    a = record["arrays"]
    return {"schemaVersion": "surface-review-v1", "caseId": "domain1-coast-drop", "kind": "coast",
            "evidence": evidence("domain1-coast-drop", "surface-coast-drop-v1", "accepted_engineering_slice",
                                  "continuous saved domain1 river engineering strip to synthetic sea; natural outlet and real coast not certified",
                                  ["coast", "coastReview"], source=source(FIXED["coast"]), artifactIdentity=record.get("identity_sha256"),
                                  coordinates={"system": "metric-xz-m", "axes": "x,height,z", "datum": "local metre datum", "units": "m"},
                                  limitations=["synthetic sea side", "static reference geometry", "no natural outlet certification"]),
            "mesh": {"bedVertices": array(a["bed_xyz_m"]), "waterVertices": array(a["water_xyz_m"]), "triangles": array(a["triangles"]),
                     "centerline": array(a["centerline_xyz_m"]), "h0": array(a["h0_m"]), "attachment": plain(record["attachment"]), "ledger": plain(record["ledger"])}}


def build_dem() -> dict[str, Any]:
    if sha256(FIXED["dem"]) != EXPECTED[FIXED["dem"]]:
        raise ValueError("DEM source hash mismatch")
    candidate = load_dem_candidate(FIXED["dem"], verify_source=False)
    manifest = candidate["manifest"]
    a = candidate["arrays"]
    stride = 2
    return {"schemaVersion": "surface-review-v1", "caseId": "dem-candidate", "kind": "dem",
            "evidence": evidence("dem-candidate", manifest["identity"]["algorithm"], "diagnostic_candidate",
                                  "real DEM candidate with unknown coverage; not publishable, not joined to synthetic scenes, no hydrology replay",
                                  ["dem", "demReview"], source=source(FIXED["dem"]), artifactIdentity=manifest["identity_sha256"],
                                  coordinates={"system": "EPSG:32651", "axes": "X=easting; Z=-northing; rows south", "datum": "unknown vertical datum", "units": "m"},
                                  limitations=manifest["summary"]["blockers"]),
            "grid": plain(manifest["identity"]["grid"]), "recipe": plain(manifest["identity"]["recipe"]),
            "display": {"stride": stride, "sourceShape": list(a["height_m"].shape), "height": array(a["height_m"], stride=stride, null_nonfinite=True),
                        "valid": array(a["valid_mask"], stride=stride), "unknown": array(a["unknown_mask"], stride=stride),
                        "core": array(a["core_mask"], stride=stride), "footprint": array(a["footprint_mask"], stride=stride),
                        "unknownCount": int(a["unknown_mask"].sum()), "coreUnknownCount": int((a["unknown_mask"] & a["core_mask"]).sum())}}


def variable_case(path, case_id, label):
    record = saved(path)
    source_record = record["source"]
    payload = dynamic_case(FIXED["pulse"], case_id, label)
    payload["evidence"].update(checked_evidence(path, record["identity_sha256"]))
    payload["evidence"].update(source=source(path), artifactIdentity=record["identity_sha256"],
        algorithm=record["algorithm_version"], limitations=["vertex-prism V(h), not continuous partial-triangle integral", "fixed wet footprint", "linear K, no inertia or natural certification"],
        scope="saved vertex-prism V(h) lumped graph prefix, physical seconds; fixed wet support, not dynamic fine water surface",
        sources=[{**source(FIXED["pulse"]), "identity": source_record["identity_sha256"]}])
    payload["timeseries"] = {"timeSeconds": array(record["time_s"]), "stages": array(record["stage_m"]),
        "storages": array(record["storage_m3"]), "signedEdgeQ": array(record["qedges_m3_s"]),
        "globalLedger": array(record["ledger_m3"]), "domainLedgers": array(record["domain_ledger_m3"]),
        "committedSteps": record["committed_steps"], "dtSeconds": record["dt_s"], "status": record["status"],
        "failedStep": plain(record["failed_step"]),
        "ledgerColumns": ["before", "local", "boundary inward", "after", "change", "residual"]}
    payload["storageCurve"] = {"geometry": record["geometry"], "knotOffsets": array(record["knot_offsets"]),
        "knotStage": array(record["knot_stage_m"]), "knotVolume": array(record["knot_volume_m3"]),
        "supportOffsets": array(record["support_offsets"]), "supportBed": array(record["support_bed_m"]),
        "supportWeight": array(record["support_weight_m2"])}
    return payload


def engineering_case():
    record = saved(ENGINEERING)
    query_surface_engineering(record)
    payload = variable_case(VARIABLE_RUN / "pulse.npz", "two-domain-engineering", "统一双域 + 两实际工程海口 + V(h)")
    if record["variable_storage"]["identity_sha256"] != saved(VARIABLE_RUN / "pulse.npz")["identity_sha256"]:
        raise ValueError("engineering variable record mismatch")
    if (record["domain_mosaic"]["identity_sha256"] != saved(FIXED["mosaic"])["identity_sha256"] or
            record["dynamic_forest"]["identity_sha256"] != saved(FIXED["pulse"])["identity_sha256"]):
        raise ValueError("embedded source identity does not match pinned standalone archive")
    payload.update(kind="engineering", mesh=build_mosaic()["mesh"], overlay=build_mosaic()["overlay"], outlets=[])
    for domain_id, drop in zip(record["domain_ids"], record["drops"]):
        arrays = drop["arrays"]
        payload["outlets"].append({"domain": domain_id, "attachment": plain(drop["attachment"]), "identity": drop["identity_sha256"],
            "mesh": {"bedVertices": array(arrays["bed_xyz_m"]), "waterVertices": array(arrays["water_xyz_m"]),
                     "triangles": array(arrays["triangles"]), "centerline": array(arrays["centerline_xyz_m"]),
                     "h0": array(arrays["h0_m"])}})
    payload["evidence"].update(checked_evidence(ENGINEERING, record["identity_sha256"]))
    payload["evidence"].update(source=source(ENGINEERING), artifactIdentity=record["identity_sha256"],
        scope="7800 m² bounded node envelope + two saved engineering strips; static fine water and dynamic lumped graph are distinct",
        sources=[{**source(FIXED["mosaic"]), "identity": record["domain_mosaic"]["identity_sha256"]},
                 {**source(FIXED["pulse"]), "identity": record["dynamic_forest"]["identity_sha256"]},
                 {**source(VARIABLE_RUN / "pulse.npz"), "identity": record["variable_storage"]["identity_sha256"]}],
        limitations=["missing 2000 m² physical footprint", "strip overlap original land z70..75", "static fine water is not lumped graph stage", "no natural certification"])
    return payload


def seam_case():
    record = saved(SEAM)
    nodes = record["nodes"]
    payload = {"schemaVersion": "surface-review-v1", "caseId": "wet-cross-precision", "kind": "mesh",
        "label": "compatible 1m/2m wet seam（有界切片）", "evidence": {
        **checked_evidence(SEAM, record["identity_sha256"]), "source": source(SEAM),
        "artifactIdentity": record["identity_sha256"], "scope": "only compatible 1m/2m wet slice, not general cross precision",
        "limitations": ["not general arbitrary cross-precision solver", "one unique graph Q inventory"]},
        "mesh": {"vertices": [[float(x),float(y),float(z)] for x,y,z in zip(nodes["x_m"],nodes["h0_m"],nodes["z_m"])],
        "h0": array(nodes["h0_m"]), "bed": array(nodes["h2_m"]), "water": array(nodes["water_surface_m"]),
        "wet": array(nodes["wet_mask"]), "protected": array(nodes["protected_mask"]),
        "cells": array(record["cells"]), "triangles": array(record["triangles"]), "wetCells": array(record["wet_cells"]),
        "cellOwner": array(record["cell_owner"]), "hydrologicOwner":
        np.asarray([record["sources"][int(owner)]["domain_id"] for owner in record["cell_owner"].ravel()]).reshape(record["cell_owner"].shape).tolist(),
        "sourceKinds": plain(record["sources"]), "contributors": plain(record["contributors"]),
        "rows": record["grid"]["shape_cells_zx"][0], "columns": record["grid"]["shape_cells_zx"][1]},
        "overlay": {"sharedBoundaryX": 30, "mosaicEnvelope": plain(record["grid"]["bbox_xz_m"]),
                    "missingOuterAreaM2": None}, "summary": plain(record["summary"])}
    return payload


def land_case():
    record = saved(LAND)
    query_surface_land_coverage(record)
    if record["source_identity_sha256"] != saved(ENGINEERING)["identity_sha256"]:
        raise ValueError("land engineering source mismatch")
    payload = engineering_case()
    payload.update(caseId="land-footprint-engineering", label="9800 m² clamped land + z75..90 两裁接出口")
    nodes = record["nodes"]
    payload["mesh"] = {"vertices": [[float(point[0]),float(height),float(point[1])]
        for point,height in zip(nodes["xz_m"],nodes["h0_m"])], "h0": array(nodes["h0_m"]),
        "bed": array(nodes["h2_m"]), "water": array(nodes["water_surface_m"]),
        "wet": array(nodes["wet_mask"]), "protected": array(nodes["protected_mask"]),
        "cells": array(record["cells"]), "triangles": array(record["triangles"]),
        "wetCells": np.all(nodes["wet_mask"][record["cells"]],axis=1).tolist(),
        "cellOwner": array(record["domain_owner"]), "hydrologicOwner": array(record["domain_owner"]),
        "sourceKinds": [record["interpretation"]], "rows":70,"columns":140,
        "sourceAudit": plain(record["audit"])}
    payload["outlets"] = []
    for outlet in record["outside_outlets"]:
        source_drop = next(drop for drop in record["source"]["drops"] if drop["identity_sha256"] == outlet["source_drop_sha256"])
        payload["outlets"].append({"domain":outlet["domain_id"], "identity":outlet["source_drop_sha256"],
            "sharedLandNodeIds":array(outlet["shared_land_node_ids"]), "mesh":{
            "bedVertices":array(outlet["bed_xyz_m"]), "waterVertices":array(outlet["water_xyz_m"]),
            "triangles":array(outlet["triangles"]), "centerline":array(source_drop["arrays"]["centerline_xyz_m"][5:]),
            "h0":array(source_drop["arrays"]["h0_m"][outlet["source_node_ids"]])}})
    payload["overlay"] = {"candidateFootprint":[5,145,5,75],"mosaicEnvelope":[5,145,5,75],
                          "missingOuterAreaM2":0,"sharedBoundaryX":75,"outsideCoastStartZ":75}
    payload["evidence"].update(checked_evidence(LAND,record["identity_sha256"]))
    payload["evidence"].update(source=source(LAND),artifactIdentity=record["identity_sha256"],
        scope="9800 m² original pixel footprint under explicit clamped half-pixel engineering interpretation; only z75..90 outside strips",
        sources=[{**source(ENGINEERING),"identity":record["source_identity_sha256"]},
                 {**source(VARIABLE_RUN / "pulse.npz"),"identity":record["source"]["variable_storage"]["identity_sha256"]}],
        limitations=["clamped engineering support, not observed outer fine DEM", "static coast z75 versus dynamic boundary z70",
                     "V(h) fixed original 676 wet cells; outlet dynamic storage excluded", "no natural certification or general cross precision"])
    payload["coverage"] = {"interpretation":record["interpretation"],"ledger":plain(record["ledger"]),
        "dynamicBoundaryZM":record["dynamic_boundary_z_m"],"staticGeometryCoastZM":record["static_geometry_coast_z_m"],
        "outletDynamicStorageIncluded":record["outlet_dynamic_storage_included"]}
    return payload


def main(output=None) -> None:
    destination = Path(output) if output is not None else OUT
    before = {path: sha256(path) for path in EXPECTED}
    if before != EXPECTED:
        raise ValueError("fixed source allowlist hash mismatch")
    payloads = {"two-domain-mosaic.json": build_mosaic(), "dynamic-pulse.json": dynamic_case(FIXED["pulse"], "dynamic-pulse", "獨立入水 pulse"),
                "dynamic-tailwater.json": dynamic_case(FIXED["tailwater"], "dynamic-tailwater", "domain2 尾水 4.2 → 5.1 m"),
                "domain1-coast-drop.json": build_coast(), "dem-candidate.json": build_dem()}
    for key, path in FIXED.items():
        name = {"mosaic":"two-domain-mosaic.json", "pulse":"dynamic-pulse.json", "tailwater":"dynamic-tailwater.json", "coast":"domain1-coast-drop.json", "dem":"dem-candidate.json"}[key]
        payloads[name]["evidence"].update(checked_evidence(path, payloads[name]["evidence"]["artifactIdentity"], diagnostic=key=="dem"))
    for name in ("baseline", "pulse", "domain2-tailwater-rise", "failed-prefix", "cancelled-prefix"):
        payloads["variable-" + name + ".json"] = variable_case(VARIABLE_RUN / (name + ".npz"), "variable-" + name, "V(h) " + name)
    payloads["two-domain-engineering.json"] = engineering_case()
    payloads["wet-cross-precision.json"] = seam_case()
    payloads["land-footprint-engineering.json"] = land_case()
    destination.mkdir(parents=True, exist_ok=True)
    version = "version-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = destination / version
    directory.mkdir(exist_ok=False)
    manifest = {"schemaVersion": "surface-review-v1", "generatedFromFixedAllowlist": True,
                "cases": [{"caseId": p["caseId"], "file": version + "/" + name, "label": p.get("label", p["caseId"]),
                           "kind": p["kind"], "status": p["evidence"]["status"]} for name, p in payloads.items()],
                "legacyManifest": "../manifest.json"}
    for name, payload in payloads.items():
        with (directory / name).open("x", encoding="utf8") as stream:
            json.dump(payload, stream, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        next(entry for entry in manifest["cases"] if entry["file"].endswith("/"+name))["sha256"] = sha256(directory / name)
    if {path: sha256(path) for path in EXPECTED} != before:
        raise ValueError("source changed during export")
    descriptor, temporary = tempfile.mkstemp(prefix=".manifest-", dir=destination)
    try:
        with os.fdopen(descriptor, "w", encoding="utf8") as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination / "manifest.json")
    finally:
        Path(temporary).unlink(missing_ok=True)
    print(f"exported {len(payloads)} surface-review cases to {directory}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    main(parser.parse_args().output)
