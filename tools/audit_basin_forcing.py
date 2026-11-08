"""M4 tools.audit_basin_forcing; merged source labels precede preserved implementations."""
from __future__ import annotations

import sys as _m4_tail_sys
from pathlib import Path as _m4_tail_Path
_m4_tail_sys.path.insert(0,str(_m4_tail_Path(__file__).resolve().parents[1]))

from datetime import datetime as _m4_audit_td_forcing_v10_reference_datetime
from datetime import timezone as _m4_audit_td_forcing_v10_reference_timezone
from pathlib import Path as _m4_audit_td_forcing_v10_reference_Path
from terrain_pipeline.common_infra import file_sha256 as _m4_audit_td_forcing_v10_reference_file_sha256
import argparse as _m4_audit_td_forcing_v10_reference_argparse
import json as _m4_audit_td_forcing_v10_reference_json
import math as _m4_audit_td_forcing_v10_reference_math
import numpy as _m4_audit_td_forcing_v10_reference_np
import sys as _m4_audit_td_forcing_v10_reference_sys

# --- tools/audit_td_forcing_v10_reference.py:12 ---
forcing_profile_10_reference_ROOT = _m4_audit_td_forcing_v10_reference_Path(__file__).resolve().parents[1]

# --- tools/audit_td_forcing_v10_reference.py:13 ---
_m4_audit_td_forcing_v10_reference_sys.path.insert(0, str(forcing_profile_10_reference_ROOT))

# --- tools/audit_td_forcing_v10_reference.py:18 ---
def forcing_profile_10_reference_reservoir_after(initial_mm, rate_mm_h, seconds, tau_s):
    equilibrium = rate_mm_h * tau_s / 3600.
    return equilibrium + (initial_mm - equilibrium) * _m4_audit_td_forcing_v10_reference_math.exp(-seconds / tau_s)

# --- tools/audit_td_forcing_v10_reference.py:23 ---
def forcing_profile_10_reference_assert_accounts(initial, result):
    states = result["states"]
    ledger = result["ledger_mm"]
    if not _m4_audit_td_forcing_v10_reference_np.isfinite(states).all() or _m4_audit_td_forcing_v10_reference_np.any(states < 0) or _m4_audit_td_forcing_v10_reference_np.any(ledger < 0):
        raise ValueError("reference audit found nonfinite/negative inventory or gross flux")
    _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(ledger[0], ledger[1] + ledger[3], rtol=0, atol=1e-9)
    _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(states[1] - initial[1], ledger[1] + ledger[2] - ledger[4] - ledger[7], rtol=0, atol=1e-9)
    _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(states[2:].sum(axis=0) - initial[2:].sum(axis=0), ledger[3] + ledger[7] - ledger[6], rtol=0, atol=1e-9)
    _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose((states[0] - initial[0]) * 1000, ledger[6] - ledger[2] - ledger[5], rtol=0, atol=1e-9)

# --- tools/audit_td_forcing_v10_reference.py:34 ---
def forcing_profile_10_reference_audit_reference():
    from terrain_pipeline.basin_storage import FORCING_V10_PROFILE as PROFILE
    from terrain_pipeline.basin_storage import simulate_forcing as simulate_forcing

    rows = []
    for step in (2.5, 1.25, .625):
        initial = _m4_audit_td_forcing_v10_reference_np.array([[0.], [30.], [4.], [0.]])
        runoff = _m4_audit_td_forcing_v10_reference_np.array([15., 150., 0., 0., 3600., 259200.])
        result = simulate_forcing(initial, _m4_audit_td_forcing_v10_reference_np.array([30.]), substep_s=step, runoff=runoff, evaporation_mm_h=0.)
        expected_fast = forcing_profile_10_reference_reservoir_after(4., 15., 3600., 3600.)
        expected = _m4_audit_td_forcing_v10_reference_np.array([[(4. + 15. - expected_fast) / 1000], [45.], [expected_fast], [0.]])
        _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        forcing_profile_10_reference_assert_accounts(initial, result)
        rows.append(dict(case="constant_excess_exact_reservoir", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

        initial = _m4_audit_td_forcing_v10_reference_np.array([[.005], [30.], [0.], [0.]])
        result = simulate_forcing(initial, _m4_audit_td_forcing_v10_reference_np.zeros(1), substep_s=step, runoff=runoff, evaporation_mm_h=0.)
        expected = _m4_audit_td_forcing_v10_reference_np.array([[0.], [35.], [0.], [0.]])
        _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["ledger_mm"][2], [5.], rtol=0, atol=1e-9)
        forcing_profile_10_reference_assert_accounts(initial, result)
        rows.append(dict(case="surface_inventory_exhaustion", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

        initial = _m4_audit_td_forcing_v10_reference_np.array([[0.], [130.], [4.], [0.]])
        result = simulate_forcing(initial, _m4_audit_td_forcing_v10_reference_np.array([30.]), duration_s=7200., substep_s=step,
                                  runoff=runoff, evaporation_mm_h=0.)
        at_saturation = forcing_profile_10_reference_reservoir_after(4., 15., 4800., 3600.)
        expected_fast = forcing_profile_10_reference_reservoir_after(at_saturation, 30., 2400., 3600.)
        expected = _m4_audit_td_forcing_v10_reference_np.array([[(4. + 40. - expected_fast) / 1000], [150.], [expected_fast], [0.]])
        _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["ledger_mm"][[1, 3], 0], [20., 40.], rtol=0, atol=1e-9)
        forcing_profile_10_reference_assert_accounts(initial, result)
        rows.append(dict(case="aligned_soil_saturation_piecewise_exact", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

        initial = _m4_audit_td_forcing_v10_reference_np.array([[0.], [30.], [0.], [3.]])
        runoff = _m4_audit_td_forcing_v10_reference_np.array([0., 150., .15, 1., 3600., 259200.])
        result = simulate_forcing(initial, _m4_audit_td_forcing_v10_reference_np.zeros(1), substep_s=step, runoff=runoff, evaporation_mm_h=0.)
        expected_slow = forcing_profile_10_reference_reservoir_after(3., 1., 3600., 259200.)
        expected = _m4_audit_td_forcing_v10_reference_np.array([[(4. - expected_slow) / 1000], [28.85], [0.], [expected_slow]])
        _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["states"], expected, rtol=0, atol=1e-9)
        forcing_profile_10_reference_assert_accounts(initial, result)
        rows.append(dict(case="percolation_exact_slow_reservoir", step_s=step,
                         max_state_error=float(abs(result["states"] - expected).max())))

    initial = _m4_audit_td_forcing_v10_reference_np.zeros((4, 4))
    initial[0] = [0., .99e-9, 1.01e-9, 1e-6]
    initial[1] = 30.
    result = simulate_forcing(initial, _m4_audit_td_forcing_v10_reference_np.full(4, 2.288880014936935))
    forcing_profile_10_reference_assert_accounts(initial, result)
    difference = result["states"][:, 2] - result["states"][:, 1]
    weighted = abs(difference[0] * 1000) + abs(difference[1:]).sum()
    if weighted > 1e-7:
        raise ValueError("wet threshold discontinuity remains in forcing")
    rows.append(dict(case="former_wet_threshold_continuity", inventory_difference_mm=float(weighted)))

    tiny_depths = _m4_audit_td_forcing_v10_reference_np.array([1e-30, 1e-20, 1e-12, .00000123456789, .00123456789])
    initial = _m4_audit_td_forcing_v10_reference_np.zeros((4, len(tiny_depths)))
    initial[0] = tiny_depths
    initial[1] = 30.
    result = simulate_forcing(initial, _m4_audit_td_forcing_v10_reference_np.zeros(len(tiny_depths)),
                              runoff=_m4_audit_td_forcing_v10_reference_np.array([15., 150., 0., 0., 3600., 259200.]), evaporation_mm_h=0.)
    forcing_profile_10_reference_assert_accounts(initial, result)
    _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["states"][0], 0., rtol=0, atol=1e-25)
    _m4_audit_td_forcing_v10_reference_np.testing.assert_allclose(result["states"][1], 30. + tiny_depths * 1000, rtol=0, atol=1e-9)
    rows.append(dict(case="mixed_scale_exhaustion", cells=len(tiny_depths)))
    return dict(schema="td-v10-independent-forcing-reference-v1", profile=PROFILE,
                cases=rows, accepted=True, solver_scope="forcing only; no transport or full domain certification",
                reference="closed-form constant-input linear reservoirs, aligned saturation and inventory limits",
                hydraulic_ready=False, publishable=False)

# --- tools/audit_td_forcing_v10_reference.py:108 ---
def forcing_profile_10_reference_write_report(report):
    from terrain_pipeline.common_infra import file_sha256 as _m4_audit_td_forcing_v10_reference_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _m4_audit_td_forcing_v10_reference_publish_bytes
    output = forcing_profile_10_reference_ROOT / "verification/td-basin-generation" / ("independent-forcing-v10-" +
              _m4_audit_td_forcing_v10_reference_datetime.now(_m4_audit_td_forcing_v10_reference_timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    dependencies = ('terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
                    'tools/audit_basin_forcing.py')
    report["code_sha256"] = {name: _m4_audit_td_forcing_v10_reference_file_sha256(forcing_profile_10_reference_ROOT / name) for name in dependencies}
    _m4_audit_td_forcing_v10_reference_publish_bytes(output, _m4_audit_td_forcing_v10_reference_json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return output

def run_forcing_profile_10_reference_cli():
    _m4_audit_td_forcing_v10_reference_argparse.ArgumentParser(description=__doc__).parse_args()
    destination = forcing_profile_10_reference_write_report(forcing_profile_10_reference_audit_reference())
    print(_m4_audit_td_forcing_v10_reference_json.dumps(dict(path=str(destination), sha256=_m4_audit_td_forcing_v10_reference_file_sha256(destination), accepted=True)))

PROFILES = {
    'forcing_profile_10_reference': run_forcing_profile_10_reference_cli,
}

def main(argv=None):
    """Select a preserved M4 validator; remaining options go to that validator."""
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',choices=tuple(PROFILES),default=next(iter(PROFILES)))
    selected,remaining=parser.parse_known_args(argv)
    previous=_m4_tail_sys.argv
    try:
        _m4_tail_sys.argv=[previous[0],*remaining]
        return PROFILES[selected.profile]()
    finally:
        _m4_tail_sys.argv=previous

if __name__ == '__main__':
    main()
