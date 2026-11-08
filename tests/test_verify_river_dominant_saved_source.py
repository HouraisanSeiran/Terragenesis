import json

import numpy as np
import pytest

from terrain_pipeline.common_infra import TerrainGrid
from terrain_pipeline.surface_rivers.metric_fluvial_delta import (
    FluvialDeltaBoundary, FluvialDeltaConfig, FluvialDeltaInterval,
    simulate_fluvial_delta,
)
from tools import verify_river_dominant_saved_source as verifier


@pytest.fixture
def saved_case(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    bed = np.full((7, 11), .2)
    bed[:, 7:] = -.5
    exports = np.zeros(bed.shape, bool)
    exports[[1, 3, 5], -1] = True
    terrain = TerrainGrid(bed, np.ones(bed.shape, bool), 100., 200., 3., 3.,
                          "diagnostic_dem_proxy", "acceptance-fixture", "d" * 64)
    boundary = FluvialDeltaBoundary(bed < 0., exports, 0., 2., "fixture-sea")
    config = FluvialDeltaConfig(porosity=.4, capacity_solid_per_water=.0001,
                               max_reentrainment_depth_per_interval_m=.03)
    forcing = [FluvialDeltaInterval((3, 1), 500., 40.),
               FluvialDeltaInterval((3, 1), 500., 0.)]
    result = simulate_fluvial_delta(terrain, boundary, forcing, config)
    np.savez_compressed(
        source / "mouth.npz", initial_bed_m=bed, final_bed_m=result["final_bed_m"],
        stored_solid_m3=result["stored_solid_m3"],
        deposited_solid_m3=result["deposited_solid_m3"], ocean_mask=bed < 0.,
        export_mask=exports, origin_xz_m=np.array([100., 200.]), spacing_m=np.array(3.),
        monthly_time_seconds=np.array([0., 86400., 172800.]),
        metadata_json=np.array(json.dumps(result["metadata"])))
    (source / "summary.json").write_text(
        json.dumps({"feedback_identity_sha256": "f" * 64}), encoding="utf-8")
    for filename in ("geometry-material-daily.npz", "feedback_bundle.npz"):
        np.savez_compressed(source / filename, test_fixture=np.array([1.]))
    monkeypatch.setattr(verifier, "resource_limits", lambda: None)
    monkeypatch.setattr(verifier, "render", lambda output, arrays: None)
    return source, tmp_path / "output"


def test_saved_source_replays_exactly_and_audits_all_arrays(saved_case):
    source, output = saved_case
    summary = verifier.run(source, output)
    assert summary["flags"]["exact_source_replay"]
    assert summary["flags"]["unchanged_zero_control"]
    assert summary["feedback_identity"] == "f" * 64
    verifier.audit(output)
    assert (output / "cold-audit.json").exists()
    with np.load(output / "result.npz", allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["origin_xz_m"], [100., 200.])
        np.testing.assert_array_equal(archive["monthly_time_seconds"], [0., 86400., 172800.])
        assert archive["monthly_water_throughput_m3"].shape == (2, 7, 11)


@pytest.mark.parametrize("field", ["monthly_stored_solid_m3", "metadata_json", "budgets_json"])
def test_cold_audit_rejects_tampered_arrays(saved_case, field):
    source, output = saved_case
    verifier.run(source, output)
    path = output / "result.npz"
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in archive.files}
    if arrays[field].dtype.kind in "US":
        arrays[field] = np.array("{}")
    else:
        arrays[field].flat[0] += 1.
    np.savez_compressed(path, **arrays)
    with pytest.raises(ValueError, match="mismatch"):
        verifier.audit(output)
    assert not (output / "cold-audit.json").exists()


def test_cold_audit_recomputes_summary_metrics(saved_case):
    source, output = saved_case
    verifier.run(source, output)
    path = output / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    summary["original_land_stored_m3"] += 1.
    path.write_text(json.dumps(summary), encoding="utf-8")
    with pytest.raises(ValueError, match="summary mismatch"):
        verifier.audit(output)


def test_existing_output_is_not_overwritten(saved_case):
    source, output = saved_case
    verifier.run(source, output)
    original = (output / "result.npz").read_bytes()
    with pytest.raises((ValueError, SystemExit), match="exists"):
        verifier.run(source, output)
    assert (output / "result.npz").read_bytes() == original


def test_bad_source_replay_does_not_create_accepted_output(saved_case):
    source, output = saved_case
    path = source / "mouth.npz"
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in archive.files}
    arrays["final_bed_m"].flat[0] += 1.
    np.savez_compressed(path, **arrays)
    with pytest.raises(ValueError, match="replay check failed"):
        verifier.run(source, output)
    assert not output.exists()


def test_cold_audit_rejects_changed_supply_source(saved_case):
    source, output = saved_case
    verifier.run(source, output)
    np.savez_compressed(source / "feedback_bundle.npz", test_fixture=np.array([2.]))
    with pytest.raises(ValueError, match="source hashes differ"):
        verifier.audit(output)
