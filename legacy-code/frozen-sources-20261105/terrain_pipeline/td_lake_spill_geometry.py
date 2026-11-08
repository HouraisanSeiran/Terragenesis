"""Read-only sampled spill geometry, not a hydraulic or permanent-river claim.

XYZ uses model metres (x, original bed height, z). A submerged lake approach
is the reversed static receiver route, not an uphill terrestrial river.
The caller supplies flow direction from saved water heads, never basin bottoms.
"""

import math
from numbers import Integral, Real

from terrain_pipeline.td_basin_overflow import _face_id


SCHEMA = "td-lake-spill-geometry-v1"


def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"invalid_{name}")
    return int(value)


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(f"invalid_{name}")
    return float(value)


def _context(hierarchy, source_stage_m, max_path_cells):
    stage = _finite(source_stage_m, "source_stage_m")
    budget = _integer(max_path_cells, "max_path_cells")
    if budget < 1:
        raise ValueError("invalid_max_path_cells")
    arrays = hierarchy["arrays"]
    shape = arrays["height_m"].shape
    if len(shape) != 2 or min(shape) < 1:
        raise ValueError("invalid_grid_shape")
    spacing = _finite(hierarchy["metadata"]["spacing_m"], "spacing_m")
    if spacing <= 0:
        raise ValueError("invalid_spacing_m")
    origin = hierarchy["metadata"]["origin_m_xz"]
    origin_x = _finite(origin[0], "origin_x_m")
    origin_z = _finite(origin[1], "origin_z_m")
    flat = {}
    for key in ("height_m", "valid_mask", "protected_mask", "contribution_owner", "cell_owner", "receiver"):
        if arrays[key].size != arrays["height_m"].size:
            raise ValueError(f"invalid_{key}_shape")
        flat[key] = arrays[key].ravel()
    return {"arrays": arrays, "flat": flat, "shape": shape, "stage": stage,
            "budget": budget, "spacing": spacing, "origin": (origin_x, origin_z)}


def _node(context, leaf):
    leaf = _integer(leaf, "leaf_id")
    arrays = context["arrays"]
    if not 0 <= leaf < len(arrays["node_unknown_contact"]):
        raise ValueError("invalid_leaf_id")
    if arrays["node_unknown_contact"][leaf]:
        raise ValueError("node_unknown_contact")
    if (arrays["node_parent"] == leaf).any():
        raise ValueError("not_a_contribution_leaf")
    return leaf


def _cell(context, cell, leaf):
    cell = _integer(cell, "cell_id")
    flat = context["flat"]
    if not 0 <= cell < len(flat["height_m"]):
        raise ValueError("cell_out_of_bounds")
    if not flat["valid_mask"][cell]:
        raise ValueError("invalid_cell")
    if flat["protected_mask"][cell]:
        raise ValueError("protected_cell")
    if _integer(flat["contribution_owner"][cell], "contribution_owner") != leaf:
        raise ValueError("route_owner_mismatch")
    owner = _integer(flat["cell_owner"][cell], "cell_owner")
    unknown = context["arrays"]["node_unknown_contact"]
    if not 0 <= owner < len(unknown) or unknown[owner]:
        raise ValueError("node_unknown_contact")
    _finite(flat["height_m"][cell], "route_height_m")
    return cell


def _d4(context, first, second):
    columns = context["shape"][1]
    first_row, first_column = divmod(first, columns)
    second_row, second_column = divmod(second, columns)
    if abs(first_row - second_row) + abs(first_column - second_column) != 1:
        raise ValueError("non_d4_connection")


def _receiver_route(context, first, leaf, budget):
    route = []
    visited = set()
    cell = first
    while True:
        cell = _cell(context, cell, leaf)
        if cell in visited:
            raise ValueError("receiver_cycle")
        if len(route) >= budget:
            raise ValueError("path_cell_budget_exceeded")
        visited.add(cell)
        route.append(cell)
        target = _integer(context["flat"]["receiver"][cell], "receiver")
        if target == -1:
            if int(context["flat"]["cell_owner"][cell]) != leaf:
                raise ValueError("sink_owner_mismatch")
            return route
        target = _cell(context, target, leaf)
        _d4(context, cell, target)
        if context["flat"]["height_m"][target] > context["flat"]["height_m"][cell]:
            raise ValueError("ascending_receiver")
        cell = target


def _xyz(context, cells):
    points = []
    for cell in cells:
        row, column = divmod(cell, context["shape"][1])
        points.append([context["origin"][0] + column * context["spacing"],
                       float(context["flat"]["height_m"][cell]),
                       context["origin"][1] + row * context["spacing"]])
    return points


def _wet_approach(context, route, sill):
    required = max(sill, max(float(context["flat"]["height_m"][cell]) for cell in route))
    if context["stage"] < required:
        raise ValueError("source_stage_below_sill_or_route_height")
    cells = list(reversed(route))
    return {"kind": "sampled_submerged_lake_approach", "cell_ids": cells,
            "xyz_m": _xyz(context, cells), "source_stage_m": context["stage"],
            "required_stage_m": required, "all_samples_stage_covered": True,
            "all_samples_submerged": all(float(context["flat"]["height_m"][cell]) < context["stage"] for cell in route),
            "is_terrestrial_river": False}


def _record(kind):
    return {"schema": SCHEMA, "kind": kind, "status": "rejected", "reason": None,
            "coordinate_system": "model_xyz_m_original_bed", "bed_modified": False,
            "hydraulic_verified": False, "permanent_river_verified": False,
            "natural_outlet_verified": False}


def trace_spill_connection(hierarchy, face, source_leaf_id, receiver_leaf_id, *,
                           source_stage_m, max_path_cells=2048):
    """Return JSON-safe exact-face geometry or a per-connection rejection.

    ``max_path_cells`` bounds the combined source and destination sample count.
    Successful records contain ``source_lake_approach``,
    ``downhill_terrain_approach`` and ``cross_face`` as separate polylines.
    """
    result = _record("basin_spill_connection")
    try:
        context = _context(hierarchy, source_stage_m, max_path_cells)
        source = _node(context, source_leaf_id)
        destination = _node(context, receiver_leaf_id)
        if source == destination:
            raise ValueError("same_source_and_receiver_leaf")
        index = _integer(face["face_index"], "face_index")
        arrays = context["arrays"]
        if not 0 <= index < len(arrays["face_cells"]):
            raise ValueError("invalid_face_index")
        cells = [_integer(cell, "face_cell_id") for cell in face["cell_ids"]]
        exact_cells = [int(cell) for cell in arrays["face_cells"][index]]
        if len(cells) != 2 or cells != exact_cells:
            raise ValueError("face_cell_ids_mismatch")
        leaves = [_integer(leaf, "face_leaf_id") for leaf in face["leaf_ids"]]
        if leaves != sorted((source, destination)):
            raise ValueError("face_leaf_ids_mismatch")
        owners = [int(context["flat"]["contribution_owner"][cell]) for cell in cells]
        if sorted(owners) != leaves:
            raise ValueError("face_owner_mismatch")
        first = cells[owners.index(source)]
        second = cells[owners.index(destination)]
        _cell(context, first, source)
        _cell(context, second, destination)
        _d4(context, first, second)
        if face["face_id"] != _face_id(hierarchy, index):
            raise ValueError("face_id_mismatch")
        sill = _finite(face["sill_m"], "sill_m")
        actual_sill = max(float(context["flat"]["height_m"][cell]) for cell in cells)
        if sill != actual_sill or sill != _finite(arrays["face_level_m"][index], "hierarchy_sill_m"):
            raise ValueError("face_sill_mismatch")
        result.update({"face_id": face["face_id"], "face_index": index,
                       "source_leaf_id": source, "receiver_leaf_id": destination,
                       "source_stage_m": context["stage"], "sill_m": sill})
        source_route = _receiver_route(context, first, source, context["budget"])
        wet = _wet_approach(context, source_route, sill)
        destination_route = _receiver_route(context, second, destination,
                                            context["budget"] - len(source_route))
        result.update({"status": "accepted", "source_sinkcell": source_route[-1],
                       "dest_sinkcell": destination_route[-1], "source_lake_approach": wet,
                       "downhill_terrain_approach": {"kind": "downhill_terrain_support_pending_channel",
                           "cell_ids": destination_route, "xyz_m": _xyz(context, destination_route),
                           "channel_verified": False},
                       "cross_face": {"cell_ids": [first, second], "xyz_m": _xyz(context, [first, second])},
                       "path_cell_count": len(source_route) + len(destination_route)})
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, OverflowError) as error:
        result["reason"] = str(error)
    return result


def trace_engineering_outlet(hierarchy, boundary, *, source_stage_m, max_path_cells=2048):
    """Trace a wet sink-to-declared-perimeter route, never a verified sea outlet."""
    result = _record("engineering_outlet")
    try:
        context = _context(hierarchy, source_stage_m, max_path_cells)
        leaf = _node(context, boundary["leaf_id"])
        cell = _cell(context, boundary["cell_id"], leaf)
        row, column = divmod(cell, context["shape"][1])
        sides = (int(row == 0) + int(row == context["shape"][0] - 1)
                 + int(column == 0) + int(column == context["shape"][1] - 1))
        if not sides or not context["arrays"]["open_boundary_mask"].ravel()[cell]:
            raise ValueError("not_declared_open_perimeter")
        boundary_cells = context["arrays"]["boundary_cells"]
        matches = [index for index, value in enumerate(boundary_cells) if int(value) == cell]
        if len(matches) != 1:
            raise ValueError("boundary_cell_mismatch")
        sill = _finite(boundary["sill_m"], "sill_m")
        if (sill != float(context["flat"]["height_m"][cell])
                or sill != _finite(context["arrays"]["boundary_level_m"][matches[0]], "boundary_sill_m")):
            raise ValueError("boundary_sill_mismatch")
        width = _finite(boundary["width_m"], "width_m")
        if width != sides * context["spacing"]:
            raise ValueError("boundary_width_mismatch")
        result.update({"boundary_cell_id": cell, "source_leaf_id": leaf,
                       "sill_m": sill, "width_m": width, "source_stage_m": context["stage"]})
        route = _receiver_route(context, cell, leaf, context["budget"])
        wet = _wet_approach(context, route, sill)
        result.update({"status": "accepted", "source_sinkcell": route[-1],
                       "source_lake_approach": wet, "path_cell_count": len(route),
                       "is_engineering": True, "is_sea_outlet": False})
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, OverflowError) as error:
        result["reason"] = str(error)
    return result
