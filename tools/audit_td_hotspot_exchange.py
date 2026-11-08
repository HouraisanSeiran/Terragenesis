"""Controlled unforced multi-face ODE comparison on a pinned TD hotspot window."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import exchange_threshold_pair as exchange
from terrain_pipeline.basin_storage import parameters_threshold_pair as parameters
from tools.audit_td_candidate_coupling import read_record


def audit(input_path, input_sha256, rain_mm_h=0.0):
    if not np.isfinite(rain_mm_h) or not 0 <= rain_mm_h <= 180:
        raise ValueError("invalid probe rain forcing")
    if file_sha256(input_path) != input_sha256:
        raise ValueError("external refinement index SHA mismatch")
    inputs = json.loads(Path(input_path).read_text(encoding="utf-8"))
    arrays, metadata = read_record(inputs["cases"]["strong"]["fine"])
    row, column, radius, frame = 125, 59, 2, 9
    rows, columns = arrays["height_m"].shape
    selected = np.arange(rows * columns).reshape(rows, columns)[row-radius:row+radius+1, column-radius:column+radius+1]
    if not arrays["valid_mask"].ravel()[selected].all():
        raise ValueError("probe includes unknown cells")
    bed = arrays["height_m"].ravel()[selected].ravel()
    initial = arrays["depth_m"][frame, selected].ravel()
    grid = np.arange(selected.size).reshape(selected.shape)
    faces = np.vstack((np.column_stack((grid[:, :-1].ravel(), grid[:, 1:].ravel())),
                       np.column_stack((grid[:-1].ravel(), grid[1:].ravel())))).astype(np.int64)
    first, second = faces[:, 0], faces[:, 1]
    sill = np.maximum(bed[first], bed[second])
    spacing = metadata["spacing_m"]
    rate = .6 / spacing
    duration = 3600.0
    source_rate = rain_mm_h / 1000 / 3600

    def derivative(time, depth):
        head = bed + depth
        positive = head[first] >= head[second]
        difference = np.where(positive, head[first] - np.maximum(sill, head[second]),
                              head[second] - np.maximum(sill, head[first]))
        signed_rate = rate * np.maximum(difference, 0) * np.where(positive, 1., -1.)
        return source_rate + np.bincount(second, weights=signed_rate, minlength=len(bed)) - np.bincount(first, weights=signed_rate, minlength=len(bed))

    reference = solve_ivp(derivative, (0, duration), initial, method="DOP853", rtol=1e-11, atol=1e-12)
    tighter = solve_ivp(derivative, (0, duration), initial, method="DOP853", rtol=1e-12, atol=1e-13)
    if not reference.success or not tighter.success:
        raise ValueError("continuous reference failed")
    reference_difference = float(abs(reference.y[:, -1] - tighter.y[:, -1]).max())
    if reference_difference > 1e-8:
        raise ValueError("continuous reference tolerance check failed")
    cases = []
    for substep, forcing_scheme in ((step, scheme) for scheme in ("pre_exchange", "symmetric") for step in (5., 2.5, 1.25, .625)):
        depth = initial.copy()
        forward = np.zeros(len(faces))
        reverse = np.zeros(len(faces))
        for step in range(round(duration / substep)):
            depth += source_rate * substep * (1 if forcing_scheme == "pre_exchange" else .5)
            depth, step_forward, step_reverse, exported, active_forward, active_reverse = exchange(
                depth, bed, faces, np.array([], np.int64), np.array([], float), spacing, substep, parameters(None), grid.shape[1])
            forward += step_forward
            reverse += step_reverse
            if forcing_scheme == "symmetric":
                depth += source_rate * substep * .5
        net = forward - reverse
        divergence = np.bincount(second, weights=net, minlength=len(bed)) - np.bincount(first, weights=net, minlength=len(bed))
        total_source_depth = duration * source_rate
        mass_error = float(abs(depth.sum() - initial.sum() - len(depth) * total_source_depth) * spacing ** 2)
        divergence_error = float(abs((depth - initial - total_source_depth) * spacing ** 2 - divergence).max())
        error = abs(depth - tighter.y[:, -1])
        if depth.min() < -1e-10 or mass_error > 1e-6 or divergence_error > 1e-6:
            raise ValueError("matching probe positivity or ledger failure")
        cases.append({"substep_s": substep, "forcing_scheme": forcing_scheme, "max_final_depth_error_m": float(error.max()),
                      "hotspot_final_depth_error_m": float(error[len(bed) // 2]), "final_depth_m": depth.tolist(),
                      "mass_error_m3": mass_error, "divergence_error_m3": divergence_error,
                      "error_against_continuous_under_1mm": bool(error.max() <= .001)})
    return {"schema": "td-hotspot-unforced-multiface-ode-v1", "utc": datetime.now(timezone.utc).isoformat(),
            "input": {"path": str(input_path), "expected_sha256": input_sha256},
            "storage_pin": inputs["cases"]["strong"]["fine"], "native_cell_ids": selected.tolist(),
            "native_origin_m_xz": metadata["origin_m_xz"], "spacing_m": spacing,
            "initial_frame": frame, "initial_time_s": frame * metadata["dt_s"], "probe_duration_s": duration,
            "bed_m": bed.tolist(), "initial_depth_m": initial.tolist(), "reference_final_depth_m": tighter.y[:, -1].tolist(),
            "reference_tolerance_difference_m": reference_difference, "cases": cases,
            "closed_probe_boundary": True, "forcing_disabled": rain_mm_h == 0, "direct_source_mm_h": rain_mm_h,
            "continuous_reference": "DOP853 threshold multi-face ODE plus constant direct surface source",
            "hydraulic_ready": False, "full_domain_certification": False,
            "solver_sha256": file_sha256(ROOT / 'terrain_pipeline/basin_storage.py'), "auditor_sha256": file_sha256(__file__),
            "limitations": "Actual terrain/initial water; artificial closed 5x5 boundary. Optional constant direct surface source excludes soil/runoff/ET. Controlled forcing split probe; not a full-domain replay or proof of the original failure cause."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--direct-source-mm-h", type=float, default=0.0)
    arguments = parser.parse_args()
    report = audit(arguments.inputs, arguments.inputs_sha256, arguments.direct_source_mm_h)
    publish_bytes(arguments.output, json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode())
    print(json.dumps({"cases": [{key: case[key] for key in ("substep_s", "forcing_scheme", "max_final_depth_error_m", "mass_error_m3")} for case in report["cases"]],
                      "reference_tolerance_difference_m": report["reference_tolerance_difference_m"]}))
