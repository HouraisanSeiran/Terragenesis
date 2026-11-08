"""Read pinned causal restart arrays and independently recompute their evidence."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record


def reduce_case(initial, arrays, topology, spacing, *, transport_only):
    states = arrays["states"]
    ledger = arrays["ledger"]
    cells = initial.shape[1]
    faces = topology["face_cells"]
    if states.shape != (4, cells) or ledger.shape != (8, cells):
        raise ValueError("causal inventory/ledger shape invalid")
    for name, values in arrays.items():
        if not np.isfinite(values).all() or (name not in ("errors", "ledger") and np.any(values < 0)):
            raise ValueError("causal arrays nonfinite/negative")
    forward, reverse = arrays["face_forward_m3"], arrays["face_reverse_m3"]
    if forward.shape != (len(faces),) or reverse.shape != forward.shape:
        raise ValueError("causal face shape invalid")
    signed = forward - reverse
    net = np.bincount(faces[:, 1], weights=signed, minlength=cells) - np.bincount(faces[:, 0], weights=signed, minlength=cells)
    area = spacing ** 2
    change = area * (states[0] - initial[0] + (states[1:] - initial[1:]).sum(axis=0) / 1000)
    if transport_only:
        np.testing.assert_array_equal(states[1:], initial[1:])
        np.testing.assert_array_equal(ledger[:7], 0.)
    else:
        np.testing.assert_allclose(ledger[6], net, rtol=1e-10, atol=1e-7)
        np.testing.assert_allclose(ledger[0], ledger[1] + ledger[2], rtol=0, atol=1e-9)
    boundary_mask = np.zeros(cells, bool)
    boundary_mask[topology["boundary_cells"]] = True
    if np.any(ledger[7, ~boundary_mask] != 0) or np.any(ledger[7] < 0):
        raise ValueError("causal undeclared/negative external outflow")
    residual = change - ledger[0] + ledger[3] + ledger[5] + ledger[7] - net
    if np.max(abs(residual), initial=0) > 1e-6 or abs(float(residual.sum())) > 1e-6:
        raise ValueError("independent causal cell/whole water budget failed")
    return dict(whole_residual_m3=float(residual.sum()), max_cell_residual_m3=float(abs(residual).max()),
                boundary_export_m3=float(ledger[7].sum()), budget_passed=True)


def audit(directory, inputs_sha256, report_sha256):
    directory = Path(directory).resolve(strict=True)
    paths = (directory / "inputs.json", directory / "report.json")
    for path, expected in zip(paths, (inputs_sha256, report_sha256)):
        if file_sha256(path) != expected:
            raise ValueError("external causal input/report pin mismatch")
    inputs, report = (json.loads(path.read_text(encoding="utf-8")) for path in paths)
    if inputs["schema"] != "td-weather-common-state-causality-v1" or report["schema"] != "td-weather-causal-isolation-report-v1":
        raise ValueError("causal schema mismatch")
    if file_sha256(inputs["index_pin"]["path"]) != inputs["index_pin"]["sha256"]:
        raise ValueError("causal source index changed")
    static, metadata = read_record(inputs["static_page"])
    fine, fine_metadata = read_record(inputs["fine_checkpoint"])
    coarse, coarse_metadata = read_record(inputs["coarse_checkpoint"])
    if fine_metadata["elapsed_s"] != 64800 or coarse_metadata["elapsed_s"] != 64800 or inputs["duration_s"] != 3600:
        raise ValueError("causal restart experiment coverage mismatch")
    states = ("depth_m", "soil_mm", "fast_mm", "slow_mm")
    initial_fine = np.vstack([fine[name] for name in states])
    initial_coarse = np.vstack([coarse[name] for name in states])
    expected_keys = {f"{mode}-{step:g}" for mode in ("normal", "transport_only") for step in (2.5, 1.25, .625, .3125)} | {"normal_coarse_initial-1.25"}
    if set(report["records"]) != expected_keys:
        raise ValueError("causal experiment case coverage mismatch")
    audits, depth = {}, {}
    for key, record in report["records"].items():
        artifact = Path(record["artifact"]["path"]).resolve(strict=True)
        if artifact.parent != directory or artifact.stat().st_size > 64 * 1024 * 1024 or file_sha256(artifact) != record["artifact"]["sha256"]:
            raise ValueError("causal artifact pin/path/budget mismatch")
        with np.load(artifact, allow_pickle=False) as archive:
            if set(archive.files) != {"states", "errors", "ledger", "face_forward_m3", "face_reverse_m3"}:
                raise ValueError("causal raw array keys mismatch")
            arrays = {name: archive[name] for name in archive.files}
        initial = initial_coarse if key.startswith("normal_coarse_initial") else initial_fine
        audits[key] = reduce_case(initial, arrays, static, metadata["spacing_m"], transport_only=key.startswith("transport_only"))
        depth[key] = arrays["states"][0].copy()
        if abs(record["water_residual_m3"] - audits[key]["whole_residual_m3"]) > 1e-6:
            raise ValueError("causal reported budget mismatch")
        step = float(key.rsplit("-", 1)[1])
        if record["face_steps"] != int(3600 / step) * len(static["face_cells"]) or record["face_steps"] > 6000000000:
            raise ValueError("causal actual work mismatch")
        if record["hotspot_depth_m"] != depth[key][60279] or record["max_depth_m"] != depth[key].max():
            raise ValueError("causal reported depth mismatch")
    comparisons = {}
    for mode in ("normal", "transport_only"):
        for first, second in ((2.5, 1.25), (1.25, .625), (.625, .3125)):
            key = f"{mode}-{first:g}-vs-{second:g}"
            difference = depth[f"{mode}-{first:g}"] - depth[f"{mode}-{second:g}"]
            reduced = dict(max_depth_difference_m=float(abs(difference).max()), max_cell=int(abs(difference).argmax()),
                           hotspot_difference_m=float(difference[60279]))
            if report["comparisons"][key] != reduced:
                raise ValueError("causal published refinement mismatch")
            comparisons[key] = reduced
    difference = depth["normal_coarse_initial-1.25"] - depth["normal-1.25"]
    initial_difference = initial_coarse[0] - initial_fine[0]
    effect = dict(initial_max_difference_m=float(abs(initial_difference).max()),
                  initial_hotspot_difference_m=float(initial_difference[60279]),
                  final_max_difference_m=float(abs(difference).max()), final_hotspot_difference_m=float(difference[60279]))
    if effect != report["comparisons"]["initial_state_effect_at_same_1.25s"]:
        raise ValueError("causal published initial state effect mismatch")
    for name, expected in inputs["code_sha256"].items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("causal frozen code changed")
    for path, expected in zip(paths, (inputs_sha256, report_sha256)):
        if file_sha256(path) != expected:
            raise ValueError("causal input changed during audit")
    return dict(schema="td-independent-weather-causality-v1", input_path=str(paths[0]), inputs_sha256=inputs_sha256,
                report_path=str(paths[1]), report_sha256=report_sha256, case_audits=audits, comparisons=comparisons,
                initial_state_effect=effect, accepted=True, solver_advanced=False, hydraulic_ready=False, publishable=False,
                limitations="One dry hour from pinned TD states; inherited initial-state differences demonstrated; does not certify a replacement forcing model.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--report-sha256", required=True)
    arguments = parser.parse_args()
    result = audit(arguments.directory, arguments.inputs_sha256, arguments.report_sha256)
    destination = ROOT / "verification/td-basin-generation" / ("independent-weather-causality-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    result["auditor_sha256"] = file_sha256(__file__)
    publish_bytes(destination, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(destination), sha256=file_sha256(destination), accepted=True)))
