"""Diagnostic: sequential default vs 4-step A/B diffusion ablation from formal 4224."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_fluvial_channel_remobilization import resource_limits, source_input
resource_limits()
import numpy as np
from tools.verify_fluvial_morphodynamics import (
    archive_result, native_material_acceptance, PHASE_FIELDS, GRAVITY_ARRAY_FIELDS)
from tools.fluvial_delta_region_budget import summarize_phase_regions
from tools.verify_fluvial_morphodynamics import (
    surface_exposure_diagnostics, sustained_distributary_evidence)
from terrain_pipeline.surface_rivers.metric_fluvial_distributary import prepare_marine_transition
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import (
    MorphodynamicsConfig, WATER_ROUTING_REPAIR_VERSION, simulate_fluvial_morphodynamics)

import argparse
_parser = argparse.ArgumentParser()
_parser.add_argument("--steps", type=int, choices=(4, 128), default=4)
_args = _parser.parse_args()
STEP_COUNT = _args.steps

FIELDS = ("beds_m", "depths_m", "stages_m", "qx_m2_s", "qz_m2_s",
          "ux_m_s", "uz_m_s", "speed_m_s")
SEA = 0.0
SPACING = 5.0
NATIVE_END = 4224
FOUR_STEP_OUTPUT = ROOT / ".scratch/hydrological-planning-domain/diffusion-ablation-4224-20261016-01"
FOUR_STEP_SUMMARY = FOUR_STEP_OUTPUT / "summary.json"
FOUR_STEP_PROOF_NAME = "four-step-proof.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


if STEP_COUNT == 128:
    output = ROOT / ".scratch/hydrological-planning-domain/diffusion-ablation-4224-128steps-20261016-01"
else:
    output = FOUR_STEP_OUTPUT
output.mkdir(exist_ok=False)
formal = ROOT / "verification/fluvial-delta/morphodynamics-20261016-01"
snapshot = output / "parent-4224-chain.json"
snapshot.write_bytes((formal / "chain.json").read_bytes())
manifest = json.loads(snapshot.read_text(encoding="utf-8"))
last_batch = manifest["batches"][-1]
assert set(last_batch.keys()) == {"path", "sha256"}
parent_archive = Path(last_batch["path"])
parent_archive_sha = last_batch["sha256"]
assert digest(parent_archive) == parent_archive_sha

four_step_proof = None
if STEP_COUNT == 128:
    assert FOUR_STEP_SUMMARY.is_file(), "missing prior 4-step summary"
    prior_summary_bytes = FOUR_STEP_SUMMARY.read_bytes()
    prior_summary = json.loads(prior_summary_bytes.decode("utf-8"))
    assert prior_summary.get("passed") is True
    assert prior_summary.get("start_step") == 4224
    assert prior_summary.get("end_step") == 4228
    checks = prior_summary.get("checks", [])
    assert "default_a_identical_all8_times_phases_ledger_stats_checkpoint_material_rng" in checks
    proof_parent_sha = prior_summary.get("parent_archive_sha256")
    assert proof_parent_sha == parent_archive_sha, "four-step proof parent sha mismatch"
    proof_snapshot = output / FOUR_STEP_PROOF_NAME
    proof_snapshot.write_bytes(prior_summary_bytes)
    four_step_proof = {"path": str(FOUR_STEP_SUMMARY), "snapshot_path": str(proof_snapshot), "sha256": hashlib.sha256(prior_summary_bytes).hexdigest(), "parent_archive_sha256": parent_archive_sha}

with np.load(parent_archive, allow_pickle=False) as saved:
    core = json.loads(str(saved["metadata_json"].item()))["core"]
    parent_fields = {key: saved[key][-1].copy() for key in FIELDS}
    parent_base = saved["final_mobile_base_m"].copy()
    parent_time = float(saved["times_s"][-1])
    valid = saved["backend_valid_mask"] & (saved["cell_type"] != -2)
    ocean = saved["backend_ocean_mask"].copy()
    exports = saved["backend_export_mask"].copy()
    inlet = saved["backend_inlet_mask"].copy()
    fixed4224_bed = saved["beds_m"][-1].copy()
assert core["native_end_step_index"] == NATIVE_END
assert core["algorithm_version"] == WATER_ROUTING_REPAIR_VERSION
assert not core.get("diagnostic_only")
parent_dir = Path(core["checkpoint_end_path"]).parent
parent_hashes = {name: digest(parent_dir / name) for name in (
    "checkpoint.npz", "adapter-material-state.npz", "adapter-continuation.json")}
assert digest(parent_dir / "checkpoint.npz") == core["checkpoint_end_sha256"]
assert digest(parent_dir / "adapter-material-state.npz") == core["material_state_end_sha256"]

first_batch = manifest["batches"][0]
assert set(first_batch.keys()) == {"path", "sha256"}
first_archive = Path(first_batch["path"])
assert digest(first_archive) == first_batch["sha256"]
with np.load(first_archive, allow_pickle=False) as initial:
    original_initial_bed = initial["initial_bed_m"].copy()

terrain, boundary, _, _, provenance, raw = source_input()
preparation = prepare_marine_transition(
    terrain, boundary, (75, 51), radius_m=300., slope_m_per_m=.03,
    maximum_raise_m=16., maximum_fill_bulk_m3=2_000_000., supplied_solid_m3=1_300_000.)
started = time.perf_counter()


def run(name, enabled, steps=STEP_COUNT, checkpoint=parent_dir, change=None, repair=True):
    if enabled is None:
        diagnostic = None
    else:
        diagnostic = {"enabled": bool(enabled), "parent_archive_path": str(parent_archive),
        "parent_archive_sha256": parent_archive_sha,
        "checkpoint_sha256": core["checkpoint_end_sha256"],
        "material_state_sha256": core["material_state_end_sha256"]}
        if four_step_proof is not None:
            diagnostic["four_step_proof"] = dict(four_step_proof)
        diagnostic["steps"] = STEP_COUNT
    result = simulate_fluvial_morphodynamics(
        terrain, boundary, config=MorphodynamicsConfig(steps=steps),
        inlet_cell=(75, 51),
        initial_cover_solid_m3=preparation["initial_cover_solid_m3"],
        output_dir=output / name, resume_checkpoint=checkpoint,
        gravity_stability=True, routing_dry_depth_m=.01,
        quantized_native_exchange=True, mechanism_transition=change,
        water_routing_repair=repair, diagnostic_diffusion_ablation=diagnostic,
        progress_callback=lambda step, seconds: print(
            "PROGRESS", name, step, seconds, flush=True))
    if enabled is None:
        result["metadata"]["diagnostic_only"] = True
        result["metadata"]["effective_diffusion_enabled"] = True
        cont = output / name / "backend/adapter-continuation.json"
        payload = json.loads(cont.read_text(encoding="utf-8"))
        payload["diagnostic_only"] = True
        payload["effective_diffusion_enabled"] = True
        cont.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    artifact = output / name / "detail.npz"
    archive_result(artifact, result, provenance=provenance,
                   raw_td_m=raw, preparation=preparation)
    residuals = [{"step": p["step_index"], "phase": p["phase"],
                  "residual_bulk_m3": float(p["delta_bulk_m3"].sum())
                  - p["injected_bulk_m3"] + p["exported_bulk_m3"]
                  + p["lost_bulk_m3"] - p["inlet_correction_bulk_m3"]}
                 for p in result["phases"]]
    gate = native_material_acceptance(result["phases"], residuals)
    assert gate["native_material_gate"]
    for phase in result["phases"]:
        floor_gap = (result["backend_source_bed_m"] - phase["end_bed_m"]).max()
        assert float(floor_gap) <= 4. + 2e-6
    (output / name / "material-audit.json").write_text(
        json.dumps(gate, indent=2), encoding="utf-8")
    region = summarize_phase_regions(
        [p["phase"] for p in result["phases"]],
        np.stack([p["delta_bulk_m3"] for p in result["phases"]]),
        parent_fields["beds_m"], result["beds_m"][-1], valid, ocean, SPACING, SEA)
    (output / name / "region-phase.json").write_text(
        json.dumps(region, indent=2), encoding="utf-8")
    arrays = {key: result[key] for key in FIELDS}
    arrays["times_s"] = result["times_s"]
    arrays["backend_valid_mask"] = valid
    arrays["cell_type"] = result["cell_type"]
    arrays["backend_ocean_mask"] = ocean
    arrays["backend_export_mask"] = exports
    arrays["backend_inlet_mask"] = inlet
    morph = sustained_distributary_evidence(arrays, spacing_m=SPACING)
    exposure = surface_exposure_diagnostics(
        original_initial_bed, result["beds_m"][-1], result["depths_m"][-1],
        ocean, valid, SPACING, SEA)
    near = valid & ocean & (np.abs(fixed4224_bed - SEA) <= 0.25)
    water_ranges = {key: [float(result[key][-1][near].min()), float(result[key][-1][near].max())] if near.any() else None for key in ("stages_m", "depths_m")}
    morph.update({"exposure": exposure, "original_initial_reference": True, "fixed4224_near_sea_level_water_ranges_m": water_ranges})
    (output / name / "morphology.json").write_text(
        json.dumps(morph, indent=2), encoding="utf-8")
    print("SAVED", name, "elapsed_s", time.perf_counter() - started, flush=True)
    return result, {"path": str(artifact), "sha256": digest(artifact),
                    "gate": gate, "region": region, "morphology": morph}


run_records = []
if STEP_COUNT == 4:
    default, default_batch = run("default", None)
    run_records.append(("default", default, default_batch))
else:
    default, default_batch = None, None
a_run, a_batch = run("ablation-a", True)
run_records.append(("ablation-a", a_run, a_batch))
b_run, b_batch = run("ablation-b", False)
run_records.append(("ablation-b", b_run, b_batch))

for name, run_result, _batch in run_records:
    for key in FIELDS:
        np.testing.assert_array_equal(run_result[key][0], parent_fields[key], err_msg=key)
    np.testing.assert_array_equal(run_result["initial_mobile_base_m"], parent_base)
    np.testing.assert_equal(float(run_result["times_s"][0]), parent_time)


def compare_phase_sequences(left, right, tag):
    assert len(left) == len(right)
    for exp, act in zip(left, right):
        assert set(exp.keys()) == set(act.keys())
        for key in exp:
            if key == "gravity_ledger":
                assert exp[key] == act[key], tag + ":" + key
            else:
                np.testing.assert_array_equal(exp[key], act[key], err_msg=tag + ":" + key)


if STEP_COUNT == 4:
    compare_phase_sequences(default["phases"], a_run["phases"], "default-vs-a")
    for key in FIELDS:
        np.testing.assert_array_equal(default[key], a_run[key], err_msg="default-a " + key)
    np.testing.assert_array_equal(default["final_mobile_base_m"], a_run["final_mobile_base_m"])
    assert default["bulk_ledger"] == a_run["bulk_ledger"]
    assert default["metadata"]["water_routing_repair_statistics"] == (
        a_run["metadata"]["water_routing_repair_statistics"])
    np.testing.assert_array_equal(default["times_s"], a_run["times_s"])
    for name in ("checkpoint.npz", "adapter-material-state.npz"):
        with np.load(output / "default/backend" / name, allow_pickle=True) as expected, \
             np.load(output / "ablation-a/backend" / name, allow_pickle=True) as actual:
            assert expected.files == actual.files
            for key in expected.files:
                np.testing.assert_equal(expected[key], actual[key], err_msg=name + ":" + key)
np.testing.assert_array_equal(a_run["times_s"], b_run["times_s"])
assert a_run["metadata"]["effective_diffusion_enabled"] is True
assert b_run["metadata"]["effective_diffusion_enabled"] is False

assert a_run["phases"][0]["phase"] == "sand"
assert b_run["phases"][0]["phase"] == "sand"
compare_phase_sequences([a_run["phases"][0]], [b_run["phases"][0]], "first-phase-a-b")

diffusion_nonzero = False
for phase in a_run["phases"]:
    if phase["phase"] == "diffusion":
        if float(np.abs(phase["delta_bulk_m3"]).sum()) > 0.:
            diffusion_nonzero = True
assert diffusion_nonzero
for phase in b_run["phases"]:
    if phase["phase"] == "diffusion":
        np.testing.assert_array_equal(phase["start_bed_m"], phase["end_bed_m"])
        assert int(np.count_nonzero(phase["delta_bulk_m3"])) == 0

for name, result, batch in run_records:
    cont = output / name / "backend/adapter-continuation.json"
    payload = json.loads(cont.read_text(encoding="utf-8"))
    assert payload["effective_diffusion_enabled"] == result["metadata"]["effective_diffusion_enabled"]
    assert payload.get("diagnostic_only", False) is True
    try:
        simulate_fluvial_morphodynamics(
            terrain, boundary, config=MorphodynamicsConfig(steps=1),
            inlet_cell=(75, 51),
            initial_cover_solid_m3=preparation["initial_cover_solid_m3"],
            output_dir=output / (name + "-resume"), resume_checkpoint=output / name / "backend",
            gravity_stability=True, routing_dry_depth_m=.01,
            quantized_native_exchange=True, water_routing_repair=True)
    except ValueError as exc:
        assert "terminal and cannot continue" in str(exc)
    else:
        raise AssertionError(name + " resume should be refused")

for name, value in parent_hashes.items():
    assert digest(parent_dir / name) == value
assert digest(parent_archive) == parent_archive_sha
assert digest(snapshot) == digest(formal / "chain.json")
if four_step_proof is not None:
    assert digest(FOUR_STEP_SUMMARY) == four_step_proof["sha256"]
    assert digest(Path(four_step_proof["snapshot_path"])) == four_step_proof["sha256"]

checks = ["parent4224_metadata_and_hashes_verified", "original_initial_reference_loaded",
    "initial_fields_times_material_and_firstsand",
    "firstsand_before_diffusion",
    "a_b_initial_material_firstsand_shared",
    "b_diffusion_phase_zero_delta", "a_diffusion_phase_has_nonzero_delta",
    "material_gate_all_runs", "source_floor_all_phases",
    "terminal_refusal_all_runs", "parent_hashes_unchanged_at_end"]
if STEP_COUNT == 4:
    checks.insert(2, "default_a_identical_all8_times_phases_ledger_stats_checkpoint_material_rng")
else:
    checks.insert(2, "four_step_prior_default_exact_evidence_verified")
summary = {"passed": True,
    "checks": checks,
    "steps": STEP_COUNT,
    "default_exact_current_run": STEP_COUNT == 4,
    "four_step_proof": dict(four_step_proof) if four_step_proof is not None else None,
    "parent": str(parent_archive), "parent_archive_sha256": parent_archive_sha,
    "original_initial_archive": str(first_archive),
    "original_initial_sha256": first_batch["sha256"],
    "start_step": NATIVE_END, "end_step": NATIVE_END + STEP_COUNT,
    "algorithm_version": WATER_ROUTING_REPAIR_VERSION,
    "parent_chain_snapshot": str(snapshot), "elapsed_s": time.perf_counter() - started,
    "runs": {name: {"ledger": result["bulk_ledger"], "material": batch["gate"],
        "regions": batch["region"], "morphology": batch["morphology"]}
        for name, result, batch in run_records},
    "semantics": "diagnostic only; bounded A/B from formal4224 separate from formal chain; "
        "default exact current-run comparison only when steps==4; "
        "reports actual exposure and sustained gate, not formal success."}
(output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2), flush=True)
