"""Prepare task15 tiles only from the fixed, independently passed task14 package."""

import argparse
from collections import defaultdict
import gc
import json
from pathlib import Path
import sys
import tempfile
import time
import math

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.common_infra import file_sha256
from terrain_pipeline.basin_topology import load_basin_hierarchy as load_basin_hierarchy
from terrain_pipeline import channel_geometry as source
from terrain_pipeline.td_shared_channel_fine import (
    FLAGS, MAX_BYTES, MAX_CELLS, MAX_RSS, MAX_TILES, PARAMETERS, PARAMETERS_IDENTITY_SHA256,
    POLICY, POLICY_IDENTITY_SHA256, SCHEMA, SPACING_M, TILE_CELLS, BudgetExceeded,
    build_tile, compact_node_fans, material_ledger, plan_tiles, seal, verify_integral_conservation)
from terrain_pipeline.td_ported_network_composition import check_memory
from tools.prepare_td_ported_junction import FROZEN_HELPERS, VERIFICATION
from tools.prepare_td_ported_network_composition import FROZEN_JUNCTION, _pin, _save
from tools.prepare_td_shared_port_channel import FROZEN_COMPOSITION

CHANNEL_DIR = VERIFICATION / "shared-port-channel-20261006-01"
CHANNEL_INDEX_SHA256 = "d4b2e125b54137de40d4ecfab4cc72f1252afb4f96c82858eafa9298d04e1d68"
CHANNEL_AUDIT_SHA256 = "54e7577d6c3e0c75836003c9092e5e5dc70f6a96872238c4d1eb7f2f216845d5"
CHANNEL_CODE = {
    "terrain_pipeline/td_shared_port_channel.py": "fa44c986240480975934c494aa02443d81fc063c18634d9fa65bd47909aadcc8",
    "tools/prepare_td_shared_port_channel.py": "bc6e116bf31d358c3af075df3592bf0a6f359d5f01a8b87ced1c2cccf19ae9b2",
    "tests/test_td_shared_port_channel.py": "831683a43dc50f3ee93e7ce62e359e31d320b6881075e3d75dd53c5c759fc586",
}
CODE_FILES = ("terrain_pipeline/td_shared_channel_fine.py", "tools/prepare_td_shared_channel_fine.py",
    "tests/test_td_shared_channel_fine.py")


def read_pin(pin, *, identity=True):
    path = Path(pin["path"]).resolve(strict=True)
    if (not path.is_relative_to(ROOT) or path.stat().st_size > MAX_BYTES
            or file_sha256(path) != pin["sha256"]
            or "bytes" in pin and path.stat().st_size != pin["bytes"]):
        raise ValueError("saved parent path/bytes/SHA mismatch: " + str(path))
    record = json.loads(path.read_bytes())
    if identity:
        source._check_identity(record)
        if "identity_sha256" in pin and pin["identity_sha256"] != record["identity_sha256"]:
            raise ValueError("saved parent identity mismatch")
    return record


def _binding(pin):
    return {key: pin[key] for key in ("path", "sha256", "identity_sha256")}


def load_channel(index_pin, audit_pin):
    if index_pin["sha256"] != CHANNEL_INDEX_SHA256 or audit_pin["sha256"] != CHANNEL_AUDIT_SHA256:
        raise ValueError("only the fixed actual passed task14 package is authorized")
    index, audit = read_pin(index_pin), read_pin(audit_pin, identity=False)
    if (index["schema"] != "td-shared-port-channel-preparation-v1"
            or audit["schema"] != "td-shared-port-channel-independent-audit-v1"
            or audit["status"] != "passed" or audit.get("errors")
            or audit["index_sha256"] != index_pin["sha256"]
            or audit["inputs"] != index["inputs"] or audit["policy_identity_sha256"] != index["policy_identity_sha256"]):
        raise ValueError("task14 passed audit/index/inputs/policy linkage invalid")
    artifacts = {}
    for key in ("graph", "selection", "manifest", "mesh", "topology"):
        record = read_pin(index[key])
        if audit[key + "_sha256"] != index[key]["sha256"]:
            raise ValueError("task14 audit artifact pin mismatch: " + key)
        artifacts[key] = record
    manifest = artifacts["manifest"]
    if (audit["manifest_identity_sha256"] != manifest["identity_sha256"]
            or audit["selected_node_ids"] != manifest["selected_node_ids"]
            or manifest["inputs"] != index["inputs"]
            or not audit["selected_source_native_functions_verified"]
            or not audit["complete_actual_reverse_midpoint_functions_verified"]):
        raise ValueError("accepted node/native function audit binding mismatch")
    for key, field in (("nodes", "node_id"), ("ports", "arc_id")):
        bindings = {row[field]: _binding(row["pin"]) for row in manifest[key]}
        if bindings != audit[key]:
            raise ValueError("all task14 node/port bindings differ from passed audit")
        for row in manifest[key]:
            record = read_pin(row["pin"])
            if record[field] != row[field] or record["inputs"] != index["inputs"]:
                raise ValueError("task14 saved node/port provenance mismatch")
            del record
    for name, expected in index["code_sha256"].items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("frozen task14 code changed: " + name)
    inputs = index["inputs"]
    for pin in inputs.values():
        path = Path(pin["path"]).resolve(strict=True)
        if not path.is_relative_to(ROOT) or file_sha256(path) != pin["sha256"]:
            raise ValueError("original source parent pin mismatch")
    hierarchy_pin = inputs["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]), expected_sha256=hierarchy_pin["sha256"],
        expected_identity=hierarchy_pin["identity_sha256"])
    sections = read_pin(inputs["06_sections"])
    protection = read_pin(inputs["wet_protection_manifest"])["wet_protection"]
    context = source._i46__context(hierarchy, sections["selected_leaf_ids"], protection)
    return index, audit, artifacts, context


def prepare(output, *, channel_index=CHANNEL_DIR / "index.json", channel_index_sha256=CHANNEL_INDEX_SHA256,
            channel_audit=CHANNEL_DIR / "independent-audit-v1.json", channel_audit_sha256=CHANNEL_AUDIT_SHA256):
    output = Path(output).resolve()
    if output.exists() or output == VERIFICATION.resolve() or not output.is_relative_to(VERIFICATION.resolve()):
        raise ValueError("new fine verification subdirectory required")
    started = time.perf_counter()
    frozen = {**FROZEN_HELPERS, **FROZEN_JUNCTION, **FROZEN_COMPOSITION, **CHANNEL_CODE}
    for name, expected in frozen.items():
        if file_sha256(ROOT / name) != expected:
            raise ValueError("frozen readonly dependency changed: " + name)
    index_pin = {"path": str(Path(channel_index).resolve()), "sha256": channel_index_sha256}
    audit_pin = {"path": str(Path(channel_audit).resolve()), "sha256": channel_audit_sha256}
    channel, audit, artifacts, context = load_channel(index_pin, audit_pin)
    channel_manifest = artifacts["manifest"]
    parent_binding = {"index": index_pin, "audit": audit_pin,
        "artifacts": {key: channel[key] for key in artifacts}, "inputs": channel["inputs"],
        "nodes": audit["nodes"], "ports": audit["ports"], "policy_identity_sha256": channel["policy_identity_sha256"]}
    compact = []
    for row in channel_manifest["nodes"]:
        if row["composition_status"] != "selected":
            continue
        record = read_pin(row["pin"])
        compact.extend(compact_node_fans(record))
        del record
        gc.collect()
    fan_record = seal({"schema": "td-shared-channel-compact-fans-v1", "policy_identity_sha256": POLICY_IDENTITY_SHA256,
        "parameters_identity_sha256": PARAMETERS_IDENTITY_SHA256,
        "channel_manifest_identity_sha256": channel_manifest["identity_sha256"],
        "fans": compact, "fan_count": len(compact), "selected_node_ids": channel_manifest["selected_node_ids"]})
    grid = {"origin_m_xz": context["origin"].tolist(), "spacing_m": SPACING_M, "tile_cells": TILE_CELLS,
        "array_order": "rows_z_columns_x", "cell_center": "origin+(global_col+0.5,global_row+0.5)*spacing",
        "sparse_scope": "all_positive_area_saved_fan_intersections_not_only_center_covered_cells"}
    grid_identity = source._record_identity(grid)
    peak = check_memory()
    code = {name: file_sha256(ROOT / name) for name in CODE_FILES + tuple(frozen)}
    try:
        plan = plan_tiles(compact, grid)
    except BudgetExceeded as error:
        output.mkdir(parents=True)
        manifest = seal({"schema": SCHEMA, "status": "refused", "rejection_reasons": [str(error)],
            "policy": POLICY, "policy_identity_sha256": POLICY_IDENTITY_SHA256, "parameters": PARAMETERS,
            "parameters_identity_sha256": PARAMETERS_IDENTITY_SHA256, "grid": grid, "grid_identity_sha256": grid_identity,
            "channel": parent_binding, "tiles": [], "all_or_none": True, "material_ledger": None,
            **{**FLAGS, "fine_generated": False}})
        _save(manifest, output / "manifest.json")
        result = seal({"schema": "td-shared-channel-fine-preparation-v1", "status": "refused", "channel": parent_binding,
            "manifest": _pin(output / "manifest.json", output / "manifest.json", manifest), "code_sha256": code,
            "rejection_reasons": [str(error)], "resource": {"max_cells": MAX_CELLS, "max_rss_bytes": MAX_RSS,
                "actual_peak_rss_bytes": peak, "max_json_bytes": MAX_BYTES, "solver_calls": 0},
            **{**FLAGS, "fine_generated": False}})
        _save(result, output / "index.json")
        return result
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".shared-channel-fine-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        _save(fan_record, staging / "compact_fans.json")
        fan_pin = _pin(staging / "compact_fans.json", output / "compact_fans.json", fan_record)
        tiles, accumulated = [], defaultdict(lambda: [[], []])
        center_volumes, tile_volumes = [], []
        count = 0
        for ordinal, tile_key in enumerate(sorted(plan["tile_masks"])):
            record = build_tile(compact, plan, tile_key, grid, context, fan_parent_identity=fan_record["identity_sha256"])
            relative = Path("tiles") / (str(ordinal).zfill(5) + ".json")
            _save(record, staging / relative)
            pin = _pin(staging / relative, output / relative, record)
            tiles.append({"tile_row_column": list(tile_key), "cell_count": len(record["cells"]),
                "contribution_count": len(record["contributions"]), "pin": pin})
            for integral in record["fan_integrals"]:
                accumulated[integral["fan_key"]][0].append(integral["coverage_area_m2"])
                accumulated[integral["fan_key"]][1].append(integral["integrated_cut_m3"])
            center_volumes.append(record["center_sample_cut_volume_m3"])
            tile_volumes.append(record["material_ledger"]["cut_rock_m3"])
            count += len(record["cells"])
            peak = max(peak, check_memory())
            print(json.dumps({"ordinal": ordinal, "tile_row_column": list(tile_key), "cells": len(record["cells"])}), flush=True)
            del record
        if count != plan["unique_cell_count"]:
            raise ValueError("whole-package cell count differs from preflight")
        integrals = verify_integral_conservation(compact, accumulated)
        total_cut = math.fsum(tile_volumes)
        material = seal({"schema": "td-shared-channel-fine-material-v1", "policy_identity_sha256": POLICY_IDENTITY_SHA256,
            "parameters_identity_sha256": PARAMETERS_IDENTITY_SHA256, "grid_identity_sha256": grid_identity,
            "fans_identity_sha256": fan_record["identity_sha256"], "channel_manifest_identity_sha256": channel_manifest["identity_sha256"],
            "material_ledger": material_ledger(total_cut), "fan_integrals": integrals,
            "center_sample_cut_volume_m3": math.fsum(center_volumes),
            "expected_saved_fan_cut_m3": math.fsum(fan["expected_integrated_cut_m3"] for fan in compact),
            "actual_coverage_area_m2": math.fsum(item["coverage_area_m2"] for item in integrals),
            "cutrock_all_exported": True, "center_volume_is_not_material_ledger": True, **FLAGS})
        _save(material, staging / "material.json")
        material_pin = _pin(staging / "material.json", output / "material.json", material)
        manifest = seal({"schema": SCHEMA, "status": "candidate_unverified", "rejection_reasons": [],
            "policy": POLICY, "policy_identity_sha256": POLICY_IDENTITY_SHA256,
            "parameters": PARAMETERS, "parameters_identity_sha256": PARAMETERS_IDENTITY_SHA256,
            "grid": grid, "grid_identity_sha256": grid_identity, "channel": parent_binding,
            "compact_fans": fan_pin, "material": material_pin, "tiles": tiles,
            "cell_count": count, "fan_count": len(compact), "all_or_none": True,
            "open_ports": artifacts["topology"]["open_ports"], "terminal_open_ports": artifacts["topology"]["terminal_open_ports"],
            "channel_refusals": [row for row in channel_manifest["nodes"] if row["composition_status"] != "selected"],
            "independent_audit_passed": False, **FLAGS})
        _save(manifest, staging / "manifest.json")
        result = seal({"schema": "td-shared-channel-fine-preparation-v1", "status": "candidate_unverified",
            "channel": parent_binding, "policy_identity_sha256": POLICY_IDENTITY_SHA256,
            "parameters_identity_sha256": PARAMETERS_IDENTITY_SHA256, "grid_identity_sha256": grid_identity,
            "manifest": _pin(staging / "manifest.json", output / "manifest.json", manifest),
            "compact_fans": fan_pin, "material": material_pin, "code_sha256": code,
            "summary": {"cell_count": count, "tile_count": len(tiles), "fan_count": len(compact),
                "integrated_cut_m3": total_cut, "center_sample_cut_volume_m3": material["center_sample_cut_volume_m3"]},
            "resource": {"actual_peak_rss_bytes": max(peak, check_memory()), "max_rss_bytes": MAX_RSS,
                "max_json_bytes": MAX_BYTES, "max_cells": MAX_CELLS, "max_tiles": MAX_TILES,
                "preflight_bbox_cell_visits": plan["bbox_cell_visits"], "elapsed_s": time.perf_counter() - started,
                "solver_calls": 0, "old_packages_modified": False,
                "raw_retention": "compact_fans_plus_one_node_or_one_tile_never_all_raw_node_functions"},
            "independent_audit_passed": False, **FLAGS})
        _save(result, staging / "index.json")
        staging.rename(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--channel-index", type=Path, default=CHANNEL_DIR / "index.json")
    parser.add_argument("--channel-index-sha256", default=CHANNEL_INDEX_SHA256)
    parser.add_argument("--channel-audit", type=Path, default=CHANNEL_DIR / "independent-audit-v1.json")
    parser.add_argument("--channel-audit-sha256", default=CHANNEL_AUDIT_SHA256)
    args = parser.parse_args()
    result = prepare(args.output, channel_index=args.channel_index, channel_index_sha256=args.channel_index_sha256,
        channel_audit=args.channel_audit, channel_audit_sha256=args.channel_audit_sha256)
    print(json.dumps({"status": result["status"], "summary": result.get("summary"),
        "rejection_reasons": result.get("rejection_reasons", [])}))


if __name__ == "__main__":
    main()
