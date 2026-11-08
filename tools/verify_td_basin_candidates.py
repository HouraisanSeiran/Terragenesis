"""Pinned real TD geometry candidates and serialized diagnostic recoupling."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_storage import load_td_source_bundle as load_td_source_bundle
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import load_basin_storage as load_basin_storage
from terrain_pipeline.geology import load_material_field
from terrain_pipeline.basin_topology import run_candidate_coupling as run_candidate_coupling


EXECUTION_SOURCE = ROOT / 'terrain_pipeline/basin_storage.py'


def execution_code_manifest(*, output_path=None):
    """Describe the actual refinement kernel without importing or compiling it."""
    import hashlib
    import platform
    import sys
    from importlib.metadata import version

    source = EXECUTION_SOURCE.read_bytes()
    manifest = {
        "schema": "td-basin-execution-code-v1",
        "execution_source": {
            "path": 'terrain_pipeline/basin_storage.py',
            "sha256": hashlib.sha256(source).hexdigest(),
            "source_utf8": source.decode("utf-8"),
        },
        "profile": {
            "name": "v2-full-refinement-6e9-v1",
            "algorithm": "D4-analytic-face-Strang-splitting-v2",
            "max_work_face_steps": 6000000000,
            "substep_budget_is_independent_of_legacy_v1": True,
        },
        "runtime": {
            "python": platform.python_version(),
            "numba": version("numba"),
            "numpy": version("numpy"),
            "platform": platform.platform(),
        },
        "cold_read": {
            "requires": [
                "numpy",
                "terrain_pipeline.td_basin_storage_refinement.py",
                "numba (only for execution, not for read-only validation)",
            ],
            "validator_mode": "read JSON/NPZ metadata and SHA only; never import refinement or call simulate",
            "jit_on_cold_read": False,
            "advancement_on_cold_read": False,
        },
    }
    if output_path is not None:
        output_path = Path(output_path)
        publish_bytes(output_path, json.dumps(manifest, ensure_ascii=False, indent=2,
                                               allow_nan=False).encode("utf-8"))
    return manifest


def compare_storage(coarse_record, fine_record):
    import numpy as np
    coarse = load_basin_storage(**coarse_record)
    fine = load_basin_storage(**fine_record)
    for key in ("height_m", "valid_mask", "face_cells", "receiver", "boundary_cells", "rain_mm_h"):
        if not np.array_equal(coarse["arrays"][key], fine["arrays"][key]):
            raise ValueError("sensitivity comparison geometry/forcing mismatch")
    if coarse["metadata"]["hierarchy_identity_sha256"] != fine["metadata"]["hierarchy_identity_sha256"]:
        raise ValueError("sensitivity topology mismatch")
    head_error = float(abs(coarse["arrays"]["depth_m"] - fine["arrays"]["depth_m"]).max())
    receiver_error = float(abs(coarse["arrays"]["routed_volume_m3"] - fine["arrays"]["routed_volume_m3"]).sum()
        / max(1e-12, fine["arrays"]["routed_volume_m3"].sum()))
    return {"max_saved_depth_difference_m": head_error, "receiver_volume_relative_l1": receiver_error,
        "gate_passed": head_error <= 0.001 and receiver_error <= 0.01,
        "coarse": coarse_record, "fine": fine_record, "scope": "entire saved calculation domain"}


def verify(inputs_path, destination, *, inputs_sha256):
    inputs_path = Path(inputs_path).resolve()
    if file_sha256(inputs_path) != inputs_sha256:
        raise ValueError("external candidate input index SHA mismatch")
    records = json.loads(inputs_path.read_text(encoding="utf-8"))
    proof = records.get("numerical_proof")
    full_passed = False
    if proof is not None:
        if file_sha256(proof["path"]) != proof["expected_sha256"]:
            raise ValueError("external numerical proof SHA mismatch")
        proof_data = json.loads(Path(proof["path"]).read_text(encoding="utf-8"))
        full_passed = proof_data.get("scope") == "entire baseline calculation domain" and all(
            proof_data["comparisons"][scenario]["gate_passed"] for scenario in ("ordinary", "strong"))
    if records.get("baseline_full_sensitivity_passed", False) != full_passed:
        raise ValueError("baseline sensitivity claim must match externally pinned full-domain proof")
    loaders = {"source": load_td_source_bundle, "hierarchy": load_basin_hierarchy,
        "material": load_material_field, "ordinary": load_basin_storage, "strong": load_basin_storage}
    if set(records["inputs"]) != set(loaders):
        raise ValueError("exact source/hierarchy/material/ordinary/strong external pins required")
    before = {role: file_sha256(record["path"]) for role, record in records["inputs"].items()}
    loaded = {role: loaders[role](**record) for role, record in records["inputs"].items()}
    result = run_candidate_coupling(loaded["source"], loaded["hierarchy"], loaded["material"], loaded["ordinary"], loaded["strong"],
        destination, numerical_sensitivity_passed=full_passed,
        refine_candidates=records.get("refine_candidates", False))
    execution = execution_code_manifest(output_path=Path(destination) / "execution-code.json")
    for candidate in result["candidates"]:
        candidate["execution_code"] = {
            "path": "execution-code.json",
            "source_sha256": execution["execution_source"]["sha256"],
            "profile": execution["profile"]["name"],
            "numba": execution["runtime"]["numba"],
        }
    after = {role: file_sha256(record["path"]) for role, record in records["inputs"].items()}
    if before != after:
        raise ValueError("candidate source inputs changed")
    publish_bytes(Path(destination) / "baseline-inputs.json", json.dumps(records, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    report = {"inputs": records, "input_index_sha256": inputs_sha256, "input_hashes_unchanged": True, "selected": result["selected_candidate_id"],
        "code_sha256": {name: file_sha256(ROOT / name) for name in ('terrain_pipeline/basin_topology.py',
            'terrain_pipeline/basin_storage.py', 'terrain_pipeline/basin_storage.py',
            'terrain_pipeline/basin_storage.py', "tools/verify_td_basin_candidates.py")},
        "execution_code": execution,
        "numerical_scope": "baseline covered-subtree sensitivity only; candidates require their own sensitivity; no auto adoption",
        "candidate_counts": len(result["candidates"]), "changed_candidates": sum(value.get("changed_cells", 0) > 0 for value in result["candidates"])}
    publish_bytes(Path(destination) / "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps({"output": str(Path(destination).resolve()), "selected": report["selected"], "candidate_counts": report["candidate_counts"]}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--inputs-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    destination = args.output or ROOT / "verification/td-basin-generation" / ("A-candidates-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    verify(args.inputs, destination, inputs_sha256=args.inputs_sha256)
