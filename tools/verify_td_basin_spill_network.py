"""Cold-read frozen TD reach and potential spill graph review bundle."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import ctypes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256, publish_bytes
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline.basin_storage import load_basin_storage as load_basin_storage
from terrain_pipeline.td_surface_reaches import load_surface_reaches, _plain
from terrain_pipeline.basin_topology import save_basin_spill_bundle as save_basin_spill_bundle
from terrain_pipeline.basin_topology import load_basin_spill_bundle as load_basin_spill_bundle


def peak_process_memory():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in
            ("peak_working_set", "working_set", "peak_paged_pool", "paged_pool", "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32")
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    query = ctypes.WinDLL("psapi").GetProcessMemoryInfo
    query.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise OSError("process memory query failed")
    return {"peak_working_set_bytes": counters.peak_working_set, "peak_pagefile_bytes": counters.peak_pagefile}


def independent_audit(result, hierarchy, storage, reaches):
    arrays = hierarchy["arrays"]
    expected = {face for face, pair in enumerate(arrays["face_cells"])
                if arrays["cell_owner"].ravel()[pair[0]] != arrays["cell_owner"].ravel()[pair[1]]}
    seen = set()
    for item in result["spills"]:
        face = item["face_index"]
        if face in seen:
            raise ValueError("duplicate physical spill face")
        seen.add(face)
        pair = list(map(int, arrays["face_cells"][face]))
        owners = [int(arrays["cell_owner"].ravel()[cell]) for cell in pair]
        if list(item["face_cell_ids"]) != pair or list(item["owner_ids"]) != owners:
            raise ValueError("face/owner mismatch")
        ancestors = []
        for owner in owners:
            chain = []
            while owner >= 0:
                chain.append(owner)
                owner = int(arrays["node_parent"][owner])
            ancestors.append(chain)
        merge = next(node for node in ancestors[0] if node in ancestors[1])
        if item["merge_node_id"] != merge or item["face_sill_m"] != max(arrays["height_m"].ravel()[pair]):
            raise ValueError("merge/sill mismatch")
        flux = item["stored_whole_run_flux"]
        if flux["forward_m3"] != storage["arrays"]["face_forward_m3"][face] or flux["reverse_m3"] != storage["arrays"]["face_reverse_m3"][face]:
            raise ValueError("directional integral mismatch")
    if seen != expected:
        raise ValueError("cross-owner coverage mismatch")
    for case, network in zip(result["reach_cases"], reaches):
        terminals = {node["node_id"]: node for node in network["nodes"] if node["kind"] == "terminal"}
        joins = case["terminal_owner_joins"]
        if {join["reach_node_id"] for join in joins} != set(terminals):
            raise ValueError("terminal coverage mismatch")
        for join in joins:
            cell = terminals[join["reach_node_id"]]["cell_id"]
            if join["cell_id"] != cell or join["owner_id"] != arrays["cell_owner"].ravel()[cell]:
                raise ValueError("terminal owner mismatch")
    return {"passed": True, "unique_cross_owner_faces": len(seen),
            "method": "all physical cross-owner faces, independent parent-chain LCA/sill/directional integrals and terminal-owner join coverage; no ancestor flux sums"}


def verify():
    reach_root = ROOT / "verification/td-surface-reaches/run-20261002T091814997493Z"
    if file_sha256(reach_root / "report.json") != "dfeedbafc7851efef423b801138017ec94867a844a2ab62db0686c051c15b67b":
        raise ValueError("external reach report pin mismatch")
    original = json.loads((reach_root / "report.json").read_bytes())
    hierarchy_pin = dict(original["inputs"]["hierarchy"])
    storage_pin = dict(original["inputs"]["storage"])
    hierarchy_pin["path"] = str(ROOT / "verification/td-basin-generation/A-20261001T184113155960Z/hierarchy.npz")
    storage_pin["path"] = str(ROOT / "verification/td-basin-generation/A-storage-v2-20261001T193000Z/ordinary.npz")
    hierarchy = load_basin_hierarchy(**{ "path": hierarchy_pin["path"], "expected_sha256": hierarchy_pin["expected_sha256"], "expected_identity": hierarchy_pin["expected_identity"]})
    storage = load_basin_storage(**{ "path": storage_pin["path"], "expected_sha256": storage_pin["expected_sha256"], "expected_identity": storage_pin["expected_identity"]})
    reaches, records = [], []
    for case in original["cases"]:
        path = reach_root / ("area-" + str(int(case["threshold_area_m2"])) + ".json")
        network = load_surface_reaches(path, expected_sha256=case["expected_sha256"], expected_identity=case["expected_identity"], hierarchy=hierarchy, storage=storage)
        reaches.append(network)
        records.append({"path": str(path), "expected_sha256": case["expected_sha256"], "expected_identity": case["expected_identity"],
                        "threshold_area_m2": case["threshold_area_m2"], "terminal_classes": _plain(network["summary"]["terminal_classes"])})
    output = ROOT / "verification/td-basin-spill-network" / ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    result = save_basin_spill_bundle(output, hierarchy, expected_hierarchy_identity=hierarchy_pin["expected_identity"],
        storage=storage, expected_storage_identity=storage_pin["expected_identity"], reach_networks=reaches)
    path = output / "bundle.json"
    pin = {"path": str(path), "expected_sha256": file_sha256(path), "expected_identity": result["identity_sha256"]}
    del result
    loaded = load_basin_spill_bundle(path, expected_sha256=pin["expected_sha256"], expected_identity=pin["expected_identity"], hierarchy=hierarchy, storage=storage, reach_networks=reaches)
    result = loaded
    checked_faces = 0
    for chunk in result["face_chunks"]:
        records_chunk = json.loads((output / chunk["file"]).read_bytes())
        for item in records_chunk:
            face = item["face_index"]
            if item["face_cell_ids"] != hierarchy["arrays"]["face_cells"][face].tolist():
                raise ValueError("independent face pair mismatch")
            if item["stored_whole_run_flux"]["forward_m3"] != storage["arrays"]["face_forward_m3"][face] or item["stored_whole_run_flux"]["reverse_m3"] != storage["arrays"]["face_reverse_m3"][face]:
                raise ValueError("independent face integral mismatch")
            checked_faces += 1
        del records_chunk
    report = {"schema": "td-basin-spill-verification-v1", "inputs": {"hierarchy": hierarchy_pin, "storage": storage_pin, "reaches": records},
              "spill": pin, "summary": _plain(result["summary"]), "audit": {"passed": True, "checked_faces": checked_faces, "method": "streaming semantic LCA/sill/owner/terminal validation plus per-chunk independent face pair/directional integral check"},
              "flags": _plain(result["flags"]), "flux_scope": _plain(result["flux_scope"]), "limitations": result["limitations"],
              "cold_read_passed": True,
              "implementation_sha256": {name: file_sha256(ROOT / name) for name in ('terrain_pipeline/basin_topology.py', "tests/test_td_basin_spill_network.py", "tools/verify_td_basin_spill_network.py")}}
    report["resources"] = {"peak_process_memory": peak_process_memory(), "json_bytes": path.stat().st_size,
                           "face_json_bytes": sum(chunk["bytes"] for chunk in result["face_chunks"]), "max_chunk_faces": 2048, "budget_bytes": 1024 ** 3}
    report["resources"]["within_1GiB"] = max(report["resources"]["peak_process_memory"].values()) <= 1024 ** 3
    if not report["resources"]["within_1GiB"]:
        publish_bytes(output / "failed-resource.json", json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False).encode())
        raise RuntimeError("resource budget failed; accepted index not published")
    index = {"schema": "td-reach-basin-spill-review-index-v1", "inputs": report["inputs"], "spills": pin,
             "consumer": {"terrain_reach_polylines": "reach package: reaches[].xyz_m", "potential_face_segments": "bundle.face_chunks[].file -> JSON record array -> [].xyz_m (2048 faces maximum; load sequentially)",
                          "catchment_graph": "bundle.contribution_leaf_graph.pairs[]; leaf_ids/all_face_indices/minimum_face_indices/surface_flux_whole_run",
                          "terminal_joins": "reach_cases[].terminal_owner_joins", "hierarchy": "basin_nodes[]",
                          "directional_flux": "face chunk [].stored_whole_run_flux; ordered face_cell_ids. Leaf pair ledger directed leaf_ids[0] to leaf_ids[1]",
                          "render_rule": "Default potential layer shows lowest_allowed_owner_pair_face only (ties retained), not certified escape saddles. All-face adjacency is a separate diagnostic layer, never labelled actual spill outlets. Whole-run measured transfers use a distinct layer. Rejected faces are not traversable. No water surface or channel width inference."},
             "flags": report["flags"], "flux_scope": report["flux_scope"]}
    for name, value in (("report.json", report), ("index.json", index)):
        publish_bytes(output / name, json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False).encode())
    pins = {name: file_sha256(output / name) for name in ("index.json", "report.json", "bundle.json")}
    publish_bytes(output / "pins.json", json.dumps(pins, indent=2).encode())
    print(json.dumps({"output": str(output), "summary": report["summary"], "audit": report["audit"], "pins": pins}, ensure_ascii=False))


if __name__ == "__main__":
    verify()
