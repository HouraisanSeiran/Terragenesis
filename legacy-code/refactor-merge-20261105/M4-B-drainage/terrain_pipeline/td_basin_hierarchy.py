"""Exact D4 lower-star merge tree, unchanged-bed routing and staged hypsometry."""

from collections import deque

import numpy as np

from terrain_pipeline.common_infra import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.td_basin_source import validate_td_source

MAX_CURVE_ENTRIES = 4_000_000


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


def _flat_receivers(height, valid, rows, columns):
    receiver = np.full(height.size, -1, np.int64)
    visited = np.zeros(height.size, bool)
    for first in np.flatnonzero(valid):
        if visited[first]:
            continue
        plateau = [int(first)]
        visited[first] = True
        pending = deque(plateau)
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
        pending = deque(sorted(seeds))
        while pending:
            cell = pending.popleft()
            for neighbor in _neighbors(cell, rows, columns):
                if valid[neighbor] and height[neighbor] == height[cell] and neighbor not in assigned:
                    assigned.add(neighbor)
                    receiver[neighbor] = cell
                    pending.append(neighbor)
    return receiver


def build_basin_hierarchy(source):
    validate_td_source(source)
    source_arrays = source["arrays"]
    bed = source_arrays["height_m"]
    rows, columns = bed.shape
    height = bed.ravel()
    valid = source_arrays["valid_mask"].ravel()
    opened = source_arrays["open_boundary_mask"].ravel()
    area = source["metadata"]["spacing_m"] ** 2
    ordered = np.flatnonzero(valid)
    ordered = ordered[np.argsort(height[ordered], kind="stable")]
    union_parent = np.arange(height.size, dtype=np.int64)
    active = np.zeros(height.size, bool)
    current_node = np.full(height.size, -1, np.int64)
    owner = np.full(height.size, -1, np.int64)
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
                upper.append(np.inf)
                children.append(previous)
                own_cells.append(cells)
                for child in previous:
                    parents[child] = node
                    upper[child] = float(level)
            current_node[root] = node
            owner[cells] = node
        start = stop

    receiver = _flat_receivers(height, valid, rows, columns)
    contribution = np.full(height.size, -1, np.int64)
    for first in np.flatnonzero(valid):
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
    for cell in np.flatnonzero(valid):
        row, column = divmod(int(cell), columns)
        if column + 1 < columns and valid[cell + 1]:
            face_cells.append((cell, cell + 1))
        if row + 1 < rows and valid[cell + columns]:
            face_cells.append((cell, cell + columns))
    faces = np.array(face_cells, np.int64).reshape(-1, 2)
    face_nodes = owner[faces]
    depths = np.zeros(len(parents), np.int64)
    ancestor = np.array(parents, np.int64)
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
    merge_nodes = np.where(first_nodes == second_nodes, first_nodes, ancestor[first_nodes])

    curve_offsets = [0]
    curve_levels, curve_volumes = [], []
    subtree_sums = []
    stage_capacity, node_count, unknown_contact, open_contact, open_levels = [], [], [], [], []
    retained_entries = 0
    for node, cells in enumerate(own_cells):
        child_count = sum(node_count[child] for child in children[node])
        child_sum = sum(subtree_sums[child] for child in children[node])
        count = len(cells) + child_count
        values = np.sort(height[cells])
        retained_entries += len(values)
        if retained_entries + len(curve_levels) > MAX_CURVE_ENTRIES:
            raise ValueError("hierarchy hypsometry work/memory budget exceeded")
        subtree_sums.append(child_sum + float(values.sum()))
        node_count.append(count)
        local_unknown = any(not valid[neighbor] for cell in cells for neighbor in _neighbors(cell, rows, columns))
        unknown_contact.append(local_unknown or any(unknown_contact[child] for child in children[node]))
        local_open = bool(opened[cells].any())
        open_contact.append(local_open or any(open_contact[child] for child in children[node]))
        local_open_level = float(height[np.asarray(cells)[opened[cells]]].min()) if local_open else np.inf
        open_levels.append(min([local_open_level] + [open_levels[child] for child in children[node]]))
        knots = np.unique(np.concatenate(([births[node]], values[values >= births[node]],
                                         [] if np.isinf(upper[node]) else [upper[node]])))
        knots = knots[knots <= upper[node]]
        prefix = np.concatenate(([0.0], np.cumsum(values, dtype=np.float64)))
        counts = np.searchsorted(values, knots, side="left")
        volumes = area * (knots * (counts + child_count) - prefix[counts] - child_sum)
        curve_levels.extend(knots)
        curve_volumes.extend(volumes)
        curve_offsets.append(len(curve_levels))
        stage_capacity.append(np.inf if np.isinf(upper[node]) else float(volumes[-1] - volumes[0]))

    arrays = dict(source_arrays)
    arrays.update({"receiver": receiver, "cell_owner": owner.reshape(bed.shape),
        "contribution_owner": contribution.reshape(bed.shape), "node_parent": np.array(parents, np.int64),
        "node_birth_m": np.array(births), "node_upper_m": np.array(upper),
        "node_cell_count": np.array(node_count, np.int64), "node_unknown_contact": np.array(unknown_contact, bool),
        "node_open_boundary": np.array(open_contact, bool), "node_open_level_m": np.array(open_levels),
        "face_cells": faces, "face_nodes": face_nodes, "face_merge_node": merge_nodes,
        "face_level_m": np.max(height[faces], axis=1),
        "boundary_cells": np.flatnonzero(opened), "boundary_level_m": height[opened],
        "curve_offsets": np.array(curve_offsets, np.int64), "curve_level_m": np.array(curve_levels),
        "curve_volume_m3": np.array(curve_volumes), "stage_capacity_m3": np.array(stage_capacity)})
    arrays = {key: readonly(value) for key, value in arrays.items()}
    metadata = {"schema": "td-basin-hierarchy-v1", "algorithm": "D4-equal-level-batch-lower-star-v1",
        "source_identity_sha256": source["identity_sha256"], "source_metadata": source["metadata"],
        "spacing_m": source["metadata"]["spacing_m"], "origin_m_xz": source["metadata"]["origin_m_xz"],
        "max_curve_entries": MAX_CURVE_ENTRIES, "retained_hypsometry_entries": retained_entries,
        "capacity_semantics": "absolute subtree V(h); stage=V(upper)-V(birth); roots unbounded",
        "nonfinite_sentinel": "+inf only in upper/open-level/stage-capacity arrays means no finite event; never a solved water level",
        "receiver_semantics": "D4 nonascending static contribution routing, not hydraulic exchange",
        "natural_outlet_verified": False, "hydraulic_ready": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def basin_volume_at_level(result, node, level_m):
    arrays = result["arrays"]
    if type(node) is not int or not 0 <= node < len(arrays["node_parent"]) or not np.isfinite(level_m):
        raise ValueError("finite level and valid node required")
    if level_m < arrays["node_birth_m"][node] or level_m > arrays["node_upper_m"][node]:
        raise ValueError("level outside connected node stage")
    start, stop = arrays["curve_offsets"][node:node + 2]
    levels = arrays["curve_level_m"][start:stop]
    volumes = arrays["curve_volume_m3"][start:stop]
    if level_m > levels[-1]:
        return float(volumes[-1] + (level_m - levels[-1]) * arrays["node_cell_count"][node] * result["metadata"]["spacing_m"] ** 2)
    return float(np.interp(level_m, levels, volumes))


def validate_basin_hierarchy(result, *, reconstruct=False):
    arrays, metadata = result["arrays"], result["metadata"]
    source_arrays = {key: arrays[key] for key in ("height_m", "valid_mask", "protected_mask", "open_boundary_mask")}
    source = {"arrays": source_arrays, "metadata": metadata["source_metadata"],
              "identity_sha256": metadata["source_identity_sha256"]}
    validate_td_source(source)
    if metadata["schema"] != "td-basin-hierarchy-v1" or result["identity_sha256"] != identity(arrays, metadata):
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
    if (parent.dtype != np.int64 or parent.ndim != 1 or not 1 <= node_count <= valid.sum() * 2 or
            np.any((parent != -1) & ((parent <= np.arange(node_count)) | (parent >= node_count))) or
            owner.shape != valid.shape or np.any(owner[~valid] != -1) or
            np.any((owner[valid] < 0) | (owner[valid] >= node_count)) or receiver.shape != valid.shape or
            receiver.dtype != np.int64 or np.any((receiver < -1) | (receiver >= valid.size))):
        raise ValueError("invalid hierarchy ownership/parent/receiver")
    bed = arrays["height_m"].ravel()
    columns = arrays["height_m"].shape[1]
    selected = np.flatnonzero(receiver >= 0)
    target = receiver[selected]
    distance = abs(selected // columns - target // columns) + abs(selected % columns - target % columns)
    if np.any(distance != 1) or not valid[target].all() or np.any(bed[target] > bed[selected]):
        raise ValueError("invalid D4 nonascending receiver")
    complete = np.zeros(valid.size, bool)
    contribution = arrays["contribution_owner"].ravel()
    for first in np.flatnonzero(valid):
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
    if faces.ndim != 2 or faces.shape[1] != 2 or faces.dtype != np.int64 or np.any((faces < 0) | (faces >= valid.size)):
        raise ValueError("invalid face indices")
    if not valid[faces].all() or not np.array_equal(arrays["face_nodes"], owner[faces]):
        raise ValueError("invalid face ownership")
    distance = abs(faces[:, 0] // columns - faces[:, 1] // columns) + abs(faces[:, 0] % columns - faces[:, 1] % columns)
    if np.any(distance != 1) or not np.array_equal(arrays["face_level_m"], np.max(bed[faces], axis=1)):
        raise ValueError("invalid D4 face elevations")
    expected_faces = []
    rows = arrays["height_m"].shape[0]
    for cell in np.flatnonzero(valid):
        row, column = divmod(int(cell), columns)
        if column + 1 < columns and valid[cell + 1]:
            expected_faces.append((cell, cell + 1))
        if row + 1 < rows and valid[cell + columns]:
            expected_faces.append((cell, cell + columns))
    if not np.array_equal(faces, np.array(expected_faces, np.int64).reshape(-1, 2)):
        raise ValueError("missing/duplicate D4 faces")
    for key in ("node_birth_m", "node_upper_m", "node_cell_count", "node_unknown_contact", "node_open_boundary",
                "node_open_level_m", "stage_capacity_m3"):
        if arrays[key].shape != (node_count,):
            raise ValueError("node array shape mismatch")
    births, upper = arrays["node_birth_m"], arrays["node_upper_m"]
    child = np.flatnonzero(parent >= 0)
    if (not np.isfinite(births).all() or np.any(np.isnan(upper)) or np.any(upper < births) or
            not np.array_equal(upper[child], births[parent[child]]) or
            not np.isposinf(upper[parent < 0]).all()):
        raise ValueError("invalid parent stage elevation")
    counts = np.bincount(owner[valid], minlength=node_count)
    for node in range(node_count):
        if parent[node] >= 0:
            counts[parent[node]] += counts[node]
    if not np.array_equal(counts, arrays["node_cell_count"]):
        raise ValueError("subtree cell double counting")
    if not np.array_equal(arrays["boundary_cells"], np.flatnonzero(arrays["open_boundary_mask"].ravel())) or not np.array_equal(
            arrays["boundary_level_m"], bed[arrays["boundary_cells"]]):
        raise ValueError("boundary face mismatch")
    offsets = arrays["curve_offsets"]
    levels, volumes = arrays["curve_level_m"], arrays["curve_volume_m3"]
    if (offsets.shape != (node_count + 1,) or offsets[0] != 0 or offsets[-1] != len(levels) or
            np.any(np.diff(offsets) <= 0) or levels.shape != volumes.shape or
            not np.isfinite(levels).all() or not np.isfinite(volumes).all() or np.any(volumes < -1e-6)):
        raise ValueError("invalid capacity CSR")
    for node in range(node_count):
        start, stop = offsets[node:node + 2]
        if (np.any(np.diff(levels[start:stop]) <= 0) or np.any(np.diff(volumes[start:stop]) < -1e-6) or
                levels[start] != arrays["node_birth_m"][node] or levels[stop - 1] > arrays["node_upper_m"][node]):
            raise ValueError("invalid stage curve")
        capacity = arrays["stage_capacity_m3"][node]
        if np.isfinite(upper[node]):
            if levels[stop - 1] != upper[node] or capacity != volumes[stop - 1] - volumes[start]:
                raise ValueError("stage marginal capacity mismatch")
        elif not np.isposinf(capacity):
            raise ValueError("invalid root capacity sentinel")
    if reconstruct:
        expected = build_basin_hierarchy(source)
        if metadata != expected["metadata"] or set(arrays) != set(expected["arrays"]) or any(
                not np.array_equal(value, expected["arrays"][key]) for key, value in arrays.items()):
            raise ValueError("hierarchy arrays differ from exact source reconstruction")
    return True


def save_basin_hierarchy(path, result):
    save_bundle(path, result, validator=lambda bundle: validate_basin_hierarchy(bundle, reconstruct=True))


def load_basin_hierarchy(path, *, expected_sha256, expected_identity):
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_basin_hierarchy)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external hierarchy identity mismatch")
    return result
