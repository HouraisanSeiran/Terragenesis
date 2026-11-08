"""Reconstruct finite source stocks and daily delivery from saved arrays only."""
import argparse
import json
from pathlib import Path

import numpy as np


def audit(directory):
    report = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    with np.load(directory / "result.npz") as saved:
        a = {key: saved[key] for key in saved.files}
    p = report["material"]["porosity"]
    area = a["area_m2"]
    with np.load(report["source_path"]) as parent:
        for key in ("trace_bed_m", "trace_loose_solid_m3", "trace_mobile_solid_m3"):
            np.testing.assert_array_equal(a[key][0], parent[key][-1])
        np.testing.assert_array_equal(a["trace_lifetime_rock_removed_solid_m3"][0], parent["trace_rock_removed_m3"][-1])
        np.testing.assert_array_equal(a["rock_floor_m"], parent["rock_floor_m"] - report["one_time_added_rock_thickness_m"])
        parent_q = parent["water_q_m3_s"]
        parent_dt = np.diff(parent["time_seconds"])
    np.testing.assert_array_equal(a["water_q_m3_s"], parent_q[np.arange(len(a["water_q_m3_s"])) % len(parent_q)])
    np.testing.assert_allclose(np.diff(a["time_seconds"]), parent_dt[np.arange(len(a["water_q_m3_s"])) % len(parent_q)], atol=0., rtol=0.)
    loose, mobile = a["trace_loose_solid_m3"], a["trace_mobile_solid_m3"]
    removed = a["trace_added_scenario_rock_removed_solid_m3"]
    bed_reconstructed = a["trace_bed_m"][0] + (loose - loose[0]) / ((1. - p) * area) - removed / area
    np.testing.assert_allclose(a["trace_bed_m"], bed_reconstructed, atol=1.e-9, rtol=0.)
    np.testing.assert_allclose(np.diff(removed, axis=0), a["eroded_rock_m3"], atol=1.e-8, rtol=1.e-12)
    np.testing.assert_allclose(a["trace_lifetime_rock_removed_solid_m3"], removed + a["old_rock_removed_solid_m3"], atol=1.e-9, rtol=0.)
    donor_incoming = np.zeros_like(a["outgoing_solid_m3"])
    for node, target in enumerate(a["receiver"]):
        if target >= 0:
            donor_incoming[:, target] += a["outgoing_solid_m3"][:, node]
    np.testing.assert_allclose(donor_incoming, a["incoming_solid_m3"], atol=1.e-9, rtol=1.e-12)
    net = a["incoming_solid_m3"] + a["eroded_rock_m3"] - a["outgoing_solid_m3"]
    balance = np.diff(loose + mobile, axis=0) - net
    terminal_export = np.where(a["receiver"][None] == -1, a["outgoing_solid_m3"], 0.)
    np.testing.assert_allclose(terminal_export, a["exported_solid_m3"], atol=1.e-10, rtol=1.e-12)
    maximum_cell_residual = float(abs(balance).max(initial=0.))
    if maximum_cell_residual > 1.e-8:
        raise AssertionError("per-node material balance failed")
    remaining = a["initial_scenario_rock_reserve_solid_m3"][None] - removed
    if remaining.min() < -1.e-7 or (a["trace_bed_m"] - a["rock_floor_m"]).min() < -1.e-9:
        raise AssertionError("finite rock reserve exceeded")
    edge = a["receiver"] >= 0
    drops = a["trace_bed_m"][:, edge] - a["trace_bed_m"][:, a["receiver"][edge]]
    if np.any(drops <= 0.):
        raise AssertionError("accepted saved bed has flat/adverse receiver grade")
    depleted = np.flatnonzero(np.maximum(remaining, 0.).sum(axis=1) <= 1.e-6)
    cumulative_export = np.cumsum(a["exported_solid_m3"].sum(axis=1))
    nonzero_days = np.flatnonzero(a["exported_solid_m3"].sum(axis=1) > 1.e-8)
    result = {"directory": str(directory), "saved_status": report["status"],
        "parent_final_stores_carried_exactly": True, "old_rock_debit_carried_exactly": True,
        "floor_appended_once": True, "hydrology_repeats_parent_year_only": True,
        "accepted_beds_keep_positive_actual_grades": True, "minimum_receiver_bed_drop_m": float(drops.min()),
        "maximum_abs_per_node_material_residual_solid_m3": maximum_cell_residual,
        "one_time_added_rock_solid_m3": float(a["appended_rock_solid_m3"].sum()),
        "new_rock_removed_solid_m3": float(removed[-1].sum()),
        "new_exported_solid_m3": float(cumulative_export[-1]) if len(cumulative_export) else 0.,
        "remaining_rock_solid_m3": float(np.maximum(remaining[-1], 0.).sum()),
        "first_exhausted_trace_index": int(depleted[0]) if len(depleted) else None,
        "first_exhausted_absolute_time_s": float(a["time_seconds"][depleted[0]]) if len(depleted) else None,
        "last_nonzero_export_day_index": int(nonzero_days[-1]) if len(nonzero_days) else None,
        "cumulative_new_export_solid_m3": cumulative_export.tolist(),
        "scope": "independent saved-array audit, not an independent sediment-law replay or observed watershed validation; not connected to delta"}
    (directory / "independent-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return {key: value for key, value in result.items() if key != "cumulative_new_export_solid_m3"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.input), indent=2))
