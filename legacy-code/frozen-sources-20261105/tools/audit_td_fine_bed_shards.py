"""Independently audit append-only fine cells, native sources and material deltas."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy
from tools.audit_td_fine_bed_raster import _source
from tools.td_entry_saved_audit import assert_close


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(pin, *, content_identity=True):
    path = Path(pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > 64*1024**2 or file_sha256(path) != pin["sha256"]:
        raise ValueError("shard cold-read file SHA/path/byte mismatch")
    result = json.loads(path.read_text(encoding="utf8"))
    if content_identity and "identity_sha256" in result:
        if digest({key: value for key, value in result.items() if key != "identity_sha256"}) != result["identity_sha256"]:
            raise ValueError("shard content identity mismatch")
    if "identity_sha256" in pin and result["identity_sha256"] != pin["identity_sha256"]:
        raise ValueError("shard external identity mismatch")
    return result


def check_memory():
    memory = psutil.Process().memory_info()
    peak = max(memory.rss, getattr(memory, "peak_wset", 0))
    if peak > 1024**3:
        raise MemoryError("shard independent audit exceeds 1GiB")
    return peak


def cut_volume(cell, spacing):
    if cell is None or cell["status"] != "candidate":
        return 0.
    return max(0., cell["source_sample"]["height_m"]-cell["derived_bed_m"])*spacing**2


def audit(index):
    for name, sha256 in index["code_sha256"].items():
        if file_sha256(ROOT/name) != sha256:
            raise ValueError("shard preparation code changed")
    base, raw, manifest = (read(index[key]) for key in ("shard0", "raw", "manifest"))
    base_audit = read(index["inputs"]["base_independent_audit"])
    if base_audit["status"] != "passed" or base_audit["raster_sha256"] != index["shard0"]["sha256"]:
        raise ValueError("immutable shard0 independent audit missing")
    if raw["base_identity_sha256"] != base["identity_sha256"] or manifest["base_identity_sha256"] != base["identity_sha256"] or manifest["raw_identity_sha256"] != raw["identity_sha256"]:
        raise ValueError("shard identity linkage mismatch")
    for name in ("grid", "selection", "parameters", "selected_leaf_ids", "wet_protection"):
        if raw[name] != base[name]:
            raise ValueError("shard parent lattice/geometry parameters changed")
    hierarchy_pin = index["inputs"]["hierarchy"]
    hierarchy = load_basin_hierarchy(hierarchy_pin["path"], expected_sha256=hierarchy_pin["sha256"], expected_identity=hierarchy_pin["identity_sha256"])
    selected = set(base["selected_leaf_ids"])
    spacing, tile = base["grid"]["spacing_m"], base["grid"]["tile_cells"]
    origin = np.array(base["grid"]["origin_m_xz"])
    cells = {}
    for window in base["windows"]:
        row_base, column_base = window["global_origin_row_column"]
        for cell in window["cells"]:
            key = (row_base+cell["local_index"]//tile, column_base+cell["local_index"]%tile)
            if key in cells:
                raise ValueError("immutable base global cell duplicated")
            cells[key] = cell
    original = {item["triangle_id"]: item for item in base["triangles"]}
    expected_retry = {identifier for identifier, item in original.items() if item["status"] == "refused" and item["rejection_reasons"] == ["raster_byte_reservation_exceeded"]}
    retried = {item["triangle_id"]: item for item in raw["triangles"]}
    if len(retried) != len(raw["triangles"]) or set(retried) != expected_retry:
        raise ValueError("shard retried unexpected or omitted original triangles")
    for identifier, triangle in retried.items():
        for name in ("vertices_xyz_m", "source_package", "source_triangle_index", "source_vertex_indices", "source_entry_index", "source_arc_id"):
            if triangle.get(name) != original[identifier].get(name):
                raise ValueError("shard original triangle index/mesh changed")
    triangles = dict(original, **retried)
    coverage, operations, reasons_count = Counter(), Counter(), Counter()
    changed_keys, shard_deltas = set(), []
    wet_cells = set(base["wet_protection"]["covered_native_cell_ids"])
    stages = {item["leaf_id"]: item["stage_m"] for item in base["wet_protection"]["stage_by_leaf"]}
    tolerance = base["parameters"]["conflict_tolerance_m"]
    for shard_number, pin in enumerate(index["shards"]):
        shard = read(pin)
        if shard["identity_sha256"] != manifest["shard_identities"][shard_number] or shard["raw_identity_sha256"] != raw["identity_sha256"] or shard["base_identity_sha256"] != base["identity_sha256"]:
            raise ValueError("shard identity chain changed")
        deltas = []
        for transaction in shard["transactions"]:
            key = tuple(transaction["global_key_row_column"])
            if key in changed_keys:
                raise ValueError("shared global cell transacted more than once")
            changed_keys.add(key)
            before = cells.get(key)
            operation = "replace" if before is not None else "insert"
            if transaction["operation"] != operation or transaction["before_sha256"] != (digest(before) if before else None):
                raise ValueError("atomic replacement before hash or collision mismatch")
            owner = "shard0" if before is not None else shard["shard_id"]
            if transaction["logical_owner"] != owner:
                raise ValueError("duplicate/wrong logical shard owner")
            cell = transaction["cell"]
            row, column = key
            xz = origin+(np.array([column, row])+.5)*spacing
            source, reasons, provenance = _source(hierarchy["arrays"], hierarchy["metadata"], selected, xz)
            for name, value in provenance.items():
                assert_close(cell["source_sample"][name], value, "native provenance "+name, atol=1e-12)
            assert_close(cell["source_sample"]["height_m"], source, "original native source")
            nearest = np.floor((xz-origin)/hierarchy["metadata"]["spacing_m"]+.5).astype(int)
            nearest_cell = int(nearest[1]*hierarchy["arrays"]["height_m"].shape[1]+nearest[0])
            leaf = int(hierarchy["arrays"]["contribution_owner"][nearest[1], nearest[0]])
            wet = nearest_cell in wet_cells or source < stages.get(leaf, -math.inf)
            if cell["source_sample"]["wet_source_support"] != bool(wet):
                raise ValueError("shard wet protection changed")
            targets, proposals = [], {}
            for proposal in cell["triangle_sources"]:
                identifier = proposal["triangle_id"]
                if identifier in proposals:
                    raise ValueError("duplicate triangle at shared fine cell")
                proposals[identifier] = proposal
                triangle = triangles[identifier]
                if triangle["status"] != "rasterized":
                    raise ValueError("refused triangle contributed to shard")
                vertices = np.array(triangle["vertices_xyz_m"])
                matrix = np.vstack((vertices[:, 0]-xz[0], vertices[:, 2]-xz[1], np.ones(3)))
                weights = np.linalg.solve(matrix, [0., 0., 1.])
                if weights.min() < -1e-8:
                    raise ValueError("saved shard cell outside parent triangle")
                assert_close(proposal["weights"], weights, "triangle weights")
                assert_close(proposal["bed_m"], weights @ vertices[:, 1], "triangle bed")
                targets.append(proposal["bed_m"])
                if identifier in retried:
                    coverage[identifier] += 1
            if before and any(proposals.get(item["triangle_id"]) != item for item in before["triangle_sources"]):
                raise ValueError("shard lost immutable old proposal")
            if not proposals or not set(proposals).intersection(retried):
                raise ValueError("transaction without actual new coverage")
            if max(targets)-min(targets) > tolerance:
                reasons.append("conflicting_triangle_overlap")
            if source-min(targets) > base["parameters"]["max_cut_m"]+tolerance:
                reasons.append("cut_depth_exceeded")
            if max(targets) > source+tolerance:
                reasons.append("fill_without_material")
            if wet and source-min(targets) > tolerance:
                reasons.append("lake_wet_bed_cut_refused")
            reasons = sorted(set(reasons))
            if cell["rejection_reasons"] != reasons or cell["status"] != ("refused" if reasons else "candidate"):
                raise ValueError("shard source/geometry no-fill gate mismatch")
            expected_bed = source if reasons else min(source, math.fsum(targets)/len(targets))
            assert_close(cell["derived_bed_m"], expected_bed, "derived cut bed or refusal rollback")
            if cell["local_index"] != (row % tile)*tile+column % tile:
                raise ValueError("shard local/global index mismatch")
            before_cut, after_cut = cut_volume(before, spacing), cut_volume(cell, spacing)
            assert_close(transaction["before_cut_m3"], before_cut, "material before")
            assert_close(transaction["after_cut_m3"], after_cut, "material after")
            assert_close(transaction["cut_delta_m3"], after_cut-before_cut, "signed material replacement delta")
            deltas.append(after_cut-before_cut)
            operations[operation] += 1
            cells[key] = cell
        delta = math.fsum(deltas)
        for name, value in shard["material_ledger_delta"].items():
            assert_close(value, delta if name in ("cut_rock_m3", "exported_excavated_rock_m3") else 0., "shard material ledger")
        shard_deltas.append(delta)
        check_memory()
    for identifier, triangle in retried.items():
        if triangle["status"] == "rasterized" and coverage[identifier] != triangle["covered_centers"]:
            raise ValueError("shard original triangle coverage missing")
    if len(cells) != manifest["summary"]["merged_cells"] or len(cells) > 2_000_000:
        raise ValueError("merged unique-cell budget/count mismatch")
    total_cut = math.fsum(cut_volume(cell, spacing) for cell in cells.values())
    assert_close(total_cut, base["material_ledger"]["cut_rock_m3"]+math.fsum(shard_deltas), "global material delta not double counted")
    for name, value in manifest["material_ledger_merged"].items():
        assert_close(value, total_cut if name in ("cut_rock_m3", "exported_excavated_rock_m3") else 0., "merged material ledger")
    resource = index["resource"]
    if resource["peak_rss_bytes"] > 1024**3 or any(resource[name] != 0 for name in ("water_solves", "forest_rebuilds", "base_rasterizations")):
        raise ValueError("shard resource or unnecessary recomputation mismatch")
    transitions = read(index["inputs"]["09_transitions"])
    cells_by_triangle = defaultdict(set)
    for key, cell in cells.items():
        reasons_count.update(cell["rejection_reasons"])
        for proposal in cell["triangle_sources"]:
            cells_by_triangle[proposal["triangle_id"]].add(key)
    entry_triangles, port_triangles = defaultdict(list), defaultdict(list)
    for triangle in triangles.values():
        if triangle["source_package"] == "09":
            entry_triangles[triangle["source_entry_index"]].append(triangle)
        else:
            port_triangles[triangle["source_arc_id"]].append(triangle)
    requests = []
    for entry_index, entry in enumerate(transitions["entries"]):
        if entry["status"] != "candidate":
            requests.append(dict(entry_id=entry["entry_id"], status="parent_refused", reasons=entry["rejection_reasons"]))
            continue
        local = entry_triangles[entry_index]+port_triangles[entry["accepted_port_arc_id"]]
        keys = set().union(*(cells_by_triangle[item["triangle_id"]] for item in local))
        refused = [cells[key] for key in keys if cells[key]["status"] != "candidate"]
        complete = bool(keys) and len(entry_triangles[entry_index]) == len(entry["triangles"]) and bool(port_triangles[entry["accepted_port_arc_id"]]) and not refused and not any(item["rejection_reasons"] for item in local)
        requests.append(dict(entry_id=entry["entry_id"], status="geometry_diagnostic_complete" if complete else "pending",
                             covered_centers=len(keys), refused_centers=len(refused), hydraulic_ready=False,
                             cell_refusals=dict(Counter(reason for cell in refused for reason in cell["rejection_reasons"]))))
    return dict(schema="td-fine-bed-shards-independent-audit-v1", status="passed", manifest_sha256=index["manifest"]["sha256"],
                base_raster_sha256=index["shard0"]["sha256"], raw_sha256=index["raw"]["sha256"],
                checked_new_transactions=len(changed_keys), merged_unique_cells=len(cells), operation_counts=dict(operations),
                cut_rock_m3=total_cut, refusal_counts=dict(reasons_count), material_ledger=manifest["material_ledger_merged"],
                readiness=dict(summary=dict(Counter(item["status"] for item in requests)), requests=requests),
                actual_peak_rss_bytes=check_memory(), water_solves=0, parent_rasterizations=0,
                native_source_verified=True, unique_ownership_verified=True, signed_material_deltas_verified=True,
                whole_entry_center_readiness_verified=True, natural_outlet_verified=False, full_watershed_fine_verified=False,
                cross_shard_hydraulics_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/"verification/natural-river-network"):
        raise ValueError("new shard independent audit output required")
    result = audit(read({"path": str(args.input.resolve()), "sha256": args.sha256}))
    result["index_sha256"] = args.sha256
    result["audit_code_sha256"] = file_sha256(Path(__file__))
    publish_bytes(output, (json.dumps(result, sort_keys=True, indent=2, allow_nan=False)+"\n").encode())
    print(json.dumps({key: result[key] for key in ("status", "checked_new_transactions", "merged_unique_cells", "cut_rock_m3", "refusal_counts", "actual_peak_rss_bytes")}))
    print(json.dumps(result["readiness"]["summary"]))


if __name__ == "__main__":
    main()
