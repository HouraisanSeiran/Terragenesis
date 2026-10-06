"""Bounded CPU geometry on finite windows; never a natural-mouth certificate."""

from collections import deque
from dataclasses import asdict, dataclass
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np
from scipy import ndimage


ALGORITHM = "mountain-depression-geometry-v1"
SCHEMA = "mountain-depression-geometry-npz-v1"
NEIGHBORS = ((-1, 0), (0, -1), (0, 1), (1, 0))
MAX_CELLS = 250000
MAX_BYTES = 512 * 1024 * 1024
MAX_METADATA = 1024 * 1024
TOL = 1e-9
ARRAY_KEYS = frozenset((
    "H0_m", "H1_m", "H2_m", "boundary_mask", "protected_mask", "escape_level_m",
    "flood_parent", "flood_order", "lake_id", "lake_mask", "lake_stage_m", "lake_area_m2",
    "lake_capacity_m3", "lake_downstream_id", "spill_lake_id", "spill_inside", "spill_outside",
    "spill_stage_m", "spill_width_m", "receiver", "order", "outlet_cells", "outlet_owner",
    "outlet_area_m2", "outlet_type", "contributing_area_m2", "flowline_mask", "dry_channel_mask",
    "accepted_mask", "accepted_outlets", "rejection_code", "candidate_H2_m", "cut_depth_m",
    "cell_cut_volume_m3", "section_cells", "section_offset_m", "section_H0_m", "section_H1_m", "section_H2_m",
))
BOOL_KEYS = frozenset(("boundary_mask", "protected_mask", "lake_mask", "flowline_mask",
                       "dry_channel_mask", "accepted_mask", "accepted_outlets"))
INT_KEYS = frozenset(("flood_parent", "flood_order", "lake_id", "lake_downstream_id", "spill_lake_id",
                      "spill_inside", "spill_outside", "receiver", "order", "outlet_cells", "outlet_owner",
                      "outlet_type", "rejection_code", "section_cells"))
GRID_KEYS = frozenset(("H0_m", "H1_m", "H2_m", "boundary_mask", "protected_mask", "escape_level_m",
                       "lake_id", "lake_mask", "outlet_owner", "contributing_area_m2", "flowline_mask",
                       "dry_channel_mask", "accepted_mask", "rejection_code", "candidate_H2_m",
                       "cut_depth_m", "cell_cut_volume_m3"))


@dataclass(frozen=True)
class GeometryBudget:
    max_cells: int = 250000
    max_bytes: int = 536870912
    max_neighbor_visits: int = 4000000
    max_valley_cut_m: float = 1.0
    max_total_cut_m: float = 2.0
    max_cut_volume_m3: float = 200000.0
    shallow_cut_m: float = 0.25
    channel_area_m2: float = 1000000.0
    min_dry_slope: float = 0.0001

    def __post_init__(self):
        for name, ceiling in (("max_cells", MAX_CELLS), ("max_bytes", MAX_BYTES),
                              ("max_neighbor_visits", 4000000)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("invalid resource budget: " + name)
        for name in ("max_valley_cut_m", "max_total_cut_m", "max_cut_volume_m3",
                     "shallow_cut_m", "channel_area_m2", "min_dry_slope"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError("invalid finite positive budget: " + name)
        if (self.max_valley_cut_m > 1 or self.max_total_cut_m > 2 or
                self.max_cut_volume_m3 > 200000 or self.shallow_cut_m > self.max_total_cut_m):
            raise ValueError("construction exceeds fixed ceiling")


def preflight(shape, budget):
    if not isinstance(budget, GeometryBudget) or len(shape) != 2 or any(type(value) is not int or value < 3 for value in shape):
        raise ValueError("bounded two-dimensional grid required")
    cells = math.prod(shape)
    estimate = cells * 768 + MAX_METADATA
    if cells > budget.max_cells or estimate > budget.max_bytes or cells * 12 > budget.max_neighbor_visits:
        raise ValueError("geometry resource budget exceeded before allocation")
    return {"cells": cells, "estimated_peak_bytes": estimate, "neighbor_visit_bound": cells * 12}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(array):
    digest = hashlib.sha256(array.dtype.str.encode("ascii"))
    digest.update(_json(list(array.shape)).encode("ascii"))
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def window_boundary(shape):
    boundary = np.zeros(shape, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    return boundary


def _neighbors(cell, shape):
    row, column = divmod(int(cell), shape[1])
    for delta_row, delta_column in NEIGHBORS:
        next_row, next_column = row + delta_row, column + delta_column
        if 0 <= next_row < shape[0] and 0 <= next_column < shape[1]:
            yield next_row * shape[1] + next_column


def _flood(height, boundary):
    """Four-neighbor minimax escape certificate with an acyclic parent witness."""
    escape = height.ravel().copy()
    discovered = boundary.ravel().copy()
    parent = np.full(height.size, -1, dtype=np.int64)
    order = np.empty(height.size, dtype=np.int64)
    heap = [(float(escape[cell]), int(cell)) for cell in np.flatnonzero(discovered)]
    heapq.heapify(heap)
    position = 0
    while heap:
        stage, cell = heapq.heappop(heap)
        order[position] = cell
        position += 1
        for neighbor in _neighbors(cell, height.shape):
            if not discovered[neighbor]:
                discovered[neighbor] = True
                escape[neighbor] = max(escape[neighbor], stage)
                parent[neighbor] = cell
                heapq.heappush(heap, (float(escape[neighbor]), neighbor))
    return escape.reshape(height.shape), parent, order


def _topological(receiver):
    donors = np.bincount(receiver[receiver >= 0], minlength=receiver.size)
    pending = deque(np.flatnonzero(donors == 0).tolist())
    order = []
    while pending:
        cell = pending.popleft()
        order.append(cell)
        target = int(receiver[cell])
        if target >= 0:
            donors[target] -= 1
            if donors[target] == 0:
                pending.append(target)
    if len(order) != receiver.size:
        raise ValueError("receiver cycle")
    return np.asarray(order[::-1], dtype=np.int64)


def _lake_geometry(height, escape, parent, flood_order):
    positive = escape > height + TOL
    labels, count = ndimage.label(positive, ndimage.generate_binary_structure(2, 1))
    labels = labels.astype(np.int64)
    rank = np.empty(height.size, dtype=np.int64)
    rank[flood_order] = np.arange(height.size)
    stages = np.zeros(count, dtype=np.float64)
    inside = np.zeros(count, dtype=np.int64)
    outside = np.zeros(count, dtype=np.int64)
    levels = escape.ravel()
    flat_labels = labels.ravel()
    grouped = np.argsort(flat_labels, kind="stable")
    offsets = np.r_[0, np.cumsum(np.bincount(flat_labels, minlength=count + 1))]
    for lake in range(1, count + 1):
        cells = grouped[offsets[lake]:offsets[lake + 1]]
        if np.ptp(levels[cells]) > TOL:
            raise ValueError("positive component spans multiple escape levels")
        stages[lake - 1] = levels[cells[0]]
        exits = cells[flat_labels[parent[cells]] != lake]
        source = int(exits[np.argmin(rank[exits])])
        inside[lake - 1], outside[lake - 1] = source, parent[source]
    return labels, stages, inside, outside


def _route_lakes(height, escape, labels, stages, inside, outside, parent, flood_order):
    receiver = parent.copy()
    rank = np.empty(height.size, dtype=np.int64)
    rank[flood_order] = np.arange(height.size)
    raw = height.ravel()
    flat_labels = labels.ravel()
    for cell in flood_order:
        if parent[cell] < 0 or flat_labels[cell]:
            continue
        candidates = [neighbor for neighbor in _neighbors(cell, height.shape)
                      if rank[neighbor] < rank[cell] and escape.flat[neighbor] <= escape.flat[cell] + TOL]
        receiver[cell] = min(candidates, key=lambda neighbor: (raw[neighbor], rank[neighbor], neighbor))
    seen = np.zeros(height.size, dtype=bool)
    for lake, source in enumerate(inside, 1):
        receiver[source] = outside[lake - 1]
        seen[source] = True
        pending = deque([int(source)])
        while pending:
            cell = pending.popleft()
            for neighbor in _neighbors(cell, height.shape):
                if flat_labels[neighbor] == lake and not seen[neighbor]:
                    seen[neighbor] = True
                    receiver[neighbor] = cell
                    pending.append(neighbor)
    return receiver, _topological(receiver)


def _ownership(receiver, order, boundary, area):
    outlets = np.flatnonzero(boundary.ravel()).astype(np.int64)
    owner = np.full(receiver.size, -1, dtype=np.int64)
    owner[outlets] = np.arange(outlets.size)
    accumulation = np.ones(receiver.size, dtype=np.float64) * area
    for cell in order:
        if receiver[cell] >= 0:
            owner[cell] = owner[receiver[cell]]
    for cell in order[::-1]:
        if receiver[cell] >= 0:
            accumulation[receiver[cell]] += accumulation[cell]
    return outlets, owner, np.bincount(owner, minlength=outlets.size).astype(np.float64) * area, accumulation


def _bed_candidates(height, lake_id, stages, receiver, order, flowline, locked, spacing, budget):
    candidate = height.ravel().copy()
    reasons = np.zeros(height.size, dtype=np.int64)
    dry = flowline & (lake_id.ravel() == 0)
    for cell in order:
        if not dry[cell] or locked.flat[cell]:
            continue
        target = int(receiver[cell])
        proposed = height.flat[cell] - budget.shallow_cut_m
        if target >= 0:
            lake = lake_id.flat[target]
            lower = stages[lake - 1] if lake else candidate[target] + spacing * budget.min_dry_slope
            proposed = max(proposed, lower)
        if proposed > height.flat[cell] + TOL:
            reasons[cell] = 1
        else:
            candidate[cell] = min(height.flat[cell], proposed)
    return candidate, reasons


def prepare_mountain_geometry(height_m, *, spacing_m, origin_m_xz, source_binding,
                              boundary_mask, protected_mask, budget=GeometryBudget()):
    """Prepare once; all areas include complete internal upstream contributions."""
    if not isinstance(height_m, np.ndarray):
        raise ValueError("height must be a resource-checkable numpy array")
    resources = preflight(tuple(height_m.shape), budget)
    if (height_m.dtype != np.dtype("float64") or not np.isfinite(height_m).all() or
            isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or
            not math.isfinite(spacing_m) or not 0 < spacing_m <= 100000 or
            len(origin_m_xz) != 2 or not np.isfinite(origin_m_xz).all() or
            not isinstance(source_binding, dict) or not source_binding):
        raise ValueError("invalid metre source geometry/binding")
    _json(source_binding)
    for mask in (boundary_mask, protected_mask):
        if not isinstance(mask, np.ndarray) or mask.dtype != bool or mask.shape != height_m.shape:
            raise ValueError("explicit boolean masks required")
    if not np.array_equal(boundary_mask, window_boundary(height_m.shape)):
        raise ValueError("v1 requires every window edge explicitly open")
    height = height_m.copy()
    escape, parent, flood_order = _flood(height, boundary_mask)
    labels, stages, inside, outside = _lake_geometry(height, escape, parent, flood_order)
    receiver, order = _route_lakes(height, escape, labels, stages, inside, outside, parent, flood_order)
    outlets, owner, outlet_area, accumulation = _ownership(receiver, order, boundary_mask, spacing_m ** 2)
    flowline = accumulation >= budget.channel_area_m2
    lake_mask = labels > 0
    shore = ndimage.binary_dilation(lake_mask, structure=ndimage.generate_binary_structure(2, 1)) & ~lake_mask
    locked = lake_mask | shore | boundary_mask | protected_mask
    candidate, reasons = _bed_candidates(height, labels, stages, receiver, order, flowline, locked, spacing_m, budget)
    proposed_volume = (height.ravel() - candidate) * spacing_m ** 2
    group_volume = np.bincount(owner, weights=proposed_volume, minlength=outlets.size)
    failed_groups = np.bincount(owner, weights=(reasons > 0).astype(float), minlength=outlets.size) > 0
    lake_groups = np.bincount(owner, weights=lake_mask.ravel().astype(float), minlength=outlets.size) > 0
    selected = np.zeros(outlets.size, dtype=bool)
    spent = 0.0
    for group in np.argsort(-outlet_area, kind="stable"):
        if not lake_groups[group] or failed_groups[group] or group_volume[group] <= 0:
            continue
        if spent + group_volume[group] <= budget.max_cut_volume_m3 + TOL:
            selected[group] = True
            spent += float(group_volume[group])
    accepted = selected[owner]
    reasons[~accepted & (reasons == 0)] = 2
    bed = height.ravel().copy()
    bed[accepted] = candidate[accepted]
    count = stages.size
    lake_area = np.bincount(labels.ravel(), minlength=count + 1)[1:].astype(float) * spacing_m ** 2
    lake_capacity = np.bincount(labels.ravel(), weights=(escape - height).ravel(), minlength=count + 1)[1:] * spacing_m ** 2
    next_lake = np.full(height.size, -1, dtype=np.int64)
    for cell in order:
        target = receiver[cell]
        if target >= 0:
            next_lake[cell] = labels.flat[target] if labels.flat[target] else next_lake[target]
    downstream_lake = next_lake[outside]
    downstream_lake[labels.ravel()[outside] > 0] = labels.ravel()[outside][labels.ravel()[outside] > 0]
    cut = (height.ravel() - bed).reshape(height.shape)
    section_cells = np.flatnonzero(accepted & flowline & ~lake_mask.ravel()).astype(np.int64)
    arrays = {
        "H0_m": height, "H1_m": height.copy(), "H2_m": bed.reshape(height.shape),
        "boundary_mask": boundary_mask.copy(), "protected_mask": protected_mask.copy(),
        "escape_level_m": escape, "flood_parent": parent, "flood_order": flood_order,
        "lake_id": labels, "lake_mask": lake_mask, "lake_stage_m": stages,
        "lake_area_m2": lake_area, "lake_capacity_m3": lake_capacity,
        "lake_downstream_id": downstream_lake, "spill_lake_id": np.arange(1, count + 1, dtype=np.int64),
        "spill_inside": inside, "spill_outside": outside, "spill_stage_m": stages.copy(),
        "spill_width_m": np.full(count, float(spacing_m)), "receiver": receiver, "order": order,
        "outlet_cells": outlets, "outlet_owner": owner.reshape(height.shape),
        "outlet_area_m2": outlet_area, "outlet_type": np.ones(outlets.size, dtype=np.int64),
        "contributing_area_m2": accumulation.reshape(height.shape),
        "flowline_mask": flowline.reshape(height.shape),
        "dry_channel_mask": (flowline & ~lake_mask.ravel()).reshape(height.shape),
        "accepted_mask": accepted.reshape(height.shape), "accepted_outlets": selected,
        "rejection_code": reasons.reshape(height.shape),
        "candidate_H2_m": candidate.reshape(height.shape), "cut_depth_m": cut,
        "cell_cut_volume_m3": cut * spacing_m ** 2, "section_cells": section_cells,
        "section_offset_m": np.array([-spacing_m / 2, 0., spacing_m / 2]),
        "section_H0_m": np.repeat(height.ravel()[section_cells, None], 3, axis=1),
        "section_H1_m": np.repeat(height.ravel()[section_cells, None], 3, axis=1),
        "section_H2_m": np.repeat(bed[section_cells, None], 3, axis=1),
    }
    metadata = {"algorithm": ALGORITHM, "schema": SCHEMA, "spacing_m": float(spacing_m),
                "origin_m_xz": list(map(float, origin_m_xz)), "source_binding": source_binding,
                "H0_sha256": _hash(height), "budget": asdict(budget), "resources": resources,
                "boundary_types": {"1": "external_open_boundary"},
                "scope": "finite_window_truncated_boundary_experiment",
                "lake_semantics": "aggregate_full_spill_equilibrium_capacity_not_initial_connected_water",
                "section_semantics": "piecewise_constant_full_cell_finite_volume_not_subcell_channel",
                "rejection_codes": {"0": "accepted", "1": "dry_slope_requires_fill", "2": "unaccepted_complete_contribution_group"}}
    result = {"arrays": arrays, "metadata": metadata}
    validate_mountain_geometry(result, trusted_height=height_m, source_binding=source_binding)
    return result


def lake_volume_at_stage(result, lake_id, stage_m):
    """Equilibrium capacity V(h), not a claim of initial pool connectivity."""
    arrays = result["arrays"]
    if type(lake_id) is not int or not 1 <= lake_id <= arrays["lake_stage_m"].size or not math.isfinite(stage_m):
        raise ValueError("invalid lake stage query")
    if stage_m > arrays["lake_stage_m"][lake_id - 1] + TOL:
        raise ValueError("query exceeds represented spill level")
    return float(np.maximum(stage_m - arrays["H0_m"][arrays["lake_id"] == lake_id], 0).sum() * result["metadata"]["spacing_m"] ** 2)


def certify_no_cut_groups(result):
    """Independent original-bed static certificate; construction selection is separate."""
    arrays, metadata = result["arrays"], result["metadata"]
    receiver = arrays["receiver"]
    height = arrays["H0_m"].ravel()
    labels = arrays["lake_id"].ravel()
    owner = arrays["outlet_owner"].ravel()
    donors = np.flatnonzero((receiver >= 0) & (labels == 0))
    targets = receiver[donors]
    downstream = height[targets].copy()
    submerged = labels[targets] > 0
    downstream[submerged] = arrays["lake_stage_m"][labels[targets[submerged]] - 1]
    bad = donors[height[donors] < downstream - TOL]
    counts = np.bincount(owner[bad], minlength=arrays["outlet_cells"].size)
    valid = counts == 0
    return {"scope": "original_bed_static_finite_window_no_cut_not_dynamic_single_pool",
            "outlet_valid_mask": valid, "cell_valid_mask": valid[owner].reshape(arrays["H0_m"].shape),
            "dry_uphill_count_by_outlet": counts, "failed_dry_donors": bad,
            "valid_area_m2": float(arrays["outlet_area_m2"][valid].sum()),
            "original_dry_uphill_edges": int(bad.size), "cut_volume_m3": 0.,
            "lake_spill_contract": "uncut_full_D4_cell_edge_at_equilibrium_stage_no_initial_connectivity_claim",
            "source_H0_sha256": metadata["H0_sha256"]}


def _equal(actual, expected, name):
    if actual.shape != np.shape(expected) or not np.array_equal(actual, expected):
        raise ValueError("static geometry mismatch: " + name)


def validate_mountain_geometry(result, *, trusted_height, source_binding):
    """Check static equations/certificates only: no flood, prepare or evolution."""
    arrays, meta = result["arrays"], result["metadata"]
    if set(arrays) != ARRAY_KEYS:
        raise ValueError("fixed geometry schema required")
    if meta["algorithm"] != ALGORITHM or meta["schema"] != SCHEMA or meta["source_binding"] != source_binding:
        raise ValueError("source/algorithm binding mismatch")
    budget = GeometryBudget(**meta["budget"])
    height = arrays["H0_m"]
    resources = preflight(tuple(height.shape), budget)
    if meta["resources"] != resources or len(meta["origin_m_xz"]) != 2 or not np.isfinite(meta["origin_m_xz"]).all():
        raise ValueError("resource or coordinate identity")
    if (meta["lake_semantics"] != "aggregate_full_spill_equilibrium_capacity_not_initial_connected_water"
            or meta["section_semantics"] != "piecewise_constant_full_cell_finite_volume_not_subcell_channel"
            or meta["rejection_codes"] != {"0": "accepted", "1": "dry_slope_requires_fill", "2": "unaccepted_complete_contribution_group"}):
        raise ValueError("geometry semantic label forgery")
    if not np.array_equal(height, trusted_height) or _hash(height) != meta["H0_sha256"]:
        raise ValueError("trusted original H0 mismatch")
    for key, values in arrays.items():
        expected_dtype = np.dtype("bool" if key in BOOL_KEYS else "int64" if key in INT_KEYS else "float64")
        if not isinstance(values, np.ndarray) or values.dtype != expected_dtype or not np.isfinite(values).all():
            raise ValueError("invalid array: " + key)
        if key in GRID_KEYS and values.shape != height.shape:
            raise ValueError("grid shape mismatch: " + key)
    spacing = meta["spacing_m"]
    if not isinstance(spacing, (int, float)) or isinstance(spacing, bool) or not math.isfinite(spacing) or not 0 < spacing <= 100000:
        raise ValueError("invalid spacing")
    if (meta["boundary_types"] != {"1": "external_open_boundary"} or
            meta["scope"] != "finite_window_truncated_boundary_experiment"):
        raise ValueError("boundary semantic forgery")
    boundary = arrays["boundary_mask"]
    _equal(boundary, window_boundary(height.shape), "all explicit boundary")
    for key in ("receiver", "flood_parent", "order", "flood_order", "outlet_owner", "lake_id"):
        if arrays[key].dtype != np.dtype("int64"):
            raise ValueError("integer topology required")
    rank = np.empty(height.size, dtype=np.int64)
    for receiver_key, order_key in (("receiver", "order"), ("flood_parent", "flood_order")):
        receiver, order = arrays[receiver_key], arrays[order_key]
        _equal(np.sort(order), np.arange(height.size), "order permutation")
        if receiver.shape != (height.size,) or (receiver < -1).any() or (receiver >= height.size).any():
            raise ValueError("receiver indices")
        _equal((receiver == -1).reshape(height.shape), boundary, "external terminals")
        rank[order] = np.arange(height.size)
        donors = np.flatnonzero(receiver >= 0)
        targets = receiver[donors]
        if (rank[targets] >= rank[donors]).any() or (np.abs(donors // height.shape[1] - targets // height.shape[1]) + np.abs(donors % height.shape[1] - targets % height.shape[1]) != 1).any():
            raise ValueError("cycle or non-width four-neighbor connection")
    escape = arrays["escape_level_m"]
    if escape.shape != height.shape or (escape < height - TOL).any():
        raise ValueError("invalid escape levels")
    _equal(escape[boundary], height[boundary], "boundary unmodified escape")
    minimum_neighbor = np.full(height.shape, np.inf)
    minimum_neighbor[1:, :] = np.minimum(minimum_neighbor[1:, :], escape[:-1, :])
    minimum_neighbor[:-1, :] = np.minimum(minimum_neighbor[:-1, :], escape[1:, :])
    minimum_neighbor[:, 1:] = np.minimum(minimum_neighbor[:, 1:], escape[:, :-1])
    minimum_neighbor[:, :-1] = np.minimum(minimum_neighbor[:, :-1], escape[:, 1:])
    _equal(escape[~boundary], np.maximum(height, minimum_neighbor)[~boundary], "minimax Bellman equation")
    parent = arrays["flood_parent"]
    donors = np.flatnonzero(parent >= 0)
    _equal(escape.ravel()[donors], np.maximum(height.ravel()[donors], escape.ravel()[parent[donors]]), "escape-to-boundary witness")
    labels, count = ndimage.label(escape > height + TOL, ndimage.generate_binary_structure(2, 1))
    _equal(arrays["lake_id"], labels.astype(np.int64), "four-connected lake labels")
    _equal(arrays["lake_mask"], labels > 0, "lake mask")
    stages = arrays["lake_stage_m"]
    if stages.shape != (count,):
        raise ValueError("lake dimensions")
    flat_labels = labels.ravel()
    wet = flat_labels > 0
    _equal(escape.ravel()[wet], stages[flat_labels[wet] - 1], "lake equilibrium stages")
    _equal(arrays["lake_area_m2"], np.bincount(flat_labels, minlength=count + 1)[1:] * spacing ** 2, "lake area")
    _equal(arrays["lake_capacity_m3"], np.bincount(flat_labels, weights=(escape - height).ravel(), minlength=count + 1)[1:] * spacing ** 2, "capacity not actual storage")
    receiver, order = arrays["receiver"], arrays["order"]
    inside, outside = arrays["spill_inside"], arrays["spill_outside"]
    if inside.shape != (count,) or outside.shape != (count,) or (inside < 0).any() or (outside < 0).any() or (inside >= height.size).any() or (outside >= height.size).any():
        raise ValueError("invalid spill indices")
    _equal(flat_labels[inside], np.arange(1, count + 1), "spill basin")
    _equal(flat_labels[outside], np.zeros(count, dtype=np.int64), "spill outside lake")
    _equal(height.ravel()[outside], stages, "original uncut saddle")
    _equal(receiver[inside], outside, "spill edge")
    _equal(arrays["spill_lake_id"], np.arange(1, count + 1), "spill lake identity")
    _equal(arrays["spill_stage_m"], stages, "spill elevation")
    _equal(arrays["spill_width_m"], np.full(count, spacing), "full-edge spill width")
    lake_donors = np.flatnonzero(wet)
    exits = lake_donors[flat_labels[receiver[lake_donors]] != flat_labels[lake_donors]]
    _equal(np.sort(exits), np.sort(inside), "one canonical spill per equilibrium lake")
    rank[arrays["flood_order"]] = np.arange(height.size)
    grouped = np.argsort(flat_labels, kind="stable")
    offsets = np.r_[0, np.cumsum(np.bincount(flat_labels, minlength=count + 1))]
    for lake in range(1, count + 1):
        cells = grouped[offsets[lake]:offsets[lake + 1]]
        witnesses = cells[flat_labels[parent[cells]] != lake]
        source = int(witnesses[np.argmin(rank[witnesses])])
        if inside[lake - 1] != source or outside[lake - 1] != parent[source]:
            raise ValueError("canonical original saddle witness mismatch")
    next_lake = np.full(height.size, -1, dtype=np.int64)
    for cell in order:
        target = receiver[cell]
        if target >= 0:
            next_lake[cell] = flat_labels[target] if flat_labels[target] else next_lake[target]
    downstream_lake = next_lake[outside]
    downstream_lake[flat_labels[outside] > 0] = flat_labels[outside][flat_labels[outside] > 0]
    _equal(arrays["lake_downstream_id"], downstream_lake, "lake downstream hierarchy")
    if (downstream_lake == np.arange(1, count + 1)).any():
        raise ValueError("lake spill routes back into itself")
    outlets = np.flatnonzero(boundary.ravel())
    owner = arrays["outlet_owner"].ravel()
    area = arrays["outlet_area_m2"]
    accumulation = arrays["contributing_area_m2"].ravel()
    _equal(arrays["outlet_cells"], outlets, "outlet cells")
    if (owner < 0).any() or (owner >= outlets.size).any():
        raise ValueError("invalid outlet ownership")
    _equal(owner[outlets], np.arange(outlets.size), "unique outlet identities")
    donors = np.flatnonzero(receiver >= 0)
    _equal(owner[donors], owner[receiver[donors]], "local complete upstream ownership")
    _equal(area, np.bincount(owner, minlength=outlets.size) * spacing ** 2, "all unique outlet areas")
    _equal(arrays["outlet_type"], np.ones(outlets.size, dtype=np.int64), "external outlet types")
    donor_sum = np.bincount(receiver[donors], weights=accumulation[donors], minlength=height.size)
    _equal(accumulation, donor_sum + spacing ** 2, "local contributing area recurrence")
    _equal(accumulation[outlets], area, "outlet area conservation")
    flowline = accumulation >= budget.channel_area_m2
    _equal(arrays["flowline_mask"], flowline.reshape(height.shape), "channel area threshold")
    _equal(arrays["dry_channel_mask"], (flowline & ~wet).reshape(height.shape), "lake not dry river")
    accepted = arrays["accepted_mask"].ravel()
    selected = arrays["accepted_outlets"]
    _equal(accepted, selected[owner], "whole contribution groups")
    _equal(arrays["H1_m"], height, "unfilled valley H1")
    bed = arrays["H2_m"]
    _equal(arrays["cut_depth_m"], height - bed, "actual cut")
    _equal(arrays["cell_cut_volume_m3"], (height - bed) * spacing ** 2, "unique volume")
    cut = height - bed
    if (cut < -TOL).any() or cut.max() > budget.max_total_cut_m + TOL or cut.sum() * spacing ** 2 > budget.max_cut_volume_m3 + TOL:
        raise ValueError("cut/fill budget")
    shore = ndimage.binary_dilation(wet.reshape(height.shape), structure=ndimage.generate_binary_structure(2, 1)) & ~wet.reshape(height.shape)
    locked = arrays["lake_mask"] | shore | boundary | arrays["protected_mask"]
    _equal(bed[locked], height[locked], "lake, shore, boundary and protection unchanged")
    _equal(bed.ravel()[~accepted], height.ravel()[~accepted], "outside accepted groups unchanged")
    dry_donors = np.flatnonzero(~wet & (receiver >= 0))
    targets = receiver[dry_donors]
    downstream = bed.ravel()[targets].copy()
    wet_targets = flat_labels[targets] > 0
    downstream[wet_targets] = stages[flat_labels[targets[wet_targets]] - 1]
    if (bed.ravel()[dry_donors] < downstream - TOL).any():
        raise ValueError("dry bed or lake-inlet uphill")
    candidate = arrays["candidate_H2_m"].ravel()
    reasons = np.zeros(height.size, dtype=np.int64)
    active = flowline & ~wet & ~locked.ravel()
    active_cells = np.flatnonzero(active)
    active_targets = receiver[active_cells]
    expected = height.ravel()[active_cells] - budget.shallow_cut_m
    has_target = active_targets >= 0
    lower = candidate[np.maximum(active_targets, 0)] + spacing * budget.min_dry_slope
    target_lakes = flat_labels[np.maximum(active_targets, 0)]
    target_wet = target_lakes > 0
    lower[target_wet] = stages[target_lakes[target_wet] - 1]
    expected[has_target] = np.maximum(expected[has_target], lower[has_target])
    failed = expected > height.ravel()[active_cells] + TOL
    reasons[active_cells[failed]] = 1
    expected[failed] = height.ravel()[active_cells[failed]]
    expected = np.minimum(expected, height.ravel()[active_cells])
    _equal(candidate[active_cells], expected, "saved local bounded bed recurrence")
    _equal(candidate[~active], height.ravel()[~active], "inactive candidate unchanged")
    _equal(bed.ravel()[accepted], candidate[accepted], "accepted actual bed")
    if (reasons[accepted] > 0).any():
        raise ValueError("accepted slope failure")
    group_volume = np.bincount(owner, weights=(height.ravel() - candidate) * spacing ** 2, minlength=outlets.size)
    failed_groups = np.bincount(owner, weights=(reasons > 0).astype(float), minlength=outlets.size) > 0
    lake_groups = np.bincount(owner, weights=wet.astype(float), minlength=outlets.size) > 0
    expected_selected = np.zeros(outlets.size, dtype=bool)
    spent = 0.0
    for group in np.argsort(-area, kind="stable"):
        if not lake_groups[group] or failed_groups[group] or group_volume[group] <= 0:
            continue
        if spent + group_volume[group] <= budget.max_cut_volume_m3 + TOL:
            expected_selected[group] = True
            spent += float(group_volume[group])
    _equal(selected, expected_selected, "fixed deterministic area-first budget selection")
    reasons[~accepted & (reasons == 0)] = 2
    _equal(arrays["rejection_code"], reasons.reshape(height.shape), "rejection evidence")
    section_cells = np.flatnonzero(accepted & flowline & ~wet)
    _equal(arrays["section_cells"], section_cells, "section identity")
    _equal(arrays["section_offset_m"], np.array([-spacing / 2, 0., spacing / 2]), "full cell sections")
    for section_key, surface_key in (("section_H0_m", "H0_m"), ("section_H1_m", "H1_m"), ("section_H2_m", "H2_m")):
        _equal(arrays[section_key], np.repeat(arrays[surface_key].ravel()[section_cells, None], 3, axis=1), "shared bed sections")
    return {"accepted_area_m2": float(accepted.sum() * spacing ** 2), "cut_volume_m3": float(cut.sum() * spacing ** 2),
            "lake_capacity_m3": float(arrays["lake_capacity_m3"].sum()), "lake_count": count,
            "total_unique_area_m2": float(area.sum())}


def screen_single_pool_lakes(result, *, min_cells=4, max_event_work=4000000):
    """Screen every elevation event, deterministically; do not assemble dynamics."""
    if type(min_cells) is not int or min_cells < 1 or type(max_event_work) is not int or not 1 <= max_event_work <= 4000000:
        raise ValueError("invalid fixed screening resources")
    arrays = result["arrays"]
    labels = arrays["lake_id"]
    height = arrays["H0_m"]
    groups = ndimage.find_objects(labels)
    decisions = []
    spent = labels.size
    for lake, slices in enumerate(groups, 1):
        mask = labels[slices] == lake
        count = int(mask.sum())
        if count < min_cells:
            decisions.append({"lake_id": lake, "status": "too_small", "cells": count})
            continue
        terrain = height[slices]
        levels = np.unique(terrain[mask])
        work = mask.size * levels.size
        if spent + work > max_event_work:
            decisions.append({"lake_id": lake, "status": "event_resource_limit", "cells": count, "requested_work": work})
            continue
        spent += work
        disconnected = 0
        max_components = 0
        for level in levels:
            _, components = ndimage.label(mask & (terrain <= level), ndimage.generate_binary_structure(2, 1))
            disconnected += int(components > 1)
            max_components = max(max_components, components)
        source = int(arrays["spill_inside"][lake - 1])
        outside = int(arrays["spill_outside"][lake - 1])
        path = [outside]
        seen = {outside}
        flags = [] if disconnected == 0 else ["multiple_initial_pools"]
        while arrays["receiver"][path[-1]] >= 0:
            if spent >= max_event_work:
                flags.append("path_resource_limit")
                break
            spent += 1
            target = int(arrays["receiver"][path[-1]])
            if target in seen:
                flags.append("cycle")
                break
            if labels.flat[target] > 0:
                flags.append("downstream_lake_requires_cascade")
                break
            if height.flat[target] > height.flat[path[-1]] + TOL:
                flags.append("downstream_uphill")
                break
            seen.add(target)
            path.append(target)
        if height.flat[path[-1]] >= arrays["lake_stage_m"][lake - 1] - TOL:
            flags.append("downstream_not_strictly_lower")
        status = flags[0] if flags else "single_pool_static_candidate"
        decisions.append({"lake_id": lake, "status": status, "reason_flags": flags, "cells": count,
                          "all_elevation_events": int(levels.size), "disconnected_events": disconnected,
                          "max_wet_components": max_components, "event_work": work,
                          "bbox_cells": int(mask.size), "path_steps": len(path) - 1,
                          "capacity_m3": float(arrays["lake_capacity_m3"][lake - 1]),
                          "spill_inside": source, "spill_outside": outside, "downstream_path": path})
    return {"max_event_work": max_event_work, "event_work": spent, "decisions": decisions}


def save_mountain_geometry(path, result, *, trusted_height, source_binding):
    """Atomic hard-link publication; no overwrite, including racing writers."""
    validate_mountain_geometry(result, trusted_height=trusted_height, source_binding=source_binding)
    arrays = result["arrays"]
    manifest = {"metadata": result["metadata"], "hashes": {key: _hash(value) for key, value in arrays.items()}}
    payload = _json(manifest).encode("ascii")
    if len(payload) > MAX_METADATA:
        raise ValueError("metadata resource budget")
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = tempfile.mkstemp(prefix=".mountain-geometry-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez_compressed(stream, manifest=np.frombuffer(payload, dtype=np.uint8), **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def load_mountain_geometry(path, *, trusted_height, source_binding):
    """Static cold loading with external source trust and pre-allocation checks."""
    with open(path, "rb") as stream:
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if len(names) != len(set(names)) or set(names) != {key + ".npy" for key in ARRAY_KEYS} | {"manifest.npy"}:
                raise ValueError("unexpected archive members")
            if sum(member.file_size for member in members) > MAX_BYTES:
                raise ValueError("archive decompression resource budget")
            headers = {}
            for member in members:
                with archive.open(member) as array_stream:
                    version = np.lib.format.read_magic(array_stream)
                    if version != (1, 0):
                        raise ValueError("unsupported NPY header")
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(array_stream)
                    if dtype.hasobject or dtype.kind not in "bifu" or math.prod(shape) * dtype.itemsize + array_stream.tell() != member.file_size:
                        raise ValueError("unsafe array header")
                    if fortran:
                        raise ValueError("noncanonical Fortran archive")
                    headers[member.filename[:-4]] = (shape, dtype)
                    if member.filename == "manifest.npy":
                        if dtype != np.dtype("uint8") or len(shape) != 1 or shape[0] > MAX_METADATA:
                            raise ValueError("manifest resource budget")
                    elif member.filename == "H0_m.npy":
                        preflight(tuple(shape), GeometryBudget())
            grid_shape = headers["H0_m"][0]
            cells = math.prod(grid_shape)
            lakes = headers["lake_stage_m"][0]
            outlets = headers["outlet_cells"][0]
            sections = headers["section_cells"][0]
            if any(len(shape) != 1 or not 0 <= shape[0] <= cells for shape in (lakes, outlets, sections)):
                raise ValueError("bounded topology header dimensions")
            lake_keys = {"lake_stage_m", "lake_area_m2", "lake_capacity_m3", "lake_downstream_id",
                         "spill_lake_id", "spill_inside", "spill_outside", "spill_stage_m", "spill_width_m"}
            outlet_keys = {"outlet_cells", "outlet_area_m2", "outlet_type", "accepted_outlets"}
            for key in ARRAY_KEYS:
                shape, dtype = headers[key]
                expected_dtype = np.dtype("bool" if key in BOOL_KEYS else "int64" if key in INT_KEYS else "float64")
                expected_shape = grid_shape if key in GRID_KEYS else lakes if key in lake_keys else outlets if key in outlet_keys else sections if key == "section_cells" else (3,) if key == "section_offset_m" else (sections[0], 3) if key.startswith("section_H") else (cells,)
                if dtype != expected_dtype or shape != expected_shape:
                    raise ValueError("schema header mismatch: " + key)
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            manifest = json.loads(archive["manifest"].tobytes().decode("ascii"))
            if set(archive.files) != set(manifest["hashes"]) | {"manifest"}:
                raise ValueError("manifest member mismatch")
            arrays = {key: archive[key].copy() for key in manifest["hashes"]}
    for key, values in arrays.items():
        if _hash(values) != manifest["hashes"][key]:
            raise ValueError("integrity hash mismatch")
    result = {"arrays": arrays, "metadata": manifest["metadata"]}
    validate_mountain_geometry(result, trusted_height=trusted_height, source_binding=source_binding)
    for key, values in arrays.items():
        arrays[key] = np.frombuffer(values.tobytes(), dtype=values.dtype).reshape(values.shape)
    return result
