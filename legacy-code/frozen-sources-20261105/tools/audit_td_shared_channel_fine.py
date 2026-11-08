"""Streaming independent task15 native sampling and exact affine material audit."""

import argparse
from collections import defaultdict
import gc
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.td_shared_channel_fine_saved_audit import (
    FLAGS, MAX_BYTES, MAX_CELLS, MAX_RSS, MAX_TILES, PARAMETERS, PARAMETERS_SHA256,
    POLICY, POLICY_SHA256, Fan, GlobalGrid, Sum, audit_ledger, audit_tile,
    check_identity, check_memory, checked_path, compare, digest,
    expected_tile_intersections, file_sha256, load_native, read, read_audit,
    require, tile_candidates)

AUDIT_SCHEMA = "td-shared-channel-fine-independent-audit-v1"
CHANNEL_DIR = ROOT / "verification/natural-river-network/shared-port-channel-20261006-01"
CHANNEL_INDEX_SHA256 = "d4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68"
CHANNEL_AUDIT_SHA256 = "54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5"
FINE_CODE = {
    "terrain_pipeline/td_shared_channel_fine.py": "79bac00a25427dcc7285bedde0f047747bc8e34bd45875784300a6b405649dd0",
    "tools/prepare_td_shared_channel_fine.py": "e984f32667fe01bbed9a568bf06d50a222503104f88f0e19b0a3e291603b433a",
    "tests/test_td_shared_channel_fine.py": "730a9bbc375db40de2381985d9ead8192487d96534670a1fd5e9ed478d2f85e1",
}


def capabilities(record):
    for key, value in FLAGS.items():
        require(record.get(key) is value, "saved fine capability differs: " + key)


def identities(record, grid_identity=None):
    require(record["policy_identity_sha256"] == POLICY_SHA256
            and record["parameters_identity_sha256"] == PARAMETERS_SHA256,
            "fine policy/parameters identity differs")
    if grid_identity is not None:
        require(record["grid_identity_sha256"] == grid_identity, "fine grid identity differs")


def code_pins(code, fixed=None):
    for name, expected in (fixed or {}).items():
        require(code.get(name) == expected, "frozen generation code differs: " + name)
    for name, expected in code.items():
        checked_path({"path": str(ROOT / name), "sha256": expected})


def load_channel(binding):
    require(Path(binding["index"]["path"]).resolve() == CHANNEL_DIR / "index.json"
            and binding["index"]["sha256"] == CHANNEL_INDEX_SHA256
            and Path(binding["audit"]["path"]).resolve() == CHANNEL_DIR / "independent-audit-v1.json"
            and binding["audit"]["sha256"] == CHANNEL_AUDIT_SHA256,
            "only fixed actual passed task14 channel is authorized")
    index, audit = read(binding["index"]), read_audit(binding["audit"])
    require(index["schema"] == "td-shared-port-channel-preparation-v1"
            and audit["schema"] == "td-shared-port-channel-independent-audit-v1"
            and audit["status"] == "passed" and audit["errors"] == []
            and audit["index_sha256"] == CHANNEL_INDEX_SHA256
            and audit["inputs"] == index["inputs"] == binding["inputs"]
            and audit["policy_identity_sha256"] == index["policy_identity_sha256"] == binding["policy_identity_sha256"]
            and audit["selected_source_native_functions_verified"] is True
            and audit["complete_actual_reverse_midpoint_functions_verified"] is True,
            "task14 independent acceptance/inputs/policy binding differs")
    artifacts = {}
    require(set(binding["artifacts"]) == {"graph", "selection", "manifest", "mesh", "topology"}, "channel artifact census differs")
    for key, pin in binding["artifacts"].items():
        require(pin == index[key] and audit[key + "_sha256"] == pin["sha256"], "channel artifact binding differs")
        artifacts[key] = read(pin)
    manifest = artifacts["manifest"]
    require(manifest["identity_sha256"] == audit["manifest_identity_sha256"]
            and manifest["inputs"] == binding["inputs"]
            and manifest["selected_node_ids"] == audit["selected_node_ids"], "task14 manifest identity/selection differs")
    for key, field in (("nodes", "node_id"), ("ports", "arc_id")):
        pins = {str(row[field]): {name: row["pin"][name] for name in ("path", "sha256", "identity_sha256")}
                for row in manifest[key]}
        require(len(pins) == len(manifest[key]) and pins == binding[key] == audit[key], "all node/port pins differ from accepted audit")
        for row in manifest[key]:
            record = read(row["pin"])
            require(record[field] == row[field] and record["inputs"] == binding["inputs"], "node/port source identity differs")
            del record
    code_pins(index["code_sha256"])
    for pin in binding["inputs"].values():
        checked_path(pin)
    sections = read(binding["inputs"]["06_sections"])
    protection = read(binding["inputs"]["wet_protection_manifest"])["wet_protection"]
    native = load_native(binding["inputs"]["hierarchy"], sections["selected_leaf_ids"], protection)
    return artifacts, native


def bind_fans(compact, channel_manifest):
    require(compact["schema"] == "td-shared-channel-compact-fans-v1"
            and compact["channel_manifest_identity_sha256"] == channel_manifest["identity_sha256"]
            and compact["selected_node_ids"] == channel_manifest["selected_node_ids"], "compact saved channel identity differs")
    identities(compact)
    saved = {row["fan_key"]: row for row in compact["fans"]}
    require(len(saved) == len(compact["fans"]) == compact["fan_count"] > 0, "duplicate/empty compact fan census")
    fans, seen = {}, set()
    raw_fields = ("vertices_xz_m", "depth_at_vertices_m", "depth_origin_xz_m",
                  "depth_coefficients_m_1xz", "boundary_segment_id")
    for row in channel_manifest["nodes"]:
        if row["composition_status"] != "selected":
            continue
        record = read(row["pin"])
        require(record["status"] == "candidate" and record["rejection_reasons"] == [], "refused node supplied fine")
        for function in record["source_functions"]:
            check_identity(function)
            require(function["status"] == "candidate" and function["rejection_reasons"] == [], "refused function supplied fine")
            for raw in function["fans"]:
                key = raw["fan_id"]
                require(key in saved and key not in seen, "raw fan omitted/duplicated in fine")
                item = saved[key]
                require(item["fan_id"] == key and item["node_id"] == record["node_id"]
                        and item["node_identity_sha256"] == record["identity_sha256"]
                        and item["triangle_id"] == function["triangle_id"]
                        and item["source_function_identity_sha256"] == function["identity_sha256"]
                        and all(item[name] == raw[name] for name in raw_fields), "compact fan altered raw function/geometry")
                fans[key] = Fan(item)
                seen.add(key)
        del record
        gc.collect()
    require(seen == set(saved), "fine contains nonselected/unsaved fans")
    return fans


def audit(index_pin):
    started = time.perf_counter()
    index = read(index_pin)
    require(index["schema"] == "td-shared-channel-fine-preparation-v1"
            and index["status"] == "candidate_unverified" and index["independent_audit_passed"] is False,
            "fine package not an unverified complete candidate")
    capabilities(index)
    code_pins(index["code_sha256"], FINE_CODE)
    artifacts, native = load_channel(index["channel"])
    manifest, compact, material = (read(index[name]) for name in ("manifest", "compact_fans", "material"))
    grid = manifest["grid"]
    expected_grid = {"origin_m_xz": native.origin.tolist(), "spacing_m": .175, "tile_cells": 64,
        "array_order": "rows_z_columns_x", "cell_center": "origin+(global_col+0.5,global_row+0.5)*spacing",
        "sparse_scope": "all_positive_area_saved_fan_intersections_not_only_center_covered_cells"}
    require(grid == expected_grid and manifest["grid_identity_sha256"] == digest(grid), "fixed native fine grid differs")
    grid_identity = digest(grid)
    for record in (index, manifest, material):
        identities(record, grid_identity)
        capabilities(record)
    require(manifest["schema"] == "td-shared-channel-fine-v1"
            and manifest["status"] == "candidate_unverified" and manifest["rejection_reasons"] == []
            and manifest["policy"] == POLICY and manifest["parameters"] == PARAMETERS
            and manifest["all_or_none"] is True and manifest["independent_audit_passed"] is False
            and manifest["channel"] == index["channel"]
            and manifest["compact_fans"] == index["compact_fans"] and manifest["material"] == index["material"],
            "fine manifest policy/parents/completeness differs")
    for key in ("open_ports", "terminal_open_ports"):
        require(manifest[key] == artifacts["topology"][key], "fine changed original open ports")
    require(manifest["channel_refusals"] == [row for row in artifacts["manifest"]["nodes"] if row["composition_status"] != "selected"], "fine changed channel refusals")
    fans = bind_fans(compact, artifacts["manifest"])
    require(material["schema"] == "td-shared-channel-fine-material-v1"
            and material["fans_identity_sha256"] == compact["identity_sha256"]
            and material["channel_manifest_identity_sha256"] == artifacts["manifest"]["identity_sha256"]
            and material["cutrock_all_exported"] is True and material["center_volume_is_not_material_ledger"] is True,
            "material semantics/parent binding differs")
    candidates, visits = tile_candidates(fans, grid)
    rows = manifest["tiles"]
    row_keys = [tuple(row["tile_row_column"]) for row in rows]
    require(row_keys == sorted(set(row_keys)) and len(rows) <= MAX_TILES
            and all(key in candidates for key in row_keys), "tile census duplicate/foreign/unsorted")
    by_tile = dict(zip(row_keys, rows))
    global_grid = GlobalGrid(grid)
    totals = defaultdict(lambda: [Sum(), Sum()])
    total_volume, total_center = Sum(), Sum()
    contribution_count = outside_centers = invalid_centers = 0
    peak = check_memory()
    for key in sorted(candidates):
        expected = expected_tile_intersections(fans, candidates[key], key, grid)
        if not expected:
            require(key not in by_tile, "empty tile retained")
            continue
        require(key in by_tile, "whole positive-area tile omitted")
        row = by_tile[key]
        tile = read(row["pin"])
        require(tile["schema"] == "td-shared-channel-fine-tile-v1"
                and tile["status"] == "candidate_unverified" and tuple(tile["tile_row_column"]) == key
                and tile["fans_identity_sha256"] == compact["identity_sha256"]
                and tile["material_semantics"] == "exact_affine_polygon_integral_not_center_depth_times_full_cell_area",
                "tile schema/status/fan/material binding differs")
        identities(tile, grid_identity)
        capabilities(tile)
        result = audit_tile(tile, fans, expected, native, global_grid)
        require(row["cell_count"] == result["cell_count"] and row["contribution_count"] == result["contribution_count"], "tile manifest count differs")
        for fan_key, values in result["fan_integrals"].items():
            for accumulator, value in zip(totals[fan_key], values):
                accumulator.add(value)
        total_volume.add(result["integrated_cut_m3"])
        total_center.add(result["center_sample_cut_volume_m3"])
        contribution_count += result["contribution_count"]
        outside_centers += result["outside_fan_centers"]
        invalid_centers += result["invalid_outside_centers"]
        peak = max(peak, check_memory())
        print(json.dumps({"tile_row_column": key, "verified_cells": global_grid.cell_count}), flush=True)
        del tile, expected, result
    require(set(totals) == set(fans) and global_grid.tiles == set(row_keys), "whole fan/tile coverage incomplete")
    material_fans = {item["fan_key"]: item for item in material["fan_integrals"]}
    require(len(material_fans) == len(material["fan_integrals"]) and set(material_fans) == set(fans), "material fan census differs")
    max_area_residual = max_cut_residual = 0.
    for key, fan in fans.items():
        area, volume = (accumulator.total() for accumulator in totals[key])
        compare(area, fan.area, "whole saved fan area conserved", atol=1e-8, rtol=1e-9)
        compare(volume, fan.volume, "whole saved fan cut conserved", atol=1e-8, rtol=1e-9)
        item = material_fans[key]
        require(item["fan_id"] == fan.saved["fan_id"], "material raw fan identity differs")
        for name, value in (("coverage_area_m2", area), ("integrated_cut_m3", volume),
                            ("area_residual_m2", area-fan.area), ("cut_residual_m3", volume-fan.volume)):
            compare(item[name], value, "whole material fan " + name, atol=1e-8, rtol=1e-9)
        max_area_residual = max(max_area_residual, abs(area-fan.area))
        max_cut_residual = max(max_cut_residual, abs(volume-fan.volume))
    volume, center = total_volume.total(), total_center.total()
    area = math.fsum(accumulators[0].total() for accumulators in totals.values())
    audit_ledger(material["material_ledger"], volume)
    for name, value in (("center_sample_cut_volume_m3", center), ("actual_coverage_area_m2", area),
                        ("expected_saved_fan_cut_m3", math.fsum(fan.volume for fan in fans.values()))):
        compare(material[name], value, "material global " + name, atol=1e-8, rtol=1e-9)
    summary = {"cell_count": global_grid.cell_count, "tile_count": len(rows), "fan_count": len(fans),
               "integrated_cut_m3": volume, "center_sample_cut_volume_m3": center}
    for key, value in summary.items():
        if key.endswith("count"):
            require(index["summary"][key] == value, "index count differs")
        else:
            compare(index["summary"][key], value, "index " + key, atol=1e-8, rtol=1e-9)
    require(manifest["cell_count"] == global_grid.cell_count and manifest["fan_count"] == len(fans), "manifest global count differs")
    resource = index["resource"]
    require(resource["max_cells"] == MAX_CELLS and resource["max_tiles"] == MAX_TILES
            and resource["max_json_bytes"] == MAX_BYTES and resource["max_rss_bytes"] == MAX_RSS
            and 0 <= resource["actual_peak_rss_bytes"] <= MAX_RSS
            and resource["preflight_bbox_cell_visits"] == visits
            and resource["solver_calls"] == 0 and resource["old_packages_modified"] is False,
            "saved resource budget/scope differs")
    result = {"schema": AUDIT_SCHEMA, "status": "passed", "errors": [],
        "index": index_pin, "index_sha256": index_pin["sha256"], "index_identity_sha256": index["identity_sha256"],
        "channel": index["channel"], "inputs": index["channel"]["inputs"],
        "policy_identity_sha256": POLICY_SHA256, "parameters_identity_sha256": PARAMETERS_SHA256,
        "grid_identity_sha256": grid_identity, "tiles": rows, "summary": summary,
        "coverage_area_m2": area, "contribution_count": contribution_count,
        "outside_fan_centers": outside_centers, "invalid_unchanged_outside_centers": invalid_centers,
        "max_fan_area_residual_m2": max_area_residual, "max_fan_cut_residual_m3": max_cut_residual,
        "native_source_and_center_bed_verified": True, "unique_global_grid_verified": True,
        "complete_saved_fan_cell_intersections_verified": True, "affine_material_integrals_verified": True,
        "material_budget_verified": True, "fine_generated": True,
        "hydraulic_ready": False, "hydraulic_solved": False, "full_network_verified": False,
        "natural_outlet_certified": False, "old_source_changed": False, "old_fine_changed": False,
        "scope": "bounded task14 derived sparse fine and affine excavation only; not N4 or hydraulic certification",
        "resource": {"actual_peak_audit_rss_bytes": max(peak, check_memory()), "max_rss_bytes": MAX_RSS,
            "max_json_bytes": MAX_BYTES, "max_cells": MAX_CELLS, "solver_calls": 0, "elapsed_s": time.perf_counter()-started}}
    for key in ("manifest", "compact_fans", "material"):
        result[key] = index[key]
        result[key + "_sha256"] = index[key]["sha256"]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-schema", choices=[AUDIT_SCHEMA], default=AUDIT_SCHEMA)
    args = parser.parse_args()
    output = args.output.resolve()
    require(not output.exists() and output.is_relative_to(ROOT / "verification/natural-river-network"), "new verification audit output required")
    result = audit({"path": str(args.input.resolve()), "sha256": args.sha256})
    result["audit_code_sha256"] = {name: file_sha256(ROOT / name) for name in (
        "tools/audit_td_shared_channel_fine.py", "tools/td_shared_channel_fine_saved_audit.py",
        "tests/test_td_shared_channel_fine_saved_audit.py")}
    result["identity_sha256"] = digest(result)
    payload = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "audit output exceeds 64MiB")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"status": result["status"], "summary": result["summary"]}))


if __name__ == "__main__":
    main()
