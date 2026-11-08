"""Independent cold-read checks of a completed finite native continuation."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import binary_propagation

GRIDS = ("eta", "eta0", "eta_init", "depth", "stage", "uw", "ux", "uy", "qw", "qx", "qy", "sand_frac", "active_layer")


def run(directory):
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    provenance, forcing = summary["provenance"], summary["forcing"]
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    for path, expected in ((provenance["parent_result"], provenance["parent_result_sha256"]),
            (provenance["parent_checkpoint"], provenance["parent_checkpoint_sha256"]),
            (provenance["parent_summary"], provenance["parent_summary_sha256"]),
            (forcing["source"], forcing["source_sha256"]), (forcing["source_summary"], forcing["source_summary_sha256"])):
        assert digest(path) == expected, path
    root = Path(__file__).resolve().parents[1]
    assert all(digest(root / path) == expected for path, expected in summary["implementation_hashes"].items())
    with np.load(directory / "result.npz") as saved:
        a = {name: saved[name] for name in saved.files}
    with np.load(provenance["parent_result"]) as saved:
        parent = {name: saved[name] for name in saved.files}
    with np.load(provenance["parent_checkpoint"], allow_pickle=True) as saved:
        old = {name: saved[name] for name in saved.files}
    with np.load(directory / "backend/checkpoint.npz", allow_pickle=True) as saved:
        final = {name: saved[name] for name in saved.files}
    assert all(np.isfinite(field).all() for field in a.values())
    assert all(np.isfinite(old[name]).all() and np.isfinite(final[name]).all() for name in GRIDS)
    mapping = {"eta": "bed_m", "depth": "depth_m", "stage": "stage_m", "qx": "qx_m2_s", "qy": "qz_m2_s",
        "sand_frac": "sand_fraction", "active_layer": "active_layer"}
    for native, name in mapping.items():
        np.testing.assert_array_equal(a[name][0], old[native])
        np.testing.assert_array_equal(a[name][-1], final[native])
        if name in parent:
            np.testing.assert_array_equal(a[name][0], parent[name][-1])
    for name in ("source_floor_m", "initial_erodible_solid_m3", "cell_type", "initial_bed_m", "local_world_xz_m"):
        np.testing.assert_array_equal(a[name], parent[name])
    np.testing.assert_array_equal(a["continuation_initial_bed_m"], parent["bed_m"][-1])
    assert int(final["time_iter"]) - int(old["time_iter"]) == summary["steps"] == 341
    np.testing.assert_allclose([old["time"], final["time"]], a["time_s"][[0, -1]], atol=0., rtol=0.)
    floor_margin = a["bed_m"].astype(float) - a["source_floor_m"]
    assert floor_margin.min() >= -2.e-6
    area = summary["config"]["dx_m"] ** 2
    packing = 1. - summary["config"]["porosity"]
    measured = np.diff(a["bed_m"].astype(float), axis=0).sum(axis=(1, 2)) * area
    predicted = np.zeros(summary["steps"])
    totals = {name: 0. for name in summary["ledger_bulk_m3"] if name != "bed_change_bulk_m3"}
    for row in summary["phase_records"]:
        index = row["step_index"] - int(old["time_iter"])
        predicted[index] += row["injected_bulk_m3"] - row["exported_bulk_m3"] - row["lost_bulk_m3"] + row["inlet_correction_bulk_m3"] + row["raw_residual_bulk_m3"]
        for name in totals:
            totals[name] += row[name]
    np.testing.assert_allclose(measured, predicted, atol=1.e-7, rtol=0.)
    for name, total in totals.items():
        np.testing.assert_allclose(total, summary["ledger_bulk_m3"][name], atol=1.e-9, rtol=0.)
    with np.load(forcing["source"]) as source:
        source_total = float(source["exported_solid_m3"].sum())
    np.testing.assert_allclose(np.diff(a["cumulative_new_input_solid_m3"]), a["schedule"][:, 3], atol=1.e-8, rtol=0.)
    np.testing.assert_allclose(source_total, a["cumulative_new_input_solid_m3"][-1], atol=1.e-8, rtol=0.)
    np.testing.assert_allclose(totals["injected_bulk_m3"] * packing, source_total, atol=1.e-8, rtol=0.)
    np.testing.assert_allclose(a["cumulative_input_solid_m3"], parent["cumulative_input_solid_m3"][-1] + a["cumulative_new_input_solid_m3"], atol=1.e-9, rtol=0.)
    inherited = set(provenance["inherited_consumed_source_sha256s"])
    assert forcing["source_sha256"] not in inherited
    assert set(summary["consumed_source_sha256s"]) == inherited | {forcing["source_sha256"]}
    inventory_start = float(floor_margin[0].sum() * area * packing)
    inventory_end = float(floor_margin[-1].sum() * area * packing)
    expected_inventory_change = (totals["injected_bulk_m3"] - totals["exported_bulk_m3"] - totals["lost_bulk_m3"] + totals["inlet_correction_bulk_m3"] + totals["raw_residual_bulk_m3"]) * packing
    np.testing.assert_allclose(inventory_end - inventory_start, expected_inventory_change, atol=1.e-7, rtol=0.)
    sea = (a["initial_bed_m"] < 0.) & (a["cell_type"] == 0)
    total_change = a["bed_m"][-1].astype(float) - a["initial_bed_m"]
    boundary_evidence = {}
    for name, index in {"left": (slice(None), 0), "right": (slice(None), -1), "downstream": (-1, slice(None))}.items():
        edge_change = total_change[index]
        altered = edge_change > .01
        boundary_evidence[name] = {"edge_cells_risen_over_1cm": int(altered.sum()),
            "edge_length_risen_over_1cm_m": float(altered.sum() * summary["config"]["dx_m"]),
            "max_rise_m": float(edge_change.max()), "positive_bed_change_bulk_m3": float(np.maximum(edge_change, 0.).sum() * area)}
        if name == "left" and altered.any():
            rows = np.flatnonzero(altered)
            boundary_evidence[name]["affected_row_range"] = [int(rows[0]), int(rows[-1])]
            boundary_evidence[name]["distance_from_stub_end_range_m"] = [float(rows[0] * 5. - 60.), float(rows[-1] * 5. - 60.)]
    land = a["initial_bed_m"] >= 0.
    tail = []
    for index in range(len(a["bed_m"]) - 5, len(a["bed_m"])):
        dry = a["depth_m"][index] <= 2.e-6
        linked = binary_propagation(land & dry, mask=dry)
        tail.append({"frame": index, "actual_dry_original_sea_m2": float(np.sum(dry & sea) * area),
            "actual_dry_connected_original_sea_m2": float(np.sum(linked & sea) * area)})
    result = {"status": "passed", "steps": summary["steps"], "all_source_and_implementation_hashes_match": True,
        "checkpoint_13_grids_finite": True, "checkpoint_parent_child_snapshot_grids_exact": list(mapping),
        "initial_13_grid_and_rng_restoration_scope": "runtime checked all 13 grids/RNG before first update; cold audit independently checks seven archived initial/final state grids; remaining six initial fields and RNG are not separately saved after restoration",
        "inherited_floor_material_inventory_and_coordinates_exact": True, "minimum_floor_margin_m": float(floor_margin.min()),
        "new_source_consumed_once_by_hash_and_volume": True, "new_source_solid_m3": source_total,
        "maximum_step_phase_to_measured_bed_change_error_bulk_m3": float(abs(measured - predicted).max()),
        "net_measured_bed_change_bulk_m3": float(measured.sum()), "phase_totals_bulk_m3": totals,
        "initial_inventory_solid_m3": inventory_start, "final_inventory_solid_m3": inventory_end,
        "inventory_change_closure_solid_m3": inventory_end - inventory_start - expected_inventory_change,
        "outer_boundary_bed_evidence": boundary_evidence,
        "boundary_interpretation": "finite source floor is an erosion lower bound, not an immutable marine-edge bed; positive deposition can reach and raise the open sea edge, so final morphology has no demonstrated lateral domain convergence",
        "final_five_frames_dry_exposure": tail,
        "scope": "independent saved-state and aggregate phase-budget reconstruction; per-phase spatial beds were not archived; no independent rerun or annual/tidal permanence claim"}
    (directory / "independent-continuation-audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    print(json.dumps(run(parser.parse_args().run), indent=2))
