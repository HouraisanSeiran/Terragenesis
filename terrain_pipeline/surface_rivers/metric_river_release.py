"""Pinned saved TD review product; reads never generate terrain or solve water."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath

import numpy as np

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from .metric_channel_product import load_channel_product

LEGACY_SCHEMA = "terragenesis-river-product-v1"
SCHEMA = "terragenesis-river-product-v2"
PATH_SEMANTICS = "release-relative"
ROOT = Path(__file__).resolve().parents[2]
M3 = ROOT / "verification/td-river-channel/m3-20261008-02/acceptance.json"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _identity(product):
    content = {key: value for key, value in product.items() if key != "identity_sha256"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _pin(path, **extra):
    path = Path(path).resolve()
    return {"path": path.as_posix(), "sha256": file_sha256(path), **extra}


def _linked(pin):
    path = Path(pin["path"])
    if file_sha256(path) != pin["sha256"]:
        raise ValueError("linked evidence hash mismatch: " + pin["path"])
    return path


def _contained_path(anchor, relative):
    if (not isinstance(relative, str) or not relative or "\\" in relative
            or PureWindowsPath(relative).drive or ":" in relative
            or PurePosixPath(relative).is_absolute()
            or any(part in ("", ".", "..") for part in relative.split("/"))):
        raise ValueError("invalid evidence relative path")
    anchor = Path(anchor).resolve()
    path = (anchor / relative).resolve()
    if not path.is_relative_to(anchor):
        raise ValueError("evidence path escapes anchor")
    return path


def resolve_release_pin(release_path, product, pin):
    """Resolve and hash-check a direct pin; v1 is workspace-linked, v2 portable.

    Pass the unmodified load_release result.
    Raw reports, identity_inputs and m7_comparison are immutable provenance, not
    executable path contracts. Use pins for M7 traces and bounded case comparison
    artifacts for valley evidence; do not run old auditors on raw bundled reports.
    """
    schema = product.get("schema")
    if schema == SCHEMA:
        if product.get("path_semantics") != PATH_SEMANTICS:
            raise ValueError("unsupported release path semantics")
        anchor = Path(release_path).resolve().parent
    elif schema == LEGACY_SCHEMA:
        anchor = ROOT
    else:
        raise ValueError("unsupported river product schema")
    fields = ("path", "sha256", "identity_sha256")
    if not any(all(pin.get(key) == registered.get(key) for key in fields)
               for registered in product["pins"].values()):
        raise ValueError("evidence reference is not a registered release pin")
    path = _contained_path(anchor, pin["path"])
    if file_sha256(path) != pin["sha256"]:
        raise ValueError("linked evidence hash mismatch: " + pin["path"])
    return path


def _consumer_pins(product):
    yield product["source"]
    for group in ("accepted", "refused"):
        for gate in product["gates"][group]:
            for role in ("evidence", "channel_trace", "sediment_trace"):
                if gate.get(role) is not None:
                    yield gate[role]
    for case in product.get("bounded_results", {}).get("cases", []):
        for role in ("geometry", "sediment", "manifest"):
            if case.get(role) is not None:
                yield case[role]
        if case.get("comparison") is not None:
            yield from case["comparison"]["artifacts"].values()


def _map_legacy_consumers(product):
    for gate in product["gates"]["refused"]:
        for role in ("channel_trace", "sediment_trace"):
            if gate.get(role) is not None:
                name = gate["name"].removesuffix("_requested_horizon") + "_" + role
                gate[role] = product["pins"][name]
    for case in product.get("bounded_results", {}).get("cases", []):
        if case.get("comparison") is not None:
            case["provenance_record"] = deepcopy(case["comparison"])
            case["comparison"] = deepcopy(case["comparison"])
            for role in case["comparison"]["artifacts"]:
                name = case["id"] + "_" + ("geometry" if role == "fine" else role)
                case["comparison"]["artifacts"][role] = product["pins"][name]


def _publish_release(product, output, evidence_paths):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    product = deepcopy(product)
    if product["schema"] == LEGACY_SCHEMA:
        _map_legacy_consumers(product)
    references = list(_consumer_pins(product))
    replacements = {}
    for name, pin in product["pins"].items():
        replacements[(pin["path"], pin["sha256"], pin.get("identity_sha256"))] = name
    reference_names = []
    for reference in references:
        key = (reference["path"], reference["sha256"], reference.get("identity_sha256"))
        if key not in replacements:
            raise ValueError("consumer evidence is not a registered release pin")
        reference_names.append(replacements[key])
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_dir = output.parent / (output.name + ".evidence")
    if evidence_dir.exists() or evidence_dir.is_symlink():
        raise FileExistsError(evidence_dir)
    with tempfile.TemporaryDirectory(prefix=".river-release-", dir=output.parent) as temporary:
        staged = Path(temporary) / "evidence"
        staged.mkdir()
        bundled = {}
        for name, pin in product["pins"].items():
            source = evidence_paths[name]
            filename = pin["sha256"] + Path(source).suffix
            destination = _contained_path(staged, filename)
            if not destination.exists():
                shutil.copyfile(source, destination)
            if file_sha256(destination) != pin["sha256"]:
                raise ValueError("linked evidence hash mismatch: " + pin["path"])
            bundled[name] = {**pin, "path": evidence_dir.name + "/" + filename}
        for reference, name in zip(references, reference_names):
            reference.update(bundled[name])
        product.update(schema=SCHEMA, path_semantics=PATH_SEMANTICS, pins=bundled,
                       evidence_scope="direct release pins bundled; raw nested documents are immutable provenance, not executable paths")
        product["identity_sha256"] = _identity(product)
        staged.rename(evidence_dir)
        try:
            publish_bytes(output, (json.dumps(product, ensure_ascii=False, sort_keys=True,
                                             allow_nan=False) + "\n").encode("utf-8"))
        except BaseException:
            shutil.rmtree(evidence_dir)
            raise
    return {"path": output.name, "output": str(output), "sha256": file_sha256(output),
            "identity_sha256": product["identity_sha256"], "publishable": False}


def export_release(base, output):
    """Copy all direct evidence from a saved v1/v2 release without recomputation."""
    if Path(output).exists():
        raise FileExistsError(output)
    product = load_release(base)
    paths = {name: resolve_release_pin(base, product, pin) for name, pin in product["pins"].items()}
    return _publish_release(product, output, paths)


def assemble(source: Path, output: Path, comparison: Path | None = None, *, acceptance: Path | None = None):
    """Bind a source manifest and actual saved native channel to a review package."""
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    acceptance_path = Path(acceptance).resolve() if acceptance is not None else M3
    manifest, acceptance = _read(source), _read(acceptance_path)
    selection = acceptance["td_selection"]
    source_pin = manifest["artifacts"]["product"]
    if source_pin != selection["source_product"] or manifest["source_sha256"] != selection["source_sha256"]:
        raise ValueError("M3 selection does not match TD source manifest")
    source_product = _contained_path(source.parent, source_pin["path"])
    if file_sha256(source_product) != source_pin["sha256"]:
        raise ValueError("TD source product hash mismatch")
    comparison_payload = _read(comparison) if comparison is not None else None
    comparison_audit = None
    pins = {"source_manifest": _pin(source), "m3_acceptance": _pin(acceptance_path),
            "source_product": _pin(source_product, identity_sha256=source_pin["identity_sha256"]),
            "raw_td_source": _pin(Path(manifest["source_path"]))}
    if pins["raw_td_source"]["sha256"] != manifest["source_sha256"]:
        raise ValueError("raw TD source hash mismatch")
    if comparison_payload is not None:
        if comparison_payload.get("schema") != "terragenesis-resolution-comparison-v1":
            raise ValueError("unsupported M7 comparison schema")
        from .metric_resolution_exchange import audit_comparison
        comparison_audit = audit_comparison(comparison)
        basis = comparison_payload["source_manifest"]
        if (basis["acceptance_sha256"] != file_sha256(acceptance_path) or basis["td_selection"] != selection
                or basis["native_channel_product"]["identity_sha256"] != acceptance["artifacts"]["td_fine"]["identity_sha256"]):
            raise ValueError("M7 source basis differs from selected M3 TD evidence")
        pins["m7_comparison"] = _pin(comparison)
        for name, case in comparison_payload["cases"].items():
            for kind in ("channel_trace", "sediment_trace"):
                record = case[kind]
                if record is None:
                    continue
                path = _contained_path(Path(comparison).parent, record["path"])
                pins[name + "_" + kind] = _pin(path, identity_sha256=record["identity_sha256"])
                if pins[name + "_" + kind]["sha256"] != record["sha256"]:
                    raise ValueError("M7 trace pin mismatch")
        channel_pin = pins["native_channel_trace"]
    else:
        record = acceptance["artifacts"]["td_coarse"]
        channel_pin = _pin(_contained_path(acceptance_path.parent, record["path"]), identity_sha256=record["identity_sha256"])
        if channel_pin["sha256"] != record["sha256"]:
            raise ValueError("M3 trace pin mismatch")
        pins["native_channel_trace"] = channel_pin
    channel = load_channel_product(_linked(channel_pin), expected_sha256=channel_pin["sha256"],
                                   expected_identity=channel_pin["identity_sha256"])
    arrays, metadata = channel["arrays"], channel["metadata"]
    selected = np.asarray(selection["selected_cell_ids"], dtype=np.int64)
    with np.load(source_product, allow_pickle=False) as archive:
        source_metadata = json.loads(archive["manifest"].tobytes())["metadata"]
        elevation = archive["elevation_m"]
        rows, cols = np.unravel_index(selected, elevation.shape)
        # Full native cells in this review window, no terrain interpolation or carving.
        r0, r1 = max(0, int(rows.min()) - 2), min(elevation.shape[0], int(rows.max()) + 3)
        c0, c1 = max(0, int(cols.min()) - 2), min(elevation.shape[1], int(cols.max()) + 3)
        terrain = {"height_m": elevation[r0:r1, c0:c1].tolist(), "origin_row": r0,
                   "origin_column": c0, "spacing_m": 30., "coordinates": "local raster X=column*30m Z=row*30m; CRS unresolved"}
        original_bed = elevation.ravel()[selected].tolist()
        lake_ids = archive["graph_lake_id"][selected].tolist()
        unknown = (~archive["graph_valid_mask"][r0:r1, c0:c1]).tolist()
    if len(selected) != len(arrays["network_receiver"]):
        raise ValueError("saved native trace count differs from TD selection")
    if not np.array_equal(arrays["network_bed_elevation_m"], np.asarray(original_bed)):
        raise ValueError("native bed differs from original TD cell bed")
    edges = [[i, int(receiver)] for i, receiver in enumerate(arrays["network_receiver"]) if receiver >= 0]
    donors = [edge[0] for edge in edges]
    graph = {"coords": np.column_stack((cols * 30., rows * 30.)).tolist(),
             "nodeKeys": [["td-native", int(cell)] for cell in selected], "bed": original_bed,
             "edges": edges, "boundary": (arrays["network_receiver"] < 0).tolist(),
             "terminalKind": arrays["network_terminal_kind"].tolist()}
    series = {"timeSeconds": arrays["trace_time_seconds"].tolist(),
              "stages": arrays["trace_stage_m"].tolist(), "storages": arrays["trace_volume_m3"].tolist(),
              "signedEdgeQ": arrays["trace_outflow_q_m3_s"][:, donors].tolist(),
              "signedEdgeQUnits": "m3/s", "committedSteps": len(arrays["trace_time_seconds"]) - 1,
              "dischargeSemantics": "saved pre-step Manning interval average; positive donor to receiver; terminal Q separately retained",
              "terminalQ": arrays["trace_outflow_q_m3_s"][:, arrays["network_receiver"] < 0].tolist()}
    unresolved = ["CRS", "natural_outlet_verification", "global_channel_geometry", "natural_lake_backwater", "morphology_recoupling"]
    if comparison_payload is None:
        unresolved.append("m7_resolution_exchange_missing")
    gates = {"accepted": [{"name": "m3_bounded_kinematic_baseline", "status": acceptance["status"], "evidence": pins["m3_acceptance"]}],
             "refused": [], "unresolved": unresolved, "m7": {"acceptance": comparison_payload.get("acceptance"), "cold_audit": comparison_audit} if comparison_payload else None,
             "publishable": False, "natural_outlet_verified": False}
    if comparison_audit:
        gates["accepted"].append({"name": "m7_committed_prefix_exchange" if comparison_audit["status"] != "accepted_conservative_1d_exchange" else "m7_conservative_1d_exchange", "status": comparison_audit["status"], "evidence": pins["m7_comparison"]})
        gates["unresolved"].append("m7_resolution_agreement_measured_unresolved")
        for name, case in comparison_payload["cases"].items():
            if case["status"] != "complete" or case["sediment_status"] != "complete":
                gates["refused"].append({"name": name + "_requested_horizon", "water_status": case["status"],
                    "sediment_status": case["sediment_status"], "failure_reason": case["failure_reason"],
                    "sediment_failure_reason": case["sediment_failure_reason"], "channel_trace": pins.get(name + "_channel_trace"),
                    "sediment_trace": pins.get(name + "_sediment_trace")})
    if metadata["status"] != "complete":
        gates["refused"].append({"name": "native_requested_horizon", "status": metadata["status"], "reason": metadata["failure_reason"]})
    geometry_failure = ROOT / "verification/td-valley-global-tiled/td1024-20261008-01/failure-prefix.json"
    if geometry_failure.exists():
        pins["global_geometry_failure_prefix"] = _pin(geometry_failure)
        gates["refused"].append({"name": "global_channel_geometry", "evidence": pins["global_geometry_failure_prefix"],
                                  "saved_result": _read(geometry_failure), "scope": "separate global candidate, not displayed native channel geometry"})
    absent = lambda reason: {"status": "unresolved", "reason": reason}
    product = {"schema": SCHEMA, "version": "2026-10-10.m8.2", "status": "saved_bounded_review",
               "publishable": False, "pins": pins,
               "source": {**pins["source_product"], "kind": "Terrain Diffusion saved 1024 raster", "raw_sha256": manifest["source_sha256"],
                          "coordinates": terrain["coordinates"], "selection": selection},
               "identity_inputs": {"source": source_metadata, "channel": metadata,
                                   "forcing_source_identity_sha256": metadata["forcing_source_identity_sha256"],
                                   "forcing_time_seconds": arrays["forcing_time_seconds"].tolist(),
                                   "forcing_local_q_m3_s": arrays["forcing_local_q_m3_s"].tolist(),
                                   "network": {key: value.tolist() for key, value in arrays.items() if key.startswith("network_")}},
               "gates": gates, "evidence": {"water_budget_m3": metadata["water_budget_m3"], "status": metadata["status"],
                   "failure_reason": metadata["failure_reason"], "unfinished_time_seconds": metadata["unfinished_time_seconds"],
                   "limitations": ["1D rectangular uncalibrated section; selected TD cells only", "frozen-water sediment does not certify bed feedback", "diagnostic topology is not fine-grid instantaneous water surface", "global publishability and natural outlet unresolved"]},
               "layers": {"original_bed": terrain, "diagnostic_topology": graph, "flow_intervals": series,
                          "lake_stage": {**absent("native channel trace has no lake stage solution"), "source_lake_ids": lake_ids},
                          "unresolved_hydraulic_cells": {"source_unknown_mask": unknown, "hydraulic_resolution": "unresolved outside selected 1D channel"},
                          "candidate_geometry": absent("no candidate 3D corridor attached"),
                          "accepted_geometry": absent("no accepted 3D corridor attached")},
               "m7_comparison": comparison_payload}
    return _publish_release(product, output, {name: _linked(pin) for name, pin in pins.items()})


def load_release(path: Path, *, expected_sha256=None, expected_identity=None):
    if expected_sha256 is not None and file_sha256(path) != expected_sha256:
        raise ValueError("external river product hash mismatch")
    product = _read(path)
    if product.get("schema") not in (SCHEMA, LEGACY_SCHEMA) or product.get("identity_sha256") != _identity(product):
        raise ValueError("river product schema/identity mismatch")
    if expected_identity is not None and product["identity_sha256"] != expected_identity:
        raise ValueError("external river product identity mismatch")
    if product.get("publishable") is not False or product["gates"].get("publishable") is not False:
        raise ValueError("global release gates are unresolved")
    for pin in product["pins"].values():
        resolve_release_pin(path, product, pin)
    if product["schema"] == SCHEMA:
        for reference in _consumer_pins(product):
            pin = {key: reference[key] for key in ("path", "sha256", "identity_sha256") if key in reference}
            resolve_release_pin(path, product, pin)
    if product.get("m7_comparison") is not None and _read(resolve_release_pin(path, product, product["pins"]["m7_comparison"])) != product["m7_comparison"]:
        raise ValueError("embedded M7 comparison differs from pinned evidence")
    if product.get("m7_comparison") is None and "m7_resolution_exchange_missing" not in product["gates"]["unresolved"]:
        raise ValueError("missing M7 evidence must remain unresolved")
    return product


def assemble_results(base: Path, output: Path, *, geometry_report: Path,
                     sediment_report: Path, valley_report: Path):
    """Extend an immutable M7 review with pinned M5/M6 and shaped valley results."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    product = load_release(base)
    evidence_paths = {name: resolve_release_pin(base, product, pin) for name, pin in product["pins"].items()}
    if product["schema"] == LEGACY_SCHEMA:
        _map_legacy_consumers(product)
    replacements = {(pin["path"], pin["sha256"]): _pin(evidence_paths[name],
                    **{key: value for key, value in pin.items() if key not in ("path", "sha256")})
                    for name, pin in product["pins"].items()}
    references = list(_consumer_pins(product)) + list(product["pins"].values())
    rebound = [replacements[(pin["path"], pin["sha256"])] for pin in references]
    for pin, replacement in zip(references, rebound):
        pin.update(replacement)
    product["schema"] = SCHEMA
    pins = product["pins"]
    reports = {"m5": Path(geometry_report), "m6": Path(sediment_report), "valley": Path(valley_report)}
    for name, path in reports.items():
        pins[name + "_results_report"] = _pin(path)
    geometry, sediment, valley = (_read(reports[name]) for name in ("m5", "m6", "valley"))
    cases = []
    for case_id, name, label in (("main", "td_fine", "TD1024 · 主段河槽"),
                                ("bend", "td_bend_fine", "TD1024 · 弯道河槽"),
                                ("sediment", "td_fine", "同一主段 · 侵蚀沉积 0–900 s")):
        record = geometry["artifacts"][name]
        pin = _pin(_contained_path(reports["m5"].parent, record["path"]), identity_sha256=record["identity_sha256"])
        if pin["sha256"] != record["sha256"]:
            raise ValueError("M5 result hash mismatch")
        pins[case_id + "_geometry"] = pin
        entry = {"id": case_id, "label": label, "kind": "m5_channel", "geometry": pin, "comparison": None}
        if case_id == "sediment":
            record = sediment["artifacts"]["td_fine"]
            pin = _pin(_contained_path(reports["m6"].parent, record["path"]), identity_sha256=record["identity_sha256"])
            if pin["sha256"] != record["sha256"]:
                raise ValueError("M6 result hash mismatch")
            pins["m6_sediment"] = pin
            entry.update(kind="m6_sediment", sediment=pin)
        cases.append(entry)
    for record in valley["cases"]:
        if record["status"] != "accepted_shaped_component":
            continue
        case_id = "valley-" + record["component"]
        artifact = record["artifacts"]["fine"]
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_absolute():
            artifact_path = _contained_path(reports["valley"].parent, artifact["path"])
        pin = _pin(artifact_path, identity_sha256=artifact["identity_sha256"])
        if pin["sha256"] != artifact["sha256"]:
            raise ValueError("Valley result hash mismatch")
        pins[case_id + "_geometry"] = pin
        for role in ("before", "coarse", "centerline"):
            evidence = record["artifacts"][role]
            evidence_path = Path(evidence["path"])
            if not evidence_path.is_absolute():
                evidence_path = _contained_path(reports["valley"].parent, evidence["path"])
            pins[case_id + "_" + role] = _pin(evidence_path, identity_sha256=evidence["identity_sha256"])
            if pins[case_id + "_" + role]["sha256"] != evidence["sha256"]:
                raise ValueError("Valley comparison hash mismatch")
        comparison = deepcopy(record)
        comparison["artifacts"] = {role: pins[case_id + "_" + ("geometry" if role == "fine" else role)]
                                   for role in record["artifacts"]}
        cases.append({"id": case_id, "label": "自然谷地 · 组件 " + record["component"],
                      "kind": "shaped_valley_component", "geometry": pin, "comparison": comparison,
                      "provenance_record": record,
                      "manifest": pins["valley_results_report"]})
    for case in cases:
        with np.load(_linked(case["geometry"]), allow_pickle=False) as archive:
            metadata = json.loads(archive["manifest"].tobytes())["metadata"]
        case["algorithm"] = metadata["algorithm"]
        case["parameters"] = metadata["config"]
        case["gates"] = {"publishable": False, "hydraulic_ready": False, "natural_outlet_verified": False}
        case["scope"] = "saved local geometry on original TD terrain; not the M7 selected 1D reach"
        case["status"] = "accepted_bounded_geometry"
        if case["kind"] == "shaped_valley_component":
            case.update(status="candidate_global_replacement", accepted_scope="bounded component original-bed monotonicity and spatial refinement")
        elif case["kind"] == "m6_sediment":
            case.update(status="accepted_bounded_frozen_water_replay", scope="M5 local main reach; four saved sediment control nodes; no coupled bed feedback")
    product["layers"]["candidate_geometry"] = {"status": "candidate_global_replacement", "case_ids": [c["id"] for c in cases if c["kind"] == "shaped_valley_component"], "scope": "local replacement candidates; global 623/673 coverage unchanged"}
    product["layers"]["accepted_geometry"] = {"status": "accepted_bounded_geometry", "case_ids": ["main", "bend"], "scope": "M5 local saved geometry only; no geometry attached to the separate M7 1D trace"}
    product.update(version="2026-10-10.m8.3", bounded_results={
        "schema": "terragenesis-m8-bounded-results-v1", "default_case": "valley-4", "cases": cases,
        "publishable": False, "hydraulic_ready": False, "natural_outlet_verified": False,
        "scope": "bounded local geometry and frozen-water sediment; global accepted edges remain 623/673"})
    product["gates"]["accepted"].extend([
        {"name": "m5_bounded_geometry", "status": geometry["status"], "evidence": pins["m5_results_report"]},
        {"name": "m6_bounded_sediment", "status": sediment["status"], "evidence": pins["m6_results_report"]},
        {"name": "shaped_valley_bounded_components", "status": valley["status"], "evidence": pins["valley_results_report"]}])
    return _publish_release(product, output, {name: _linked(pin) for name, pin in pins.items()})
