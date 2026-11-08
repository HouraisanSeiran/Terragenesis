"""Independent D4 component, capacity and sediment reductions on pinned saved files."""

import argparse
from collections import deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.ndimage import label

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import checked_archive, publish_bytes


def file_record(path):
    source = Path(path).resolve(strict=True)
    return {"path": str(source), "bytes": source.stat().st_size,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}


def read_saved(path, expected_sha256):
    fields = checked_archive(path, expected_sha256=expected_sha256, max_bytes=1024 ** 3)
    if "manifest" in fields:
        metadata = json.loads(fields.pop("manifest").tobytes())["metadata"]
    else:
        metadata = json.loads(str(fields.pop("metadata_json").item()))
        fields.pop("identity_sha256")
    return fields, metadata


def near(actual, expected, *, absolute=1e-6, relative=1e-10):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError("nonfinite independent quantity")
    if np.any(np.abs(actual - expected) > absolute + relative * np.abs(expected)):
        raise ValueError("independent numerical reduction mismatch")


def audit_hierarchy(arrays, metadata):
    height, valid = arrays["height_m"], arrays["valid_mask"]
    count = height.size
    owner = arrays["cell_owner"].ravel()
    parents = arrays["node_parent"]
    nodes = len(parents)
    if np.any(owner[~valid.ravel()] != -1) or np.any(owner[valid.ravel()] < 0):
        raise ValueError("invalid exclusive ownership")
    if np.any(parents < -1) or np.any(parents >= nodes):
        raise ValueError("invalid parent")
    child_ids = np.flatnonzero(parents >= 0)
    if np.any(parents[child_ids] <= child_ids):
        raise ValueError("nonascending merge-tree IDs")
    faces = arrays["face_cells"]
    ids = np.arange(count).reshape(height.shape)
    expected_faces = set()
    for first, second in ((ids[:, :-1], ids[:, 1:]), (ids[:-1, :], ids[1:, :])):
        covered = valid.ravel()[first] & valid.ravel()[second]
        expected_faces.update(zip(first[covered].tolist(), second[covered].tolist()))
    if len(faces) != len(expected_faces) or set(map(tuple, faces.tolist())) != expected_faces:
        raise ValueError("missing/duplicate D4 faces")
    near(arrays["face_level_m"], np.max(height.ravel()[faces], axis=1), absolute=0, relative=0)
    np.testing.assert_array_equal(arrays["face_nodes"], owner[faces])
    receiver = arrays["receiver"]
    sources = np.flatnonzero(valid.ravel() & (receiver >= 0))
    targets = receiver[sources]
    if np.any(targets >= count) or np.any(~valid.ravel()[targets]):
        raise ValueError("receiver outside known grid")
    source_rows, source_columns = np.divmod(sources, height.shape[1])
    target_rows, target_columns = np.divmod(targets, height.shape[1])
    if np.any(np.abs(source_rows - target_rows) + np.abs(source_columns - target_columns) != 1):
        raise ValueError("corner or nonlocal routing")
    if np.any(height.ravel()[targets] > height.ravel()[sources]):
        raise ValueError("original-bed uphill receiver")
    indegree = np.bincount(targets, minlength=count)
    pending = deque(np.flatnonzero(valid.ravel() & (indegree == 0)).tolist())
    visited = 0
    while pending:
        cell = pending.popleft()
        visited += 1
        target = receiver[cell]
        if target >= 0:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(int(target))
    if visited != np.count_nonzero(valid):
        raise ValueError("receiver cycle")
    leaves = np.ones(nodes, bool)
    leaves[parents[child_ids]] = False
    contribution = arrays["contribution_owner"].ravel()
    if np.any(~leaves[contribution[valid.ravel()]]):
        raise ValueError("contribution does not terminate in leaf")
    np.testing.assert_array_equal(contribution[sources], contribution[targets])
    terminals = np.flatnonzero(valid.ravel() & (receiver < 0))
    np.testing.assert_array_equal(contribution[terminals], owner[terminals])
    spacing = metadata["spacing_m"]
    area = spacing ** 2
    sampled = np.unique(np.linspace(0, nodes - 1, min(nodes, 96)).astype(int))
    checked_curves = 0
    for node in sampled:
        ancestor = owner.copy()
        for unused in range(nodes):
            advance = (ancestor >= 0) & (ancestor < node)
            if not advance.any():
                break
            ancestor[advance] = parents[ancestor[advance]]
        members = valid.ravel() & (ancestor == node)
        if np.count_nonzero(members) != arrays["node_cell_count"][node]:
            raise ValueError("subtree count differs from exclusive membership")
        start, stop = arrays["curve_offsets"][node:node + 2]
        chosen_knots = np.unique(np.linspace(start, stop - 1, min(stop - start, 7)).astype(int))
        bed = height.ravel()[members]
        for knot in chosen_knots:
            level_m = arrays["curve_level_m"][knot]
            volume = math.fsum(np.maximum(level_m - bed, 0).tolist()) * area
            near(arrays["curve_volume_m3"][knot], volume)
            checked_curves += 1
        upper = arrays["node_upper_m"][node]
        if np.isfinite(upper):
            birth = arrays["node_birth_m"][node]
            stage = math.fsum((np.maximum(upper - bed, 0) - np.maximum(birth - bed, 0)).tolist()) * area
            near(arrays["stage_capacity_m3"][node], stage)
    structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    thresholds = np.unique(np.quantile(height[valid], np.linspace(0, 1, 13)))
    component_checks = 0
    for threshold in thresholds:
        wet = valid & (height <= threshold)
        labels, components = label(wet, structure)
        ancestor = owner.copy()
        for unused in range(nodes):
            current = np.maximum(ancestor, 0)
            parent = parents[current]
            advance = (ancestor >= 0) & (parent >= 0)
            advance &= arrays["node_birth_m"][np.maximum(parent, 0)] <= threshold
            if not advance.any():
                break
            ancestor[advance] = parent[advance]
        pairs = np.unique(np.column_stack((labels.ravel()[wet.ravel()], ancestor[wet.ravel()])), axis=0)
        if len(pairs) != components or len(np.unique(pairs[:, 1])) != components:
            raise ValueError("merge tree differs from independent D4 threshold components")
        component_checks += components
    return {"valid_cells": int(valid.sum()), "nodes": nodes, "leaves": int(leaves.sum()),
            "faces": len(faces), "receiver_edges": len(sources), "uphill_edges": 0,
            "capacity_sample_nodes": len(sampled), "exact_capacity_checks": checked_curves,
            "thresholds": len(thresholds), "component_checks": component_checks,
            "natural_outlet_verified": False}


def audit_morphology(arrays, metadata):
    valid = arrays["valid_mask"]
    area = metadata["spacing_m"] ** 2
    source_porosity = metadata["material_parameters"]["source_porosity"]
    deposit_porosity = metadata["material_parameters"]["deposit_porosity"]
    density = metadata["material_parameters"]["solid_density_kg_m3"]
    erosion = arrays["erosion_depth_m"]
    deposit = arrays["deposit_depth_m"]
    near(arrays["height_m"][valid] - arrays["original_height_m"][valid], (deposit - erosion)[valid])
    near(arrays["source_geometry_m3"], area * erosion)
    near(arrays["source_solid_m3"], area * erosion * (1 - source_porosity))
    near(arrays["source_mass_kg"], area * erosion * (1 - source_porosity) * density)
    near(arrays["deposited_solid_m3"], area * deposit * (1 - deposit_porosity))
    incoming = np.zeros(valid.size)
    receiver = arrays["receiver"]
    sources = np.flatnonzero(valid.ravel() & (receiver >= 0))
    np.add.at(incoming, receiver[sources], arrays["transported_solid_m3"].ravel()[sources])
    near(arrays["incoming_solid_m3"].ravel(), incoming)
    available = incoming.reshape(valid.shape) + arrays["source_solid_m3"]
    destinations = sum(arrays[name] for name in ("transported_solid_m3", "deposited_solid_m3", "stored_solid_m3", "exported_solid_m3"))
    near(destinations, available)
    sums = {name: math.fsum(arrays[name].ravel().tolist()) for name in
            ("source_solid_m3", "deposited_solid_m3", "stored_solid_m3", "exported_solid_m3")}
    residual = sums["source_solid_m3"] - sums["deposited_solid_m3"] - sums["stored_solid_m3"] - sums["exported_solid_m3"]
    near(sums["source_solid_m3"], sum(sums[name] for name in ("deposited_solid_m3", "stored_solid_m3", "exported_solid_m3")))
    protected = arrays["protected_mask"] | ~valid
    if np.any(erosion[protected] != 0) or np.any(deposit[protected] != 0):
        raise ValueError("unknown/protected geometry modified")
    return dict(sums, residual_m3=residual, changed_cells=int(np.count_nonzero(erosion + deposit)),
                erosion_max_m=float(erosion.max()), deposit_max_m=float(deposit.max()))


def audit_storage(arrays, metadata):
    height = arrays["height_m"]
    valid = arrays["valid_mask"].ravel()
    area = metadata["spacing_m"] ** 2
    time_step = metadata["dt_s"]
    depth = arrays["depth_m"]
    stores = depth + sum(arrays[name] for name in ("soil_mm", "fast_mm", "slow_mm")) / 1000
    steps = len(depth) - 1
    if np.any(stores < 0) or not np.isfinite(stores).all() or np.any(stores[:, ~valid] != 0):
        raise ValueError("invalid stored water state")
    rain_volume = arrays["rain_mm_h"] * (time_step / 3600) * area / 1000
    near(arrays["rain_volume_m3"], rain_volume)
    near(arrays["lake_rain_m3"] + arrays["land_rain_m3"], rain_volume)
    changes = np.diff(stores, axis=0) * area
    near(arrays["storage_change_m3"], changes)
    expected = (rain_volume + arrays["internal_net_m3"] - arrays["soil_et_m3"]
                - arrays["surface_et_m3"] - arrays["boundary_outflow_m3"])
    near(changes, expected)
    faces = arrays["face_cells"]
    net_face = arrays["face_forward_m3"] - arrays["face_reverse_m3"]
    net_cell = np.zeros(height.size)
    np.add.at(net_cell, faces[:, 0], -net_face)
    np.add.at(net_cell, faces[:, 1], net_face)
    near(arrays["internal_net_m3"].sum(axis=0), net_cell)
    sources = np.flatnonzero(valid & (arrays["receiver"] >= 0))
    directed = {(int(first), int(second)): float(volume) for (first, second), volume in zip(faces, arrays["face_forward_m3"])}
    directed.update({(int(second), int(first)): float(volume) for (first, second), volume in zip(faces, arrays["face_reverse_m3"])})
    routed = np.zeros(height.size)
    for source in sources:
        routed[source] = directed[(int(source), int(arrays["receiver"][source]))]
    near(arrays["routed_volume_m3"], routed)
    if "active_forward_s" in arrays:
        duration = arrays["active_forward_s"] + arrays["active_reverse_s"]
        if np.any(duration < 0) or np.any(duration > steps * time_step + 1e-8):
            raise ValueError("duplicate directional face activity duration")
        directed_duration = {(int(first), int(second)): float(value) for (first, second), value in zip(faces, arrays["active_forward_s"])}
        directed_duration.update({(int(second), int(first)): float(value) for (first, second), value in zip(faces, arrays["active_reverse_s"])})
        expected_duration = np.zeros(height.size)
        for source in sources:
            expected_duration[source] = directed_duration[(int(source), int(arrays["receiver"][source]))]
        near(arrays["wet_duration_s"], expected_duration)
    if np.any(arrays["wet_duration_s"] < 0) or np.any(arrays["wet_duration_s"] > steps * time_step + 1e-8):
        raise ValueError("invalid routed duration")
    allowed_boundary = np.zeros(height.size, bool)
    allowed_boundary[arrays["boundary_cells"]] = True
    if np.any(arrays["boundary_outflow_m3"][:, ~allowed_boundary] != 0):
        raise ValueError("water exported through undeclared boundary")
    budgets = []
    maximum_residual = 0.
    for step in range(steps):
        rain_total = math.fsum(rain_volume[step].tolist())
        losses = math.fsum((arrays["soil_et_m3"][step] + arrays["surface_et_m3"][step]).tolist())
        external = math.fsum(arrays["boundary_outflow_m3"][step].tolist())
        change = math.fsum(changes[step].tolist())
        residual = rain_total - losses - external - change
        near(rain_total, losses + external + change)
        near(math.fsum(arrays["internal_net_m3"][step].tolist()), 0, absolute=1e-6 + rain_total * 1e-10)
        maximum_residual = max(maximum_residual, abs(residual))
        budgets.append({"step": step, "rain_m3": rain_total, "loss_m3": losses,
                        "external_m3": external, "storage_change_m3": change, "residual_m3": residual})
    return {"steps": steps, "valid_cells": int(valid.sum()), "D4_faces": len(faces),
            "initial_water_m3": math.fsum(stores[0].tolist()) * area,
            "final_water_m3": math.fsum(stores[-1].tolist()) * area,
            "max_step_global_residual_m3": maximum_residual,
            "max_depth_m": float(depth.max()), "budgets": budgets,
            "face_volume_integrals_match_cell_divergence": True,
            "routed_is_actual_face_integral": True, "natural_outlet_verified": False}


def audit_breach(arrays, metadata):
    area = metadata["spacing_m"] ** 2
    config = metadata["material_parameters"]
    erosion = arrays["erosion_depth_m"]
    valid = arrays["valid_mask"]
    path = arrays["path_cell_ids"]
    rows, columns = np.divmod(path, valid.shape[1])
    if len(np.unique(path)) != len(path) or np.any(np.abs(np.diff(rows)) + np.abs(np.diff(columns)) != 1):
        raise ValueError("nonlocal/repeated saddle path")
    near(arrays["height_m"][valid], (arrays["original_height_m"] - erosion)[valid])
    near(arrays["source_geometry_m3"], erosion * area)
    near(arrays["source_solid_m3"], erosion * area * (1 - config["source_porosity"]))
    near(arrays["source_mass_kg"], arrays["source_solid_m3"] * config["solid_density_kg_m3"])
    if np.any(erosion[arrays["protected_mask"] | ~valid] != 0) or np.any(erosion < 0):
        raise ValueError("illegal saddle geometry change")
    outside = np.ones(valid.size, bool)
    outside[path] = False
    if np.any(erosion.ravel()[outside] != 0) or erosion.ravel()[path[0]] != 0 or erosion.ravel()[path[-1]] != 0:
        raise ValueError("saddle changed outside path or endpoint anchors")
    source = math.fsum(arrays["source_solid_m3"].ravel().tolist())
    inventory = np.zeros(valid.size)
    inventory[path[-1]] = source
    near(arrays["stored_solid_m3"].ravel(), inventory)
    for name in ("transported_solid_m3", "exported_solid_m3", "deposited_solid_m3", "deposit_geometry_m3"):
        near(arrays[name], 0)
    if metadata["status"] == "rejected":
        near(erosion, 0, absolute=0, relative=0)
        if not metadata["rejection_reasons"]:
            raise ValueError("rejected saddle lacks reason")
    else:
        target = arrays["path_target_bed_m"]
        if np.any(np.diff(target) >= 0):
            raise ValueError("saddle target does not descend")
        near(erosion.ravel()[path], arrays["original_height_m"].ravel()[path] - target)
        if np.any(erosion.ravel()[path] > arrays["path_erodible_thickness_m"] + 1e-8) or np.any(erosion.ravel()[path] > arrays["path_potential_depth_m"] + 1e-8):
            raise ValueError("saddle exceeds finite material or water potential")
    return {"status": metadata["status"], "path_cells": len(path), "source_solid_m3": source,
            "inventory_solid_m3": math.fsum(inventory.tolist()), "changed_cells": int(np.count_nonzero(erosion)),
            "external_face_evidence_independently_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hierarchy", type=Path)
    parser.add_argument("--hierarchy-sha256")
    parser.add_argument("--morphology", type=Path)
    parser.add_argument("--morphology-sha256")
    parser.add_argument("--storage", type=Path)
    parser.add_argument("--storage-sha256")
    parser.add_argument("--breach", type=Path)
    parser.add_argument("--breach-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"algorithm": "td-basin-independent-audit-v1", "reviewed_utc": datetime.now(timezone.utc).isoformat(),
              "auditor": file_record(__file__), "inputs": {}, "checks": {}}
    for name, auditor in (("hierarchy", audit_hierarchy), ("morphology", audit_morphology), ("storage", audit_storage), ("breach", audit_breach)):
        path = getattr(args, name)
        if path is not None:
            arrays, metadata = read_saved(path, getattr(args, name + "_sha256"))
            report["inputs"][name] = file_record(path)
            report["checks"][name] = auditor(arrays, metadata)
    if not report["checks"]:
        raise ValueError("at least one pinned artifact required")
    payload = (json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False, indent=2) + "\n").encode()
    publish_bytes(args.output, payload)
    print(json.dumps(report["checks"], ensure_ascii=True))


if __name__ == "__main__":
    main()
