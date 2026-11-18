"""One-round D4 morphology heuristic with an explicit internal sediment ledger."""

from collections import deque
import math

import numpy as np

from terrain_pipeline.geology import LITHOLOGY_MAX_CELLS as MAX_CELLS, _material_bundle as _bundle, _material_check_identity as _check_identity, _load_bundle, _mask, _parameters, _material_positive as _positive, _save_bundle, _material_shape as _shape, _validate_cold_material


ALGORITHM = "td-d4-single-round-water-material-sediment-v1"
DEFAULT_PARAMETERS = {"erosion_scale_m": 0.15, "reference_volume_m3": 1000.0,
                      "reference_duration_s": 3600.0, "transport_ratio": 0.002,
                      "max_deposit_depth_m": 4.0, "max_work_cells": MAX_CELLS,
                      "engineering_open_boundary_cell_ids": []}


def _config(parameters, shape):
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown morphology parameters")
    result = {**DEFAULT_PARAMETERS, **supplied}
    for name in ("erosion_scale_m", "transport_ratio", "max_deposit_depth_m"):
        result[name] = _positive(result[name], name, allow_zero=True)
    for name in ("reference_volume_m3", "reference_duration_s"):
        result[name] = _positive(result[name], name)
    budget = result["max_work_cells"]
    if not isinstance(budget, (int, np.integer)) or isinstance(budget, (bool, np.bool_)) or not 0 < budget <= MAX_CELLS or math.prod(shape) > budget:
        raise ValueError("morphology work budget exceeded")
    result["max_work_cells"] = int(budget)
    terminals = result["engineering_open_boundary_cell_ids"]
    if any(not isinstance(cell, (int, np.integer)) or isinstance(cell, (bool, np.bool_)) or not 0 <= cell < math.prod(shape) for cell in terminals):
        raise ValueError("invalid boundary cell id")
    if len(set(terminals)) != len(terminals):
        raise ValueError("duplicate boundary declaration")
    result["engineering_open_boundary_cell_ids"] = sorted(map(int, terminals))
    return result


def _water(values, shape, name):
    result = np.asarray(values)
    if result.shape not in (shape, (math.prod(shape),)) or result.dtype.kind not in "fiu":
        raise ValueError(name + " must be numeric and same-shape or flat")
    result = result.astype(np.float64).reshape(shape)
    if not np.isfinite(result).all() or np.any(result < 0):
        raise ValueError(name + " must be finite nonnegative")
    return result


def _graph(height, valid, receiver, protected, wet):
    count = height.size
    if receiver.shape != (count,) or receiver.dtype.kind not in "iu":
        raise ValueError("receiver must be flat integer D4 array")
    if np.any(receiver < -1) or np.any(receiver >= count):
        raise ValueError("receiver outside domain")
    receiver = receiver.astype(np.int64)
    valid_flat = valid.ravel()
    if np.any(receiver[~valid_flat] != -1):
        raise ValueError("unknown cells cannot route")
    sources = np.flatnonzero(valid_flat & (receiver >= 0))
    targets = receiver[sources]
    if np.any(~valid_flat[targets]):
        raise ValueError("receiver crosses unknown")
    source_rows, source_cols = np.divmod(sources, height.shape[1])
    target_rows, target_cols = np.divmod(targets, height.shape[1])
    if np.any(np.abs(source_rows - target_rows) + np.abs(source_cols - target_cols) != 1):
        raise ValueError("receiver requires explicit D4 face")
    if np.any(height.ravel()[targets] > height.ravel()[sources]):
        raise ValueError("receiver uphill: no legal original-bed descent")
    active = wet.ravel()[sources]
    if np.any(active & (protected.ravel()[sources] | protected.ravel()[targets])):
        raise ValueError("active morphology path crosses protected cell")
    indegree = np.bincount(targets, minlength=count)
    queue = deque(np.flatnonzero(valid_flat & (indegree == 0)).tolist())
    order = []
    while queue:
        source = queue.popleft()
        order.append(source)
        target = receiver[source]
        if target >= 0:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(int(target))
    if len(order) != np.count_nonzero(valid_flat):
        raise ValueError("receiver cycle")
    return receiver, order, sources, targets


def generate_morphology(height_m, valid_mask, receiver, routed_volume_m3, wet_duration_s,
                        *, spacing_m, materials, parameters=None, candidate_kind="breach"):
    """Return an immutable independent candidate; never rebuild or advance hydrology."""
    height = np.asarray(height_m)
    shape = _shape(height.shape)
    if height.dtype.kind not in "fiu":
        raise ValueError("height must be numeric")
    height = height.astype(np.float64)
    valid = _mask(valid_mask, shape, "valid_mask")
    if valid_mask is None or not np.isfinite(height[valid]).all() or np.isinf(height).any():
        raise ValueError("valid height must be finite; unknown may be NaN")
    spacing = _positive(spacing_m, "spacing_m")
    area = spacing ** 2
    if not math.isfinite(area) or area == 0:
        raise ValueError("cell area outside numerical budget")
    config = _config(parameters, shape)
    if candidate_kind not in ("breach", "deposition"):
        raise ValueError("unknown morphology candidate kind")
    _validate_cold_material(materials)
    if tuple(materials["metadata"]["shape"]) != shape or materials["metadata"]["spacing_m"] != spacing:
        raise ValueError("material grid mismatch")
    material_arrays = materials["arrays"]
    material_config = materials["metadata"]["parameters"]
    protected = material_arrays["protected_mask"]
    volume = _water(routed_volume_m3, shape, "routed_volume_m3")
    duration = _water(wet_duration_s, shape, "wet_duration_s")
    if np.any(volume[~valid] != 0) or np.any(duration[~valid] != 0):
        raise ValueError("unknown cells cannot receive routed water")
    wet = (volume > 0) & (duration > 0)
    receiver, order, sources, targets = _graph(height, valid, np.asarray(receiver), protected, wet)
    open_mask = np.zeros(shape, bool)
    for cell in config["engineering_open_boundary_cell_ids"]:
        row, col = divmod(cell, shape[1])
        if not valid[row, col] or protected[row, col] or receiver[cell] != -1 or (row not in (0, shape[0] - 1) and col not in (0, shape[1] - 1)):
            raise ValueError("engineering outlet must be valid nonprotected boundary terminal")
        open_mask[row, col] = True
    slope = np.zeros(height.size)
    slope[sources] = (height.ravel()[sources] - height.ravel()[targets]) / spacing
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        potential = config["erosion_scale_m"] * material_arrays["erodibility"] * material_arrays["weak_path_preference"]
        potential = potential * np.log1p(volume / config["reference_volume_m3"])
        potential = potential * (-np.expm1(-duration / config["reference_duration_s"])) * np.sqrt(slope.reshape(shape))
    if not np.isfinite(potential).all():
        raise ValueError("erosion potential exceeds numerical budget")
    erosion = np.where(valid & ~protected & wet, np.minimum(potential, material_arrays["erodible_thickness_m"]), 0.0)
    source_geometry = erosion * area
    source_solid = source_geometry * (1 - material_config["source_porosity"])
    source_mass = source_solid * material_config["solid_density_kg_m3"]
    incoming = np.zeros(height.size)
    transported = np.zeros(height.size)
    deposited = np.zeros(height.size)
    stored = np.zeros(height.size)
    exported = np.zeros(height.size)
    residual = np.zeros(height.size)
    capacity = np.where(wet, config["transport_ratio"] * volume, 0).ravel()
    deposit_limit_solid = config["max_deposit_depth_m"] * area * (1 - material_config["deposit_porosity"])
    if not np.isfinite(capacity).all() or not math.isfinite(deposit_limit_solid) or not np.isfinite(source_mass).all():
        raise ValueError("sediment quantity exceeds numerical budget")
    for source in order:
        available = incoming[source] + source_solid.ravel()[source]
        target = receiver[source]
        movable = min(available, capacity[source])
        if target >= 0:
            if movable > 0 and (protected.ravel()[source] or protected.ravel()[target]):
                raise ValueError("sediment path crosses protected cell")
            transported[source] = movable
            incoming[target] += movable
        elif open_mask.ravel()[source]:
            exported[source] = movable
        else:
            movable = 0.0
        remainder = max(0.0, available - movable)
        if candidate_kind == "deposition" and incoming[source] > 0 and not protected.ravel()[source]:
            deposited[source] = min(remainder, incoming[source], deposit_limit_solid)
        stored[source] = remainder - deposited[source]
        residual[source] = available - transported[source] - exported[source] - deposited[source] - stored[source]
    deposited = deposited.reshape(shape)
    deposit_geometry = deposited / (1 - material_config["deposit_porosity"])
    deposit_depth = deposit_geometry / area
    delta = deposit_depth - erosion
    derived = height + delta
    arrays = {"height_m": derived, "original_height_m": height, "valid_mask": valid,
              "receiver": receiver, "routed_volume_m3": volume, "wet_duration_s": duration,
              "erosion_depth_m": erosion, "deposit_depth_m": deposit_depth, "height_delta_m": delta,
              "remaining_erodible_thickness_m": material_arrays["erodible_thickness_m"] - erosion,
              "source_geometry_m3": source_geometry, "source_solid_m3": source_solid,
              "source_mass_kg": source_mass, "incoming_solid_m3": incoming.reshape(shape),
              "transported_solid_m3": transported.reshape(shape), "deposited_solid_m3": deposited,
              "deposit_geometry_m3": deposit_geometry, "stored_solid_m3": stored.reshape(shape),
              "exported_solid_m3": exported.reshape(shape), "cell_residual_m3": residual.reshape(shape),
              "engineering_open_boundary_mask": open_mask, "protected_mask": protected}
    ledger = {name: float(np.sum(arrays[name], dtype=np.float64)) for name in (
        "source_geometry_m3", "source_solid_m3", "source_mass_kg", "deposited_solid_m3",
        "deposit_geometry_m3", "stored_solid_m3", "exported_solid_m3")}
    ledger["solid_residual_m3"] = ledger["source_solid_m3"] - ledger["deposited_solid_m3"] - ledger["stored_solid_m3"] - ledger["exported_solid_m3"]
    terminals = valid.ravel() & (receiver == -1)
    metadata = {"algorithm": ALGORITHM, "format_version": 1, "shape": list(shape),
                "spacing_m": spacing, "origin_m_xz": materials["metadata"]["origin_m_xz"],
                "candidate_kind": candidate_kind, "parameters": config, "material_parameters": material_config,
                "material_identity_sha256": materials["identity_sha256"], "ledger": ledger,
                "generation_rounds": 1, "model": "generative heuristic; no real evolution age",
                "requires_topology_rebuild": bool(np.any(delta != 0)), "hydrology_coupled_verified": False,
                "natural_outlet_verified": False,
                "diagnostics": {"wet_closed_terminal_count": int(np.count_nonzero(terminals & wet.ravel() & ~open_mask.ravel())),
                                "protected_cell_count": int(np.count_nonzero(protected)),
                                "exhausted_cell_count": int(np.count_nonzero((erosion > 0) & (arrays["remaining_erodible_thickness_m"] == 0))),
                                "terminal_policy": "no local erosion without legal D4 receiver; closed sediment explicitly stored"}}
    bundle = _bundle(arrays, metadata)
    validate_morphology(bundle)
    return bundle


def validate_morphology(bundle):
    """Check the saved geometry and per-cell source/destination ledger without generating."""
    _check_identity(bundle)
    arrays = bundle["arrays"]
    metadata = bundle["metadata"]
    if metadata.get("algorithm") != ALGORITHM or metadata.get("format_version") != 1 or metadata.get("generation_rounds") != 1:
        raise ValueError("unsupported morphology format")
    shape = _shape(metadata["shape"])
    spacing = _positive(metadata["spacing_m"], "spacing_m")
    _config(metadata["parameters"], shape)
    material_config = _parameters(metadata["material_parameters"])
    required = {"height_m", "original_height_m", "valid_mask", "receiver", "routed_volume_m3", "wet_duration_s",
                "erosion_depth_m", "deposit_depth_m", "height_delta_m", "remaining_erodible_thickness_m",
                "source_geometry_m3", "source_solid_m3", "source_mass_kg", "incoming_solid_m3",
                "transported_solid_m3", "deposited_solid_m3", "deposit_geometry_m3", "stored_solid_m3",
                "exported_solid_m3", "cell_residual_m3", "engineering_open_boundary_mask", "protected_mask"}
    if set(arrays) != required:
        raise ValueError("morphology array names mismatch")
    valid = _mask(arrays["valid_mask"], shape, "valid_mask")
    protected = _mask(arrays["protected_mask"], shape, "protected_mask")
    open_mask = _mask(arrays["engineering_open_boundary_mask"], shape, "engineering_open_boundary_mask")
    for name, values in arrays.items():
        if name == "receiver":
            continue
        if values.shape != shape:
            raise ValueError("morphology array shape mismatch")
        if values.dtype.kind != "b":
            if values.dtype != np.dtype("float64") or not np.isfinite(values[valid]).all() or np.isinf(values).any():
                raise ValueError("invalid morphology numerical field")
            if name not in ("height_m", "original_height_m", "height_delta_m", "cell_residual_m3") and (not np.isfinite(values).all() or np.any(values < 0)):
                raise ValueError("negative or nonfinite sediment/water field")
    wet = (arrays["routed_volume_m3"] > 0) & (arrays["wet_duration_s"] > 0)
    if np.any(arrays["routed_volume_m3"][~valid] != 0) or np.any(arrays["wet_duration_s"][~valid] != 0):
        raise ValueError("saved water on unknown cell")
    receiver, order, sources, targets = _graph(arrays["original_height_m"], valid, arrays["receiver"], protected, wet)
    declared_open = np.zeros(shape, bool)
    for cell in metadata["parameters"]["engineering_open_boundary_cell_ids"]:
        row, col = divmod(cell, shape[1])
        if not valid[row, col] or protected[row, col] or receiver[cell] != -1 or (row not in (0, shape[0] - 1) and col not in (0, shape[1] - 1)):
            raise ValueError("invalid saved engineering boundary")
        declared_open[row, col] = True
    if not np.array_equal(open_mask, declared_open) or np.any(arrays["exported_solid_m3"][~open_mask] != 0):
        raise ValueError("undeclared sediment export")
    for name in ("erosion_depth_m", "deposit_depth_m", "source_solid_m3", "deposited_solid_m3"):
        if np.any(arrays[name][protected | ~valid] != 0):
            raise ValueError("protected or unknown geometry change")
    def check(actual, expected):
        if not np.allclose(actual, expected, rtol=1e-12, atol=1e-9, equal_nan=True):
            raise ValueError("morphology geometry/ledger mismatch")
    area = spacing ** 2
    check(arrays["source_geometry_m3"], area * arrays["erosion_depth_m"])
    check(arrays["source_solid_m3"], (1 - material_config["source_porosity"]) * arrays["source_geometry_m3"])
    check(arrays["source_mass_kg"], material_config["solid_density_kg_m3"] * arrays["source_solid_m3"])
    check(arrays["deposit_geometry_m3"], arrays["deposited_solid_m3"] / (1 - material_config["deposit_porosity"]))
    check(arrays["deposit_depth_m"], arrays["deposit_geometry_m3"] / area)
    check(arrays["height_delta_m"], arrays["deposit_depth_m"] - arrays["erosion_depth_m"])
    check(arrays["height_m"], arrays["original_height_m"] + arrays["height_delta_m"])
    original_thickness = arrays["remaining_erodible_thickness_m"] + arrays["erosion_depth_m"]
    low, high = material_config["erodible_thickness_range_m"]
    if np.any(original_thickness < low - 1e-12) or np.any(original_thickness > high + 1e-12):
        raise ValueError("remaining material thickness mismatch")
    terminals = receiver.reshape(shape) == -1
    if np.any(arrays["erosion_depth_m"][terminals | ~wet] != 0):
        raise ValueError("erosion without wet legal receiver")
    if metadata.get("candidate_kind") not in ("breach", "deposition"):
        raise ValueError("invalid saved candidate kind")
    if metadata["candidate_kind"] == "breach" and np.any(arrays["deposited_solid_m3"] != 0):
        raise ValueError("breach unexpectedly deposits")
    if np.any(arrays["deposited_solid_m3"] > arrays["incoming_solid_m3"] + 1e-12):
        raise ValueError("deposit lacks downstream source")
    if np.any(arrays["deposit_depth_m"] > metadata["parameters"]["max_deposit_depth_m"] + 1e-12):
        raise ValueError("deposit bound exceeded")
    expected_incoming = np.zeros(math.prod(shape))
    np.add.at(expected_incoming, targets, arrays["transported_solid_m3"].ravel()[sources])
    check(arrays["incoming_solid_m3"].ravel(), expected_incoming)
    if np.any(arrays["transported_solid_m3"].ravel()[receiver == -1] != 0):
        raise ValueError("terminal transport without receiver")
    capacity = np.where(wet, metadata["parameters"]["transport_ratio"] * arrays["routed_volume_m3"], 0)
    if np.any(arrays["transported_solid_m3"] + arrays["exported_solid_m3"] > capacity + 1e-12):
        raise ValueError("transport capacity exceeded")
    if np.any((arrays["transported_solid_m3"].ravel()[sources] > 0) & (protected.ravel()[sources] | protected.ravel()[targets])):
        raise ValueError("protected saved sediment path")
    available = arrays["source_solid_m3"] + arrays["incoming_solid_m3"]
    used = arrays["transported_solid_m3"] + arrays["deposited_solid_m3"] + arrays["stored_solid_m3"] + arrays["exported_solid_m3"]
    residual = available - used
    if np.any(np.abs(residual) > 1e-9 + 1e-12 * available):
        raise ValueError("per-cell solid budget failed")
    check(arrays["cell_residual_m3"], residual)
    for name in ("source_geometry_m3", "source_solid_m3", "source_mass_kg", "deposited_solid_m3",
                 "deposit_geometry_m3", "stored_solid_m3", "exported_solid_m3"):
        check(metadata["ledger"][name], float(np.sum(arrays[name])))
    total_residual = float(np.sum(arrays["source_solid_m3"]) - np.sum(arrays["deposited_solid_m3"]) - np.sum(arrays["stored_solid_m3"]) - np.sum(arrays["exported_solid_m3"]))
    check(metadata["ledger"]["solid_residual_m3"], total_residual)
    if abs(total_residual) > 1e-6 + 1e-10 * float(np.sum(arrays["source_solid_m3"])):
        raise ValueError("total solid budget failed")
    return True


def save_morphology(bundle, path):
    validate_morphology(bundle)
    return _save_bundle(bundle, path)


def load_morphology(path, *, expected_sha256=None, expected_identity=None):
    bundle = _load_bundle(path, expected_sha256=expected_sha256, expected_identity=expected_identity)
    validate_morphology(bundle)
    return bundle
