"""Pinned 256 squared TD static hierarchy inventory; no rainfall advancement."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_source import PRIMARY_PATH, PRIMARY_SHA256, load_td_source, save_td_source
from terrain_pipeline.td_basin_hierarchy import build_basin_hierarchy, load_basin_hierarchy, save_basin_hierarchy


def verify(destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    start = time.perf_counter()
    tracemalloc.start()
    source = load_td_source()
    hierarchy = build_basin_hierarchy(source)
    arrays = hierarchy["arrays"]
    source_path, hierarchy_path = destination / "source.npz", destination / "hierarchy.npz"
    save_td_source(source_path, source)
    save_basin_hierarchy(hierarchy_path, hierarchy)
    loaded = load_basin_hierarchy(hierarchy_path, expected_sha256=file_sha256(hierarchy_path),
                                 expected_identity=hierarchy["identity_sha256"])
    assert loaded["identity_sha256"] == hierarchy["identity_sha256"]
    assert file_sha256(PRIMARY_PATH) == PRIMARY_SHA256
    parent = arrays["node_parent"]
    children_count = np.bincount(parent[parent >= 0], minlength=len(parent))
    leaves = np.flatnonzero(children_count == 0)
    roots = np.flatnonzero(parent == -1)
    receiver = arrays["receiver"]
    cells = np.flatnonzero(receiver >= 0)
    bed = arrays["height_m"].ravel()
    flat = bed[cells] == bed[receiver[cells]]
    inventory = []
    for node in range(len(parent)):
        start_curve, stop_curve = arrays["curve_offsets"][node:node + 2]
        inventory.append({"node": node, "parent": int(parent[node]), "children": int(children_count[node]),
            "birth_m": float(arrays["node_birth_m"][node]),
            "upper_m": None if np.isinf(arrays["node_upper_m"][node]) else float(arrays["node_upper_m"][node]),
            "stage_capacity_m3": None if np.isinf(arrays["stage_capacity_m3"][node]) else float(arrays["stage_capacity_m3"][node]),
            "volume_at_birth_m3": float(arrays["curve_volume_m3"][start_curve]),
            "owned_cells": int((arrays["cell_owner"] == node).sum()),
            "subtree_cells": int(arrays["node_cell_count"][node]),
            "unknown_contact": bool(arrays["node_unknown_contact"][node]),
            "engineering_open_contact": bool(arrays["node_open_boundary"][node]),
            "open_contact_level_m": None if np.isinf(arrays["node_open_level_m"][node]) else float(arrays["node_open_level_m"][node]),
            "curve_entries": int(stop_curve - start_curve)})
    publish_bytes(destination / "inventory.json", json.dumps(inventory, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = {"status": "51_implementation_ready_for_independent_acceptance", "shape": list(bed.reshape(arrays["height_m"].shape).shape),
        "input": {"path": str(PRIMARY_PATH), "sha256": PRIMARY_SHA256, "unchanged": True},
        "source_metadata": source["metadata"], "hierarchy_identity_sha256": hierarchy["identity_sha256"],
        "artifacts": {"source.npz": file_sha256(source_path), "hierarchy.npz": file_sha256(hierarchy_path),
                      "inventory.json": file_sha256(destination / "inventory.json")},
        "code_sha256": {name: file_sha256(ROOT / name) for name in (
            "terrain_pipeline/td_basin_source.py", "terrain_pipeline/td_basin_hierarchy.py",
            "tests/test_td_basin_source_hierarchy.py", "tools/verify_td_basin_source_hierarchy.py")},
        "statistics": {"valid_cells": int(arrays["valid_mask"].sum()), "area_m2": float(arrays["valid_mask"].sum() * source["metadata"]["spacing_m"] ** 2),
            "nodes": len(parent), "leaves": len(leaves), "roots": roots.tolist(), "merge_nodes": int((children_count > 0).sum()),
            "multifurcations": int((children_count > 2).sum()), "curve_entries": len(arrays["curve_level_m"]),
            "hypsometry_owned_entries": hierarchy["metadata"]["retained_hypsometry_entries"],
            "D4_faces": len(arrays["face_cells"]), "strict_descent_receivers": int((~flat).sum()),
            "flat_receivers": int(flat.sum()), "terminals": int(((receiver < 0) & arrays["valid_mask"].ravel()).sum()),
            "unknown_contact_leaves": int(arrays["node_unknown_contact"][leaves].sum()),
            "engineering_contact_leaves": int(arrays["node_open_boundary"][leaves].sum()),
            "closed_components": int((~arrays["node_open_boundary"][roots]).sum()),
            "positive_finite_stages": int(((arrays["stage_capacity_m3"] > 0) & np.isfinite(arrays["stage_capacity_m3"])).sum())},
        "peak_traced_bytes": peak, "elapsed_s": time.perf_counter() - start,
        "limitations": ["static full-domain topology only; 53 nested wet-state and recession not yet implemented",
            "static routing is algorithmic first-entry contribution assignment, not physical travel time",
            "root infinity is a topology sentinel; explicit boundary faces govern future outflow",
            "engineering open contact does not certify natural outlets or hydrological closure",
            "unknown-contact capacities describe known covered cells only", "no natural morphology or Minecraft acceptance claim"]}
    publish_bytes(destination / "report.json", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    destination = arguments.output or ROOT / "verification/td-basin-generation" / ("A-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    report = verify(destination)
    print(json.dumps({"output": str(destination), "statistics": report["statistics"],
                      "elapsed_s": report["elapsed_s"], "peak_traced_bytes": report["peak_traced_bytes"]}, ensure_ascii=False))
