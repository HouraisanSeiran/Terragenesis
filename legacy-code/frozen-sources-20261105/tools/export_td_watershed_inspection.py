"""Read-only inspection of saved TD geometry; no routing or geometry generation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = ROOT / "verification/natural-river-network/watershed-geometry-20261005-01/index.json"
DEFAULT_SHA256 = "fec57d5c9df599ba3c419d2283910d27afe172c236743b3536769bf579af662b"
MAX_BYTES = 64 * 1024**2
SCHEMA = "td-watershed-inspection-v1"
FLAGS = {"hydraulic_ready": False, "publishable": False, "natural_outlet_verified": False,
         "permanent_trunk_ready": False, "solver_advanced": False, "bed_changed": False,
         "water_surface_meshed": False, "bed_rasterized": False, "parametric_only": True}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encoded(record):
    payload = json.dumps(record, ensure_ascii=False, allow_nan=False,
                         separators=(",", ":")).encode("utf-8")
    require(len(payload) <= MAX_BYTES, "inspection artifact exceeds 64MiB")
    return payload


def read_pin(pin, base):
    path = (Path(base) / pin["path"]).resolve(strict=True)
    require(path.is_relative_to(ROOT.resolve()), "input outside workspace")
    require(path.stat().st_size <= MAX_BYTES, "input exceeds 64MiB")
    payload = path.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == pin["sha256"].lower(), "input SHA256 mismatch")
    return payload, {**pin, "path": str(path), "bytes": len(payload)}


def read_json_pin(pin, base):
    payload, resolved = read_pin(pin, base)
    record = json.loads(payload)
    if "identity_sha256" in pin:
        require(record.get("identity_sha256") == pin["identity_sha256"], "identity mismatch")
    encoded(record)
    return record, resolved


def unique(records, key):
    result = {record[key]: record for record in records}
    require(len(result) == len(records), "duplicate " + key)
    return result


def validate_geometry(paths, sections, arrays, metadata):
    require(paths["schema"] == "td-watershed-paths-v1", "unsupported paths schema")
    require(sections["schema"] == "td-watershed-sections-v1", "unsupported sections schema")
    height = arrays["height_m"]
    require(height.ndim == 2 and height.size <= 250_000 and np.isfinite(height).all(), "invalid native terrain")
    origin = metadata["origin_m_xz"]
    spacing = metadata["spacing_m"]
    require(np.isfinite(origin).all() and np.isfinite(spacing) and spacing > 0, "invalid coordinates")
    require(paths["grid_shape"] == list(height.shape) and paths["origin_m_xz"] == origin
            and paths["spacing_m"] == spacing, "path/native grid mismatch")
    nodes = unique(paths["nodes"], "node_id")
    arcs = unique(paths["arcs"], "arc_id")
    for node in nodes.values():
        cell = node["cell_id"]
        require(type(cell) is int and 0 <= cell < height.size, "invalid native cell")
        row, column = divmod(cell, height.shape[1])
        expected = [origin[0] + column * spacing, float(height[row, column]), origin[1] + row * spacing]
        require(node["node_id"] == f"cell:{cell}" and node["xyz_m"] == expected
                and arrays["valid_mask"].flat[cell]
                and node["leaf_id"] == arrays["contribution_owner"].flat[cell], "node differs from native terrain")
    for arc in arcs.values():
        ids = arc["node_ids"]
        require(len(ids) >= 1 and all(identifier in nodes for identifier in ids), "arc references missing node")
        require(arc["xyz_m"] == [nodes[identifier]["xyz_m"] for identifier in ids]
                and arc["cell_ids"] == [nodes[identifier]["cell_id"] for identifier in ids], "arc geometry mismatch")
        require(arc["channel_candidate"] is (arc["kind"] == "land_channel"), "support cannot be channel")
        for first, second in zip(arc["cell_ids"], arc["cell_ids"][1:]):
            require(abs(first // height.shape[1] - second // height.shape[1])
                    + abs(first % height.shape[1] - second % height.shape[1]) == 1, "non-D4 arc")
        if arc["channel_candidate"]:
            require(len(ids) == 2 and arrays["receiver"][arc["cell_ids"][0]] == arc["cell_ids"][1], "not native receiver")
    mesh = sections["mesh"]
    vertices = np.asarray(mesh["vertices_xyz_m"], dtype=float)
    triangles = np.asarray(mesh["triangles"])
    require(vertices.ndim == 2 and vertices.shape[1] == 3 and np.isfinite(vertices).all(), "invalid saved vertices")
    require(triangles.ndim == 2 and triangles.shape[1] == 3 and triangles.dtype.kind in "iu"
            and np.all((triangles >= 0) & (triangles < len(vertices))), "invalid triangle reference")
    diagnostics = unique(sections["reach_diagnostics"], "arc_id")
    edges = unique(sections["edge_sections"], "arc_id")
    candidates = {key for key, arc in arcs.items() if arc["channel_candidate"]}
    require(set(diagnostics) == candidates, "missing candidate diagnostics")
    accepted = {key for key, record in diagnostics.items() if record["status"] == "geometry_candidate"}
    require(set(edges) == accepted, "mesh edge/diagnostic mismatch")
    require(all(record["status"] in ("rejected", "geometry_candidate")
                and bool(record["rejection_reasons"]) == (record["status"] == "rejected")
                for record in diagnostics.values()), "invalid rejection status")
    owners = mesh["triangle_arc_ids"]
    require(len(owners) == len(triangles), "triangle ownership length mismatch")
    used = []
    for key, edge in edges.items():
        require(edge["node_ids"] == arcs[key]["node_ids"], "edge node mismatch")
        for index in edge["triangle_indices"]:
            require(type(index) is int and 0 <= index < len(triangles) and owners[index] == key,
                    "invalid edge triangle reference")
            used.append(index)
    require(sorted(used) == list(range(len(triangles))), "missing/duplicate/forged triangle ownership")
    require(sections["support_arcs"] == [arc for arc in paths["arcs"] if not arc["channel_candidate"]], "support mismatch")
    node_sections = unique(sections["node_sections"], "node_id")
    require(set(node_sections) == set(nodes), "missing node sections")
    for record in node_sections.values():
        require(record["node_id"] in nodes and record["source_xyz_m"] == nodes[record["node_id"]]["xyz_m"], "section node mismatch")
    for identifier, indices in mesh["node_vertex_indices"].items():
        require(identifier in nodes and all(type(index) is int and 0 <= index < len(vertices) for index in indices),
                "invalid node vertex reference")
        require([mesh["vertices_xyz_m"][index] for index in indices]
                == node_sections[identifier]["cross_section_xyz_m"], "saved vertex/cross-section mismatch")


def load_inspection(index_path=DEFAULT_INDEX, index_sha256=DEFAULT_SHA256):
    index_path = Path(index_path).resolve(strict=True)
    index, index_pin = read_json_pin({"path": str(index_path), "sha256": index_sha256}, ROOT)
    require(index["schema"] == "td-watershed-geometry-preparation-v1", "unsupported index schema")
    pins = {"index": index_pin}
    records = {}
    for key in ("paths", "sections", "review", "parent_graph", "parent_index", "parent_audit"):
        records[key], pins[key] = read_json_pin(index[key], index_path.parent)
    for key, pin in index["inputs"].items():
        _, pins[key] = read_pin(pin, index_path.parent)
    with np.load(pins["hierarchy"]["path"], allow_pickle=False) as bundle:
        manifest = json.loads(bytes(bundle["manifest"]))
        arrays = {key: bundle[key].copy() for key in
                  ("height_m", "valid_mask", "protected_mask", "receiver", "contribution_owner")}
    require(manifest["identity_sha256"] == pins["hierarchy"]["identity_sha256"], "hierarchy identity mismatch")
    paths, sections, saved = records["paths"], records["sections"], records["review"]
    for key in ("hierarchy", "topology", "ordinary"):
        require(paths[key + "_identity_sha256"] == sections[key + "_identity_sha256"]
                == pins[key]["identity_sha256"], "parent identity mismatch")
    require(paths["graph_identity_sha256"] == records["parent_graph"]["identity_sha256"]
            == sections["composite_parent_identity"]["graph"], "graph identity mismatch")
    require(sections["composite_parent_identity"]["paths"] == paths["identity_sha256"], "section parent mismatch")
    require(paths["source_identity_sha256"] == sections["source_identity_sha256"]
            == manifest["metadata"]["source_identity_sha256"], "native source identity mismatch")
    for record in (index, paths, sections, saved):
        for key in ("hydraulic_ready", "publishable", "natural_outlet_verified", "permanent_trunk_ready", "bed_changed"):
            require(record.get(key) is False, "unsupported source capability: " + key)
    require(saved["paths"] == paths and saved["sections"] == sections
            and np.array_equal(saved["height_m"], arrays["height_m"])
            and saved["origin_m_xz"] == manifest["metadata"]["origin_m_xz"]
            and saved["spacing_m"] == manifest["metadata"]["spacing_m"], "saved review differs from sources")
    validate_geometry(paths, sections, arrays, manifest["metadata"])
    actual_counts = {"node_count": len(paths["nodes"]), "arc_count": len(paths["arcs"]),
                     "vertex_count": len(sections["mesh"]["vertices_xyz_m"]),
                     "triangle_count": len(sections["mesh"]["triangles"]),
                     "section_count": len(sections["node_sections"]), "basin_count": len(paths["lakes"]),
                     "land_arc_count": len(sections["reach_diagnostics"])}
    require(all(index["summary"][key] == value for key, value in actual_counts.items()), "saved count mismatch")
    selected = np.flatnonzero(arrays["valid_mask"] & np.isin(arrays["contribution_owner"], paths["selected_leaf_ids"])).tolist()
    require(selected == saved["primary_support_cell_ids"], "primary support mismatch")
    require(len(selected) * paths["spacing_m"]**2 == index["summary"]["primary_support_area_m2"], "support area mismatch")
    rejected = [record for record in sections["reach_diagnostics"] if record["status"] == "rejected"]
    return {"schema": SCHEMA, "algorithm": "saved-only-inspection-export-v1", "pins": pins,
            "coordinates": {"axes": "x east, y elevation, z south", "array_order": "[z,x]",
                            "cell_id": "row*columns+column", "length_unit": "m", "area_unit": "m2",
                            "discharge_unit": "m3/s", "origin_m_xz": paths["origin_m_xz"],
                            "spacing_m": paths["spacing_m"], "real_world_georeference": None,
                            "semantics": "physical metric model; TD-generated, not surveyed or Minecraft blocks"},
            "terrain": {"height_m": arrays["height_m"].tolist(), "valid_mask": arrays["valid_mask"].tolist(),
                        "protected_mask": arrays["protected_mask"].tolist(), "sampling": "native; no resampling"},
            "views": {"full_domain": True, "primary_support_cell_ids": selected,
                      "primary_support_area_m2": index["summary"]["primary_support_area_m2"]},
            "layers": {"nodes": paths["nodes"], "receiver_candidates": [arc for arc in paths["arcs"] if arc["channel_candidate"]],
                       "support_arcs": sections["support_arcs"], "saved_bed_mesh": sections["mesh"],
                       "constructible_edges": sections["edge_sections"], "rejected_edges": rejected,
                       "lakes": paths["lakes"], "sampled_lake_wet_cell_ids": saved["sampled_lake_wet_cell_ids"],
                       "sampled_stage_by_leaf": saved["sampled_stage_by_leaf"]},
            "node_sections": [{key: record[key] for key in
                               ("node_id", "source_xyz_m", "bed_m", "width_m", "depth_m",
                                "representative_q_m3_s", "level", "rejection_reasons")}
                              for record in sections["node_sections"]],
            "reach_diagnostics": sections["reach_diagnostics"],
            "supply": {"semantics": "uncalibrated prior, not measured or instantaneous discharge",
                       "source_semantics": sections["supply_semantics"], "parameters": sections["parameters"]},
            "sample": {"saved_index": saved["sampled_index"], "time_s": saved["sampled_time_s"]},
            "summary": index["summary"], "limitations": ["Support arcs are not hydraulic directions or beds.",
                "Saved strips are locally continuous only; rejected junctions are not filled.",
                "Lake maximum-stage coverage is not simultaneous water; sampled footprint is separate.",
                "No water surface, fine DEM, new carved terrain, solver, or permanent flow certification.",
                "Frontend navigation and layered inspection integration pending Claude."], **FLAGS}


def mesh_caseartifact(review):
    mesh = review["layers"]["saved_bed_mesh"]
    heights = [point[1] for point in mesh["vertices_xyz_m"]]
    return {"schema": "td-watershed-inspection-mesh-case-v1", "kind": "mesh",
            "caseId": "td-watershed-saved-bed-strips", "label": "Saved parametric bed strips (not water)",
            "mesh": {"vertices": mesh["vertices_xyz_m"], "triangles": mesh["triangles"],
                     "bed": heights, "h0": heights, "water": None, "wet": [], "wetCells": [],
                     "cells": [], "hydrologicOwner": [], "cellOwner": []},
            "pins": review["pins"], "triangle_arc_ids": mesh["triangle_arc_ids"],
            "evidence": {"status": "diagnostic_saved_geometry", "scope": "Saved bed strips only; H0 alias is NOT native terrain",
                         "source": review["pins"]["sections"], "limitations": review["limitations"]}, **FLAGS}


def publish_directory(output, artifacts):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT.resolve()) and not output.exists(), "output must be a NEW workspace directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".watershed-inspection-", dir=output.parent))
    try:
        for name, payload in artifacts.items():
            require(len(payload) <= MAX_BYTES, "artifact exceeds 64MiB")
            (staging / name).write_bytes(payload)
        require(not output.exists(), "output appeared during export")
        os.rename(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return output


def parser(description):
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    result.add_argument("--index-sha256", default=DEFAULT_SHA256)
    result.add_argument("--output", type=Path, required=True)
    return result


def main():
    args = parser(__doc__).parse_args()
    review = load_inspection(args.index, args.index_sha256)
    artifacts = {"review.json": encoded(review), "caseartifact.json": encoded(mesh_caseartifact(review))}
    print(publish_directory(args.output, artifacts))


if __name__ == "__main__":
    main()
