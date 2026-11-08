"""Read-only readiness inventory for interrupted v10 weather checkpoints."""

from dataclasses import asdict
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.runoff import RunoffParameters as RunoffParameters
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import PRIMARY_PATH as PRIMARY_PATH
from terrain_pipeline.basin_storage import PRIMARY_SHA256 as PRIMARY_SHA256
from terrain_pipeline.basin_storage import load_td_source_bundle as load_td_source_bundle
from terrain_pipeline.td_native_weather_storage_inputs import load_weather_inputs
from terrain_pipeline.td_native_weather_storage_v10_io import PHYSICS, load_native_weather_v10_hour


ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = ("eastward", "westward")
STEPS = (2.5, 1.25)
EXPECTED_WEATHER_SHA256 = "333046a82778411b95bcb691988a7b016347de1ad288ad2d841cc6a089bb1271"


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _pin(record, path):
    _require(set(record) == {"path", "expected_sha256", "expected_identity"}, "artifact pin fields mismatch")
    _require(Path(record["path"]).resolve() == path.resolve(), "artifact pin path mismatch")
    _require(path.is_file() and not path.is_symlink(), "artifact missing or symlinked")
    _require(file_sha256(path) == record["expected_sha256"], "artifact SHA mismatch")


def _codes(inputs):
    codes = inputs.get("code_sha256")
    _require(isinstance(codes, dict) and codes, "frozen code pins missing")
    for name, digest in codes.items():
        path = (ROOT / name).resolve()
        _require(path.is_relative_to(ROOT) and path.is_file() and file_sha256(path) == digest,
                 "frozen code changed: " + name)


def inspect_prefix(run, *, run_inputs_sha256):
    run = Path(run).resolve(strict=True)
    input_path = run / "run-inputs.json"
    _require(input_path.is_file() and file_sha256(input_path) == run_inputs_sha256, "run-inputs external pin mismatch")
    inputs = json.loads(input_path.read_text(encoding="utf-8"))
    _require(inputs.get("schema") == "td-v10-spatial-weather-run-inputs-v1"
             and inputs.get("steps_s") == list(STEPS)
             and inputs.get("physics_version") == "v10-unified-infiltration; not execution-equivalence"
             and inputs.get("primary_sha256") == PRIMARY_SHA256
             and inputs.get("chunk_max_face_steps") == 6000000000
             and inputs.get("job_max_bytes") == 1073741824
             and inputs.get("depth_gate_m") == .001 and inputs.get("receiver_gate") == .01,
             "v10 original run contract mismatch")
    _require(Path(PRIMARY_PATH).is_file() and file_sha256(PRIMARY_PATH) == PRIMARY_SHA256,
             "original primary source changed")
    _codes(inputs)
    hierarchy_record = inputs["hierarchy"]
    hierarchy = load_basin_hierarchy(**hierarchy_record)
    weather_record = inputs["weather_index"]
    _require(weather_record["sha256"] == EXPECTED_WEATHER_SHA256, "original weather index mismatch")
    weather = load_weather_inputs(weather_record["path"], expected_sha256=weather_record["sha256"], hierarchy=hierarchy)
    _require(weather["index_pin"] == weather_record, "weather index pin mismatch")
    source_record = weather["source"]
    source = load_td_source_bundle(**source_record)
    _require(source["metadata"]["source_sha256"] == PRIMARY_SHA256, "original source identity mismatch")
    for name in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask"):
        _require(np.array_equal(source["arrays"][name], hierarchy["arrays"][name]), "source/hierarchy mismatch: " + name)
    _require(not source["arrays"]["protected_mask"].any(), "protected source rejected")
    faces = len(hierarchy["arrays"]["face_cells"])
    budgets = {str(step): {"chunk_face_steps": math.ceil(3600 / step) * faces,
                           "global_face_steps_per_direction": 24 * math.ceil(3600 / step) * faces} for step in STEPS}
    _require(inputs.get("budgets") == budgets, "work budgets mismatch")
    _require(set(inputs.get("weather_records", {})) == set(DIRECTIONS)
             and set(inputs.get("forcing_identities", {})) == set(DIRECTIONS), "weather direction coverage mismatch")
    groups = {}
    for direction in DIRECTIONS:
        case = weather["cases"][direction]
        _require(inputs["weather_records"][direction] == case["record"]
                 and inputs["forcing_identities"][direction] == case["forcing_identity"],
                 "weather artifact/forcing identity mismatch")
        for step in STEPS:
            group = run / f"{direction}-{step:g}s"
            _require(not group.exists() or group.is_dir() and not group.is_symlink(), "invalid group directory")
            names = [] if not group.exists() else [entry.name for entry in group.iterdir()]
            _require(all(name.startswith("hour-") and len(name) == 7 and name[5:].isdigit()
                         and int(name[5:]) < 24 for name in names), "unexpected group entry")
            _require(all((group / name).is_dir() and not (group / name).is_symlink() for name in names),
                     "invalid hour directory")
            present = sorted(int(name[5:]) for name in names)
            reported = [hour for hour in present if (group / f"hour-{hour:02d}" / "report.json").is_file()]
            _require(reported == list(range(len(reported))), "missing hour or gap in reported prefix")
            ignored = [hour for hour in present if hour not in reported]
            _require(not reported or not any(hour < reported[-1] for hour in ignored), "orphan partial within prefix")
            _require(len(ignored) <= 1 and (not ignored or ignored[0] == len(reported)),
                     "orphan or gapped partial tail")
            previous = None
            pages = []
            budgets_seen = []
            for hour in reported:
                page_dir = group / f"hour-{hour:02d}"
                _require({entry.name for entry in page_dir.iterdir()} == {"report.json", "storage.npz", "checkpoint.npz"},
                         "hour files missing or extra")
                report_path = page_dir / "report.json"
                _require(not report_path.is_symlink(), "report symlink rejected")
                report = json.loads(report_path.read_text(encoding="utf-8"))
                _require(set(report) == {"hour", "storage", "checkpoint", "elapsed_s", "forcing_identity",
                                         "chunk_work_face_steps", "global_water_residual_m3"}
                         and type(report["hour"]) is int and report["hour"] == hour
                         and report["forcing_identity"] == case["forcing_identity"]
                         and report["chunk_work_face_steps"] == budgets[str(step)]["chunk_face_steps"]
                         and type(report["elapsed_s"]) in (int, float) and math.isfinite(report["elapsed_s"])
                         and report["elapsed_s"] > 0, "hour report mismatch")
                for kind in ("storage", "checkpoint"):
                    _pin(report[kind], page_dir / f"{kind}.npz")
                result = load_native_weather_v10_hour(
                    report["storage"], report["checkpoint"], hierarchy=hierarchy,
                    rain_mm_h=case["rain_mm_h"][hour], forcing_identity=case["forcing_identity"],
                    hour=hour, step_s=step, parameters=PHYSICS,
                    runoff_parameters=asdict(RunoffParameters()), previous_checkpoint_record=previous)
                residual = float(result["storage"]["arrays"]["balance_residual_m3"].sum())
                _require(report["global_water_residual_m3"] == residual, "reported water residual mismatch")
                budgets_seen.append(result["budget"])
                pages.append({"hour": hour, "report_sha256": file_sha256(report_path),
                              "storage": report["storage"], "checkpoint": report["checkpoint"]})
                previous = report["checkpoint"]
                del result
            cumulative = None
            if budgets_seen:
                rain = math.fsum(item["rain_m3"] for item in budgets_seen)
                residual = math.fsum([budgets_seen[0]["initial_water_m3"], rain,
                                      -math.fsum(item["loss_m3"] for item in budgets_seen),
                                      -math.fsum(item["external_m3"] for item in budgets_seen),
                                      -budgets_seen[-1]["final_water_m3"]])
                allowed = 1e-6 + rain * 1e-10
                _require(abs(residual) <= allowed, "cumulative prefix water budget failed")
                cumulative = {"residual_m3": residual, "allowed_m3": allowed, "passed": True}
            groups[f"{direction}-{step:g}s"] = {"verified_hours": len(pages), "pages": pages,
                "last_checkpoint": previous, "cumulative_budget": cumulative,
                "ignored_unrecoverable_tail_hours": ignored}
    _require({entry.name for entry in run.iterdir() if entry.is_dir()} <= set(groups), "unexpected run group")
    _require(file_sha256(input_path) == run_inputs_sha256, "run-inputs changed during audit")
    _require(file_sha256(PRIMARY_PATH) == PRIMARY_SHA256, "primary changed during audit")
    _require(file_sha256(hierarchy_record["path"]) == hierarchy_record["expected_sha256"]
             and file_sha256(source_record["path"]) == source_record["expected_sha256"]
             and file_sha256(weather_record["path"]) == weather_record["sha256"], "input changed during audit")
    for case in weather["cases"].values():
        _require(file_sha256(case["record"]["path"]) == case["record"]["expected_sha256"], "weather changed during audit")
    _codes(inputs)
    return {"schema": "td-v10-weather-prefix-recovery-readiness-v1", "run": str(run),
            "run_inputs_sha256": run_inputs_sha256, "source": source_record, "hierarchy": hierarchy_record,
            "weather_index": weather_record, "weather_records": inputs["weather_records"],
            "code_sha256": inputs["code_sha256"], "groups": groups,
            "prefix_io_chain_verified": True, "resource_authenticated": False,
            "complete_run_accepted": False, "resume_authorized": False,
            "acceptance_index_generated": False, "solver_advanced": False,
            "limitations": "Read-only saved prefix; missing final index/resource prevents execution authentication. "
                           "Unknown tail without report is ignored and unrecoverable; no automatic resume."}
