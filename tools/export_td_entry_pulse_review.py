"""Lossless, bounded pure-IO review of an independently audited isolated pulse."""

import argparse
import gc
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, identity, load_bundle, publish_bytes
from tools.export_td_entry_shallow_water_review import _encoded_array, _json, _memory_check, _pin

MAX_JSON_BYTES = 64 * 1024**2
MAX_RSS_BYTES = 1024**3
FALSE_FLAGS = (
    "actual_lake_boundary_hydraulics_verified", "natural_outlet_verified",
    "complete_river_hydraulics_verified", "cross_domain_hydraulics_verified",
    "vdm_integrated", "full_river_verified", "per_face_gross_transfer_verified",
)
REQUIRED_GATES = (
    "local_saved_hydraulics_verified", "time_refinement_verified",
    "all_water_from_upstream_Q_verified",
)
ARRIVAL_GATE = "upstream_pulse_to_saved_source_wet_support_verified"


def read_bundle(pin):
    path = Path(pin["path"]).resolve(strict=True)
    if (not path.is_relative_to(ROOT) or path.stat().st_size > MAX_RSS_BYTES
            or ("bytes" in pin and path.stat().st_size != pin["bytes"])):
        raise ValueError("bundle path or byte budget mismatch")

    def validate(record):
        if identity(record["arrays"], record["metadata"]) != record["identity_sha256"]:
            raise ValueError("bundle internal content identity mismatch")
        if any(not np.isfinite(value).all() for value in record["arrays"].values()):
            raise ValueError("bundle contains nonfinite data")

    record = load_bundle(path, expected_sha256=pin["sha256"], validator=validate,
                         max_bytes=MAX_RSS_BYTES)
    if record["identity_sha256"] != pin["identity_sha256"]:
        raise ValueError("bundle external identity mismatch")
    _memory_check(psutil.Process(), 0)
    return record


def _check_code_pins(pins):
    if not pins:
        raise ValueError("missing producer or audit code pins")
    for filename, sha256 in pins.items():
        path = (ROOT / filename).resolve(strict=True)
        if not path.is_relative_to(ROOT) or file_sha256(path) != sha256:
            raise ValueError("code SHA mismatch: " + filename)


def _group(record, names):
    return {name: _encoded_array(record["arrays"][name]) for name in names}


def _read_inputs(index_path, input_sha, audit_path, audit_sha):
    index = _json(index_path, input_sha)
    audit = _json(audit_path, audit_sha)
    if (index.get("schema") != "td-entry-pulse-propagation-run-v1"
            or index.get("status") != "saved_requires_independent_audit"
            or audit.get("schema") != "td-entry-pulse-independent-audit-v1"
            or audit.get("index_sha256") != input_sha or audit.get("status") != "passed"):
        raise ValueError("matching completed event and independent audit required")
    for gate in REQUIRED_GATES:
        if audit.get(gate) is not True:
            raise ValueError("required independent gate failed: " + gate)
    if type(audit.get(ARRIVAL_GATE)) is not bool:
        raise ValueError("arrival gate must explicitly be true or false")
    for flag in FALSE_FLAGS:
        if audit.get(flag, False) is not False:
            raise ValueError("unsupported certification: " + flag)
    if audit.get("comparison", {}).get("passed") is not True:
        raise ValueError("independent time comparison is not passed")
    cases = sorted(index.get("cases", []), key=lambda item: item["level"])
    if (len(cases) != 2 or [item["level"] for item in cases] != [0, 1]
            or len({item["case_id"] for item in cases}) != 2
            or any(item["case_index"] != 0 or item["status"] != "saved_requires_independent_audit"
                   for item in cases)):
        raise ValueError("exactly two completed levels of case zero required")
    receptions = audit.get("source_isolated_reception", [])
    audit_cases = audit.get("cases", [])
    if (len(audit_cases) != 2 or len(receptions) != 2
            or {item["case_id"] for item in audit_cases} != {item["case_id"] for item in cases}
            or any(item.get("status") != "passed" for item in audit_cases)
            or {item["case_id"] for item in receptions} != {item["case_id"] for item in cases}
            or any(item.get("all_water_from_upstream_Q_verified") is not True
                   or item.get("exact_zero_external_water_input_verified") is not True
                   for item in receptions)):
        raise ValueError("complete, source-isolated reception reports required")
    if any(type(item.get(ARRIVAL_GATE)) is not bool for item in receptions):
        raise ValueError("missing per-level arrival gate")
    if audit[ARRIVAL_GATE] != all(item[ARRIVAL_GATE] for item in receptions):
        raise ValueError("aggregate and per-level arrival gates disagree")
    parent_pin = index["source_parent_index"]
    parent = _json(parent_pin["path"], parent_pin["sha256"])
    parent_audit_pin = index["source_parent_audit"]
    parent_audit = _json(parent_audit_pin["path"], parent_audit_pin["sha256"])
    if (parent_audit.get("status") != "passed"
            or parent_audit.get("index_sha256") != parent_pin["sha256"]
            or index["carrier"] != parent["carrier"]):
        raise ValueError("carrier is not the exact independently audited parent")
    prepared_pin, prepared_audit_pin = index["parent"], index["preparation_audit"]
    prepared = _json(prepared_pin["path"], prepared_pin["sha256"])
    prepared_audit = _json(prepared_audit_pin["path"], prepared_audit_pin["sha256"])
    if (prepared.get("schema") != "td-entry-pulse-propagation-preparation-v1"
            or prepared_audit.get("status") != "passed"
            or prepared_audit.get("index_sha256") != prepared_pin["sha256"]
            or any(prepared[name] != index[name] for name in
                   ("carrier", "geometry", "forcing", "source_parent_index", "source_parent_audit",
                    "declared_maxdt_s", "code_sha256"))):
        raise ValueError("run is not bound to the independently accepted pulse preparation")
    _check_code_pins(index["code_sha256"])
    _check_code_pins(audit["audit_code_sha256"])
    return index, audit, cases


def _static(carrier, geometry, forcing):
    bed, bed_meta = carrier["arrays"], carrier["metadata"]
    geom, force, force_meta = geometry["arrays"], forcing["arrays"], forcing["metadata"]
    shape = bed["derived_bed_m"].shape
    if (bed_meta.get("schema") != "td-entry-shallow-water-bed-v1"
            or geometry["metadata"].get("schema") != "td-entry-pulse-dry-drain-geometry-v1"
            or force_meta.get("schema") != "td-entry-pulse-isolated-forcing-v1"
            or bed_meta["spacing_m"] != .175 or len(shape) != 2
            or bed["derived_bed_m"].size > 65536
            or geometry["metadata"]["bed_identity_sha256"] != carrier["identity_sha256"]
            or force_meta["bed_identity_sha256"] != carrier["identity_sha256"]
            or force_meta["geometry_identity_sha256"] != geometry["identity_sha256"]):
        raise ValueError("static schemas, lattice or source linkage mismatch")
    grid_names = (
        "source_bed_m", "derived_bed_m", "wet_protected_mask", "overlay_mask",
        "valid_mask", "protected_mask", "forcing_mask", "global_row", "global_column",
        "longitudinal_from_upstream_m", "centerline_offset_m",
    )
    if any(bed[name].shape != shape for name in grid_names):
        raise ValueError("static grid shape mismatch")
    kinds, boundary_cells = geom["boundary_kind"], geom["boundary_cell"]
    if (not np.isin(kinds, (0, 1)).all() or not np.any(kinds == 1)
            or not np.array_equal(geom["H2_m"], bed["derived_bed_m"])
            or not np.array_equal(geom["boundary_crest_m"], bed["derived_bed_m"].ravel()[boundary_cells])):
        raise ValueError("only unchanged-bed closed/dry-drain boundaries supported")
    times = force["time_s"]
    if (not np.array_equal(times, np.arange(25, dtype=float) * 10.)
            or force_meta["duration_s"] != 240. or force_meta["pulse_duration_s"] != 120.
            or force_meta["interval_s"] != 10.
            or force["forcing_m3_s"].shape != (1, 24, bed["derived_bed_m"].size)
            or force["initial_depth_m"].shape != (1, *shape)
            or np.any(force["initial_depth_m"] != 0)
            or force_meta["injection_node_id"] != bed_meta["injection_node_id"]
            or force_meta["ordinary_q_m3_s"] != bed_meta["ordinary_q_m3_s"]):
        raise ValueError("exact isolated 240s/120s pulse schedule required")
    mask = bed["forcing_mask"]
    if mask.dtype != bool or not mask.any():
        raise ValueError("missing exact upstream injection mask")
    expected = ((times[:-1] < 120.)[:, None] * mask.ravel()[None]
                * float(force_meta["ordinary_q_m3_s"]) / mask.sum())
    if not np.array_equal(force["forcing_m3_s"][0], expected):
        raise ValueError("saved ordinary Q schedule/mask mismatch")
    if (force["boundary_stage_m"].shape != (1, 24, len(kinds))
            or not np.array_equal(force["boundary_stage_m"],
                                  np.broadcast_to(geom["boundary_crest_m"], (1, 24, len(kinds))))):
        raise ValueError("dry boundary forcing must equal actual bed crest")
    origin = np.asarray(bed_meta["global_lattice_origin_m_xz"], dtype=float)
    if origin.shape != (2,):
        raise ValueError("global lattice origin mismatch")
    coordinates = np.stack((origin[0] + (bed["global_column"] + .5) * .175,
                            bed["derived_bed_m"],
                            origin[1] + (bed["global_row"] + .5) * .175), axis=-1)
    if bed["chain_xyz_m"].shape != (4, 3) or bed["chain_native_cell_ids"].shape != (4,):
        raise ValueError("four-point saved 90m chain required")
    return {
        "grid": {"shape": list(shape), "spacing_m": .175,
                 "global_lattice_origin_m_xz": origin.tolist(),
                 "coordinate_system": "model x east, y elevation, z south; arrays row-major [z,x]"},
        "arrays": dict(_group(carrier, grid_names), global_xyz_m=_encoded_array(coordinates)),
        "carrier_metadata": bed_meta,
        "chain_90m": dict(_group(carrier, ("chain_xyz_m", "chain_native_cell_ids")),
                           entry_id=bed_meta["entry_id"], length_m=90.,
                           semantics="saved accepted edge, land taper, unchanged source wet support; not a natural lake boundary"),
        "upstream_Q_schedule": dict(_group(forcing, ("time_s", "forcing_m3_s", "initial_depth_m")),
                                    metadata=force_meta,
                                    axes="case, interval, flattened row-major cell",
                                    interval_total_q_m3_s=_encoded_array(force["forcing_m3_s"].sum(axis=2)),
                                    semantics="exact upstream ordinary Q only; no rain or momentum source"),
        "dry_drain": dict(_group(geometry, ("boundary_cell", "boundary_kind", "boundary_crest_m")),
                          kind_labels={"0": "closed", "1": "dry engineering drain"},
                          downstream_side=geometry["metadata"].get("downstream_side"),
                          geometry_metadata=geometry["metadata"],
                          semantics="saved short downstream cross-section; ghost level is actual bed crest, no prescribed lake stage"),
    }


def _frame(case, index, forcing, shape, process):
    state = read_bundle(case["state"])
    meta, arrays = state["metadata"], state["arrays"]
    if (meta.get("schema") != "td-entry-shallow-water-state-v1" or meta.get("status") != "completed"
            or meta["source_identity"] != index["carrier"]["identity_sha256"]
            or meta["geometry_identity_sha256"] != index["geometry"]["identity_sha256"]
            or meta["forcing_identity"] != index["forcing"]["identity_sha256"]
            or meta["case_index"] != 0 or meta["max_dt_requested_s"] != case["max_dt_s"]
            or case["max_dt_s"] != index["declared_maxdt_s"][case["level"]]
            or meta["committed_time_s"] != 240.):
        raise ValueError("completed state identity or level mismatch")
    if (not np.array_equal(arrays["time_s"], forcing["arrays"]["time_s"])
            or any(arrays[name].shape != (25, *shape) for name in
                   ("depth_m", "momentum_x_m2_s", "momentum_z_m2_s"))
            or np.any(arrays["depth_m"] < 0) or arrays["ledger"].shape != (25, 5)
            or arrays["initial_depth_m"].shape != shape
            or np.any(arrays["initial_depth_m"] != 0)
            or any(np.any(arrays[name][0] != 0) for name in
                   ("depth_m", "momentum_x_m2_s", "momentum_z_m2_s"))
            or np.any(arrays["ledger"][:, 1] != 0) or meta["boundary_input_m3"] != 0):
        raise ValueError("all 25 dry-start, zero-boundary-import frames required")
    peak = _memory_check(process, 0)
    frame = dict(_group(state, ("time_s", "depth_m", "momentum_x_m2_s", "momentum_z_m2_s",
                               "initial_depth_m", "ledger")),
                 case_id=case["case_id"], case_index=0, level=case["level"], max_dt_s=case["max_dt_s"],
                 frame_count=25, actual_state_identity_sha256=state["identity_sha256"],
                 state_identity_sha256=state["identity_sha256"], state_pin=case["state"],
                 state_metadata=meta, diagnostics=case.get("diagnostics", {}),
                 ledger_columns=["supplied_m3", "boundary_import_m3", "boundary_export_m3",
                                 "stored_volume_m3", "mass_residual_m3"])
    del state, arrays
    gc.collect()
    for key, schema in (("intervals", "td-entry-shallow-water-intervals-v1"),
                        ("first_rk", "td-entry-shallow-water-first-rk-v1")):
        record = read_bundle(case[key])
        if (record["metadata"].get("schema") != schema
                or record["metadata"]["state_identity_sha256"] != frame["state_identity_sha256"]):
            raise ValueError("observer identity is not bound to actual saved state")
        frame[key + "_pin"] = case[key]
        frame[key + "_identity_sha256"] = record["identity_sha256"]
        peak = _memory_check(process, peak)
        del record
        gc.collect()
    return frame, peak


def _review(index_path, input_sha, audit_path, audit_sha):
    started = time.perf_counter()
    process = psutil.Process()
    index, audit, cases = _read_inputs(index_path, input_sha, audit_path, audit_sha)
    carrier, geometry, forcing = (read_bundle(index[name]) for name in ("carrier", "geometry", "forcing"))
    review = _static(carrier, geometry, forcing)
    shape = carrier["arrays"]["derived_bed_m"].shape
    peak = _memory_check(process, 0)
    del carrier, geometry
    gc.collect()
    frames = []
    if index["declared_maxdt_s"] != [.01, .005]:
        raise ValueError("two declared original time levels required")
    for case in cases:
        frame, frame_peak = _frame(case, index, forcing, shape, process)
        frames.append(frame)
        peak = max(peak, frame_peak, _memory_check(process, peak))
    formal = audit[ARRIVAL_GATE]
    review.update(
        schema="td-entry-pulse-review-v1", status="formal_review_ready" if formal else "diagnostic_only",
        formal_consumption_allowed=formal,
        formal_refusal_reasons=[] if formal else ["upstream_pulse_to_saved_source_wet_support_not_verified"],
        input_index_sha256=input_sha, audit_sha256=audit_sha,
        index_pin=_pin(index_path), audit_pin=_pin(audit_path),
        carrier_pin=index["carrier"], geometry_pin=index["geometry"], forcing_pin=index["forcing"],
        source_parent_index=index["source_parent_index"], source_parent_audit=index["source_parent_audit"],
        preparation_index_pin=index["parent"], preparation_audit_pin=index["preparation_audit"],
        source_pins=index.get("inputs", {}), code_sha256=index["code_sha256"],
        audit_code_sha256=audit["audit_code_sha256"],
        exporter_code_sha256={filename: file_sha256(ROOT / filename) for filename in
                             ("tools/export_td_entry_pulse_review.py", "tools/export_td_entry_shallow_water_review.py",
                              "terrain_pipeline/common_infra.py")},
        frames=frames, source_isolated_reception=audit["source_isolated_reception"],
        comparison=audit["comparison"], independent_case_audits=audit["cases"],
        diagnostic_gates={"independent_audit_status": audit["status"],
                          **{gate: audit[gate] for gate in (*REQUIRED_GATES, ARRIVAL_GATE)},
                          **{flag: False for flag in FALSE_FLAGS}},
        encoding_contract={"encoding": "npy-zlib-base64", "lossless": True,
                           "dtype": "exact NPY dtype.str including byte order", "shape": "exact NPY shape",
                           "order": "C", "resampled": False, "observer_packets": "external immutable pins"},
        event_resource=index.get("resource", {}),
        export_resource={"solver_calls": 0, "resampling_calls": 0, "hard_output_bytes": MAX_JSON_BYTES,
                         "hard_rss_bytes": MAX_RSS_BYTES, "actual_peak_rss_bytes": peak,
                         "io_wall_s_before_serialization": time.perf_counter() - started},
        semantics="pure IO of saved source-isolated pulse; no solver, interpolation, bed mutation or fabricated lake stage",
        **{flag: False for flag in FALSE_FLAGS})
    payload = json.dumps(review, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf8")
    if len(payload) > MAX_JSON_BYTES:
        raise MemoryError("lossless pulse review exceeds 64MiB; no fallback resampling")
    _memory_check(process, peak)
    return review, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    allowed = (ROOT / "verification/natural-river-network").resolve()
    if output.exists() or not output.is_relative_to(allowed) or output == allowed:
        raise ValueError("new isolated review output directory required")
    started = time.perf_counter()
    review, payload = _review(args.input, args.sha256, args.audit, args.audit_sha256)
    sha256 = hashlib.sha256(payload).hexdigest()
    manifest = {
        "schema": "td-entry-pulse-review-export-v1", "status": review["status"],
        "formal_consumption_allowed": review["formal_consumption_allowed"],
        "formal_refusal_reasons": review["formal_refusal_reasons"],
        "formal_consumption_requires": ["independent_audit_status_passed", *REQUIRED_GATES, ARRIVAL_GATE],
        "review": {"path": str(output / "review.json"), "sha256": sha256, "bytes": len(payload)},
        "review_identity_sha256": sha256, "input_index_sha256": args.sha256, "audit_sha256": args.audit_sha256,
        "actual_state_identities_sha256": [frame["actual_state_identity_sha256"] for frame in review["frames"]],
        "export_resource": dict(review["export_resource"], io_wall_s_before_publication=time.perf_counter() - started,
                                actual_peak_rss_bytes=_memory_check(psutil.Process(), 0)),
        "flags": {flag: False for flag in FALSE_FLAGS},
    }
    manifest_payload = (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf8")
    if len(payload) + len(manifest_payload) > MAX_JSON_BYTES:
        raise MemoryError("complete lossless export exceeds total 64MiB")
    output.mkdir(parents=True, exist_ok=False)
    publish_bytes(output / "review.json", payload)
    publish_bytes(output / "index.json", manifest_payload)
    print(json.dumps(manifest, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
