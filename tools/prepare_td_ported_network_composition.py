"""Save all bounded three-arm hub attempts and a candidate display composition."""

import argparse
import gc
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_ported_junction import build_ported_junction, save_ported_junction
from terrain_pipeline.td_ported_network_composition import (
    MAX_BYTES, MAX_HUBS, MAX_RSS, POLICY_IDENTITY_SHA256, NetworkComposer, census_hubs, check_memory)
from terrain_pipeline import channel_geometry as geometry
from tools.prepare_td_ported_junction import INPUTS, FROZEN_HELPERS, VERIFICATION, _read

SCHEMA = "td-ported-network-composition-preparation-v1"
FROZEN_JUNCTION = {
    "terrain_pipeline/td_ported_junction.py": "7ff3d0d6ebbe7ac65aac16045d905c248d0e7768148303d998540c351a146eb5",
    "tools/prepare_td_ported_junction.py": "7cb7d67b6bdefdd06134bda55b3c0e95d436a00a29ce68cff16bba45cce0dba5",
    "tests/test_td_ported_junction.py": "c3603653e4c715241e0a691a2dea0997b692fbe446fbdac599de3061b73dc03e",
}
CODE_FILES = ("terrain_pipeline/td_ported_network_composition.py",
    "tools/prepare_td_ported_network_composition.py", "tests/test_td_ported_network_composition.py")


def _save(record, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.partial")
    written = 0
    with temporary.open("xb") as stream:
        for fragment in geometry._json_fragments(record):
            written += len(fragment)
            if written > MAX_BYTES:
                raise MemoryError("composition artifact exceeds 64MiB: " + path.name)
            stream.write(fragment)
        stream.flush()
    temporary.rename(path)
    check_memory()


def _pin(saved_path, published_path, record):
    return {"path": str(published_path), "sha256": file_sha256(saved_path),
        "bytes": saved_path.stat().st_size, "identity_sha256": record["identity_sha256"]}


def _parents():
    paths, sections = _read(INPUTS["06_paths"]), _read(INPUTS["06_sections"])
    old_index = _read(INPUTS["06_index"])
    source_index = _read(INPUTS["source_bank_parent_index"])
    audit = _read(INPUTS["source_bank_parent_audit"])
    wet = _read(INPUTS["wet_protection_manifest"])
    if (old_index["paths"]["sha256"] != INPUTS["06_paths"]["sha256"]
            or old_index["sections"]["sha256"] != INPUTS["06_sections"]["sha256"]
            or audit["status"] != "passed"
            or audit["index_sha256"] != INPUTS["source_bank_parent_index"]["sha256"]
            or audit["manifest_sha256"] != INPUTS["wet_protection_manifest"]["sha256"]
            or source_index["manifest"]["sha256"] != INPUTS["wet_protection_manifest"]["sha256"]
            or wet["paths_identity_sha256"] != paths["identity_sha256"]
            or wet["sections_identity_sha256"] != sections["identity_sha256"]):
        raise ValueError("immutable 06/source/wet parent chain mismatch")
    pin = INPUTS["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(pin["path"]),
        expected_sha256=pin["sha256"], expected_identity=pin["identity_sha256"])
    if wet["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
        raise ValueError("wet hierarchy identity mismatch")
    return hierarchy, paths, sections, wet["wet_protection"]


def prepare(output):
    output = Path(output).resolve()
    if output.exists() or output == VERIFICATION.resolve() or not output.is_relative_to(VERIFICATION.resolve()):
        raise ValueError("new verification subdirectory required")
    staging = output.with_name(output.name + ".partial")
    if staging.exists():
        raise ValueError("staging exists; inspect previous incomplete preparation before retry")
    started = time.perf_counter()
    for name, expected in {**FROZEN_HELPERS, **FROZEN_JUNCTION}.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("frozen readonly code pin mismatch: " + name)
    hierarchy, paths, sections, wet = _parents()
    census = census_hubs(paths, sections)
    composer = NetworkComposer(paths, sections)
    staging.mkdir(parents=True)
    census_record = geometry._seal({"schema": "td-ported-network-census-v1",
        "policy_identity_sha256": POLICY_IDENTITY_SHA256, "inputs": INPUTS,
        "all_actual_three_arm_hubs": True, "max_hubs": MAX_HUBS, "hub_count": len(census), "hubs": census})
    _save(census_record, staging / "census.json")
    peak_rss = check_memory()
    for ordinal, entry in enumerate(census):
        relative = Path("junctions") / (str(ordinal).zfill(3) + "-" + entry["hub_node_id"].replace(":", "-"))
        record = build_ported_junction(hierarchy, paths, sections,
            hub_node_id=entry["hub_node_id"], incident_arc_ids=entry["incident_arc_ids"],
            wet_protection=wet, input_pins=INPUTS)
        save_ported_junction(record, staging / relative)
        pin = _pin(staging / relative / "junction.json", output / relative / "junction.json", record)
        row = composer.add_junction(record, pin, entry)
        peak_rss = max(peak_rss, check_memory())
        print(json.dumps({"ordinal": ordinal, "hub_node_id": entry["hub_node_id"],
            "generation_status": row["generation_status"], "composition_status": row["composition_status"]}), flush=True)
        del record
        gc.collect()
    bundle = composer.finish()
    bundle["manifest"]["inputs"] = INPUTS
    bundle["manifest"].pop("identity_sha256")
    geometry._seal(bundle["manifest"])
    index = {"schema": SCHEMA, "status": "candidate_unverified", "inputs": INPUTS,
        "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "census": _pin(staging / "census.json", output / "census.json", census_record),
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES + tuple(FROZEN_HELPERS) + tuple(FROZEN_JUNCTION)},
        "hub_count": len(census), "generation_candidate_count": sum(row["generation_status"] == "candidate" for row in composer.hubs),
        "composition_selected_count": sum(row["composition_status"] == "selected" for row in composer.hubs),
        "metrics_status": "candidate_unverified", "independent_audit_passed": False, "full_network_verified": False,
        "fine_generated": False, "hydraulic_ready": False, "material_budget_verified": False}
    for key, record in bundle.items():
        _save(record, staging / (key + ".json"))
        index[key] = _pin(staging / (key + ".json"), output / (key + ".json"), record)
    index["resource"] = {"actual_peak_rss_bytes": max(peak_rss, check_memory()), "max_rss_bytes": MAX_RSS,
        "max_json_bytes": MAX_BYTES, "max_hubs": MAX_HUBS, "elapsed_s": time.perf_counter() - started,
        "solver_calls": 0, "fine_cells_generated": 0, "old_packages_modified": False,
        "raw_retention": "one_junction_at_a_time_then_only_geometry_and_outer_port_coefficients"}
    _save(geometry._seal(index), staging / "index.json")
    staging.rename(output)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index = prepare(args.output)
    print(json.dumps({key: index[key] for key in ("status", "hub_count",
        "generation_candidate_count", "composition_selected_count", "resource")}, sort_keys=True))


if __name__ == "__main__":
    main()
