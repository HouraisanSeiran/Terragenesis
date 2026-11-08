"""Independent physical-face, LCA, storage and reach-join audit of a pinned spill bundle."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record
from tools.audit_td_surface_reaches import read_json, identity


def iter_faces(network, bundle_path):
    if "spills" in network:
        yield from network["spills"]
        return
    for number, chunk in enumerate(network["face_chunks"]):
        if chunk["file"] != f"faces-{number:04d}.json" or not 1 <= chunk["face_count"] <= 2048:
            raise ValueError("invalid chunk path/count")
        path = Path(bundle_path).parent / chunk["file"]
        if path.stat().st_size != chunk["bytes"] or chunk["bytes"] > 4 * 1024 * 1024:
            raise ValueError("chunk byte budget mismatch")
        records = read_json(path, chunk["expected_sha256"])
        import hashlib
        digest = hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if digest != chunk["identity_sha256"] or len(records) != chunk["face_count"]:
            raise ValueError("chunk identity/count mismatch")
        yield from records


def audit(index_path, index_sha256):
    index = read_json(index_path, index_sha256)
    topology, metadata = read_record(index["inputs"]["hierarchy"])
    water, water_metadata = read_record(index["inputs"]["storage"])
    pin = index["spills"]
    network = read_json(pin["path"], pin["expected_sha256"])
    if identity(network) != pin["expected_identity"] or network["identity_sha256"] != pin["expected_identity"]:
        raise ValueError("spill identity mismatch")
    faces = topology["face_cells"]
    owners = topology["cell_owner"].ravel()
    parent = topology["node_parent"]
    bed = topology["height_m"].ravel()
    protected = topology["protected_mask"].ravel()
    columns = topology["height_m"].shape[1]
    spacing = metadata["spacing_m"]
    origin = metadata["origin_m_xz"]
    expected_faces = set(map(int, np.flatnonzero(owners[faces[:, 0]] != owners[faces[:, 1]])))
    seen = set()
    ids = set()
    incident = {}
    saddle_faces = 0
    transfer_faces = 0
    rejected = 0
    basin_nodes = {record["node_id"]: record for record in network["basin_nodes"]}
    pair_minimum = {}
    for face in expected_faces:
        first, second = faces[face]
        allowed = not protected[[first, second]].any() and not topology["node_unknown_contact"][owners[[first, second]]].any()
        if allowed:
            pair = tuple(sorted(map(int, owners[[first, second]])))
            pair_minimum[pair] = min(pair_minimum.get(pair, float("inf")), float(max(bed[first], bed[second])))
    for record in iter_faces(network, pin["path"]):
        face = record["face_index"]
        if face in seen or record["face_id"] in ids:
            raise ValueError("duplicate physical face")
        seen.add(face)
        ids.add(record["face_id"])
        first, second = map(int, faces[face])
        if record["face_cell_ids"] != [first, second] or record["owner_ids"] != [int(owners[first]), int(owners[second])]:
            raise ValueError("face ownership mismatch")
        first_chain = set()
        cursor = int(owners[first])
        while cursor >= 0:
            first_chain.add(cursor)
            cursor = int(parent[cursor])
        cursor = int(owners[second])
        while cursor >= 0 and cursor not in first_chain:
            cursor = int(parent[cursor])
        if cursor != record["merge_node_id"] or cursor != int(topology["face_merge_node"][face]):
            raise ValueError("independent LCA mismatch")
        sill = float(max(bed[first], bed[second]))
        if sill != record["face_sill_m"] or sill != topology["face_level_m"][face]:
            raise ValueError("physical sill mismatch")
        saddle_faces += cursor >= 0 and sill == topology["node_birth_m"][cursor]
        allowed = not protected[[first, second]].any() and not topology["node_unknown_contact"][owners[[first, second]]].any() and cursor >= 0
        if bool(record["potential_connection_allowed"]) != allowed:
            raise ValueError("barrier allowance mismatch")
        lowest = allowed and sill == pair_minimum[tuple(sorted(map(int, owners[[first, second]])))]
        if record["lowest_allowed_owner_pair_face"] != lowest:
            raise ValueError("lowest owner-pair face mismatch")
        rejected += not allowed
        xyz = [[origin[0] + cell % columns * spacing, bed[cell], origin[1] + cell // columns * spacing] for cell in (first, second)]
        np.testing.assert_array_equal(record["xyz_m"], xyz)
        flux = record["stored_whole_run_flux"]
        forward = float(water["face_forward_m3"][face])
        reverse = float(water["face_reverse_m3"][face])
        for key, expected in (("forward_m3", forward), ("reverse_m3", reverse), ("gross_m3", forward + reverse),
                              ("net_first_to_second_m3", forward - reverse)):
            if flux[key] != expected:
                raise ValueError("directional face ledger mismatch")
        transfer_faces += forward + reverse > 0
        for owner in (int(owners[first]), int(owners[second])):
            incident.setdefault(owner, set()).add(record["face_id"])
        for owner, recorded_branch in zip(map(int, owners[[first, second]]), record["merge_child_ids"]):
            branch = None
            cursor_child = owner
            while cursor_child >= 0 and cursor_child != cursor:
                if parent[cursor_child] == cursor:
                    branch = cursor_child
                    break
                cursor_child = int(parent[cursor_child])
            if recorded_branch != branch:
                raise ValueError("merge child mismatch")
            if branch is not None:
                stage = basin_nodes[branch]
                if stage["upper_m"] != topology["node_upper_m"][branch] or stage["stage_capacity_m3"] != topology["stage_capacity_m3"][branch]:
                    raise ValueError("branch stage evidence mismatch")
    if seen != expected_faces:
        raise ValueError("cross-owner face coverage mismatch")
    leaf_graph = network.get("contribution_leaf_graph")
    leaf_faces_checked = 0
    pair_count = 0
    if leaf_graph is not None:
        leaves = topology["contribution_owner"].ravel()
        cross_leaf = set(map(int, np.flatnonzero(leaves[faces[:, 0]] != leaves[faces[:, 1]])))
        leaf_seen = set()
        pair_seen = set()
        leaf_divergence = np.zeros(len(parent))
        for pair in leaf_graph["pairs"]:
            leaf_pair = tuple(pair["leaf_ids"])
            if leaf_pair in pair_seen or leaf_pair[0] >= leaf_pair[1]:
                raise ValueError("duplicate or unordered leaf pair")
            pair_seen.add(leaf_pair)
            forward, reverse = 0., 0.
            minimum = float("inf")
            minimum_faces = []
            rejected_faces = []
            for face in pair["all_face_indices"]:
                if face in leaf_seen:
                    raise ValueError("repeated cross-leaf face")
                leaf_seen.add(face)
                first, second = faces[face]
                if tuple(sorted(map(int, leaves[[first, second]]))) != leaf_pair:
                    raise ValueError("exclusive catchment pair mismatch")
                allowed = not protected[[first, second]].any() and not topology["node_unknown_contact"][leaves[[first, second]]].any()
                sill = max(bed[first], bed[second])
                if not allowed:
                    rejected_faces.append(face)
                elif sill < minimum:
                    minimum, minimum_faces = sill, [face]
                elif sill == minimum:
                    minimum_faces.append(face)
                face_forward = water["face_forward_m3"][face]
                face_reverse = water["face_reverse_m3"][face]
                along, against = (face_forward, face_reverse) if leaves[first] == leaf_pair[0] else (face_reverse, face_forward)
                forward += along
                reverse += against
            if pair["minimum_face_indices"] != minimum_faces or pair["rejected_face_indices"] != rejected_faces:
                raise ValueError("leaf-pair minimum/barrier mismatch")
            if pair["minimum_physical_sill_m"] != (float(minimum) if minimum_faces else None):
                raise ValueError("leaf minimum sill mismatch")
            for key, expected in (("forward_leaf0_to_leaf1_m3", forward), ("reverse_leaf1_to_leaf0_m3", reverse),
                                  ("gross_m3", forward + reverse), ("net_leaf0_to_leaf1_m3", forward - reverse)):
                if not np.isclose(pair[key], expected, rtol=1e-13, atol=1e-10):
                    raise ValueError("exclusive catchment crossing ledger mismatch")
            leaf_divergence[leaf_pair[0]] -= forward - reverse
            leaf_divergence[leaf_pair[1]] += forward - reverse
        if leaf_seen != cross_leaf:
            raise ValueError("exclusive leaf graph lost faces")
        valid = topology["valid_mask"].ravel()
        expected_divergence = np.bincount(leaves[valid], weights=water["internal_net_m3"].sum(axis=0)[valid], minlength=len(parent))
        np.testing.assert_allclose(leaf_divergence, expected_divergence, rtol=1e-10, atol=1e-6)
        leaf_faces_checked, pair_count = len(leaf_seen), len(pair_seen)
    joins_checked = 0
    reach_records = {case["threshold_area_m2"]: case for case in index["inputs"]["reaches"]}
    for case in network["reach_cases"]:
        reach_pin = reach_records[case["threshold_area_m2"]]
        reaches = read_json(reach_pin["path"], reach_pin["expected_sha256"])
        terminals = {node["node_id"]: node for node in reaches["nodes"] if node["kind"] == "terminal"}
        observed = set()
        for join in case["terminal_owner_joins"]:
            node = terminals[join["reach_node_id"]]
            owner = int(owners[node["cell_id"]])
            if join["owner_id"] != owner or join["cell_id"] != node["cell_id"] or join["terminal_kind"] != node["terminal_kind"]:
                raise ValueError("terminal ownership mismatch")
            if set(join["incident_face_ids"]) != incident.get(owner, set()):
                raise ValueError("terminal face incidence mismatch")
            observed.add(node["node_id"])
            joins_checked += 1
        if observed != set(terminals):
            raise ValueError("terminal join coverage mismatch")
    return {"schema": "td-independent-basin-spill-audit-v1", "utc": datetime.now(timezone.utc).isoformat(),
            "index": {"path": str(index_path), "expected_sha256": index_sha256}, "checks_passed": True,
            "unique_cross_owner_faces": len(seen), "faces_at_merge_birth_saddle_level": int(saddle_faces),
            "recorded_transfer_faces": int(transfer_faces), "rejected_faces": int(rejected), "terminal_joins_checked": joins_checked,
            "unique_cross_leaf_faces": leaf_faces_checked, "exclusive_leaf_pairs": pair_count,
            "solver_advanced": False, "hydraulic_ready": False, "natural_outlet_verified": False,
            "auditor_sha256": file_sha256(__file__),
            "limitations": "Complete physical adjacency is broader than lowest spill outlets. Whole-run exchanges do not establish onset, continuous channel paths, or routed outlet discharge. No sum over nested control volumes."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = audit(arguments.index, arguments.index_sha256)
    publish_bytes(arguments.output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode())
    print(json.dumps({key: report[key] for key in ("checks_passed", "unique_cross_owner_faces", "faces_at_merge_birth_saddle_level", "recorded_transfer_faces", "terminal_joins_checked")}))
