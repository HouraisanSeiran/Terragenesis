"""Run the fixed TD candidate in bounded native checkpoint batches."""

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[name] = "1"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_fluvial_channel_remobilization import resource_limits, source_input
from tools.verify_fluvial_morphodynamics import archive_result, formal_acceptance
from terrain_pipeline.surface_rivers.metric_fluvial_distributary import prepare_marine_transition
from terrain_pipeline.surface_rivers.metric_fluvial_morphodynamics import (
    MorphodynamicsConfig, SOURCE_LIMITED_VERSION, GRAVITY_VERSION, GRAVITY_PARAMETERS,
    DRY_DEPTH_VERSION, QUANTIZED_EXCHANGE_VERSION, WATER_ROUTING_REPAIR_VERSION, WATER_REPAIR_MECHANISMS,
    mechanism_identity_for, simulate_fluvial_morphodynamics,
)


def run(output, target_step, transition_path=None, resume_chain=None, gravity_stability=False,
        routing_dry_depth_m=None, quantized_native_exchange=False, water_routing_repair=False):
    resource_limits()
    maximum_step = 4224 if water_routing_repair else 4096
    if target_step < 512 or target_step > maximum_step or target_step % 128:
        raise ValueError("fixed candidate target must be 512..%d in 128-step batches" % maximum_step)
    if water_routing_repair and (not quantized_native_exchange or target_step != 4224):
        raise ValueError("water repair first continuous candidate requires quantized exchange and target 4224")
    if routing_dry_depth_m is not None and (routing_dry_depth_m != .01 or not gravity_stability):
        raise ValueError("only explicit .01m gravity routing-depth sensitivity is supported")
    if quantized_native_exchange and (not gravity_stability or routing_dry_depth_m != .01):
        raise ValueError("quantized exchange requires the .01m gravity candidate")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "chain.json"
    if manifest_path.exists():
        if resume_chain is not None:
            raise ValueError("existing candidate manifest already owns its continuation")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    elif resume_chain is not None:
        if not gravity_stability or transition_path is None:
            raise ValueError("external candidate chain requires explicit gravity mechanism transition")
        resume_chain = Path(resume_chain).resolve()
        manifest = json.loads(resume_chain.read_text(encoding="utf-8"))
    else:
        manifest = {"schema": "saved-pydeltarcm-chain-v1", "batches": []}
    algorithm_version = GRAVITY_VERSION if gravity_stability else SOURCE_LIMITED_VERSION
    if routing_dry_depth_m is not None:
        algorithm_version = DRY_DEPTH_VERSION
    if quantized_native_exchange:
        algorithm_version = QUANTIZED_EXCHANGE_VERSION
    if water_routing_repair:
        algorithm_version = WATER_ROUTING_REPAIR_VERSION
    start_step, resume, previous_version = 0, None, None
    if manifest["batches"]:
        import numpy as np
        last = manifest["batches"][-1]
        artifact = Path(last["path"])
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != last["sha256"]:
            raise ValueError("previous batch archive bytes changed")
        with np.load(artifact, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata_json"].item()))["core"]
        if metadata.get("diagnostic_only"):
            raise ValueError("terminal diagnostic cannot be a formal chain parent")
        start_step = metadata["native_end_step_index"]
        previous_version = metadata["algorithm_version"]
        resume = str(Path(metadata["checkpoint_end_path"]).parent)
    transition = None
    if previous_version is not None and previous_version != algorithm_version:
        if transition_path is None:
            raise ValueError("resuming a different mechanism requires --mechanism-transition")
        transition = json.loads(Path(transition_path).read_text(encoding="utf-8"))
        if (transition["after_step"] != start_step or transition["from_algorithm_version"] != previous_version
                or transition["to_algorithm_version"] != algorithm_version):
            raise ValueError("transition must identify this checkpoint and preserved failure")
        if gravity_stability:
            expected_previous = SOURCE_LIMITED_VERSION if routing_dry_depth_m is None else GRAVITY_VERSION
            expected_start = 2048 if routing_dry_depth_m is None else 2432
            if quantized_native_exchange:
                expected_previous, expected_start = DRY_DEPTH_VERSION, 2688
            if water_routing_repair:
                expected_previous, expected_start = QUANTIZED_EXCHANGE_VERSION, 4096
            if (previous_version != expected_previous or start_step != expected_start or resume_chain is None
                    or Path(transition["parent_manifest_path"]).resolve() != resume_chain
                    or hashlib.sha256(resume_chain.read_bytes()).hexdigest() != transition["parent_manifest_sha256"]
                    or Path(transition["checkpoint_path"]).resolve() != Path(metadata["checkpoint_end_path"]).resolve()
                    or transition["checkpoint_sha256"] != metadata["checkpoint_end_sha256"]
                    or transition.get("gravity_parameters") != GRAVITY_PARAMETERS
                    or transition.get("mechanism_identity") != mechanism_identity_for(algorithm_version)
                    or not transition.get("reason")):
                raise ValueError("new gravity candidate requires its preserved parent chain/checkpoint and explicit mechanism declaration")
            if routing_dry_depth_m is not None and (transition.get("routing_dry_depth_m") != .01
                    or transition.get("from_routing_dry_depth_m") != (.01 if quantized_native_exchange else .1)):
                raise ValueError("routing-depth sensitivity must declare the native .1m to .01m numerical change")
            if quantized_native_exchange and transition.get("quantized_native_exchange") is not True:
                raise ValueError("quantized exchange transition must explicitly declare the precision mechanism")
            if routing_dry_depth_m is not None and (
                    Path(transition["material_state_start_path"]).resolve() != Path(metadata["material_state_end_path"]).resolve()
                    or transition["material_state_start_sha256"] != metadata["material_state_end_sha256"]):
                raise ValueError("routing-depth sensitivity must inherit the actual parent mobile material state")
            evidence_key = "morphology_failure_evidence" if routing_dry_depth_m is None else "numerical_sensitivity_evidence"
            if quantized_native_exchange and not water_routing_repair:
                evidence_key = "numerical_precision_evidence"
                if not transition.get(evidence_key):
                    raise ValueError("quantized exchange requires preserved precision failure and reproduction evidence")
            if water_routing_repair:
                evidence_key = "water_routing_repair_evidence"
                if (transition.get("water_routing_repair") is not True
                        or transition.get("water_repair_mechanisms") != WATER_REPAIR_MECHANISMS
                        or not transition.get(evidence_key)):
                    raise ValueError("water repair transition must declare its mechanisms and preserved routing evidence")
            for evidence in transition[evidence_key]:
                if hashlib.sha256(Path(evidence["path"]).read_bytes()).hexdigest() != evidence["sha256"]:
                    raise ValueError("preserved morphology failure evidence bytes differ")
        elif hashlib.sha256(Path(transition["failed_archive_path"]).read_bytes()).hexdigest() != transition["failed_archive_sha256"]:
            raise ValueError("transition failure archive bytes differ")
        manifest.setdefault("mechanism_transitions", []).append(transition)
    if water_routing_repair and (not manifest["batches"] or start_step < 4096 or start_step > 4224):
        raise ValueError("water repair candidate must inherit formal v5/4096 or its own bounded v6 chain")
    terrain, boundary, _, _, provenance, raw = source_input()
    provenance = dict(provenance)
    provenance["sediment_origin"] = "declared preparation supply and native river sediment; original source incision separately measured"
    preparation = prepare_marine_transition(terrain, boundary, (75, 51), radius_m=300.,
        slope_m_per_m=.03, maximum_raise_m=16., maximum_fill_bulk_m3=2_000_000., supplied_solid_m3=1_300_000.)
    config = MorphodynamicsConfig(steps=128)
    declaration = {"fixed_config": asdict(config), "first_formal_assessment_step": 512,
                   "maximum_step": maximum_step, "batch_steps": 128,
                   "specification": str(ROOT / ".scratch/hydrological-planning-domain/issues/16-fluvial-delta-morphodynamics.md"),
                   "resource_policy": "two CPU cores, BelowNormal, one numerical thread",
                   "source": provenance, "preparation": preparation["metadata"]}
    if gravity_stability:
        declaration.update(algorithm_version=algorithm_version, gravity_parameters=dict(GRAVITY_PARAMETERS))
    if routing_dry_depth_m is not None:
        declaration["routing_dry_depth_m"] = routing_dry_depth_m
    if quantized_native_exchange:
        declaration["quantized_native_exchange"] = True
    if water_routing_repair:
        declaration.update(water_routing_repair=True, water_repair_mechanisms=dict(WATER_REPAIR_MECHANISMS),
            first_formal_assessment_step=4224,
            specification=str(ROOT / ".scratch/hydrological-planning-domain/issues/17-water-routing-continuous-evolution.md"))
    declaration_path = output / "declaration.json"
    if not declaration_path.exists():
        declaration_path.write_text(json.dumps(declaration, indent=2), encoding="utf-8")
    started = time.perf_counter()
    for begin in range(start_step, target_step, 128):
        suffix = "v6" if water_routing_repair else "v5" if quantized_native_exchange else "v4" if routing_dry_depth_m is not None else "v3" if gravity_stability else "v2"
        directory = output / ("batch-%04d-%04d-%s" % (begin, begin + 128, suffix))
        if directory.exists():
            raise ValueError("preserve existing completed or failed batch: " + str(directory))
        result = simulate_fluvial_morphodynamics(terrain, boundary, config=config, inlet_cell=(75, 51),
            initial_cover_solid_m3=preparation["initial_cover_solid_m3"], output_dir=directory,
            resume_checkpoint=resume,
            gravity_stability=gravity_stability,
            routing_dry_depth_m=routing_dry_depth_m,
            quantized_native_exchange=quantized_native_exchange,
            water_routing_repair=water_routing_repair,
            mechanism_transition=transition if transition is not None and begin == transition["after_step"] else None,
            progress_callback=lambda iteration, seconds: print("PROGRESS", iteration, "physical_s", seconds,
                "elapsed_s", round(time.perf_counter() - started, 3), flush=True))
        artifact = directory / "detail.npz"
        archive_result(artifact, result, provenance=provenance, raw_td_m=raw, preparation=preparation)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        print("BATCH_SAVED", begin + 128, "elapsed_s", round(time.perf_counter() - started, 3),
              "ledger", json.dumps(result["bulk_ledger"], sort_keys=True), flush=True)
        audit_process = subprocess.run([sys.executable, str(ROOT / "tools/verify_fluvial_morphodynamics.py"),
            "--audit", str(artifact), "--expected-sha256", digest], check=True, capture_output=True, text=True)
        audit = json.loads(audit_process.stdout)
        (directory / "cold-audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        if not audit["material_acceptance"]["native_material_gate"]:
            raise ValueError("saved batch fails the fixed native material gate")
        manifest["batches"].append({"path": str(artifact), "sha256": digest})
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if begin + 128 >= 512:
            formal = formal_acceptance(manifest_path)
            (output / ("formal-assessment-%04d.json" % (begin + 128))).write_text(
                json.dumps(formal, indent=2), encoding="utf-8")
            accepted = formal["formal_acceptance"]["all_formal_gates"]
            print("FORMAL_ASSESSMENT", begin + 128, "all_formal_gates", accepted, flush=True)
            if accepted:
                print("FORMAL_ACCEPTED", begin + 128, "manifest", str(manifest_path), flush=True)
                return
        resume = str(Path(result["metadata"]["checkpoint_end_path"]).parent)
        del result
    print("TARGET_REACHED", target_step, "elapsed_s", round(time.perf_counter() - started, 3),
          "manifest", str(manifest_path), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "verification/fluvial-delta/morphodynamics-20261015-01")
    parser.add_argument("--target-step", type=int, default=512)
    parser.add_argument("--mechanism-transition", type=Path)
    parser.add_argument("--resume-chain", type=Path)
    parser.add_argument("--gravity-stability", action="store_true")
    parser.add_argument("--routing-dry-depth-m", type=float)
    parser.add_argument("--quantized-native-exchange", action="store_true")
    parser.add_argument("--water-routing-repair", action="store_true")
    arguments = parser.parse_args()
    run(arguments.output, arguments.target_step, arguments.mechanism_transition,
        arguments.resume_chain, arguments.gravity_stability, arguments.routing_dry_depth_m,
        arguments.quantized_native_exchange, arguments.water_routing_repair)
