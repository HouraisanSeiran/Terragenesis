"""Triangle-covered derived beds sampled from the unchanged native TD DEM."""

from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from terrain_pipeline.common_infra import identity, publish_bytes

SCHEMA = "td-fine-bed-raster-v1"
ALGORITHM = "native-bilinear-global-center-triangle-raster-v1"
MAX_CELLS = 2_000_000
MAX_WINDOWS = 4096
MAX_BYTES = 64 * 1024**2
MAX_TRIANGLES = 100_000
FLAGS = ("hydraulic_ready", "hydraulic_solved", "natural_outlet_certified",
         "publish_ready", "bed_changed", "cross_window_hydraulics_verified")
LEDGER_KEYS = ("cut_rock_m3", "exported_excavated_rock_m3", "solid_fill_m3",
               "sediment_deposited_solid_m3", "sediment_deposited_bulk_m3",
               "sediment_pore_m3", "external_fill_import_m3")


def _encoded(record):
    return json.dumps(record, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _digest(record):
    return hashlib.sha256(_encoded(record)).hexdigest()


def _positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("invalid " + name)
    return float(value)


def _pin(value):
    if not isinstance(value, str) or len(value) != 64 or any(
            digit not in "0123456789abcdef" for digit in value):
        raise ValueError("invalid identity pin")
    return value


def _wet_protection(value, native_shape):
    if value is None:
        return {"covered_native_cell_ids": [], "stage_by_leaf": []}
    covered = value["covered_native_cell_ids"]
    stages = value["stage_by_leaf"]
    if (not isinstance(covered, list) or covered != sorted(set(covered))
            or any(type(cell) is not int or not 0 <= cell < math.prod(native_shape) for cell in covered)):
        raise ValueError("invalid wet native coverage")
    leaves = [item["leaf_id"] for item in stages]
    if (leaves != sorted(set(leaves)) or any(type(leaf) is not int or leaf < 0 for leaf in leaves)
            or any(type(item["stage_m"]) not in (float, int) or not math.isfinite(item["stage_m"])
                   for item in stages)):
        raise ValueError("invalid wet protection stages")
    return {"covered_native_cell_ids": list(covered),
            "stage_by_leaf": [{"leaf_id": item["leaf_id"], "stage_m": float(item["stage_m"])}
                              for item in stages]}


def _context(hierarchy, selected_leaf_ids=None, wet_protection=None):
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    if hierarchy["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("hierarchy identity mismatch")
    height = np.asarray(arrays["height_m"])
    if height.ndim != 2 or min(height.shape) < 2 or height.size > 250_000:
        raise ValueError("invalid native DEM shape")
    for name in ("valid_mask", "protected_mask", "open_boundary_mask", "cell_owner", "contribution_owner"):
        if np.asarray(arrays[name]).shape != height.shape:
            raise ValueError("native mask/owner shape mismatch")
    origin = np.asarray(metadata["origin_m_xz"], float)
    if origin.shape != (2,) or not np.isfinite(origin).all():
        raise ValueError("invalid native origin")
    protection = _wet_protection(wet_protection, height.shape)
    return {"height": height, "arrays": arrays, "origin": origin,
            "spacing": _positive(metadata["spacing_m"], "native spacing"),
            "selected_leaf_ids": set(selected_leaf_ids) if selected_leaf_ids is not None else None,
            "wet_protection": protection,
            "covered_native_cells": set(protection["covered_native_cell_ids"]),
            "stage_by_leaf": {item["leaf_id"]: item["stage_m"] for item in protection["stage_by_leaf"]}}


def _sample(context, x_m, z_m):
    arrays = context["arrays"]
    native = context["height"]
    columns_float, rows_float = ((np.array([x_m, z_m]) - context["origin"])
                                / context["spacing"])
    rows, columns = native.shape
    if not (0 <= columns_float <= columns - 1 and 0 <= rows_float <= rows - 1):
        return {"height_m": None, "rejection_reasons": ["outside_native_dem"],
                "native_cell_ids": [], "weights": [], "owner_ids": [], "contribution_leaf_ids": [],
                "wet_source_support": False}
    column = min(int(math.floor(columns_float)), columns - 2)
    row = min(int(math.floor(rows_float)), rows - 2)
    horizontal, vertical = columns_float - column, rows_float - row
    corners = ((row, column, (1 - horizontal) * (1 - vertical)),
               (row, column + 1, horizontal * (1 - vertical)),
               (row + 1, column, (1 - horizontal) * vertical),
               (row + 1, column + 1, horizontal * vertical))
    cell_ids, weights, owners, leaf_ids, reasons = [], [], [], [], set()
    height = 0.
    for row_index, column_index, weight in corners:
        if weight == 0.:
            continue
        owner = int(arrays["cell_owner"][row_index, column_index])
        leaf = int(arrays["contribution_owner"][row_index, column_index])
        cell_ids.append(int(row_index * columns + column_index))
        weights.append(float(weight))
        owners.append(owner)
        leaf_ids.append(leaf)
        if context["selected_leaf_ids"] is not None and leaf not in context["selected_leaf_ids"]:
            reasons.add("outside_selected_component")
        if not arrays["valid_mask"][row_index, column_index]:
            reasons.add("unknown_native_corner")
        if arrays["protected_mask"][row_index, column_index]:
            reasons.add("protected_native_corner")
        if arrays["open_boundary_mask"][row_index, column_index]:
            reasons.add("open_boundary_native_corner")
        unknown = arrays["node_unknown_contact"]
        if (owner < 0 or owner >= len(unknown) or unknown[owner]
                or leaf < 0 or leaf >= len(unknown) or unknown[leaf]):
            reasons.add("unknown_native_owner")
        value = float(native[row_index, column_index])
        if not math.isfinite(value):
            reasons.add("nonfinite_native_height")
        else:
            height += weight * value
    source_height = None if any(reason in reasons for reason in (
        "unknown_native_corner", "nonfinite_native_height")) else float(height)
    nearest_column = int(math.floor(columns_float + .5))
    nearest_row = int(math.floor(rows_float + .5))
    nearest_cell = nearest_row * columns + nearest_column
    nearest_leaf = int(arrays["contribution_owner"][nearest_row, nearest_column])
    stage = context["stage_by_leaf"].get(nearest_leaf)
    wet_source = (nearest_cell in context["covered_native_cells"]
                  or (source_height is not None and stage is not None and source_height < stage))
    return {"height_m": source_height,
            "rejection_reasons": sorted(reasons), "native_cell_ids": cell_ids,
            "weights": weights, "owner_ids": owners, "contribution_leaf_ids": leaf_ids,
            "wet_source_support": bool(wet_source)}


def sample_native_dem(hierarchy, x_m, z_m, *, selected_leaf_ids=None, wet_protection=None):
    """Bilinear sample with provenance; exactly zero-weight corners are ignored."""
    if not math.isfinite(x_m) or not math.isfinite(z_m):
        raise ValueError("nonfinite sample coordinates")
    return _sample(_context(hierarchy, selected_leaf_ids, wet_protection), x_m, z_m)


def _triangle(points, indices):
    if (not isinstance(indices, list) or len(indices) != 3 or len(set(indices)) != 3
            or any(type(index) is not int or not 0 <= index < len(points) for index in indices)):
        raise ValueError("invalid triangle indices")
    vertices = points[indices]
    area = ((vertices[1, 0] - vertices[0, 0]) * (vertices[2, 2] - vertices[0, 2])
            - (vertices[1, 2] - vertices[0, 2]) * (vertices[2, 0] - vertices[0, 0]))
    if abs(area) < 1e-12:
        raise ValueError("degenerate projected triangle")
    return vertices


def _mesh_points(values):
    points = np.asarray(values, float)
    if not len(values):
        return np.empty((0, 3))
    if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
        raise ValueError("invalid mesh points")
    return points


def _triangles(sections, transitions, scope):
    mesh = sections["mesh"]
    points = _mesh_points(mesh["vertices_xyz_m"])
    source_ids = mesh["triangle_arc_ids"]
    if len(source_ids) != len(mesh["triangles"]):
        raise ValueError("missing original mesh triangle provenance")
    ownership = {}
    for edge in sections["edge_sections"]:
        for index in edge["triangle_indices"]:
            if index in ownership:
                raise ValueError("duplicate original triangle owner")
            ownership[index] = edge["arc_id"]
    if set(ownership) != set(range(len(mesh["triangles"]))):
        raise ValueError("original triangle ownership census mismatch")
    result = []
    port_arcs = {entry["accepted_port_arc_id"] for entry in transitions["entries"]
                 if entry["status"] == "candidate"} if transitions is not None else set()
    for index, indices in enumerate(mesh["triangles"]):
        if ownership.get(index) != source_ids[index]:
            raise ValueError("unaccepted or unowned original triangle")
        if scope == "transitions-only" or (scope == "lake-entry-neighborhood" and source_ids[index] not in port_arcs):
            continue
        result.append({"triangle_id": "06:" + str(index), "source_package": "06",
                       "source_arc_id": source_ids[index], "source_triangle_index": index,
                       "source_vertex_indices": list(indices),
                       "vertices_xyz_m": _triangle(points, indices).tolist(),
                       "status": "pending", "rejection_reasons": []})
    if transitions is not None:
        for entry_index, entry in enumerate(transitions["entries"]):
            if entry["status"] != "candidate":
                continue
            points = _mesh_points(entry["vertices_xyz_m"])
            for index, indices in enumerate(entry["triangles"]):
                result.append({"triangle_id": f"09:{entry_index}:{index}",
                               "source_package": "09", "source_entry_index": entry_index,
                               "source_triangle_index": index, "source_vertex_indices": list(indices),
                               "vertices_xyz_m": _triangle(points, indices).tolist(),
                               "status": "pending", "rejection_reasons": []})
    if len(result) > MAX_TRIANGLES:
        raise MemoryError("triangle provenance budget exceeded")
    return result


def _center_bounds(vertices, origin, spacing):
    minimum = vertices[:, [0, 2]].min(axis=0)
    maximum = vertices[:, [0, 2]].max(axis=0)
    first = np.ceil((minimum - origin) / spacing - .5 - 1e-9).astype(np.int64)
    last = np.floor((maximum - origin) / spacing - .5 + 1e-9).astype(np.int64)
    return [int(first[0]), int(first[1]), int(last[0]), int(last[1])]


def _weights(vertices, x_m, z_m):
    first, second, third = vertices
    denominator = ((second[2] - third[2]) * (first[0] - third[0])
                   + (third[0] - second[0]) * (first[2] - third[2]))
    first_weight = ((second[2] - third[2]) * (x_m - third[0])
                    + (third[0] - second[0]) * (z_m - third[2])) / denominator
    second_weight = ((third[2] - first[2]) * (x_m - third[0])
                     + (first[0] - third[0]) * (z_m - third[2])) / denominator
    weights = np.array([first_weight, second_weight, 1 - first_weight - second_weight])
    if weights.min() < -1e-9:
        return None
    weights = np.clip(weights, 0., 1.)
    return weights / weights.sum()


def _ledger(cells, spacing):
    cut = math.fsum(max(0., cell["source_sample"]["height_m"] - cell["derived_bed_m"])
                    * spacing**2 for cell in cells if cell["status"] == "candidate")
    return {key: cut if key in ("cut_rock_m3", "exported_excavated_rock_m3") else 0.
            for key in LEDGER_KEYS}


def _shape(record):
    return {key: record[key] for key in ("source_identity_sha256", "hierarchy_identity_sha256",
            "selected_leaf_ids", "wet_protection", "selection", "grid", "triangles", "windows", "material_ledger")}


def build_fine_bed_raster(hierarchy, sections, transitions=None, *, fine_spacing_m=2.,
                          max_cut_m=4., conflict_tolerance_m=1e-6,
                          tile_cells=32, max_cells=MAX_CELLS, max_windows=MAX_WINDOWS,
                          input_pins=None, scope="all", resource_check=None, wet_protection=None):
    """Rasterize only accepted 06/09 mesh, keeping the TD source unchanged."""
    selected_leaves = sections["selected_leaf_ids"]
    if (not selected_leaves or selected_leaves != sorted(set(selected_leaves))
            or any(type(leaf) is not int or leaf < 0 for leaf in selected_leaves)):
        raise ValueError("explicit selected contribution leaves required")
    if scope not in {"all", "lake-entry-neighborhood", "transitions-only"}:
        raise ValueError("invalid triangle selection scope")
    if scope != "all" and transitions is None:
        raise ValueError("local transition scope requires transitions")
    if transitions is not None and "wet_protection" in transitions:
        declared = _wet_protection(transitions["wet_protection"], hierarchy["arrays"]["height_m"].shape)
        if wet_protection is not None and declared != _wet_protection(
                wet_protection, hierarchy["arrays"]["height_m"].shape):
            raise ValueError("transition wet protection mismatch")
        wet_protection = declared
    context = _context(hierarchy, selected_leaves, wet_protection)
    if resource_check is not None:
        resource_check()
    if sections.get("schema") != "td-watershed-sections-v1":
        raise ValueError("accepted task06 sections required")
    source_identity = _pin(hierarchy["metadata"]["source_identity_sha256"])
    if (sections["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]
            or sections["source_identity_sha256"] != source_identity):
        raise ValueError("sections/hierarchy source mismatch")
    if transitions is not None:
        if (transitions.get("source_identity_sha256", source_identity) != source_identity
                or transitions.get("hierarchy_identity_sha256", hierarchy["identity_sha256"])
                != hierarchy["identity_sha256"]):
            raise ValueError("transition source mismatch")
        if transitions.get("sections_identity_sha256", sections["identity_sha256"]) != sections["identity_sha256"]:
            raise ValueError("transition sections identity mismatch")
        if transitions.get("selected_leaf_ids", selected_leaves) != selected_leaves:
            raise ValueError("transition selected component mismatch")
        _pin(transitions["identity_sha256"])
    requested_spacing = _positive(fine_spacing_m, "fine spacing")
    cut_limit = _positive(max_cut_m, "cut limit")
    tolerance = _positive(conflict_tolerance_m, "overlap tolerance")
    if (type(tile_cells) is not int or not 1 <= tile_cells <= 256
            or type(max_cells) is not int or not 1 <= max_cells <= MAX_CELLS
            or type(max_windows) is not int or not 1 <= max_windows <= MAX_WINDOWS):
        raise ValueError("invalid raster resource bounds")
    port_arcs = {entry["accepted_port_arc_id"] for entry in transitions["entries"]
                 if entry["status"] == "candidate"} if transitions is not None else set()
    accepted_arcs = {edge["arc_id"] for edge in sections["edge_sections"]}
    if scope == "lake-entry-neighborhood" and not port_arcs.issubset(accepted_arcs):
        raise ValueError("09 port arc is not an accepted 06 edge")
    used_nodes = {node for edge in sections["edge_sections"] for node in edge["node_ids"]
                  if scope == "all" or (scope == "lake-entry-neighborhood" and edge["arc_id"] in port_arcs)}
    widths = [_positive(node["width_m"], "channel width") for node in sections["node_sections"]
              if node["node_id"] in used_nodes]
    if used_nodes and len(widths) != len(used_nodes):
        raise ValueError("missing width provenance")
    if transitions is not None:
        widths.extend(_positive(entry["width_m"], "transition width")
                      for entry in transitions["entries"]
                      if entry["status"] == "candidate" and "width_m" in entry)
    spacing = min([requested_spacing] + [width / 4. for width in widths])
    triangles = _triangles(sections, transitions, scope)
    if resource_check is not None:
        resource_check()
    selection = {"scope": scope,
                 "selected_06_triangle_indices": [item["source_triangle_index"] for item in triangles
                                                  if item["source_package"] == "06"],
                 "selected_09_entry_indices": [index for index, entry in enumerate(transitions["entries"])
                                               if entry["status"] == "candidate"] if transitions else [],
                 "accepted_port_arc_ids": sorted(port_arcs),
                 "full_06_triangle_count": len(sections["mesh"]["triangles"]),
                 "selected_09_triangle_count": sum(item["source_package"] == "09" for item in triangles)}
    selection["identity_sha256"] = _digest(selection)
    provenance_bytes = sum(len(_encoded(triangle)) + 192 for triangle in triangles)
    provenance_bytes += len(_encoded(selection))
    if provenance_bytes + 65536 > MAX_BYTES:
        raise MemoryError("original triangle source chain exceeds byte budget")
    origin = context["origin"]
    samples, source_cache, tiles = {}, {}, set()
    visit_budget, visits = max_cells * 16, 0
    reserved_cell_bytes = 0
    for triangle_number, triangle in enumerate(triangles):
        if resource_check is not None and triangle_number % 128 == 0:
            resource_check()
        vertices = np.asarray(triangle["vertices_xyz_m"])
        native_max = origin + (np.array(context["height"].shape[::-1]) - 1) * context["spacing"]
        if (np.any(vertices[:, [0, 2]] < origin) or np.any(vertices[:, [0, 2]] > native_max)):
            triangle.update(status="refused", rejection_reasons=["triangle_outside_native_dem"])
            continue
        bounds = _center_bounds(vertices, origin, spacing)
        triangle["global_center_extent_xz"] = bounds
        count = max(0, bounds[2] - bounds[0] + 1) * max(0, bounds[3] - bounds[1] + 1)
        if count > max_cells or visits + count > visit_budget:
            triangle.update(status="refused", rejection_reasons=["raster_visit_budget_exceeded"])
            continue
        visits += count
        covered = []
        new_keys, new_tiles = set(), set()
        for row in range(bounds[1], bounds[3] + 1):
            for column in range(bounds[0], bounds[2] + 1):
                x_m, z_m = origin + (np.array([column, row]) + .5) * spacing
                weights = _weights(vertices, float(x_m), float(z_m))
                if weights is None:
                    continue
                key = (row, column)
                tile = (row // tile_cells, column // tile_cells)
                covered.append((key, {"triangle_id": triangle["triangle_id"],
                                      "weights": weights.tolist(),
                                      "bed_m": float(weights @ vertices[:, 1])}))
                if key not in samples:
                    new_keys.add(key)
                if tile not in tiles:
                    new_tiles.add(tile)
        if len(samples) + len(new_keys) > max_cells or len(tiles) + len(new_tiles) > max_windows:
            triangle.update(status="refused", rejection_reasons=["sparse_raster_budget_exceeded"])
            continue
        new_sources, new_source_bytes = {}, 0
        for row, column in sorted(new_keys):
            x_m, z_m = origin + (np.array([column, row]) + .5) * spacing
            source = _sample(context, float(x_m), float(z_m))
            new_sources[(row, column)] = source
            scaffold = {"local_index": tile_cells**2 - 1, "source_sample": source,
                        "derived_bed_m": source["height_m"], "status": "candidate",
                        "triangle_sources": [], "rejection_reasons": sorted(set(
                            source["rejection_reasons"] + ["conflicting_triangle_overlap",
                                "cut_depth_exceeded", "fill_without_material", "lake_wet_bed_cut_refused"]))}
            new_source_bytes += len(_encoded(scaffold)) + 64
        new_proposal_bytes = sum(len(_encoded(proposal)) + 2 for key, proposal in covered)
        new_window_bytes = len(new_tiles) * 2048
        increment = new_source_bytes + new_proposal_bytes + new_window_bytes
        reserved_bytes = provenance_bytes + 65536 + reserved_cell_bytes + increment
        if reserved_bytes > MAX_BYTES:
            triangle.update(status="refused", rejection_reasons=["raster_byte_reservation_exceeded"])
            continue
        reserved_cell_bytes += increment
        source_cache.update(new_sources)
        tiles.update(new_tiles)
        triangle.update(status="rasterized" if covered else "no_center_coverage",
                        covered_centers=len(covered))
        for key, proposal in covered:
            samples.setdefault(key, []).append(proposal)
    windows = {}
    statuses = Counter()
    for sample_number, ((row, column), proposals) in enumerate(sorted(samples.items())):
        if resource_check is not None and sample_number % 4096 == 0:
            resource_check()
        x_m, z_m = origin + (np.array([column, row]) + .5) * spacing
        source_sample = source_cache[(row, column)]
        reasons = set(source_sample["rejection_reasons"])
        proposed = [proposal["bed_m"] for proposal in proposals]
        if max(proposed) - min(proposed) > tolerance:
            reasons.add("conflicting_triangle_overlap")
        source_height = source_sample["height_m"]
        if source_height is not None:
            if source_sample["wet_source_support"] and source_height - min(proposed) > tolerance:
                reasons.add("lake_wet_bed_cut_refused")
            if source_height - min(proposed) > cut_limit + tolerance:
                reasons.add("cut_depth_exceeded")
            if max(proposed) > source_height + tolerance:
                reasons.add("fill_without_material")
        derived = source_height
        if not reasons:
            derived = min(source_height, math.fsum(proposed) / len(proposed))
        status = "refused" if reasons else "candidate"
        statuses[status] += 1
        tile = (row // tile_cells, column // tile_cells)
        local_index = (row % tile_cells) * tile_cells + column % tile_cells
        cell = {"local_index": local_index, "source_sample": source_sample,
                "derived_bed_m": derived, "status": status,
                "rejection_reasons": sorted(reasons), "triangle_sources": proposals}
        windows.setdefault(tile, []).append(cell)
    records = []
    for (tile_row, tile_column), cells in sorted(windows.items()):
        records.append({"window_id": f"fine:{tile_row}:{tile_column}",
                        "global_origin_row_column": [tile_row * tile_cells, tile_column * tile_cells],
                        "shape": [tile_cells, tile_cells], "cells": cells,
                        "triangle_ids": sorted({proposal["triangle_id"] for cell in cells
                                                for proposal in cell["triangle_sources"]}),
                        "material_ledger": _ledger(cells, spacing)})
    material = {key: math.fsum(window["material_ledger"][key] for window in records)
                for key in LEDGER_KEYS}
    result = {"schema": SCHEMA, "algorithm": ALGORITHM,
              "source_identity_sha256": source_identity,
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "sections_identity_sha256": _pin(sections["identity_sha256"]),
              "selected_leaf_ids": list(selected_leaves), "selection": selection,
              "wet_protection": context["wet_protection"],
              "transitions_identity_sha256": transitions["identity_sha256"] if transitions else None,
              "input_pins": dict(input_pins or {}),
              "grid": {"origin_m_xz": origin.tolist(), "spacing_m": spacing,
                       "center_offset_cells": .5, "tile_cells": tile_cells,
                       "native_shape": list(context["height"].shape),
                       "native_spacing_m": context["spacing"],
                       "coordinate_system": "model_x_elevation_y_z_m"},
              "parameters": {"requested_spacing_m": requested_spacing,
                             "width_cells_minimum": 4, "max_cut_m": cut_limit,
                             "conflict_tolerance_m": tolerance,
                             "minimum_source_width_m": min(widths) if widths else None},
              "budgets": {"max_cells": max_cells, "max_windows": max_windows,
                          "max_json_bytes": MAX_BYTES, "max_triangles": MAX_TRIANGLES,
                          "max_center_visits": visit_budget},
              "triangles": triangles, "windows": records, "material_ledger": material,
              "summary": {"sparse_cells": len(samples), "window_count": len(records),
                          "candidate_cells": statuses["candidate"], "refused_cells": statuses["refused"],
                          "refused_triangles": sum(item["status"] == "refused" for item in triangles),
                          "no_center_coverage_triangles": sum(item["status"] == "no_center_coverage" for item in triangles),
                          "conflict_cells": sum("conflicting_triangle_overlap" in cell["rejection_reasons"]
                                                for window in records for cell in window["cells"]),
                          "changed_cells": sum(cell["status"] == "candidate" and
                                               cell["derived_bed_m"] < cell["source_sample"]["height_m"]
                                               for window in records for cell in window["cells"]),
                          "center_visits": visits},
              "semantics": "derived_candidate_not_surveyed_dem; uncovered_bed_unchanged; sparse_centers_only; no_cross_window_hydraulic_claim",
              "ledger_semantics": "cell_center_prism_quadrature; excavated_rock_exported_not_converted_to_sediment; no_fill_supply",
              "source_bed_unchanged": True,
              **{flag: False for flag in FLAGS}}
    result["shape_identity_sha256"] = _digest(_shape(result))
    result["identity_sha256"] = _digest(result)
    validate_fine_bed_raster(result)
    if len(_encoded(result)) > MAX_BYTES:
        raise MemoryError("fine raster JSON exceeds 64MiB; reduce explicit bounds")
    if resource_check is not None:
        resource_check()
    return result


def validate_fine_bed_raster(record, hierarchy=None, sections=None, transitions=None, *, wet_protection=None):
    """Cold structural, provenance, geometric, and material checks, no regeneration."""
    if record.get("schema") != SCHEMA or record.get("algorithm") != ALGORITHM:
        raise ValueError("raster schema mismatch")
    if record.get("identity_sha256") != _digest({key: value for key, value in record.items()
                                               if key != "identity_sha256"}):
        raise ValueError("raster identity mismatch")
    if record.get("shape_identity_sha256") != _digest(_shape(record)):
        raise ValueError("raster shape identity mismatch")
    if any(record.get(flag) is not False for flag in FLAGS):
        raise ValueError("raster certification flags must remain false")
    if record.get("source_bed_unchanged") is not True:
        raise ValueError("source bed must remain unchanged")
    for name in ("source_identity_sha256", "hierarchy_identity_sha256", "sections_identity_sha256"):
        _pin(record[name])
    grid = record["grid"]
    spacing = _positive(grid["spacing_m"], "fine spacing")
    tile_cells = grid["tile_cells"]
    origin = np.asarray(grid["origin_m_xz"], float)
    if origin.shape != (2,) or not np.isfinite(origin).all() or grid["center_offset_cells"] != .5:
        raise ValueError("invalid center lattice")
    if type(tile_cells) is not int or not 1 <= tile_cells <= 256:
        raise ValueError("invalid tile dimension")
    tolerance = _positive(record["parameters"]["conflict_tolerance_m"], "tolerance")
    limit = _positive(record["parameters"]["max_cut_m"], "cut limit")
    width = record["parameters"]["minimum_source_width_m"]
    if (spacing > record["parameters"]["requested_spacing_m"]
            or (width is not None and spacing > _positive(width, "source width") / 4.)):
        raise ValueError("fine spacing violates width/4")
    selection = record["selection"]
    if selection["identity_sha256"] != _digest({key: value for key, value in selection.items()
                                              if key != "identity_sha256"}):
        raise ValueError("triangle selection identity mismatch")
    if selection["scope"] not in {"all", "lake-entry-neighborhood", "transitions-only"}:
        raise ValueError("invalid saved selection scope")
    protection = _wet_protection(record["wet_protection"], grid["native_shape"])
    if wet_protection is not None and protection != _wet_protection(wet_protection, grid["native_shape"]):
        raise ValueError("cold external wet protection mismatch")
    if transitions is not None and "wet_protection" in transitions and protection != _wet_protection(
            transitions["wet_protection"], grid["native_shape"]):
        raise ValueError("cold transition wet protection mismatch")
    native_context = _context(hierarchy, record["selected_leaf_ids"], protection) if hierarchy is not None else None
    if native_context is not None:
        if (hierarchy["identity_sha256"] != record["hierarchy_identity_sha256"]
                or hierarchy["metadata"]["source_identity_sha256"] != record["source_identity_sha256"]
                or list(native_context["height"].shape) != grid["native_shape"]
                or native_context["spacing"] != grid["native_spacing_m"]
                or native_context["origin"].tolist() != grid["origin_m_xz"]):
            raise ValueError("cold native hierarchy/grid mismatch")
    if sections is not None and sections["identity_sha256"] != record["sections_identity_sha256"]:
        raise ValueError("cold sections pin mismatch")
    if transitions is not None and transitions["identity_sha256"] != record["transitions_identity_sha256"]:
        raise ValueError("cold transitions pin mismatch")
    triangle_map = {item["triangle_id"]: item for item in record["triangles"]}
    if len(triangle_map) != len(record["triangles"]) or len(triangle_map) > MAX_TRIANGLES:
        raise ValueError("duplicate or excessive triangles")
    saved_indices = [triangle["source_triangle_index"] for triangle in record["triangles"]
                     if triangle["source_package"] == "06"]
    if saved_indices != selection["selected_06_triangle_indices"]:
        raise ValueError("06 selection/source triangle census mismatch")
    if (selection["scope"] == "transitions-only" and saved_indices
            or selection["selected_09_triangle_count"] != sum(
                triangle["source_package"] == "09" for triangle in record["triangles"])):
        raise ValueError("selection scope/census mismatch")
    if sections is not None:
        if record["selected_leaf_ids"] != sections["selected_leaf_ids"]:
            raise ValueError("cold selected component mismatch")
        expected_indices = [] if selection["scope"] == "transitions-only" else [
            index for index, arc in enumerate(sections["mesh"]["triangle_arc_ids"])
            if selection["scope"] == "all" or arc in selection["accepted_port_arc_ids"]]
        if (expected_indices != saved_indices
                or selection["full_06_triangle_count"] != len(sections["mesh"]["triangles"])):
            raise ValueError("cold scope selection differs from parent")
    if transitions is not None:
        expected_entries = [index for index, entry in enumerate(transitions["entries"])
                            if entry["status"] == "candidate"]
        expected_ports = sorted({transitions["entries"][index]["accepted_port_arc_id"]
                                 for index in expected_entries})
        if (expected_entries != selection["selected_09_entry_indices"]
                or expected_ports != selection["accepted_port_arc_ids"]):
            raise ValueError("cold 09 entry selection mismatch")
        expected_ids = {f"09:{entry_index}:{index}" for entry_index in expected_entries
                        for index in range(len(transitions["entries"][entry_index]["triangles"]))}
        if expected_ids != {triangle["triangle_id"] for triangle in record["triangles"]
                            if triangle["source_package"] == "09"}:
            raise ValueError("cold 09 original triangle census mismatch")
    parent_owners = {index: edge["arc_id"] for edge in sections["edge_sections"]
                     for index in edge["triangle_indices"]} if sections is not None else {}
    for triangle in triangle_map.values():
        points = _mesh_points(triangle["vertices_xyz_m"])
        _triangle(points, [0, 1, 2])
        if triangle["status"] not in {"rasterized", "refused", "no_center_coverage"}:
            raise ValueError("invalid triangle status")
        parent = None
        if triangle["source_package"] == "06" and sections is not None:
            parent = sections["mesh"]
            index = triangle["source_triangle_index"]
            if parent["triangle_arc_ids"][index] != triangle["source_arc_id"]:
                raise ValueError("cold original triangle arc mismatch")
            if parent_owners.get(index) != triangle["source_arc_id"]:
                raise ValueError("cold original triangle is not an accepted edge")
        if triangle["source_package"] == "09" and transitions is not None:
            parent = transitions["entries"][triangle["source_entry_index"]]
            if parent["status"] != "candidate":
                raise ValueError("cold transition is not a candidate")
        if parent is not None:
            indices = parent["triangles"][triangle["source_triangle_index"]]
            if (indices != triangle["source_vertex_indices"]
                    or [parent["vertices_xyz_m"][index] for index in indices]
                    != triangle["vertices_xyz_m"]):
                raise ValueError("cold original triangle geometry mismatch")
    keys, window_ids, statuses = set(), set(), Counter()
    triangle_census = Counter()
    for window in record["windows"]:
        if window["window_id"] in window_ids or window["shape"] != [tile_cells, tile_cells]:
            raise ValueError("duplicate or invalid window")
        window_ids.add(window["window_id"])
        row_base, column_base = window["global_origin_row_column"]
        if row_base % tile_cells or column_base % tile_cells:
            raise ValueError("misaligned fine window")
        source_ids = set()
        for cell in window["cells"]:
            index = cell["local_index"]
            if type(index) is not int or not 0 <= index < tile_cells**2:
                raise ValueError("invalid local center index")
            row, column = row_base + index // tile_cells, column_base + index % tile_cells
            if (row, column) in keys:
                raise ValueError("duplicate global source sample")
            keys.add((row, column))
            x_m, z_m = origin + (np.array([column, row]) + .5) * spacing
            source = cell["source_sample"]
            if type(source["wet_source_support"]) is not bool:
                raise ValueError("invalid wet source support marker")
            if native_context is not None:
                expected_sample = _sample(native_context, float(x_m), float(z_m))
                if source != expected_sample:
                    raise ValueError("cold native bilinear source mismatch")
            if not (len(source["native_cell_ids"]) == len(source["weights"]) == len(source["owner_ids"])
                    == len(source["contribution_leaf_ids"])):
                raise ValueError("invalid native provenance")
            if source["weights"] and (any(weight <= 0 for weight in source["weights"])
                                      or abs(math.fsum(source["weights"]) - 1.) > 1e-9):
                raise ValueError("invalid native weights")
            proposals = cell["triangle_sources"]
            if not proposals or len({item["triangle_id"] for item in proposals}) != len(proposals):
                raise ValueError("missing/duplicate triangle coverage")
            for proposal in proposals:
                triangle = triangle_map[proposal["triangle_id"]]
                if triangle["status"] != "rasterized":
                    raise ValueError("refused triangle contributed a bed")
                points = np.asarray(triangle["vertices_xyz_m"])
                weights = _weights(points, float(x_m), float(z_m))
                if (weights is None or not np.allclose(weights, proposal["weights"], atol=1e-9, rtol=0)
                        or abs(float(weights @ points[:, 1]) - proposal["bed_m"]) > tolerance):
                    raise ValueError("triangle interpolation provenance mismatch")
                source_ids.add(proposal["triangle_id"])
                triangle_census[proposal["triangle_id"]] += 1
            wet_cut = (source["wet_source_support"] and source["height_m"] is not None
                       and source["height_m"] - min(item["bed_m"] for item in proposals) > tolerance)
            if wet_cut != ("lake_wet_bed_cut_refused" in cell["rejection_reasons"]):
                raise ValueError("wet bed cut refusal mismatch")
            status = cell["status"]
            if status not in {"candidate", "refused"}:
                raise ValueError("invalid cell status")
            statuses[status] += 1
            if status == "candidate":
                height, derived = source["height_m"], cell["derived_bed_m"]
                if (source["rejection_reasons"] or cell["rejection_reasons"] or height is None
                        or not math.isfinite(height) or not math.isfinite(derived)
                        or not -tolerance <= height - derived <= limit + tolerance):
                    raise ValueError("illegal accepted cut/fill")
                if not set(source["contribution_leaf_ids"]).issubset(record["selected_leaf_ids"]):
                    raise ValueError("accepted center outside selected component")
                values = [proposal["bed_m"] for proposal in proposals]
                if source["wet_source_support"] and height - min(values) > tolerance:
                    raise ValueError("accepted cut on protected wet source bed")
                if (max(values) - min(values) > tolerance or max(values) > height + tolerance
                        or abs(derived - min(height, math.fsum(values) / len(values))) > tolerance):
                    raise ValueError("unrejected triangle conflict/fill")
            elif not cell["rejection_reasons"] or cell["derived_bed_m"] != source["height_m"]:
                raise ValueError("refused center changed native bed")
        if sorted(source_ids) != window["triangle_ids"]:
            raise ValueError("window triangle source chain mismatch")
        expected = _ledger(window["cells"], spacing)
        if any(abs(expected[key] - window["material_ledger"][key]) > 1e-8 for key in LEDGER_KEYS):
            raise ValueError("window cut/material ledger mismatch")
    for triangle in triangle_map.values():
        if triangle["status"] == "rasterized" and triangle_census[triangle["triangle_id"]] != triangle["covered_centers"]:
            raise ValueError("triangle coverage census mismatch")
    expected = {key: math.fsum(window["material_ledger"][key] for window in record["windows"])
                for key in LEDGER_KEYS}
    if any(abs(expected[key] - record["material_ledger"][key]) > 1e-8 for key in LEDGER_KEYS):
        raise ValueError("total material ledger mismatch")
    summary, budgets = record["summary"], record["budgets"]
    if (summary["sparse_cells"] != len(keys) or summary["window_count"] != len(window_ids)
            or summary["candidate_cells"] != statuses["candidate"]
            or summary["refused_cells"] != statuses["refused"]
            or not len(keys) <= budgets["max_cells"] <= MAX_CELLS
            or not len(window_ids) <= budgets["max_windows"] <= MAX_WINDOWS
            or budgets["max_json_bytes"] != MAX_BYTES):
        raise ValueError("raster summary/resource mismatch")
    if len(_encoded(record)) > MAX_BYTES:
        raise MemoryError("fine raster exceeds 64MiB")
    return record


def save_fine_bed_raster(record, path, *, resource_check=None):
    validate_fine_bed_raster(record)
    payload = _encoded(record)
    if len(payload) > MAX_BYTES:
        raise MemoryError("fine raster exceeds 64MiB")
    if resource_check is not None:
        resource_check()
    publish_bytes(path, payload)
    return Path(path)


def load_fine_bed_raster(path, *, expected_sha256, expected_identity,
                        hierarchy=None, sections=None, transitions=None, wet_protection=None):
    target = Path(path)
    if target.stat().st_size > MAX_BYTES:
        raise MemoryError("fine raster exceeds 64MiB")
    payload = target.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("fine raster file SHA mismatch")
    record = json.loads(payload)
    if record.get("identity_sha256") != expected_identity:
        raise ValueError("external fine raster identity mismatch")
    return validate_fine_bed_raster(record, hierarchy, sections, transitions, wet_protection=wet_protection)
