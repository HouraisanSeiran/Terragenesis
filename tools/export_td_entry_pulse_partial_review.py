"""Pure-IO diagnostic export of the one recovered level, never formal acceptance."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_entry_shallow_water import read_bundle, read_json, check_memory
from tools.export_td_entry_pulse_review import _static, _frame


def export(input_path, input_sha, audit_path, audit_sha, output):
    index = read_json(dict(path=str(input_path.resolve()), sha256=input_sha))
    audit = read_json(dict(path=str(audit_path.resolve()), sha256=audit_sha))
    if (index["schema"] != "td-entry-pulse-interruption-recovery-v1" or index["status"] != "diagnostic_interrupted"
            or audit["status"] != "passed" or audit["index_sha256"] != input_sha
            or audit["time_refinement_verified"] is not False
            or audit["local_saved_hydraulics_verified"] is not True
            or audit["all_water_from_upstream_Q_verified"] is not True
            or len(index["cases"]) != 1 or index["cases"][0]["level"] != 0):
        raise ValueError("partial review requires the independently audited recovered coarse level")
    for name, sha in audit["audit_code_sha256"].items():
        if file_sha256(ROOT/name) != sha:
            raise ValueError("recovery audit implementation changed")
    carrier, geometry, forcing = (read_bundle(index[name]) for name in ("carrier", "geometry", "forcing"))
    review = _static(carrier, geometry, forcing)
    frame, peak = _frame(index["cases"][0], index, forcing, carrier["arrays"]["derived_bed_m"].shape, psutil.Process())
    review.update(schema="td-entry-pulse-partial-review-v1", status="diagnostic_only", formal_consumption_allowed=False,
        formal_refusal_reasons=["fine_level_interrupted_by_host_restart", "time_refinement_not_verified"],
        input_index_sha256=input_sha, audit_sha256=audit_sha,
        index_pin=dict(path=str(input_path.resolve()), sha256=input_sha),
        audit_pin=dict(path=str(audit_path.resolve()), sha256=audit_sha),
        frames=[frame], source_isolated_reception=audit["source_isolated_reception"], comparison=audit["comparison"],
        source_pins=index["inputs"], code_sha256=index["code_sha256"], audit_code_sha256=audit["audit_code_sha256"],
        carrier_pin=index["carrier"], geometry_pin=index["geometry"], forcing_pin=index["forcing"],
        event_resource=index["resource"], local_saved_hydraulics_verified=True, all_water_from_upstream_Q_verified=True,
        single_saved_level_reaches_wet_support=audit["single_saved_level_reaches_wet_support"],
        time_refinement_verified=False, upstream_pulse_to_saved_source_wet_support_verified=False,
        natural_outlet_verified=False, complete_river_hydraulics_verified=False, cross_domain_hydraulics_verified=False,
        vdm_integrated=False, full_river_verified=False,
        export_resource=dict(solver_calls=0, resampling_calls=0, actual_peak_rss_bytes=max(peak, check_memory())),
        semantics="25 actual coarse frames after host interruption; wet-support arrival is one-level evidence, not time-converged or natural-lake certification")
    payload = json.dumps(review, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    manifest = dict(schema="td-entry-pulse-partial-review-export-v1", status="diagnostic_only", formal_consumption_allowed=False,
        review=dict(path=str(output/"review.json"), sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload)),
        input_index_sha256=input_sha, audit_sha256=audit_sha, exporter_code_sha256=file_sha256(Path(__file__)), solver_calls=0)
    manifest_payload = (json.dumps(manifest, sort_keys=True, indent=2)+"\n").encode()
    if len(payload)+len(manifest_payload) > 64*1024**2:
        raise MemoryError("partial lossless review exceeds unchanged 64MiB limit")
    check_memory()
    publish_bytes(output/"review.json", payload)
    publish_bytes(output/"index.json", manifest_payload)
    print(json.dumps(manifest))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--audit-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"verification/natural-river-network"):
        raise ValueError("new bounded partial review directory required")
    export(args.input, args.sha256, args.audit, args.audit_sha256, output)


if __name__ == "__main__":
    main()
