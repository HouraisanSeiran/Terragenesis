"""Publish explicitly pinned accepted TD review or isolated geometry candidates."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_surface_reaches import _plain
from terrain_pipeline.td_hour_pages_review import export_hour_pages_review, load_hour_pages_review
from tools.audit_td_hour_pages_binary import audit as audit_binary

DEPENDENCIES = ("tools/publish_td_accepted_review.py", "tools/audit_td_hour_pages_binary.py",
    "tools/audit_td_accepted_morphology.py", "terrain_pipeline/td_hour_pages_review.py",
    "terrain_pipeline/td_hour_pages_acceptance_io.py", "terrain_pipeline/td_accepted_water_morphology.py")


def frozen_dependencies():
    return {name: file_sha256(ROOT / name) for name in DEPENDENCIES}


def recheck_dependencies(pins, acceptance_path, acceptance_sha256):
    from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256

    if frozen_dependencies() != pins or file_sha256(acceptance_path) != acceptance_sha256:
        raise ValueError("publisher dependencies or acceptance changed during publication")
    if file_sha256(PRIMARY_PATH) != PRIMARY_SHA256:
        raise ValueError("original primary source changed during publication")


def quarantine(output, error):
    if not output.exists():
        return
    destination = output.with_name(output.name + "-rejected-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.rename(destination)
    index = destination / "index.json"
    if index.is_file():
        index.rename(destination / "rejected-index.json")
    publish_bytes(destination / "rejected.json", json.dumps(dict(accepted=False, reason=str(error),
        intended_output=str(output), artifacts_retained_for_diagnosis=True), indent=2).encode("utf-8"))


def accepted_inputs(path, expected_sha256):
    path = Path(path).resolve(strict=True)
    if path.stat().st_size > 8 * 1024 ** 2 or file_sha256(path) != expected_sha256:
        raise ValueError("independent acceptance external pin/budget mismatch")
    accepted = json.loads(path.read_text(encoding="utf-8"))
    if (accepted.get("schema") != "td-independent-final-continuation-acceptance-v1" or
            accepted.get("all_saved_numerical_gates_passed") is not True or
            accepted.get("original_inputs_and_frozen_code_unchanged") is not True or
            accepted["cold_acceptance"]["io_chain_accepted"] is not True or
            accepted["input_index_sha256"] != accepted["acceptance_arguments"]["expected_sha256"]):
        raise ValueError("complete independently accepted two-rain continuation required")
    if set(accepted["numerical_reports"]) != {"ordinary", "strong"}:
        raise ValueError("both independent numerical reports required")
    for scenario, record in accepted["numerical_reports"].items():
        report_path = Path(record["path"]).resolve(strict=True)
        if report_path.stat().st_size > 8 * 1024 ** 2 or file_sha256(report_path) != record["expected_sha256"]:
            raise ValueError("independent numerical report external pin mismatch")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        cold = accepted["cold_acceptance"]["scenarios"][scenario]
        if (report["scenario"] != scenario or report["saved_frames"] != 25 or
                report["checkpoint_chain_checked"] is not True or report["gate_passed"] is not True or
                cold["numerical_gate_passed"] is not True or
                report["max_saved_depth_difference_m"] != cold["depth_difference_m"] or
                report["cumulative_receiver_relative_l1"] != cold["receiver_relative_l1"]):
            raise ValueError("independent numerical report differs from accepted final")
    if file_sha256(accepted["input_index"]) != accepted["input_index_sha256"]:
        raise ValueError("accepted original final index changed")
    return accepted


def publish_review(acceptance_path, acceptance_sha256, output, *, include_hour_flux=False):
    pins = frozen_dependencies()
    accepted = accepted_inputs(acceptance_path, acceptance_sha256)
    output = Path(output).absolute()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".accepted-review-", dir=output.parent))
    staged_review = staging / "review"
    options = dict(input_index=accepted["input_index"], acceptance_arguments=accepted["acceptance_arguments"],
                   selected_steps_s=(1.25,), include_hour_flux=include_hour_flux, output_budget_bytes=536870912)
    try:
        result = export_hour_pages_review(directory=staged_review, **options)
        index = staged_review / "index.json"
        digest = file_sha256(index)
        load_hour_pages_review(index, expected_sha256=digest, expected_identity=result["identity_sha256"], **options)
        report = audit_binary(index, digest)
        recheck_dependencies(pins, acceptance_path, acceptance_sha256)
        staged_review.rename(output)
        report["input_index"] = str(output / "index.json")
    except BaseException as error:
        quarantine(staged_review, error)
        raise
    finally:
        if staging.exists() and not any(staging.iterdir()):
            staging.rmdir()
    index = output / "index.json"
    return dict(stage="native_review", index=dict(path=str(index), expected_sha256=digest,
        expected_identity=result["identity_sha256"]), independent_native_audit=report,
        acceptance=dict(path=str(Path(acceptance_path).resolve()), expected_sha256=acceptance_sha256),
        code_sha256=pins,
        all_saved_numerical_gates_passed=True, frontend_connected=False, hydraulic_ready=False,
        natural_outlet_verified=False, publishable=False)


def publish_geometry(acceptance_path, acceptance_sha256, output, source_record):
    from terrain_pipeline.td_accepted_water_morphology import export_accepted_water_morphology, load_accepted_water_morphology, MATERIAL_PATH, MATERIAL_SHA, MATERIAL_ID
    from tools.audit_td_accepted_morphology import audit

    pins = frozen_dependencies()
    accepted = accepted_inputs(acceptance_path, acceptance_sha256)
    output = Path(output).absolute()
    if output.exists():
        raise FileExistsError(output)
    options = dict(input_index=accepted["input_index"], acceptance_arguments=accepted["acceptance_arguments"],
                   source_record=source_record, material_record=dict(path=str(MATERIAL_PATH), expected_sha256=MATERIAL_SHA, expected_identity=MATERIAL_ID))
    try:
        result = export_accepted_water_morphology(directory=output, **options)
        index = output / "index.json"
        digest = file_sha256(index)
        load_accepted_water_morphology(index, expected_sha256=digest, expected_identity=result["identity_sha256"], **options)
        report = audit(index, digest, acceptance_path, acceptance_sha256)
        recheck_dependencies(pins, acceptance_path, acceptance_sha256)
    except BaseException as error:
        quarantine(output, error)
        raise
    return dict(stage="geometry_only", index=dict(path=str(index), expected_sha256=digest, expected_identity=result["identity_sha256"]),
        independent_morphology_audit=report, code_sha256=pins, recoupling_required=True, topology_rebuild_pending=True,
        selection="baseline pending", frontend_connected=False, hydraulic_ready=False, natural_outlet_verified=False, publishable=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("review", "geometry"), required=True)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--acceptance-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-hour-flux", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-sha256")
    parser.add_argument("--source-identity")
    args = parser.parse_args()
    if args.stage == "geometry":
        if args.source is None or args.source_sha256 is None or args.source_identity is None or args.include_hour_flux:
            parser.error("geometry requires explicit source SHA/identity and no review flux option")
        source = dict(path=str(args.source.resolve(strict=True)), expected_sha256=args.source_sha256, expected_identity=args.source_identity)
        result = publish_geometry(args.acceptance, args.acceptance_sha256, args.output, source)
    else:
        if any(value is not None for value in (args.source, args.source_sha256, args.source_identity)):
            parser.error("source options belong to geometry stage")
        result = publish_review(args.acceptance, args.acceptance_sha256, args.output, include_hour_flux=args.include_hour_flux)
    result["publisher_sha256"] = file_sha256(__file__)
    report_path = ROOT / "verification/td-basin-generation" / ("independent-published-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(report_path, json.dumps(_plain(result), indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(report=str(report_path), report_sha256=file_sha256(report_path), index=result["index"])))


if __name__ == "__main__":
    main()
