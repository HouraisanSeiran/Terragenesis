"""Compare D4 pair splitting against independent matrix/continuous ODE solutions."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import exchange_strang_two_sweep as exchange
from terrain_pipeline.basin_storage import parameters_strang_split as parameters


def audit_numerics():
    shape = (2, 3)
    spacing = 30.0
    faces = np.array([[0, 1], [1, 2], [3, 4], [4, 5], [0, 3], [1, 4], [2, 5]], dtype=np.int64)
    config = parameters({"surface_evaporation_mm_h": 0})
    rate = config["face_conductance_m_s"] / spacing
    matrix = np.zeros((6, 6))
    for first, second in faces:
        matrix[first, first] -= rate
        matrix[second, second] -= rate
        matrix[first, second] += rate
        matrix[second, first] += rate
    results = []
    for name, bed, initial in (
        ("flat_heat_equation", np.zeros(6), np.array([3., .2, .1, .4, 1., .05])),
        ("threshold_events", np.array([0., 1., .4, 1.8, .1, 1.2]), np.array([3., .0, .05, .0, 2.4, .1])),
    ):
        def derivative(seconds, depth):
            change = np.zeros(6)
            head = bed + depth
            for first, second in faces:
                sill = max(bed[first], bed[second])
                if head[first] > head[second]:
                    flow = rate * max(head[first] - max(sill, head[second]), 0)
                else:
                    flow = -rate * max(head[second] - max(sill, head[first]), 0)
                change[first] -= flow
                change[second] += flow
            return change
        reference = solve_ivp(derivative, (0., 120.), initial, method="DOP853", rtol=1e-12, atol=1e-13, max_step=.25)
        if not reference.success:
            raise ValueError("independent ODE reference failed")
        exact = reference.y[:, -1]
        matrix_difference = None
        if name == "flat_heat_equation":
            matrix_exact = expm(matrix * 120.) @ initial
            matrix_difference = float(np.max(abs(matrix_exact - exact)))
            if matrix_difference > 1e-10:
                raise ValueError("independent references disagree")
            exact = matrix_exact
        errors = []
        for time_step in (12., 6., 3., 1.5):
            depth = initial.copy()
            accumulated_forward = np.zeros(len(faces))
            accumulated_reverse = np.zeros(len(faces))
            for count in range(int(120 / time_step)):
                depth, forward, reverse, exported, forward_duration, reverse_duration = exchange(
                    depth, bed, faces, np.array([], np.int64), np.array([]), spacing, time_step, config, shape[1])
                accumulated_forward += forward
                accumulated_reverse += reverse
                if np.any(depth < 0) or abs(depth.sum() - initial.sum()) > 1e-12:
                    raise ValueError("pair splitting violated positivity/conservation")
                if np.any(forward_duration + reverse_duration > time_step + 1e-12):
                    raise ValueError("pair splitting duplicated physical activity time")
            divergence = np.zeros(6)
            for face, volume in zip(faces, accumulated_forward - accumulated_reverse):
                divergence[face[0]] -= volume
                divergence[face[1]] += volume
            if np.max(abs(divergence - (depth - initial) * spacing ** 2)) > 1e-8:
                raise ValueError("integrated pair flux does not match cell inventory")
            errors.append({"substep_s": time_step, "max_depth_error_m": float(np.max(abs(depth - exact)))})
        if not all(finer["max_depth_error_m"] < coarse["max_depth_error_m"] for coarse, finer in zip(errors, errors[1:])):
            raise ValueError("face refinement did not converge to independent ODE")
        if errors[-1]["max_depth_error_m"] > .001:
            raise ValueError("fine face solution misses 1mm reference gate")
        results.append({"case": name, "reference": "DOP853 threshold ODE, 1e-12 tolerance, <=0.25s" if matrix_difference is None else "matrix exponential and independently integrated ODE",
                        "reference_cross_difference_m": matrix_difference, "comparisons": errors})
    return {"schema": "td-face-independent-numerical-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
            "cases": results, "auditor_sha256": file_sha256(__file__),
            "solver_sha256": file_sha256(ROOT / 'terrain_pipeline/basin_storage.py'),
            "scope": "unforced six-cell exchange; not rainfall, TD full-domain or momentum equation certification"}


def audit_compiled_pairs():
    from terrain_pipeline.basin_storage import refinement_compiled_exchange as _compiled_exchange

    generator = np.random.default_rng(20261002)
    maximum_error = 0.0
    exact_duration_cases = 0
    duration_difference_cases = 0
    for case in range(80):
        rows, columns = (2 + case % 4, 3 + case % 5)
        ids = np.arange(rows * columns).reshape(rows, columns)
        faces = np.vstack((np.column_stack((ids[:, :-1].ravel(), ids[:, 1:].ravel())),
                           np.column_stack((ids[:-1].ravel(), ids[1:].ravel()))))
        known = generator.random(rows * columns) > .15
        faces = faces[known[faces[:, 0]] & known[faces[:, 1]]]
        bed = generator.integers(0, 5, rows * columns).astype(float) + 1400.
        depth = generator.uniform(0, 5, rows * columns)
        depth[~known] = 0
        first, second = faces[:, 0], faces[:, 1]
        horizontal = first // columns == second // columns
        groups = np.where(horizontal, first % columns % 2, 2 + first // columns % 2)
        prepared = tuple(np.flatnonzero(groups == group) for group in range(4))
        ordered = np.concatenate(prepared)
        offsets = np.concatenate(([0], np.cumsum([len(group) for group in prepared])))
        perimeter = np.zeros((rows, columns), bool)
        perimeter[[0, -1]] = True
        perimeter[:, [0, -1]] = True
        boundary = np.flatnonzero(perimeter.ravel() & known)
        widths = np.full(len(boundary), 30.)
        config = parameters({"surface_evaporation_mm_h": 0})
        dt_s = (60., 5., 2.5, 1.25)[case % 4]
        expected = exchange(depth, bed, faces, boundary, widths, 30., dt_s, config, columns, prepared)
        actual = _compiled_exchange(depth, bed, faces, boundary, widths, 30., dt_s, .6, ordered, offsets)
        for actual_array, expected_array in zip(actual[:4], expected[:4]):
            error = float(np.max(abs(actual_array - expected_array))) if actual_array.size else 0.
            maximum_error = max(maximum_error, error)
            if not np.allclose(actual_array, expected_array, rtol=1e-11, atol=1e-10):
                raise ValueError("compiled threshold kernel differs from frozen numpy law")
        if all(np.array_equal(actual_array, expected_array) for actual_array, expected_array in zip(actual[4:], expected[4:])):
            exact_duration_cases += 1
        else:
            duration_difference_cases += 1
        if np.any(actual[0] < 0) or abs(actual[0].sum() * 900 + actual[3].sum() - depth.sum() * 900) > 1e-8:
            raise ValueError("compiled exchange violates whole water account")
    return {"cases": 80, "random_seed": 20261002, "maximum_state_or_volume_difference": maximum_error,
            "exact_activity_cases": exact_duration_cases, "activity_roundoff_difference_cases": duration_difference_cases,
            "scope": "single substep known masked D4 grids and engineering drainage, not full transient TD"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compiled", action="store_true")
    args = parser.parse_args()
    report = audit_numerics()
    if args.compiled:
        report["compiled_pairs"] = audit_compiled_pairs()
        report["compiled_solver_sha256"] = file_sha256(ROOT / 'terrain_pipeline/basin_storage.py')
    publish_bytes(args.output, json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8"))
    print(json.dumps(report["cases"]))
    if args.compiled:
        print(json.dumps(report["compiled_pairs"]))


if __name__ == "__main__":
    main()
