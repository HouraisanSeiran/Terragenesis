"""Bounded finite-window lake/reach coupling; never certifies a natural outlet."""

import math

import numpy as np
from terrain_pipeline.irregular_grid import segments_clear

from terrain_pipeline.lake_routing import LakeRoutingRecipe, evaluate_lake_routing
from terrain_pipeline.mountain_runoff_routing import _order, preflight
from terrain_pipeline.common_infra import identity, readonly, save_bundle, load_bundle, validate_source
from terrain_pipeline.rainfall_runoff import (
    ARRAY_KEYS as RUNOFF_KEYS, STATE_KEYS as RUNOFF_STATES,
    _hash, _json, _strict_json, simulate_rainfall_runoff, validate_rainfall_runoff_result,
)


SCHEMA = "mountain-lake-coupling-v1"
BOUNDARIES = {"external_open_boundary", "closed_terminal", "ocean_open_boundary"}
MAX_BYTES = 768 * 1024 * 1024
BASE_KEYS = {"height_m", "hydrology_mask", "cell_owner", "receiver", "anchor_node", "node_downstream", "tau_s",
    "cell_node", "allocation_counts", "area_m2", "node_order", "lateral_volume_m3", "incoming_volume_m3",
    "land_allocation_counts", "surface_allocation_counts", "surface_rain_volume_m3", "surface_evaporation_volume_m3",
    "outflow_volume_m3", "storage_m3", "lake_stage_m", "lake_loss_volume_m3", "boundary_nodes",
    "boundary_volume_m3", "total_boundary_volume_m3"}
META_KEYS = {"schema", "status", "source_identity", "source_metadata", "geometry_identity", "geometry_passed",
    "node_kind", "node_boundary_type", "boundary_policy", "runoff_metadata", "lake_evidence", "river_stage_solved",
    "selection_metadata", "selection_identity", "rain_support", "lake_evaporation_mm_h", "surface_scope",
    "hydrological_closure_certified"}


def terminal_ownership(receiver, calculation_mask):
    """Global partition with no dynamic node allocation, including every edge outlet."""
    if (not isinstance(receiver, np.ndarray) or receiver.ndim != 2 or receiver.dtype != np.int64 or
            not 1 <= receiver.size <= 250_000 or not isinstance(calculation_mask, np.ndarray) or
            calculation_mask.shape != receiver.shape or calculation_mask.dtype != bool or not calculation_mask.any()):
        raise ValueError("invalid bounded receiver/domain")
    flat = receiver.ravel()
    order = _order(flat)
    moving = np.flatnonzero(flat >= 0)
    targets = flat[moving]
    active = calculation_mask.ravel()
    if (active[moving] & ~active[targets]).any():
        raise ValueError("active receiver leaves calculation domain without explicit terminal")
    participating = active[moving]
    if not segments_clear(moving[participating], targets[participating], calculation_mask).all():
        raise ValueError("receiver segment crosses outside the calculation domain")
    owner = np.full(flat.size, -1, np.int64)
    terminals = np.flatnonzero((flat == -1) & active)
    owner[terminals] = terminals
    for current in order[::-1]:
        if active[current] and flat[current] >= 0:
            owner[current] = owner[flat[current]]
    if (owner[active] < 0).any():
        raise ValueError("unmapped contributing cell")
    counts = np.bincount(owner[active], minlength=flat.size)[terminals]
    return {"terminal_owner": readonly(owner.reshape(receiver.shape)),
            "terminal_flat": readonly(terminals), "contributing_counts": readonly(counts)}


def contribution_mask(receiver, calculation_mask, terminal_flat):
    partition = terminal_ownership(receiver, calculation_mask)
    if type(terminal_flat) is not int or terminal_flat not in partition["terminal_flat"]:
        raise ValueError("terminal not in global partition")
    mask = partition["terminal_owner"] == terminal_flat
    return readonly(mask), {
        "terminal_flat": terminal_flat, "contributing_cells": int(mask.sum()),
        "full_receiver_sha256": _hash(receiver), "full_domain_sha256": _hash(calculation_mask),
        "terminal_owner_sha256": _hash(partition["terminal_owner"]),
        "mask_sha256": _hash(mask), "upstream_complete_within_finite_window": True,
        "hydrological_closure_certified": False}


def local_allocation(receiver, anchor_node, cell_owner, calculation_mask, node_downstream, *, spacing_m, hrus):
    """First lake/reach encountered, never an accumulated upstream discharge input."""
    terminal_ownership(receiver, calculation_mask)
    shape = receiver.shape
    for value in (anchor_node, cell_owner):
        if not isinstance(value, np.ndarray) or value.shape != shape or value.dtype != np.int64:
            raise ValueError("typed anchor/HRU grid required")
    if (not isinstance(node_downstream, np.ndarray) or node_downstream.ndim != 1 or
            node_downstream.dtype != np.int64 or not 1 <= node_downstream.size <= 2048 or
            type(hrus) is not int or not 1 <= hrus <= 256 or
            isinstance(spacing_m, bool) or not isinstance(spacing_m, (int, float)) or
            not math.isfinite(spacing_m) or not 0 < spacing_m <= 100000):
        raise ValueError("invalid nodes/HRUs/spacing")
    _order(node_downstream)
    active = calculation_mask.ravel()
    anchor = anchor_node.ravel()
    hru = cell_owner.ravel()
    if ((anchor < -1).any() or (anchor >= node_downstream.size).any() or
            (anchor[~active] != -1).any() or (hru[~active] != -1).any() or
            (hru[active] < 0).any() or (hru[active] >= hrus).any()):
        raise ValueError("invalid node or unique HRU ownership")
    if set(anchor[active & (anchor >= 0)].tolist()) != set(range(node_downstream.size)):
        raise ValueError("every dynamic node needs an explicit geometric anchor")
    receiver_flat = receiver.ravel()
    cell_node = anchor.copy()
    for current in _order(receiver_flat)[::-1]:
        if active[current] and cell_node[current] < 0 and receiver_flat[current] >= 0:
            cell_node[current] = cell_node[receiver_flat[current]]
    if (cell_node[active] < 0).any():
        raise ValueError("unmapped local contributing area")
    for current in np.flatnonzero(active & (anchor >= 0)):
        target = receiver_flat[current]
        node = anchor[current]
        if target == -1:
            if node_downstream[node] != -1:
                raise ValueError("terminal anchor/node topology mismatch")
        elif cell_node[target] != node and node_downstream[node] != cell_node[target]:
            raise ValueError("node topology disagrees with first downstream anchor")
    counts = np.bincount(cell_node[active] * hrus + hru[active],
        minlength=node_downstream.size * hrus).reshape(node_downstream.size, hrus)
    area = np.bincount(hru[active], minlength=hrus).astype(np.float64) * spacing_m**2
    if (area <= 0).any():
        raise ValueError("empty HRU")
    return {"cell_node": readonly(cell_node.reshape(shape)), "allocation_counts": readonly(counts),
            "area_m2": readonly(area), "node_order": readonly(_order(node_downstream))}


def _topology(source, topology, cell_owner, hrus, selection=None):
    validate_source(source)
    required = {"receiver", "anchor_node", "node_downstream", "node_kind", "node_boundary_type",
                "tau_s", "source_identity", "geometry_identity", "geometry_passed", "boundary_policy"}
    if set(topology) != required or topology["source_identity"] != source["identity_sha256"]:
        raise ValueError("same-source explicit topology required")
    if (type(topology["geometry_passed"]) is not bool or
            not isinstance(topology["geometry_identity"], str) or len(topology["geometry_identity"]) != 64 or
            topology["boundary_policy"] != source["metadata"]["boundary"]["policy"]):
        raise ValueError("geometry/boundary evidence required")
    downstream = topology["node_downstream"]
    count = downstream.size
    for key in ("node_kind", "node_boundary_type"):
        if not isinstance(topology[key], list) or len(topology[key]) != count:
            raise ValueError("invalid node records")
    if any(kind not in {"river", "lake", "terminal"} for kind in topology["node_kind"]):
        raise ValueError("invalid node kind")
    tau = topology["tau_s"]
    if (not isinstance(tau, np.ndarray) or tau.shape != (count,) or tau.dtype != np.float64 or
            not np.isfinite(tau).all() or (tau <= 0).any() or (tau > 1e12).any()):
        raise ValueError("finite positive river residence times required")
    for node, target in enumerate(downstream):
        boundary = topology["node_boundary_type"][node]
        if (target == -1 and boundary not in BOUNDARIES) or (target >= 0 and boundary is not None):
            raise ValueError("explicit terminal type required")
        if boundary == "ocean_open_boundary":
            raise ValueError("natural coast evidence is not supported by this finite-window adapter")
        if topology["node_kind"][node] == "terminal" and target != -1:
            raise ValueError("terminal cannot have downstream node")
    mask = source["arrays"]["hydrology_mask"] if selection is None else validate_selection(source, topology, selection)
    return local_allocation(topology["receiver"], topology["anchor_node"], cell_owner,
        mask, downstream, spacing_m=source["metadata"]["spacing_m"], hrus=hrus)


def geometry_binding(source, topology, geometry, selection=None):
    """Bind externally accepted B payload, not caller acceptance booleans."""
    if not isinstance(geometry, dict) or set(geometry) != {"arrays", "metadata"}:
        raise ValueError("externally accepted geometry payload required")
    arrays = geometry["arrays"]
    from terrain_pipeline.mountain_depression_geometry import validate_mountain_geometry, certify_no_cut_groups

    binding = geometry["metadata"].get("source_binding")
    if not isinstance(binding, dict) or binding.get("source_identity") != source["identity_sha256"]:
        raise ValueError("geometry source binding identity required")
    if (geometry["metadata"]["spacing_m"] != source["metadata"]["spacing_m"] or
            geometry["metadata"]["origin_m_xz"] != source["metadata"]["origin_m_xz"] or
            source["metadata"]["boundary"]["policy"] != "all_edges_open"):
        raise ValueError("geometry/source grid or boundary policy mismatch")
    validate_mountain_geometry(geometry, trusted_height=source["arrays"]["height_m"], source_binding=binding)
    if identity(arrays, geometry["metadata"]) != topology["geometry_identity"]:
        raise ValueError("external geometry payload identity mismatch")
    if not np.array_equal(arrays["H0_m"], source["arrays"]["height_m"]):
        raise ValueError("geometry H0 differs from trusted source")
    if not np.array_equal(arrays["receiver"].reshape(topology["receiver"].shape), topology["receiver"]):
        raise ValueError("geometry receiver mismatch")
    mask = source["arrays"]["hydrology_mask"] if selection is None else validate_selection(source, topology, selection)
    no_cut = certify_no_cut_groups(geometry)
    if not no_cut["cell_valid_mask"][mask].all():
        raise ValueError("selected contribution domain lacks no-cut static geometry certificate")
    lake_cells = mask & (arrays["lake_id"] > 0)
    for cell in np.flatnonzero(lake_cells):
        node = int(topology["anchor_node"].flat[cell])
        if node < 0 or topology["node_kind"][node] != "lake":
            raise ValueError("every source lake cell must map to a lake node, never a river")
    for node, kind in enumerate(topology["node_kind"]):
        if kind == "lake":
            labels = np.unique(arrays["lake_id"][topology["anchor_node"] == node])
            if labels.size != 1 or labels[0] <= 0:
                raise ValueError("lake node must represent one explicit geometry basin")
    return True


def build_group_topology(source, geometry, group):
    """Keep every dry route cell and every lake in a complete contribution group."""
    arrays = geometry["arrays"]
    if type(group) is not int or not 0 <= group < arrays["outlet_cells"].size:
        raise ValueError("invalid group index")
    receiver = arrays["receiver"].reshape(source["arrays"]["height_m"].shape)
    terminal = int(arrays["outlet_cells"][group])
    mask, proof = contribution_mask(receiver, source["arrays"]["hydrology_mask"], terminal)
    if not np.array_equal(mask, arrays["outlet_owner"] == group):
        raise ValueError("independent global owner disagrees with selected geometry group")
    selection = make_selection(source, receiver, mask, proof=proof)
    labels = arrays["lake_id"]
    lakes = np.unique(labels[mask])
    lakes = lakes[lakes > 0]
    dry_cells = np.flatnonzero(mask.ravel() & (labels.ravel() == 0))
    count = lakes.size + dry_cells.size
    if not 1 <= count <= 2048:
        raise ValueError("complete group exceeds dynamic node budget; no terminal dropping")
    anchor = np.full(mask.shape, -1, np.int64)
    kinds = []
    lake_nodes = {}
    for node, lake in enumerate(lakes):
        anchor[mask & (labels == lake)] = node
        lake_nodes[int(lake)] = node
        kinds.append("lake")
    anchor.ravel()[dry_cells] = np.arange(lakes.size, count)
    kinds.extend(["river"] * dry_cells.size)
    downstream = np.full(count, -1, np.int64)
    tau = np.full(count, source["metadata"]["spacing_m"], np.float64)
    for lake, node in lake_nodes.items():
        downstream[node] = int(anchor.flat[arrays["spill_outside"][lake - 1]])
        if downstream[node] < 0:
            raise ValueError("lake spill exits complete group unexpectedly")
    for cell in dry_cells:
        target = int(receiver.flat[cell])
        if target >= 0:
            downstream[anchor.flat[cell]] = anchor.flat[target]
    boundaries = ["external_open_boundary" if target < 0 else None for target in downstream]
    topology = {"receiver": receiver.copy(), "anchor_node": anchor, "node_downstream": downstream,
        "node_kind": kinds, "node_boundary_type": boundaries, "tau_s": tau,
        "source_identity": source["identity_sha256"], "geometry_identity": identity(arrays, geometry["metadata"]),
        "geometry_passed": True, "boundary_policy": "all_edges_open"}
    geometry_binding(source, topology, geometry, selection)
    return topology, selection, lake_nodes


def group_lake_specs(source, geometry, topology, lake_nodes, *, steps, coefficient=1.7):
    """Uncalibrated broad-crested weir Q=C*full-cell width*head**1.5, bounded by shore."""
    if not 0 < coefficient <= 3 or type(steps) is not int or not 1 <= steps <= 3000:
        raise ValueError("invalid explicit weir parameters")
    arrays = geometry["arrays"]
    height = source["arrays"]["height_m"]
    specs = {}
    for lake, node in lake_nodes.items():
        basin = arrays["lake_id"] == lake
        outside = int(arrays["spill_outside"][lake - 1])
        spill = np.array(divmod(outside, height.shape[1]), np.int64)
        path_flat = [outside]
        while arrays["receiver"][path_flat[-1]] >= 0:
            target = int(arrays["receiver"][path_flat[-1]])
            if arrays["lake_id"].flat[target] > 0:
                path_flat.append(target)
                break
            path_flat.append(target)
        path = np.column_stack(np.unravel_index(path_flat, height.shape)).astype(np.int64)
        shore = np.zeros(height.shape, bool)
        for row, column in np.argwhere(basin):
            for delta_row, delta_column in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbor = row + delta_row, column + delta_column
                if not basin[neighbor]:
                    shore[neighbor] = True
        shore[tuple(spill)] = False
        spill_stage = float(height[tuple(spill)])
        max_stage = float(height[shore].min())
        if max_stage <= spill_stage:
            raise ValueError("no unique-sill positive headroom; multi-sill modeling required")
        stages = np.linspace(spill_stage, max_stage, 65)
        flow = coefficient * source["metadata"]["spacing_m"] * (stages - spill_stage)**1.5
        legal = np.zeros(height.shape, bool)
        legal[tuple(path[-1])] = True
        specs[node] = {"basin_mask": basin, "legal_spill_grid_zx": spill,
            "downstream_path_grid_zx": path, "domain_mask": source["arrays"]["hydrology_mask"],
            "protected_mask": arrays["protected_mask"], "legal_outlet_mask": legal,
            "single_pool_certified": True, "geometry_identity": topology["geometry_identity"],
            "recipe": {"initial_stage_m": float(height[basin].min()), "loss_m3_s": (0.,) * steps,
                "rating_stage_m": tuple(stages), "rating_outflow_m3_s": tuple(flow),
                "max_stage_m": max_stage, "volume_abs_tolerance_m3": 1e-9, "volume_rel_tolerance": 1e-12}}
    return specs


def make_selection(source, receiver, mask, *, proof):
    """Selection identity is separate from the immutable full height-source identity."""
    validate_source(source)
    if (not isinstance(mask, np.ndarray) or mask.dtype != bool or mask.shape != source["arrays"]["height_m"].shape or
            not mask.any() or (mask & ~source["arrays"]["hydrology_mask"]).any()):
        raise ValueError("invalid selection domain")
    arrays = {"mask": readonly(mask)}
    metadata = {"source_identity": source["identity_sha256"], "receiver_sha256": _hash(receiver),
                "proof": _strict_json(_json(proof)), "hydrological_closure_certified": False}
    return {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def validate_selection(source, topology, selection):
    arrays, metadata = selection["arrays"], selection["metadata"]
    if (set(arrays) != {"mask"} or selection["identity_sha256"] != identity(arrays, metadata) or
            metadata["source_identity"] != source["identity_sha256"] or
            metadata["receiver_sha256"] != _hash(topology["receiver"]) or
            metadata["hydrological_closure_certified"] is not False):
        raise ValueError("selection/source/topology binding mismatch")
    mask = arrays["mask"]
    if mask.dtype != bool or mask.shape != source["arrays"]["height_m"].shape or not mask.any():
        raise ValueError("invalid selected domain")
    if (mask & ~source["arrays"]["hydrology_mask"]).any():
        raise ValueError("selection exceeds source calculation domain")
    proof = metadata["proof"]
    receiver = topology["receiver"].ravel()
    _order(receiver)
    active = source["arrays"]["hydrology_mask"].ravel()
    selected = mask.ravel()
    moving = np.flatnonzero(active & (receiver >= 0))
    if not active[receiver[moving]].all():
        raise ValueError("full source donor exits declared calculation domain")
    if (selected[moving] != selected[receiver[moving]]).any():
        raise ValueError("selection drops upstream contributions or downstream path")
    terminals = np.flatnonzero(selected & (receiver == -1))
    if (terminals.size != 1 or proof.get("terminal_flat") != int(terminals[0]) or
            proof.get("contributing_cells") != int(selected.sum()) or
            proof.get("mask_sha256") != _hash(mask) or
            proof.get("full_receiver_sha256") != _hash(topology["receiver"]) or
            proof.get("full_domain_sha256") != _hash(source["arrays"]["hydrology_mask"]) or
            proof.get("upstream_complete_within_finite_window") is not True or
            proof.get("hydrological_closure_certified") is not False):
        raise ValueError("selection complete-contribution certificate mismatch")
    return mask


def single_pool_proof(height, basin, spill, path, domain, protected, legal, *, max_stage_m):
    """Every strict sublevel event must be connected, including intermediate saddles."""
    shape = height.shape
    for mask in (basin, domain, protected, legal):
        if not isinstance(mask, np.ndarray) or mask.shape != shape or mask.dtype != bool:
            raise ValueError("typed single-pool geometry masks required")
    if not basin.any() or (basin & (~domain | protected)).any():
        raise ValueError("pool outside legal unprotected domain")
    if basin[0].any() or basin[-1].any() or basin[:, 0].any() or basin[:, -1].any():
        raise ValueError("pool touches truncated boundary")
    points = np.asarray(path)
    sill = np.asarray(spill)
    if (sill.shape != (2,) or sill.dtype.kind not in "iu" or points.ndim != 2 or
            points.shape[1] != 2 or points.dtype.kind not in "iu" or not 2 <= len(points) <= height.size or
            (points < 0).any() or (points[:, 0] >= shape[0]).any() or (points[:, 1] >= shape[1]).any() or
            (sill < 0).any() or sill[0] >= shape[0] or sill[1] >= shape[1] or
            not np.array_equal(points[0], sill)):
        raise ValueError("invalid explicit spill/path")
    spill_point = tuple(sill)
    if basin[spill_point] or not domain[spill_point] or protected[spill_point]:
        raise ValueError("spill must be outside basin inside legal domain")
    neighbors = ((-1, 0), (1, 0), (0, -1), (0, 1))
    if not any(0 <= sill[0] + delta_row < shape[0] and 0 <= sill[1] + delta_column < shape[1] and
            basin[sill[0] + delta_row, sill[1] + delta_column] for delta_row, delta_column in neighbors):
        raise ValueError("spill must touch basin")
    rows, columns = points.T
    if (not legal[tuple(points[-1])] or not domain[rows, columns].all() or
            protected[rows, columns].any() or basin[rows, columns].any() or
            np.any(np.abs(np.diff(points, axis=0)).sum(axis=1) != 1) or
            len(set(map(tuple, points))) != len(points) or
            (np.diff(height[rows, columns]) > 0).any() or
            height[tuple(points[-1])] >= height[spill_point]):
        raise ValueError("invalid downstream sill/path/closure evidence")
    if not math.isfinite(max_stage_m) or max_stage_m < height[spill_point]:
        raise ValueError("invalid maximum pool stage")
    if (height[basin] >= height[spill_point]).any():
        raise ValueError("basin includes dry spill-height cells")
    for row, column in np.argwhere(basin):
        for delta_row, delta_column in neighbors:
            neighbor = (row + delta_row, column + delta_column)
            if not basin[neighbor] and neighbor != spill_point and height[neighbor] < max_stage_m:
                raise ValueError("unmodeled low shore/saddle")
    cells = np.flatnonzero(basin.ravel())
    ordered = cells[np.argsort(height.ravel()[cells], kind="stable")]
    parent = np.full(height.size, -1, np.int64)
    active = np.zeros(height.size, bool)
    components = 0

    def root(cell):
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    position = 0
    events = 0
    while position < ordered.size:
        level = height.flat[ordered[position]]
        end = position + 1
        while end < ordered.size and height.flat[ordered[end]] == level:
            end += 1
        for cell in ordered[position:end]:
            active[cell] = True
            parent[cell] = cell
            components += 1
            row, column = divmod(int(cell), shape[1])
            for delta_row, delta_column in neighbors:
                next_row, next_column = row + delta_row, column + delta_column
                if 0 <= next_row < shape[0] and 0 <= next_column < shape[1]:
                    neighbor = next_row * shape[1] + next_column
                    if active[neighbor]:
                        first, second = root(int(cell)), root(neighbor)
                        if first != second:
                            parent[second] = first
                            components -= 1
        events += 1
        if components != 1:
            raise ValueError(f"disconnected sublevel pool at event {events}, above {level} m")
        position = end
    return {"all_sublevel_events_connected": True, "events_checked": events,
            "basin_cells": int(cells.size), "basin_sha256": _hash(basin)}


def couple_rainfall(source, topology, cell_owner, rain_mm_h, *, dt_s, geometry,
                   parameters=None, lakes=None, selection=None, surface_rain=False,
                   lake_evaporation_mm_h=0.0):
    """Solve DAG in topological order, lakes via existing bounded single-pool solver."""
    if not isinstance(rain_mm_h, np.ndarray) or rain_mm_h.ndim != 2:
        raise ValueError("rain [step,HRU] required")
    steps, hrus = rain_mm_h.shape
    preflight(steps, source["arrays"]["height_m"].size, hrus, topology["node_downstream"].size)
    mapping = _topology(source, topology, cell_owner, hrus, selection)
    if not topology["geometry_passed"]:
        return {"status": "diagnostic_geometry_not_passed", "source_identity": source["identity_sha256"],
                "geometry_identity": topology["geometry_identity"], "mapping": mapping,
                "dynamic_water_solved": False}
    geometry_binding(source, topology, geometry, selection)
    mask = source["arrays"]["hydrology_mask"] if selection is None else selection["arrays"]["mask"]
    count = topology["node_downstream"].size
    lake_specs = {} if lakes is None else lakes
    expected_lakes = {node for node, kind in enumerate(topology["node_kind"]) if kind == "lake"}
    if set(lake_specs) != expected_lakes:
        raise ValueError("every lake needs explicit single-pool geometry/rating")
    if len(expected_lakes) * source["arrays"]["height_m"].size > 2_000_000:
        raise ValueError("retained single-pool geometry resource budget exceeded")
    if type(surface_rain) is not bool or isinstance(lake_evaporation_mm_h, bool) or not isinstance(lake_evaporation_mm_h, (int, float)) or not math.isfinite(lake_evaporation_mm_h) or not 0 <= lake_evaporation_mm_h <= 1000:
        raise ValueError("invalid surface rainfall/evaporation forcing")
    if not surface_rain and lake_evaporation_mm_h != 0:
        raise ValueError("surface evaporation requires explicit surface rainfall partition")
    land_counts = mapping["allocation_counts"].copy()
    lake_counts = np.zeros_like(land_counts)
    if surface_rain:
        for node in expected_lakes:
            basin = topology["anchor_node"] == node
            labels = cell_owner[basin]
            lake_counts[node] = np.bincount(labels, minlength=hrus)
        land_counts -= lake_counts
    cell_area = source["metadata"]["spacing_m"]**2
    land_area = land_counts.sum(axis=0).astype(np.float64) * cell_area
    if (land_area <= 0).any():
        raise ValueError("surface partition requires every HRU to retain positive land area")
    runoff = simulate_rainfall_runoff(rain_mm_h, land_area, dt_s=dt_s,
        source_id=source["identity_sha256"], parameters=parameters)
    fractions = land_counts * cell_area / land_area
    lateral = runoff["local_q_m3_s"] @ fractions.T * dt_s
    direct_rain = rain_mm_h @ (lake_counts * cell_area).T / 1000. * dt_s / 3600.
    evaporation = lake_counts.sum(axis=1)[None, :] * cell_area / 1000. * lake_evaporation_mm_h * dt_s / 3600.
    evaporation = np.repeat(evaporation, steps, axis=0)
    lateral += direct_rain
    incoming = lateral.copy()
    outflow = np.zeros((steps, count), np.float64)
    storage = np.zeros((steps + 1, count), np.float64)
    lake_stage = np.full((steps + 1, count), np.nan, np.float64)
    losses = np.zeros((steps, count), np.float64)
    lake_evidence = {}
    lake_arrays = {}
    for node in mapping["node_order"]:
        node = int(node)
        kind = topology["node_kind"][node]
        target = int(topology["node_downstream"][node])
        if kind == "lake":
            spec = lake_specs[node]
            required = {"basin_mask", "legal_spill_grid_zx", "downstream_path_grid_zx",
                        "domain_mask", "protected_mask", "legal_outlet_mask", "recipe",
                        "single_pool_certified", "geometry_identity"}
            if (set(spec) != required or spec["single_pool_certified"] is not True or
                    spec["geometry_identity"] != topology["geometry_identity"] or
                    not isinstance(spec["recipe"], dict)):
                raise ValueError("single-pool geometry evidence required; merged dry saddles forbidden")
            if (spec["basin_mask"].shape != topology["anchor_node"].shape or
                    not np.array_equal(spec["basin_mask"], topology["anchor_node"] == node)):
                raise ValueError("lake basin must match all node anchors exactly")
            if (not np.array_equal(spec["domain_mask"], source["arrays"]["hydrology_mask"]) or
                    not np.array_equal(spec["protected_mask"], geometry["arrays"]["protected_mask"])):
                raise ValueError("lake domain/protection must match trusted source geometry")
            _check_legal_mask(spec["legal_outlet_mask"], spec["downstream_path_grid_zx"])
            recipe_values = dict(spec["recipe"], dt_s=dt_s,
                inflow_m3_s=tuple(incoming[:, node] / dt_s))
            recipe_values["loss_m3_s"] = tuple(np.asarray(spec["recipe"]["loss_m3_s"]) + evaporation[:, node] / dt_s)
            recipe = LakeRoutingRecipe(**recipe_values)
            proof = single_pool_proof(source["arrays"]["height_m"], spec["basin_mask"],
                spec["legal_spill_grid_zx"], spec["downstream_path_grid_zx"], spec["domain_mask"],
                spec["protected_mask"], spec["legal_outlet_mask"], max_stage_m=recipe.max_stage_m)
            _check_pool_path(topology["receiver"], spec["downstream_path_grid_zx"], spec["legal_outlet_mask"],
                anchor_node=topology["anchor_node"], node_kind=topology["node_kind"], current_node=node,
                node_downstream=topology["node_downstream"])
            for key in ("domain_mask", "protected_mask", "legal_outlet_mask"):
                lake_arrays[f"lake_{node}_{key}"] = spec[key].copy()
            spacing = source["metadata"]["spacing_m"]
            origin = source["metadata"]["origin_m_xz"]
            lake = evaluate_lake_routing(source["arrays"]["height_m"], spec["basin_mask"],
                spec["legal_spill_grid_zx"], spacing, spacing, source["identity_sha256"], recipe,
                spec["downstream_path_grid_zx"], spec["domain_mask"], spec["protected_mask"],
                spec["legal_outlet_mask"], origin[0], origin[1], "sea_zero_m")
            if not lake["scenario_feasible"]:
                return {"status": "diagnostic_lake_failed", "source_identity": source["identity_sha256"],
                    "geometry_identity": topology["geometry_identity"], "failed_node": node,
                    "lake_failure": lake, "dynamic_water_solved": False}
            outflow[:, node] = lake["arrays"]["step_outflow_volume_m3"]
            storage[:, node] = lake["arrays"]["storage_m3"]
            lake_stage[:, node] = lake["arrays"]["stage_m"]
            losses[:, node] = lake["arrays"]["step_loss_volume_m3"]
            lake_evidence[str(node)] = {"identity_sha256": lake["identity_sha256"],
                "summary": lake["summary"], "input": lake["input"],
                "basin_sha256": _hash(spec["basin_mask"]), "single_pool_proof": proof,
                "pool_geometry": {key: value.tolist() for key, value in lake["arrays"].items()
                    if key in {"legal_spill_grid_zx", "downstream_path_grid_zx"}}}
        elif topology["node_boundary_type"][node] == "closed_terminal":
            storage[1:, node] = np.cumsum(incoming[:, node])
        else:
            ratio = dt_s / topology["tau_s"][node]
            for step in range(steps):
                storage[step + 1, node] = (storage[step, node] + incoming[step, node]) / (1 + ratio)
                outflow[step, node] = ratio * storage[step + 1, node]
        if target >= 0:
            incoming[:, target] += outflow[:, node]
    for node in expected_lakes:
        path = lake_specs[node]["downstream_path_grid_zx"]
        receiver_node = int(topology["anchor_node"][tuple(path[-1])])
        if receiver_node >= 0 and topology["node_kind"][receiver_node] == "lake":
            sill = float(source["arrays"]["height_m"][tuple(path[0])])
            submerged = np.flatnonzero(lake_stage[:, receiver_node] > sill + 1e-9)
            if submerged.size:
                return {"status": "diagnostic_receiving_pool_submerges_free_weir",
                    "source_identity": source["identity_sha256"], "geometry_identity": topology["geometry_identity"],
                    "failed_node": node, "receiving_node": receiver_node, "failed_state": int(submerged[0]),
                    "sill_stage_m": sill, "receiving_stage_m": float(lake_stage[submerged[0], receiver_node]),
                    "dynamic_water_solved": False, "whole_system_prefix_valid": False,
                    "limitation": "independent DAG trajectories are not a committed coupled prefix under tailwater"}
    boundary_nodes = np.flatnonzero((topology["node_downstream"] < 0) & np.array([
        boundary == "external_open_boundary" for boundary in topology["node_boundary_type"]]))
    arrays = {"height_m": source["arrays"]["height_m"],
        "hydrology_mask": mask, "cell_owner": cell_owner,
        **{key: topology[key] for key in ("receiver", "anchor_node", "node_downstream", "tau_s")},
        **mapping, "lateral_volume_m3": lateral, "incoming_volume_m3": incoming,
        "land_allocation_counts": land_counts, "surface_allocation_counts": lake_counts,
        "surface_rain_volume_m3": direct_rain, "surface_evaporation_volume_m3": evaporation,
        "outflow_volume_m3": outflow, "storage_m3": storage, "lake_stage_m": lake_stage,
        "lake_loss_volume_m3": losses, "boundary_nodes": boundary_nodes,
        "boundary_volume_m3": outflow[:, boundary_nodes],
        "total_boundary_volume_m3": outflow[:, boundary_nodes].sum(axis=1)}
    arrays.update(lake_arrays)
    arrays.update({"runoff_" + key: value for key, value in runoff.items() if key != "metadata"})
    metadata = _strict_json(_json({"schema": SCHEMA, "status": "finite_window_engineering_scenario",
        "source_identity": source["identity_sha256"], "source_metadata": source["metadata"],
        "geometry_identity": topology["geometry_identity"], "geometry_passed": True,
        "node_kind": topology["node_kind"], "node_boundary_type": topology["node_boundary_type"],
        "boundary_policy": topology["boundary_policy"], "runoff_metadata": runoff["metadata"],
        "lake_evidence": lake_evidence, "river_stage_solved": False,
        "selection_metadata": None if selection is None else selection["metadata"],
        "selection_identity": None if selection is None else selection["identity_sha256"],
        "rain_support": "fixed_lake_footprint_direct_rain" if surface_rain else "fixed_land_conceptual_runoff_all_cells",
        "lake_evaporation_mm_h": float(lake_evaporation_mm_h),
        "surface_scope": "fixed_full_basin_footprint_even_when_dry; prescribed_evaporation_dry_deficit_fails; no_dynamic_wet_area",
        "hydrological_closure_certified": False}))
    result = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_coupling(result)
    result["arrays"] = {key: readonly(value) for key, value in arrays.items()}
    return result


def _equal(actual, expected, name, *, atol=1e-8, rtol=2e-11):
    if not np.allclose(actual, expected, atol=atol, rtol=rtol, equal_nan=True):
        raise ValueError("coupling semantic mismatch: " + name)


def _check_pool_path(receiver, path, legal, *, anchor_node, node_kind, current_node, node_downstream):
    points = np.asarray(path)
    flat = points[:, 0] * receiver.shape[1] + points[:, 1]
    if not np.array_equal(receiver.ravel()[flat[:-1]], flat[1:]):
        raise ValueError("lake downstream path must follow same-source topology receiver")
    if not legal[tuple(points[-1])]:
        raise ValueError("lake path must reach an explicit destination")
    endpoint_node = int(anchor_node.flat[flat[-1]])
    for cell in flat[:-1]:
        node = int(anchor_node.flat[cell])
        if node >= 0 and node_kind[node] == "lake":
            raise ValueError("downstream path may only enter a receiving lake at its endpoint")
    if receiver.ravel()[flat[-1]] != -1:
        if endpoint_node < 0 or node_kind[endpoint_node] != "lake" or endpoint_node == current_node:
            raise ValueError("lake path must end at a topology terminal or distinct receiving lake")
    path_nodes = anchor_node.ravel()[flat]
    previous = current_node
    for node in path_nodes:
        node = int(node)
        if node < 0:
            continue
        if node != previous:
            if int(node_downstream[previous]) != node:
                raise ValueError("lake path node cascade disagrees with DAG")
            previous = node


def _check_legal_mask(legal, path):
    expected = np.zeros(legal.shape, bool)
    expected[tuple(np.asarray(path)[-1])] = True
    if legal.dtype != bool or not np.array_equal(legal, expected):
        raise ValueError("legal destination mask must contain exactly the explicit path endpoint")


def _free_weir_tailwater(sill_stage_m, receiving_stage_m):
    if not np.isfinite(receiving_stage_m).all() or (receiving_stage_m > sill_stage_m + 1e-9).any():
        raise ValueError("receiving_pool_submerges_free_weir")


def validate_coupling(result, *, source=None, topology=None, geometry=None, selection=None):
    """Static equations only: no preparation, inference or dynamic solver replay."""
    arrays, meta = result["arrays"], result["metadata"]
    if (set(meta) != META_KEYS or meta["schema"] != SCHEMA or meta["geometry_passed"] is not True or
            meta["status"] != "finite_window_engineering_scenario" or meta["river_stage_solved"] is not False or
            meta["hydrological_closure_certified"] is not False or
            result["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("coupling identity/status mismatch")
    expected_masks = {f"lake_{node}_{key}" for node, kind in enumerate(meta["node_kind"]) if kind == "lake"
        for key in ("domain_mask", "protected_mask", "legal_outlet_mask")}
    if set(arrays) != BASE_KEYS | {"runoff_" + key for key in RUNOFF_KEYS} | expected_masks:
        raise ValueError("unexpected coupling array schema")
    _coupling_headers(dict({key: (value.shape, value.dtype) for key, value in arrays.items()},
                           manifest=((1,), np.dtype("uint8"))))
    runoff = {key[7:]: value for key, value in arrays.items() if key.startswith("runoff_")}
    runoff["metadata"] = meta["runoff_metadata"]
    validate_rainfall_runoff_result(runoff)
    steps, hrus = runoff["local_q_m3_s"].shape
    count = arrays["node_downstream"].size
    preflight(steps, arrays["height_m"].size, hrus, count)
    if source is not None:
        validate_source(source)
        if meta["source_identity"] != source["identity_sha256"] or meta["source_metadata"] != source["metadata"]:
            raise ValueError("external trusted source mismatch")
        if _hash(arrays["height_m"]) != _hash(source["arrays"]["height_m"]):
            raise ValueError("external source height mismatch")
        if selection is None:
            if meta["selection_identity"] is not None or _hash(arrays["hydrology_mask"]) != _hash(source["arrays"]["hydrology_mask"]):
                raise ValueError("external source array mismatch")
        else:
            validate_selection(source, topology, selection)
            if (meta["selection_identity"] != selection["identity_sha256"] or
                    meta["selection_metadata"] != selection["metadata"] or
                    _hash(arrays["hydrology_mask"]) != _hash(selection["arrays"]["mask"])):
                raise ValueError("external selection mismatch")
    if topology is not None:
        if meta["geometry_identity"] != topology["geometry_identity"] or topology["geometry_passed"] is not True:
            raise ValueError("external geometry mismatch")
        for key in ("receiver", "anchor_node", "node_downstream", "tau_s"):
            if _hash(arrays[key]) != _hash(topology[key]):
                raise ValueError("external topology array mismatch")
        for key in ("node_kind", "node_boundary_type", "boundary_policy"):
            if meta[key] != topology[key]:
                raise ValueError("external topology metadata mismatch")
    if geometry is not None:
        if source is None or topology is None:
            raise ValueError("source/topology required with external geometry")
        geometry_binding(source, topology, geometry, selection)
        for node, kind in enumerate(meta["node_kind"]):
            if kind == "lake":
                if (not np.array_equal(arrays[f"lake_{node}_domain_mask"], source["arrays"]["hydrology_mask"]) or
                        not np.array_equal(arrays[f"lake_{node}_protected_mask"], geometry["arrays"]["protected_mask"])):
                    raise ValueError("saved lake domain/protection differs from external source geometry")
    flat_receiver = arrays["receiver"].ravel()
    _order(flat_receiver)
    terminal_ownership(arrays["receiver"], arrays["hydrology_mask"])
    _equal(arrays["node_order"], _order(arrays["node_downstream"]), "saved DAG order", atol=0, rtol=0)
    active = arrays["hydrology_mask"].ravel()
    saved_node = arrays["cell_node"].ravel()
    anchor = arrays["anchor_node"].ravel()
    hru = arrays["cell_owner"].ravel()
    if ((saved_node[active] < 0).any() or (saved_node[active] >= count).any() or
            (saved_node[~active] != -1).any() or (anchor[~active] != -1).any() or
            (hru[active] < 0).any() or (hru[active] >= hrus).any() or (hru[~active] != -1).any()):
        raise ValueError("invalid saved unique ownership")
    anchors = active & (anchor >= 0)
    if (anchor[anchors] >= count).any() or (anchor < -1).any():
        raise ValueError("invalid saved anchors")
    _equal(saved_node[anchors], anchor[anchors], "saved anchor ownership", atol=0, rtol=0)
    for current in np.flatnonzero(active):
        target = int(flat_receiver[current])
        if target < 0:
            if anchor[current] < 0 or arrays["node_downstream"][anchor[current]] != -1:
                raise ValueError("unanchored terminal")
        else:
            if not active[target]:
                raise ValueError("saved receiver exits active domain")
            if anchor[current] < 0:
                if saved_node[current] != saved_node[target]:
                    raise ValueError("saved first-node recurrence failed")
            elif saved_node[target] != anchor[current] and arrays["node_downstream"][anchor[current]] != saved_node[target]:
                raise ValueError("saved anchor DAG mismatch")
    counts = np.bincount(saved_node[active] * hrus + hru[active], minlength=count * hrus).reshape(count, hrus)
    area = np.bincount(hru[active], minlength=hrus).astype(np.float64) * meta["source_metadata"]["spacing_m"]**2
    _equal(arrays["allocation_counts"], counts, "saved HRU/node intersection counts", atol=0, rtol=0)
    _equal(arrays["area_m2"], area, "saved HRU area", atol=0, rtol=0)
    land_counts = counts.copy()
    surface_counts = np.zeros_like(counts)
    if meta["rain_support"] == "fixed_lake_footprint_direct_rain":
        for node, kind in enumerate(meta["node_kind"]):
            if kind == "lake":
                labels = arrays["cell_owner"][arrays["anchor_node"] == node]
                surface_counts[node] = np.bincount(labels, minlength=hrus)
        land_counts -= surface_counts
    elif meta["rain_support"] != "fixed_land_conceptual_runoff_all_cells":
        raise ValueError("unknown rainfall support")
    cell_area = meta["source_metadata"]["spacing_m"]**2
    land_area = land_counts.sum(axis=0).astype(np.float64) * cell_area
    _equal(arrays["land_allocation_counts"], land_counts, "unique land rainfall support", atol=0, rtol=0)
    _equal(arrays["surface_allocation_counts"], surface_counts, "unique surface rainfall support", atol=0, rtol=0)
    _equal(runoff["area_m2"], land_area, "runoff land HRU areas", atol=0, rtol=0)
    dt = runoff["metadata"]["dt_s"]
    surface_rain = runoff["rain_mm_h"] @ (surface_counts * cell_area).T / 1000. * dt / 3600.
    surface_evap = np.repeat(surface_counts.sum(axis=1)[None, :] * cell_area / 1000. *
        meta["lake_evaporation_mm_h"] * dt / 3600., steps, axis=0)
    _equal(arrays["surface_rain_volume_m3"], surface_rain, "direct surface rain")
    _equal(arrays["surface_evaporation_volume_m3"], surface_evap, "prescribed surface evaporation")
    lateral = runoff["local_q_m3_s"] @ (land_counts * cell_area / land_area).T * dt + surface_rain
    _equal(arrays["lateral_volume_m3"], lateral, "fresh area allocation")
    incoming = lateral.copy()
    storage = arrays["storage_m3"]
    outflow = arrays["outflow_volume_m3"]
    losses = arrays["lake_loss_volume_m3"]
    if storage.shape != (steps + 1, count) or arrays["lake_stage_m"].shape != storage.shape:
        raise ValueError("invalid state shape")
    for value in (storage, outflow, losses, arrays["incoming_volume_m3"]):
        if value.dtype != np.float64 or not np.isfinite(value).all() or (value < 0).any():
            raise ValueError("invalid nonnegative finite water")
    if outflow.shape != (steps, count) or losses.shape != outflow.shape:
        raise ValueError("invalid flux shape")
    for node, target in enumerate(arrays["node_downstream"]):
        if target >= 0:
            incoming[:, target] += outflow[:, node]
    _equal(arrays["incoming_volume_m3"], incoming, "internal transfer exactly once")
    for node, kind in enumerate(meta["node_kind"]):
        if kind == "lake":
            evidence = meta["lake_evidence"][str(node)]
            recipe = evidence["input"]["recipe"]
            if (evidence["input"]["source_identity"] != meta["source_identity"] or
                    evidence["input"]["spacing_x_m"] != meta["source_metadata"]["spacing_m"] or
                    evidence["input"]["spacing_z_m"] != meta["source_metadata"]["spacing_m"] or
                    evidence["input"]["origin_x_m"] != meta["source_metadata"]["origin_m_xz"][0] or
                    evidence["input"]["origin_z_m"] != meta["source_metadata"]["origin_m_xz"][1] or
                    evidence["input"]["vertical_datum"] != "sea_zero_m" or recipe["dt_s"] != dt):
                raise ValueError("saved lake source/grid/time binding mismatch")
            stage = arrays["lake_stage_m"][:, node]
            basin = arrays["anchor_node"] == node
            proof = single_pool_proof(arrays["height_m"], basin,
                np.array(evidence["pool_geometry"]["legal_spill_grid_zx"], np.int64),
                np.array(evidence["pool_geometry"]["downstream_path_grid_zx"], np.int64),
                arrays[f"lake_{node}_domain_mask"], arrays[f"lake_{node}_protected_mask"],
                arrays[f"lake_{node}_legal_outlet_mask"], max_stage_m=recipe["max_stage_m"])
            if proof != evidence["single_pool_proof"]:
                raise ValueError("saved single-pool proof mismatch")
            sill = evidence["pool_geometry"]["legal_spill_grid_zx"]
            if recipe["rating_stage_m"][0] != arrays["height_m"][tuple(sill)] or recipe["rating_outflow_m3_s"][0] != 0:
                raise ValueError("saved rating must start at measured sill with zero discharge")
            _equal(np.array(recipe["inflow_m3_s"])*dt, incoming[:, node], "saved supplied lake inflow")
            _check_legal_mask(arrays[f"lake_{node}_legal_outlet_mask"],
                np.array(evidence["pool_geometry"]["downstream_path_grid_zx"], np.int64))
            _check_pool_path(arrays["receiver"], np.array(evidence["pool_geometry"]["downstream_path_grid_zx"], np.int64),
                arrays[f"lake_{node}_legal_outlet_mask"], anchor_node=arrays["anchor_node"],
                node_kind=meta["node_kind"], current_node=node, node_downstream=arrays["node_downstream"])
            endpoint = evidence["pool_geometry"]["downstream_path_grid_zx"][-1]
            receiving = int(arrays["anchor_node"][tuple(endpoint)])
            if receiving >= 0 and meta["node_kind"][receiving] == "lake":
                spill = evidence["pool_geometry"]["legal_spill_grid_zx"]
                _free_weir_tailwater(arrays["height_m"][tuple(spill)], arrays["lake_stage_m"][:, receiving])
            if _hash(basin) != evidence["basin_sha256"] or not np.isfinite(stage).all():
                raise ValueError("lake basin/stage mismatch")
            floors = arrays["height_m"][basin]
            area = meta["source_metadata"]["spacing_m"]**2
            volume = np.array([np.maximum(level - floors, 0).sum() * area for level in stage])
            tolerance = recipe["volume_abs_tolerance_m3"]
            relative = recipe["volume_rel_tolerance"]
            _equal(storage[:, node], volume, "lake V(h)", atol=tolerance, rtol=relative)
            if (stage > recipe["max_stage_m"]).any() or (stage > recipe["rating_stage_m"][-1]).any():
                raise ValueError("lake rating extrapolation")
            expected_out = np.interp(stage[1:], recipe["rating_stage_m"], recipe["rating_outflow_m3_s"], left=0) * dt
            _equal(outflow[:, node], expected_out, "lake rating", atol=tolerance, rtol=relative)
            _equal(losses[:, node], np.array(recipe["loss_m3_s"]) * dt, "lake supplied loss")
            _equal(storage[0, node], np.maximum(recipe["initial_stage_m"] - floors, 0).sum() * area,
                "lake initial volume", atol=tolerance, rtol=relative)
        else:
            if not np.isnan(arrays["lake_stage_m"][:, node]).all():
                raise ValueError("linear reach must not display fabricated stage")
            _equal(storage[0, node], 0., "zero initial river/terminal storage")
            _equal(losses[:, node], 0., "no implicit river losses")
            if meta["node_boundary_type"][node] == "closed_terminal":
                _equal(outflow[:, node], 0., "closed terminal outflow")
            else:
                _equal(storage[1:, node], (storage[:-1, node] + incoming[:, node]) /
                    (1 + dt / arrays["tau_s"][node]), "river backward Euler")
                _equal(outflow[:, node], storage[1:, node] * dt / arrays["tau_s"][node], "river release")
    residual = incoming - outflow - losses - np.diff(storage, axis=0)
    scale = np.maximum.reduce((incoming, outflow, storage[:-1], storage[1:], np.ones_like(outflow)))
    tolerance = 1e-8 + scale * 2e-10
    if (np.abs(residual) > tolerance).any():
        raise ValueError("individual lake/reach balance failed")
    boundary_nodes = np.flatnonzero((arrays["node_downstream"] < 0) & np.array([
        value == "external_open_boundary" for value in meta["node_boundary_type"]]))
    _equal(arrays["boundary_nodes"], boundary_nodes, "boundary identifiers", atol=0, rtol=0)
    _equal(arrays["boundary_volume_m3"], outflow[:, boundary_nodes], "each outlet contribution")
    boundary = outflow[:, boundary_nodes].sum(axis=1)
    _equal(arrays["total_boundary_volume_m3"], boundary, "total boundary")
    rain = runoff["rain_volume_m3"].sum(axis=1) + surface_rain.sum(axis=1)
    et = runoff["et_volume_m3"].sum(axis=1) + losses.sum(axis=1)
    change = runoff["storage_change_m3"].sum(axis=1) + np.diff(storage, axis=0).sum(axis=1)
    joint = rain - et - boundary - change
    allowed = tolerance.sum(axis=1) + 1e-8
    if (np.abs(joint) > allowed).any() or np.abs(joint).sum() > allowed.sum():
        raise ValueError("joint rain-soil-lake-river-boundary balance failed")
    return {"max_node_residual_m3": float(np.abs(residual).max()),
            "max_joint_interval_residual_m3": float(np.abs(joint).max()),
            "sum_absolute_joint_residual_m3": float(np.abs(joint).sum()),
            "total_boundary_volume_m3": float(boundary.sum()),
            "outlet_volume_m3": {str(int(node)): float(outflow[:, node].sum()) for node in boundary_nodes},
            "boundary_condition_comparison": "separate_boundary_experiment"}


def save_coupling(path, result):
    save_bundle(path, result, validator=validate_coupling)


def load_coupling(path, *, expected_sha256, source, topology, geometry, selection=None):
    return load_bundle(path, expected_sha256=expected_sha256, max_bytes=MAX_BYTES,
        header_validator=_coupling_headers,
        validator=lambda result: validate_coupling(result, source=source, topology=topology,
            geometry=geometry, selection=selection))


def _coupling_headers(headers):
    shape, dtype = headers.get("height_m", ((), np.dtype("O")))
    rain_shape, rain_dtype = headers.get("runoff_rain_mm_h", ((), np.dtype("O")))
    node_shape, node_dtype = headers.get("node_downstream", ((), np.dtype("O")))
    if (len(shape) != 2 or dtype != np.float64 or len(rain_shape) != 2 or rain_dtype != np.float64 or
            len(node_shape) != 1 or node_dtype != np.int64):
        raise ValueError("invalid typed coupling allocation headers")
    steps, hrus = rain_shape
    nodes = node_shape[0]
    preflight(steps, math.prod(shape), hrus, nodes)
    lake_mask_keys = set(headers) - BASE_KEYS - {"runoff_" + key for key in RUNOFF_KEYS} - {"manifest"}
    lake_nodes = set()
    for key in lake_mask_keys:
        parts = key.split("_", 2)
        if len(parts) != 3 or parts[0] != "lake" or not parts[1].isdigit() or parts[2] not in {
                "domain_mask", "protected_mask", "legal_outlet_mask"}:
            raise ValueError("unknown coupling archive member")
        node = int(parts[1])
        if not 0 <= node < nodes or str(node) != parts[1]:
            raise ValueError("invalid retained lake node")
        lake_nodes.add(node)
    expected_masks = {f"lake_{node}_{key}" for node in lake_nodes
        for key in ("domain_mask", "protected_mask", "legal_outlet_mask")}
    if lake_mask_keys != expected_masks or len(lake_nodes) * math.prod(shape) > 2_000_000:
        raise ValueError("retained lake mask count budget/schema mismatch")
    if set(headers) != BASE_KEYS | {"runoff_" + key for key in RUNOFF_KEYS} | expected_masks | {"manifest"}:
        raise ValueError("missing coupling archive members")
    manifest_shape, manifest_dtype = headers["manifest"]
    if manifest_dtype != np.uint8 or len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 1_048_576:
        raise ValueError("manifest allocation budget")
    grid_types = {"height_m": "float64", "hydrology_mask": "bool", "cell_owner": "int64",
        "receiver": "int64", "anchor_node": "int64", "cell_node": "int64"}
    for key, expected in grid_types.items():
        if headers.get(key) != (shape, np.dtype(expected)):
            raise ValueError("coupling grid header mismatch")
    for key in ("lateral_volume_m3", "incoming_volume_m3", "outflow_volume_m3", "lake_loss_volume_m3",
                "surface_rain_volume_m3", "surface_evaporation_volume_m3"):
        if headers.get(key) != ((steps, nodes), np.dtype("float64")):
            raise ValueError("coupling flux header mismatch")
    for key in ("storage_m3", "lake_stage_m"):
        if headers.get(key) != ((steps + 1, nodes), np.dtype("float64")):
            raise ValueError("coupling state header mismatch")
    for key in ("allocation_counts", "land_allocation_counts", "surface_allocation_counts"):
        if headers[key] != ((nodes, hrus), np.dtype("int64")):
            raise ValueError("allocation header mismatch")
    for key in ("tau_s", "node_order", "area_m2", "total_boundary_volume_m3"):
        expected_shape = (hrus,) if key == "area_m2" else (steps,) if key == "total_boundary_volume_m3" else (nodes,)
        expected_dtype = np.dtype("int64" if key == "node_order" else "float64")
        if headers[key] != (expected_shape, expected_dtype):
            raise ValueError("coupling vector header mismatch")
    boundary_shape, boundary_dtype = headers["boundary_nodes"]
    if len(boundary_shape) != 1 or not 0 <= boundary_shape[0] <= nodes or boundary_dtype != np.int64:
        raise ValueError("boundary node header mismatch")
    if headers["boundary_volume_m3"] != ((steps, boundary_shape[0]), np.dtype("float64")):
        raise ValueError("boundary flux header mismatch")
    for key, (entry_shape, entry_dtype) in headers.items():
        if key.startswith("lake_") and key.endswith("_mask"):
            if entry_shape != shape or entry_dtype != bool:
                raise ValueError("lake retained mask header mismatch")
        if key.startswith("runoff_"):
            name = key[7:]
            expected = (hrus,) if name == "area_m2" else (steps + 1, hrus) if name in {
                "soil_mm", "fast_mm", "slow_mm"} else (steps, hrus)
            if entry_shape != expected or entry_dtype != np.float64:
                raise ValueError("runoff retained header mismatch")
