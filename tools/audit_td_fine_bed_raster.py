"""Audit raw native DEM, original triangles and saved cut/export quadrature."""

import argparse
from collections import Counter
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


def _read(pin):
    path = Path(pin["path"]).resolve(strict=True)
    if not path.is_relative_to(ROOT) or path.stat().st_size > 64 * 1024**2 or file_sha256(path) != pin["sha256"]:
        raise ValueError("input SHA/location/budget mismatch")
    record = json.loads(path.read_text(encoding="utf-8"))
    if "identity_sha256" in pin and record.get("identity_sha256") != pin["identity_sha256"]:
        raise ValueError("input identity mismatch")
    return record


def _source(arrays, metadata, selected_leaves, xz):
    height = np.asarray(arrays["height_m"], dtype=float)
    spacing = float(metadata["spacing_m"])
    position = (xz - np.asarray(metadata["origin_m_xz"])) / spacing
    if np.any(position < 0) or position[0] > height.shape[1] - 1 or position[1] > height.shape[0] - 1:
        return None, ["outside_native_dem"], {"native_cell_ids": [], "weights": [], "owner_ids": [], "contribution_leaf_ids": []}
    first = np.floor(position).astype(int)
    fraction = position - first
    total, reasons = 0., set()
    provenance = {"native_cell_ids": [], "weights": [], "owner_ids": [], "contribution_leaf_ids": []}
    for delta_z, delta_x in ((0, 0), (0, 1), (1, 0), (1, 1)):
        weight = (fraction[0] if delta_x else 1 - fraction[0]) * (fraction[1] if delta_z else 1 - fraction[1])
        if weight == 0:
            continue
        row, column = first[1] + delta_z, first[0] + delta_x
        if not arrays["valid_mask"][row, column]:
            reasons.add("unknown_native_corner")
        if arrays["protected_mask"][row, column]:
            reasons.add("protected_native_corner")
        if arrays["open_boundary_mask"][row, column]:
            reasons.add("open_boundary_native_corner")
        owner = int(arrays["cell_owner"][row, column])
        provenance["native_cell_ids"].append(int(row * height.shape[1] + column))
        provenance["weights"].append(float(weight))
        provenance["owner_ids"].append(owner)
        provenance["contribution_leaf_ids"].append(int(arrays["contribution_owner"][row, column]))
        if owner < 0 or owner >= len(arrays["node_unknown_contact"]) or arrays["node_unknown_contact"][owner]:
            reasons.add("unknown_native_owner")
        if int(arrays["contribution_owner"][row, column]) not in selected_leaves:
            reasons.add("outside_selected_component")
        value = float(height[row, column])
        if not math.isfinite(value):
            reasons.add("nonfinite_native_height")
        else:
            total += weight * value
    return (None if reasons & {"unknown_native_corner", "nonfinite_native_height"} else total), sorted(reasons), provenance


def audit(directory):
    manifest = json.loads((directory / "index.json").read_text(encoding="utf-8"))
    record = _read(manifest["raster"])
    canonical = {key: value for key, value in record.items() if key != "identity_sha256"}
    if hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest() != record["identity_sha256"]:
        raise ValueError("raster content identity mismatch")
    if record["schema"] != "td-fine-bed-raster-v1":
        raise ValueError("unsupported raster schema")
    pins = manifest["inputs"]
    sections, paths = _read(pins["06_sections"]), _read(pins["06_paths"])
    transitions = _read(pins["09_transitions"]) if "09_transitions" in pins else None
    hierarchy_pin = pins["hierarchy"]
    hierarchy = load_basin_hierarchy(Path(hierarchy_pin["path"]), expected_sha256=hierarchy_pin["sha256"],
                                     expected_identity=hierarchy_pin["identity_sha256"])
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    if record["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or record["sections_identity_sha256"] != sections["identity_sha256"]:
        raise ValueError("hierarchy/sections linkage mismatch")
    if record["transitions_identity_sha256"] != (transitions["identity_sha256"] if transitions else None):
        raise ValueError("transition linkage mismatch")
    selected_leaves = set(paths["selected_leaf_ids"])
    wet_cells = {cell for lake in paths["lakes"] for cell in lake["covered_cell_ids"]}
    lake_stages = {lake["leaf_id"]: lake["ordinary_stage_max_m"] for lake in paths["lakes"]}
    expected_protection = {"covered_native_cell_ids": sorted(wet_cells),
                           "stage_by_leaf": [{"leaf_id": leaf, "stage_m": lake_stages[leaf]} for leaf in sorted(lake_stages)]}
    if record["wet_protection"] != expected_protection:
        raise ValueError("wet protection differs from original saved lakes")
    if record["selected_leaf_ids"] != paths["selected_leaf_ids"] or record["source_identity_sha256"] != metadata["source_identity_sha256"]:
        raise ValueError("source/component linkage mismatch")
    selection = record["selection"]
    unsigned_selection = {key: value for key, value in selection.items() if key != "identity_sha256"}
    if hashlib.sha256(json.dumps(unsigned_selection, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest() != selection["identity_sha256"]:
        raise ValueError("selection content identity mismatch")
    entries_expected = [index for index, entry in enumerate(transitions["entries"]) if entry["status"] == "candidate"] if transitions else []
    ports_expected = sorted({transitions["entries"][index]["accepted_port_arc_id"] for index in entries_expected}) if transitions else []
    scope = selection["scope"]
    indices_expected = [] if scope == "transitions-only" else [index for index, arc in enumerate(sections["mesh"]["triangle_arc_ids"]) if scope == "all" or arc in ports_expected]
    if scope not in {"all", "lake-entry-neighborhood", "transitions-only"} or selection["selected_06_triangle_indices"] != indices_expected or selection["selected_09_entry_indices"] != entries_expected or selection["accepted_port_arc_ids"] != ports_expected:
        raise ValueError("selection differs from frozen parent geometry")
    grid = record["grid"]
    spacing = float(grid["spacing_m"])
    origin = np.asarray(grid["origin_m_xz"], dtype=float)
    tile_cells = grid["tile_cells"]
    if grid["center_offset_cells"] != .5 or grid["origin_m_xz"] != metadata["origin_m_xz"] or spacing <= 0 or spacing > record["parameters"]["minimum_source_width_m"] / 4 + 1e-12:
        raise ValueError("global fine lattice/width mismatch")
    triangle_map = {}
    accepted_land = {edge["arc_id"]: set(edge["triangle_indices"]) for edge in sections["edge_sections"]}
    for triangle in record["triangles"]:
        identifier = triangle["triangle_id"]
        if identifier in triangle_map:
            raise ValueError("duplicate triangle ID")
        triangle_map[identifier] = triangle
        if triangle["source_package"] == "06":
            mesh = sections["mesh"]
            index = triangle["source_triangle_index"]
            if index not in accepted_land[triangle["source_arc_id"]] or mesh["triangle_arc_ids"][index] != triangle["source_arc_id"]:
                raise ValueError("unaccepted land triangle")
        elif triangle["source_package"] == "09" and transitions is not None:
            mesh = transitions["entries"][triangle["source_entry_index"]]
            index = triangle["source_triangle_index"]
            if mesh["status"] != "candidate":
                raise ValueError("refused lake-entry triangle used")
        else:
            raise ValueError("unsupported parent geometry")
        indices = mesh["triangles"][index]
        if triangle["source_vertex_indices"] != indices or triangle["vertices_xyz_m"] != [mesh["vertices_xyz_m"][vertex] for vertex in indices]:
            raise ValueError("saved triangle differs from original mesh")
    expected_triangles = {"06:" + str(index) for index in indices_expected}
    if transitions:
        expected_triangles.update(f"09:{entry_index}:{index}" for entry_index in entries_expected
                                  for index in range(len(transitions["entries"][entry_index]["triangles"])))
    if set(triangle_map) != expected_triangles:
        raise ValueError("selected original triangle census mismatch")
    source_cut, statuses, coverage, refusals = [], Counter(), Counter(), Counter()
    cells_seen, windows_seen = set(), set()
    max_cut = float(record["parameters"]["max_cut_m"])
    tolerance = float(record["parameters"]["conflict_tolerance_m"])
    for window in record["windows"]:
        if window["window_id"] in windows_seen:
            raise ValueError("duplicate window")
        windows_seen.add(window["window_id"])
        row_base, column_base = window["global_origin_row_column"]
        if row_base % tile_cells or column_base % tile_cells or window["shape"] != [tile_cells, tile_cells]:
            raise ValueError("invalid tile alignment")
        cuts = []
        for cell in window["cells"]:
            index = cell["local_index"]
            row, column = row_base + index // tile_cells, column_base + index % tile_cells
            if (row, column) in cells_seen or not 0 <= index < tile_cells ** 2:
                raise ValueError("duplicate or invalid global cell")
            cells_seen.add((row, column))
            xz = origin + (np.array([column, row]) + .5) * spacing
            source, reasons, provenance = _source(arrays, metadata, selected_leaves, xz)
            for name, expected in provenance.items():
                actual = cell["source_sample"][name]
                if name == "weights":
                    if len(expected) != len(actual) or not np.allclose(actual, expected, atol=1e-12, rtol=0):
                        raise ValueError("native corner weights mismatch")
                elif actual != expected:
                    raise ValueError("native corner provenance mismatch")
            source_saved = cell["source_sample"]["height_m"]
            nearest = np.floor((xz - np.asarray(metadata["origin_m_xz"])) / metadata["spacing_m"] + .5).astype(int)
            native_height = np.asarray(arrays["height_m"])
            native_cell = int(nearest[1] * native_height.shape[1] + nearest[0])
            nearest_leaf = int(arrays["contribution_owner"][nearest[1], nearest[0]])
            wet = native_cell in wet_cells or (source is not None and source < lake_stages.get(nearest_leaf, -math.inf))
            if cell["source_sample"]["wet_source_support"] is not bool(wet):
                raise ValueError("actual lake wet support mismatch")
            if source is None:
                if source_saved is not None:
                    raise ValueError("unknown source replaced")
            elif source_saved is None or abs(source - source_saved) > 1e-8:
                raise ValueError("raw DEM mismatch")
            proposed, proposal_ids = [], set()
            for proposal in cell["triangle_sources"]:
                identifier = proposal["triangle_id"]
                if identifier in proposal_ids:
                    raise ValueError("duplicate triangle contribution")
                proposal_ids.add(identifier)
                triangle = triangle_map[identifier]
                if triangle["status"] != "rasterized":
                    raise ValueError("unrasterized triangle contributed")
                vertices = np.asarray(triangle["vertices_xyz_m"])
                matrix = np.vstack((vertices[:, 0] - xz[0], vertices[:, 2] - xz[1], np.ones(3)))
                weights = np.linalg.solve(matrix, np.array([0., 0., 1.]))
                if weights.min() < -1e-8 or not np.allclose(weights, proposal["weights"], atol=1e-8, rtol=0):
                    raise ValueError("center outside triangle or altered interpolation")
                expected_bed = float(weights @ vertices[:, 1])
                if abs(expected_bed - proposal["bed_m"]) > 1e-8:
                    raise ValueError("triangle bed mismatch")
                proposed.append(expected_bed)
                coverage[identifier] += 1
            if not proposed:
                raise ValueError("uncovered changed cell")
            if max(proposed) - min(proposed) > tolerance:
                reasons.append("conflicting_triangle_overlap")
            if source is not None:
                if source - min(proposed) > max_cut + tolerance:
                    reasons.append("cut_depth_exceeded")
                if max(proposed) > source + tolerance:
                    reasons.append("fill_without_material")
                if source - min(proposed) > tolerance and wet:
                    reasons.append("lake_wet_bed_cut_refused")
            reasons = sorted(set(reasons))
            if cell["rejection_reasons"] != reasons or cell["status"] != ("refused" if reasons else "candidate"):
                raise ValueError("source/geometry refusal mismatch")
            statuses[cell["status"]] += 1
            refusals.update(reasons)
            if cell["status"] == "refused":
                if cell["derived_bed_m"] != source_saved:
                    raise ValueError("refused cell modified")
                continue
            expected = min(source, math.fsum(proposal["bed_m"] for proposal in cell["triangle_sources"]) / len(proposed))
            if abs(expected - cell["derived_bed_m"]) > 1e-8:
                raise ValueError("derived bed differs from original triangles")
            cuts.append((source - cell["derived_bed_m"]) * spacing ** 2)
        cut = math.fsum(cuts)
        source_cut.append(cut)
        for key, value in window["material_ledger"].items():
            expected = cut if key in {"cut_rock_m3", "exported_excavated_rock_m3"} else 0.
            if abs(value - expected) > 1e-7:
                raise ValueError("window cut/export/fill ledger mismatch")
    for identifier, triangle in triangle_map.items():
        if triangle["status"] == "rasterized" and triangle["covered_centers"] != coverage[identifier]:
            raise ValueError("triangle coverage count mismatch")
    total_cut = math.fsum(source_cut)
    for key, value in record["material_ledger"].items():
        expected = total_cut if key in {"cut_rock_m3", "exported_excavated_rock_m3"} else 0.
        if abs(value - expected) > 1e-7:
            raise ValueError("global material ledger mismatch")
    summary = record["summary"]
    if summary["sparse_cells"] != len(cells_seen) or summary["window_count"] != len(windows_seen) or summary["candidate_cells"] != statuses["candidate"] or summary["refused_cells"] != statuses["refused"] or len(cells_seen) > 2_000_000 or len(windows_seen) > 4096:
        raise ValueError("count/resource mismatch")
    resource = manifest["resource"]
    if resource["peak_rss_bytes"] > 1024**3 or resource["max_rss_bytes"] != 1024**3 or resource["artifact_bytes"] > 64 * 1024**2 or resource["water_solves"] != 0 or resource["forest_rebuilds"] != 0:
        raise ValueError("saved resource budget mismatch")
    for flag in ("hydraulic_ready", "hydraulic_solved", "natural_outlet_certified", "publish_ready", "bed_changed", "cross_window_hydraulics_verified"):
        if record[flag] is not False:
            raise ValueError("candidate flag inflation")
    return {"schema": "td-fine-bed-raster-independent-audit-v1", "status": "passed",
            "raster_identity_sha256": record["identity_sha256"], "raster_sha256": manifest["raster"]["sha256"],
            "checked_cells": len(cells_seen), "candidate_cells": statuses["candidate"],
            "refused_cells": statuses["refused"], "refusal_counts": dict(refusals),
            "cut_rock_m3": total_cut, "material_ledger": record["material_ledger"], "solver_calls": 0,
            "scope": "saved triangle-covered centers and raw TD source; center-prism quadrature, not exact solid volume or complete continuous corridor"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    directory = args.input.resolve(strict=True)
    result = audit(directory)
    publish_bytes(directory / "independent-audit.json", json.dumps(result, allow_nan=False, separators=(",", ":")).encode("utf-8"))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
