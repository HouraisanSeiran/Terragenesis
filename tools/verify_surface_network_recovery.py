"""Fixed CPU-only recovery verification with replayable success/failure bundles."""

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.artifacts.contracts import array_hash
from terrain_pipeline.surface_network_recovery import (
    RecoveryRecipe, load_surface_network_recovery, recover_surface_network,
    save_surface_network_recovery,
)
from terrain_pipeline.channel_reroute import RerouteRecipe
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from tests.test_surface_network_recovery import (
    SurfaceNetworkRecoveryTests, mountain_coast_case, recovery_case, rewrite_bundle,
)


def _write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)


def _verify_case(name, case, directory):
    result = recover_surface_network(**case)
    path = directory / (name + ".npz")
    save_surface_network_recovery(result, path)
    loaded = load_surface_network_recovery(path)
    if loaded["identity_sha256"] != result["identity_sha256"]:
        raise AssertionError("saved recovery identity changed")
    if loaded["accepted"] != result["accepted"]:
        raise AssertionError("saved recovery acceptance changed")
    record = {"status": result["status"], "accepted": result["accepted"],
        "selected_method": result["selected_method"], "identity_sha256": result["identity_sha256"],
        "summary": result["summary"], "attempts": result["attempts"],
        "bundle": str(path.resolve()), "semantic_reload_passed": True,
        "readonly_reloaded_arrays": not loaded["final_plan"]["arrays"]["source_height_m"].flags.writeable}
    _write_json(directory / (name + ".json"), record)
    return record


def _reject_case(name, case):
    try:
        recover_surface_network(**case)
    except ValueError as error:
        return {"rejected": True, "reason": str(error)}
    raise AssertionError(name + " was unexpectedly accepted as an input")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="Only run fixed artifact scenarios")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = ROOT / "verification" / "surface-network-recovery" / ("run-" + stamp)
    directory.mkdir(parents=True, exist_ok=False)
    cases = {}
    for kind in ("baseline", "valley", "reroute"):
        cases[kind] = _verify_case(kind, recovery_case(kind), directory)
        if not cases[kind]["accepted"]:
            raise AssertionError(kind + " fixed positive case failed")
    case, land, ocean = mountain_coast_case()
    cases["engineered_mountain_coast"] = _verify_case("engineered_mountain_coast", case, directory)
    evidence = {"land_mask": land, "ocean_mask": ocean,
        "coarse_legal_outlet_mask": case["plan"]["arrays"]["channel_mask"] &
                                    case["plan"]["arrays"]["outlet_mask"]}
    with (directory / "engineered_land_ocean.npz").open("xb") as stream:
        np.savez_compressed(stream, **evidence)
    mountain = cases["engineered_mountain_coast"]
    height = case["plan"]["arrays"]["source_height_m"]
    mountain["evidence"] = {"type": "engineered_two_source_network_not_real_fuxi_certification",
        "land_ocean_frozen": True, "land_ocean_file": str((directory / "engineered_land_ocean.npz").resolve()),
        "mask_sha256": {name: array_hash(value) for name, value in evidence.items()},
        "relief_m": float(height.max() - height.min()), "coarse_shape_zx": list(height.shape),
        "coarse_spacing_m": 10., "fine_spacing_m": 1., "tributary_count": 2,
        "active_outlet_grid_zx": [15, 8], "outlet_discharge_m3_s": .2,
        "bed_limit_m": 4., "valley_limit_m": 4.,
        "full_land_rainfall_catchment_closed": False,
        "inactive_receivers": "unrouted side-land cells remain inactive outlets; only two explicit sources carry Q",
        "limitation": "mild longitudinal channel grade and isolated high side mountains; not steep-gorge acceptance"}
    _write_json(directory / "engineered_mountain_evidence.json", mountain["evidence"])
    for name in ("budget", "protection", "domain", "search_exhaustion", "fine_work_exhaustion", "ledger_budget"):
        case = recovery_case("reroute" if name in ("protection", "search_exhaustion") else
                             "valley" if name in ("fine_work_exhaustion", "ledger_budget") else "baseline")
        if name == "budget":
            case["budget"] = SurfaceNetworkBudget(4., 0., 0.)
        if name == "protection":
            case["recovery_recipe"] = RecoveryRecipe(max_attempts=2)
        if name == "domain":
            domain = case["fine"].domain_mask.copy()
            domain[30, 30] = False
            case["fine"] = replace(case["fine"], domain_mask=domain)
            case["coarse_domain"][3, 3] = False
            case["recovery_recipe"] = RecoveryRecipe(max_attempts=2)
        if name == "search_exhaustion":
            case["reroute_recipe"] = RerouteRecipe(max_expansions=1)
        if name == "fine_work_exhaustion":
            case["recovery_recipe"] = RecoveryRecipe(max_total_fine_cells=61 * 61)
        if name == "ledger_budget":
            case["valley_recipe"] = replace(case["valley_recipe"], max_total_cut_volume_m3=0.)
            case["recovery_recipe"] = RecoveryRecipe(max_attempts=2)
        cases[name] = _verify_case(name, case, directory)
        if cases[name]["accepted"]:
            raise AssertionError(name + " negative case unexpectedly passed")
    early_rejections = {}
    case = recovery_case()
    case["plan"]["arrays"]["discharge_m3_s"] = case["plan"]["arrays"]["discharge_m3_s"].copy()
    case["plan"]["arrays"]["discharge_m3_s"][2, 3] = .1
    early_rejections["changed_q"] = _reject_case("changed_q", case)
    case = recovery_case()
    legal = case["fine"].legal_outlet_mask.copy()
    legal[60, 30] = False
    case["fine"] = replace(case["fine"], legal_outlet_mask=legal)
    early_rejections["wrong_legal_outlet"] = _reject_case("wrong_legal_outlet", case)
    forged = directory / "forged_rehashed_summary.npz"
    save_surface_network_recovery(recover_surface_network(**recovery_case("valley")), forged)
    rewrite_bundle(forged, lambda manifest, arrays: manifest["tree"]["attempts"][0].update(accepted=True))
    try:
        load_surface_network_recovery(forged)
    except ValueError as error:
        early_rejections["rehashed_summary_load"] = {"rejected": True, "reason": str(error), "bundle": str(forged)}
    else:
        raise AssertionError("forged rehashed summary loaded")
    test_record = {"run": not args.skip_tests}
    if not args.skip_tests:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceNetworkRecoveryTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        test_record.update(count=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        if not result.wasSuccessful():
            raise AssertionError("focused recovery tests failed")
    report = {"verification": "surface-network-recovery", "utc_run": stamp,
        "cases": cases, "early_rejections": early_rejections, "tests": test_record,
        "limits": {"no_gpu_game_java": True, "no_budget_increase": True,
            "real_two_mountains": "not recomputed; previous deep-valley over-budget failure remains",
            "real_outlet_certification": "not supplied; no unknown SRTM read",
            "lake_water_published": False,
            "accepted_engineering_is_not_naturalness_or_complete_real_geography_acceptance": True}}
    _write_json(directory / "report.json", report)
    print(directory / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
