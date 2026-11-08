"""Prepare a bounded branched shared-midpoint fragment without solver or fine cells."""

import argparse
import gc
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256
from terrain_pipeline.td_shared_port_channel import (
    FLAGS, MAX_BYTES, MAX_FACES, MAX_NODES, MAX_NODES_HARD, MAX_RSS,
    PARAMETERS, POLICY_IDENTITY_SHA256, FragmentComposer, build_midpoint_port,
    build_node_piece, select_fragment, seal)
from terrain_pipeline.td_ported_network_composition import check_memory
from tools.prepare_td_ported_junction import INPUTS, FROZEN_HELPERS, VERIFICATION
from tools.prepare_td_ported_network_composition import FROZEN_JUNCTION, _parents, _pin, _save

SCHEMA = "td-shared-port-channel-preparation-v1"
FROZEN_COMPOSITION = {
    "terrain_pipeline/td_ported_network_composition.py": "b4db872c525aa65a186afb25857fc7edd7cf725a8a37f4f90c48c643227c9165",
    "tools/prepare_td_ported_network_composition.py": "a6182f7f1e15e5b9ef866c5def5b11f3ea2940706900347f81cf77f553bd1df3",
    "tests/test_td_ported_network_composition.py": "08ecf11221ccbee91c33d54d7ca9240f7f43a73008782f3d0d47213f0646083e",
}
CODE_FILES = ("terrain_pipeline/td_shared_port_channel.py", "tools/prepare_td_shared_port_channel.py",
    "tests/test_td_shared_port_channel.py")


def _read_local(pin, output, staging):
    published = Path(pin["path"])
    relative = published.relative_to(output)
    saved = staging / relative
    if saved.stat().st_size > MAX_BYTES or file_sha256(saved) != pin["sha256"]:
        raise ValueError("local port pin or size changed")
    return json.loads(saved.read_bytes())


def prepare(output, *, max_nodes=MAX_NODES):
    output = Path(output).resolve()
    if output.exists() or output == VERIFICATION.resolve() or not output.is_relative_to(VERIFICATION.resolve()):
        raise ValueError("new verification subdirectory required")
    staging = output.with_name(output.name + ".partial")
    if staging.exists():
        raise ValueError("staging exists; inspect incomplete preparation before retry")
    frozen = {**FROZEN_HELPERS, **FROZEN_JUNCTION, **FROZEN_COMPOSITION}
    for name, expected in frozen.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("frozen readonly helper changed: " + name)
    started = time.perf_counter()
    hierarchy, paths, sections, wet = _parents()
    graph, selection = select_fragment(hierarchy, paths, sections, wet_protection=wet, max_nodes=max_nodes)
    staging.mkdir(parents=True)
    index = {"schema": SCHEMA, "status": "candidate_unverified", "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "inputs": INPUTS, "parameters": PARAMETERS,
        "code_sha256": {name: file_sha256(ROOT / name) for name in CODE_FILES + tuple(frozen)},
        "independent_audit_passed": False, **{flag: False for flag in FLAGS}}
    for key, record in (("graph", graph), ("selection", selection)):
        _save(record, staging / (key + ".json"))
        index[key] = _pin(staging / (key + ".json"), output / (key + ".json"), record)
    port_rows = []
    for ordinal, arc_id in enumerate(selection["selected_arc_ids"]):
        record = build_midpoint_port(hierarchy, paths, sections, arc_id=arc_id,
            wet_protection=wet, input_pins=INPUTS)
        relative = Path("ports") / (str(ordinal).zfill(4) + ".json")
        _save(record, staging / relative)
        port_rows.append({"arc_id": arc_id, "node_ids": record["node_ids"], "status": record["status"],
            "rejection_reasons": record["rejection_reasons"],
            "pin": _pin(staging / relative, output / relative, record)})
        del record
        gc.collect()
    by_node = {node_id: [] for node_id in selection["selected_node_ids"]}
    for row in port_rows:
        for node_id in row["node_ids"]:
            by_node[node_id].append(row)
    composer = FragmentComposer(paths, sections, selection)
    peak = check_memory()
    clipping = selection["boundary_arc_clipping"]
    for ordinal, node_id in enumerate(selection["selected_node_ids"]):
        local_ports = [_read_local(row["pin"], output, staging) for row in by_node[node_id]]
        record = build_node_piece(hierarchy, paths, sections, node_id=node_id, midpoint_ports=local_ports,
            wet_protection=wet, input_pins=INPUTS,
            clipping_evidence=[row for row in clipping if node_id in row["node_ids"]])
        relative = Path("nodes") / (str(ordinal).zfill(4) + ".json")
        _save(record, staging / relative)
        pin = _pin(staging / relative, output / relative, record)
        row = composer.add_node(record, pin)
        print(json.dumps({"ordinal": ordinal, "node_id": node_id,
            "generation_status": row["generation_status"], "composition_status": row["composition_status"]}), flush=True)
        peak = max(peak, check_memory())
        del record, local_ports
        gc.collect()
    bundle = composer.finish(port_rows, INPUTS)
    for key, record in bundle.items():
        _save(record, staging / (key + ".json"))
        index[key] = _pin(staging / (key + ".json"), output / (key + ".json"), record)
    index["summary"] = {"original_land_arcs": graph["original_land_arc_count"],
        "attempted_nodes": len(selection["selected_node_ids"]), "attempted_arcs": len(port_rows),
        "selected_nodes": len(bundle["manifest"]["selected_node_ids"]),
        "joined_arcs": bundle["topology"]["joined_arc_count"],
        "component_count": bundle["topology"]["component_count"],
        "longest_directed_path_m": bundle["topology"]["longest_directed_path"]["plan_length_m"],
        "branch_nodes": len(bundle["topology"]["branch_node_ids"]), "mesh_faces": len(bundle["mesh"]["triangles"])}
    index["resource"] = {"actual_peak_rss_bytes": max(peak, check_memory()), "max_rss_bytes": MAX_RSS,
        "max_json_bytes": MAX_BYTES, "max_nodes": max_nodes, "hard_max_nodes": MAX_NODES_HARD,
        "max_faces": MAX_FACES, "elapsed_s": time.perf_counter() - started,
        "raw_retention": "one_node_and_at_most_four_ports_then_release_raw_functions",
        "solver_calls": 0, "fine_cells_generated": 0, "old_packages_modified": False}
    _save(seal(index), staging / "index.json")
    staging.rename(output)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-nodes", type=int, default=MAX_NODES)
    args = parser.parse_args()
    index = prepare(args.output, max_nodes=args.max_nodes)
    print(json.dumps({"status": index["status"], "summary": index["summary"], "resource": index["resource"]}, sort_keys=True))


if __name__ == "__main__":
    main()
