"""Export an audited shallow-water event as one bounded front-end review JSON.

This is a pure IO adapter. It never solves, resamples, interpolates, or repairs
the saved event. Formal output requires the matching independent audit.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import zlib

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, identity, load_bundle, publish_bytes

MAX_JSON_BYTES = 64 * 1024**2
MAX_RSS_BYTES = 1024**3
CASE_SCHEMAS = {"td-entry-shallow-water-state-v1", "td-entry-shallow-water-intervals-v1",
                "td-entry-shallow-water-first-rk-v1"}
FALSE_FLAGS = ("natural_outlet_verified", "complete_river_hydraulics_verified",
               "cross_domain_hydraulics_verified", "vdm_integrated", "full_river_verified")


def _json(path, expected_sha):
    path = Path(path).resolve(strict=True)
    if (not path.is_relative_to(ROOT) or path.stat().st_size > MAX_JSON_BYTES
            or file_sha256(path) != expected_sha):
        raise ValueError("JSON input path/SHA/budget mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def _pin(path, record=None):
    result = {"path": str(Path(path).resolve()), "sha256": file_sha256(path),
              "bytes": Path(path).stat().st_size}
    if record is not None:
        result["identity_sha256"] = record["identity_sha256"]
    return result


def _bundle(pin):
    path = Path(pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT):
        raise ValueError("NPZ input outside workspace")

    def validator(record):
        if record.get("identity_sha256") != identity(record["arrays"], record["metadata"]):
            raise ValueError("NPZ internal identity mismatch")
        for array in record["arrays"].values():
            if not isinstance(array, np.ndarray) or not np.isfinite(array).all():
                raise ValueError("NPZ contains nonfinite or nonarray data")

    record = load_bundle(path, expected_sha256=pin["sha256"], validator=validator,
                         max_bytes=MAX_JSON_BYTES)
    if record["identity_sha256"] != pin.get("identity_sha256"):
        raise ValueError("NPZ external identity mismatch")
    return record


def _memory_check(process, peak):
    memory = process.memory_info()
    peak = max(peak, memory.rss, getattr(memory, "peak_wset", 0))
    if peak > MAX_RSS_BYTES:
        raise MemoryError("review export exceeds hard 1GiB RSS limit")
    return peak


def _encoded_array(array):
    """Compact lossless array encoding; the browser can inflate and parse NPY."""
    value = np.ascontiguousarray(array)
    header = {"dtype": value.dtype.str, "shape": list(value.shape),
              "order": "C", "encoding": "npy-zlib-base64"}
    import io
    stream = io.BytesIO()
    np.save(stream, value, allow_pickle=False)
    header["data"] = base64.b64encode(zlib.compress(stream.getvalue(), 6)).decode("ascii")
    return header


def _array_group(record, names):
    return {name: _encoded_array(record["arrays"][name]) for name in names if name in record["arrays"]}


def _read_event(index_path, input_sha, audit_path, audit_sha, process):
    index = _json(index_path, input_sha)
    audit = _json(audit_path, audit_sha)
    if audit.get("status") != "passed":
        raise ValueError("matching independent audit is not passed")
    if audit.get("index_sha256") != input_sha:
        raise ValueError("audit is not bound to the requested event index")
    if audit.get("local_saved_hydraulics_verified") is not True:
        raise ValueError("saved shallow-water audit gate is not passed")
    if audit.get("time_refinement_verified") is not True:
        raise ValueError("time-refinement audit gate is not passed")
    for name in FALSE_FLAGS:
        if audit.get(name, False) is not False:
            raise ValueError("audit certification flag must remain false: " + name)
    if index.get("schema") != "td-entry-shallow-water-run-v1":
        raise ValueError("unsupported shallow-water event index")
    if index.get("status") in {"diagnostic_failure", "failed"}:
        raise ValueError("event index reports diagnostic failure")
    cases = index.get("cases", [])
    if len(cases) != 4 or any(item.get("status") not in {"saved_requires_independent_audit", "passed"}
                              for item in cases):
        raise ValueError("all four audited event cases are required")
    peak = _memory_check(process, 0)
    carrier = _bundle(index["carrier"])
    geometry = _bundle(index["geometry"])
    forcing = _bundle(index["forcing"])
    peak = _memory_check(process, peak)
    for name, record in (("carrier", carrier), ("geometry", geometry), ("forcing", forcing)):
        if record["metadata"].get("schema") is None:
            raise ValueError("missing carrier schema: " + name)
    if carrier["metadata"].get("schema") != "td-entry-shallow-water-bed-v1":
        raise ValueError("unexpected carrier schema")
    if carrier["metadata"].get("spacing_m") != .175:
        raise ValueError("review requires original 0.175m lattice")
    if carrier["arrays"]["source_bed_m"].shape != carrier["arrays"]["derived_bed_m"].shape:
        raise ValueError("source/derived bed shape mismatch")
    if carrier["arrays"]["overlay_mask"].shape != carrier["arrays"]["derived_bed_m"].shape:
        raise ValueError("overlay mask shape mismatch")
    case_records = []
    for item in sorted(cases, key=lambda value: (value["case_index"], value["level"])):
        state = _bundle(item["state"])
        intervals = _bundle(item["intervals"])
        first_rk = _bundle(item["first_rk"])
        if (state["metadata"].get("schema") not in CASE_SCHEMAS
                or intervals["metadata"].get("schema") not in CASE_SCHEMAS
                or first_rk["metadata"].get("schema") not in CASE_SCHEMAS):
            raise ValueError("case bundle schema mismatch")
        if state["metadata"].get("status") != "completed":
            raise ValueError("case is not completed: " + item["case_id"])
        if (state["metadata"].get("geometry_identity_sha256") != geometry["identity_sha256"]
                or state["metadata"].get("forcing_identity") != forcing["identity_sha256"]):
            raise ValueError("case parent identity mismatch")
        if intervals["metadata"].get("state_identity_sha256") != state["identity_sha256"]:
            raise ValueError("interval state identity mismatch")
        if first_rk["metadata"].get("state_identity_sha256") != state["identity_sha256"]:
            raise ValueError("first RK state identity mismatch")
        if state["arrays"]["depth_m"].shape[0] != len(state["arrays"]["time_s"]):
            raise ValueError("saved depth frame/time mismatch")
        if state["arrays"]["momentum_x_m2_s"].shape != state["arrays"]["depth_m"].shape:
            raise ValueError("saved momentum/depth shape mismatch")
        case_records.append({"case": item, "state": state, "intervals": intervals,
                             "first_rk": first_rk})
        peak = _memory_check(process, peak)
    return index, audit, carrier, geometry, forcing, case_records, peak


def _review(index_path, input_sha, audit_path, audit_sha):
    process = psutil.Process()
    index, audit, carrier, geometry, forcing, cases, peak = _read_event(
        index_path, input_sha, audit_path, audit_sha, process)
    bed = carrier["arrays"]
    global_origin = np.asarray(carrier["metadata"]["global_lattice_origin_m_xz"], dtype=float)
    spacing = float(carrier["metadata"]["spacing_m"])
    if (bed["global_row"].shape != bed["global_column"].shape
            or global_origin.shape != (2,) or not np.isfinite(global_origin).all()):
        raise ValueError("saved global lattice metadata mismatch")
    global_x = global_origin[0] + (bed["global_column"] + .5) * spacing
    global_z = global_origin[1] + (bed["global_row"] + .5) * spacing
    coordinates = np.stack((global_x, bed["derived_bed_m"], global_z), axis=-1)
    if coordinates.shape[:2] != bed["derived_bed_m"].shape:
        raise ValueError("global metric coordinate shape mismatch")
    frames = []
    for item in cases:
        state = item["state"]
        frames.append({"case_id": item["case"]["case_id"], "case_index": item["case"]["case_index"],
                       "level": item["case"]["level"], "max_dt_s": item["case"]["max_dt_s"],
                       "time_s": _encoded_array(state["arrays"]["time_s"]),
                       "depth_m": _encoded_array(state["arrays"]["depth_m"]),
                       "momentum_x_m2_s": _encoded_array(state["arrays"]["momentum_x_m2_s"]),
                       "momentum_z_m2_s": _encoded_array(state["arrays"]["momentum_z_m2_s"]),
                       "diagnostics": item["case"].get("diagnostics", {}),
                       "state_identity_sha256": state["identity_sha256"],
                       "intervals_identity_sha256": item["intervals"]["identity_sha256"],
                       "first_rk_identity_sha256": item["first_rk"]["identity_sha256"]})
    chain = {"xyz_m": bed["chain_xyz_m"].tolist(),
             "native_cell_ids": bed["chain_native_cell_ids"].tolist(),
             "entry_id": carrier["metadata"]["entry_id"],
             "length_m": 90.0, "semantics": "saved upstream port -> land predecessor -> lake anchor -> wet support"}
    tailwater = {"time_s": _encoded_array(forcing["arrays"]["time_s"]),
                 "boundary_stage_m": _encoded_array(forcing["arrays"]["boundary_stage_m"]),
                 "semantics": forcing["metadata"].get("baseline_stage_semantics", "engineering boundary")}
    review = {"schema": "td-entry-shallow-water-review-v1", "status": "formal_review_ready",
              "input_index_sha256": input_sha, "audit_sha256": audit_sha,
              "source_pins": index.get("inputs", {}), "index_pin": _pin(index_path),
              "audit_pin": _pin(audit_path), "carrier_pin": index["carrier"],
              "geometry_pin": index["geometry"], "forcing_pin": index["forcing"],
              "code_sha256": index.get("code_sha256", {}),
              "audit_code_sha256": audit.get("audit_code_sha256", {}),
              "grid": {"shape": list(bed["derived_bed_m"].shape),
                       "spacing_m": carrier["metadata"]["spacing_m"],
                       "origin_m_xz": carrier["metadata"]["global_lattice_origin_m_xz"],
                       "coordinate_system": "model x east, y elevation, z south; row-major [z,x]",
                       "coordinates_encoding": "global_xyz_m row-major"},
              "arrays": {"global_xyz_m": _encoded_array(coordinates),
                         "source_bed_m": _encoded_array(bed["source_bed_m"]),
                         "derived_bed_m": _encoded_array(bed["derived_bed_m"]),
                         "wet_protected_mask": _encoded_array(bed["wet_protected_mask"]),
                         "overlay_mask": _encoded_array(bed["overlay_mask"]),
                         "forcing_mask": _encoded_array(bed["forcing_mask"])},
              "chain_90m": chain, "tailwater": tailwater, "frames": frames,
              "diagnostic_gates": {"independent_audit_status": audit["status"],
                                   "local_saved_hydraulics_verified": audit["local_saved_hydraulics_verified"],
                                   "time_refinement_verified": audit["time_refinement_verified"],
                                   "gross_directional_time_convergence_verified": audit.get("gross_directional_time_convergence_verified", False),
                                   "natural_outlet_verified": False,
                                   "complete_river_hydraulics_verified": False,
                                   "cross_domain_hydraulics_verified": False,
                                   "vdm_integrated": False,
                                   "full_river_verified": False},
              "event_resource": index.get("resource", {}),
              "audit_summary": {key: audit[key] for key in ("carrier", "cases", "comparisons") if key in audit},
              "semantics": "lossless saved event review; no solver, interpolation, resampling, bed or water-surface mutation",
              **{flag: False for flag in FALSE_FLAGS}}
    encoded = json.dumps(review, sort_keys=True, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise MemoryError("review JSON exceeds 64MiB without resampling")
    _memory_check(process, peak)
    return review, encoded


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
        raise ValueError("new review output directory required")
    review, payload = _review(args.input, args.sha256, args.audit, args.audit_sha256)
    output.mkdir(parents=True, exist_ok=False)
    publish_bytes(output / "review.json", payload)
    manifest = {"schema": "td-entry-shallow-water-review-preparation-v1",
                "status": review["status"], "review": _pin(output / "review.json"),
                "input_index_sha256": args.sha256, "audit_sha256": args.audit_sha256,
                "review_identity_sha256": hashlib.sha256(payload).hexdigest(),
                "formal_consumption_requires": "matching independent audit status=passed and all saved cases completed",
                "flags": {flag: review[flag] for flag in FALSE_FLAGS}}
    publish_bytes(output / "index.json", (json.dumps(manifest, sort_keys=True, indent=2)+"\n").encode())
    print(json.dumps(manifest, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
