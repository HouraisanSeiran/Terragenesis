"""Finite saddle path analytic evidence; actual TD face-flux integration pending."""

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
from terrain_pipeline.td_basin_breach import generate_saddle_breach, load_saddle_breach, saddle_path_face_identity, save_saddle_breach
from terrain_pipeline.td_material_field import make_material_field
from tools.verify_td_material_field import hostile_checks


def analytic_case(*, volume=1e8, duration=86400, thickness=4, protected=False, unknown=False, target=None, missing_hydro=False):
    height = np.asarray([[2.0, np.nan if unknown else 2.01, 1.98, 1.94]])
    valid = np.isfinite(height)
    mask = np.asarray([[False, protected, False, False]])
    materials = make_material_field(height.shape, origin_m_xz=(0, 0), spacing_m=1, protected_mask=mask,
                                    parameters={"erodibility_range": [1, 1], "weak_path_preference_range": [1, 1],
                                                "erodible_thickness_range_m": [thickness, thickness]})
    path = np.arange(4, dtype=np.int64)
    target = np.linspace(2, 1.94, 4) if target is None else target
    identities = {"source_identity_sha256": "1" * 64, "topology_identity_sha256": "2" * 64, "hydro_identity_sha256": "3" * 64}
    faces = saddle_path_face_identity(height, path, source_identity_sha256=identities["source_identity_sha256"], topology_identity_sha256=identities["topology_identity_sha256"])
    hydro = {"hydro_identity_sha256": identities["hydro_identity_sha256"], "face_cell_ids": [1, 2],
             "outward_volume_m3": volume, "positive_outflow_steps": duration, "dt_s": 1}
    anchor = {"topology_identity_sha256": identities["topology_identity_sha256"], "source_basin_id": 0,
              "destination_basin_id": 1, "tail_cell_ids": [3], "engineering_open_boundary": False}
    return generate_saddle_breach(height, valid, spacing_m=1, materials=materials, path_cell_ids=path,
                                  target_bed_m=target, path_face_identity=faces, **identities,
                                  routed_volume_m3=np.full(4, volume), wet_duration_s=np.full(4, duration),
                                  hydro_face_evidence=None if missing_hydro else hydro, downstream_anchor_evidence=anchor)


def independent_audit(bundle):
    arrays = bundle["arrays"]
    metadata = bundle["metadata"]
    path = arrays["path_cell_ids"]
    target = arrays["path_target_bed_m"]
    height = arrays["original_height_m"]
    rows, cols = np.divmod(path, height.shape[1])
    assert np.all(np.abs(np.diff(rows)) + np.abs(np.diff(cols)) == 1)
    slope = (target[:-1] - target[1:]) / metadata["spacing_m"]
    expected_potential = 0.15 * np.log1p(arrays["path_routed_volume_m3"][:-1] / 1000)
    expected_potential *= (1 - np.exp(-arrays["path_wet_duration_s"][:-1] / 3600)) * np.sqrt(np.maximum(slope, 0))
    np.testing.assert_allclose(arrays["path_potential_depth_m"][:-1], expected_potential, rtol=1e-12, atol=1e-12)
    if metadata["status"] == "rejected":
        np.testing.assert_array_equal(arrays["height_m"], height)
        assert np.sum(arrays["source_solid_m3"]) == 0
    else:
        assert np.all(slope >= 1e-6)
        np.testing.assert_allclose(target, np.linspace(target[0], target[-1], path.size), atol=1e-12, rtol=0)
        np.testing.assert_allclose(arrays["height_m"].ravel()[path], target, atol=1e-12, rtol=0)
        requested = height.ravel()[path] - target
        assert np.all(requested <= arrays["path_potential_depth_m"] + 1e-8)
        assert np.all(requested <= arrays["path_erodible_thickness_m"] + 1e-8)
    area = metadata["spacing_m"] ** 2
    removed = float(np.nansum(height - arrays["height_m"])) * area
    solid = removed * 0.9
    mass = solid * 2650
    stored = float(np.sum(arrays["stored_solid_m3"]))
    assert abs(solid - stored) <= 1e-9 + 1e-12 * solid
    assert abs(float(np.sum(arrays["source_mass_kg"])) - mass) <= 1e-9
    assert arrays["stored_solid_m3"].ravel()[path[-1]] == stored
    assert arrays["height_m"].ravel()[path[-1]] == height.ravel()[path[-1]]
    assert arrays["height_m"].ravel()[path[0]] == height.ravel()[path[0]]
    return {"source_geometry_m3": removed, "source_solid_m3": solid,
            "source_mass_kg": mass, "endpoint_inventory_solid_m3": stored,
            "independent_residual_m3": solid - stored, "status": metadata["status"]}


def verify(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cases = {"success": analytic_case(), "insufficient_water": analytic_case(volume=1),
             "insufficient_thickness": analytic_case(thickness=0.015), "protection": analytic_case(protected=True),
             "unknown": analytic_case(unknown=True), "zero_water": analytic_case(volume=0),
             "zero_duration": analytic_case(duration=0), "missing_actual_face": analytic_case(missing_hydro=True)}
    assert len(cases) <= 8
    reports = {}
    for name, bundle in cases.items():
        if name != "success":
            assert bundle["metadata"]["status"] == "rejected"
        path = output / (name + ".npz")
        save_saddle_breach(bundle, path)
        digest = file_sha256(path)
        with patch("terrain_pipeline.td_basin_breach.generate_saddle_breach", side_effect=AssertionError("cold generation forbidden")), patch("terrain_pipeline.td_material_field.make_material_field", side_effect=AssertionError("cold material generation forbidden")):
            loaded = load_saddle_breach(path, expected_sha256=digest, expected_identity=bundle["identity_sha256"])
        reports[name] = {"archive": str(path.resolve()), "expected_sha256": digest,
                         "expected_identity": bundle["identity_sha256"], "rejection_reasons": loaded["metadata"]["rejection_reasons"],
                         "independent_audit": independent_audit(loaded)}
    checks = hostile_checks(cases["success"], load_saddle_breach)
    checks["pinned_cold_read_without_generation"] = True
    checks["independent_analytic_source_endpoint_inventory_and_formula"] = True
    checks["all_rejections_preserve_complete_baseline"] = True
    path = output / "success.npz"
    before = file_sha256(path)
    try:
        save_saddle_breach(cases["zero_water"], path)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing publication overwritten")
    assert file_sha256(path) == before
    checks["existing_publication_unchanged_after_rejected_overwrite"] = True
    report = {"verified_analytic_stage": True, "actual_td_applied": False, "issue_54_resolved": False,
              "external_hydro_and_anchor_evidence_verified": False, "cases": reports, "checks": checks,
              "code_sha256": {name: file_sha256(ROOT / name) for name in (
                  "terrain_pipeline/td_basin_breach.py", "tests/test_td_basin_breach.py", "tools/verify_td_basin_breach.py")},
              "limitations": "Synthetic face evidence only; caller must verify actual 53 archive/face, receiver tail and <=8 real basin candidates before actual TD application. Target-slope heuristic; all cut solids in endpoint independent inventory; no bed fill or export."}
    (output / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ("verification/td-basin-generation/B-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "/breach"))
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.output), ensure_ascii=False))
