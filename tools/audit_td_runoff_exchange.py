"""Independent saved-array water accounts and fixed-forcing temporal audit."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import load_overflow_topology as load_overflow_topology
from terrain_pipeline.basin_storage import load_runoff_exchange as load_runoff_exchange

CASES = {"normal-spatial-recession-24h": (30., 86400.), "strong-spatial-recession-6h": (120., 21600.)}


def verify_controls(event, level):
    number = level["level"]
    expected = {"max_step_s": 300. / 2**number, "rtol": 5e-7 / 2**number,
                "atol_stage_m": 2e-7 / 2**number, "flux_atol_m3": .001 / 2**number}
    if level["controls"] != expected or any(event["metadata"].get(name) != value for name, value in expected.items()):
        raise ValueError("saved event controls do not prove actual two-level refinement")


def audit_arrays(topology, event):
    arrays = event["arrays"]
    rain, et = arrays["rain_volume_m3"], arrays["et_volume_m3"]
    steps, count = rain.shape
    lookup = {int(leaf): position for position, leaf in enumerate(topology["arrays"]["leaf_ids"])}
    net = np.zeros((steps, count))
    forward, reverse = arrays["face_forward_m3"], arrays["face_reverse_m3"]
    for position, face in enumerate(topology["faces"]):
        first, second = (lookup[leaf] for leaf in face["leaf_ids"])
        signed = forward[:, position] - reverse[:, position]
        net[:, first] -= signed
        net[:, second] += signed
    boundary = np.zeros_like(net)
    for position, face in enumerate(topology["engineering_boundaries"]):
        boundary[:, lookup[face["leaf_id"]]] += arrays["engineering_boundary_outflow_m3"][:, position]
    factor = topology["arrays"]["leaf_area_m2"] / 1000.
    stores = {name: arrays[name + "_mm"] * factor for name in ("soil", "fast", "slow")}
    stores["surface"] = arrays["surface_volume_m3"]
    local_storage = stores["soil"] + stores["fast"] + stores["slow"]
    runoff_residual = rain - et - arrays["outflow_volume_m3"] - np.diff(local_storage, axis=0)
    surface_residual = arrays["outflow_volume_m3"] + net - boundary - np.diff(stores["surface"], axis=0)
    total = local_storage + stores["surface"]
    total_residual = rain - et + net - boundary - np.diff(total, axis=0)
    global_residual = rain.sum(axis=1) - et.sum(axis=1) - boundary.sum(axis=1) - np.diff(total.sum(axis=1))
    components = {
        "soil": arrays["infiltration_mm"] - arrays["actual_et_mm"] - arrays["percolation_mm"] - np.diff(arrays["soil_mm"], axis=0),
        "fast": arrays["excess_mm"] - arrays["fast_release_mm"] - np.diff(arrays["fast_mm"], axis=0),
        "slow": arrays["percolation_mm"] - arrays["slow_release_mm"] - np.diff(arrays["slow_mm"], axis=0),
    }
    maximum = {"runoff_m3": float(np.abs(runoff_residual).max()), "surface_m3": float(np.abs(surface_residual).max()),
               "total_per_leaf_m3": float(np.abs(total_residual).max()), "global_m3": float(np.abs(global_residual).max())}
    maximum.update({name + "_component_m3": float(np.max(np.abs(residual * factor))) for name, residual in components.items()})
    if any(value > 1e-7 for value in maximum.values()):
        raise ValueError("independent water ledger failed: " + json.dumps(maximum))
    curves = topology["arrays"]
    stage_error = 0.
    for leaf, (start, end) in enumerate(zip(curves["curve_offsets"][:-1], curves["curve_offsets"][1:])):
        volumes = np.sum(np.maximum(arrays["stage_m"][:, leaf, None] - curves["curve_level_m"][start:end], 0.) * curves["curve_area_m2"][start:end], axis=1)
        error = np.abs(volumes - arrays["surface_volume_m3"][:, leaf])
        stage_error = max(stage_error, float(error.max()))
        if np.any(error > 1e-6 + arrays["surface_volume_m3"][:, leaf] * 1e-10):
            raise ValueError("independent original-bed stage-volume inversion failed")
    gross = float((forward + reverse).sum())
    canceled = float(2. * np.minimum(forward.sum(axis=0), reverse.sum(axis=0)).sum())
    return {"passed": True, "max_residuals": maximum, "max_stage_volume_error_m3": stage_error,
            "canceled_fraction_of_gross": canceled / gross if gross else 0.,
            "active_faces": int(np.count_nonzero((forward + reverse).sum(axis=0))),
            "rain_m3": float(rain.sum()), "et_m3": float(et.sum()), "external_outflow_m3": float(boundary.sum()),
            "final_stores_m3": {name: float(value[-1].sum()) for name, value in stores.items()},
            "initial_stores_m3": {name: float(value[0].sum()) for name, value in stores.items()},
            "source_terms": "rain minus ET; runoff and inter-basin exchange are internal transfers, not new water"}


def audit(directory, expected_sha256, *, report_name="independent-audit-v2.json"):
    directory = Path(directory).resolve(strict=True)
    path = directory / "index.json"
    if file_sha256(path) != expected_sha256:
        raise ValueError("coupled index hash mismatch")
    index = json.loads(path.read_text(encoding="utf-8"))
    if (index.get("schema") != "td-runoff-exchange-refinement-v1"
            or len(index["cases"]) != 2 or {case["name"] for case in index["cases"]} != set(CASES)
            or any(index.get(flag) is not False for flag in ("hydraulic_ready", "natural_outlet_verified", "publishable", "full_coupled_timestep_refinement_passed", "tailwater_verified"))):
        raise ValueError("coupled audit case coverage/schema/certification mismatch")
    for name, expected in index["configuration"]["code_sha256"].items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("coupled event code pin mismatch")
    parent_pin = index["configuration"]["parent_index"]
    if file_sha256(parent_pin["path"]) != parent_pin["sha256"]:
        raise ValueError("original-bed parent input pin mismatch")
    parent = json.loads(Path(parent_pin["path"]).read_text(encoding="utf-8"))
    if parent["topology"] != index["configuration"]["topology"]:
        raise ValueError("new event topology differs from fixed original-bed parent")
    pin = index["configuration"]["topology"]
    topology = load_overflow_topology(pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    levels = topology["arrays"]["curve_level_m"][topology["arrays"]["curve_offsets"][:-1]]
    factor = .7 + .6 * (levels - levels.min()) / max(float(np.ptp(levels)), 1.)
    factor /= float(np.average(factor, weights=topology["arrays"]["leaf_area_m2"]))
    cases = []
    with patch('terrain_pipeline.basin_storage.simulate_runoff_exchange', side_effect=AssertionError("cold audit forbids solving")), patch('scipy.integrate.Radau', side_effect=AssertionError("cold audit forbids Radau")):
        for case in index["cases"]:
            if [level["level"] for level in case["levels"]] != [0, 1]:
                raise ValueError("cold audit requires exactly two actual refinement levels")
            rain_rate, duration = CASES[case["name"]]
            steps = int(duration / 300.)
            expected_rain = np.zeros((steps, len(factor)))
            expected_rain[:steps // 2] = rain_rate * factor
            events, records = [], []
            for level in case["levels"]:
                pin = level["event"]
                event = load_runoff_exchange(directory / pin["path"], expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"], topology=topology)
                verify_controls(event, level)
                if (event["metadata"]["duration_s"] != duration or event["metadata"]["timestep_s"] != 300.
                        or not np.array_equal(event["arrays"]["rain_mm_h"], expected_rain)
                        or np.count_nonzero(event["arrays"]["surface_volume_m3"][0]) != 0):
                    raise ValueError("cold audit source scenario, saved duration, or initial condition differs")
                events.append(event)
                records.append({"identity_sha256": event["identity_sha256"], "ledger": audit_arrays(topology, event)})
            first, second = (event["arrays"] for event in events)
            if (not np.array_equal(first["outflow_volume_m3"], second["outflow_volume_m3"])
                    or events[0]["identity_sha256"] == events[1]["identity_sha256"]
                    or events[0]["metadata"]["parameters"] != events[1]["metadata"]["parameters"]
                    or events[0]["metadata"]["runoff_metadata"] != events[1]["metadata"]["runoff_metadata"]):
                raise ValueError("cold refinement forcing differs")
            stage = float(np.max(np.abs(first["stage_m"] - second["stage_m"])))
            first_net = np.cumsum(first["face_forward_m3"] - first["face_reverse_m3"], axis=0)
            second_net = np.cumsum(second["face_forward_m3"] - second["face_reverse_m3"], axis=0)
            numerator, denominator = np.abs(first_net - second_net).sum(axis=1), np.abs(second_net).sum(axis=1)
            relative = float(np.max(np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 0.)))
            passed = stage <= .001 and relative <= .01 and not np.any((denominator == 0.) & (numerator > 1e-8))
            cases.append({"name": case["name"], "levels": records, "max_stage_error_m": stage,
                          "max_cumulative_net_relative_l1": relative, "surface_time_refinement_passed": bool(passed)})
    resource = index["resources"]
    if resource["peak_rss_bytes"] > 1024**3 or resource["counted_rhs_work"] > 6_000_000_000 or resource["monitor_error"]:
        raise ValueError("coupled event resource audit failed")
    report = {"schema": "td-runoff-exchange-independent-audit-v2", "status": "passed" if all(case["surface_time_refinement_passed"] for case in cases) else "diagnostic_failure",
              "index_sha256": expected_sha256, "cases": cases, "cold_read": True, "solver_advanced": False,
              "scope": "four inventory ledgers and fixed-forcing surface-integrator time refinement; not full coupled timestep convergence",
              "resources": resource, "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
              "full_coupled_timestep_refinement_passed": False, "tailwater_verified": False}
    if Path(report_name).name != report_name or not report_name.endswith(".json"):
        raise ValueError("audit report must be a local JSON filename")
    publish_bytes(directory / report_name, json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--report-name", default="independent-audit-v2.json")
    args = parser.parse_args()
    report = audit(args.directory, args.index_sha256, report_name=args.report_name)
    print(json.dumps({"status": report["status"], "cases": [{key: value for key, value in case.items() if key != "levels"} for case in report["cases"]]}, ensure_ascii=False))
