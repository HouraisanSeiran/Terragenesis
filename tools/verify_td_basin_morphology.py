"""Independent analytic single-round sediment accounting; no TD coupled solve."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_basin_morphology import generate_morphology, load_morphology, save_morphology
from terrain_pipeline.td_material_field import make_material_field
from tools.verify_td_material_field import hostile_checks


def analytic_case(height, receiver, *, candidate_kind="breach", open_cells=(), volume=None, duration=None, protected=None, parameters=None):
    height = np.asarray(height, np.float64)
    volume = np.full(height.shape, 1000.0) if volume is None else np.asarray(volume, np.float64)
    duration = np.full(height.shape, 3600.0) if duration is None else np.asarray(duration, np.float64)
    materials = make_material_field(height.shape, origin_m_xz=(0, 0), spacing_m=1,
                                    protected_mask=protected, parameters={"erodibility_range": [1, 1],
                                    "weak_path_preference_range": [1, 1], "erodible_thickness_range_m": [4, 4]})
    return generate_morphology(height, np.isfinite(height), np.asarray(receiver, np.int64), volume, duration,
                               spacing_m=1, materials=materials, candidate_kind=candidate_kind,
                               parameters={"engineering_open_boundary_cell_ids": list(open_cells), **(parameters or {})})


def independent_audit(bundle):
    arrays = bundle["arrays"]
    area = bundle["metadata"]["spacing_m"] ** 2
    material = bundle["metadata"]["material_parameters"]
    config = bundle["metadata"]["parameters"]
    height = arrays["original_height_m"].ravel()
    receiver = arrays["receiver"]
    expected_incoming = np.zeros(height.size)
    expected_depth = np.zeros(height.size)
    for cell, target in enumerate(receiver):
        if target < 0:
            continue
        assert abs(cell // arrays["height_m"].shape[1] - target // arrays["height_m"].shape[1]) + abs(cell % arrays["height_m"].shape[1] - target % arrays["height_m"].shape[1]) == 1
        expected_incoming[target] += arrays["transported_solid_m3"].ravel()[cell]
        slope = (height[cell] - height[target]) / bundle["metadata"]["spacing_m"]
        assert slope >= 0
        volume = arrays["routed_volume_m3"].ravel()[cell]
        duration = arrays["wet_duration_s"].ravel()[cell]
        expected_depth[cell] = min(4, config["erosion_scale_m"] * np.log1p(volume / 1000) * (1 - np.exp(-duration / 3600)) * np.sqrt(slope))
    np.testing.assert_allclose(arrays["erosion_depth_m"].ravel(), expected_depth, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(arrays["incoming_solid_m3"].ravel(), expected_incoming, rtol=1e-12, atol=1e-12)
    source_geometry = float(np.sum(expected_depth)) * area
    source_solid = source_geometry * (1 - material["source_porosity"])
    deposited = float(np.sum(arrays["deposited_solid_m3"]))
    stored = float(np.sum(arrays["stored_solid_m3"]))
    exported = float(np.sum(arrays["exported_solid_m3"]))
    residual = source_solid - deposited - stored - exported
    assert abs(residual) <= 1e-9 + 1e-12 * source_solid
    assert abs(float(np.sum(arrays["source_mass_kg"])) - source_solid * material["solid_density_kg_m3"]) <= 1e-9
    np.testing.assert_allclose(arrays["deposit_depth_m"] * area, arrays["deposited_solid_m3"] / (1 - material["deposit_porosity"]), rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(arrays["height_m"] - arrays["original_height_m"], arrays["deposit_depth_m"] - arrays["erosion_depth_m"], rtol=1e-12, atol=1e-12)
    for cell in range(height.size):
        available = arrays["source_solid_m3"].ravel()[cell] + expected_incoming[cell]
        used = sum(arrays[name].ravel()[cell] for name in ("transported_solid_m3", "deposited_solid_m3", "stored_solid_m3", "exported_solid_m3"))
        assert abs(available - used) <= 1e-9 + 1e-12 * available
    return {"source_geometry_m3": source_geometry, "source_solid_m3": source_solid,
            "deposit_solid_m3": deposited, "deposit_geometry_m3": deposited / (1 - material["deposit_porosity"]),
            "stored_solid_m3": stored, "exported_solid_m3": exported, "independent_residual_m3": residual}


def verify(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cases = {
        "chain_open": analytic_case([[3, 2, 1]], [1, 2, -1], open_cells=[2]),
        "chain_closed": analytic_case([[3, 2, 1]], [1, 2, -1]),
        "chain_deposit": analytic_case([[3, 2, 1]], [1, 2, -1], candidate_kind="deposition"),
        "confluence": analytic_case([[3, 2], [4, 1]], [1, 3, 3, -1], candidate_kind="deposition"),
        "zero_water": analytic_case([[3, 2, 1]], [1, 2, -1], volume=[[0, 0, 0]]),
        "zero_duration": analytic_case([[3, 2, 1]], [1, 2, -1], duration=[[0, 0, 0]]),
        "bounded_deposit": analytic_case([[3, 2, 1]], [1, 2, -1], candidate_kind="deposition", parameters={"transport_ratio": 0.00001, "max_deposit_depth_m": 0.0001}),
        "flat": analytic_case([[2, 2, 2]], [1, 2, -1]),
    }
    reports = {}
    for name, bundle in cases.items():
        path = output / (name + ".npz")
        save_morphology(bundle, path)
        digest = file_sha256(path)
        with patch("terrain_pipeline.td_basin_morphology.generate_morphology", side_effect=AssertionError("cold advance forbidden")), patch("terrain_pipeline.td_material_field.make_material_field", side_effect=AssertionError("cold generation forbidden")):
            loaded = load_morphology(path, expected_sha256=digest, expected_identity=bundle["identity_sha256"])
        reports[name] = {"archive": str(path.resolve()), "expected_sha256": digest,
                         "expected_identity": bundle["identity_sha256"], "independent_audit": independent_audit(loaded)}
    checks = {"all_analytic_ledgers_independently_checked": True, "pinned_cold_read_without_generation": True}
    checks.update(hostile_checks(cases["chain_closed"], load_morphology))
    for name, height, receiver, options in (
        ("uphill_rejected", [[1, 2, 3]], [1, 2, -1], {}),
        ("diagonal_rejected", [[3, 2], [4, 1]], [3, 3, 3, -1], {}),
        ("protection_rejected", [[3, 2, 1]], [1, 2, -1], {"protected": np.asarray([[False, True, False]])}),
        ("unknown_crossing_rejected", [[3, np.nan, 1]], [1, 2, -1], {"volume": [[1000, 0, 1000]], "duration": [[3600, 0, 3600]]}),
        ("cycle_rejected", [[2, 2, 1]], [1, 0, -1], {}),
        ("budget_rejected", [[3, 2, 1]], [1, 2, -1], {"parameters": {"max_work_cells": 2}})):
        try:
            analytic_case(height, receiver, **options)
        except ValueError:
            checks[name] = True
        else:
            raise AssertionError(name)
    report = {"verified_analytic_stage": True, "issue_54_resolved": False,
              "hydrology_coupled_verified": False, "checks": checks, "cases": reports,
              "limitations": "Single round generative heuristic; A 53 and actual TD coupled selection/rebuild still pending; no physical evolution age or naturalness certification."}
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ("verification/td-basin-generation/B-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "/morphology"))
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.output), ensure_ascii=False))
