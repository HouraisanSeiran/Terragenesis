"""Whole-entry gates on saved fine coverage, without solving or regenerating."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes


def assess(directory):
    manifest = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    raster_pin = manifest["raster"]
    raster_path = Path(raster_pin["path"])
    if file_sha256(raster_path) != raster_pin["sha256"] or raster_path.stat().st_size > 64 * 1024**2:
        raise ValueError("raster SHA/budget mismatch")
    record = json.loads(raster_path.read_text(encoding="utf-8"))
    audit_path = directory / "independent-audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["status"] != "passed" or audit["raster_identity_sha256"] != record["identity_sha256"] or audit["raster_sha256"] != raster_pin["sha256"]:
        raise ValueError("independent source audit required")
    pin = manifest["inputs"]["09_transitions"]
    transition_path = Path(pin["path"])
    if file_sha256(transition_path) != pin["sha256"]:
        raise ValueError("transition SHA mismatch")
    transitions = json.loads(transition_path.read_text(encoding="utf-8"))
    if transitions["identity_sha256"] != record["transitions_identity_sha256"]:
        raise ValueError("transition identity mismatch")
    entry_triangles, port_triangles, cells_by_triangle = defaultdict(list), defaultdict(list), defaultdict(set)
    cell_records = {}
    for triangle in record["triangles"]:
        if triangle["source_package"] == "09":
            entry_triangles[triangle["source_entry_index"]].append(triangle)
        else:
            port_triangles[triangle["source_arc_id"]].append(triangle)
    for window in record["windows"]:
        row_base, column_base = window["global_origin_row_column"]
        size = record["grid"]["tile_cells"]
        for cell in window["cells"]:
            index = cell["local_index"]
            key = (row_base + index // size, column_base + index % size)
            cell_records[key] = cell
            for proposal in cell["triangle_sources"]:
                cells_by_triangle[proposal["triangle_id"]].add(key)
    requests = []
    for entry_index, entry in enumerate(transitions["entries"]):
        if entry["status"] != "candidate":
            requests.append({"entry_id": entry["entry_id"], "status": "parent_refused", "reasons": entry["rejection_reasons"]})
            continue
        triangles = entry_triangles[entry_index]
        ports = port_triangles[entry["accepted_port_arc_id"]]
        reasons = []
        if len(triangles) != len(entry["triangles"]):
            reasons.append("missing_entry_triangle_coverage")
        if not ports:
            reasons.append("upstream_port_not_rasterized")
        triangle_refusals = Counter(reason for triangle in triangles + ports for reason in triangle["rejection_reasons"])
        if triangle_refusals:
            reasons.append("triangle_resource_or_domain_refusal")
        keys = set().union(*(cells_by_triangle[triangle["triangle_id"]] for triangle in triangles + ports))
        refused = [cell_records[key] for key in keys if cell_records[key]["status"] != "candidate"]
        if refused:
            reasons.append("entry_or_port_contains_refused_cells")
        if not keys:
            reasons.append("no_fine_center_support")
        requests.append({"entry_id": entry["entry_id"],
                         "status": "geometry_diagnostic_complete" if not reasons else "pending",
                         "reasons": reasons, "entry_triangle_count": len(triangles),
                         "port_triangle_count": len(ports), "covered_centers": len(keys),
                         "refused_centers": len(refused), "triangle_refusals": dict(triangle_refusals),
                         "cell_refusals": dict(Counter(reason for cell in refused for reason in cell["rejection_reasons"])),
                         "hydraulic_ready": False})
    return {"schema": "td-lake-entry-raster-readiness-v1", "requests": requests,
            "summary": dict(Counter(request["status"] for request in requests)),
            "source_raster_sha256": raster_pin["sha256"], "source_audit_sha256": file_sha256(audit_path),
            "source_transition_sha256": pin["sha256"], "solver_calls": 0,
            "hydraulic_ready": False, "natural_outlet_verified": False, "publishable": False,
            "semantics": "all-or-nothing local entry/port saved-center gate; no partial-cell river promotion; not physical propagation or full watershed continuity"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    directory = args.input.resolve(strict=True)
    result = assess(directory)
    publish_bytes(directory / "entry-readiness.json", json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
