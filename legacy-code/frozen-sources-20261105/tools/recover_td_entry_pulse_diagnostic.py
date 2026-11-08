"""Recover only complete saved pulse records after an interrupted host session."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, load_bundle, publish_bytes
from tools.audit_td_entry_shallow_water import audit_case, read_json, validate_bundle, check_memory
from tools.audit_td_entry_pulse_propagation import audit_preparation, audit_reception

PREPARATION_SHA = "27dfbdee74ee3ed83639e8525a697571d51d26a689b1009a1d1f66217146cf7f"


def pin(path, bundle=None):
    result = dict(path=str(path.resolve()), sha256=file_sha256(path), bytes=path.stat().st_size)
    if bundle is not None:
        result["identity_sha256"] = bundle["identity_sha256"]
    return result


def recover(output):
    preparation_path = ROOT/"verification/natural-river-network/entry-pulse-propagation-prepare-20261006-01/index.json"
    prepared = read_json(dict(path=str(preparation_path), sha256=PREPARATION_SHA))
    preparation_audit_path = preparation_path.parent/"independent-audit.json"
    preparation_audit = read_json(pin(preparation_audit_path))
    if preparation_audit["status"] != "passed" or preparation_audit["index_sha256"] != PREPARATION_SHA:
        raise ValueError("original prepared pulse audit unavailable")
    event_directory = ROOT/"verification/natural-river-network/entry-pulse-propagation-events-20261006-01"
    if psutil.pid_exists(22972) or (event_directory/"index.json").exists():
        raise ValueError("original runner/index may still be live; recovery cannot compete")
    index = dict(prepared, schema="td-entry-pulse-interruption-recovery-v1", status="diagnostic_interrupted",
                 parent=pin(preparation_path), preparation_audit=pin(preparation_audit_path), cases=[], comparisons=[],
                 interrupted_original_directory=str(event_directory), original_runner_pid=22972,
                 host_boot_observed_iso=datetime.fromtimestamp(psutil.boot_time()).astimezone().isoformat(),
                 recovery_observed_iso=datetime.now().astimezone().isoformat())
    preparation, bed, geometry, forcing, longitudinal = audit_preparation(index)
    complete_saved_work = 0
    for level in (0, 1):
        prefix = "isolated-normal-pulse-retreat-level-"+str(level)
        filenames = {name: event_directory/(prefix+"-"+suffix+".npz") for name, suffix in
                     (("state", "state"), ("intervals", "intervals"), ("first_rk", "first-rk"))}
        if not all(path.is_file() for path in filenames.values()):
            continue
        case = dict(case_id=prefix, case_index=0, level=level, max_dt_s=prepared["declared_maxdt_s"][level],
                    status="saved_requires_independent_audit")
        for name, path in filenames.items():
            bundle = load_bundle(path, expected_sha256=file_sha256(path), validator=validate_bundle, max_bytes=1024**3)
            case[name] = pin(path, bundle)
            if name == "state":
                if bundle["metadata"]["status"] != "completed" or bundle["metadata"]["committed_time_s"] != 240.:
                    raise ValueError("partial event cannot masquerade as complete saved level")
                complete_saved_work += bundle["metadata"]["face_evaluations"]*3//2
            del bundle
        index["cases"].append(case)
    if len(index["cases"]) != 1 or index["cases"][0]["level"] != 0:
        raise ValueError("recovery expects the one actually preserved complete coarse level")
    report, compact = audit_case(index["cases"][0], bed, geometry, forcing, longitudinal)
    reception = audit_reception(index["cases"][0], bed, geometry, forcing, longitudinal)
    index["resource"] = dict(complete_saved_face_work_units=complete_saved_work, max_work=6_000_000_000,
        uncheckpointed_fine_attempt_work_unknown=True, conservatively_reserved_total_face_work_units=6_000_000_000,
        original_runner_peak_rss_unknown=True, recovery_peak_rss_bytes=check_memory(), solver_calls=0,
        semantics="complete saved coarse work is exact; lost fine work is not estimated, remaining original allocation remains reserved")
    index_payload = (json.dumps(index, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    publish_bytes(output/"index.json", index_payload)
    result = dict(schema="td-entry-pulse-recovered-independent-audit-v1", status="passed", recovery_status="diagnostic_interrupted",
        index_sha256=file_sha256(output/"index.json"), preparation=preparation, cases=[report], source_isolated_reception=[reception],
        local_saved_hydraulics_verified=True, all_water_from_upstream_Q_verified=True,
        time_refinement_verified=False, upstream_pulse_to_saved_source_wet_support_verified=False,
        single_saved_level_reaches_wet_support=reception["upstream_pulse_to_saved_source_wet_support_verified"],
        comparison=dict(passed=False, status="unavailable_after_host_restart", coarse_level_saved=True, fine_level_saved=False),
        actual_lake_boundary_hydraulics_verified=False, natural_outlet_verified=False,
        complete_river_hydraulics_verified=False, cross_domain_hydraulics_verified=False,
        complete_saved_face_work_units=complete_saved_work, recovery_peak_rss_bytes=check_memory(), solver_calls=0,
        scope="one complete source-isolated level only; no fine-level convergence certification",
        audit_code_sha256={name: file_sha256(ROOT/name) for name in (
            "tools/recover_td_entry_pulse_diagnostic.py", "tools/audit_td_entry_pulse_propagation.py",
            "tools/audit_td_entry_shallow_water.py", "tools/td_entry_saved_audit.py", "tools/single_domain_shallow_water_audit.py")})
    publish_bytes(output/"independent-audit.json", (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode())
    print(json.dumps({name: value for name, value in result.items() if name not in ("cases", "source_isolated_reception", "audit_code_sha256")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"verification/natural-river-network"):
        raise ValueError("new recovery directory required")
    recover(output)


if __name__ == "__main__":
    main()
