"""Explicit finite saddle-path cuts; infeasible paths preserve the entire baseline."""

import hashlib
import math

import numpy as np

from terrain_pipeline.td_material_field import (
    _bundle, _check_identity, _json, _load_bundle, _mask, _positive, _save_bundle,
    _shape, _validate_cold_material, _parameters as _material_parameters,
)


ALGORITHM = "td-explicit-d4-saddle-path-target-slope-v1"
DEFAULT_PARAMETERS = {"erosion_scale_m": 0.15, "reference_volume_m3": 1000.0,
                      "reference_duration_s": 3600.0, "transport_ratio": 0.002,
                      "max_path_cells": 64}


def _sha256(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(name + " must be externally supplied lowercase SHA256")
    return value


def _path_ids(path_cell_ids, shape, max_path_cells):
    path = np.asarray(path_cell_ids)
    if path.ndim != 1 or path.dtype.kind not in "iu" or not 3 <= path.size <= max_path_cells:
        raise ValueError("path must be a bounded integer sequence with two anchors and an interior")
    if np.any(path < 0) or np.any(path >= math.prod(shape)) or np.unique(path).size != path.size:
        raise ValueError("path cells must be unique and inside domain")
    path = path.astype(np.int64)
    rows, columns = np.divmod(path, shape[1])
    if np.any(np.abs(np.diff(rows)) + np.abs(np.diff(columns)) != 1):
        raise ValueError("path must use explicit D4 faces")
    return path


def saddle_path_face_identity(height_m, path_cell_ids, *, source_identity_sha256, topology_identity_sha256):
    """Identity of ordered directed D4 faces, tied to the caller's frozen topology."""
    height = np.asarray(height_m, np.float64)
    shape = _shape(height.shape)
    topology = _sha256(topology_identity_sha256, "topology_identity_sha256")
    source = _sha256(source_identity_sha256, "source_identity_sha256")
    path = _path_ids(path_cell_ids, shape, 64)
    record = {"shape": list(shape), "topology_identity_sha256": topology,
              "source_identity_sha256": source,
              "original_path_bed_m": [float(value) if math.isfinite(value) else None for value in height.ravel()[path]],
              "directed_faces": np.column_stack((path[:-1], path[1:])).tolist()}
    return hashlib.sha256(_json(record).encode("utf-8")).hexdigest()


def _parameters(parameters):
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown saddle breach parameter")
    config = {**DEFAULT_PARAMETERS, **supplied}
    for name in ("erosion_scale_m", "transport_ratio"):
        config[name] = _positive(config[name], name, allow_zero=True)
    for name in ("reference_volume_m3", "reference_duration_s"):
        config[name] = _positive(config[name], name)
    maximum = config["max_path_cells"]
    if not isinstance(maximum, (int, np.integer)) or isinstance(maximum, (bool, np.bool_)) or not 3 <= maximum <= 64:
        raise ValueError("path work budget must be 3..64 cells")
    for name in ("erosion_scale_m", "reference_volume_m3", "reference_duration_s", "transport_ratio"):
        if config[name] != DEFAULT_PARAMETERS[name]:
            raise ValueError("saddle contract v1 fixes " + name)
    config["max_path_cells"] = int(maximum)
    return config


def _path_values(values, shape, path, name):
    values = np.asarray(values)
    if values.dtype.kind not in "fiu":
        raise ValueError(name + " must be numeric")
    if values.shape == shape or values.shape == (math.prod(shape),):
        result = values.ravel()[path].astype(np.float64)
    elif values.shape == path.shape:
        result = values.astype(np.float64)
    else:
        raise ValueError(name + " must match path or domain")
    if not np.isfinite(result).all() or np.any(result < 0):
        raise ValueError(name + " must be finite nonnegative")
    return result


def _hydro_evidence(evidence, hydro_identity, path, shape):
    if evidence is None:
        return None
    required = {"hydro_identity_sha256", "face_cell_ids", "outward_volume_m3", "positive_outflow_steps", "dt_s"}
    if not isinstance(evidence, dict) or set(evidence) != required or evidence["hydro_identity_sha256"] != hydro_identity:
        raise ValueError("invalid hydro face evidence identity/fields")
    face = np.asarray(evidence["face_cell_ids"])
    if face.shape != (2,) or face.dtype.kind not in "iu" or not any(np.array_equal(face, path[index:index + 2]) for index in range(path.size - 1)):
        raise ValueError("outward saddle face must be an ordered path D4 face")
    steps = evidence["positive_outflow_steps"]
    if not isinstance(steps, (int, np.integer)) or isinstance(steps, (bool, np.bool_)) or steps < 0:
        raise ValueError("invalid positive outward-flow step count")
    volume = _positive(evidence["outward_volume_m3"], "outward_volume_m3", allow_zero=True)
    dt = _positive(evidence["dt_s"], "dt_s")
    duration = int(steps) * dt
    if not math.isfinite(duration):
        raise ValueError("face wet duration overflow")
    return {**evidence, "face_cell_ids": list(map(int, face)), "outward_volume_m3": volume,
            "positive_outflow_steps": int(steps), "dt_s": dt, "wet_duration_s": duration}


def _anchor_evidence(evidence, height, valid, protected, path, topology_identity):
    if evidence is None:
        return None
    required = {"topology_identity_sha256", "source_basin_id", "destination_basin_id", "tail_cell_ids", "engineering_open_boundary"}
    if not isinstance(evidence, dict) or set(evidence) != required or evidence["topology_identity_sha256"] != topology_identity:
        raise ValueError("invalid downstream anchor evidence")
    for name in ("source_basin_id", "destination_basin_id"):
        if not isinstance(evidence[name], (int, np.integer)) or isinstance(evidence[name], (bool, np.bool_)) or evidence[name] < 0:
            raise ValueError("invalid anchor basin id")
    if type(evidence["engineering_open_boundary"]) is not bool:
        raise ValueError("engineering boundary evidence must be boolean")
    tail = np.asarray(evidence["tail_cell_ids"])
    if tail.ndim != 1 or tail.dtype.kind not in "iu" or not 1 <= tail.size <= 64:
        raise ValueError("anchor tail must be a bounded integer sequence")
    tail = tail.astype(np.int64)
    if tail[0] != path[-1] or np.any(tail < 0) or np.any(tail >= height.size) or np.unique(tail).size != tail.size or np.intersect1d(tail[1:], path[:-1]).size:
        raise ValueError("anchor tail loops back or lies outside domain")
    rows, cols = np.divmod(tail, height.shape[1])
    if np.any(np.abs(np.diff(rows)) + np.abs(np.diff(cols)) != 1):
        raise ValueError("anchor tail must use D4 faces")
    if np.any(~valid.ravel()[tail]) or np.any(protected.ravel()[tail]) or np.any(np.diff(height.ravel()[tail]) > 0):
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
    height = np.asarray(height_m)
    shape = _shape(height.shape)
    if height.dtype.kind not in "fiu":
        raise ValueError("height must be numeric")
    height = height.astype(np.float64)
    valid = _mask(valid_mask, shape, "valid_mask")
    if valid_mask is None or not np.isfinite(height[valid]).all() or np.isinf(height).any():
        raise ValueError("valid height must be finite")
    spacing = _positive(spacing_m, "spacing_m")
    if not math.isfinite(spacing ** 2) or spacing ** 2 == 0:
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
    target = np.asarray(target_bed_m)
    if target.shape != path.shape or target.dtype.kind not in "fiu" or not np.isfinite(target).all():
        raise ValueError("target_bed_m must contain a finite bed for each path cell")
    target = target.astype(np.float64)
    volume = _path_values(routed_volume_m3, shape, path, "routed_volume_m3")
    duration = _path_values(wet_duration_s, shape, path, "wet_duration_s")
    _validate_cold_material(materials)
    if tuple(materials["metadata"]["shape"]) != shape or materials["metadata"]["spacing_m"] != spacing:
        raise ValueError("material grid mismatch")
    material = materials["arrays"]
    original = height.ravel()[path]
    thickness = material["erodible_thickness_m"].ravel()[path]
    requested = original - target
    slope = np.zeros(path.size)
    slope[:-1] = (target[:-1] - target[1:]) / spacing
    potential = np.zeros(path.size)
    reasons = []
    hydro_evidence = _hydro_evidence(hydro_face_evidence, hydro_identity, path, shape)
    anchor_evidence = _anchor_evidence(downstream_anchor_evidence, height, valid,
                                       material["protected_mask"], path, topology_identity)
    if hydro_evidence is None:
        reasons.append("missing_actual_saddle_face_flux_evidence")
    elif np.any(volume != hydro_evidence["outward_volume_m3"]) or np.any(duration != hydro_evidence["wet_duration_s"]):
        raise ValueError("path exposure must equal outward saddle-face integrated quantity")
    if anchor_evidence is None:
        reasons.append("missing_legal_downstream_anchor_evidence")
    if np.any(~valid.ravel()[path]):
        reasons.append("unknown_path_cell")
    if np.any(material["protected_mask"].ravel()[path]):
        reasons.append("protected_path_cell")
    if not np.isfinite(original).all():
        reasons.append("unknown_original_bed")
    if np.any(np.diff(target) >= 0):
        reasons.append("target_not_strictly_downhill")
    if np.any(slope[:-1] < 1e-6):
        reasons.append("target_slope_below_minimum")
    if not np.allclose(target, np.linspace(target[0], target[-1], path.size), rtol=0, atol=1e-8):
        reasons.append("target_not_anchor_linear_interpolation")
    if target[0] != original[0] or target[-1] != original[-1]:
        reasons.append("endpoint_anchor_changed")
    if np.any(requested < 0):
        reasons.append("target_requires_unsourced_fill")
    if not np.any(requested[1:-1] > 0):
        reasons.append("no_saddle_cut_requested")
    if np.any(requested > thickness + 1e-8):
        reasons.append("insufficient_erodible_thickness")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        potential[:-1] = (config["erosion_scale_m"] * material["erodibility"].ravel()[path[:-1]]
                          * material["weak_path_preference"].ravel()[path[:-1]]
                          * np.log1p(volume[:-1] / config["reference_volume_m3"])
                          * (-np.expm1(-duration[:-1] / config["reference_duration_s"]))
                          * np.sqrt(np.maximum(slope[:-1], 0)))
    if not np.isfinite(potential).all():
        raise ValueError("path potential exceeds numerical budget")
    needs_cut = requested > 0
    if np.any(needs_cut & ((volume <= 0) | (duration <= 0))):
        reasons.append("no_water_or_duration_at_cut")
    if np.any(needs_cut & (requested > potential + 1e-8)):
        reasons.append("insufficient_water_material_potential")
    if np.any(volume <= 0) or np.any(duration <= 0):
        reasons.append("zero_saddle_exposure")
    accepted = not reasons
    erosion = np.zeros(shape)
    if accepted:
        erosion.ravel()[path] = requested
    area = spacing ** 2
    source_geometry = erosion * area
    material_config = materials["metadata"]["parameters"]
    source_solid = source_geometry * (1 - material_config["source_porosity"])
    source_mass = source_solid * material_config["solid_density_kg_m3"]
    if not np.isfinite(source_mass).all():
        raise ValueError("path source mass exceeds numerical budget")
    stored_solid = np.zeros(shape)
    stored_solid.ravel()[path[-1]] = float(np.sum(source_solid))
    arrays = {"original_height_m": height, "height_m": height - erosion, "valid_mask": valid,
              "protected_mask": material["protected_mask"], "path_cell_ids": path,
              "path_target_bed_m": target, "path_routed_volume_m3": volume,
              "path_wet_duration_s": duration, "path_potential_depth_m": potential,
              "path_erodible_thickness_m": thickness,
              "path_required_depth_m": np.where(np.isfinite(requested), requested, 0.0), "erosion_depth_m": erosion,
              "height_delta_m": -erosion, "source_geometry_m3": source_geometry,
              "source_solid_m3": source_solid, "source_mass_kg": source_mass,
              "stored_solid_m3": stored_solid, "transported_solid_m3": np.zeros(shape),
              "exported_solid_m3": np.zeros(shape), "deposited_solid_m3": np.zeros(shape),
              "deposit_geometry_m3": np.zeros(shape)}
    ledger = {name: float(np.sum(arrays[name])) for name in (
        "source_geometry_m3", "source_solid_m3", "source_mass_kg", "stored_solid_m3",
        "transported_solid_m3", "exported_solid_m3", "deposited_solid_m3", "deposit_geometry_m3")}
    if not all(math.isfinite(value) for value in ledger.values()):
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
    result = _bundle(arrays, metadata)
    validate_saddle_breach(result)
    return result


def validate_saddle_breach(bundle):
    _check_identity(bundle)
    arrays = bundle["arrays"]
    metadata = bundle["metadata"]
    if metadata.get("algorithm") != ALGORITHM or metadata.get("format_version") != 1:
        raise ValueError("unsupported saddle breach format")
    shape = _shape(metadata["shape"])
    config = _parameters(metadata["parameters"])
    path = _path_ids(arrays["path_cell_ids"], shape, config["max_path_cells"])
    if metadata["path_face_identity"] != saddle_path_face_identity(arrays["original_height_m"], path, source_identity_sha256=metadata["source_identity_sha256"], topology_identity_sha256=metadata["topology_identity_sha256"]):
        raise ValueError("saved path face identity mismatch")
    for name in ("source_identity_sha256", "hydro_identity_sha256", "material_identity_sha256"):
        _sha256(metadata[name], name)
    valid = _mask(arrays["valid_mask"], shape, "valid_mask")
    protected = _mask(arrays["protected_mask"], shape, "protected_mask")
    spacing = _positive(metadata["spacing_m"], "spacing_m")
    for name, values in arrays.items():
        expected_shape = path.shape if name.startswith("path_") else shape
        if values.shape != expected_shape:
            raise ValueError("saved saddle array shape mismatch")
        if name != "path_cell_ids" and values.dtype.kind != "b":
            if values.dtype != np.dtype("float64") or np.isinf(values).any():
                raise ValueError("invalid saved saddle array dtype/value")
            if name not in ("original_height_m", "height_m") and not np.isfinite(values).all():
                raise ValueError("nonfinite saved saddle ledger")
    erosion = arrays["erosion_depth_m"]
    if np.any(erosion < 0) or np.any(erosion[protected | ~valid] != 0):
        raise ValueError("invalid saddle erosion")
    outside = np.ones(math.prod(shape), bool)
    outside[path] = False
    if np.any(erosion.ravel()[outside] != 0):
        raise ValueError("saddle change outside explicit path")
    def check(actual, expected):
        if not np.allclose(actual, expected, rtol=1e-12, atol=1e-9, equal_nan=True):
            raise ValueError("saved saddle geometry/ledger mismatch")
    if metadata["status"] == "rejected":
        if not metadata["rejection_reasons"] or np.any(erosion != 0):
            raise ValueError("rejected saddle must preserve entire baseline")
    elif metadata["status"] == "candidate":
        target = arrays["path_target_bed_m"]
        original = arrays["original_height_m"].ravel()[path]
        if metadata["rejection_reasons"] or np.any(~valid.ravel()[path]) or np.any(protected.ravel()[path]) or np.any(np.diff(target) >= 0):
            raise ValueError("invalid accepted saddle path")
        if target[0] != original[0] or target[-1] != original[-1]:
            raise ValueError("saved saddle anchor changed")
        check(erosion.ravel()[path], original - target)
        if np.any(erosion.ravel()[path] > arrays["path_erodible_thickness_m"] + 1e-8) or np.any(erosion.ravel()[path] > arrays["path_potential_depth_m"] + 1e-8):
            raise ValueError("saved saddle exceeds thickness or water potential")
        if not np.allclose(target, np.linspace(target[0], target[-1], path.size), rtol=0, atol=1e-8) or np.any((target[:-1] - target[1:]) / spacing < 1e-6):
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
    material = _material_parameters(metadata["material_parameters"])
    check(arrays["source_solid_m3"], arrays["source_geometry_m3"] * (1 - material["source_porosity"]))
    check(arrays["source_mass_kg"], arrays["source_solid_m3"] * material["solid_density_kg_m3"])
    expected_stored = np.zeros(shape)
    expected_stored.ravel()[path[-1]] = float(np.sum(arrays["source_solid_m3"]))
    check(arrays["stored_solid_m3"], expected_stored)
    for name in ("transported_solid_m3", "exported_solid_m3", "deposited_solid_m3", "deposit_geometry_m3"):
        if np.any(arrays[name] != 0):
            raise ValueError("unapproved sediment transfer in saddle phase")
    for name, total in metadata["ledger"].items():
        check(total, 0.0 if name == "solid_residual_m3" else float(np.sum(arrays[name])))
    return True


def save_saddle_breach(bundle, path):
    validate_saddle_breach(bundle)
    return _save_bundle(bundle, path)


def load_saddle_breach(path, *, expected_sha256=None, expected_identity=None):
    bundle = _load_bundle(path, expected_sha256=expected_sha256, expected_identity=expected_identity)
    validate_saddle_breach(bundle)
    return bundle
