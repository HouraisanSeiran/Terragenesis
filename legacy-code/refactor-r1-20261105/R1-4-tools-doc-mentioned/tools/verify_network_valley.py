"""Verify network valleys without publishing unverified mountain outlets."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe, load_plan, plan_channel, save_plan
from terrain_pipeline.network_valley import (
    NetworkValleyRecipe, load_network_valley, prepare_network_valley, save_network_valley,
)
from terrain_pipeline.surface_network_prepare import (
    SurfaceNetworkBudget, load_surface_network, prepare_surface_network,
    save_surface_network, save_surface_network_diagnostic, slice_surface_network,
)
from terrain_pipeline.valley_geometry import (
    ValleyGeometryRecipe, evaluate_fine_valley_ledger, load_fine_valley_ledger,
    save_fine_valley_ledger,
)
from tests.test_channel_stage_inundation import confluence_plan

PLAN_ROOT = ROOT / "verification/metric-channel-plan/run-20260929T140629572001Z"
COAST_ROOT = ROOT / "verification/river-feasibility/extended-20260929T114427548312Z"


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def channel_recipe(plan):
    parameters = plan["identity"]["parameters"]
    return ChannelRecipe(**{name: parameters[name] for name in ChannelRecipe.__dataclass_fields__})


def outlet_domain_review():
    records = json.loads((PLAN_ROOT / "report.json").read_text(encoding="utf-8"))["samples"]
    mountains = {}
    for name in ("normal_mountain", "pressure_mountain"):
        path = PLAN_ROOT / records[name]["plan_npz"]
        plan = load_plan(path)
        arrays = plan["arrays"]
        outlets = arrays["outlet_mask"] & arrays["channel_mask"]
        boundary = np.zeros(outlets.shape, dtype=bool)
        boundary[[0, -1], :] = True
        boundary[:, [0, -1]] = True
        assert file_hash(path) == records[name]["plan_file_sha256"]
        mountains[name] = {
            "source_plan": str(path.relative_to(ROOT)),
            "source_plan_file_sha256": file_hash(path),
            "original_source": records[name]["source"],
            "original_source_file_sha256": file_hash(ROOT / records[name]["source"]),
            "source_identity_sha256": plan["identity_sha256"],
            "sea_level_elevation_m": plan["identity"]["parameters"]["sea_level_elevation_m"],
            "active_outlet_grid_zx": np.argwhere(outlets).tolist(),
            "active_outlets_on_window_boundary": int(np.count_nonzero(outlets & boundary)),
            "outlet_note": records[name]["outlet_note"],
            "legal_natural_outlet_verified": False,
            "publication_blocker": "artificial_window_outlet_and_unverified_complete_domain",
        }
        assert mountains[name]["original_source_file_sha256"] == records[name]["source_file_sha256"]
    catalog_path = COAST_ROOT / "catchments.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    closed = [entry for entry in catalog["mouths"] if entry["observed_window_closed"]]
    return {"mountains": mountains, "existing_coast_catalog": {
        "source": str(catalog_path.relative_to(ROOT)), "sha256": file_hash(catalog_path),
        "closed_catchment_count": len(closed),
        "max_closed_relief_m": max((entry["land_relief_m"] for entry in closed), default=None),
        "largest_closed_land_cells": max((entry["land_cells"] for entry in closed), default=None),
        "scope": "existing_catalog_review_not_new_scan_or_verified_mountain_domain"}}


def save_unvalidated_diagnostic(result, path):
    record = {name: result[name] for name in
              ("identity", "identity_sha256", "status", "summary")}
    record["scope"] = "unvalidated_failure_diagnostic_not_publishable"
    groups = {"geometry": result["arrays"]}
    if "network" in result:
        record["planning_identity"] = result["planning_identity"]
        record["planning_identity_sha256"] = result["planning_identity_sha256"]
        record["replanned_plan"] = {name: result["replanned_plan"][name] for name in
                                   ("identity", "identity_sha256", "status")}
        groups["network"] = result["network"]
        groups["replanned"] = result["replanned_plan"]["arrays"]
    payload = {f"{group}__{name}": values for group, arrays in groups.items()
               for name, values in arrays.items()}
    np.savez_compressed(path, manifest=json.dumps(record, sort_keys=True), **payload)


def assert_reload_equal(original, loaded, groups=("arrays",)):
    for field in ("identity", "identity_sha256", "status", "summary"):
        if field in original:
            assert original[field] == loaded[field], field
    for group in groups:
        assert set(original[group]) == set(loaded[group])
        for field, values in original[group].items():
            np.testing.assert_array_equal(loaded[group][field], values)


def save_case(name, plan, valley, destination, record):
    record.update(
        status=valley["status"], valley_identity_sha256=valley["identity_sha256"],
        planning_identity_sha256=valley["planning_identity_sha256"],
        planning_identity=valley["planning_identity"], valley_summary=valley["summary"],
        active_edge_count=len(valley["network"]["active_edges"]),
        max_required_valley_cut_m=float(valley["arrays"]["valley_cut_m"].max()),
        before_over_budget_nodes=int(plan["arrays"]["over_budget_mask"].sum()),
        after_over_budget_nodes=int(valley["replanned_plan"]["arrays"]["over_budget_mask"].sum()),
        save_reload_equal=False,
        rejection_reasons=[name for name, failed in valley["summary"]["failures"].items() if failed],
    )
    try:
        path = save_network_valley(valley, destination / f"{name}-valley.npz")
        record["valley_npz"] = path.name
        loaded = load_network_valley(path)
        assert_reload_equal(valley, loaded, ("arrays", "network"))
        for field in ("planning_identity", "planning_identity_sha256"):
            assert loaded[field] == valley[field]
        assert_reload_equal(valley["replanned_plan"], loaded["replanned_plan"])
        replanned_path = save_plan(valley["replanned_plan"], destination / f"{name}-replanned.npz")
        record["replanned_npz"] = replanned_path.name
        assert_reload_equal(valley["replanned_plan"], load_plan(replanned_path))
        record["save_reload_equal"] = True
    except Exception as error:
        record["storage_error"] = f"{type(error).__name__}: {error}"
        fallback = destination / f"{name}-unvalidated-diagnostic.npz"
        save_unvalidated_diagnostic(valley, fallback)
        record["unvalidated_diagnostic_npz"] = fallback.name
        raise


def synthetic_case(destination, report):
    base = confluence_plan()
    arrays = base["arrays"]
    height = arrays["source_height_m"].copy()
    height[3, 3] += 5.
    discharge = np.full(height.shape, .01)
    discharge.flat[[9, 11]] = .1
    discharge.flat[[17, 24, 31, 38, 45]] = .2
    donor_flow = np.zeros(height.size)
    connected = arrays["receiver"] >= 0
    np.add.at(donor_flow, arrays["receiver"][connected], discharge.ravel()[connected])
    local_runoff = discharge.ravel() - donor_flow
    total_input = float(local_runoff.sum())
    total_outflow = float(discharge[arrays["outlet_mask"]].sum())
    report["flow_conservation"] = {
        "local_runoff_m3_s": local_runoff.reshape(height.shape).tolist(),
        "min_local_runoff_m3_s": float(local_runoff.min()),
        "total_input_m3_s": total_input, "total_outlet_discharge_m3_s": total_outflow,
        "input_outlet_residual_m3_s": total_input - total_outflow,
        "confluence_node": 17, "confluence_donors": [9, 11],
        "confluence_donor_discharge_m3_s": discharge.flat[[9, 11]].tolist(),
        "confluence_discharge_m3_s": float(discharge.flat[17]),
        "confluence_residual_m3_s": float(discharge.flat[17] - donor_flow[17]),
    }
    assert np.all(local_runoff >= 0.)
    np.testing.assert_allclose(total_input, total_outflow, rtol=0., atol=1e-12)
    np.testing.assert_array_equal(np.flatnonzero(arrays["receiver"] == 17), [9, 11])
    assert discharge.flat[17] == donor_flow[17] == .2
    recipe = channel_recipe(base)
    blocked = plan_channel(height, arrays["receiver"], arrays["order"], arrays["outlet_mask"],
                           discharge, 10., 10., 0., 0., 0.,
                           "network-valley-raised-ridge", recipe)
    fixture_path = save_plan(blocked, destination / "synthetic-source-plan.npz")
    assert_reload_equal(blocked, load_plan(fixture_path))
    report["source_plan_npz"] = fixture_path.name
    domain = np.ones(height.shape, dtype=bool)
    protected = np.zeros(height.shape, dtype=bool)
    geometry_recipe = ValleyGeometryRecipe(8., 10000., 100000., 100000.)
    network_recipe = NetworkValleyRecipe(3.75, 30., 30., .00001)
    valley = prepare_network_valley(blocked, domain, protected, network_recipe, geometry_recipe, recipe)
    save_case("synthetic-confluence", blocked, valley, destination, report)
    report["network_recipe"] = asdict(network_recipe)
    report["valley_recipe"] = asdict(geometry_recipe)
    report["channel_recipe"] = asdict(recipe)
    report["negative_cases"] = {}
    for name in ("zero_valley_budget", "protected_ridge", "outside_domain"):
        case_domain, case_protected = domain.copy(), protected.copy()
        case_recipe = geometry_recipe
        if name == "zero_valley_budget":
            case_recipe = ValleyGeometryRecipe(0., 0., 0., 0.)
        elif name == "protected_ridge":
            case_protected[3, 3] = True
        else:
            case_domain[3, 3] = False
        case_report = {"accepted": False}
        report["negative_cases"][name] = case_report
        rejected = prepare_network_valley(blocked, case_domain, case_protected,
                                          network_recipe, case_recipe, recipe)
        save_case(name, blocked, rejected, destination, case_report)
        assert not rejected["summary"]["geometry_feasible"]
        assert case_report["rejection_reasons"]
        case_report["rejected"] = True
    fine_domain = np.ones((61, 61), dtype=bool)
    fine_protected = np.zeros((61, 61), dtype=bool)
    legal = np.zeros((61, 61), dtype=bool)
    legal[-1, 27:34] = True
    surface = prepare_surface_network(
        valley["replanned_plan"], 0., 0., 1., 1., (61, 61), fine_domain, fine_protected,
        legal, np.array([5.2]), SectionRecipe(), StageRecipe(max_depth_m=4., max_lift_above_nominal_m=3.),
        InundationRecipe(max_lateral_reach_m=15.), SurfaceNetworkBudget(4., 5000., 5000.))
    report.update(surface_status=surface["status"], surface_summary=surface["summary"],
                  legal_natural_outlet_verified=True,
                  fine_grid={"shape_zx": [61, 61], "spacing_m_xz": [1., 1.],
                             "outlet_stage_m": 5.2, "max_bed_cut_m": 4., "max_lateral_reach_m": 15.})
    if surface["status"] == "prepared":
        surface_path = save_surface_network(surface, destination / "synthetic-water.npz")
        loaded_surface = load_surface_network(surface_path)
    else:
        surface_path = save_surface_network_diagnostic(surface, destination / "synthetic-water-diagnostic.npz")
        loaded_surface = load_surface_network(surface_path, allow_diagnostic=True)
    report["surface_npz"] = surface_path.name
    assert_reload_equal(surface, loaded_surface)
    report["surface_reload_equal"] = True
    ledger = evaluate_fine_valley_ledger(valley, surface)
    report.update(surface_status=surface["status"], surface_summary=surface["summary"],
                  fine_ledger_status=ledger["status"], fine_ledger_summary=ledger["summary"])
    if ledger["status"] != "prepared":
        diagnostic_path = destination / "synthetic-fine-ledger-unvalidated-diagnostic.npz"
        save_unvalidated_diagnostic(ledger, diagnostic_path)
        report["fine_ledger_diagnostic_npz"] = diagnostic_path.name
        return report
    loaded_ledger = load_fine_valley_ledger(save_fine_valley_ledger(ledger, destination / "synthetic-fine-ledger.npz"))
    report["fine_ledger_npz"] = "synthetic-fine-ledger.npz"
    for original, loaded in ((surface, loaded_surface), (ledger, loaded_ledger)):
        assert original["identity_sha256"] == loaded["identity_sha256"]
        for field, values in original["arrays"].items():
            np.testing.assert_array_equal(loaded["arrays"][field], values)
    first = slice_surface_network(loaded_surface, slice(10, 41), slice(10, 41))
    second = slice_surface_network(loaded_surface, slice(20, 41), slice(20, 41))
    assert len(second["arrays"]) == 12
    assert first["origin_x_m"] + 10. == second["origin_x_m"]
    assert first["origin_z_m"] + 10. == second["origin_z_m"]
    for field, values in second["arrays"].items():
        np.testing.assert_array_equal(first["arrays"][field][10:, 10:], values)
    np.testing.assert_allclose(loaded_ledger["arrays"]["total_cut_m"],
                               loaded_ledger["arrays"]["valley_cut_m"] + loaded_ledger["arrays"]["bed_cut_m"],
                               rtol=0., atol=1e-9)
    report.update(surface_and_fine_ledger_reload_equal=True, same_grid_overlap_array_count=len(second["arrays"]))
    expected = {"valley_cut_volume_m3": 1039.264797, "bed_cut_volume_m3": 162.329385,
                "total_cut_volume_m3": 1201.594182}
    report["expected_fine_volumes_m3"] = expected
    for field, value in expected.items():
        np.testing.assert_allclose(ledger["summary"][field], value, rtol=0., atol=1e-6)
    np.testing.assert_array_equal(height, blocked["arrays"]["source_height_m"])
    report["source_height_unchanged"] = True
    report["accepted"] = (valley["summary"]["geometry_feasible"] and
                          surface["status"] == ledger["status"] == "prepared" and
                          all(case["rejected"] for case in report["negative_cases"].values()))
    return report


def mountain_cases(destination, review, results):
    for name, entry in review["mountains"].items():
        path = ROOT / entry["source_plan"]
        plan = load_plan(path)
        shape = plan["arrays"]["source_height_m"].shape
        parameters = plan["identity"]["parameters"]
        geometry_recipe = ValleyGeometryRecipe(4., 1e8, 1e9, 1e9)
        network_recipe = NetworkValleyRecipe(2., 60., 60., .0001)
        record = results[name] = {"accepted": False}
        record.update(legal_natural_outlet_verified=False,
                             water_preparation_skipped=entry["publication_blocker"],
                             diagnostic_domain_note="window_only_not_verified_hydrologic_domain",
                             valley_recipe=asdict(geometry_recipe), network_recipe=asdict(network_recipe),
                             source_shape_zx=list(shape),
                             source_spacing_m_xz=[parameters["spacing_x_m"], parameters["spacing_z_m"]],
                             sea_level_elevation_m=parameters["sea_level_elevation_m"])
        try:
            assert shape == (487, 487)
            assert parameters["spacing_x_m"] == parameters["spacing_z_m"] == 30.
            assert parameters["sea_level_elevation_m"] == 126.
            valley = prepare_network_valley(plan, np.ones(shape, dtype=bool), np.zeros(shape, dtype=bool),
                                           network_recipe, geometry_recipe, channel_recipe(plan))
            save_case(name, plan, valley, destination, record)
            assert not valley["summary"]["geometry_feasible"]
            expected_edges = {"normal_mountain": 2324, "pressure_mountain": 1605}
            expected_depth = {"normal_mountain": 54.703, "pressure_mountain": 190.742}
            expected_over_budget = {"normal_mountain": 201, "pressure_mountain": 1079}
            assert record["active_edge_count"] == expected_edges[name]
            assert record["before_over_budget_nodes"] == expected_over_budget[name]
            assert record["after_over_budget_nodes"] == 0
            np.testing.assert_allclose(record["max_required_valley_cut_m"], expected_depth[name], rtol=0., atol=.001)
            record["diagnostic_checks_passed"] = True
        except Exception as error:
            record["execution_error"] = f"{type(error).__name__}: {error}"
            record["traceback"] = traceback.format_exc()
        record["source_plan_file_sha256_after"] = file_hash(path)
        assert record["source_plan_file_sha256_after"] == entry["source_plan_file_sha256"]
    return results


def main():
    destination = ROOT / "verification/network-valley" / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    destination.mkdir(parents=True)
    report = {"purpose": "full-D8 network valley planning and shared confluence constraints",
              "scope": "engineering_trial_not_calibrated_or_full_surface_delivery",
              "synthetic": {"accepted": False}, "mountain_diagnostics": {},
              "gpu_or_game_started": False, "budgets_relaxed": False}
    report_path = destination / "report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(destination)
    try:
        review = outlet_domain_review()
        report["outlet_domain_review"] = review
        try:
            synthetic_case(destination, report["synthetic"])
        except Exception as error:
            report["synthetic"]["execution_error"] = f"{type(error).__name__}: {error}"
            report["synthetic"]["traceback"] = traceback.format_exc()
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        mountain_cases(destination, review, report["mountain_diagnostics"])
    except Exception as error:
        report["execution_error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
    finally:
        unchanged = True
        for name, entry in report.get("outlet_domain_review", {}).get("mountains", {}).items():
            for field, digest_field in (("source_plan", "source_plan_file_sha256"),
                                        ("original_source", "original_source_file_sha256")):
                after = file_hash(ROOT / entry[field])
                entry[digest_field + "_after"] = after
                unchanged = unchanged and after == entry[digest_field]
        coast = report.get("outlet_domain_review", {}).get("existing_coast_catalog")
        if coast:
            coast["sha256_after"] = file_hash(ROOT / coast["source"])
            unchanged = unchanged and coast["sha256_after"] == coast["sha256"]
        report["source_files_unchanged"] = unchanged
        report["verification_passed"] = (
            unchanged and report["synthetic"]["accepted"] and "execution_error" not in report and
            len(report["mountain_diagnostics"]) == 2 and
            all(case.get("diagnostic_checks_passed", False) for case in report["mountain_diagnostics"].values()))
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["verification_passed"]:
        raise SystemExit("Verification incomplete; report and diagnostics preserved, budgets unchanged")


if __name__ == "__main__":
    main()
