"""Compare the new forcing hypothesis with independent closed-form inventories."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes


def reservoir_after(initial_mm, rate_mm_h, seconds, tau_s):
    equilibrium = rate_mm_h * tau_s / 3600.
    return equilibrium + (initial_mm - equilibrium) * math.exp(-seconds / tau_s)


def assert_accounts(initial, result):
    states = result["states"]
    ledger = result["ledger_mm"]
    if not np.isfinite(states).all() or np.any(states < 0) or np.any(ledger < 0):
        raise ValueError("reference audit found nonfinite/negative inventory or gross flux")
    np.testing.assert_allclose(ledger[0], ledger[1] + ledger[3], rtol=0, atol=1e-9)
    np.testing.assert_allclose(states[1] - initial[1], ledger[1] + ledger[2] - ledger[4] - ledger[7], rtol=0, atol=1e-9)
    np.testing.assert_allclose(states[2:].sum(axis=0) - initial[2:].sum(axis=0), ledger[3] + ledger[7] - ledger[6], rtol=0, atol=1e-9)
    np.testing.assert_allclose((states[0] - initial[0]) * 1000, ledger[6] - ledger[2] - ledger[5], rtol=0, atol=1e-9)


def audit_reference():
    from terrain_pipeline.basin_storage import FORCING_V10_PROFILE as PROFILE
    from terrain_pipeline.basin_storage import simulate_forcing as simulate_forcing

    rows = []
    for step in (2.5, 1.25, .625):
        initial = np.array([[0.], [30.], [4.], [0.]])
        runoff = np.array([15., 150., 0., 0., 3600., 259200.])
        result = simulate_forcing(initial, np.array([30.]), substep_s=step, runoff=runoff, evaporation_mm_h=0.)
        expected_fast = reservoir_after(4., 15., 3600., 3600.)
        expected = np.array([[(4. + 15. - expected_fast) / 1000], [45.], [expected_fast], [0.]])
        np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        assert_accounts(initial, result)
        rows.append(dict(case="constant_excess_exact_reservoir", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

        initial = np.array([[.005], [30.], [0.], [0.]])
        result = simulate_forcing(initial, np.zeros(1), substep_s=step, runoff=runoff, evaporation_mm_h=0.)
        expected = np.array([[0.], [35.], [0.], [0.]])
        np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        np.testing.assert_allclose(result["ledger_mm"][2], [5.], rtol=0, atol=1e-9)
        assert_accounts(initial, result)
        rows.append(dict(case="surface_inventory_exhaustion", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

        initial = np.array([[0.], [130.], [4.], [0.]])
        result = simulate_forcing(initial, np.array([30.]), duration_s=7200., substep_s=step,
                                  runoff=runoff, evaporation_mm_h=0.)
        at_saturation = reservoir_after(4., 15., 4800., 3600.)
        expected_fast = reservoir_after(at_saturation, 30., 2400., 3600.)
        expected = np.array([[(4. + 40. - expected_fast) / 1000], [150.], [expected_fast], [0.]])
        np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        np.testing.assert_allclose(result["ledger_mm"][[1, 3], 0], [20., 40.], rtol=0, atol=1e-9)
        assert_accounts(initial, result)
        rows.append(dict(case="aligned_soil_saturation_piecewise_exact", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

        initial = np.array([[0.], [30.], [0.], [3.]])
        runoff = np.array([0., 150., .15, 1., 3600., 259200.])
        result = simulate_forcing(initial, np.zeros(1), substep_s=step, runoff=runoff, evaporation_mm_h=0.)
        expected_slow = reservoir_after(3., 1., 3600., 259200.)
        expected = np.array([[(4. - expected_slow) / 1000], [28.85], [0.], [expected_slow]])
        np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        assert_accounts(initial, result)
        rows.append(dict(case="percolation_exact_slow_reservoir", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

    initial = np.zeros((4, 4))
    initial[0] = [0., .99e-9, 1.01e-9, 1e-6]
    initial[1] = 30.
    result = simulate_forcing(initial, np.full(4, 2.288880014936935))
    assert_accounts(initial, result)
    difference = result["states"][:, 2] - result["states"][:, 1]
    weighted = abs(difference[0] * 1000) + abs(difference[1:]).sum()
    if weighted > 1e-7:
        raise ValueError("wet threshold discontinuity remains in forcing")
    rows.append(dict(case="former_wet_threshold_continuity", inventory_difference_mm=float(weighted)))

    tiny_depths = np.array([1e-30, 1e-20, 1e-12, .00000123456789, .00123456789])
    initial = np.zeros((4, len(tiny_depths)))
    initial[0] = tiny_depths
    initial[1] = 30.
    result = simulate_forcing(initial, np.zeros(len(tiny_depths)),
                              runoff=np.array([15., 150., 0., 0., 3600., 259200.]), evaporation_mm_h=0.)
    assert_accounts(initial, result)
    np.testing.assert_allclose(result["states"][0], 0., rtol=0, atol=1e-25)
    np.testing.assert_allclose(result["states"][1], 30. + tiny_depths * 1000, rtol=0, atol=1e-9)
    rows.append(dict(case="mixed_scale_exhaustion", cells=len(tiny_depths)))
    return dict(schema="td-v10-independent-forcing-reference-v1", profile=PROFILE,
                cases=rows, accepted=True, solver_scope="forcing only; no transport or full domain certification",
                reference="closed-form constant-input linear reservoirs, aligned saturation and inventory limits",
                hydraulic_ready=False, publishable=False)


def write_report(report):
    output = ROOT / "verification/td-basin-generation" / ("independent-forcing-v10-" +
              datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    dependencies = ("terrain_pipeline/td_basin_forcing_v10.py", "terrain_pipeline/td_basin_storage_compiled.py",
                    "tools/audit_td_forcing_v10_reference.py")
    report["code_sha256"] = {name: file_sha256(ROOT / name) for name in dependencies}
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return output


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    destination = write_report(audit_reference())
    print(json.dumps(dict(path=str(destination), sha256=file_sha256(destination), accepted=True)))
