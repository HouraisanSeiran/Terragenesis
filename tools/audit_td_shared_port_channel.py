"""Cold independent audit of bounded shared-midpoint saved channel geometry."""

import argparse
import gc
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_fine_bed_shards import read, check_memory
from tools.audit_td_source_conforming_banks_v3 import require
from tools.audit_td_ported_network_composition_v3 import parent_inputs
from tools.td_shared_port_channel_saved_audit import (
    FLAGS, POLICY, POLICY_SHA256, PARAMETERS, check_identity, independent_selection,
    audit_midpoint, audit_node, FragmentAudit, compare, face_components)

AUDIT_SCHEMA = "td-shared-port-channel-independent-audit-v1"
FROZEN_CODE = {
    "terrain_pipeline/td_shared_port_channel.py": "fa44c986240480975934c494aa02443d81fc063c18634d9fa65bd47909aadcc8",
    "tools/prepare_td_shared_port_channel.py": "bc6e116bf31d358c3af075df3592bf0a6f359d5f01a8b87ced1c2cccf19ae9b2",
    "tests/test_td_shared_port_channel.py": "831683a43dc50f3ee93e7ce62e359e31d320b6881075e3d75dd53c5c759fc586",
}


def pin_binding(pin):
    path = Path(pin["path"]).resolve(strict=True)
    require(pin["bytes"] == path.stat().st_size <= 64*1024**2, "saved channel pin byte count differs")
    return {key: pin[key] for key in ("path", "sha256", "identity_sha256")}


def audit(index):
    check_identity(index)
    require(index["schema"] == "td-shared-port-channel-preparation-v1" and index["status"] == "candidate_unverified"
            and index["policy_identity_sha256"] == POLICY_SHA256 and index["parameters"] == PARAMETERS,
            "shared preparation schema/policy/parameters differ")
    require(index["independent_audit_passed"] is False, "preparation inherited audit acceptance")
    for flag in FLAGS:
        require(index[flag] is False, "preparation promoted capability")
    resource = index["resource"]
    require(2 <= resource["max_nodes"] <= 128 and resource["max_nodes"] <= resource["hard_max_nodes"] <= 256
            and resource["max_faces"] <= 20000 and 0 < resource["max_json_bytes"] <= 64*1024**2
            and 0 <= resource["actual_peak_rss_bytes"] <= resource["max_rss_bytes"] <= 1024**3
            and resource["solver_calls"] == resource["fine_cells_generated"] == 0
            and resource["old_packages_modified"] is False, "channel preparation resource/scope differs")
    for name, sha in FROZEN_CODE.items():
        require(index["code_sha256"].get(name) == sha and file_sha256(ROOT/name) == sha, "frozen shared generator pin differs: "+name)
    for name, sha in index["code_sha256"].items():
        path = (ROOT/name).resolve()
        require(path.is_relative_to(ROOT) and file_sha256(path) == sha, "saved readonly code pin differs")
    pins = index["inputs"]
    paths, sections, hierarchy, protection = parent_inputs(pins)
    for parent in (paths, sections):
        require(parent["hierarchy_identity_sha256"] == hierarchy["identity_sha256"]
                and parent["source_identity_sha256"] == hierarchy["metadata"]["source_identity_sha256"], "original native source identity differs")
    require(paths["ordinary_identity_sha256"] == sections["ordinary_identity_sha256"], "original ordinary discharge identity differs")
    artifacts = {}
    for key in ("graph", "selection", "manifest", "mesh", "topology"):
        pin_binding(index[key])
        artifacts[key] = read(index[key])
        check_identity(artifacts[key])
    graph, selection, manifest = artifacts["graph"], artifacts["selection"], artifacts["manifest"]
    expected_graph, expected_selection = independent_selection(hierarchy, paths, sections, protection, resource["max_nodes"])
    compare(graph, expected_graph, "complete original land graph")
    compare(selection, expected_selection, "independent bounded longest-chain/branch safety selection")
    require(len(selection["selected_node_ids"]) <= resource["max_nodes"], "selection exceeds bounded nodes")
    require(manifest["schema"] == "td-shared-port-channel-v1" and manifest["policy"] == POLICY
            and manifest["policy_identity_sha256"] == POLICY_SHA256 and manifest["parameters"] == PARAMETERS
            and manifest["inputs"] == pins, "manifest policy/original input pins differ")
    require([row["arc_id"] for row in manifest["ports"]] == selection["selected_arc_ids"]
            and [row["node_id"] for row in manifest["nodes"]] == selection["selected_node_ids"], "manifest omitted/duplicated node or canonical arc port")
    port_bindings, node_bindings, summaries = {}, {}, []
    port_rows = {row["arc_id"]: row for row in manifest["ports"]}
    for row in manifest["ports"]:
        binding = pin_binding(row["pin"])
        record = read(row["pin"])
        require(row["arc_id"] == record["arc_id"] and row["node_ids"] == record["node_ids"]
                and row["status"] == record["status"] and row["rejection_reasons"] == record["rejection_reasons"], "canonical port row/record binding differs")
        audit_midpoint(record, paths, sections, hierarchy, protection, pins)
        port_bindings[str(row["arc_id"])] = binding
        del record
        gc.collect()
    composer = FragmentAudit()
    peak = check_memory()
    for ordinal, row in enumerate(manifest["nodes"]):
        node_bindings[str(row["node_id"])] = pin_binding(row["pin"])
        record = read(row["pin"])
        require(record["node_id"] == row["node_id"], "node pin identifies a different original node")
        local = [read(port_rows[arc]["pin"]) for arc in selection["selected_arc_ids"] if row["node_id"] in port_rows[arc]["node_ids"]]
        require(len(local) <= 4 or record["status"] == "refused", "unbounded accepted node port retention")
        clipping = [entry for entry in selection["boundary_arc_clipping"] if row["node_id"] in entry["node_ids"]]
        result, descriptors = audit_node(record, local, paths, sections, hierarchy, protection, pins, clipping)
        expected_row = composer.consider(record, row["pin"], descriptors)
        compare(row, expected_row, "independent atomic composition node selection")
        summaries.append(result)
        print(json.dumps(dict(ordinal=ordinal, node_id=row["node_id"], generation_status=result["generation_status"],
                              composition_status=expected_row["composition_status"])), flush=True)
        peak = max(peak, check_memory())
        del record, local, descriptors, result
        gc.collect()
    expected_manifest, expected_topology = composer.finish(paths, sections, selection, manifest["ports"], pins)
    compare({key: value for key, value in manifest.items() if key != "identity_sha256"}, expected_manifest, "whole saved fragment manifest/seams/replacement ledger")
    require({key: value for key, value in artifacts["mesh"].items() if key != "identity_sha256"} == composer.mesh,
            "fragment mesh differs from exact selected node faces or includes old06 mesh")
    require(len(composer.mesh["triangles"]) <= resource["max_faces"]
            and len(face_components(composer.mesh)) == expected_topology["component_count"],
            "global actual triangle components/nonmanifold or face budget differs from verified port graph")
    compare({key: value for key, value in artifacts["topology"].items() if key != "identity_sha256"}, expected_topology,
            "actual complete-boundary graph components/longest chain/branches/open ends")
    expected_summary = dict(original_land_arcs=graph["original_land_arc_count"], attempted_nodes=len(selection["selected_node_ids"]),
        attempted_arcs=len(manifest["ports"]), selected_nodes=len(expected_manifest["selected_node_ids"]),
        joined_arcs=expected_topology["joined_arc_count"], component_count=expected_topology["component_count"],
        longest_directed_path_m=expected_topology["longest_directed_path"]["plan_length_m"],
        branch_nodes=len(expected_topology["branch_node_ids"]), mesh_faces=len(composer.mesh["triangles"]))
    compare(index["summary"], expected_summary, "index geometry-evidenced metrics")
    return dict(schema=AUDIT_SCHEMA, status="passed", errors=[], policy_identity_sha256=POLICY_SHA256,
        inputs=pins, selected_node_ids=expected_manifest["selected_node_ids"], nodes=node_bindings, ports=port_bindings,
        manifest_identity_sha256=manifest["identity_sha256"], node_audits=summaries, summary=expected_summary,
        selected_source_native_functions_verified=bool(expected_manifest["selected_node_ids"]),
        complete_actual_reverse_midpoint_functions_verified=True, original_source_and_discharge_unchanged=True,
        old06_replacement_ledger_verified=True, no_old06_mesh_overlay=True, no_node_id_only_connections=True,
        components=expected_topology["components"], longest_directed_path=expected_topology["longest_directed_path"],
        branch_node_ids=expected_topology["branch_node_ids"], branch_arc_ids=expected_topology["branch_arc_ids"],
        other_component_arc_ids=expected_topology["other_component_arc_ids"], open_ports=expected_topology["open_ports"],
        terminal_open_ports=expected_topology["terminal_open_ports"], external_closure_verified=False,
        geometric_boundary_conditions_only=True, actual_peak_audit_rss_bytes=max(peak, check_memory()),
        scope="bounded derived source-minus-cut fragment and saved replacement candidate ledger; open geometry ports are not hydraulic BCs",
        **{flag: False for flag in FLAGS},
        **{key+"_sha256": index[key]["sha256"] for key in ("graph", "selection", "manifest", "mesh", "topology")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-schema", choices=[AUDIT_SCHEMA], default=AUDIT_SCHEMA)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT/"verification/natural-river-network"), "new channel verification output required")
    result = audit(read(dict(path=str(args.input.resolve()), sha256=args.sha256)))
    result.update(index_sha256=args.sha256, audit_code_sha256={name: file_sha256(ROOT/name) for name in (
        "tools/audit_td_shared_port_channel.py", "tools/td_shared_port_channel_saved_audit.py",
        "tools/audit_td_ported_network_composition_v3.py", "tools/td_ported_network_saved_audit.py",
        "tools/audit_td_ported_junction_v3.py", "tools/td_ported_junction_saved_audit_v3.py",
        "tools/td_ported_junction_saved_audit_v2.py", "tools/audit_td_source_conforming_banks_v3.py",
        "tools/td_source_conforming_saved_audit.py", "tools/td_source_conforming_saved_audit_v3.py",
        "tools/audit_td_fine_bed_shards.py", "tools/audit_td_fine_bed_raster.py")})
    publish_bytes(output, (json.dumps(result, sort_keys=True, allow_nan=False, indent=2)+"\n").encode())
    print(json.dumps({key: result[key] for key in ("schema", "status", "summary", "full_network_verified", "actual_peak_audit_rss_bytes")}))


if __name__ == "__main__":
    main()
