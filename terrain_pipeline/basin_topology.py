"""basin_topology: merged M4 implementation; source locations precede each statement."""
from __future__ import annotations

from collections import Counter as _m4_basin_spill_network_Counter
from collections import deque as _m4_basin_hierarchy_deque
from collections import deque as _m4_lake_outlet_forest_deque
from copy import deepcopy as _m4_lake_outlet_forest_deepcopy
from numbers import Integral as _m4_lake_spill_geometry_Integral
from numbers import Real as _m4_lake_spill_geometry_Real
from pathlib import Path as _m4_basin_candidates_Path
from pathlib import Path as _m4_basin_escape_plan_Path
from pathlib import Path as _m4_basin_spill_network_Path
from pathlib import Path as _m4_lake_spill_corridor_Path
from scipy.sparse import csr_matrix as _m4_lake_outlet_forest_csr_matrix
from scipy.sparse.csgraph import connected_components as _m4_lake_outlet_forest_connected_components
import hashlib as _m4_basin_breach_hashlib
import hashlib as _m4_basin_reception_hashlib
import hashlib as _m4_lake_spill_corridor_hashlib
import hashlib as _m4_lake_spill_graph_hashlib
import hashlib as _m4_stable_spill_paths_hashlib
import heapq as _m4_basin_escape_plan_heapq
import json as _m4_basin_candidates_json
import json as _m4_basin_escape_plan_json
import json as _m4_basin_reception_json
import json as _m4_basin_spill_network_json
import json as _m4_lake_spill_corridor_json
import json as _m4_lake_spill_graph_json
import json as _m4_stable_spill_paths_json
import math as _m4_basin_breach_math
import math as _m4_basin_escape_plan_math
import math as _m4_basin_spill_network_math
import math as _m4_lake_outlet_forest_math
import math as _m4_lake_spill_corridor_math
import math as _m4_lake_spill_geometry_math
import numpy as _m4_basin_breach_np
import numpy as _m4_basin_candidates_np
import numpy as _m4_basin_escape_plan_np
import numpy as _m4_basin_hierarchy_np
import numpy as _m4_basin_reception_np
import numpy as _m4_basin_spill_network_np
import numpy as _m4_lake_spill_corridor_np
import numpy as _m4_lake_spill_graph_np
import numpy as _m4_stable_spill_paths_np
import os as _m4_basin_candidates_os
import shutil as _m4_basin_candidates_shutil
import tempfile as _m4_basin_candidates_tempfile

CATEGORY = "B"

# --- terrain_pipeline/td_basin_hierarchy.py:10 ---
MAX_CURVE_ENTRIES = 4_000_000

# --- terrain_pipeline/td_basin_hierarchy.py:13 ---
def _neighbors(cell, rows, columns):
    row, column = divmod(int(cell), columns)
    if row:
        yield cell - columns
    if column:
        yield cell - 1
    if column + 1 < columns:
        yield cell + 1
    if row + 1 < rows:
        yield cell + columns

# --- terrain_pipeline/td_basin_hierarchy.py:25 ---
def _flat_receivers(height, valid, rows, columns):
    receiver = _m4_basin_hierarchy_np.full(height.size, -1, _m4_basin_hierarchy_np.int64)
    visited = _m4_basin_hierarchy_np.zeros(height.size, bool)
    for first in _m4_basin_hierarchy_np.flatnonzero(valid):
        if visited[first]:
            continue
        plateau = [int(first)]
        visited[first] = True
        pending = _m4_basin_hierarchy_deque(plateau)
        seeds = []
        while pending:
            cell = pending.popleft()
            lower = []
            for neighbor in _neighbors(cell, rows, columns):
                if not valid[neighbor]:
                    continue
                if height[neighbor] < height[cell]:
                    lower.append(neighbor)
                elif height[neighbor] == height[cell] and not visited[neighbor]:
                    visited[neighbor] = True
                    plateau.append(neighbor)
                    pending.append(neighbor)
            if lower:
                receiver[cell] = min(lower, key=lambda neighbor: (height[neighbor], neighbor))
                seeds.append(cell)
        if not seeds:
            seeds = [min(plateau)]
        assigned = set(seeds)
        pending = _m4_basin_hierarchy_deque(sorted(seeds))
        while pending:
            cell = pending.popleft()
            for neighbor in _neighbors(cell, rows, columns):
                if valid[neighbor] and height[neighbor] == height[cell] and neighbor not in assigned:
                    assigned.add(neighbor)
                    receiver[neighbor] = cell
                    pending.append(neighbor)
    return receiver

# --- terrain_pipeline/td_basin_hierarchy.py:64 ---
def build_basin_hierarchy(source):
    from terrain_pipeline.basin_storage import validate_td_source as _m4_basin_hierarchy_validate_td_source
    from terrain_pipeline.common_infra import identity as _m4_basin_hierarchy_identity
    from terrain_pipeline.common_infra import readonly as _m4_basin_hierarchy_readonly
    _m4_basin_hierarchy_validate_td_source(source)
    source_arrays = source["arrays"]
    bed = source_arrays["height_m"]
    rows, columns = bed.shape
    height = bed.ravel()
    valid = source_arrays["valid_mask"].ravel()
    opened = source_arrays["open_boundary_mask"].ravel()
    area = source["metadata"]["spacing_m"] ** 2
    ordered = _m4_basin_hierarchy_np.flatnonzero(valid)
    ordered = ordered[_m4_basin_hierarchy_np.argsort(height[ordered], kind="stable")]
    union_parent = _m4_basin_hierarchy_np.arange(height.size, dtype=_m4_basin_hierarchy_np.int64)
    active = _m4_basin_hierarchy_np.zeros(height.size, bool)
    current_node = _m4_basin_hierarchy_np.full(height.size, -1, _m4_basin_hierarchy_np.int64)
    owner = _m4_basin_hierarchy_np.full(height.size, -1, _m4_basin_hierarchy_np.int64)
    parents, births, upper, children, own_cells = [], [], [], [], []

    def find(cell):
        root = int(cell)
        while union_parent[root] != root:
            root = int(union_parent[root])
        while union_parent[cell] != cell:
            previous = int(union_parent[cell])
            union_parent[cell] = root
            cell = previous
        return root

    def union(first, second):
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            union_parent[max(first_root, second_root)] = min(first_root, second_root)

    start = 0
    while start < ordered.size:
        stop = start + 1
        level = height[ordered[start]]
        while stop < ordered.size and height[ordered[stop]] == level:
            stop += 1
        batch = ordered[start:stop]
        contacts = []
        for cell in batch:
            for neighbor in _neighbors(cell, rows, columns):
                if active[neighbor]:
                    contacts.append((int(cell), int(current_node[find(neighbor)])))
        active[batch] = True
        for cell in batch:
            for neighbor in _neighbors(cell, rows, columns):
                if active[neighbor]:
                    union(cell, neighbor)
        groups = {}
        for cell in batch:
            groups.setdefault(find(cell), [[], set()])[0].append(int(cell))
        for cell, node in contacts:
            groups[find(cell)][1].add(node)
        for root, (cells, previous) in sorted(groups.items()):
            previous = sorted(previous)
            if len(previous) == 1:
                node = previous[0]
                own_cells[node].extend(cells)
            else:
                node = len(parents)
                parents.append(-1)
                births.append(float(level))
                upper.append(_m4_basin_hierarchy_np.inf)
                children.append(previous)
                own_cells.append(cells)
                for child in previous:
                    parents[child] = node
                    upper[child] = float(level)
            current_node[root] = node
            owner[cells] = node
        start = stop

    receiver = _flat_receivers(height, valid, rows, columns)
    contribution = _m4_basin_hierarchy_np.full(height.size, -1, _m4_basin_hierarchy_np.int64)
    for first in _m4_basin_hierarchy_np.flatnonzero(valid):
        pending = []
        cell = int(first)
        while contribution[cell] < 0:
            pending.append(cell)
            downstream = int(receiver[cell])
            if downstream < 0:
                contribution[cell] = owner[cell]
                break
            cell = downstream
        contribution[pending] = contribution[cell]

    face_cells = []
    for cell in _m4_basin_hierarchy_np.flatnonzero(valid):
        row, column = divmod(int(cell), columns)
        if column + 1 < columns and valid[cell + 1]:
            face_cells.append((cell, cell + 1))
        if row + 1 < rows and valid[cell + columns]:
            face_cells.append((cell, cell + columns))
    faces = _m4_basin_hierarchy_np.array(face_cells, _m4_basin_hierarchy_np.int64).reshape(-1, 2)
    face_nodes = owner[faces]
    depths = _m4_basin_hierarchy_np.zeros(len(parents), _m4_basin_hierarchy_np.int64)
    ancestor = _m4_basin_hierarchy_np.array(parents, _m4_basin_hierarchy_np.int64)
    for node in range(len(parents) - 1, -1, -1):
        if parents[node] >= 0:
            depths[node] = depths[parents[node]] + 1
        else:
            ancestor[node] = node
    jumps = [ancestor]
    for exponent in range(1, max(1, int(depths.max()).bit_length())):
        jumps.append(jumps[-1][jumps[-1]])
    first_nodes, second_nodes = face_nodes[:, 0].copy(), face_nodes[:, 1].copy()
    swap = depths[first_nodes] < depths[second_nodes]
    temporary = first_nodes[swap].copy()
    first_nodes[swap] = second_nodes[swap]
    second_nodes[swap] = temporary
    difference = depths[first_nodes] - depths[second_nodes]
    for exponent, jump in enumerate(jumps):
        selected = (difference & (1 << exponent)) != 0
        first_nodes[selected] = jump[first_nodes[selected]]
    for jump in reversed(jumps):
        selected = jump[first_nodes] != jump[second_nodes]
        first_nodes[selected] = jump[first_nodes[selected]]
        second_nodes[selected] = jump[second_nodes[selected]]
    merge_nodes = _m4_basin_hierarchy_np.where(first_nodes == second_nodes, first_nodes, ancestor[first_nodes])

    curve_offsets = [0]
    curve_levels, curve_volumes = [], []
    subtree_sums = []
    stage_capacity, node_count, unknown_contact, open_contact, open_levels = [], [], [], [], []
    retained_entries = 0
    for node, cells in enumerate(own_cells):
        child_count = sum(node_count[child] for child in children[node])
        child_sum = sum(subtree_sums[child] for child in children[node])
        count = len(cells) + child_count
        values = _m4_basin_hierarchy_np.sort(height[cells])
        retained_entries += len(values)
        if retained_entries + len(curve_levels) > MAX_CURVE_ENTRIES:
            raise ValueError("hierarchy hypsometry work/memory budget exceeded")
        subtree_sums.append(child_sum + float(values.sum()))
        node_count.append(count)
        local_unknown = any(not valid[neighbor] for cell in cells for neighbor in _neighbors(cell, rows, columns))
        unknown_contact.append(local_unknown or any(unknown_contact[child] for child in children[node]))
        local_open = bool(opened[cells].any())
        open_contact.append(local_open or any(open_contact[child] for child in children[node]))
        local_open_level = float(height[_m4_basin_hierarchy_np.asarray(cells)[opened[cells]]].min()) if local_open else _m4_basin_hierarchy_np.inf
        open_levels.append(min([local_open_level] + [open_levels[child] for child in children[node]]))
        knots = _m4_basin_hierarchy_np.unique(_m4_basin_hierarchy_np.concatenate(([births[node]], values[values >= births[node]],
                                         [] if _m4_basin_hierarchy_np.isinf(upper[node]) else [upper[node]])))
        knots = knots[knots <= upper[node]]
        prefix = _m4_basin_hierarchy_np.concatenate(([0.0], _m4_basin_hierarchy_np.cumsum(values, dtype=_m4_basin_hierarchy_np.float64)))
        counts = _m4_basin_hierarchy_np.searchsorted(values, knots, side="left")
        volumes = area * (knots * (counts + child_count) - prefix[counts] - child_sum)
        curve_levels.extend(knots)
        curve_volumes.extend(volumes)
        curve_offsets.append(len(curve_levels))
        stage_capacity.append(_m4_basin_hierarchy_np.inf if _m4_basin_hierarchy_np.isinf(upper[node]) else float(volumes[-1] - volumes[0]))

    arrays = dict(source_arrays)
    arrays.update({"receiver": receiver, "cell_owner": owner.reshape(bed.shape),
        "contribution_owner": contribution.reshape(bed.shape), "node_parent": _m4_basin_hierarchy_np.array(parents, _m4_basin_hierarchy_np.int64),
        "node_birth_m": _m4_basin_hierarchy_np.array(births), "node_upper_m": _m4_basin_hierarchy_np.array(upper),
        "node_cell_count": _m4_basin_hierarchy_np.array(node_count, _m4_basin_hierarchy_np.int64), "node_unknown_contact": _m4_basin_hierarchy_np.array(unknown_contact, bool),
        "node_open_boundary": _m4_basin_hierarchy_np.array(open_contact, bool), "node_open_level_m": _m4_basin_hierarchy_np.array(open_levels),
        "face_cells": faces, "face_nodes": face_nodes, "face_merge_node": merge_nodes,
        "face_level_m": _m4_basin_hierarchy_np.max(height[faces], axis=1),
        "boundary_cells": _m4_basin_hierarchy_np.flatnonzero(opened), "boundary_level_m": height[opened],
        "curve_offsets": _m4_basin_hierarchy_np.array(curve_offsets, _m4_basin_hierarchy_np.int64), "curve_level_m": _m4_basin_hierarchy_np.array(curve_levels),
        "curve_volume_m3": _m4_basin_hierarchy_np.array(curve_volumes), "stage_capacity_m3": _m4_basin_hierarchy_np.array(stage_capacity)})
    arrays = {key: _m4_basin_hierarchy_readonly(value) for key, value in arrays.items()}
    metadata = {"schema": "td-basin-hierarchy-v1", "algorithm": "D4-equal-level-batch-lower-star-v1",
        "source_identity_sha256": source["identity_sha256"], "source_metadata": source["metadata"],
        "spacing_m": source["metadata"]["spacing_m"], "origin_m_xz": source["metadata"]["origin_m_xz"],
        "max_curve_entries": MAX_CURVE_ENTRIES, "retained_hypsometry_entries": retained_entries,
        "capacity_semantics": "absolute subtree V(h); stage=V(upper)-V(birth); roots unbounded",
        "nonfinite_sentinel": "+inf only in upper/open-level/stage-capacity arrays means no finite event; never a solved water level",
        "receiver_semantics": "D4 nonascending static contribution routing, not hydraulic exchange",
        "natural_outlet_verified": False, "hydraulic_ready": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": _m4_basin_hierarchy_identity(arrays, metadata)}

# --- terrain_pipeline/td_basin_hierarchy.py:240 ---
def basin_volume_at_level(result, node, level_m):
    arrays = result["arrays"]
    if type(node) is not int or not 0 <= node < len(arrays["node_parent"]) or not _m4_basin_hierarchy_np.isfinite(level_m):
        raise ValueError("finite level and valid node required")
    if level_m < arrays["node_birth_m"][node] or level_m > arrays["node_upper_m"][node]:
        raise ValueError("level outside connected node stage")
    start, stop = arrays["curve_offsets"][node:node + 2]
    levels = arrays["curve_level_m"][start:stop]
    volumes = arrays["curve_volume_m3"][start:stop]
    if level_m > levels[-1]:
        return float(volumes[-1] + (level_m - levels[-1]) * arrays["node_cell_count"][node] * result["metadata"]["spacing_m"] ** 2)
    return float(_m4_basin_hierarchy_np.interp(level_m, levels, volumes))

# --- terrain_pipeline/td_basin_hierarchy.py:254 ---
def validate_basin_hierarchy(result, *, reconstruct=False):
    from terrain_pipeline.basin_storage import validate_td_source as _m4_basin_hierarchy_validate_td_source
    from terrain_pipeline.common_infra import identity as _m4_basin_hierarchy_identity
    arrays, metadata = result["arrays"], result["metadata"]
    source_arrays = {key: arrays[key] for key in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask")}
    source = {"arrays": source_arrays, "metadata": metadata["source_metadata"],
              "identity_sha256": metadata["source_identity_sha256"]}
    _m4_basin_hierarchy_validate_td_source(source)
    if metadata["schema"] != "td-basin-hierarchy-v1" or result["identity_sha256"] != _m4_basin_hierarchy_identity(arrays, metadata):
        raise ValueError("hierarchy identity/schema mismatch")
    required = {"height_m", "valid_mask", "protected_mask", "open_boundary_mask", "receiver", "cell_owner",
        "contribution_owner", "node_parent", "node_birth_m", "node_upper_m", "node_cell_count",
        "node_unknown_contact", "node_open_boundary", "node_open_level_m", "face_cells", "face_nodes",
        "face_merge_node", "face_level_m", "boundary_cells", "boundary_level_m", "curve_offsets",
        "curve_level_m", "curve_volume_m3", "stage_capacity_m3"}
    if set(arrays) != required:
        raise ValueError("unexpected hierarchy arrays")
    parent = arrays["node_parent"]
    node_count = len(parent)
    owner = arrays["cell_owner"].ravel()
    valid = arrays["valid_mask"].ravel()
    receiver = arrays["receiver"]
    if (parent.dtype != _m4_basin_hierarchy_np.int64 or parent.ndim != 1 or not 1 <= node_count <= valid.sum() * 2 or
            _m4_basin_hierarchy_np.any((parent != -1) & ((parent <= _m4_basin_hierarchy_np.arange(node_count)) | (parent >= node_count))) or
            owner.shape != valid.shape or _m4_basin_hierarchy_np.any(owner[~valid] != -1) or
            _m4_basin_hierarchy_np.any((owner[valid] < 0) | (owner[valid] >= node_count)) or receiver.shape != valid.shape or
            receiver.dtype != _m4_basin_hierarchy_np.int64 or _m4_basin_hierarchy_np.any((receiver < -1) | (receiver >= valid.size))):
        raise ValueError("invalid hierarchy ownership/parent/receiver")
    bed = arrays["height_m"].ravel()
    columns = arrays["height_m"].shape[1]
    selected = _m4_basin_hierarchy_np.flatnonzero(receiver >= 0)
    target = receiver[selected]
    distance = abs(selected // columns - target // columns) + abs(selected % columns - target % columns)
    if _m4_basin_hierarchy_np.any(distance != 1) or not valid[target].all() or _m4_basin_hierarchy_np.any(bed[target] > bed[selected]):
        raise ValueError("invalid D4 nonascending receiver")
    complete = _m4_basin_hierarchy_np.zeros(valid.size, bool)
    contribution = arrays["contribution_owner"].ravel()
    for first in _m4_basin_hierarchy_np.flatnonzero(valid):
        pending = []
        seen = set()
        cell = int(first)
        while not complete[cell]:
            if cell in seen:
                raise ValueError("receiver cycle")
            seen.add(cell)
            pending.append(cell)
            if receiver[cell] < 0:
                if contribution[cell] != owner[cell]:
                    raise ValueError("terminal contribution mismatch")
                break
            downstream = int(receiver[cell])
            if contribution[cell] != contribution[downstream]:
                raise ValueError("contribution receiver mismatch")
            cell = downstream
        complete[pending] = True
    faces = arrays["face_cells"]
    if faces.ndim != 2 or faces.shape[1] != 2 or faces.dtype != _m4_basin_hierarchy_np.int64 or _m4_basin_hierarchy_np.any((faces < 0) | (faces >= valid.size)):
        raise ValueError("invalid face indices")
    if not valid[faces].all() or not _m4_basin_hierarchy_np.array_equal(arrays["face_nodes"], owner[faces]):
        raise ValueError("invalid face ownership")
    distance = abs(faces[:, 0] // columns - faces[:, 1] // columns) + abs(faces[:, 0] % columns - faces[:, 1] % columns)
    if _m4_basin_hierarchy_np.any(distance != 1) or not _m4_basin_hierarchy_np.array_equal(arrays["face_level_m"], _m4_basin_hierarchy_np.max(bed[faces], axis=1)):
        raise ValueError("invalid D4 face elevations")
    expected_faces = []
    rows = arrays["height_m"].shape[0]
    for cell in _m4_basin_hierarchy_np.flatnonzero(valid):
        row, column = divmod(int(cell), columns)
        if column + 1 < columns and valid[cell + 1]:
            expected_faces.append((cell, cell + 1))
        if row + 1 < rows and valid[cell + columns]:
            expected_faces.append((cell, cell + columns))
    if not _m4_basin_hierarchy_np.array_equal(faces, _m4_basin_hierarchy_np.array(expected_faces, _m4_basin_hierarchy_np.int64).reshape(-1, 2)):
        raise ValueError("missing/duplicate D4 faces")
    for key in ("node_birth_m", "node_upper_m", "node_cell_count", "node_unknown_contact", "node_open_boundary",
                "node_open_level_m", "stage_capacity_m3"):
        if arrays[key].shape != (node_count,):
            raise ValueError("node array shape mismatch")
    births, upper = arrays["node_birth_m"], arrays["node_upper_m"]
    child = _m4_basin_hierarchy_np.flatnonzero(parent >= 0)
    if (not _m4_basin_hierarchy_np.isfinite(births).all() or _m4_basin_hierarchy_np.any(_m4_basin_hierarchy_np.isnan(upper)) or _m4_basin_hierarchy_np.any(upper < births) or
            not _m4_basin_hierarchy_np.array_equal(upper[child], births[parent[child]]) or
            not _m4_basin_hierarchy_np.isposinf(upper[parent < 0]).all()):
        raise ValueError("invalid parent stage elevation")
    counts = _m4_basin_hierarchy_np.bincount(owner[valid], minlength=node_count)
    for node in range(node_count):
        if parent[node] >= 0:
            counts[parent[node]] += counts[node]
    if not _m4_basin_hierarchy_np.array_equal(counts, arrays["node_cell_count"]):
        raise ValueError("subtree cell double counting")
    if not _m4_basin_hierarchy_np.array_equal(arrays["boundary_cells"], _m4_basin_hierarchy_np.flatnonzero(arrays["open_boundary_mask"].ravel())) or not _m4_basin_hierarchy_np.array_equal(
            arrays["boundary_level_m"], bed[arrays["boundary_cells"]]):
        raise ValueError("boundary face mismatch")
    offsets = arrays["curve_offsets"]
    levels, volumes = arrays["curve_level_m"], arrays["curve_volume_m3"]
    if (offsets.shape != (node_count + 1,) or offsets[0] != 0 or offsets[-1] != len(levels) or
            _m4_basin_hierarchy_np.any(_m4_basin_hierarchy_np.diff(offsets) <= 0) or levels.shape != volumes.shape or
            not _m4_basin_hierarchy_np.isfinite(levels).all() or not _m4_basin_hierarchy_np.isfinite(volumes).all() or _m4_basin_hierarchy_np.any(volumes < -1e-6)):
        raise ValueError("invalid capacity CSR")
    for node in range(node_count):
        start, stop = offsets[node:node + 2]
        if (_m4_basin_hierarchy_np.any(_m4_basin_hierarchy_np.diff(levels[start:stop]) <= 0) or _m4_basin_hierarchy_np.any(_m4_basin_hierarchy_np.diff(volumes[start:stop]) < -1e-6) or
                levels[start] != arrays["node_birth_m"][node] or levels[stop - 1] > arrays["node_upper_m"][node]):
            raise ValueError("invalid stage curve")
        capacity = arrays["stage_capacity_m3"][node]
        if _m4_basin_hierarchy_np.isfinite(upper[node]):
            if levels[stop - 1] != upper[node] or capacity != volumes[stop - 1] - volumes[start]:
                raise ValueError("stage marginal capacity mismatch")
        elif not _m4_basin_hierarchy_np.isposinf(capacity):
            raise ValueError("invalid root capacity sentinel")
    if reconstruct:
        expected = build_basin_hierarchy(source)
        if metadata != expected["metadata"] or set(arrays) != set(expected["arrays"]) or any(
                not _m4_basin_hierarchy_np.array_equal(value, expected["arrays"][key]) for key, value in arrays.items()):
            raise ValueError("hierarchy arrays differ from exact source reconstruction")
    return True

# --- terrain_pipeline/td_basin_hierarchy.py:369 ---
def save_basin_hierarchy(path, result):
    from terrain_pipeline.common_infra import save_bundle as _m4_basin_hierarchy_save_bundle
    _m4_basin_hierarchy_save_bundle(path, result, validator=lambda bundle: validate_basin_hierarchy(bundle, reconstruct=True))

# --- terrain_pipeline/td_basin_hierarchy.py:373 ---
def load_basin_hierarchy(path, *, expected_sha256, expected_identity):
    from terrain_pipeline.common_infra import load_bundle as _m4_basin_hierarchy_load_bundle
    result = _m4_basin_hierarchy_load_bundle(path, expected_sha256=expected_sha256, validator=validate_basin_hierarchy)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external hierarchy identity mismatch")
    return result

# --- terrain_pipeline/td_basin_spill_network.py:16 ---
SPILL_NETWORK_SCHEMA = "td-basin-spill-network-v1"

# --- terrain_pipeline/td_basin_spill_network.py:17 ---
MAX_JSON_BYTES = 128 * 1024 * 1024

# --- terrain_pipeline/td_basin_spill_network.py:20 ---
def _read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON")

    return _m4_basin_spill_network_json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)

# --- terrain_pipeline/td_basin_spill_network.py:35 ---
def _finite(value):
    return float(value) if _m4_basin_spill_network_math.isfinite(value) else None

# --- terrain_pipeline/td_basin_spill_network.py:39 ---
def _checked_network(hierarchy, reach_networks, storage, hierarchy_pin, storage_pin, face_sink=None):
    from terrain_pipeline.td_surface_reaches import _checked_surface_reaches as _m4_basin_spill_network_checked_surface_reaches
    from terrain_pipeline.td_surface_reaches import _freeze as _m4_basin_spill_network_freeze
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_spill_network_hash
    from terrain_pipeline.td_surface_reaches import _plain as _m4_basin_spill_network_plain
    from terrain_pipeline.td_surface_reaches import _storage_match as _m4_basin_spill_network_storage_match
    if hierarchy["identity_sha256"] != hierarchy_pin:
        raise ValueError("external hierarchy identity mismatch")
    validate_basin_hierarchy(hierarchy)
    if storage is not None:
        if storage_pin is None or storage["identity_sha256"] != storage_pin:
            raise ValueError("external storage identity mismatch")
        _m4_basin_spill_network_storage_match(hierarchy, storage)
    elif storage_pin is not None:
        raise ValueError("storage pin without storage")
    arrays = hierarchy["arrays"]
    parent = arrays["node_parent"]
    chains = []
    for node in range(len(parent)):
        chain = []
        cursor = node
        while cursor >= 0:
            if cursor in chain:
                raise ValueError("parent cycle")
            chain.append(cursor)
            cursor = int(parent[cursor])
        chains.append(chain)
    ancestor_sets = [set(chain) for chain in chains]
    bed = arrays["height_m"].ravel()
    owners = arrays["cell_owner"].ravel()
    protected = arrays["protected_mask"].ravel()
    unknown = arrays["node_unknown_contact"]
    columns = arrays["height_m"].shape[1]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]

    def point(cell):
        row, column = divmod(cell, columns)
        return [origin[0] + column * spacing, float(bed[cell]), origin[1] + row * spacing]

    spills, incident, rejected = [], {}, _m4_basin_spill_network_Counter()
    pair_minimum = {}
    for pair in arrays["face_cells"]:
        first, second = map(int, pair)
        first_owner, second_owner = int(owners[first]), int(owners[second])
        if first_owner == second_owner or protected[first] or protected[second] or unknown[first_owner] or unknown[second_owner]:
            continue
        key = tuple(sorted((first_owner, second_owner)))
        pair_minimum[key] = min(pair_minimum.get(key, _m4_basin_spill_network_math.inf), float(max(bed[first], bed[second])))
    counts = _m4_basin_spill_network_Counter()
    for face, pair in enumerate(arrays["face_cells"]):
        first, second = map(int, pair)
        first_owner, second_owner = int(owners[first]), int(owners[second])
        second_ancestors = ancestor_sets[second_owner]
        merge = next((node for node in chains[first_owner] if node in second_ancestors), -1)
        if merge != int(arrays["face_merge_node"][face]):
            raise ValueError("saved face merge is not owner LCA")
        if first_owner == second_owner:
            continue
        reasons = []
        if protected[first] or protected[second]:
            reasons.append("protected_endpoint")
        if unknown[first_owner] or unknown[second_owner]:
            reasons.append("unknown_owner_subtree")
        if merge < 0:
            reasons.append("no_common_merge")
        sill = float(max(bed[first], bed[second]))
        if sill != arrays["face_level_m"][face]:
            raise ValueError("face sill mismatch")
        endpoints = sorted([[float(value).hex() for value in point(cell)] for cell in (first, second)])
        face_id = "face:" + _m4_basin_spill_network_hash([hierarchy["metadata"]["source_identity_sha256"], endpoints])
        stages = []
        for owner in (first_owner, second_owner):
            chain = chains[owner]
            branch = chain[chain.index(merge) - 1] if merge in chain and owner != merge else None
            stages.append(branch)
        flux = None
        if storage is not None:
            water = storage["arrays"]
            forward = float(water["face_forward_m3"][face])
            reverse = float(water["face_reverse_m3"][face])
            flux = {"forward_m3": forward, "reverse_m3": reverse,
                    "gross_m3": forward + reverse, "net_first_to_second_m3": forward - reverse,
                    "positive_transfer_recorded": forward + reverse > 0}
        record = {"face_id": face_id, "face_index": face, "face_cell_ids": [first, second],
                  "owner_ids": [first_owner, second_owner], "xyz_m": [point(first), point(second)],
                  "merge_node_id": merge, "merge_birth_m": None if merge < 0 else float(arrays["node_birth_m"][merge]),
                  "face_sill_m": sill, "physical_face_sill_m": sill, "merge_child_ids": stages,
                  "potential_connection_allowed": not reasons, "rejection_reasons": reasons,
                  "potential_only": flux is None or not flux["positive_transfer_recorded"],
                  "stored_whole_run_flux": flux}
        key = tuple(sorted(record["owner_ids"]))
        record["lowest_allowed_owner_pair_face"] = not reasons and sill == pair_minimum.get(key)
        record["classification"] = "rejected_adjacency" if reasons else "lowest_owner_pair_face" if record["lowest_allowed_owner_pair_face"] else "higher_owner_pair_adjacency"
        counts["cross_owner_faces"] += 1
        counts["allowed_potential_faces"] += not reasons
        counts["lowest_owner_pair_faces"] += record["lowest_allowed_owner_pair_face"]
        counts["recorded_transfer_faces"] += flux is not None and flux["positive_transfer_recorded"]
        if face_sink is None:
            spills.append(record)
        else:
            face_sink(record)
        rejected.update(reasons)
        for owner in (first_owner, second_owner):
            incident.setdefault(owner, []).append(face_id)
    cases = []
    thresholds = set()
    for network in reach_networks:
        expected = _m4_basin_spill_network_checked_surface_reaches(hierarchy, threshold_area_m2=network["threshold_area_m2"],
            expected_hierarchy_identity=hierarchy_pin, storage=storage, expected_storage_identity=storage_pin)
        if _m4_basin_spill_network_plain(network) != _m4_basin_spill_network_plain(expected):
            raise ValueError("reach semantic mismatch")
        if network["threshold_area_m2"] in thresholds:
            raise ValueError("duplicate reach threshold")
        thresholds.add(network["threshold_area_m2"])
        joins = []
        for node in network["nodes"]:
            if node["kind"] != "terminal":
                continue
            owner = int(owners[node["cell_id"]])
            joins.append({"reach_node_id": node["node_id"], "cell_id": node["cell_id"],
                          "terminal_kind": node["terminal_kind"], "owner_id": owner,
                          "contribution_leaf_id": int(arrays["contribution_owner"].ravel()[node["cell_id"]]),
                          "incident_face_ids": incident.get(owner, [])})
        cases.append({"threshold_area_m2": network["threshold_area_m2"],
                      "reach_identity_sha256": network["identity_sha256"], "terminal_owner_joins": joins})
    nodes = [{"node_id": node, "parent_id": int(parent[node]),
              "birth_m": float(arrays["node_birth_m"][node]),
              "upper_m": _finite(arrays["node_upper_m"][node]),
              "stage_capacity_m3": _finite(arrays["stage_capacity_m3"][node]),
              "unknown_contact": bool(unknown[node]), "open_boundary": bool(arrays["node_open_boundary"][node])}
             for node in range(len(parent))]
    result = {"schema": SPILL_NETWORK_SCHEMA, "algorithm": "unique-D4-cross-owner-face-LCA-v1",
              "hierarchy_identity_sha256": hierarchy_pin,
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "storage_identity_sha256": storage_pin,
              "grid": {"shape_zx": list(arrays["height_m"].shape), "spacing_m": spacing,
                       "origin_m_xz": origin, "axes": "X east, Z south; XYZ metres"},
              "basin_nodes": nodes, "spills": spills, "reach_cases": cases,
              "summary": {**{name: counts[name] for name in ("cross_owner_faces", "lowest_owner_pair_faces", "allowed_potential_faces", "recorded_transfer_faces")}, "rejection_counts": dict(rejected)},
              "flux_scope": {"elapsed_s": None if storage is None else (storage["arrays"]["depth_m"].shape[0] - 1) * storage["metadata"]["dt_s"],
                             "time_series_available": False, "spill_onset_known": False,
                             "semantics": "Unique physical face, ordered first-to-second. Whole-run directional integrals; never summed over nested basin ancestors or reported as outlet Q."},
              "flags": {"readonly": True, "bed_unchanged": True, "receiver_unchanged": True,
                        "hydraulic_ready": False, "transient_converged": False, "natural_outlet_verified": False,
                        "water_generated": False, "publishable": False},
              "limitations": "All cross-owner faces are potential adjacency, not actual spill outlets or routed channels. Lowest allowed owner-pair faces include ties and are not certified global basin escape saddles. LCA merge birth and physical face sill are distinct. Subtree capacity thresholds are not measured storage and cannot be added across ancestors. Rejected faces retain evidence but are not allowed graph links. No dynamic onset, discharge, channel geometry or new water."}
    result["identity_sha256"] = _m4_basin_spill_network_hash(result)
    return _m4_basin_spill_network_freeze(result)

# --- terrain_pipeline/td_basin_spill_network.py:185 ---
def make_basin_spill_network(hierarchy, *, expected_hierarchy_identity, reach_networks=(),
                            storage=None, expected_storage_identity=None):
    return _checked_network(hierarchy, reach_networks, storage, expected_hierarchy_identity, expected_storage_identity)

# --- terrain_pipeline/td_basin_spill_network.py:190 ---
def save_basin_spill_network(result, path):
    from terrain_pipeline.common_infra import publish_bytes as _m4_basin_spill_network_publish_bytes
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_spill_network_hash
    from terrain_pipeline.td_surface_reaches import _plain as _m4_basin_spill_network_plain
    plain = _m4_basin_spill_network_plain(result)
    digest = plain.pop("identity_sha256", None)
    if plain.get("schema") != SPILL_NETWORK_SCHEMA or _m4_basin_spill_network_hash(plain) != digest:
        raise ValueError("spill identity/schema mismatch")
    plain["identity_sha256"] = digest
    payload = _m4_basin_spill_network_json.dumps(plain, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("spill JSON budget exceeded")
    _m4_basin_spill_network_publish_bytes(path, payload)

# --- terrain_pipeline/td_basin_spill_network.py:202 ---
def load_basin_spill_network(path, *, expected_sha256, expected_identity, hierarchy,
                            reach_networks=(), storage=None):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_spill_network_file_sha256
    from terrain_pipeline.td_surface_reaches import _freeze as _m4_basin_spill_network_freeze
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_spill_network_hash
    path = _m4_basin_spill_network_Path(path)
    if path.stat().st_size > MAX_JSON_BYTES or _m4_basin_spill_network_file_sha256(path) != expected_sha256:
        raise ValueError("external spill hash/budget mismatch")
    checked = _checked_network(hierarchy, reach_networks, storage, hierarchy["identity_sha256"],
        None if storage is None else storage["identity_sha256"])
    semantic_identity = checked["identity_sha256"]
    del checked
    if semantic_identity != expected_identity:
        raise ValueError("saved spill semantics mismatch")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite JSON")

    result = _m4_basin_spill_network_json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)
    digest = result.pop("identity_sha256")
    if digest != expected_identity or _m4_basin_spill_network_hash(result) != digest:
        raise ValueError("external spill identity mismatch")
    result["identity_sha256"] = digest
    return _m4_basin_spill_network_freeze(result)

# --- terrain_pipeline/td_basin_spill_network.py:233 ---
def save_basin_spill_bundle(directory, hierarchy, *, expected_hierarchy_identity,
                           reach_networks=(), storage=None, expected_storage_identity=None):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_spill_network_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _m4_basin_spill_network_publish_bytes
    from terrain_pipeline.td_surface_reaches import _freeze as _m4_basin_spill_network_freeze
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_spill_network_hash
    from terrain_pipeline.td_surface_reaches import _plain as _m4_basin_spill_network_plain
    directory = _m4_basin_spill_network_Path(directory)
    chunks, pending = [], []

    def flush():
        if not pending:
            return
        name = f"faces-{len(chunks):04d}.json"
        payload = _m4_basin_spill_network_json.dumps(pending, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        _m4_basin_spill_network_publish_bytes(directory / name, payload)
        chunks.append({"file": name, "expected_sha256": _m4_basin_spill_network_file_sha256(directory / name),
                       "identity_sha256": _m4_basin_spill_network_hash(pending), "face_count": len(pending), "bytes": len(payload)})
        pending.clear()

    def sink(record):
        pending.append(record)
        if len(pending) == 2048:
            flush()

    metadata = _m4_basin_spill_network_plain(_checked_network(hierarchy, reach_networks, storage, expected_hierarchy_identity,
        expected_storage_identity, face_sink=sink))
    flush()
    metadata.pop("identity_sha256")
    metadata.pop("spills")
    metadata["schema"] = "td-basin-spill-sharded-v2"
    metadata["face_chunks"] = chunks
    metadata["contribution_leaf_graph"] = _leaf_graph(hierarchy, storage)
    metadata["identity_sha256"] = _m4_basin_spill_network_hash(metadata)
    _m4_basin_spill_network_publish_bytes(directory / "bundle.json", _m4_basin_spill_network_json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    return _m4_basin_spill_network_freeze(metadata)

# --- terrain_pipeline/td_basin_spill_network.py:266 ---
def load_basin_spill_bundle(path, *, expected_sha256, expected_identity, hierarchy,
                           reach_networks=(), storage=None):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_spill_network_file_sha256
    from terrain_pipeline.td_surface_reaches import _freeze as _m4_basin_spill_network_freeze
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_spill_network_hash
    from terrain_pipeline.td_surface_reaches import _plain as _m4_basin_spill_network_plain
    path = _m4_basin_spill_network_Path(path)
    if path.stat().st_size > 16 * 1024 * 1024 or _m4_basin_spill_network_file_sha256(path) != expected_sha256:
        raise ValueError("external spill bundle pin/budget mismatch")
    metadata = _read_json(path)
    digest = metadata.pop("identity_sha256")
    if digest != expected_identity or _m4_basin_spill_network_hash(metadata) != digest or metadata["schema"] != "td-basin-spill-sharded-v2":
        raise ValueError("external spill bundle identity mismatch")
    chunks = metadata["face_chunks"]
    if not isinstance(chunks, list) or len(chunks) > 1000:
        raise ValueError("invalid chunk registry")
    registered = set()
    for index, pin in enumerate(chunks):
        if pin["file"] != f"faces-{index:04d}.json" or type(pin["face_count"]) is not int or not 1 <= pin["face_count"] <= 2048:
            raise ValueError("unsafe chunk path/order/count")
        chunk_path = path.parent / pin["file"]
        if not chunk_path.is_file() or chunk_path.is_symlink() or chunk_path.resolve().parent != path.parent.resolve():
            raise ValueError("missing or redirected face chunk")
        registered.add(pin["file"])
    if {entry.name for entry in path.parent.glob("faces-*.json")} != registered:
        raise ValueError("extra or missing face chunk files")
    cursor, pending = 0, []

    def check_chunk():
        nonlocal cursor
        if not pending:
            return
        if cursor >= len(chunks):
            raise ValueError("missing face chunk")
        pin = chunks[cursor]
        if pin["file"] != f"faces-{cursor:04d}.json" or pin["face_count"] != len(pending):
            raise ValueError("face chunk order/count mismatch")
        chunk_path = path.parent / pin["file"]
        if chunk_path.stat().st_size != pin["bytes"] or pin["bytes"] > 4 * 1024 * 1024 or _m4_basin_spill_network_file_sha256(chunk_path) != pin["expected_sha256"]:
            raise ValueError("external face chunk pin/budget mismatch")
        payload = _read_json(chunk_path)
        if _m4_basin_spill_network_hash(payload) != pin["identity_sha256"] or payload != pending:
            raise ValueError("face chunk semantic mismatch")
        cursor += 1
        pending.clear()

    def sink(record):
        pending.append(record)
        if len(pending) == 2048:
            check_chunk()

    expected = _m4_basin_spill_network_plain(_checked_network(hierarchy, reach_networks, storage,
        metadata["hierarchy_identity_sha256"], metadata["storage_identity_sha256"], face_sink=sink))
    check_chunk()
    if cursor != len(chunks):
        raise ValueError("extra face chunks")
    expected.pop("identity_sha256")
    expected.pop("spills")
    expected["schema"] = metadata["schema"]
    expected["face_chunks"] = chunks
    expected["contribution_leaf_graph"] = _leaf_graph(hierarchy, storage)
    if expected != metadata:
        raise ValueError("bundle metadata semantics mismatch")
    metadata["identity_sha256"] = digest
    return _m4_basin_spill_network_freeze(metadata)

# --- terrain_pipeline/td_basin_spill_network.py:329 ---
def _leaf_graph(hierarchy, storage):
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_spill_network_hash
    arrays = hierarchy["arrays"]
    leaf = arrays["contribution_owner"].ravel()
    protected = arrays["protected_mask"].ravel()
    bed = arrays["height_m"].ravel()
    leaf_nodes = []
    leaf_ids = {}
    columns = arrays["height_m"].shape[1]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    valid = arrays["valid_mask"].ravel()
    for node in _m4_basin_spill_network_np.unique(leaf[valid]):
        cells = _m4_basin_spill_network_np.flatnonzero(valid & (leaf == node))
        terminals = cells[arrays["receiver"][cells] < 0]
        if len(terminals) != 1:
            raise ValueError("catchment requires unique receiver terminal")
        terminal = int(terminals[0])
        row, column = divmod(terminal, columns)
        xyz = [float(origin[0] + column * spacing), float(bed[terminal]), float(origin[1] + row * spacing)]
        stable_id = "leaf:" + _m4_basin_spill_network_hash([hierarchy["metadata"]["source_identity_sha256"], [value.hex() for value in xyz]])
        leaf_ids[int(node)] = stable_id
        kind = "protected_terminal" if protected[terminal] else "unknown_contact" if arrays["node_unknown_contact"][node] else "engineered_open" if arrays["open_boundary_mask"].ravel()[terminal] else "internal_basin"
        leaf_nodes.append({"leaf_id": int(node), "stable_leaf_id": stable_id,
                           "terminal_cell_id": terminal, "terminal_xyz_m": xyz, "terminal_kind": kind,
                           "cell_count": len(cells), "area_m2": len(cells) * spacing ** 2,
                           "cell_id_bounds": [int(cells.min()), int(cells.max())],
                           "bounds_semantics": "inclusive min/max bounds, not a contiguous membership range"})
    pairs = {}
    for face, cells in enumerate(arrays["face_cells"]):
        first, second = map(int, cells)
        first_leaf, second_leaf = int(leaf[first]), int(leaf[second])
        if first_leaf == second_leaf:
            continue
        key = tuple(sorted((first_leaf, second_leaf)))
        entry = pairs.setdefault(key, {"leaf_ids": list(key), "all_face_indices": [],
            "minimum_physical_sill_m": None, "minimum_face_indices": [],
            "forward_leaf0_to_leaf1_m3": 0., "reverse_leaf1_to_leaf0_m3": 0.,
            "rejected_face_indices": []})
        entry["all_face_indices"].append(face)
        rejected = protected[first] or protected[second] or arrays["node_unknown_contact"][first_leaf] or arrays["node_unknown_contact"][second_leaf]
        sill = float(max(bed[first], bed[second]))
        if rejected:
            entry["rejected_face_indices"].append(face)
        elif entry["minimum_physical_sill_m"] is None or sill < entry["minimum_physical_sill_m"]:
            entry["minimum_physical_sill_m"] = sill
            entry["minimum_face_indices"] = [face]
        elif sill == entry["minimum_physical_sill_m"]:
            entry["minimum_face_indices"].append(face)
        if storage is not None:
            forward = float(storage["arrays"]["face_forward_m3"][face])
            reverse = float(storage["arrays"]["face_reverse_m3"][face])
            along, against = (forward, reverse) if first_leaf == key[0] else (reverse, forward)
            entry["forward_leaf0_to_leaf1_m3"] += along
            entry["reverse_leaf1_to_leaf0_m3"] += against
    for entry in pairs.values():
        entry["stable_leaf_ids"] = [leaf_ids[node] for node in entry["leaf_ids"]]
        entry["pair_id"] = "leaf-pair:" + _m4_basin_spill_network_hash(sorted(entry["stable_leaf_ids"]))
        entry["surface_flux_whole_run"] = storage is not None
        entry["gross_m3"] = entry["forward_leaf0_to_leaf1_m3"] + entry["reverse_leaf1_to_leaf0_m3"]
        entry["net_leaf0_to_leaf1_m3"] = entry["forward_leaf0_to_leaf1_m3"] - entry["reverse_leaf1_to_leaf0_m3"]
        entry["potential_connection_allowed"] = bool(entry["minimum_face_indices"])
    return {"partition": "exclusive contribution_owner catchments, not nested cell_owner activation nodes",
            "semantics": "Each cross-leaf physical face appears once. Pair directional volumes are whole-run surface_flux, never discharge Q or known spill onset. Minimum pair faces are not global natural escape outlets. Rejected faces remain in measured ledger but are not traversable links.",
            "leaf_nodes": leaf_nodes, "pairs": list(pairs.values()), "unique_cross_leaf_faces": sum(len(entry["all_face_indices"]) for entry in pairs.values())}

# --- terrain_pipeline/td_basin_breach.py:14 ---
ALGORITHM = "td-explicit-d4-saddle-path-target-slope-v1"

# --- terrain_pipeline/td_basin_breach.py:15 ---
DEFAULT_PARAMETERS = {"erosion_scale_m": 0.15, "reference_volume_m3": 1000.0,
                      "reference_duration_s": 3600.0, "transport_ratio": 0.002,
                      "max_path_cells": 64}

# --- terrain_pipeline/td_basin_breach.py:20 ---
def _sha256(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(name + " must be externally supplied lowercase SHA256")
    return value

# --- terrain_pipeline/td_basin_breach.py:26 ---
def _path_ids(path_cell_ids, shape, max_path_cells):
    path = _m4_basin_breach_np.asarray(path_cell_ids)
    if path.ndim != 1 or path.dtype.kind not in "iu" or not 3 <= path.size <= max_path_cells:
        raise ValueError("path must be a bounded integer sequence with two anchors and an interior")
    if _m4_basin_breach_np.any(path < 0) or _m4_basin_breach_np.any(path >= _m4_basin_breach_math.prod(shape)) or _m4_basin_breach_np.unique(path).size != path.size:
        raise ValueError("path cells must be unique and inside domain")
    path = path.astype(_m4_basin_breach_np.int64)
    rows, columns = _m4_basin_breach_np.divmod(path, shape[1])
    if _m4_basin_breach_np.any(_m4_basin_breach_np.abs(_m4_basin_breach_np.diff(rows)) + _m4_basin_breach_np.abs(_m4_basin_breach_np.diff(columns)) != 1):
        raise ValueError("path must use explicit D4 faces")
    return path

# --- terrain_pipeline/td_basin_breach.py:39 ---
def saddle_path_face_identity(height_m, path_cell_ids, *, source_identity_sha256, topology_identity_sha256):
    """Identity of ordered directed D4 faces, tied to the caller's frozen topology."""
    from terrain_pipeline.geology import _json as _m4_basin_breach_json
    from terrain_pipeline.geology import _material_shape as _m4_basin_breach_shape
    height = _m4_basin_breach_np.asarray(height_m, _m4_basin_breach_np.float64)
    shape = _m4_basin_breach_shape(height.shape)
    topology = _sha256(topology_identity_sha256, "topology_identity_sha256")
    source = _sha256(source_identity_sha256, "source_identity_sha256")
    path = _path_ids(path_cell_ids, shape, 64)
    record = {"shape": list(shape), "topology_identity_sha256": topology,
              "source_identity_sha256": source,
              "original_path_bed_m": [float(value) if _m4_basin_breach_math.isfinite(value) else None for value in height.ravel()[path]],
              "directed_faces": _m4_basin_breach_np.column_stack((path[:-1], path[1:])).tolist()}
    return _m4_basin_breach_hashlib.sha256(_m4_basin_breach_json(record).encode("utf-8")).hexdigest()

# --- terrain_pipeline/td_basin_breach.py:53 ---
def _parameters(parameters):
    from terrain_pipeline.geology import _material_positive as _m4_basin_breach_positive
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown saddle breach parameter")
    config = {**DEFAULT_PARAMETERS, **supplied}
    for name in ("erosion_scale_m", "transport_ratio"):
        config[name] = _m4_basin_breach_positive(config[name], name, allow_zero=True)
    for name in ("reference_volume_m3", "reference_duration_s"):
        config[name] = _m4_basin_breach_positive(config[name], name)
    maximum = config["max_path_cells"]
    if not isinstance(maximum, (int, _m4_basin_breach_np.integer)) or isinstance(maximum, (bool, _m4_basin_breach_np.bool_)) or not 3 <= maximum <= 64:
        raise ValueError("path work budget must be 3..64 cells")
    for name in ("erosion_scale_m", "reference_volume_m3", "reference_duration_s", "transport_ratio"):
        if config[name] != DEFAULT_PARAMETERS[name]:
            raise ValueError("saddle contract v1 fixes " + name)
    config["max_path_cells"] = int(maximum)
    return config

# --- terrain_pipeline/td_basin_breach.py:72 ---
def _path_values(values, shape, path, name):
    values = _m4_basin_breach_np.asarray(values)
    if values.dtype.kind not in "fiu":
        raise ValueError(name + " must be numeric")
    if values.shape == shape or values.shape == (_m4_basin_breach_math.prod(shape),):
        result = values.ravel()[path].astype(_m4_basin_breach_np.float64)
    elif values.shape == path.shape:
        result = values.astype(_m4_basin_breach_np.float64)
    else:
        raise ValueError(name + " must match path or domain")
    if not _m4_basin_breach_np.isfinite(result).all() or _m4_basin_breach_np.any(result < 0):
        raise ValueError(name + " must be finite nonnegative")
    return result

# --- terrain_pipeline/td_basin_breach.py:87 ---
def _hydro_evidence(evidence, hydro_identity, path, shape):
    from terrain_pipeline.geology import _material_positive as _m4_basin_breach_positive
    if evidence is None:
        return None
    required = {"hydro_identity_sha256", "face_cell_ids", "outward_volume_m3", "positive_outflow_steps", "dt_s"}
    if not isinstance(evidence, dict) or set(evidence) != required or evidence["hydro_identity_sha256"] != hydro_identity:
        raise ValueError("invalid hydro face evidence identity/fields")
    face = _m4_basin_breach_np.asarray(evidence["face_cell_ids"])
    if face.shape != (2,) or face.dtype.kind not in "iu" or not any(_m4_basin_breach_np.array_equal(face, path[index:index + 2]) for index in range(path.size - 1)):
        raise ValueError("outward saddle face must be an ordered path D4 face")
    steps = evidence["positive_outflow_steps"]
    if not isinstance(steps, (int, _m4_basin_breach_np.integer)) or isinstance(steps, (bool, _m4_basin_breach_np.bool_)) or steps < 0:
        raise ValueError("invalid positive outward-flow step count")
    volume = _m4_basin_breach_positive(evidence["outward_volume_m3"], "outward_volume_m3", allow_zero=True)
    dt = _m4_basin_breach_positive(evidence["dt_s"], "dt_s")
    duration = int(steps) * dt
    if not _m4_basin_breach_math.isfinite(duration):
        raise ValueError("face wet duration overflow")
    return {**evidence, "face_cell_ids": list(map(int, face)), "outward_volume_m3": volume,
            "positive_outflow_steps": int(steps), "dt_s": dt, "wet_duration_s": duration}

# --- terrain_pipeline/td_basin_breach.py:108 ---
def _anchor_evidence(evidence, height, valid, protected, path, topology_identity):
    if evidence is None:
        return None
    required = {"topology_identity_sha256", "source_basin_id", "destination_basin_id", "tail_cell_ids", "engineering_open_boundary"}
    if not isinstance(evidence, dict) or set(evidence) != required or evidence["topology_identity_sha256"] != topology_identity:
        raise ValueError("invalid downstream anchor evidence")
    for name in ("source_basin_id", "destination_basin_id"):
        if not isinstance(evidence[name], (int, _m4_basin_breach_np.integer)) or isinstance(evidence[name], (bool, _m4_basin_breach_np.bool_)) or evidence[name] < 0:
            raise ValueError("invalid anchor basin id")
    if type(evidence["engineering_open_boundary"]) is not bool:
        raise ValueError("engineering boundary evidence must be boolean")
    tail = _m4_basin_breach_np.asarray(evidence["tail_cell_ids"])
    if tail.ndim != 1 or tail.dtype.kind not in "iu" or not 1 <= tail.size <= 64:
        raise ValueError("anchor tail must be a bounded integer sequence")
    tail = tail.astype(_m4_basin_breach_np.int64)
    if tail[0] != path[-1] or _m4_basin_breach_np.any(tail < 0) or _m4_basin_breach_np.any(tail >= height.size) or _m4_basin_breach_np.unique(tail).size != tail.size or _m4_basin_breach_np.intersect1d(tail[1:], path[:-1]).size:
        raise ValueError("anchor tail loops back or lies outside domain")
    rows, cols = _m4_basin_breach_np.divmod(tail, height.shape[1])
    if _m4_basin_breach_np.any(_m4_basin_breach_np.abs(_m4_basin_breach_np.diff(rows)) + _m4_basin_breach_np.abs(_m4_basin_breach_np.diff(cols)) != 1):
        raise ValueError("anchor tail must use D4 faces")
    if _m4_basin_breach_np.any(~valid.ravel()[tail]) or _m4_basin_breach_np.any(protected.ravel()[tail]) or _m4_basin_breach_np.any(_m4_basin_breach_np.diff(height.ravel()[tail]) > 0):
        raise ValueError("anchor tail crosses unknown/protection or climbs original bed")
    if not height.ravel()[path[-1]] < height.ravel()[path[0]]:
        raise ValueError("downstream anchor must be lower than start")
    if evidence["engineering_open_boundary"]:
        row, col = divmod(int(tail[-1]), height.shape[1])
        if row not in (0, height.shape[0] - 1) and col not in (0, height.shape[1] - 1):
            raise ValueError("engineering tail does not reach domain boundary")
    elif evidence["source_basin_id"] == evidence["destination_basin_id"]:
        raise ValueError("anchor returns to source basin")
    return {**evidence, "tail_cell_ids": tail.tolist(), "source_basin_id": int(evidence["source_basin_id"]),
            "destination_basin_id": int(evidence["destination_basin_id"])}

# --- terrain_pipeline/td_basin_breach.py:142 ---
def generate_saddle_breach(height_m, valid_mask, *, spacing_m, materials,
                           path_cell_ids, target_bed_m, path_face_identity,
                           source_identity_sha256, topology_identity_sha256,
                           hydro_identity_sha256, routed_volume_m3, wet_duration_s,
                           hydro_face_evidence=None, downstream_anchor_evidence=None,
                           parameters=None):
    """Cut only when every interior cell meets thickness and water potential.

    Target slope is an explicit new heuristic, not the original-bed incision
    slope. Both end anchors stay unchanged. All solids remain explicitly stored
    at the endpoint's independent sediment inventory; hydrological rerouting and
    any later sediment transfer require rebuilt topology and separate accounting.
    """
    from terrain_pipeline.geology import _material_bundle as _m4_basin_breach_bundle
    from terrain_pipeline.geology import _mask as _m4_basin_breach_mask
    from terrain_pipeline.geology import _material_positive as _m4_basin_breach_positive
    from terrain_pipeline.geology import _material_shape as _m4_basin_breach_shape
    from terrain_pipeline.geology import _validate_cold_material as _m4_basin_breach_validate_cold_material
    height = _m4_basin_breach_np.asarray(height_m)
    shape = _m4_basin_breach_shape(height.shape)
    if height.dtype.kind not in "fiu":
        raise ValueError("height must be numeric")
    height = height.astype(_m4_basin_breach_np.float64)
    valid = _m4_basin_breach_mask(valid_mask, shape, "valid_mask")
    if valid_mask is None or not _m4_basin_breach_np.isfinite(height[valid]).all() or _m4_basin_breach_np.isinf(height).any():
        raise ValueError("valid height must be finite")
    spacing = _m4_basin_breach_positive(spacing_m, "spacing_m")
    if not _m4_basin_breach_math.isfinite(spacing ** 2) or spacing ** 2 == 0:
        raise ValueError("cell area outside numerical budget")
    config = _parameters(parameters)
    path = _path_ids(path_cell_ids, shape, config["max_path_cells"])
    source_identity = _sha256(source_identity_sha256, "source_identity_sha256")
    topology_identity = _sha256(topology_identity_sha256, "topology_identity_sha256")
    hydro_identity = _sha256(hydro_identity_sha256, "hydro_identity_sha256")
    expected_faces = saddle_path_face_identity(height, path, source_identity_sha256=source_identity,
                                               topology_identity_sha256=topology_identity)
    if _sha256(path_face_identity, "path_face_identity") != expected_faces:
        raise ValueError("path face identity does not match ordered topology-bound D4 faces")
    target = _m4_basin_breach_np.asarray(target_bed_m)
    if target.shape != path.shape or target.dtype.kind not in "fiu" or not _m4_basin_breach_np.isfinite(target).all():
        raise ValueError("target_bed_m must contain a finite bed for each path cell")
    target = target.astype(_m4_basin_breach_np.float64)
    volume = _path_values(routed_volume_m3, shape, path, "routed_volume_m3")
    duration = _path_values(wet_duration_s, shape, path, "wet_duration_s")
    _m4_basin_breach_validate_cold_material(materials)
    if tuple(materials["metadata"]["shape"]) != shape or materials["metadata"]["spacing_m"] != spacing:
        raise ValueError("material grid mismatch")
    material = materials["arrays"]
    original = height.ravel()[path]
    thickness = material["erodible_thickness_m"].ravel()[path]
    requested = original - target
    slope = _m4_basin_breach_np.zeros(path.size)
    slope[:-1] = (target[:-1] - target[1:]) / spacing
    potential = _m4_basin_breach_np.zeros(path.size)
    reasons = []
    hydro_evidence = _hydro_evidence(hydro_face_evidence, hydro_identity, path, shape)
    anchor_evidence = _anchor_evidence(downstream_anchor_evidence, height, valid,
                                       material["protected_mask"], path, topology_identity)
    if hydro_evidence is None:
        reasons.append("missing_actual_saddle_face_flux_evidence")
    elif _m4_basin_breach_np.any(volume != hydro_evidence["outward_volume_m3"]) or _m4_basin_breach_np.any(duration != hydro_evidence["wet_duration_s"]):
        raise ValueError("path exposure must equal outward saddle-face integrated quantity")
    if anchor_evidence is None:
        reasons.append("missing_legal_downstream_anchor_evidence")
    if _m4_basin_breach_np.any(~valid.ravel()[path]):
        reasons.append("unknown_path_cell")
    if _m4_basin_breach_np.any(material["protected_mask"].ravel()[path]):
        reasons.append("protected_path_cell")
    if not _m4_basin_breach_np.isfinite(original).all():
        reasons.append("unknown_original_bed")
    if _m4_basin_breach_np.any(_m4_basin_breach_np.diff(target) >= 0):
        reasons.append("target_not_strictly_downhill")
    if _m4_basin_breach_np.any(slope[:-1] < 1e-6):
        reasons.append("target_slope_below_minimum")
    if not _m4_basin_breach_np.allclose(target, _m4_basin_breach_np.linspace(target[0], target[-1], path.size), rtol=0, atol=1e-8):
        reasons.append("target_not_anchor_linear_interpolation")
    if target[0] != original[0] or target[-1] != original[-1]:
        reasons.append("endpoint_anchor_changed")
    if _m4_basin_breach_np.any(requested < 0):
        reasons.append("target_requires_unsourced_fill")
    if not _m4_basin_breach_np.any(requested[1:-1] > 0):
        reasons.append("no_saddle_cut_requested")
    if _m4_basin_breach_np.any(requested > thickness + 1e-8):
        reasons.append("insufficient_erodible_thickness")
    with _m4_basin_breach_np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        potential[:-1] = (config["erosion_scale_m"] * material["erodibility"].ravel()[path[:-1]]
                          * material["weak_path_preference"].ravel()[path[:-1]]
                          * _m4_basin_breach_np.log1p(volume[:-1] / config["reference_volume_m3"])
                          * (-_m4_basin_breach_np.expm1(-duration[:-1] / config["reference_duration_s"]))
                          * _m4_basin_breach_np.sqrt(_m4_basin_breach_np.maximum(slope[:-1], 0)))
    if not _m4_basin_breach_np.isfinite(potential).all():
        raise ValueError("path potential exceeds numerical budget")
    needs_cut = requested > 0
    if _m4_basin_breach_np.any(needs_cut & ((volume <= 0) | (duration <= 0))):
        reasons.append("no_water_or_duration_at_cut")
    if _m4_basin_breach_np.any(needs_cut & (requested > potential + 1e-8)):
        reasons.append("insufficient_water_material_potential")
    if _m4_basin_breach_np.any(volume <= 0) or _m4_basin_breach_np.any(duration <= 0):
        reasons.append("zero_saddle_exposure")
    accepted = not reasons
    erosion = _m4_basin_breach_np.zeros(shape)
    if accepted:
        erosion.ravel()[path] = requested
    area = spacing ** 2
    source_geometry = erosion * area
    material_config = materials["metadata"]["parameters"]
    source_solid = source_geometry * (1 - material_config["source_porosity"])
    source_mass = source_solid * material_config["solid_density_kg_m3"]
    if not _m4_basin_breach_np.isfinite(source_mass).all():
        raise ValueError("path source mass exceeds numerical budget")
    stored_solid = _m4_basin_breach_np.zeros(shape)
    stored_solid.ravel()[path[-1]] = float(_m4_basin_breach_np.sum(source_solid))
    arrays = {"original_height_m": height, "height_m": height - erosion, "valid_mask": valid,
              "protected_mask": material["protected_mask"], "path_cell_ids": path,
              "path_target_bed_m": target, "path_routed_volume_m3": volume,
              "path_wet_duration_s": duration, "path_potential_depth_m": potential,
              "path_erodible_thickness_m": thickness,
              "path_required_depth_m": _m4_basin_breach_np.where(_m4_basin_breach_np.isfinite(requested), requested, 0.0), "erosion_depth_m": erosion,
              "height_delta_m": -erosion, "source_geometry_m3": source_geometry,
              "source_solid_m3": source_solid, "source_mass_kg": source_mass,
              "stored_solid_m3": stored_solid, "transported_solid_m3": _m4_basin_breach_np.zeros(shape),
              "exported_solid_m3": _m4_basin_breach_np.zeros(shape), "deposited_solid_m3": _m4_basin_breach_np.zeros(shape),
              "deposit_geometry_m3": _m4_basin_breach_np.zeros(shape)}
    ledger = {name: float(_m4_basin_breach_np.sum(arrays[name])) for name in (
        "source_geometry_m3", "source_solid_m3", "source_mass_kg", "stored_solid_m3",
        "transported_solid_m3", "exported_solid_m3", "deposited_solid_m3", "deposit_geometry_m3")}
    if not all(_m4_basin_breach_math.isfinite(value) for value in ledger.values()):
        raise ValueError("total path source exceeds numerical budget")
    ledger["solid_residual_m3"] = 0.0
    metadata = {"algorithm": ALGORITHM, "format_version": 1, "shape": list(shape), "spacing_m": spacing,
                "origin_m_xz": materials["metadata"]["origin_m_xz"], "status": "candidate" if accepted else "rejected",
                "rejection_reasons": reasons, "parameters": config, "material_parameters": material_config,
                "source_identity_sha256": source_identity, "topology_identity_sha256": topology_identity,
                "hydro_identity_sha256": hydro_identity, "material_identity_sha256": materials["identity_sha256"],
                "path_face_identity": expected_faces, "ledger": ledger, "generation_rounds": 1,
                "hydro_face_evidence": hydro_evidence, "downstream_anchor_evidence": anchor_evidence,
                "exposure_policy": "saddle_outward_face_exposure_assigned_to_path_not_dry_cell_hydraulic_flux",
                "external_evidence_verified": False,
                "anchor_receiver_tail_verified": False,
                "candidate_budget_policy": "caller must enforce <=8 independent basin candidates",
                "slope_policy": "explicit_strictly_downhill_target_path_v1",
                "sediment_policy": "all_cut_solid_in_endpoint_independent_inventory_no_bed_fill_no_export",
                "requires_topology_rebuild": accepted, "hydrology_coupled_verified": False,
                "model": "generative path feasibility heuristic; no real evolution age"}
    result = _m4_basin_breach_bundle(arrays, metadata)
    validate_saddle_breach(result)
    return result

# --- terrain_pipeline/td_basin_breach.py:286 ---
def validate_saddle_breach(bundle):
    from terrain_pipeline.geology import _material_check_identity as _m4_basin_breach_check_identity
    from terrain_pipeline.geology import _mask as _m4_basin_breach_mask
    from terrain_pipeline.geology import _parameters as _m4_basin_breach_material_parameters
    from terrain_pipeline.geology import _material_positive as _m4_basin_breach_positive
    from terrain_pipeline.geology import _material_shape as _m4_basin_breach_shape
    _m4_basin_breach_check_identity(bundle)
    arrays = bundle["arrays"]
    metadata = bundle["metadata"]
    if metadata.get("algorithm") != ALGORITHM or metadata.get("format_version") != 1:
        raise ValueError("unsupported saddle breach format")
    shape = _m4_basin_breach_shape(metadata["shape"])
    config = _parameters(metadata["parameters"])
    path = _path_ids(arrays["path_cell_ids"], shape, config["max_path_cells"])
    if metadata["path_face_identity"] != saddle_path_face_identity(arrays["original_height_m"], path, source_identity_sha256=metadata["source_identity_sha256"], topology_identity_sha256=metadata["topology_identity_sha256"]):
        raise ValueError("saved path face identity mismatch")
    for name in ("source_identity_sha256", "hydro_identity_sha256", "material_identity_sha256"):
        _sha256(metadata[name], name)
    valid = _m4_basin_breach_mask(arrays["valid_mask"], shape, "valid_mask")
    protected = _m4_basin_breach_mask(arrays["protected_mask"], shape, "protected_mask")
    spacing = _m4_basin_breach_positive(metadata["spacing_m"], "spacing_m")
    for name, values in arrays.items():
        expected_shape = path.shape if name.startswith("path_") else shape
        if values.shape != expected_shape:
            raise ValueError("saved saddle array shape mismatch")
        if name != "path_cell_ids" and values.dtype.kind != "b":
            if values.dtype != _m4_basin_breach_np.dtype("float64") or _m4_basin_breach_np.isinf(values).any():
                raise ValueError("invalid saved saddle array dtype/value")
            if name not in ("original_height_m", "height_m") and not _m4_basin_breach_np.isfinite(values).all():
                raise ValueError("nonfinite saved saddle ledger")
    erosion = arrays["erosion_depth_m"]
    if _m4_basin_breach_np.any(erosion < 0) or _m4_basin_breach_np.any(erosion[protected | ~valid] != 0):
        raise ValueError("invalid saddle erosion")
    outside = _m4_basin_breach_np.ones(_m4_basin_breach_math.prod(shape), bool)
    outside[path] = False
    if _m4_basin_breach_np.any(erosion.ravel()[outside] != 0):
        raise ValueError("saddle change outside explicit path")
    def check(actual, expected):
        if not _m4_basin_breach_np.allclose(actual, expected, rtol=1e-12, atol=1e-9, equal_nan=True):
            raise ValueError("saved saddle geometry/ledger mismatch")
    if metadata["status"] == "rejected":
        if not metadata["rejection_reasons"] or _m4_basin_breach_np.any(erosion != 0):
            raise ValueError("rejected saddle must preserve entire baseline")
    elif metadata["status"] == "candidate":
        target = arrays["path_target_bed_m"]
        original = arrays["original_height_m"].ravel()[path]
        if metadata["rejection_reasons"] or _m4_basin_breach_np.any(~valid.ravel()[path]) or _m4_basin_breach_np.any(protected.ravel()[path]) or _m4_basin_breach_np.any(_m4_basin_breach_np.diff(target) >= 0):
            raise ValueError("invalid accepted saddle path")
        if target[0] != original[0] or target[-1] != original[-1]:
            raise ValueError("saved saddle anchor changed")
        check(erosion.ravel()[path], original - target)
        if _m4_basin_breach_np.any(erosion.ravel()[path] > arrays["path_erodible_thickness_m"] + 1e-8) or _m4_basin_breach_np.any(erosion.ravel()[path] > arrays["path_potential_depth_m"] + 1e-8):
            raise ValueError("saved saddle exceeds thickness or water potential")
        if not _m4_basin_breach_np.allclose(target, _m4_basin_breach_np.linspace(target[0], target[-1], path.size), rtol=0, atol=1e-8) or _m4_basin_breach_np.any((target[:-1] - target[1:]) / spacing < 1e-6):
            raise ValueError("saved target is not legal straight downhill profile")
        if metadata["hydro_face_evidence"] is None or metadata["downstream_anchor_evidence"] is None:
            raise ValueError("saved candidate lacks water/anchor evidence")
        hydro = dict(metadata["hydro_face_evidence"])
        hydro.pop("wet_duration_s")
        hydro = _hydro_evidence(hydro, metadata["hydro_identity_sha256"], path, shape)
        _anchor_evidence(metadata["downstream_anchor_evidence"], arrays["original_height_m"], valid, protected, path, metadata["topology_identity_sha256"])
        check(arrays["path_routed_volume_m3"], hydro["outward_volume_m3"])
        check(arrays["path_wet_duration_s"], hydro["wet_duration_s"])
    else:
        raise ValueError("invalid saddle status")
    check(arrays["height_delta_m"], -erosion)
    check(arrays["height_m"], arrays["original_height_m"] - erosion)
    check(arrays["source_geometry_m3"], spacing ** 2 * erosion)
    material = _m4_basin_breach_material_parameters(metadata["material_parameters"])
    check(arrays["source_solid_m3"], arrays["source_geometry_m3"] * (1 - material["source_porosity"]))
    check(arrays["source_mass_kg"], arrays["source_solid_m3"] * material["solid_density_kg_m3"])
    expected_stored = _m4_basin_breach_np.zeros(shape)
    expected_stored.ravel()[path[-1]] = float(_m4_basin_breach_np.sum(arrays["source_solid_m3"]))
    check(arrays["stored_solid_m3"], expected_stored)
    for name in ("transported_solid_m3", "exported_solid_m3", "deposited_solid_m3", "deposit_geometry_m3"):
        if _m4_basin_breach_np.any(arrays[name] != 0):
            raise ValueError("unapproved sediment transfer in saddle phase")
    for name, total in metadata["ledger"].items():
        check(total, 0.0 if name == "solid_residual_m3" else float(_m4_basin_breach_np.sum(arrays[name])))
    return True

# --- terrain_pipeline/td_basin_breach.py:363 ---
def save_saddle_breach(bundle, path):
    from terrain_pipeline.geology import _save_bundle as _m4_basin_breach_save_bundle
    validate_saddle_breach(bundle)
    return _m4_basin_breach_save_bundle(bundle, path)

# --- terrain_pipeline/td_basin_breach.py:368 ---
def load_saddle_breach(path, *, expected_sha256=None, expected_identity=None):
    from terrain_pipeline.geology import _load_bundle as _m4_basin_breach_load_bundle
    bundle = _m4_basin_breach_load_bundle(path, expected_sha256=expected_sha256, expected_identity=expected_identity)
    validate_saddle_breach(bundle)
    return bundle

# --- terrain_pipeline/td_basin_candidates.py:21 ---
def validate_candidate_inputs(source, hierarchy, materials, ordinary, strong):
    from terrain_pipeline.basin_storage import validate_basin_storage as _m4_basin_candidates_validate_basin_storage
    from terrain_pipeline.basin_storage import validate_td_source as _m4_basin_candidates_validate_td_source
    from terrain_pipeline.geology import _validate_cold_material as _m4_basin_candidates_validate_cold_material
    _m4_basin_candidates_validate_td_source(source)
    validate_basin_hierarchy(hierarchy)
    _m4_basin_candidates_validate_cold_material(materials)
    for hydro in (ordinary, strong):
        _m4_basin_candidates_validate_basin_storage(hydro)
        if hydro["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]:
            raise ValueError("hydrology/topology identity chain mismatch")
        if not _m4_basin_candidates_np.array_equal(hydro["arrays"]["height_m"], source["arrays"]["height_m"]):
            raise ValueError("hydrology original bed mismatch")
        if not _m4_basin_candidates_np.array_equal(hydro["arrays"]["receiver"], hierarchy["arrays"]["receiver"]):
            raise ValueError("hydrology receiver mismatch")
    if hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"]:
        raise ValueError("source/topology chain mismatch")
    if (materials["metadata"]["shape"] != list(source["arrays"]["height_m"].shape) or
            materials["metadata"]["origin_m_xz"] != source["metadata"]["origin_m_xz"] or
            materials["metadata"]["spacing_m"] != source["metadata"]["spacing_m"] or
            not _m4_basin_candidates_np.array_equal(materials["arrays"]["protected_mask"], source["arrays"]["protected_mask"])):
        raise ValueError("material source grid/protection mismatch")
    for hydro in (ordinary, strong):
        for key in ("valid_mask", "face_cells", "boundary_cells"):
            if not _m4_basin_candidates_np.array_equal(hydro["arrays"][key], hierarchy["arrays"][key]):
                raise ValueError("hydro coverage/face/boundary mismatch")
    if ordinary["metadata"]["parameters"] != strong["metadata"]["parameters"]:
        raise ValueError("ordinary/strong numerical parameter mismatch")
    return True

# --- terrain_pipeline/td_basin_candidates.py:49 ---
def _tail(receiver, start, limit=64):
    cells = [int(start)]
    while receiver[cells[-1]] >= 0:
        if len(cells) >= limit:
            return None
        next_cell = int(receiver[cells[-1]])
        if next_cell in cells:
            return None
        cells.append(next_cell)
    return cells

# --- terrain_pipeline/td_basin_candidates.py:61 ---
def find_saddle_paths(source, hierarchy, ordinary):
    topology, hydro = hierarchy["arrays"], ordinary["arrays"]
    bed = topology["height_m"].ravel()
    contribution = topology["contribution_owner"].ravel()
    parent = topology["node_parent"]
    child_count = _m4_basin_candidates_np.bincount(parent[parent >= 0], minlength=len(parent))
    receiver = topology["receiver"]
    paths, rejected = [], []
    for face_index, face in enumerate(topology["face_cells"]):
        for outward, volume_key, duration_key in ((face, "face_forward_m3", "active_forward_s"),
                                                 (face[::-1], "face_reverse_m3", "active_reverse_s")):
            first, second = map(int, outward)
            leaf = int(contribution[first])
            if (leaf < 0 or child_count[leaf] != 0 or parent[leaf] < 0 or topology["node_open_boundary"][leaf] or
                    topology["node_unknown_contact"][leaf] or contribution[second] == leaf or
                    topology["face_merge_node"][face_index] != parent[leaf] or
                    abs(topology["face_level_m"][face_index] - topology["node_upper_m"][leaf]) > 1e-8 or
                    hydro[volume_key][face_index] <= 0 or hydro[duration_key][face_index] <= 0):
                continue
            prefix = _tail(receiver, first)
            suffix = _tail(receiver, second)
            reason = None
            if prefix is None or suffix is None:
                reason = "receiver_tail_exceeds64"
            else:
                prefix = prefix[::-1]
                lower = [index for index, cell in enumerate(suffix) if bed[cell] < bed[prefix[0]]]
                if not lower:
                    reason = "no_lower_downstream_anchor"
                else:
                    anchor_index = lower[0]
                    path = prefix + suffix[:anchor_index + 1]
                    tail = suffix[anchor_index:]
                    target = _m4_basin_candidates_np.linspace(bed[path[0]], bed[path[-1]], len(path))
                    if len(path) > 64 or len(set(path)) != len(path):
                        reason = "path_exceeds64_or_repeated"
                    elif _m4_basin_candidates_np.any(target > bed[path] + 1e-8):
                        reason = "straight_target_requires_fill"
                    elif bed[tail[-1]] >= bed[path[0]] or contribution[tail[-1]] == leaf:
                        reason = "tail_not_different_lower_leaf"
                    elif _m4_basin_candidates_np.any(source["arrays"]["protected_mask"].ravel()[path + tail]):
                        reason = "protected_path_or_tail"
                    else:
                        duration = float(hydro[duration_key][face_index])
                        substep = ordinary["metadata"]["substep_s"]
                        if ordinary["metadata"]["algorithm"] == "D4-analytic-face-Strang-splitting-v2":
                            substep /= 2
                        steps = int(round(duration / substep))
                        if abs(steps * substep - duration) > 1e-8:
                            raise ValueError("face activity not integral substeps")
                        paths.append({"leaf": leaf, "face_index": face_index, "face_cell_ids": [first, second],
                            "path": path, "target": target.tolist(), "tail": tail,
                            "destination_leaf": int(contribution[tail[-1]]),
                            "volume_m3": float(hydro[volume_key][face_index]), "duration_s": duration,
                            "positive_outflow_steps": steps, "substep_s": substep,
                            "sill_m": float(topology["face_level_m"][face_index]),
                            "required_cut_m3": float(_m4_basin_candidates_np.maximum(0, bed[path] - target).sum() * source["metadata"]["spacing_m"] ** 2)})
            if reason:
                rejected.append({"leaf": leaf, "face_index": face_index, "face_cell_ids": [first, second], "reason": reason})
    return paths, rejected

# --- terrain_pipeline/td_basin_candidates.py:123 ---
def generate_candidate_geometries(source, hierarchy, materials, ordinary, strong):
    from terrain_pipeline.td_basin_morphology import generate_morphology as _m4_basin_candidates_generate_morphology
    validate_candidate_inputs(source, hierarchy, materials, ordinary, strong)
    topology = hierarchy["arrays"]
    volume, duration = ordinary["arrays"]["routed_volume_m3"], ordinary["arrays"]["wet_duration_s"]
    opened = _m4_basin_candidates_np.flatnonzero(source["arrays"]["open_boundary_mask"].ravel() & (topology["receiver"] < 0)).tolist()
    bundles = {}
    for candidate_id, kind in (("valley_incision", "breach"), ("source_deposition", "deposition")):
        bundles[candidate_id] = _m4_basin_candidates_generate_morphology(source["arrays"]["height_m"], source["arrays"]["valid_mask"],
            topology["receiver"], volume, duration, spacing_m=source["metadata"]["spacing_m"], materials=materials,
            parameters={"engineering_open_boundary_cell_ids": opened}, candidate_kind=kind)
    paths, rejected = find_saddle_paths(source, hierarchy, ordinary)
    for path in paths:
        material_cost = materials["arrays"]["erodibility"].ravel()[path["path"]]
        path["material_cost"] = float(_m4_basin_candidates_np.maximum(0, source["arrays"]["height_m"].ravel()[path["path"]] - path["target"]).dot(1 / material_cost))
    paths.sort(key=lambda path: (path["sill_m"], path["required_cut_m3"], path["material_cost"], path["face_index"], path["face_cell_ids"]))
    selected = []
    seen_leaves = set()
    for path in paths:
        if path["leaf"] not in seen_leaves and len(selected) < 8:
            selected.append(path)
            seen_leaves.add(path["leaf"])
    for index, path in enumerate(selected):
        path_identity = saddle_path_face_identity(source["arrays"]["height_m"], path["path"],
            source_identity_sha256=source["identity_sha256"], topology_identity_sha256=hierarchy["identity_sha256"])
        evidence = {"hydro_identity_sha256": ordinary["identity_sha256"], "face_cell_ids": path["face_cell_ids"],
            "outward_volume_m3": path["volume_m3"], "positive_outflow_steps": path["positive_outflow_steps"], "dt_s": path["substep_s"]}
        anchor = {"topology_identity_sha256": hierarchy["identity_sha256"], "source_basin_id": path["leaf"],
            "destination_basin_id": path["destination_leaf"], "tail_cell_ids": path["tail"],
            "engineering_open_boundary": bool(source["arrays"]["open_boundary_mask"].ravel()[path["tail"][-1]])}
        bundles["saddle_breach_" + str(index)] = generate_saddle_breach(source["arrays"]["height_m"], source["arrays"]["valid_mask"],
            spacing_m=source["metadata"]["spacing_m"], materials=materials, path_cell_ids=path["path"], target_bed_m=path["target"],
            path_face_identity=path_identity, source_identity_sha256=source["identity_sha256"], topology_identity_sha256=hierarchy["identity_sha256"],
            hydro_identity_sha256=ordinary["identity_sha256"], routed_volume_m3=_m4_basin_candidates_np.full(len(path["path"]), path["volume_m3"]),
            wet_duration_s=_m4_basin_candidates_np.full(len(path["path"]), path["duration_s"]), hydro_face_evidence=evidence, downstream_anchor_evidence=anchor)
    return bundles, {"eligible_paths": len(paths), "selected_paths": selected, "path_rejections": rejected,
        "external_face_receiver_evidence_checked": True, "all_saddle_parameters_default": True}

# --- terrain_pipeline/td_basin_candidates.py:161 ---
def select_candidate(records, *, numerical_sensitivity_passed):
    eligible = []
    for record in records:
        if record["candidate_id"] == "baseline":
            continue
        if numerical_sensitivity_passed and record.get("gates_passed", False) and record.get("improved", False):
            eligible.append(record)
    if not eligible:
        return "baseline"
    return min(eligible, key=lambda record: (record["disturbance_m3"], record["max_abs_delta_m"], record["candidate_id"]))["candidate_id"]

# --- terrain_pipeline/td_basin_candidates.py:173 ---
def run_candidate_coupling(source, hierarchy, materials, ordinary, strong, output, *, numerical_sensitivity_passed=False,
                           refine_candidates=False):
    from terrain_pipeline.basin_storage import make_td_source as _m4_basin_candidates_make_td_source
    from terrain_pipeline.basin_storage import save_basin_storage as _m4_basin_candidates_save_basin_storage
    from terrain_pipeline.basin_storage import save_td_source as _m4_basin_candidates_save_td_source
    from terrain_pipeline.basin_storage import simulate_threshold_storage as _m4_basin_candidates_simulate_basin_storage
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_candidates_file_sha256
    from terrain_pipeline.common_infra import publish_bytes as _m4_basin_candidates_publish_bytes
    from terrain_pipeline.runoff import RunoffParameters as _m4_basin_candidates_RunoffParameters
    from terrain_pipeline.td_basin_morphology import save_morphology as _m4_basin_candidates_save_morphology
    output = _m4_basin_candidates_Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    bundles, path_report = generate_candidate_geometries(source, hierarchy, materials, ordinary, strong)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = _m4_basin_candidates_Path(_m4_basin_candidates_tempfile.mkdtemp(prefix=".candidate-", dir=output.parent))
    records = [{"candidate_id": "baseline", "gates_passed": True, "selected": False,
        "source_identity_sha256": source["identity_sha256"], "hierarchy_identity_sha256": hierarchy["identity_sha256"],
        "ordinary_identity_sha256": ordinary["identity_sha256"], "strong_identity_sha256": strong["identity_sha256"],
        "hydraulic_ready": False, "publishable": False, "natural_outlet_verified": False}]

    def artifact(path, bundle):
        return {"path": str(output / path.relative_to(temporary)), "expected_sha256": _m4_basin_candidates_file_sha256(path),
                "expected_identity": bundle["identity_sha256"]}

    try:
        for candidate_id, morphology in bundles.items():
            print("candidate " + candidate_id, flush=True)
            directory = temporary / candidate_id
            directory.mkdir()
            morphology_path = directory / "morphology.npz"
            saddle = candidate_id.startswith("saddle_breach")
            if saddle:
                save_saddle_breach(morphology, morphology_path)
            else:
                _m4_basin_candidates_save_morphology(morphology, morphology_path)
            delta = morphology["arrays"]["height_m"] - source["arrays"]["height_m"]
            ledger = morphology["metadata"]["ledger"]
            record = {"candidate_id": candidate_id, "morphology": artifact(morphology_path, morphology),
                "changed_cells": int((delta != 0).sum()), "max_abs_delta_m": float(abs(delta).max()),
                "disturbance_m3": ledger["source_geometry_m3"] + ledger["deposit_geometry_m3"], "material_ledger": ledger,
                "numerical_sensitivity_passed": numerical_sensitivity_passed, "gates_passed": False, "improved": False,
                "publishable": False, "hydraulic_ready": False, "natural_outlet_verified": False,
                "candidate_sensitivity_verified": False,
                "rejection_reasons": ["candidate_specific_transient_sensitivity_not_verified"] if numerical_sensitivity_passed else ["baseline_strong_transient_not_converged"],
                "external_evidence_verified": saddle}
            if saddle and morphology["metadata"]["status"] == "rejected":
                record["rejection_reasons"].extend(morphology["metadata"]["rejection_reasons"])
            if not record["changed_cells"]:
                record["rejection_reasons"].append("unchanged_geometry")
                records.append(record)
                continue
            candidate_source = _m4_basin_candidates_make_td_source(morphology["arrays"]["height_m"], spacing_m=source["metadata"]["spacing_m"],
                origin_m_xz=source["metadata"]["origin_m_xz"], valid_mask=source["arrays"]["valid_mask"],
                protected_mask=source["arrays"]["protected_mask"], open_boundary_mask=source["arrays"]["open_boundary_mask"],
                source_sha256=source["metadata"]["source_sha256"])
            candidate_topology = build_basin_hierarchy(candidate_source)
            _m4_basin_candidates_save_td_source(directory / "source.npz", candidate_source)
            save_basin_hierarchy(directory / "hierarchy.npz", candidate_topology)
            record["source"] = artifact(directory / "source.npz", candidate_source)
            record["hierarchy"] = artifact(directory / "hierarchy.npz", candidate_topology)
            record["rebuilt_nodes"] = len(candidate_topology["arrays"]["node_parent"])
            for scenario, baseline in (("ordinary", ordinary), ("strong", strong)):
                solver = _m4_basin_candidates_simulate_basin_storage
                if baseline["metadata"]["algorithm"] == "D4-analytic-face-Strang-splitting-v2":
                    from terrain_pipeline.basin_storage import storageimplicit_simulate as solver
                if refine_candidates:
                    from terrain_pipeline.basin_storage import storagerefined_simulate as solver
                parameters = _m4_basin_candidates_RunoffParameters(**baseline["metadata"]["runoff_parameters"])
                rain = baseline["arrays"]["rain_mm_h"].reshape((-1,) + source["arrays"]["height_m"].shape)
                initial = baseline["arrays"]["depth_m"][0].reshape(source["arrays"]["height_m"].shape)
                water = solver(candidate_topology, rain, dt_s=baseline["metadata"]["dt_s"],
                    initial_depth_m=initial, runoff_parameters=parameters, parameters=baseline["metadata"]["parameters"])
                path = directory / (scenario + ".npz")
                _m4_basin_candidates_save_basin_storage(path, water)
                record[scenario] = artifact(path, water)
                area = source["metadata"]["spacing_m"] ** 2
                values, old = water["arrays"], baseline["arrays"]
                differences = {key: float((values[key].sum() - old[key].sum())) for key in (
                    "soil_et_m3", "surface_et_m3", "boundary_outflow_m3")}
                for key in ("soil_mm", "fast_mm", "slow_mm"):
                    differences["final_" + key + "_m3"] = float((values[key][-1].sum() - old[key][-1].sum()) * area / 1000)
                differences["final_surface_m3"] = float((values["depth_m"][-1].sum() - old["depth_m"][-1].sum()) * area)
                differences["max_cell_residual_m3"] = float(abs(values["balance_residual_m3"]).max())
                record[scenario + "_differences"] = differences
                coarse_depth = values["depth_m"].copy() if refine_candidates else None
                coarse_volume = values["routed_volume_m3"].copy() if refine_candidates else None
                del water, values
                if refine_candidates:
                    refined_parameters = dict(baseline["metadata"]["parameters"])
                    refined_parameters["substep_s"] /= 2
                    refined_parameters["max_work_face_steps"] = 6_000_000_000
                    refined = solver(candidate_topology, rain, dt_s=baseline["metadata"]["dt_s"],
                        initial_depth_m=initial, runoff_parameters=parameters, parameters=refined_parameters)
                    refined_path = directory / (scenario + "-refined.npz")
                    _m4_basin_candidates_save_basin_storage(refined_path, refined)
                    record[scenario + "_refined"] = artifact(refined_path, refined)
                    fine_values = refined["arrays"]
                    head_error = float(abs(coarse_depth - fine_values["depth_m"]).max())
                    volume_error = float(abs(coarse_volume - fine_values["routed_volume_m3"]).sum() / max(1e-12, fine_values["routed_volume_m3"].sum()))
                    record[scenario + "_sensitivity"] = {"scope": "entire candidate domain", "max_depth_difference_m": head_error,
                        "receiver_volume_relative_l1": volume_error, "gate_passed": head_error <= .001 and volume_error <= .01}
                    del refined, fine_values, coarse_depth, coarse_volume
            ordinary_difference = record["ordinary_differences"]
            evaporation_increase = ordinary_difference["soil_et_m3"] + ordinary_difference["surface_et_m3"]
            internal_storage_increase = sum(ordinary_difference["final_" + key + "_m3"] for key in ("soil_mm", "fast_mm", "slow_mm"))
            record["improved"] = (ordinary_difference["final_surface_m3"] < -1e-6 and
                ordinary_difference["boundary_outflow_m3"] > 1e-6 and evaporation_increase <= 1e-6 and internal_storage_increase <= 1e-6)
            record["candidate_sensitivity_verified"] = refine_candidates and all(record[scenario + "_sensitivity"]["gate_passed"] for scenario in ("ordinary", "strong"))
            record["gates_passed"] = numerical_sensitivity_passed and record["candidate_sensitivity_verified"]
            if record["candidate_sensitivity_verified"]:
                record["rejection_reasons"] = [reason for reason in record["rejection_reasons"] if reason != "candidate_specific_transient_sensitivity_not_verified"]
            elif refine_candidates:
                record["rejection_reasons"].append("candidate_full_domain_transient_not_converged")
            if not record["improved"]:
                record["rejection_reasons"].append("no_verified_non_evaporation_connectivity_improvement")
            records.append(record)
        selected = select_candidate(records, numerical_sensitivity_passed=numerical_sensitivity_passed)
        for record in records:
            record["selected"] = record["candidate_id"] == selected
        payload = {"schema": "td-basin-candidate-records-v1", "selected_candidate_id": selected, "candidates": records,
            "saddle_search": path_report, "numerical_sensitivity_passed": numerical_sensitivity_passed,
            "mode": "diagnostic coupling only when numerical sensitivity fails; never automatic terrain adoption",
            "publishable": False, "hydraulic_ready": False, "natural_outlet_verified": False}
        _m4_basin_candidates_publish_bytes(temporary / "records.json", _m4_basin_candidates_json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
        _m4_basin_candidates_os.rename(temporary, output)
        return payload
    except BaseException:
        _m4_basin_candidates_shutil.rmtree(temporary)
        raise

# --- terrain_pipeline/td_stable_spill_paths.py:14 ---
STABLE_SPILL_SCHEMA = "td-stable-spill-paths-v1"

# --- terrain_pipeline/td_stable_spill_paths.py:15 ---
MAX_PATH_CELLS = 64

# --- terrain_pipeline/td_stable_spill_paths.py:16 ---
MAX_CANDIDATES = 8

# --- terrain_pipeline/td_stable_spill_paths.py:17 ---
CASE_NAMES = ("normal-24h", "strong-6h")

# --- terrain_pipeline/td_stable_spill_paths.py:20 ---
def _digest(record):
    return _m4_stable_spill_paths_hashlib.sha256(_m4_stable_spill_paths_json.dumps(record, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()

# --- terrain_pipeline/td_stable_spill_paths.py:25 ---
def _d4(first, second, columns):
    return abs(first // columns - second // columns) + abs(first % columns - second % columns) == 1

# --- terrain_pipeline/td_stable_spill_paths.py:29 ---
def trace_receiver_side(hierarchy, start_cell, basin_id, *, max_path_cells=MAX_PATH_CELLS):
    if type(max_path_cells) is not int or not 3 <= max_path_cells <= MAX_PATH_CELLS:
        raise ValueError("receiver path budget must be 3..64 cells")
    arrays = hierarchy["arrays"]
    height = arrays["height_m"].ravel()
    receiver = arrays["receiver"].ravel()
    owner = arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    columns = arrays["height_m"].shape[1]
    path, reasons, seen = [], [], set()
    cell = int(start_cell)
    complete = False
    while True:
        if not 0 <= cell < height.size:
            reasons.append("receiver_outside_source_domain")
            break
        if cell in seen:
            reasons.append("receiver_cycle")
            break
        if len(path) >= max_path_cells:
            reasons.append("receiver_path_length_exceeds_budget")
            break
        seen.add(cell)
        path.append(cell)
        if not valid[cell] or not _m4_stable_spill_paths_np.isfinite(height[cell]):
            reasons.append("unknown_receiver_path_cell")
            break
        if protected[cell]:
            reasons.append("protected_receiver_path_cell")
        if owner[cell] != basin_id:
            reasons.append("receiver_leaves_face_basin")
            break
        downstream = int(receiver[cell])
        if downstream == -1:
            complete = True
            break
        if not 0 <= downstream < height.size:
            reasons.append("receiver_outside_source_domain")
            break
        if not _d4(cell, downstream, columns):
            reasons.append("receiver_not_d4_adjacent")
            break
        if height[downstream] > height[cell]:
            reasons.append("receiver_climbs_original_bed")
            break
        cell = downstream
    return {"basin_id": int(basin_id), "start_cell_id": int(start_cell),
            "cell_ids": path, "terminal_cell_id": path[-1] if complete else None,
            "complete": complete, "length_m": max(0, len(path) - 1) * hierarchy["metadata"]["spacing_m"],
            "rejection_reasons": sorted(set(reasons))}

# --- terrain_pipeline/td_stable_spill_paths.py:82 ---
def _face_geometry(face, topology_face, hierarchy):
    from terrain_pipeline.basin_storage import _face_id as _m4_stable_spill_paths_face_id
    arrays = hierarchy["arrays"]
    index = face["hierarchy_face_index"]
    cells = face["cell_ids"]
    if (cells != topology_face["cell_ids"] or index != topology_face["face_index"] or
            cells != arrays["face_cells"][index].tolist() or face["face_id"] != _m4_stable_spill_paths_face_id(hierarchy, index)):
        raise ValueError("reception source face identity/cell mismatch")
    owners = arrays["contribution_owner"].ravel()[cells].tolist()
    if owners != face["cell_owner_leaf_ids"] or sorted(owners) != face["leaf_ids"]:
        raise ValueError("reception cell/leaf orientation mismatch")
    height = arrays["height_m"].ravel()
    columns = arrays["height_m"].shape[1]
    spacing = hierarchy["metadata"]["spacing_m"]
    origin = hierarchy["metadata"]["origin_m_xz"]
    endpoints = [[origin[0] + (cell % columns) * spacing, float(height[cell]),
                  origin[1] + (cell // columns) * spacing] for cell in cells]
    if (not _d4(*cells, columns) or endpoints != face["endpoints_xyz_m"] or
            float(max(height[cells])) != face["sill_m"]):
        raise ValueError("reception face XYZ/sill/D4 differs from source bed")

# --- terrain_pipeline/td_stable_spill_paths.py:103 ---
def build_stable_spill_paths(hierarchy, topology, cases, *, max_path_cells=MAX_PATH_CELLS):
    """Reverse only the source-side static chain, then cross the actual saddle face."""
    from terrain_pipeline.basin_storage import _topology_identity as _m4_stable_spill_paths_topology_identity
    validate_basin_hierarchy(hierarchy)
    if type(max_path_cells) is not int or not 3 <= max_path_cells <= MAX_PATH_CELLS:
        raise ValueError("path work budget must be 3..64 cells")
    if (topology["identity_sha256"] != _m4_stable_spill_paths_topology_identity(topology) or
            topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"]):
        raise ValueError("topology/hierarchy identity mismatch")
    lookup = {case["name"]: case for case in cases}
    if len(lookup) != len(cases) or set(lookup) != set(CASE_NAMES):
        raise ValueError("ordinary and strong audited cases required exactly once")
    face_lookup = {}
    for name in CASE_NAMES:
        case = lookup[name]
        reception = case["reception"]
        validate_basin_reception(reception, expected_identity=reception["identity_sha256"])
        restored = build_basin_reception(topology, case["selected_event"], case["reference_event"], hierarchy)
        if restored["identity_sha256"] != reception["identity_sha256"]:
            raise ValueError("reception differs from actual saved event/refinement")
        face_lookup[name] = {face["face_id"]: face for face in reception["faces"]}
        if len(face_lookup[name]) != len(topology["faces"]):
            raise ValueError("reception face coverage/duplicate mismatch")
    records = []
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    height = arrays["height_m"].ravel()
    for topology_face in topology["faces"]:
        face_id = topology_face["face_id"]
        evidence = {name: face_lookup[name][face_id] for name in CASE_NAMES}
        for face in evidence.values():
            _face_geometry(face, topology_face, hierarchy)
        ordinary, strong = (evidence[name] for name in CASE_NAMES)
        reasons = []
        for name, face in evidence.items():
            if not face["stable_relationship"]:
                reasons.append(name + ":not_stable_reception")
        directions = {(face["source_leaf_id"], face["receiver_leaf_id"])
                      for face in evidence.values() if face["stable_relationship"]}
        if len(directions) > 1:
            reasons.append("ordinary_strong_direction_conflict")
        record = {"face_id": face_id, "hierarchy_face_index": ordinary["hierarchy_face_index"],
                  "face_cell_ids": ordinary["cell_ids"], "face_leaf_ids": ordinary["leaf_ids"],
                  "source_identity_sha256": metadata["source_identity_sha256"],
                  "hierarchy_identity_sha256": hierarchy["identity_sha256"],
                  "topology_identity_sha256": topology["identity_sha256"],
                  "sill_m": ordinary["sill_m"], "event_evidence": evidence,
                  "side_paths": [], "path_cell_ids": [], "bounded_candidate_requests": []}
        if directions:
            source_basin, destination_basin = next(iter(sorted(directions)))
            face_cells = ordinary["cell_ids"]
            owners = ordinary["cell_owner_leaf_ids"]
            source_cell = face_cells[owners.index(source_basin)]
            destination_cell = face_cells[owners.index(destination_basin)]
            source_side = trace_receiver_side(hierarchy, source_cell, source_basin, max_path_cells=max_path_cells)
            destination_side = trace_receiver_side(hierarchy, destination_cell, destination_basin, max_path_cells=max_path_cells)
            record.update(source_basin_id=source_basin, destination_basin_id=destination_basin,
                          directed_face_cell_ids=[source_cell, destination_cell],
                          side_paths=[source_side, destination_side])
            for side_name, side in [("source", source_side), ("destination", destination_side)]:
                reasons.extend(side_name + ":" + reason for reason in side["rejection_reasons"])
            path = list(reversed(source_side["cell_ids"])) + destination_side["cell_ids"]
            record["path_cell_ids"] = path
            record["path_length_m"] = (len(path) - 1) * metadata["spacing_m"]
            if not source_side["complete"] or not destination_side["complete"]:
                reasons.append("incomplete_receiver_chain")
            if not 3 <= len(path) <= max_path_cells:
                reasons.append("saddle_path_length_outside_budget")
            if len(set(path)) != len(path):
                reasons.append("saddle_path_repeats_cell")
            if path and not height[path[-1]] < height[path[0]]:
                reasons.append("downstream_anchor_not_lower_than_source_anchor")
            if source_basin == destination_basin:
                reasons.append("downstream_anchor_returns_to_source_basin")
            if not reasons:
                target = _m4_stable_spill_paths_np.linspace(height[path[0]], height[path[-1]], len(path))
                if _m4_stable_spill_paths_np.any(target > height[path]):
                    reasons.append("target_requires_unsourced_fill")
                if _m4_stable_spill_paths_np.any((target[:-1] - target[1:]) / metadata["spacing_m"] < 1e-6):
                    reasons.append("target_slope_below_minimum")
                if not _m4_stable_spill_paths_np.any(height[path[1:-1]] > target[1:-1]):
                    reasons.append("no_saddle_cut_requested")
                record["target_bed_m"] = target.tolist()
            if not reasons:
                path_identity = saddle_path_face_identity(arrays["height_m"], path,
                    source_identity_sha256=metadata["source_identity_sha256"],
                    topology_identity_sha256=topology["identity_sha256"])
                record["path_face_identity"] = path_identity
                for name in CASE_NAMES:
                    event = lookup[name]["selected_event"]
                    face = evidence[name]
                    field = "face_forward_m3" if source_basin == face["leaf_ids"][0] else "face_reverse_m3"
                    outward = event["arrays"][field][:, face["face_index"]]
                    volume = float(outward.sum())
                    steps = int(_m4_stable_spill_paths_np.count_nonzero(outward > 0))
                    duration = steps * event["metadata"]["timestep_s"]
                    hydro = {"hydro_identity_sha256": event["identity_sha256"],
                             "face_cell_ids": [source_cell, destination_cell],
                             "outward_volume_m3": volume, "positive_outflow_steps": steps,
                             "dt_s": event["metadata"]["timestep_s"]}
                    anchor = {"topology_identity_sha256": topology["identity_sha256"],
                              "source_basin_id": source_basin, "destination_basin_id": destination_basin,
                              "tail_cell_ids": [path[-1]], "engineering_open_boundary": False}
                    request = {"case": name, "face_id": face_id, "path_cell_ids": path,
                               "target_bed_m": record["target_bed_m"], "path_face_identity": path_identity,
                               "source_identity_sha256": metadata["source_identity_sha256"],
                               "topology_identity_sha256": topology["identity_sha256"],
                               "hydro_identity_sha256": event["identity_sha256"],
                               "routed_volume_m3": volume, "wet_duration_s": duration,
                               "hydro_face_evidence": hydro, "downstream_anchor_evidence": anchor,
                               "exposure_policy": "actual outward saddle-face volume assigned to path; not per-cell hydraulic flux"}
                    request["identity_sha256"] = _digest(request)
                    record["bounded_candidate_requests"].append(request)
        record["rejection_reasons"] = sorted(set(reasons))
        record["status"] = "rejected" if reasons else "bounded_candidate_request"
        record["identity_sha256"] = _digest(record)
        records.append(record)
    result = {"schema": STABLE_SPILL_SCHEMA, "algorithm": "actual-d4-face-two-static-receiver-chains-v1",
              "source_identity_sha256": metadata["source_identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "topology_identity_sha256": topology["identity_sha256"],
              "event_identity_sha256": {name: lookup[name]["selected_event"]["identity_sha256"] for name in CASE_NAMES},
              "reception_identity_sha256": {name: lookup[name]["reception"]["identity_sha256"] for name in CASE_NAMES},
              "max_path_cells": max_path_cells, "max_independent_candidates": MAX_CANDIDATES,
              "paths": records, "baseline": {"unchanged": True, "source_identity_sha256": metadata["source_identity_sha256"]},
              "semantics": "static receiver geometry plus two audited event-dependent reception records; no permanent trunk or solved channel",
              "solver_advanced": False, "geometry_generated": False,
              "hydraulic_ready": False, "publishable": False, "natural_outlet_verified": False,
              "continuous_fine_corridor_ready": False}
    result["identity_sha256"] = _digest(result)
    return result

# --- terrain_pipeline/td_stable_spill_paths.py:234 ---
def generate_bounded_candidates(report, hierarchy, materials, *, max_candidates=MAX_CANDIDATES):
    """Generate independent alternatives on the unchanged baseline, never chain cuts."""
    if type(max_candidates) is not int or not 0 <= max_candidates <= MAX_CANDIDATES:
        raise ValueError("independent candidate budget must be 0..8")
    if report["identity_sha256"] != _digest({key: value for key, value in report.items() if key != "identity_sha256"}):
        raise ValueError("spill request report identity mismatch")
    validate_basin_hierarchy(hierarchy)
    if (report["schema"] != STABLE_SPILL_SCHEMA or report["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            report["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("candidate baseline hierarchy identity mismatch")
    if (tuple(materials["metadata"]["shape"]) != hierarchy["arrays"]["height_m"].shape or
            materials["metadata"]["origin_m_xz"] != hierarchy["metadata"]["origin_m_xz"] or
            materials["metadata"]["spacing_m"] != hierarchy["metadata"]["spacing_m"]):
        raise ValueError("candidate material grid differs from source")
    if not _m4_stable_spill_paths_np.array_equal(materials["arrays"]["protected_mask"], hierarchy["arrays"]["protected_mask"]):
        raise ValueError("candidate material protection differs from source")
    attempts, candidates = [], []
    calls = 0
    for path in report["paths"]:
        for request in path["bounded_candidate_requests"]:
            if (request["identity_sha256"] != _digest({key: value for key, value in request.items() if key != "identity_sha256"}) or
                    request["source_identity_sha256"] != report["source_identity_sha256"] or
                    request["topology_identity_sha256"] != report["topology_identity_sha256"] or
                    request["hydro_identity_sha256"] != report["event_identity_sha256"][request["case"]]):
                raise ValueError("candidate request evidence identity mismatch")
            attempt = {"request_identity_sha256": request["identity_sha256"], "face_id": path["face_id"], "case": request["case"]}
            if calls >= max_candidates:
                attempt.update(status="not_attempted", rejection_reasons=["independent_candidate_budget_exhausted"])
            else:
                fields = {key: request[key] for key in ("path_cell_ids", "target_bed_m", "path_face_identity",
                          "source_identity_sha256", "topology_identity_sha256", "hydro_identity_sha256",
                          "routed_volume_m3", "wet_duration_s", "hydro_face_evidence", "downstream_anchor_evidence")}
                for key in ("routed_volume_m3", "wet_duration_s"):
                    fields[key] = _m4_stable_spill_paths_np.full(len(request["path_cell_ids"]), request[key])
                try:
                    calls += 1
                    bundle = generate_saddle_breach(hierarchy["arrays"]["height_m"], hierarchy["arrays"]["valid_mask"],
                        spacing_m=hierarchy["metadata"]["spacing_m"], materials=materials, **fields,
                        parameters={"max_path_cells": report["max_path_cells"]})
                    candidate_index = len(candidates)
                    candidates.append(bundle)
                    attempt.update(status=bundle["metadata"]["status"],
                                   candidate_index=candidate_index, identity_sha256=bundle["identity_sha256"],
                                   rejection_reasons=bundle["metadata"]["rejection_reasons"])
                except ValueError as error:
                    attempt.update(status="failed", rejection_reasons=["breach_contract_rejected"], error=str(error))
            attempts.append(attempt)
    return {"attempts": attempts, "candidates": candidates, "generation_calls": calls, "baseline_unchanged": True,
            "hydraulic_ready": False, "publishable": False}

# --- terrain_pipeline/td_basin_reception.py:13 ---
RECEPTION_SCHEMA = "td-stable-basin-reception-v1"

# --- terrain_pipeline/td_basin_reception.py:14 ---
MIN_FACE_VOLUME_M3 = 1e-6

# --- terrain_pipeline/td_basin_reception.py:15 ---
RECEPTION_RELATIVE_TOLERANCE = .01

# --- terrain_pipeline/td_basin_reception.py:16 ---
LEDGER_TOLERANCE_M3 = 1e-7

# --- terrain_pipeline/td_basin_reception.py:19 ---
def _sha(value):
    return _m4_basin_reception_hashlib.sha256(_m4_basin_reception_json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()

# --- terrain_pipeline/td_basin_reception.py:24 ---
def _event_ledger(topology, event, leaf_lookup):
    arrays = event["arrays"]
    water = arrays["volume_m3"]
    steps, count = arrays["input_volume_m3"].shape
    incoming = _m4_basin_reception_np.zeros((steps, count))
    outgoing = _m4_basin_reception_np.zeros_like(incoming)
    exports = _m4_basin_reception_np.zeros_like(incoming)
    for face_index, face in enumerate(topology["faces"]):
        first, second = (leaf_lookup[int(leaf)] for leaf in face["leaf_ids"])
        incoming[:, first] += arrays["face_reverse_m3"][:, face_index]
        outgoing[:, first] += arrays["face_forward_m3"][:, face_index]
        incoming[:, second] += arrays["face_forward_m3"][:, face_index]
        outgoing[:, second] += arrays["face_reverse_m3"][:, face_index]
    for boundary_index, boundary in enumerate(topology["engineering_boundaries"]):
        exports[:, leaf_lookup[int(boundary["leaf_id"])]] += arrays["engineering_boundary_outflow_m3"][:, boundary_index]
    residual = arrays["input_volume_m3"] + incoming - outgoing - exports - _m4_basin_reception_np.diff(water, axis=0)
    if not _m4_basin_reception_np.isfinite(residual).all() or _m4_basin_reception_np.any(_m4_basin_reception_np.abs(residual) > LEDGER_TOLERANCE_M3):
        raise ValueError("independent per-interval basin inventory closure failed")
    if not _m4_basin_reception_np.allclose(arrays["face_net_m3"], arrays["face_forward_m3"] - arrays["face_reverse_m3"], rtol=0, atol=1e-9):
        raise ValueError("saved face net disagrees with directional volumes")
    if not _m4_basin_reception_np.allclose(arrays["input_volume_m3"],
                       (arrays["rain_mm_h"][:, None] * event["metadata"]["parameters"]["runoff_coefficient"] / 3_600_000.
                        + event["metadata"]["parameters"]["baseflow_mm_per_day"] / 86_400_000.)
                       * topology["arrays"]["leaf_area_m2"][None, :] * event["metadata"]["timestep_s"],
                       rtol=0, atol=LEDGER_TOLERANCE_M3):
        raise ValueError("saved rain input mismatch")
    return incoming, outgoing, exports, residual

# --- terrain_pipeline/td_basin_reception.py:53 ---
def build_basin_reception(topology, event, reference_event, hierarchy):
    """Report saved-interval exchange; no solver calls or permanent channel claim."""
    from terrain_pipeline.basin_storage import _face_id as _m4_basin_reception_face_id
    from terrain_pipeline.basin_storage import _physical_faces as _m4_basin_reception_physical_faces
    from terrain_pipeline.basin_storage import _topology_identity as _m4_basin_reception_topology_identity
    from terrain_pipeline.basin_storage import validate_overflow_event as _m4_basin_reception_validate_overflow_event
    validate_basin_hierarchy(hierarchy)
    if topology["identity_sha256"] != _m4_basin_reception_topology_identity(topology):
        raise ValueError("topology identity mismatch")
    if (topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            topology["metadata"]["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("topology/hierarchy identity mismatch")
    _m4_basin_reception_validate_overflow_event(event, topology)
    _m4_basin_reception_validate_overflow_event(reference_event, topology)
    metadata, reference = event["metadata"], reference_event["metadata"]
    for key in ("topology_identity_sha256", "hierarchy_identity_sha256", "source_identity_sha256", "parameters", "steps", "timestep_s", "duration_s"):
        if metadata[key] != reference[key]:
            raise ValueError("event/reference physics or time grid mismatch")
    if metadata["topology_identity_sha256"] != topology["identity_sha256"]:
        raise ValueError("event/topology identity mismatch")
    arrays, other = event["arrays"], reference_event["arrays"]
    if not _m4_basin_reception_np.array_equal(arrays["rain_mm_h"], other["rain_mm_h"]) or not _m4_basin_reception_np.array_equal(arrays["volume_m3"][0], other["volume_m3"][0]):
        raise ValueError("event/reference rain or initial inventory mismatch")
    leaves = [int(leaf) for leaf in topology["arrays"]["leaf_ids"]]
    lookup = {leaf: index for index, leaf in enumerate(leaves)}
    if len(lookup) != len(leaves):
        raise ValueError("duplicate topology leaf")
    ledgers = _event_ledger(topology, event, lookup)
    _event_ledger(topology, reference_event, lookup)
    height = hierarchy["arrays"]["height_m"]
    rows, columns = height.shape
    valid = hierarchy["arrays"]["valid_mask"].ravel()
    protected = hierarchy["arrays"]["protected_mask"].ravel()
    owners = hierarchy["arrays"]["contribution_owner"].ravel()
    face_cells = hierarchy["arrays"]["face_cells"]
    spacing = float(hierarchy["metadata"]["spacing_m"])
    origin = hierarchy["metadata"]["origin_m_xz"]
    if spacing <= 0 or not _m4_basin_reception_np.isfinite(spacing):
        raise ValueError("invalid hierarchy spacing")
    faces = []
    seen = set()
    expected_faces = _m4_basin_reception_physical_faces(hierarchy, topology["arrays"]["leaf_ids"], lookup)
    if ({face["face_id"] for face in expected_faces} != {face["face_id"] for face in topology["faces"]} or
            len(expected_faces) != len(topology["faces"])):
        raise ValueError("lowest-sill D4 face coverage mismatch")
    steps = metadata["steps"]
    late_start = int(_m4_basin_reception_np.floor(.8 * steps))
    for face_index, face in enumerate(topology["faces"]):
        hierarchy_index = int(face["face_index"])
        if not 0 <= hierarchy_index < len(face_cells) or hierarchy_index in seen:
            raise ValueError("face coverage or duplicate mismatch")
        seen.add(hierarchy_index)
        cells = [int(cell) for cell in face_cells[hierarchy_index]]
        if cells != face["cell_ids"] or any(not 0 <= cell < rows * columns for cell in cells):
            raise ValueError("face cell pairing mismatch")
        first_row, first_col = divmod(cells[0], columns)
        second_row, second_col = divmod(cells[1], columns)
        if (abs(first_row - second_row) + abs(first_col - second_col) != 1 or
                not valid[cells].all() or protected[cells].any()):
            raise ValueError("face D4/valid/protection mismatch")
        cell_owners = [int(owners[cell]) for cell in cells]
        if sorted(cell_owners) != face["leaf_ids"] or face["leaf_ids"][0] == face["leaf_ids"][1]:
            raise ValueError("face owner pairing mismatch")
        if face["face_id"] != _m4_basin_reception_face_id(hierarchy, hierarchy_index) or face["sill_m"] != float(max(height.ravel()[cells])):
            raise ValueError("face identity or original-bed sill mismatch")
        endpoints = [[float(origin[0] + column * spacing), float(height[row, column]),
                      float(origin[1] + row * spacing)] for row, column in ((first_row, first_col), (second_row, second_col))]
        forward = arrays["face_forward_m3"][:, face_index]
        reverse = arrays["face_reverse_m3"][:, face_index]
        net = forward - reverse
        ref_net = other["face_forward_m3"][:, face_index] - other["face_reverse_m3"][:, face_index]
        gross = forward + reverse
        significant = gross >= MIN_FACE_VOLUME_M3
        active = _m4_basin_reception_np.flatnonzero(significant)
        signs = _m4_basin_reception_np.sign(net[active])
        signs = signs[signs != 0]
        switches = int(_m4_basin_reception_np.count_nonzero(signs[1:] != signs[:-1]))
        total_net = float(net.sum())
        direction = int(_m4_basin_reception_np.sign(total_net))
        late_net = float(net[late_start:].sum())
        late_ref_net = float(ref_net[late_start:].sum())
        late_abs = float(_m4_basin_reception_np.abs(net[late_start:]).sum())
        late_consistency = max(0., direction * late_net / late_abs) if late_abs else 0.
        significant_pair = _m4_basin_reception_np.maximum(gross, other["face_forward_m3"][:, face_index] + other["face_reverse_m3"][:, face_index]) >= MIN_FACE_VOLUME_M3
        interval_error = float(_m4_basin_reception_np.abs(net[significant_pair] - ref_net[significant_pair]).sum())
        interval_scale = float(_m4_basin_reception_np.abs(ref_net[significant_pair]).sum())
        relative_error = interval_error / max(interval_scale, MIN_FACE_VOLUME_M3)
        interval_relative_error = float(_m4_basin_reception_np.max(_m4_basin_reception_np.abs(net[significant_pair] - ref_net[significant_pair]) /
                                               _m4_basin_reception_np.maximum(_m4_basin_reception_np.abs(ref_net[significant_pair]), MIN_FACE_VOLUME_M3))) if significant_pair.any() else 0.
        stable = bool(active.size and direction and switches == 0 and
                      float(gross.sum()) >= MIN_FACE_VOLUME_M3 and
                      direction * total_net >= (1 - RECEPTION_RELATIVE_TOLERANCE) * float(gross.sum()) and
                      direction * late_net >= MIN_FACE_VOLUME_M3 and
                      direction * late_ref_net >= MIN_FACE_VOLUME_M3 and
                      late_consistency >= 1 - RECEPTION_RELATIVE_TOLERANCE and
                      relative_error <= RECEPTION_RELATIVE_TOLERANCE and
                      interval_relative_error <= RECEPTION_RELATIVE_TOLERANCE and
                      _m4_basin_reception_np.all(_m4_basin_reception_np.sign(net[significant_pair]) == _m4_basin_reception_np.sign(ref_net[significant_pair])))
        faces.append({"face_id": face["face_id"], "face_index": face_index,
                      "hierarchy_face_index": hierarchy_index, "cell_ids": cells,
                      "cell_owner_leaf_ids": cell_owners, "leaf_ids": face["leaf_ids"],
                      "endpoints_xyz_m": endpoints,
                      "face_center_xyz_m": [(first + second) / 2 for first, second in zip(*endpoints)],
                      "width_m": spacing, "spacing_m": spacing,
                      "coverage": "pinned original-bed D4 face; endpoints valid and unprotected",
                      "sill_m": face["sill_m"], "first_active_interval": int(active[0]) if active.size else None,
                      "last_active_interval": int(active[-1]) if active.size else None,
                      "forward_m3": float(forward.sum()), "reverse_m3": float(reverse.sum()),
                      "net_m3": total_net, "gross_m3": float(gross.sum()),
                      "canceled_m3": float(2 * min(forward.sum(), reverse.sum())),
                      "active_interval_sign_switches": switches, "late_start_interval": late_start,
                      "late_net_m3": late_net, "late_direction_consistency": late_consistency,
                      "interval_net_relative_l1_difference": relative_error,
                      "max_interval_net_relative_difference": interval_relative_error,
                      "stable_relationship": stable,
                      "receiver_leaf_id": face["leaf_ids"][1 if direction > 0 else 0] if stable else None,
                      "source_leaf_id": face["leaf_ids"][0 if direction > 0 else 1] if stable else None})
    basins = []
    incoming, outgoing, exports, residual = ledgers
    parameters = metadata["parameters"]
    for index, leaf in enumerate(leaves):
        rain_input = arrays["rain_mm_h"] * parameters["runoff_coefficient"] / 3_600_000. * topology["arrays"]["leaf_area_m2"][index] * metadata["timestep_s"]
        baseflow_input = _m4_basin_reception_np.full(steps, parameters["baseflow_mm_per_day"] / 86_400_000. * topology["arrays"]["leaf_area_m2"][index] * metadata["timestep_s"])
        basins.append({"leaf_id": leaf, "rain_input_m3": rain_input.tolist(),
                       "baseflow_input_m3": baseflow_input.tolist(),
                       "face_in_m3": incoming[:, index].tolist(),
                       "face_out_m3": outgoing[:, index].tolist(),
                       "external_export_m3": exports[:, index].tolist(),
                       "inventory_m3": arrays["volume_m3"][:, index].tolist(),
                       "inventory_residual_m3": residual[:, index].tolist()})
    result = {"schema": RECEPTION_SCHEMA, "topology_identity_sha256": topology["identity_sha256"],
              "hierarchy_identity_sha256": hierarchy["identity_sha256"],
              "event_identity_sha256": event["identity_sha256"],
              "reference_event_identity_sha256": reference_event["identity_sha256"],
              "thresholds": {"minimum_diagnostic_face_volume_m3": MIN_FACE_VOLUME_M3,
                             "interval_net_relative_l1": RECEPTION_RELATIVE_TOLERANCE,
                             "inventory_residual_m3": LEDGER_TOLERANCE_M3},
              "faces": faces, "basins": basins, "saved_interval_count": steps,
              "basin_series_semantics": "each basin column covers saved intervals 0..steps-1; inventory_m3 covers boundaries 0..steps",
              "max_abs_inventory_residual_m3": float(_m4_basin_reception_np.max(_m4_basin_reception_np.abs(residual))),
              "relationship_semantics": "event-dependent shared-face reception; cycles allowed; no permanent river or backwater certification",
              "publishable": False, "natural_outlet_verified": False, "hydraulic_ready": False,
              "continuous_fine_corridor_ready": False}
    result["identity_sha256"] = _sha(result)
    return result

# --- terrain_pipeline/td_basin_reception.py:196 ---
def load_basin_reception(path, *, expected_sha256, expected_identity):
    from pathlib import Path
    from terrain_pipeline.common_infra import file_sha256

    path = Path(path)
    if path.stat().st_size >= 128 * 1024**2 or file_sha256(path) != expected_sha256:
        raise ValueError("reception file budget/hash mismatch")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate reception key")
            result[key] = value
        return result
    record = _m4_basin_reception_json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite reception JSON")))
    return validate_basin_reception(record, expected_identity=expected_identity)

# --- terrain_pipeline/td_basin_reception.py:215 ---
def validate_basin_reception(record, *, expected_identity):
    record = dict(record)
    digest = record.pop("identity_sha256", None)
    if record.get("schema") != RECEPTION_SCHEMA or digest != expected_identity or _sha(record) != digest:
        raise ValueError("reception identity/schema mismatch")
    for flag in ("publishable", "natural_outlet_verified", "hydraulic_ready", "continuous_fine_corridor_ready"):
        if record.get(flag) is not False:
            raise ValueError("reception cannot certify hydraulic or publishing readiness")
    thresholds = record.get("thresholds", {})
    if thresholds != {"minimum_diagnostic_face_volume_m3": MIN_FACE_VOLUME_M3,
                      "interval_net_relative_l1": RECEPTION_RELATIVE_TOLERANCE,
                      "inventory_residual_m3": LEDGER_TOLERANCE_M3}:
        raise ValueError("reception thresholds mismatch")
    steps = record.get("saved_interval_count")
    if type(steps) is not int or steps < 1 or not isinstance(record.get("faces"), list) or not isinstance(record.get("basins"), list):
        raise ValueError("reception shape mismatch")
    fields = ("rain_input_m3", "baseflow_input_m3", "face_in_m3", "face_out_m3",
              "external_export_m3", "inventory_residual_m3")
    for basin in record["basins"]:
        if any(not isinstance(basin.get(field), list) or len(basin[field]) != steps for field in fields):
            raise ValueError("reception basin series shape mismatch")
        if not isinstance(basin.get("inventory_m3"), list) or len(basin["inventory_m3"]) != steps + 1:
            raise ValueError("reception inventory series shape mismatch")
        if any(not _m4_basin_reception_np.isfinite(basin[field]).all() for field in (*fields, "inventory_m3")):
            raise ValueError("nonfinite reception basin series")
        if any(_m4_basin_reception_np.any(_m4_basin_reception_np.asarray(basin[field]) < 0.) for field in (*fields[:-1], "inventory_m3")):
            raise ValueError("negative reception inventory or directional series")
        residual = (_m4_basin_reception_np.asarray(basin["rain_input_m3"]) + _m4_basin_reception_np.asarray(basin["baseflow_input_m3"])
                    + _m4_basin_reception_np.asarray(basin["face_in_m3"]) - _m4_basin_reception_np.asarray(basin["face_out_m3"])
                    - _m4_basin_reception_np.asarray(basin["external_export_m3"]) - _m4_basin_reception_np.diff(basin["inventory_m3"]))
        if (_m4_basin_reception_np.max(_m4_basin_reception_np.abs(residual)) > LEDGER_TOLERANCE_M3 or
                not _m4_basin_reception_np.allclose(residual, basin["inventory_residual_m3"], rtol=0, atol=1e-9)):
            raise ValueError("reception reconstructed inventory closure failed")
        if _m4_basin_reception_np.max(_m4_basin_reception_np.abs(basin["inventory_residual_m3"])) > LEDGER_TOLERANCE_M3:
            raise ValueError("reception inventory residual mismatch")
    if not _m4_basin_reception_np.isfinite(record.get("max_abs_inventory_residual_m3", float("nan"))) or record["max_abs_inventory_residual_m3"] > LEDGER_TOLERANCE_M3:
        raise ValueError("reception inventory summary mismatch")
    for face in record["faces"]:
        if (not isinstance(face.get("endpoints_xyz_m"), list) or len(face["endpoints_xyz_m"]) != 2 or
                any(len(point) != 3 or not _m4_basin_reception_np.isfinite(point).all() for point in face["endpoints_xyz_m"]) or
                not isinstance(face.get("face_center_xyz_m"), list) or len(face["face_center_xyz_m"]) != 3 or
                not _m4_basin_reception_np.isfinite(face["face_center_xyz_m"]).all() or
                not all(_m4_basin_reception_np.isfinite(face.get(key, float("nan"))) for key in
                        ("width_m", "spacing_m", "sill_m", "forward_m3", "reverse_m3", "net_m3", "gross_m3",
                         "canceled_m3", "late_net_m3", "late_direction_consistency",
                         "interval_net_relative_l1_difference", "max_interval_net_relative_difference"))):
            raise ValueError("reception face shape or finite mismatch")
        forward, reverse = face["forward_m3"], face["reverse_m3"]
        if (forward < 0. or reverse < 0. or face["width_m"] <= 0. or face["spacing_m"] <= 0. or
                not _m4_basin_reception_np.isclose(face["net_m3"], forward - reverse, rtol=0, atol=1e-7) or
                not _m4_basin_reception_np.isclose(face["gross_m3"], forward + reverse, rtol=0, atol=1e-7) or
                not _m4_basin_reception_np.isclose(face["canceled_m3"], 2 * min(forward, reverse), rtol=0, atol=1e-7)):
            raise ValueError("reception directional totals mismatch")
    record["identity_sha256"] = digest
    return record

# --- terrain_pipeline/td_lake_spill_geometry.py:14 ---
SPILL_GEOMETRY_SCHEMA = "td-lake-spill-geometry-v1"

# --- terrain_pipeline/td_lake_spill_geometry.py:17 ---
def _integer(value, name):
    if isinstance(value, bool) or not isinstance(value, _m4_lake_spill_geometry_Integral):
        raise ValueError(f"invalid_{name}")
    return int(value)

# --- terrain_pipeline/td_lake_spill_geometry.py:23 ---
def spill_geometry_finite(value, name):
    if isinstance(value, bool) or not isinstance(value, _m4_lake_spill_geometry_Real) or not _m4_lake_spill_geometry_math.isfinite(value):
        raise ValueError(f"invalid_{name}")
    return float(value)

# --- terrain_pipeline/td_lake_spill_geometry.py:29 ---
def _context(hierarchy, source_stage_m, max_path_cells):
    stage = spill_geometry_finite(source_stage_m, "source_stage_m")
    budget = _integer(max_path_cells, "max_path_cells")
    if budget < 1:
        raise ValueError("invalid_max_path_cells")
    arrays = hierarchy["arrays"]
    shape = arrays["height_m"].shape
    if len(shape) != 2 or min(shape) < 1:
        raise ValueError("invalid_grid_shape")
    spacing = spill_geometry_finite(hierarchy["metadata"]["spacing_m"], "spacing_m")
    if spacing <= 0:
        raise ValueError("invalid_spacing_m")
    origin = hierarchy["metadata"]["origin_m_xz"]
    origin_x = spill_geometry_finite(origin[0], "origin_x_m")
    origin_z = spill_geometry_finite(origin[1], "origin_z_m")
    flat = {}
    for key in ("height_m", "valid_mask", "protected_mask", "contribution_owner", "cell_owner", "receiver"):
        if arrays[key].size != arrays["height_m"].size:
            raise ValueError(f"invalid_{key}_shape")
        flat[key] = arrays[key].ravel()
    return {"arrays": arrays, "flat": flat, "shape": shape, "stage": stage,
            "budget": budget, "spacing": spacing, "origin": (origin_x, origin_z)}

# --- terrain_pipeline/td_lake_spill_geometry.py:53 ---
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

# --- terrain_pipeline/td_lake_spill_geometry.py:65 ---
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
    spill_geometry_finite(flat["height_m"][cell], "route_height_m")
    return cell

# --- terrain_pipeline/td_lake_spill_geometry.py:84 ---
def spill_geometry_d4(context, first, second):
    columns = context["shape"][1]
    first_row, first_column = divmod(first, columns)
    second_row, second_column = divmod(second, columns)
    if abs(first_row - second_row) + abs(first_column - second_column) != 1:
        raise ValueError("non_d4_connection")

# --- terrain_pipeline/td_lake_spill_geometry.py:92 ---
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
        spill_geometry_d4(context, cell, target)
        if context["flat"]["height_m"][target] > context["flat"]["height_m"][cell]:
            raise ValueError("ascending_receiver")
        cell = target

# --- terrain_pipeline/td_lake_spill_geometry.py:116 ---
def spill_geometry_xyz(context, cells):
    points = []
    for cell in cells:
        row, column = divmod(cell, context["shape"][1])
        points.append([context["origin"][0] + column * context["spacing"],
                       float(context["flat"]["height_m"][cell]),
                       context["origin"][1] + row * context["spacing"]])
    return points

# --- terrain_pipeline/td_lake_spill_geometry.py:126 ---
def _wet_approach(context, route, sill):
    required = max(sill, max(float(context["flat"]["height_m"][cell]) for cell in route))
    if context["stage"] < required:
        raise ValueError("source_stage_below_sill_or_route_height")
    cells = list(reversed(route))
    return {"kind": "sampled_submerged_lake_approach", "cell_ids": cells,
            "xyz_m": spill_geometry_xyz(context, cells), "source_stage_m": context["stage"],
            "required_stage_m": required, "all_samples_stage_covered": True,
            "all_samples_submerged": all(float(context["flat"]["height_m"][cell]) < context["stage"] for cell in route),
            "is_terrestrial_river": False}

# --- terrain_pipeline/td_lake_spill_geometry.py:138 ---
def _record(kind):
    return {"schema": SPILL_GEOMETRY_SCHEMA, "kind": kind, "status": "rejected", "reason": None,
            "coordinate_system": "model_xyz_m_original_bed", "bed_modified": False,
            "hydraulic_verified": False, "permanent_river_verified": False,
            "natural_outlet_verified": False}

# --- terrain_pipeline/td_lake_spill_geometry.py:145 ---
def trace_spill_connection(hierarchy, face, source_leaf_id, receiver_leaf_id, *,
                           source_stage_m, max_path_cells=2048):
    """Return JSON-safe exact-face geometry or a per-connection rejection.

    ``max_path_cells`` bounds the combined source and destination sample count.
    Successful records contain ``source_lake_approach``,
    ``downhill_terrain_approach`` and ``cross_face`` as separate polylines.
    """
    from terrain_pipeline.basin_storage import _face_id as _m4_lake_spill_geometry_face_id
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
        spill_geometry_d4(context, first, second)
        if face["face_id"] != _m4_lake_spill_geometry_face_id(hierarchy, index):
            raise ValueError("face_id_mismatch")
        sill = spill_geometry_finite(face["sill_m"], "sill_m")
        actual_sill = max(float(context["flat"]["height_m"][cell]) for cell in cells)
        if sill != actual_sill or sill != spill_geometry_finite(arrays["face_level_m"][index], "hierarchy_sill_m"):
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
                           "cell_ids": destination_route, "xyz_m": spill_geometry_xyz(context, destination_route),
                           "channel_verified": False},
                       "cross_face": {"cell_ids": [first, second], "xyz_m": spill_geometry_xyz(context, [first, second])},
                       "path_cell_count": len(source_route) + len(destination_route)})
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, OverflowError) as error:
        result["reason"] = str(error)
    return result

# --- terrain_pipeline/td_lake_spill_geometry.py:204 ---
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
        sill = spill_geometry_finite(boundary["sill_m"], "sill_m")
        if (sill != float(context["flat"]["height_m"][cell])
                or sill != spill_geometry_finite(context["arrays"]["boundary_level_m"][matches[0]], "boundary_sill_m")):
            raise ValueError("boundary_sill_mismatch")
        width = spill_geometry_finite(boundary["width_m"], "width_m")
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

# --- terrain_pipeline/td_lake_spill_graph.py:15 ---
SPILL_GRAPH_SCHEMA = "td-lake-spill-graph-v1"

# --- terrain_pipeline/td_lake_spill_graph.py:16 ---
MIN_VOLUME_M3 = 1e-6

# --- terrain_pipeline/td_lake_spill_graph.py:17 ---
SPILL_GRAPH_RELATIVE_TOLERANCE = .01

# --- terrain_pipeline/td_lake_spill_graph.py:18 ---
SPILL_GRAPH_MAX_BYTES = 32 * 1024**2

# --- terrain_pipeline/td_lake_spill_graph.py:19 ---
FLAGS = ("hydraulic_ready", "natural_outlet_verified", "publishable", "permanent_trunk_ready")

# --- terrain_pipeline/td_lake_spill_graph.py:22 ---
def digest(record):
    return _m4_lake_spill_graph_hashlib.sha256(_m4_lake_spill_graph_json.dumps(record, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode("utf-8")).hexdigest()

# --- terrain_pipeline/td_lake_spill_graph.py:27 ---
def face_evidence(first, second, position):
    fine, coarse = first["arrays"], second["arrays"]
    forward, reverse = fine["face_forward_m3"][:, position], fine["face_reverse_m3"][:, position]
    other_forward = coarse["face_forward_m3"][:, position]
    other_reverse = coarse["face_reverse_m3"][:, position]
    net, other = forward - reverse, other_forward - other_reverse
    gross, other_gross = forward + reverse, other_forward + other_reverse
    significant = _m4_lake_spill_graph_np.maximum(gross, other_gross) >= MIN_VOLUME_M3
    active = _m4_lake_spill_graph_np.flatnonzero(gross >= MIN_VOLUME_M3)
    signs = _m4_lake_spill_graph_np.sign(net[active])
    signs = signs[signs != 0]
    switches = int(_m4_lake_spill_graph_np.count_nonzero(signs[1:] != signs[:-1]))
    direction = int(_m4_lake_spill_graph_np.sign(net.sum()))
    late_start = int(.8 * len(net))
    late_net = float(net[late_start:].sum())
    late_ref = float(other[late_start:].sum())
    late_abs = float(_m4_lake_spill_graph_np.abs(net[late_start:]).sum())
    consistency = max(0., direction * late_net / late_abs) if late_abs else 0.
    error = float(_m4_lake_spill_graph_np.abs(net[significant] - other[significant]).sum())
    scale = float(_m4_lake_spill_graph_np.abs(other[significant]).sum())
    relative = error / max(scale, MIN_VOLUME_M3)
    interval_error = float(_m4_lake_spill_graph_np.max(_m4_lake_spill_graph_np.abs(net[significant] - other[significant]) /
        _m4_lake_spill_graph_np.maximum(_m4_lake_spill_graph_np.abs(other[significant]), MIN_VOLUME_M3))) if significant.any() else 0.
    reasons = []
    if not active.size or direction == 0:
        reasons.append("no_significant_directional_transfer")
    if switches:
        reasons.append("saved_interval_direction_switches")
    if direction * float(net.sum()) < (1. - SPILL_GRAPH_RELATIVE_TOLERANCE) * float(gross.sum()):
        reasons.append("cancellation_exceeds_one_percent")
    if direction * late_net < MIN_VOLUME_M3 or direction * late_ref < MIN_VOLUME_M3:
        reasons.append("no_same_direction_late_reception")
    if consistency < 1. - SPILL_GRAPH_RELATIVE_TOLERANCE:
        reasons.append("late_direction_not_consistent")
    if relative > SPILL_GRAPH_RELATIVE_TOLERANCE or interval_error > SPILL_GRAPH_RELATIVE_TOLERANCE:
        reasons.append("per_face_time_refinement_failed")
    if not _m4_lake_spill_graph_np.array_equal(_m4_lake_spill_graph_np.sign(net[significant]), _m4_lake_spill_graph_np.sign(other[significant])):
        reasons.append("refinement_direction_disagreement")
    return {"stable_relationship": not reasons, "direction": direction,
            "forward_m3": float(forward.sum()), "reverse_m3": float(reverse.sum()),
            "net_m3": float(net.sum()), "gross_m3": float(gross.sum()),
            "canceled_m3": float(2 * min(forward.sum(), reverse.sum())),
            "active_interval_sign_switches": switches,
            "first_active_interval": int(active[0]) if active.size else None,
            "last_active_interval": int(active[-1]) if active.size else None,
            "late_start_interval": late_start, "late_net_m3": late_net,
            "late_direction_consistency": consistency,
            "interval_net_relative_l1_difference": relative,
            "max_interval_net_relative_difference": interval_error,
            "rejection_reasons": reasons}

# --- terrain_pipeline/td_lake_spill_graph.py:79 ---
def sampled_stage(event, leaf_index, interval_values):
    active = _m4_lake_spill_graph_np.flatnonzero(interval_values >= MIN_VOLUME_M3)
    if not active.size:
        return None
    samples = _m4_lake_spill_graph_np.unique(_m4_lake_spill_graph_np.concatenate((active, active + 1)))
    position = int(samples[_m4_lake_spill_graph_np.argmax(event["arrays"]["stage_m"][samples, leaf_index])])
    return {"saved_index": position, "time_s": position * event["metadata"]["timestep_s"],
            "stage_m": float(event["arrays"]["stage_m"][position, leaf_index]),
            "semantics": "saved stage adjacent to an active transfer interval; not an internal solver-stage sample"}

# --- terrain_pipeline/td_lake_spill_graph.py:90 ---
def interval_ranges(mask):
    positions = _m4_lake_spill_graph_np.flatnonzero(mask)
    if not positions.size:
        return []
    groups = _m4_lake_spill_graph_np.split(positions, _m4_lake_spill_graph_np.flatnonzero(_m4_lake_spill_graph_np.diff(positions) > 1) + 1)
    return [[int(group[0]), int(group[-1] + 1)] for group in groups]

# --- terrain_pipeline/td_lake_spill_graph.py:98 ---
def validate_inputs(hierarchy, topology, ordinary, ordinary_reference, strong, strong_reference):
    from terrain_pipeline.basin_storage import _topology_identity as _m4_lake_spill_graph_topology_identity
    from terrain_pipeline.basin_storage import validate_runoff_exchange as _m4_lake_spill_graph_validate_runoff_exchange
    validate_basin_hierarchy(hierarchy)
    if (topology["identity_sha256"] != _m4_lake_spill_graph_topology_identity(topology) or
            topology["metadata"]["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            topology["metadata"]["source_identity_sha256"] != hierarchy["metadata"]["source_identity_sha256"]):
        raise ValueError("lake graph requires matching immutable bed and physical topology")
    for selected, reference, duration in ((ordinary, ordinary_reference, 86400.), (strong, strong_reference, 21600.)):
        for event in (selected, reference):
            _m4_lake_spill_graph_validate_runoff_exchange(event, topology)
            if event["metadata"]["duration_s"] != duration or event["metadata"]["timestep_s"] != 300.:
                raise ValueError("fixed ordinary/strong saved event interval required")
        for key in ("parameters", "runoff_metadata", "topology_identity_sha256", "source_identity_sha256"):
            if selected["metadata"][key] != reference["metadata"][key]:
                raise ValueError("event/reference physics or forcing differs")
        if (selected["identity_sha256"] == reference["identity_sha256"] or
                selected["metadata"]["max_step_s"] != 150. or reference["metadata"]["max_step_s"] != 300. or
                not _m4_lake_spill_graph_np.array_equal(selected["arrays"]["rain_mm_h"], reference["arrays"]["rain_mm_h"])):
            raise ValueError("actual distinct 150s/300s surface integration required")

# --- terrain_pipeline/td_lake_spill_graph.py:118 ---
def build_lake_spill_graph(hierarchy, topology, ordinary, ordinary_reference, strong, strong_reference):
    from terrain_pipeline.basin_storage import _face_id as _m4_lake_spill_graph_face_id
    validate_inputs(hierarchy, topology, ordinary, ordinary_reference, strong, strong_reference)
    arrays = hierarchy["arrays"]
    leaves = topology["arrays"]["leaf_ids"].tolist()
    lookup = {leaf: position for position, leaf in enumerate(leaves)}
    bed, owner = arrays["height_m"].ravel(), arrays["contribution_owner"].ravel()
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    columns = arrays["height_m"].shape[1]
    spacing, origin = hierarchy["metadata"]["spacing_m"], hierarchy["metadata"]["origin_m_xz"]
    nodes, blocked = [], []
    for position, leaf in enumerate(leaves):
        cells = _m4_lake_spill_graph_np.flatnonzero(valid & (owner == leaf))
        sinks = cells[arrays["receiver"][cells] < 0]
        if len(sinks) != 1:
            raise ValueError("one static contribution terminal per leaf required")
        terminal = int(sinks[0])
        reasons = []
        if arrays["node_unknown_contact"][leaf]:
            reasons.append("unknown_contact")
        if protected[cells].any():
            reasons.append("protected_basin")
        if reasons:
            blocked.append(leaf)
        stages = ordinary["arrays"]["stage_m"][:, position]
        nodes.append({"leaf_id": leaf, "kind": "retained_basin_storage", "terminal_cell_id": terminal,
            "terminal_xyz_m": [origin[0] + terminal % columns * spacing, float(bed[terminal]),
                               origin[1] + terminal // columns * spacing],
            "exclusive_area_m2": float(topology["arrays"]["leaf_area_m2"][position]),
            "ordinary_stage_min_m": float(stages.min()), "ordinary_stage_max_m": float(stages.max()),
            "ordinary_max_surface_volume_m3": float(ordinary["arrays"]["surface_volume_m3"][:, position].max()),
            "ordinary_runoff_supply_m3": float(ordinary["arrays"]["outflow_volume_m3"][:, position].sum()),
            "blocked_reasons": reasons})
    edges, routed_edges = [], []
    for position, face in enumerate(topology["faces"]):
        hierarchy_index = face["face_index"]
        cells = arrays["face_cells"][hierarchy_index].tolist()
        if (cells != face["cell_ids"] or face["face_id"] != _m4_lake_spill_graph_face_id(hierarchy, hierarchy_index) or
                sorted(owner[cells].tolist()) != face["leaf_ids"] or face["sill_m"] != max(bed[cells])):
            raise ValueError("graph face differs from actual bed")
        normal = face_evidence(ordinary, ordinary_reference, position)
        storm = face_evidence(strong, strong_reference, position)
        item = {**face, "ordinary": normal, "strong": storm, "routing_eligible": False,
                "strong_direction_agrees": bool(normal["direction"] != 0 and normal["direction"] == storm["direction"]),
                "source_leaf_id": None, "receiver_leaf_id": None, "geometry": None}
        if normal["stable_relationship"]:
            source, receiver = face["leaf_ids"] if normal["direction"] > 0 else face["leaf_ids"][::-1]
            directional = normal["direction"] * (ordinary["arrays"]["face_forward_m3"][:, position] -
                                                ordinary["arrays"]["face_reverse_m3"][:, position])
            sample = sampled_stage(ordinary, lookup[source], directional)
            geometry = ({"status": "rejected", "reason": "no_significant_saved_directional_interval"}
                        if sample is None else trace_spill_connection(
                            hierarchy, face, source, receiver, source_stage_m=sample["stage_m"]))
            item.update(source_leaf_id=source, receiver_leaf_id=receiver, sampled_source_stage=sample, geometry=geometry)
            item["routing_eligible"] = geometry["status"] == "accepted" and source not in blocked and receiver not in blocked
            if item["routing_eligible"]:
                routed_edges.append({"face_id": face["face_id"], "source_leaf_id": source,
                                     "receiver_leaf_id": receiver, "net_m3": abs(normal["net_m3"])})
        edges.append(item)
    outlets, routed_outlets = [], []
    for position, boundary in enumerate(topology["engineering_boundaries"]):
        actual = ordinary["arrays"]["engineering_boundary_outflow_m3"][:, position]
        other = ordinary_reference["arrays"]["engineering_boundary_outflow_m3"][:, position]
        significant = _m4_lake_spill_graph_np.maximum(actual, other) >= MIN_VOLUME_M3
        error = float(_m4_lake_spill_graph_np.abs(actual - other).sum() / max(float(other.sum()), MIN_VOLUME_M3))
        interval_error = float(_m4_lake_spill_graph_np.max(_m4_lake_spill_graph_np.abs(actual[significant] - other[significant]) /
            _m4_lake_spill_graph_np.maximum(other[significant], MIN_VOLUME_M3))) if significant.any() else 0.
        sample = sampled_stage(ordinary, lookup[boundary["leaf_id"]], actual)
        reasons = []
        if actual.sum() < MIN_VOLUME_M3 or other.sum() < MIN_VOLUME_M3:
            reasons.append("no_actual_boundary_export")
        if error > SPILL_GRAPH_RELATIVE_TOLERANCE or interval_error > SPILL_GRAPH_RELATIVE_TOLERANCE:
            reasons.append("outlet_time_refinement_failed")
        geometry = None if sample is None else trace_engineering_outlet(hierarchy, boundary, source_stage_m=sample["stage_m"])
        if geometry is not None and geometry["status"] != "accepted":
            reasons.append("outlet_geometry_rejected")
        if boundary["leaf_id"] in blocked:
            reasons.append("blocked_basin")
        item = {**boundary, "kind": "engineering_outlet", "outflow_m3": float(actual.sum()),
                "strong_outflow_m3": float(strong["arrays"]["engineering_boundary_outflow_m3"][:, position].sum()),
                "relative_l1_difference": error, "max_interval_relative_difference": interval_error,
                "sampled_source_stage": sample, "geometry": geometry,
                "routing_eligible": not reasons and geometry is not None, "rejection_reasons": reasons}
        outlets.append(item)
        if item["routing_eligible"]:
            routed_outlets.append({"leaf_id": boundary["leaf_id"], "cell_id": boundary["cell_id"], "outflow_m3": item["outflow_m3"]})
    forest = build_outlet_forest(leaves, topology["arrays"]["leaf_area_m2"].tolist(), routed_edges, routed_outlets,
                                blocked_leaf_ids=blocked)
    graph = {"schema": SPILL_GRAPH_SCHEMA, "algorithm": "saved-ordinary-stable-faces-retained-lakes-v1",
             "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
             "hierarchy_identity_sha256": hierarchy["identity_sha256"], "topology_identity_sha256": topology["identity_sha256"],
             "event_identity_sha256": {"ordinary": ordinary["identity_sha256"], "ordinary_reference": ordinary_reference["identity_sha256"],
                                       "strong": strong["identity_sha256"], "strong_reference": strong_reference["identity_sha256"]},
             "thresholds": {"minimum_volume_m3": MIN_VOLUME_M3, "relative_tolerance": SPILL_GRAPH_RELATIVE_TOLERANCE,
                            "late_start_fraction": .8}, "nodes": nodes, "edges": edges, "outlets": outlets,
             "routing_forest": forest,
             "semantics": "event-supported basin/lake/spill graph; forests are diagnostic subsets of the original graph; approach polylines are not carved channels",
             "solver_advanced": False, "bed_changed": False, "water_generated": False,
             **{name: False for name in FLAGS}}
    graph["identity_sha256"] = digest(graph)
    return graph

# --- terrain_pipeline/td_lake_spill_graph.py:221 ---
def save_lake_spill_graph(graph, path):
    from terrain_pipeline.common_infra import publish_bytes as _m4_lake_spill_graph_publish_bytes
    expected = digest({key: value for key, value in graph.items() if key != "identity_sha256"})
    if graph.get("schema") != SPILL_GRAPH_SCHEMA or graph.get("identity_sha256") != expected or any(graph.get(name) is not False for name in FLAGS):
        raise ValueError("lake graph identity/flags mismatch")
    payload = _m4_lake_spill_graph_json.dumps(graph, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > SPILL_GRAPH_MAX_BYTES:
        raise MemoryError("lake/spill graph exceeds 32MiB")
    _m4_lake_spill_graph_publish_bytes(path, payload)

# --- terrain_pipeline/td_lake_spill_corridor.py:13 ---
SPILL_CORRIDOR_SCHEMA = "td-lake-spill-original-bed-diagnostic-v2"

# --- terrain_pipeline/td_lake_spill_corridor.py:14 ---
MAX_CORRIDORS = 4096

# --- terrain_pipeline/td_lake_spill_corridor.py:15 ---
MAX_STATIONS = 1_000_000

# --- terrain_pipeline/td_lake_spill_corridor.py:16 ---
EPS = 1e-8

# --- terrain_pipeline/td_lake_spill_corridor.py:19 ---
def corridor_digest(value):
    return _m4_lake_spill_corridor_hashlib.sha256(_m4_lake_spill_corridor_json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()

# --- terrain_pipeline/td_lake_spill_corridor.py:24 ---
def corridor_xyz(value, name):
    array = _m4_lake_spill_corridor_np.asarray(value, dtype=float)
    if array.ndim != 2 or array.shape[1] != 3 or len(array) < 1 or not _m4_lake_spill_corridor_np.isfinite(array).all():
        raise ValueError(f"{name} must be finite XYZ stations")
    return array

# --- terrain_pipeline/td_lake_spill_corridor.py:31 ---
def _join(cross_face, downhill, cross_cells, downhill_cells):
    first = corridor_xyz(cross_face, "cross-face")
    second = corridor_xyz(downhill, "downhill")
    if (len(first) != 2 or len(cross_cells) != 2 or len(second) != len(downhill_cells)):
        raise ValueError("invalid_station_cells")
    if cross_cells[-1] != downhill_cells[0]:
        raise ValueError("join_cell_mismatch")
    if not _m4_lake_spill_corridor_np.array_equal(first[-1], second[0]):
        raise ValueError("join_xyz_mismatch")
    return _m4_lake_spill_corridor_np.vstack((first, second[1:]))

# --- terrain_pipeline/td_lake_spill_corridor.py:43 ---
def _audit_profile(points, sill_m):
    heights = points[:, 1]
    crest = int(_m4_lake_spill_corridor_np.argmax(heights))
    after = _m4_lake_spill_corridor_np.diff(heights[crest:])
    reasons = []
    if not _m4_lake_spill_corridor_math.isfinite(float(sill_m)) or abs(float(max(heights[:2])) - float(sill_m)) > EPS:
        reasons.append("physical_sill_mismatch")
    if _m4_lake_spill_corridor_np.any(heights[2:] > max(heights[:2]) + EPS):
        reasons.append("crest_not_at_shared_sill")
    if len(after) and _m4_lake_spill_corridor_np.any(after > EPS):
        reasons.append("downstream_profile_rises")
    return {"crest_station": crest,
            "crest_m": float(heights[crest]),
            "downstream_min_m": float(heights[-1]),
            "downstream_drop_m": float(heights[crest] - heights[-1]),
            "rejection_reasons": reasons,
            "single_crest_downhill": not reasons}

# --- terrain_pipeline/td_lake_spill_corridor.py:62 ---
def _corridor(edge):
    geometry = edge.get("geometry") or {}
    if geometry.get("status") != "accepted":
        return {"corridor_id": edge.get("face_id"), "status": "rejected",
                "rejection_reasons": ["spill_geometry_not_accepted"]}
    wet = geometry.get("source_lake_approach", {}).get("xyz_m")
    cross = geometry.get("cross_face", {}).get("xyz_m")
    dry = geometry.get("downhill_terrain_approach", {}).get("xyz_m")
    try:
        cross_cells = geometry["cross_face"]["cell_ids"]
        dry_cells = geometry["downhill_terrain_approach"]["cell_ids"]
        points = _join(cross, dry, cross_cells, dry_cells)
        profile = _audit_profile(points, edge["sill_m"])
        if geometry.get("sill_m") != edge["sill_m"]:
            profile["rejection_reasons"].append("geometry_sill_mismatch")
            profile["single_crest_downhill"] = False
    except (ValueError, KeyError, TypeError) as error:
        return {"corridor_id": edge.get("face_id"), "status": "rejected",
                "rejection_reasons": [str(error)]}
    if not profile["single_crest_downhill"]:
        return {"corridor_id": edge["face_id"], "status": "rejected",
                "source_leaf_id": edge.get("source_leaf_id"),
                "receiver_leaf_id": edge.get("receiver_leaf_id"),
                "profile": profile, "rejection_reasons": profile["rejection_reasons"]}
    return {
        "corridor_id": edge["face_id"],
        "status": "candidate",
        "source_leaf_id": edge["source_leaf_id"],
        "receiver_leaf_id": edge["receiver_leaf_id"],
        "source_lake_approach_xyz_m": wet,
        "spill_cross_face_xyz_m": cross,
        "downstream_support_xyz_m": dry,
        "source_geometry": geometry,
        "sill_m": edge["sill_m"],
        "centerline_cell_ids": cross_cells + dry_cells[1:],
        "centerline_bed_xyz_m": points.tolist(),
        "profile": profile,
        "open_lake_port": True,
        "open_downstream_port": True,
        "source_bed_unchanged": True,
        "channel_verified": False,
        "hydraulic_solved": False,
        "natural_outlet_verified": False,
        "publishable": False,
        "semantics": "saved_original_bed_path_diagnostic_not_new_bed_or_continuous_channel",
    }

# --- terrain_pipeline/td_lake_spill_corridor.py:110 ---
def build_lake_spill_corridors(graph, paths=None, *, provenance=None):
    if graph.get("schema") != "td-lake-spill-graph-v1":
        raise ValueError("saved lake spill graph is required")
    domain_edges = [edge for edge in graph.get("edges", []) if edge.get("routing_eligible")]
    selected = None
    if paths is not None:
        if paths.get("graph_identity_sha256") != graph["identity_sha256"]:
            raise ValueError("paths_graph_identity_mismatch")
        selected = sorted({arc["face_id"] for arc in paths.get("arcs", []) if arc.get("face_id")})
        if not set(selected) <= {edge["face_id"] for edge in domain_edges}:
            raise ValueError("paths_face_not_routing_eligible")
    edges = domain_edges if selected is None else [edge for edge in domain_edges if edge["face_id"] in selected]
    if len(edges) > MAX_CORRIDORS:
        raise ValueError("corridor budget exceeded")
    corridors = [_corridor(edge) for edge in edges]
    for edge, corridor in zip(edges, corridors):
        corridor.update(source_leaf_id=edge.get("source_leaf_id"),
                        receiver_leaf_id=edge.get("receiver_leaf_id"),
                        sill_m=edge.get("sill_m"), source_geometry=edge.get("geometry"))
    accepted = sum(item["status"] == "candidate" for item in corridors)
    rejected = len(corridors) - accepted
    result = {
        "schema": SPILL_CORRIDOR_SCHEMA,
        "algorithm": "saved-event-spill-original-bed-diagnostic-v2",
        "source_graph_identity_sha256": graph["identity_sha256"],
        "scope": "all_domain" if paths is None else "paths_main_watershed",
        "domain_routing_eligible_count": len(domain_edges),
        "selected_face_ids": [edge["face_id"] for edge in edges],
        "source_paths_identity_sha256": None if paths is None else paths["identity_sha256"],
        "provenance": provenance or {},
        "corridors": corridors,
        "summary": {"requested": len(corridors), "candidate": accepted, "rejected": rejected,
                    "candidate_station_count": sum(len(item.get("centerline_bed_xyz_m", []))
                                                   for item in corridors if item["status"] == "candidate")},
        "status": "candidate" if accepted else "pending",
        "continuous_bed_ready": False,
        "integrated_with_watershed_mesh": False,
        "bed_changed": False,
        "hydraulic_solved": False,
        "natural_outlet_certified": False,
        "publishable": False,
        "solver_calls": 0,
        "limitation": "original-bed diagnostic only; no derived bed, continuous channel or hydraulic certification",
    }
    if result["summary"]["candidate_station_count"] > MAX_STATIONS:
        raise ValueError("station budget exceeded")
    result["identity_sha256"] = corridor_digest(result)
    validate_lake_spill_corridors(result)
    return result

# --- terrain_pipeline/td_lake_spill_corridor.py:161 ---
def validate_lake_spill_corridors(result):
    if result.get("schema") != SPILL_CORRIDOR_SCHEMA or result.get("status") not in {"pending", "candidate"}:
        raise ValueError("invalid spill corridor package")
    if result.get("continuous_bed_ready") is not False or result.get("integrated_with_watershed_mesh") is not False:
        raise ValueError("spill corridor cannot claim integration")
    for name in ("bed_changed", "hydraulic_solved", "natural_outlet_certified", "publishable"):
        if result.get(name) is not False:
            raise ValueError("spill corridor certification flag must remain false")
    corridors = result.get("corridors", [])
    if (len(corridors) > MAX_CORRIDORS or result.get("solver_calls") != 0 or
            any(item.get("status") not in {"candidate", "rejected"} for item in corridors) or
            result.get("selected_face_ids") != [item.get("corridor_id") for item in corridors] or
            len(set(result["selected_face_ids"])) != len(corridors)):
        raise ValueError("invalid corridor census or budget")
    accepted = sum(item.get("status") == "candidate" for item in corridors)
    summary = {"requested": len(corridors), "candidate": accepted,
               "rejected": len(corridors) - accepted,
               "candidate_station_count": sum(len(item.get("centerline_bed_xyz_m", []))
                                              for item in corridors if item.get("status") == "candidate")}
    if result.get("summary") != summary:
        raise ValueError("spill corridor summary mismatch")
    if summary["candidate_station_count"] > MAX_STATIONS:
        raise ValueError("station budget exceeded")
    for item in corridors:
        if item.get("status") == "candidate":
            points = corridor_xyz(item["centerline_bed_xyz_m"], "candidate centerline")
            if not item.get("open_lake_port") or not item.get("open_downstream_port"):
                raise ValueError("candidate corridor must retain both open ports")
            if item.get("source_bed_unchanged") is not True or item.get("channel_verified") is not False:
                raise ValueError("candidate corridor provenance mismatch")
            if item["profile"]["crest_station"] != int(_m4_lake_spill_corridor_np.argmax(points[:, 1])):
                raise ValueError("candidate crest mismatch")
            geometry = item["source_geometry"]
            joined = _join(geometry["cross_face"]["xyz_m"], geometry["downhill_terrain_approach"]["xyz_m"],
                           geometry["cross_face"]["cell_ids"], geometry["downhill_terrain_approach"]["cell_ids"])
            if not _m4_lake_spill_corridor_np.array_equal(points, joined) or item["profile"] != _audit_profile(joined, item["sill_m"]):
                raise ValueError("candidate original-bed profile mismatch")
    unsigned = dict(result)
    identity = unsigned.pop("identity_sha256", None)
    if identity != corridor_digest(unsigned):
        raise ValueError("spill corridor identity mismatch")
    return True

# --- terrain_pipeline/td_lake_spill_corridor.py:205 ---
def save_lake_spill_corridors(result, path):
    validate_lake_spill_corridors(result)
    target = _m4_lake_spill_corridor_Path(path)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_m4_lake_spill_corridor_json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return target

# --- terrain_pipeline/td_lake_spill_corridor.py:215 ---
def load_lake_spill_corridors(path):
    result = _m4_lake_spill_corridor_json.loads(_m4_lake_spill_corridor_Path(path).read_text(encoding="utf-8"))
    validate_lake_spill_corridors(result)
    return result

# --- terrain_pipeline/td_lake_outlet_forest.py:11 ---
def _identifier(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value

# --- terrain_pipeline/td_lake_outlet_forest.py:17 ---
def _positive(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or
            not _m4_lake_outlet_forest_math.isfinite(value) or value <= 0):
        raise ValueError(f"{name} must be finite and positive")
    return float(value)

# --- terrain_pipeline/td_lake_outlet_forest.py:24 ---
def _face_key(value):
    if isinstance(value, str) and value:
        return (1, value)
    return (0, _identifier(value, "face_id"))

# --- terrain_pipeline/td_lake_outlet_forest.py:30 ---
def _fields(record, names, kind):
    if not isinstance(record, dict) or any(name not in record for name in names):
        raise ValueError(f"{kind} must contain {', '.join(names)}")

# --- terrain_pipeline/td_lake_outlet_forest.py:35 ---
def build_outlet_forest(leaf_ids, areas_m2, directed_edges, outlets, *, blocked_leaf_ids=()):
    """Select shortest supported routes to actual exports without altering edges.

    Ties prefer root leaf/cell, larger face net volume, then face/receiver ID.
    Components own each reachable leaf exactly once. Main path is root-first
    and follows the child with largest accumulated upstream area. Its face IDs
    are source-to-export; event-union support does not prove simultaneous flow.
    """
    if len(leaf_ids) != len(areas_m2):
        raise ValueError("leaf_ids and areas_m2 must have equal lengths")
    areas = {}
    for leaf_id, area in zip(leaf_ids, areas_m2):
        leaf_id = _identifier(leaf_id, "leaf_id")
        if leaf_id in areas:
            raise ValueError("leaf_ids must be unique")
        areas[leaf_id] = _positive(area, "area_m2")
    ordered_ids = sorted(areas)
    blocked = {_identifier(leaf_id, "blocked_leaf_id") for leaf_id in blocked_leaf_ids}
    if not blocked.issubset(areas):
        raise ValueError("blocked_leaf_ids must refer to known leaves")

    incoming = {leaf_id: [] for leaf_id in ordered_ids}
    edges = []
    face_ids = set()
    for edge in directed_edges:
        _fields(edge, ("face_id", "source_leaf_id", "receiver_leaf_id", "net_m3"), "edge")
        face_id = edge["face_id"]
        _face_key(face_id)
        source = _identifier(edge["source_leaf_id"], "source_leaf_id")
        receiver = _identifier(edge["receiver_leaf_id"], "receiver_leaf_id")
        _positive(edge["net_m3"], "net_m3")
        if source not in areas or receiver not in areas:
            raise ValueError("edges must refer to known leaves")
        if source == receiver:
            raise ValueError("self-loop edges are not allowed")
        if face_id in face_ids:
            raise ValueError("edge face_ids must be unique")
        face_ids.add(face_id)
        copied = _m4_lake_outlet_forest_deepcopy(edge)
        edges.append(copied)
        incoming[receiver].append(copied)
    edges.sort(key=lambda edge: _face_key(edge["face_id"]))

    seeds = {}
    for outlet in outlets:
        _fields(outlet, ("leaf_id", "cell_id", "outflow_m3"), "outlet")
        leaf_id = _identifier(outlet["leaf_id"], "outlet leaf_id")
        cell_id = _identifier(outlet["cell_id"], "outlet cell_id")
        outflow = _positive(outlet["outflow_m3"], "outflow_m3")
        if leaf_id not in areas:
            raise ValueError("outlets must refer to known leaves")
        if leaf_id in blocked:
            continue
        previous = seeds.get(leaf_id)
        if previous is None or (-outflow, cell_id) < (-previous["outflow_m3"], previous["cell_id"]):
            seeds[leaf_id] = {"leaf_id": leaf_id, "cell_id": cell_id, "outflow_m3": outflow}

    indices = {leaf_id: index for index, leaf_id in enumerate(ordered_ids)}
    adjacency = _m4_lake_outlet_forest_csr_matrix(
        ([1] * len(edges),
         ([indices[edge["source_leaf_id"]] for edge in edges],
          [indices[edge["receiver_leaf_id"]] for edge in edges])),
        shape=(len(ordered_ids), len(ordered_ids)),
    )
    if ordered_ids:
        _, labels = _m4_lake_outlet_forest_connected_components(adjacency, directed=True, connection="strong")
        groups = {}
        for leaf_id, label in zip(ordered_ids, labels):
            groups.setdefault(int(label), []).append(leaf_id)
        strong_components = sorted(groups.values())
    else:
        strong_components = []
    cyclic_components = [group for group in strong_components if len(group) > 1]

    hops = {leaf_id: 0 for leaf_id in sorted(seeds)}
    queue = _m4_lake_outlet_forest_deque(sorted(seeds))
    visit_order = []
    while queue:
        receiver = queue.popleft()
        visit_order.append(receiver)
        for edge in sorted(incoming[receiver], key=lambda edge: _face_key(edge["face_id"])):
            source = edge["source_leaf_id"]
            if source in blocked or source in hops:
                continue
            hops[source] = hops[receiver] + 1
            queue.append(source)

    records = {}
    children = {leaf_id: [] for leaf_id in ordered_ids}
    for leaf_id in ordered_ids:
        records[leaf_id] = {
            "leaf_id": leaf_id,
            "reachable": leaf_id in hops,
            "parent_leaf_id": None,
            "parent_face_id": None,
            "root_leaf_id": None,
            "root_boundary_cell_id": None,
            "hops": hops.get(leaf_id),
            "supported_area_m2": 0.0,
            "reason": "blocked" if leaf_id in blocked else "no_event_supported_route_to_export",
        }
    outgoing = {leaf_id: [] for leaf_id in ordered_ids}
    for edge in edges:
        outgoing[edge["source_leaf_id"]].append(edge)
    for leaf_id in sorted(visit_order, key=lambda leaf_id: (hops[leaf_id], leaf_id)):
        record = records[leaf_id]
        if hops[leaf_id] == 0:
            root_leaf_id = leaf_id
        else:
            candidates = [edge for edge in outgoing[leaf_id]
                          if hops.get(edge["receiver_leaf_id"]) == hops[leaf_id] - 1]
            selected = min(candidates, key=lambda edge: (
                records[edge["receiver_leaf_id"]]["root_leaf_id"],
                records[edge["receiver_leaf_id"]]["root_boundary_cell_id"],
                -edge["net_m3"], _face_key(edge["face_id"]), edge["receiver_leaf_id"],
            ))
            parent = selected["receiver_leaf_id"]
            root_leaf_id = records[parent]["root_leaf_id"]
            record["parent_leaf_id"] = parent
            record["parent_face_id"] = selected["face_id"]
            children[parent].append(leaf_id)
        record["root_leaf_id"] = root_leaf_id
        record["root_boundary_cell_id"] = seeds[root_leaf_id]["cell_id"]
        record["reason"] = None
    for leaf_id in sorted(visit_order, key=lambda leaf_id: (-hops[leaf_id], leaf_id)):
        records[leaf_id]["supported_area_m2"] = _m4_lake_outlet_forest_math.fsum(
            [areas[leaf_id]] + [records[child]["supported_area_m2"] for child in sorted(children[leaf_id])]
        )

    members = {root: [] for root in seeds}
    for leaf_id in ordered_ids:
        if records[leaf_id]["reachable"]:
            members[records[leaf_id]["root_leaf_id"]].append(leaf_id)
    components = [{
        "root_leaf_id": root,
        "root_boundary_cell_id": seeds[root]["cell_id"],
        "leaf_ids": members[root],
        "area_m2": _m4_lake_outlet_forest_math.fsum(areas[leaf_id] for leaf_id in members[root]),
        "leaf_count": len(members[root]),
        "outlet": _m4_lake_outlet_forest_deepcopy(seeds[root]),
    } for root in sorted(seeds)]
    primary = min(components, key=lambda component: (
        -component["area_m2"], -component["outlet"]["outflow_m3"],
        component["root_boundary_cell_id"], component["root_leaf_id"],
    )) if components else None
    main_path = []
    if primary is not None:
        current = primary["root_leaf_id"]
        while True:
            main_path.append(current)
            if not children[current]:
                break
            current = min(children[current], key=lambda child: (
                -records[child]["supported_area_m2"], child,
            ))
    return {
        "records": [records[leaf_id] for leaf_id in ordered_ids],
        "components": components,
        "primary_component": _m4_lake_outlet_forest_deepcopy(primary),
        "main_path": main_path,
        "main_path_face_ids": [records[leaf_id]["parent_face_id"]
                               for leaf_id in reversed(main_path[1:])],
        "graph_diagnostics": {
            "directed_edges": edges,
            "leaf_count": len(ordered_ids),
            "edge_count": len(edges),
            "strong_components": strong_components,
            "cyclic_components": cyclic_components,
            "has_cycles": bool(cyclic_components),
            "blocked_leaf_ids": sorted(blocked),
        },
        "permanent_trunk_ready": False,
        "hydraulic_ready": False,
        "natural_outlet_verified": False,
        "publishable": False,
    }

# --- terrain_pipeline/td_basin_escape_plan.py:15 ---
ESCAPE_PLAN_SCHEMA = "td-basin-escape-plan-v1"

# --- terrain_pipeline/td_basin_escape_plan.py:16 ---
ESCAPE_PLAN_MAX_BYTES = 16 * 1024 * 1024

# --- terrain_pipeline/td_basin_escape_plan.py:19 ---
def escape_plan_face_id(hierarchy, face):
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_escape_plan_hash
    arrays, metadata = hierarchy["arrays"], hierarchy["metadata"]
    columns = arrays["height_m"].shape[1]
    spacing = metadata["spacing_m"]
    origin = metadata["origin_m_xz"]
    endpoints = []
    for cell in arrays["face_cells"][face]:
        row, column = divmod(int(cell), columns)
        xyz = [float(origin[0] + column * spacing), float(arrays["height_m"].ravel()[cell]),
               float(origin[1] + row * spacing)]
        endpoints.append([value.hex() for value in xyz])
    return "face:" + _m4_basin_escape_plan_hash([metadata["source_identity_sha256"], sorted(endpoints)])

# --- terrain_pipeline/td_basin_escape_plan.py:33 ---
def _checked_plan(hierarchy, graph, seeds, hierarchy_pin):
    from terrain_pipeline.td_surface_reaches import _freeze as _m4_basin_escape_plan_freeze
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_escape_plan_hash
    from terrain_pipeline.td_surface_reaches import _plain as _m4_basin_escape_plan_plain
    if hierarchy["identity_sha256"] != hierarchy_pin:
        raise ValueError("external hierarchy identity mismatch")
    validate_basin_hierarchy(hierarchy)
    expected_graph = _leaf_graph(hierarchy, None)
    graph_plain = _m4_basin_escape_plan_plain(graph)
    if graph_plain["leaf_nodes"] != expected_graph["leaf_nodes"]:
        raise ValueError("catchment node semantics mismatch")
    geometry_fields = ("leaf_ids", "stable_leaf_ids", "pair_id", "all_face_indices", "minimum_physical_sill_m",
                       "minimum_face_indices", "rejected_face_indices", "potential_connection_allowed")
    if len(graph_plain["pairs"]) != len(expected_graph["pairs"]):
        raise ValueError("catchment pair coverage mismatch")
    for actual, expected in zip(graph_plain["pairs"], expected_graph["pairs"]):
        if any(actual[name] != expected[name] for name in geometry_fields):
            raise ValueError("catchment pair geometry mismatch")
    arrays = hierarchy["arrays"]
    leaf = arrays["contribution_owner"].ravel()
    bed = arrays["height_m"].ravel()
    valid = arrays["valid_mask"].ravel()
    protected = arrays["protected_mask"].ravel()
    nodes = {node["leaf_id"]: node for node in expected_graph["leaf_nodes"]}
    blocked = {}
    for node in nodes:
        reasons = []
        if arrays["node_unknown_contact"][node]:
            reasons.append("unknown_contact")
        if _m4_basin_escape_plan_np.any(protected & (leaf == node)):
            reasons.append("protected_catchment")
        blocked[node] = reasons
    seeds = _m4_basin_escape_plan_plain(seeds)
    if not isinstance(seeds, list):
        raise ValueError("explicit seed list required")
    seed_cells = set()
    seed_records = []
    for seed in seeds:
        if set(seed) != {"leaf_id", "boundary_cell_id"}:
            raise ValueError("seed requires leaf and exact engineering boundary cell")
        node, cell = seed["leaf_id"], seed["boundary_cell_id"]
        if type(node) is not int or type(cell) is not int or node not in nodes or not 0 <= cell < len(bed):
            raise ValueError("invalid seed cell/leaf")
        if not arrays["open_boundary_mask"].ravel()[cell] or int(leaf[cell]) != node or blocked[node]:
            raise ValueError("seed is not an allowed engineering boundary")
        if cell in seed_cells:
            raise ValueError("duplicate engineering boundary seed")
        seed_cells.add(cell)
        seed_records.append({**seed, "boundary_level_m": float(bed[cell]), "stable_leaf_id": nodes[node]["stable_leaf_id"]})
    seed_records.sort(key=lambda item: (item["stable_leaf_id"], item["boundary_level_m"], item["boundary_cell_id"]))
    adjacency = {node: [] for node in nodes}
    for pair in expected_graph["pairs"]:
        first, second = pair["leaf_ids"]
        if not pair["potential_connection_allowed"] or blocked[first] or blocked[second]:
            continue
        face = min(pair["minimum_face_indices"], key=lambda index: escape_plan_face_id(hierarchy, index))
        evidence = {"pair_id": pair["pair_id"], "face_index": face, "face_id": escape_plan_face_id(hierarchy, face),
                    "face_cell_ids": arrays["face_cells"][face].tolist(), "physical_sill_m": pair["minimum_physical_sill_m"]}
        adjacency[first].append((second, evidence))
        adjacency[second].append((first, evidence))
    distances = {node: _m4_basin_escape_plan_math.inf for node in nodes}
    candidate_keys, parents, chosen_faces, roots = {}, {}, {}, {}
    heap = []
    for seed in seed_records:
        node, cell, stage = seed["leaf_id"], seed["boundary_cell_id"], seed["boundary_level_m"]
        key = (stage, "seed", nodes[node]["stable_leaf_id"], cell)
        if node not in candidate_keys or key < candidate_keys[node]:
            candidate_keys[node] = key
            distances[node] = stage
            parents[node], chosen_faces[node], roots[node] = None, None, cell
            _m4_basin_escape_plan_heapq.heappush(heap, (stage, nodes[node]["stable_leaf_id"], node, key))
    settled = {}
    while heap:
        stage, stable_id, node, key = _m4_basin_escape_plan_heapq.heappop(heap)
        if node in settled or candidate_keys[node] != key:
            continue
        settled[node] = len(settled)
        for target, evidence in adjacency[node]:
            if target in settled:
                continue
            target_stage = max(stage, evidence["physical_sill_m"])
            target_key = (target_stage, "face", evidence["face_id"], stable_id)
            if target not in candidate_keys or target_key < candidate_keys[target]:
                candidate_keys[target] = target_key
                distances[target] = target_stage
                parents[target], chosen_faces[target], roots[target] = node, evidence, roots[node]
                _m4_basin_escape_plan_heapq.heappush(heap, (target_stage, nodes[target]["stable_leaf_id"], target, target_key))
    records = []
    area = hierarchy["metadata"]["spacing_m"] ** 2
    for node in sorted(nodes, key=lambda value: nodes[value]["stable_leaf_id"]):
        reachable = node in settled
        stage = distances[node] if reachable else None
        volume = None if not reachable else float(_m4_basin_escape_plan_np.maximum(stage - bed[valid & (leaf == node)], 0).sum() * area)
        records.append({"leaf_id": node, "stable_leaf_id": nodes[node]["stable_leaf_id"],
                        "reachable": reachable, "minimum_escape_stage_m": stage,
                        "parent_leaf_id": parents.get(node), "minimum_face": chosen_faces.get(node),
                        "root_boundary_cell_id": roots.get(node), "settlement_rank": settled.get(node),
                        "raise_to_stage_volume_m3": volume,
                        "unreachable_reasons": [] if reachable else blocked[node] or ["no_allowed_path_to_explicit_seed"]})
    result = {"schema": ESCAPE_PLAN_SCHEMA, "algorithm": "multi-source-minimax-settled-parent-forest-v1",
              "hierarchy_identity_sha256": hierarchy_pin,
              "source_identity_sha256": hierarchy["metadata"]["source_identity_sha256"],
              "catchment_geometry_identity_sha256": _m4_basin_escape_plan_hash(expected_graph), "engineering_seeds": seed_records,
              "leaves": records, "summary": {"leaf_count": len(records), "reachable_leaves": len(settled),
                "unreachable_leaves": len(records) - len(settled),
                "exclusive_raise_to_stage_volume_m3": sum(item["raise_to_stage_volume_m3"] or 0. for item in records)},
              "flags": {"potential_only": True, "bed_unchanged": True, "receiver_unchanged": True,
                        "hydraulic_verified": False, "hydraulic_ready": False, "transient_converged": False,
                        "publishable": False, "natural_outlet_verified": False, "water_generated": False},
              "semantics": "Engineering seed stage equals its unchanged boundary bed. Minimum maximum face sill to any explicit seed. Parent always settled earlier, including equal levels; physical IDs resolve ties. Raise-to-stage volume sums positive(stage-bed) over exclusive catchment cells, not existing water, incremental fill demand or nested hierarchy capacities. Unknown or any protected catchment is conservatively blocked. No imposed receiver link, bed filling/cutting, hydro solve, spill onset, Q or coupled cross-domain advancement."}
    result["identity_sha256"] = _m4_basin_escape_plan_hash(result)
    return _m4_basin_escape_plan_freeze(result)

# --- terrain_pipeline/td_basin_escape_plan.py:144 ---
def make_basin_escape_plan(hierarchy, *, contribution_leaf_graph, engineering_seeds, expected_hierarchy_identity):
    return _checked_plan(hierarchy, contribution_leaf_graph, engineering_seeds, expected_hierarchy_identity)

# --- terrain_pipeline/td_basin_escape_plan.py:148 ---
def save_basin_escape_plan(result, path):
    from terrain_pipeline.common_infra import publish_bytes as _m4_basin_escape_plan_publish_bytes
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_escape_plan_hash
    from terrain_pipeline.td_surface_reaches import _plain as _m4_basin_escape_plan_plain
    plain = _m4_basin_escape_plan_plain(result)
    digest = plain.pop("identity_sha256")
    if plain.get("schema") != ESCAPE_PLAN_SCHEMA or _m4_basin_escape_plan_hash(plain) != digest:
        raise ValueError("escape plan identity/schema mismatch")
    plain["identity_sha256"] = digest
    payload = _m4_basin_escape_plan_json.dumps(plain, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(payload) > ESCAPE_PLAN_MAX_BYTES:
        raise ValueError("escape plan JSON budget exceeded")
    _m4_basin_escape_plan_publish_bytes(path, payload)

# --- terrain_pipeline/td_basin_escape_plan.py:160 ---
def load_basin_escape_plan(path, *, expected_sha256, expected_identity, hierarchy, contribution_leaf_graph):
    from terrain_pipeline.common_infra import file_sha256 as _m4_basin_escape_plan_file_sha256
    from terrain_pipeline.td_surface_reaches import _freeze as _m4_basin_escape_plan_freeze
    from terrain_pipeline.td_surface_reaches import _hash as _m4_basin_escape_plan_hash
    path = _m4_basin_escape_plan_Path(path)
    if path.stat().st_size > ESCAPE_PLAN_MAX_BYTES or _m4_basin_escape_plan_file_sha256(path) != expected_sha256:
        raise ValueError("external escape plan pin/budget mismatch")
    result = _read_json(path)
    digest = result.pop("identity_sha256")
    if digest != expected_identity or _m4_basin_escape_plan_hash(result) != digest:
        raise ValueError("external escape plan identity mismatch")
    seeds = [{"leaf_id": seed["leaf_id"], "boundary_cell_id": seed["boundary_cell_id"]} for seed in result["engineering_seeds"]]
    expected = _checked_plan(hierarchy, contribution_leaf_graph, seeds, result["hierarchy_identity_sha256"])
    if expected["identity_sha256"] != digest:
        raise ValueError("escape plan semantic mismatch")
    result["identity_sha256"] = digest
    return _m4_basin_escape_plan_freeze(result)
