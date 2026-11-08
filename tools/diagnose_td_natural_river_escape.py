"""Read-only potential escape-chain screening for the frozen natural river basin."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.td_natural_river_network import load_natural_river_network


SCHEMA = "td-natural-river-potential-escape-diagnostic-v1"
INDEX = ROOT / "verification/natural-river-network/round2-20261005-01/index.json"
INDEX_SHA256 = "2b8fc32f56a6a7f54e38cd5792247ae0355c40cd74ad272f5fdba81745981213"
PLAN = ROOT / "verification/td-basin-escape-plan/run-20261002T100017974303Z/escape-plan.json"
PLAN_SHA256 = "d3f78cc120802df390aa8d990c9f699c1d554970fed6ee395a6f1d9133656268"
PLAN_IDENTITY = "bbb54e1b54dc0f2cce3421f8f7248a335cf0bcdc267e642661013440c5854149"
MAX_PLAN_BYTES = 16 * 1024 * 1024


def _digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_json(path, expected_sha256, max_bytes):
    path = Path(path)
    if path.stat().st_size > max_bytes or file_sha256(path) != expected_sha256:
        raise ValueError("external JSON SHA/budget mismatch")

    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("nonfinite JSON value")

    return json.loads(path.read_bytes(), object_pairs_hook=unique_pairs, parse_constant=reject_constant)


def load_saved_inputs(index_path=INDEX, index_sha256=INDEX_SHA256, plan_path=PLAN,
                      plan_sha256=PLAN_SHA256, plan_identity=PLAN_IDENTITY):
    index_path = Path(index_path)
    index = _read_json(index_path, index_sha256, 2 * 1024 * 1024)
    if index.get("schema") != "td-natural-river-delivery-v1":
        raise ValueError("delivery index schema mismatch")
    if any(index.get(flag) is not False for flag in
           ("hydraulic_ready", "natural_outlet_verified", "publishable", "solver_advanced")):
        raise ValueError("delivery index certification flags mismatch")
    network_pin = index["artifacts"]["network"]
    hierarchy_pin = index["input_pins"]["hierarchy"]
    original_pin = index["input_pins"]["original_td"]
    network_path = (index_path.parent / network_pin["path"]).resolve()
    hierarchy_path = Path(hierarchy_pin["path"])
    if network_path.parent != index_path.parent.resolve():
        raise ValueError("network path leaves pinned delivery")
    if file_sha256(original_pin["path"]) != original_pin["sha256"]:
        raise ValueError("original TD source SHA mismatch")
    hierarchy = load_basin_hierarchy(hierarchy_path, expected_sha256=hierarchy_pin["expected_sha256"],
                                     expected_identity=hierarchy_pin["expected_identity"])
    if hierarchy["metadata"]["source_metadata"]["source_sha256"] != original_pin["sha256"]:
        raise ValueError("hierarchy original TD source pin mismatch")
    network = load_natural_river_network(network_path, expected_sha256=network_pin["sha256"],
                                         expected_identity=network_pin["identity_sha256"], hierarchy=hierarchy)
    plan = _read_json(plan_path, plan_sha256, MAX_PLAN_BYTES)
    embedded_identity = plan.pop("identity_sha256", None)
    if embedded_identity != plan_identity or _digest(plan) != plan_identity:
        raise ValueError("escape plan identity mismatch")
    plan["identity_sha256"] = embedded_identity
    pins = {
        "delivery_index": {"path": str(index_path), "sha256": index_sha256},
        "network": {"path": str(network_path), "sha256": network_pin["sha256"],
                    "identity_sha256": network_pin["identity_sha256"]},
        "hierarchy": {"path": str(hierarchy_path), "sha256": hierarchy_pin["expected_sha256"],
                      "identity_sha256": hierarchy_pin["expected_identity"]},
        "original_td": {"path": original_pin["path"], "sha256": original_pin["sha256"]},
        "escape_plan": {"path": str(plan_path), "sha256": plan_sha256, "identity_sha256": plan_identity},
    }
    return network, hierarchy, plan, pins


def _verify_pins_unchanged(pins):
    for name in ("delivery_index", "network", "hierarchy", "original_td", "escape_plan"):
        record = pins[name]
        if file_sha256(record["path"]) != record["sha256"]:
            raise ValueError(f"input changed before publication: {name}")


def _minimum_pair_faces(hierarchy, pairs):
    arrays = hierarchy["arrays"]
    owners = arrays["contribution_owner"].ravel()
    bed = arrays["height_m"].ravel()
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    unknown = arrays["node_unknown_contact"]
    minima = {}
    for face_index, face in enumerate(arrays["face_cells"]):
        first, second = map(int, face)
        pair = tuple(sorted((int(owners[first]), int(owners[second]))))
        if pair not in pairs:
            continue
        if (not valid[first] or not valid[second] or protected[first] or protected[second] or
                unknown[pair[0]] or unknown[pair[1]]):
            continue
        sill = float(max(bed[first], bed[second]))
        previous = minima.get(pair)
        if previous is None or sill < previous[0]:
            minima[pair] = (sill, [face_index])
        elif sill == previous[0]:
            previous[1].append(face_index)
    return minima


def _face_identity(hierarchy, face_index):
    arrays = hierarchy["arrays"]
    metadata = hierarchy["metadata"]
    columns = arrays["height_m"].shape[1]
    origin_x, origin_z = metadata["origin_m_xz"]
    spacing = metadata["spacing_m"]
    endpoints = []
    for cell in arrays["face_cells"][face_index]:
        row, column = divmod(int(cell), columns)
        xyz = (float(origin_x + column * spacing), float(arrays["height_m"].ravel()[cell]),
               float(origin_z + row * spacing))
        endpoints.append([value.hex() for value in xyz])
    return "face:" + _digest([metadata["source_identity_sha256"], sorted(endpoints)])


def _checked_chain(network, hierarchy, plan):
    source = hierarchy["arrays"]
    river = network["arrays"]
    metadata = network["metadata"]
    if (plan.get("schema") != "td-basin-escape-plan-v1" or
            plan.get("algorithm") != "multi-source-minimax-settled-parent-forest-v1" or
            plan.get("hierarchy_identity_sha256") != hierarchy["identity_sha256"] or
            plan.get("source_identity_sha256") != hierarchy["metadata"]["source_identity_sha256"] or
            metadata["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            metadata["source_identity_sha256"] != plan["source_identity_sha256"]):
        raise ValueError("foreign hierarchy/source/plan identity")
    if plan["flags"].get("potential_only") is not True or any(
            plan["flags"].get(flag) is not False for flag in
            ("hydraulic_ready", "hydraulic_verified", "natural_outlet_verified", "publishable", "water_generated")):
        raise ValueError("escape plan certification semantics mismatch")
    terminal = metadata["summary"]["selected_terminal_cell_id"]
    if (terminal != 16088 or river["receiver"][terminal] != -1 or
            not river["selected_basin_mask"].ravel()[terminal] or
            not np.array_equal(river["source_height_m"], source["height_m"])):
        raise ValueError("selected terminal/source mismatch")
    owners = source["contribution_owner"].ravel()
    leaf_id = int(owners[terminal])
    records = {record["leaf_id"]: record for record in plan["leaves"]}
    if len(records) != len(plan["leaves"]) or leaf_id not in records:
        raise ValueError("escape plan leaf coverage invalid")
    selected_cells = river["selected_basin_mask"].ravel()
    if not np.all(owners[selected_cells] == leaf_id):
        raise ValueError("selected basin spans multiple contribution leaves")
    seed_by_leaf = {seed["leaf_id"]: seed for seed in plan["engineering_seeds"]}
    if len(seed_by_leaf) != len(plan["engineering_seeds"]):
        raise ValueError("duplicate engineering seed leaf")
    bed = source["height_m"].ravel()
    faces = source["face_cells"]
    chain = []
    visited = set()
    current = leaf_id
    while True:
        if current in visited:
            raise ValueError("escape parent cycle")
        visited.add(current)
        record = records.get(current)
        if record is None or record["reachable"] is not True:
            raise ValueError("escape chain contains missing/unreachable leaf")
        stage = record["minimum_escape_stage_m"]
        if type(stage) not in (float, int) or not math.isfinite(stage):
            raise ValueError("nonfinite escape stage")
        parent_id = record["parent_leaf_id"]
        if parent_id is None:
            if record["minimum_face"] is not None or current not in seed_by_leaf:
                raise ValueError("root lacks explicit engineering seed")
            seed = seed_by_leaf[current]
            root_cell = seed["boundary_cell_id"]
            if (root_cell != record["root_boundary_cell_id"] or
                    not source["open_boundary_mask"].ravel()[root_cell] or
                    int(owners[root_cell]) != current or
                    float(bed[root_cell]) != stage or seed["boundary_level_m"] != stage or
                    seed["stable_leaf_id"] != record["stable_leaf_id"]):
                raise ValueError("root seed/open-boundary mismatch")
            break
        parent = records.get(parent_id)
        if parent is None or parent["reachable"] is not True:
            raise ValueError("missing escape parent")
        if (type(record["settlement_rank"]) is not int or type(parent["settlement_rank"]) is not int or
                parent["settlement_rank"] >= record["settlement_rank"]):
            raise ValueError("escape parent rank/cycle invalid")
        evidence = record["minimum_face"]
        if not isinstance(evidence, dict):
            raise ValueError("missing exact minimum face")
        face_index = evidence["face_index"]
        if type(face_index) is not int or not 0 <= face_index < len(faces):
            raise ValueError("minimum face index out of range")
        face_cells = faces[face_index]
        if (evidence["face_cell_ids"] != face_cells.tolist() or
                {int(owners[cell]) for cell in face_cells} != {current, parent_id} or
                source["protected_mask"].ravel()[face_cells].any() or
                not source["valid_mask"].ravel()[face_cells].all()):
            raise ValueError("minimum face does not join physical owner pair")
        physical_sill = float(max(bed[face_cells[0]], bed[face_cells[1]]))
        if (evidence["physical_sill_m"] != physical_sill or
                source["face_level_m"][face_index] != physical_sill or
                evidence["face_id"] != _face_identity(hierarchy, face_index) or
                evidence["pair_id"] != "leaf-pair:" + _digest(sorted((record["stable_leaf_id"], parent["stable_leaf_id"])))):
            raise ValueError("minimum face physical sill/identity mismatch")
        if (max(parent["minimum_escape_stage_m"], physical_sill) != stage or
                parent["root_boundary_cell_id"] != record["root_boundary_cell_id"]):
            raise ValueError("escape minimax/root recurrence mismatch")
        chain.append({"leaf_id": current, "parent_leaf_id": parent_id,
                      "minimum_escape_stage_m": float(stage), "settlement_rank": record["settlement_rank"],
                      "minimum_face": evidence})
        current = parent_id
    pair_keys = {tuple(sorted((step["leaf_id"], step["parent_leaf_id"]))) for step in chain}
    pair_minima = _minimum_pair_faces(hierarchy, pair_keys)
    for step in chain:
        pair = tuple(sorted((step["leaf_id"], step["parent_leaf_id"])))
        minimum = pair_minima.get(pair)
        evidence = step["minimum_face"]
        if minimum is None or minimum[0] != evidence["physical_sill_m"]:
            raise ValueError("saved face is not the physical minimum for its pair")
        chosen = min(minimum[1], key=lambda face_index: _face_identity(hierarchy, face_index))
        if chosen != evidence["face_index"]:
            raise ValueError("minimum face tie identity mismatch")
    root = records[current]
    if any(step["minimum_face"] is None for step in chain):
        raise ValueError("missing chain face")
    return terminal, leaf_id, records[leaf_id], root, chain


def diagnose_escape_chain(network, hierarchy, plan, pins):
    terminal, leaf_id, selected_record, root, chain = _checked_chain(network, hierarchy, plan)
    arrays = hierarchy["arrays"]
    river = network["arrays"]
    mask = river["selected_basin_mask"].ravel()
    bed = arrays["height_m"].ravel()[mask]
    spacing = float(hierarchy["metadata"]["spacing_m"])
    area_m2 = int(mask.sum()) * spacing ** 2
    first_sill_m = chain[0]["minimum_face"]["physical_sill_m"] if chain else None
    escape_stage_m = float(selected_record["minimum_escape_stage_m"])

    def hypothetical_storage(stage):
        return float(np.maximum(stage - bed, 0).sum() * spacing ** 2)

    first_storage_m3 = hypothetical_storage(first_sill_m) if first_sill_m is not None else None
    escape_storage_m3 = hypothetical_storage(escape_stage_m)
    if selected_record["raise_to_stage_volume_m3"] is not None and not math.isclose(
            escape_storage_m3, selected_record["raise_to_stage_volume_m3"], rel_tol=1e-12, abs_tol=1e-7):
        raise ValueError("selected exclusive original-bed storage mismatch")
    scenarios = []
    recipe = network["metadata"]["recipe"]
    for index, forcing in enumerate(network["metadata"]["forcing"]):
        duration_s = forcing["duration_s"]
        rainfall_m3 = area_m2 * forcing["rainfall_mm"] / 1000 * recipe["runoff_coefficient"]
        baseflow_m3 = area_m2 * recipe["baseflow_mm_per_day"] / 1000 * duration_s / 86400
        total_m3 = rainfall_m3 + baseflow_m3
        saved_m3 = float(river["local_q_m3_s"][index, mask].sum() * duration_s)
        if not math.isclose(total_m3, saved_m3, rel_tol=1e-12, abs_tol=1e-8):
            raise ValueError("saved local Q and scenario volume disagree")
        scenarios.append({"name": forcing["name"], "role": forcing["role"], "duration_s": duration_s,
                          "rainfall_runoff_m3": rainfall_m3, "baseflow_m3": baseflow_m3,
                          "constant_rate_volume_m3": total_m3,
                          "volume_to_first_sill_storage_ratio": total_m3 / first_storage_m3 if first_storage_m3 and first_storage_m3 > 0 else None,
                          "volume_to_escape_stage_storage_ratio": total_m3 / escape_storage_m3 if escape_storage_m3 > 0 else None})
    report = {"schema": SCHEMA, "algorithm": SCHEMA, "pins": pins,
              "auditor_sha256": file_sha256(__file__),
              "selected_terminal_cell_id": terminal, "selected_contribution_leaf_id": leaf_id,
              "selected_basin_area_m2": area_m2,
              "first_physical_sill_m": first_sill_m, "global_potential_escape_stage_m": escape_stage_m,
              "hypothetical_original_bed_storage_m3": {"first_sill": first_storage_m3,
                                                        "global_escape_stage": escape_storage_m3},
              "escape_chain": {"physical_face_steps": chain,
                               "root_leaf_id": root["leaf_id"],
                               "root_engineering_boundary_cell_id": root["root_boundary_cell_id"],
                               "root_engineering_boundary_bed_m": root["minimum_escape_stage_m"]},
              "fixed_forcing_volume_comparison": scenarios,
              "flags": {"potential_only": True, "hydraulic_ready": False, "hydraulic_verified": False,
                        "natural_outlet_verified": False, "publishable": False, "water_generated": False,
                        "solver_advanced": False},
              "semantics": "Original-bed static face chain and hypothetical fill integrals only. Fixed rain converts to constant local runoff rate, with baseflow shown separately. Ratios do not state required rain, spill onset, dynamic overflow, natural outlet or a river centerline."}
    report["identity_sha256"] = _digest(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    network, hierarchy, plan, pins = load_saved_inputs()
    report = diagnose_escape_chain(network, hierarchy, plan, pins)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
    _verify_pins_unchanged(pins)
    publish_bytes(args.output, payload)
    print(json.dumps({"output": str(args.output), "sha256": file_sha256(args.output),
                      "identity_sha256": report["identity_sha256"]}))


if __name__ == "__main__":
    main()
