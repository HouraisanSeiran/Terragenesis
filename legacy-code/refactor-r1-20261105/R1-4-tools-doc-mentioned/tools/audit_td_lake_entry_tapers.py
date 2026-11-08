"""Independent saved geometry/source audit; never imports the taper builder."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from terrain_pipeline.td_basin_hierarchy import load_basin_hierarchy


def _json(pin, base):
    path = (base / pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > 32 * 1024**2 or file_sha256(path) != pin["sha256"]:
        raise ValueError("saved input pin/budget mismatch")
    result = json.loads(path.read_text(encoding="utf-8"))
    if "identity_sha256" in pin and result["identity_sha256"] != pin["identity_sha256"]:
        raise ValueError("saved identity pin mismatch")
    return result


def audit(directory):
    manifest = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    record = _json(manifest["entries"], directory)
    identity = record.pop("identity_sha256")
    actual = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    if actual != identity:
        raise ValueError("entry content identity mismatch")
    parents = manifest["inputs"]
    paths = _json(parents["paths"], directory)
    sections = _json(parents["sections"], directory)
    if sections["composite_parent_identity"]["paths"] != paths["identity_sha256"] or sections["selected_leaf_ids"] != paths["selected_leaf_ids"] or record["selected_leaf_ids"] != paths["selected_leaf_ids"]:
        raise ValueError("sections/paths/component linkage mismatch")
    protection = {"covered_native_cell_ids": sorted({cell for lake in paths["lakes"] for cell in lake["covered_cell_ids"]}),
                  "stage_by_leaf": [{"leaf_id": lake["leaf_id"], "stage_m": lake["ordinary_stage_max_m"]}
                                    for lake in sorted(paths["lakes"], key=lambda lake: lake["leaf_id"])],
                  "semantics": "conservative maximum-saved-stage lake protection, not simultaneous water geometry"}
    if record.get("wet_protection") != protection:
        raise ValueError("wet protection differs from saved paths")
    hierarchy_pin = parents["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]), expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    for key, expected in (("paths_identity_sha256", paths["identity_sha256"]),
                          ("sections_identity_sha256", sections["identity_sha256"]),
                          ("hierarchy_identity_sha256", hierarchy["identity_sha256"])):
        if record[key] != expected:
            raise ValueError("parent identity linkage mismatch")
    nodes = {node["node_id"]: node for node in paths["nodes"]}
    arcs = {arc["arc_id"]: arc for arc in paths["arcs"]}
    ports = {edge["arc_id"]: edge for edge in sections["edge_sections"]}
    requested = {arc["arc_id"] for arc in paths["arcs"] if arc["kind"] == "lake_entry_support"}
    if len(record["entries"]) != len(requested) or {entry["entry_id"] for entry in record["entries"]} != requested:
        raise ValueError("entry request coverage mismatch")
    arrays = hierarchy["arrays"]
    height = np.asarray(arrays["height_m"], dtype=float)
    origin = np.asarray(hierarchy["metadata"]["origin_m_xz"])
    spacing = float(hierarchy["metadata"]["spacing_m"])
    vertices_count = 0
    for entry in record["entries"]:
        if entry["status"] == "refused":
            if not entry["rejection_reasons"] or entry["vertices_xyz_m"] or entry["triangles"]:
                raise ValueError("invalid refusal record")
            continue
        if entry["status"] != "candidate" or entry["rejection_reasons"]:
            raise ValueError("invalid candidate status")
        support = arcs[entry["entry_id"]]
        land = arcs[entry["land_arc_id"]]
        port = ports[entry["accepted_port_arc_id"]]
        if support["node_ids"] != [entry["anchor_node_id"], entry["wet_node_id"]] or land["node_ids"] != [entry["upstream_node_id"], entry["anchor_node_id"]] or land["kind"] != "land_channel" or port["node_ids"][-1] != entry["upstream_node_id"]:
            raise ValueError("port/path mismatch")
        for first, second in (land["node_ids"], support["node_ids"]):
            if int(np.asarray(arrays["receiver"]).ravel()[nodes[first]["cell_id"]]) != nodes[second]["cell_id"]:
                raise ValueError("saved native receiver mismatch")
        vertices = np.asarray(entry["vertices_xyz_m"], dtype=float).reshape(-1, 5, 3)
        if not np.isfinite(vertices).all() or len(vertices) != entry["station_count"]:
            raise ValueError("invalid vertices")
        vertices_count += vertices.size // 3
        if not np.array_equal(vertices[0, [0, 1, 3, 4]], port["cross_section_xyz_m"][-1]) or entry["accepted_port_xyz_m"] != port["cross_section_xyz_m"][-1]:
            raise ValueError("shared port altered")
        xz = vertices[:, :, [0, 2]].reshape(-1, 2)
        coordinates = (xz - origin) / spacing
        if np.any(coordinates < 0) or np.any(coordinates[:, 0] > height.shape[1] - 1) or np.any(coordinates[:, 1] > height.shape[0] - 1):
            raise ValueError("outside source")
        floor = np.floor(coordinates).astype(int)
        weights = coordinates - floor
        source = np.zeros(len(coordinates))
        for delta_z in range(2):
            for delta_x in range(2):
                weight = (weights[:, 0] if delta_x else 1 - weights[:, 0]) * (weights[:, 1] if delta_z else 1 - weights[:, 1])
                active = weight > 0
                columns, rows = floor[active, 0] + delta_x, floor[active, 1] + delta_z
                if not arrays["valid_mask"][rows, columns].all() or arrays["protected_mask"][rows, columns].any() or arrays["open_boundary_mask"][rows, columns].any() or not np.isin(arrays["contribution_owner"][rows, columns], record["selected_leaf_ids"]).all():
                    raise ValueError("invalid source support")
                source[active] += weight[active] * height[rows, columns]
        source = source.reshape(-1, 5)
        if not np.allclose(source.ravel(), entry["source_vertex_height_m"], rtol=0, atol=1e-8):
            raise ValueError("actual DEM samples differ")
        cut = source - vertices[:, :, 1]
        if cut.min() < -1e-8 or cut.max() > 4 + 1e-8 or not np.allclose(cut[-1], 0, rtol=0, atol=1e-8) or np.max(np.diff(vertices[:, 2, 1])) > 1e-8:
            raise ValueError("cut/fill or center-grade mismatch")
        fractions = np.linspace(0, 1, len(vertices))
        expected = (1 - 3 * fractions ** 2 + 2 * fractions ** 3)[:, None] * cut[0]
        if not np.allclose(cut, expected, atol=1e-8, rtol=0):
            raise ValueError("cut taper mismatch")
        start = np.asarray(nodes[entry["upstream_node_id"]]["xyz_m"])[[0, 2]]
        end = np.asarray(nodes[entry["anchor_node_id"]]["xyz_m"])[[0, 2]]
        if not np.allclose(vertices[:, 2, [0, 2]], start + fractions[:, None] * (end - start), atol=1e-8, rtol=0):
            raise ValueError("centerline differs from native land segment")
        actual_port = np.asarray(port["cross_section_xyz_m"][-1], dtype=float)
        expanded = np.insert(actual_port, 2, (actual_port[1] + actual_port[2]) / 2, axis=0)
        offsets = expanded[:, [0, 2]] - start
        expected_xz = start[None, None, :] + fractions[:, None, None] * (end - start) + offsets[None, :, :]
        if not np.allclose(vertices[:, :, [0, 2]], expected_xz, atol=1e-8, rtol=0):
            raise ValueError("lateral geometry differs from translated accepted port")
        actual_width = float(np.linalg.norm(actual_port[1, [0, 2]] - actual_port[2, [0, 2]]))
        if abs(actual_width - entry["width_m"]) > 1e-8 or not np.allclose(expanded[2, [0, 2]], start, atol=1e-8, rtol=0):
            raise ValueError("port midpoint/width mismatch")
        nearest = np.floor((xz - origin) / spacing + .5).astype(int)
        nearest_cells = nearest[:, 1] * height.shape[1] + nearest[:, 0]
        owners = arrays["contribution_owner"][nearest[:, 1], nearest[:, 0]]
        stages = {lake["leaf_id"]: lake["ordinary_stage_max_m"] for lake in paths["lakes"]}
        lake_stage = np.array([stages.get(int(owner), -np.inf) for owner in owners])
        wet = np.isin(nearest_cells, protection["covered_native_cell_ids"]) | (source.ravel() < lake_stage)
        if np.any(wet & (cut.ravel() > 1e-8)):
            raise ValueError("positive cut inside protected lake support")
        if float(np.linalg.norm(end - start)) / (len(vertices) - 1) > min(1., entry["width_m"] / 4.) + 1e-8:
            raise ValueError("station resolution mismatch")
        expected_triangles = []
        for station in range(len(vertices) - 1):
            for lateral in range(4):
                first = station * 5 + lateral
                expected_triangles.extend([[first, first + 1, first + 6], [first, first + 6, first + 5]])
        if entry["triangles"] != expected_triangles or entry["anchor_source_profile_xyz_m"] != vertices[-1].tolist():
            raise ValueError("triangle/anchor identity mismatch")
        projected = vertices.reshape(-1, 3)[np.asarray(entry["triangles"])][:, :, [0, 2]]
        signed = ((projected[:, 1, 0] - projected[:, 0, 0]) * (projected[:, 2, 1] - projected[:, 0, 1])
                  - (projected[:, 1, 1] - projected[:, 0, 1]) * (projected[:, 2, 0] - projected[:, 0, 0]))
        if np.any(np.abs(signed) < 1e-12) or np.any(np.sign(signed) != np.sign(signed[0])):
            raise ValueError("degenerate/folded projected triangles")
    summary = {"requested": len(record["entries"]), "candidates": sum(entry["status"] == "candidate" for entry in record["entries"]),
               "vertices": vertices_count, "refusals": dict(Counter(reason for entry in record["entries"] for reason in entry["rejection_reasons"]))}
    if summary != record["summary"] or vertices_count > 100_000:
        raise ValueError("summary/budget mismatch")
    for flag in ("hydraulic_ready", "publishable", "natural_outlet_verified", "new_bed_hydrology_verified", "solver_advanced", "lake_bed_changed"):
        if record[flag] is not False:
            raise ValueError("candidate flag inflation")
    return {"schema": "td-lake-entry-taper-audit-v1", "status": "passed", "scope": "saved ports, native receivers, real DEM vertex samples and land-side taper; not raster interior or hydraulic certification",
            "entry_identity_sha256": identity, "summary": summary, "solver_calls": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.input.resolve(strict=True))
    publish_bytes(args.input / "independent-audit.json", json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
