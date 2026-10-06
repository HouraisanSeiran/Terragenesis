"""Fixed non-game delivery scenarios and generation-free read-only verification."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.surface_network_consumer import (
    export_surface_network, load_surface_network_delivery, sample_surface_network,
    slice_surface_network_delivery,
)
from terrain_pipeline.surface_network_recovery import recover_surface_network
from tests.test_surface_network_recovery import recovery_case
from tests.test_surface_network_consumer import (
    DATUM, DECLARATION, SurfaceNetworkConsumerTests, forbid_generation,
    forge_delivery_proof, rehash_surface_recovery,
)


def _write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    directory = ROOT / "verification" / "surface-network-consumer" / ("run-" + stamp)
    directory.mkdir(parents=True, exist_ok=False)
    cases = {}
    results = {}
    for kind in ("baseline", "valley", "reroute"):
        recovery = recover_surface_network(**recovery_case(kind))
        results[kind] = recovery
        path = export_surface_network(recovery, DATUM, directory / kind, source_declaration=DECLARATION)
        with forbid_generation():
            delivery = load_surface_network_delivery(path)
            first = slice_surface_network_delivery(delivery, slice(10, 51), slice(0, 41))
            second = slice_surface_network_delivery(delivery, slice(10, 51), slice(25, 61))
            for name in first["arrays"]:
                np.testing.assert_array_equal(first["arrays"][name][:, 25:41], second["arrays"][name][:, :16])
                if first["arrays"][name].flags.writeable:
                    raise AssertionError("consumer returned a writable window")
            sample = sample_surface_network(delivery, 30., 30.)
        graph = delivery["centerline"]
        geometry = delivery["geometry"]
        h0 = recovery["surface"]["arrays"]["source_surface_m"] if recovery["fine_ledger"] is None else recovery["fine_ledger"]["arrays"]["source_surface_m"]
        np.testing.assert_array_equal(delivery["base"].reference_elevation_m, h0)
        cases[kind] = {"path": str(path.resolve()), "recovery_sha256": recovery["identity_sha256"],
            "content_id": delivery["manifest"]["content_id"], "base_content_id": delivery["base"].content_id,
            "derived_content_id": delivery["derived"].content_id, "h0_original_bound": True,
            "generation_forbidden_during_read": True, "overlapping_windows_equal": True,
            "readonly_windows": True, "dry_stage_zero": bool(np.all(geometry["water_surface_m"][~geometry["wet_mask"]] == 0)),
            "wet_nodes": int(geometry["wet_mask"].sum()), "coarse_graph_nodes": graph["receiver"].size,
            "all_outlet_q_m3_s": float(graph["discharge_m3_s"][graph["outlet_mask"]].sum()),
            "active_outlet_q_m3_s": float(graph["discharge_m3_s"][graph["outlet_mask"] & graph["active_mask"]].sum()),
            "inactive_outlet_q_m3_s": float(graph["discharge_m3_s"][graph["outlet_mask"] & ~graph["active_mask"]].sum()),
            "all_local_source_q_m3_s": float(graph["local_discharge_m3_s"].sum()),
            "sample_water_depth_m": float(sample["arrays"]["water_depth_m"][0, 0])}
    rejected = {}
    for name in ("rehashed_stage_jump", "rehashed_fine_domain", "rehashed_off_channel_protection"):
        forged = deepcopy(results["baseline"])
        if name == "rehashed_stage_jump":
            field, cell = "water_surface_m", (9, 19)
            changed = forged["surface"]["arrays"][field].copy()
            changed[cell] += 2.
        elif name == "rehashed_fine_domain":
            field, cell = "domain_mask", (9, 19)
            changed = forged["surface"]["arrays"][field].copy()
            changed[cell] = False
        else:
            field, cell = "protected_mask", (1, 1)
            changed = forged["surface"]["arrays"][field].copy()
            changed[cell] = True
        forged["surface"]["arrays"][field] = changed
        rehash_surface_recovery(forged)
        path = export_surface_network(results["baseline"], DATUM, directory / name, source_declaration=DECLARATION)
        forge_delivery_proof(path, forged)
        try:
            with forbid_generation():
                load_surface_network_delivery(path)
        except ValueError as error:
            rejected[name] = {"rejected": True, "reason": str(error), "path": str(path.resolve()),
                              "all_surface_recovery_artifact_file_hashes_updated": True}
        else:
            raise AssertionError(name + " unexpectedly loaded")
    failed_case = recovery_case("valley")
    failed_case["valley_recipe"] = replace(failed_case["valley_recipe"], max_total_cut_volume_m3=0.)
    failed_case["recovery_recipe"] = replace(failed_case["recovery_recipe"], max_attempts=2)
    failed = recover_surface_network(**failed_case)
    try:
        export_surface_network(failed, DATUM, directory / "ledger_failure", source_declaration=DECLARATION)
    except ValueError as error:
        rejected["cumulative_ledger_failure"] = {"rejected": True, "reason": str(error),
            "surface_prepared_but_recovery_failed": failed["surface"]["status"] == "prepared",
            "partial_directory_absent": not (directory / "ledger_failure").exists()}
    else:
        raise AssertionError("cumulative ledger failure exported")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SurfaceNetworkConsumerTests)
    test_result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"verification": "surface-network-consumer-v1", "utc_run": stamp,
        "cases": cases, "rejections": rejected,
        "tests": {"count": test_result.testsRun, "failures": len(test_result.failures), "errors": len(test_result.errors)},
        "scope": {"generic_artifact_double_package": True, "hydrology_sidecar_not_Q_raster": True,
            "no_game_gpu_java_or_model": True, "natural_outlets_certified": False,
            "lake_water_published": False, "full_land_rainfall_catchment_closed": False}}
    _write_json(directory / "report.json", report)
    print(directory / "report.json")
    if not test_result.wasSuccessful():
        raise AssertionError("consumer focused tests failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
