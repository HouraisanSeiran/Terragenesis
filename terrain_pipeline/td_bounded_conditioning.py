"""Uncalibrated initial-bed alternatives, independent of frozen erosion gates."""

import hashlib
import json
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import (
    MAX_CELLS, MAX_METADATA, identity, load_bundle, readonly, save_bundle,
)
from terrain_pipeline.td_basin_breach import saddle_path_face_identity
from terrain_pipeline.td_basin_hierarchy import validate_basin_hierarchy
from terrain_pipeline.td_basin_overflow import _face_id
from terrain_pipeline.td_basin_source import validate_td_source
from terrain_pipeline.td_material_field import _validate_cold_material
from terrain_pipeline.td_stable_spill_paths import SCHEMA as SPILL_SCHEMA, _digest


SCHEMA = "td-bounded-conditioning-v1"
ALGORITHM = "ordinary-weighted-disjoint-initial-geometry-v1"
CANDIDATE_IDS = ("baseline", "limited_fill", "limited_breach", "mixed")
DEFAULT_PARAMETERS = {
    "max_cut_m": 4.0, "max_fill_m": 1.0,
    "max_cut_m3": 100000.0, "max_fill_m3": 100000.0,
    "max_treatments": 32, "min_slope": 1e-6, "seed": 20261005,
}
FLOAT_ARRAYS = {"height_m", "original_height_m", "delta_m", "erodible_thickness_m"}
MASK_ARRAYS = {"valid_mask", "protected_mask", "open_boundary_mask", "unknown_contact_mask"}
INT_ARRAYS = {"contribution_owner", "receiver"}


def _parameters(parameters):
    supplied = {} if parameters is None else dict(parameters)
    if set(supplied) - set(DEFAULT_PARAMETERS):
        raise ValueError("unknown conditioning parameters")
    config = {**DEFAULT_PARAMETERS, **supplied}
    for name in ("max_cut_m", "max_fill_m", "max_cut_m3", "max_fill_m3", "min_slope"):
        value = config[name]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("invalid finite geometry budget: " + name)
        config[name] = float(value)
    if config["min_slope"] <= 0:
        raise ValueError("min_slope must be positive")
    if type(config["max_treatments"]) is not int or not 0 <= config["max_treatments"] <= 32:
        raise ValueError("max_treatments must be 0..32")
    if type(config["seed"]) is not int or not 0 <= config["seed"] < 2 ** 64:
        raise ValueError("seed must be uint64")
    return config


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("lowercase SHA256 required")
    return value


def _record_identity(record):
    if record.get("identity_sha256") != _digest({key: value for key, value in record.items() if key != "identity_sha256"}):
        raise ValueError("spill record identity mismatch")


def _random_unit(seed, face_id, channel):
    digest = hashlib.sha256((str(seed) + ":" + face_id + ":" + channel).encode("ascii")).digest()
    return (int.from_bytes(digest[:8], "big") + 1) / (2 ** 64 + 2)


def _geometry(arrays, record, spacing, config, kind):
    """Return an atomic proposal on the original bed, including anchor support."""
    original = arrays["original_height_m"].ravel()
    owner = arrays["contribution_owner"].ravel()
    receiver = arrays["receiver"].ravel()
    path = record["path_cell_ids"]
    face = record["directed_face_cell_ids"]
    source = record["source_basin_id"]
    destination = record["destination_basin_id"]
    columns = arrays["original_height_m"].shape[1]
    if (type(source) is not int or type(destination) is not int or source < 0 or destination < 0 or
            source == destination or not isinstance(path, list) or not 3 <= len(path) <= 64 or
            any(type(cell) is not int or not 0 <= cell < original.size for cell in path) or
            len(set(path)) != len(path) or not isinstance(face, list) or len(face) != 2):
        return None, "invalid_source_destination_path"
    if any(abs(first // columns - second // columns) + abs(first % columns - second % columns) != 1
           for first, second in zip(path, path[1:])):
        return None, "path_not_d4"
    crossings = [index for index in range(len(path) - 1) if path[index:index + 2] == face]
    if len(crossings) != 1:
        return None, "path_missing_directed_face"
    crossing = crossings[0]
    if (not np.all(owner[path[:crossing + 1]] == source) or
            not np.all(owner[path[crossing + 1:]] == destination) or
            receiver[path[0]] != -1 or receiver[path[-1]] != -1 or
            any(receiver[path[index]] != path[index - 1] for index in range(1, crossing + 1)) or
            any(receiver[path[index]] != path[index + 1] for index in range(crossing + 1, len(path) - 1))):
        return None, "source_destination_receiver_anchor_mismatch"
    if (type(record["sill_m"]) not in (int, float) or not math.isfinite(record["sill_m"]) or
            record["sill_m"] != float(max(original[face]))):
        return None, "sill_differs_from_real_face"
    if original[path[-1]] >= original[path[0]]:
        return None, "downstream_anchor_not_lower"
    if kind == "breach":
        cells = np.asarray(path, dtype=np.int64)
        target = original[cells].copy()
        for index in range(1, len(path)):
            target[index] = min(original[path[index]], target[index - 1] - spacing * config["min_slope"])
        if target[-1] != original[path[-1]]:
            return None, "downstream_anchor_requires_modification"
        change = target - original[cells]
        support = cells
    elif kind == "fill":
        cells = np.flatnonzero((owner == source) & (original < record["sill_m"]))
        change = record["sill_m"] - original[cells]
        support = np.union1d(cells, path)
    else:
        return None, "unknown_treatment_kind"
    if any(np.any(arrays[name].ravel()[support]) for name in ("protected_mask", "unknown_contact_mask")):
        return None, "protected_or_unknown_support"
    if not np.all(arrays["valid_mask"].ravel()[support]):
        return None, "invalid_support"
    if np.any(arrays["open_boundary_mask"].ravel()[cells] & (change != 0)):
        return None, "open_boundary_geometry_change"
    if not np.any(change != 0):
        return None, "no_geometry_change"
    if np.any(-change > config["max_cut_m"]) or np.any(change > config["max_fill_m"]):
        return None, "maximum_thickness_exceeded"
    if np.any(-change > arrays["erodible_thickness_m"].ravel()[cells]):
        return None, "insufficient_erodible_thickness"
    area = spacing ** 2
    cut = float(np.maximum(-change, 0).sum() * area)
    fill = float(np.maximum(change, 0).sum() * area)
    return (cells, change, support, cut, fill), None


def _ledger(delta, spacing, material_parameters):
    cut = float(np.maximum(-delta, 0).sum() * spacing ** 2)
    fill = float(np.maximum(delta, 0).sum() * spacing ** 2)
    cut_solid = cut * (1 - material_parameters["source_porosity"])
    fill_solid = fill * (1 - material_parameters["deposit_porosity"])
    density = material_parameters["solid_density_kg_m3"]
    return {
        "cut_geometry_m3": cut, "fill_geometry_m3": fill,
        "cut_solid_m3": cut_solid, "fill_solid_m3": fill_solid,
        "external_initial_material_input_solid_m3": fill_solid,
        "external_initial_material_output_solid_m3": cut_solid,
        "net_external_initial_material_input_solid_m3": fill_solid - cut_solid,
        "external_initial_material_input_kg": fill_solid * density,
        "external_initial_material_output_kg": cut_solid * density,
        "net_external_initial_material_input_kg": (fill_solid - cut_solid) * density,
        "internal_material_transfer_solid_m3": 0.0,
        "semantics": "initial geometry only; cut exported and fill externally supplied; no dynamic erosion or deposition",
    }


def _requests(source, hierarchy, materials, report):
    validate_td_source(source)
    validate_basin_hierarchy(hierarchy)
    _validate_cold_material(materials)
    _record_identity(report)
    if (report["schema"] != SPILL_SCHEMA or report["source_identity_sha256"] != source["identity_sha256"] or
            report["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
            hierarchy["metadata"]["source_identity_sha256"] != source["identity_sha256"]):
        raise ValueError("conditioning source/hierarchy/spill mismatch")
    if (materials["metadata"]["shape"] != list(source["arrays"]["height_m"].shape) or
            any(materials["metadata"][key] != source["metadata"][key] for key in ("spacing_m", "origin_m_xz")) or
            not np.array_equal(materials["arrays"]["protected_mask"], source["arrays"]["protected_mask"])):
        raise ValueError("material grid/protection mismatch")
    records = []
    seen = set()
    for path in report["paths"]:
        _record_identity(path)
        if path["status"] != "bounded_candidate_request":
            continue
        if path["rejection_reasons"] or path["face_id"] in seen:
            raise ValueError("rejected or duplicate bounded path")
        seen.add(path["face_id"])
        ordinary = [request for request in path["bounded_candidate_requests"] if request["case"] == "normal-24h"]
        if len(ordinary) != 1:
            raise ValueError("one ordinary request required per bounded path")
        request = ordinary[0]
        _record_identity(request)
        hydro = request["hydro_face_evidence"]
        anchor = request["downstream_anchor_evidence"]
        face_index = path["hierarchy_face_index"]
        if type(face_index) is not int or not 0 <= face_index < len(hierarchy["arrays"]["face_cells"]):
            raise ValueError("invalid hierarchy face index")
        face_cells = hierarchy["arrays"]["face_cells"][face_index].tolist()
        if (path["face_id"] != _face_id(hierarchy, face_index) or path["face_cell_ids"] != face_cells or
                path["source_identity_sha256"] != source["identity_sha256"] or
                path["hierarchy_identity_sha256"] != hierarchy["identity_sha256"] or
                path["topology_identity_sha256"] != report["topology_identity_sha256"] or
                sorted(path["directed_face_cell_ids"]) != sorted(face_cells) or
                request["path_cell_ids"] != path["path_cell_ids"] or request["face_id"] != path["face_id"] or
                request["source_identity_sha256"] != source["identity_sha256"] or
                request["topology_identity_sha256"] != report["topology_identity_sha256"] or
                request["hydro_identity_sha256"] != report["event_identity_sha256"]["normal-24h"] or
                hydro["hydro_identity_sha256"] != request["hydro_identity_sha256"] or
                hydro["face_cell_ids"] != path["directed_face_cell_ids"] or
                hydro["outward_volume_m3"] != request["routed_volume_m3"] or
                anchor["topology_identity_sha256"] != report["topology_identity_sha256"] or
                anchor["source_basin_id"] != path["source_basin_id"] or
                anchor["destination_basin_id"] != path["destination_basin_id"] or
                anchor["tail_cell_ids"] != [path["path_cell_ids"][-1]] or
                anchor["engineering_open_boundary"] is not False):
            raise ValueError("ordinary request geometry/evidence mismatch")
        expected_face = saddle_path_face_identity(source["arrays"]["height_m"], request["path_cell_ids"],
            source_identity_sha256=source["identity_sha256"], topology_identity_sha256=report["topology_identity_sha256"])
        if request["path_face_identity"] != expected_face or path["path_face_identity"] != expected_face:
            raise ValueError("path face identity mismatch")
        volume = request["routed_volume_m3"]
        if type(volume) not in (int, float) or not math.isfinite(volume) or volume < 0:
            raise ValueError("invalid ordinary water weight")
        record = {key: path[key] for key in ("face_id", "path_cell_ids", "directed_face_cell_ids",
                  "source_basin_id", "destination_basin_id", "sill_m")}
        record.update(request_identity_sha256=request["identity_sha256"], ordinary_water_volume_m3=float(volume))
        records.append(record)
    return records


def build_conditioning_candidates(source, hierarchy, materials, spill_report, *, parameters=None):
    """Build four immutable alternatives, never use an event erosion-potential gate."""
    config = _parameters(parameters)
    requests = _requests(source, hierarchy, materials, spill_report)
    requests.sort(key=lambda record: (
        -math.log(_random_unit(config["seed"], record["face_id"], "order")) / record["ordinary_water_volume_m3"]
        if record["ordinary_water_volume_m3"] > 0 else math.inf, record["face_id"]))
    arrays = dict(source["arrays"])
    arrays["original_height_m"] = arrays["height_m"]
    arrays["erodible_thickness_m"] = materials["arrays"]["erodible_thickness_m"]
    arrays["contribution_owner"] = hierarchy["arrays"]["contribution_owner"]
    arrays["receiver"] = hierarchy["arrays"]["receiver"].reshape(arrays["height_m"].shape)
    owners = arrays["contribution_owner"]
    arrays["unknown_contact_mask"] = np.where(owners >= 0,
        hierarchy["arrays"]["node_unknown_contact"][np.maximum(owners, 0)], True)
    spacing = source["metadata"]["spacing_m"]
    candidates = {}
    for candidate_id in CANDIDATE_IDS:
        height = arrays["original_height_m"].copy()
        occupied = np.zeros(height.size, bool)
        accepted, rejected = [], []
        cut_total = fill_total = 0.0
        for record in requests if candidate_id != "baseline" else []:
            if candidate_id == "mixed":
                kind = "fill" if _random_unit(config["seed"], record["face_id"], "kind") < 0.5 else "breach"
            else:
                kind = "fill" if candidate_id == "limited_fill" else "breach"
            treatment = dict(record, kind=kind)
            proposal, reason = _geometry(arrays, record, spacing, config, kind)
            if record["ordinary_water_volume_m3"] <= 0:
                reason = "no_ordinary_water_weight"
            if proposal is not None and reason is None:
                cells, change, support, cut, fill = proposal
                if occupied[support].any():
                    reason = "occupied_support_conflict"
                elif len(accepted) >= config["max_treatments"]:
                    reason = "global_treatment_budget_exceeded"
                elif cut_total + cut > config["max_cut_m3"] or fill_total + fill > config["max_fill_m3"]:
                    reason = "global_geometry_budget_exceeded"
            if reason is not None:
                rejected.append(dict(treatment, rejection_reasons=[reason]))
                continue
            height.ravel()[cells] = arrays["original_height_m"].ravel()[cells] + change
            occupied[support] = True
            cut_total += cut
            fill_total += fill
            accepted.append(dict(treatment, cut_geometry_m3=cut, fill_geometry_m3=fill))
        result_arrays = {**arrays, "height_m": height, "delta_m": height - arrays["original_height_m"]}
        metadata = {
            "schema": SCHEMA, "algorithm": ALGORITHM, "candidate_id": candidate_id,
            "source_identity_sha256": source["identity_sha256"], "source_metadata": source["metadata"],
            "hierarchy_identity_sha256": hierarchy["identity_sha256"],
            "material_identity_sha256": materials["identity_sha256"],
            "spill_identity_sha256": spill_report["identity_sha256"],
            "spacing_m": spacing, "origin_m_xz": source["metadata"]["origin_m_xz"],
            "coordinates": source["metadata"]["coordinates"], "parameters": config, "seed": config["seed"],
            "material_parameters": materials["metadata"]["parameters"],
            "geometry_ledger": _ledger(result_arrays["delta_m"], spacing, materials["metadata"]["parameters"]),
            "accepted_treatments": accepted, "rejected_treatments": rejected,
            "weight_policy": "normal-24h outward water; seeded exponential weighted ordering without replacement",
            "path_selection_policy": "existing bounded_candidate_request stable-path set from ordinary/strong prescreen; strong rainfall volumes never shape permanent beds",
            "initial_material_source": "explicit generative external fill supply and external cut disposal; uncalibrated, not a verified natural sediment source",
            "budget_status": "explicit_generative_uncalibrated",
            "storage_semantics": "retained depressions; fill to real sill does not certify drainage",
            "natural": False, "hydraulic": False, "publishable": False,
            "natural_outlet_verified": False, "hydraulic_ready": False,
            "dynamic_erosion_or_deposition": False,
        }
        frozen = {key: readonly(value) for key, value in result_arrays.items()}
        metadata = json.loads(json.dumps(metadata, allow_nan=False))
        bundle = {"arrays": frozen, "metadata": metadata, "identity_sha256": identity(frozen, metadata)}
        validate_conditioning(bundle)
        candidates[candidate_id] = bundle
    return candidates


def validate_conditioning(result):
    """Cold structural and geometry replay validation; no solver or generation."""
    arrays, metadata = result["arrays"], result["metadata"]
    if (metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM or
            metadata.get("candidate_id") not in CANDIDATE_IDS or
            result["identity_sha256"] != identity(arrays, metadata)):
        raise ValueError("conditioning schema/identity mismatch")
    if set(arrays) != FLOAT_ARRAYS | MASK_ARRAYS | INT_ARRAYS:
        raise ValueError("conditioning array names mismatch")
    shape = arrays["height_m"].shape
    if len(shape) != 2 or not 1 <= math.prod(shape) <= MAX_CELLS:
        raise ValueError("invalid bounded conditioning shape")
    for name, values in arrays.items():
        dtype = np.float64 if name in FLOAT_ARRAYS else (bool if name in MASK_ARRAYS else np.int64)
        if values.shape != shape or values.dtype != dtype or (name in FLOAT_ARRAYS and not np.isfinite(values).all()):
            raise ValueError("invalid conditioning array: " + name)
    for name in ("source_identity_sha256", "hierarchy_identity_sha256", "material_identity_sha256", "spill_identity_sha256"):
        _sha(metadata[name])
    source_arrays = {key: arrays[key] for key in ("valid_mask", "protected_mask", "open_boundary_mask")}
    source_arrays["height_m"] = arrays["original_height_m"]
    validate_td_source({"arrays": source_arrays, "metadata": metadata["source_metadata"],
                        "identity_sha256": metadata["source_identity_sha256"]})
    if any(metadata[key] != metadata["source_metadata"][key] for key in ("spacing_m", "origin_m_xz", "coordinates")):
        raise ValueError("conditioning grid mismatch")
    config = _parameters(metadata["parameters"])
    if config != metadata["parameters"] or metadata["seed"] != config["seed"]:
        raise ValueError("conditioning parameter/seed mismatch")
    for key in ("natural", "hydraulic", "publishable", "natural_outlet_verified", "hydraulic_ready", "dynamic_erosion_or_deposition"):
        if metadata.get(key) is not False:
            raise ValueError("conditioning certification must remain false")
    if metadata.get("budget_status") != "explicit_generative_uncalibrated":
        raise ValueError("uncalibrated geometry designation required")
    material = metadata["material_parameters"]
    if (type(material["solid_density_kg_m3"]) not in (int, float) or
            not math.isfinite(material["solid_density_kg_m3"]) or material["solid_density_kg_m3"] <= 0 or
            any(type(material[key]) not in (int, float) or not math.isfinite(material[key]) or
                not 0 <= material[key] < 1 for key in ("source_porosity", "deposit_porosity")) or
            np.any(arrays["erodible_thickness_m"] < 0)):
        raise ValueError("invalid conditioning solid material")
    expected = arrays["original_height_m"].copy()
    occupied = np.zeros(expected.size, bool)
    accepted = metadata["accepted_treatments"]
    if len(accepted) > config["max_treatments"] or (metadata["candidate_id"] == "baseline" and (accepted or metadata["rejected_treatments"])):
        raise ValueError("conditioning treatment count mismatch")
    for treatment in accepted:
        _sha(treatment["request_identity_sha256"])
        volume = treatment["ordinary_water_volume_m3"]
        if type(volume) not in (int, float) or not math.isfinite(volume) or volume <= 0:
            raise ValueError("accepted treatment requires ordinary water")
        kind = treatment["kind"]
        candidate_id = metadata["candidate_id"]
        expected_kind = "fill" if candidate_id == "limited_fill" else "breach"
        if candidate_id == "mixed":
            expected_kind = "fill" if _random_unit(config["seed"], treatment["face_id"], "kind") < 0.5 else "breach"
        if kind != expected_kind:
            raise ValueError("candidate treatment mode mismatch")
        proposal, reason = _geometry(arrays, treatment, metadata["spacing_m"], config, kind)
        if reason is not None:
            raise ValueError("accepted conditioning geometry rejected: " + reason)
        cells, change, support, cut, fill = proposal
        if occupied[support].any() or treatment["cut_geometry_m3"] != cut or treatment["fill_geometry_m3"] != fill:
            raise ValueError("conditioning support/geometry ledger mismatch")
        occupied[support] = True
        expected.ravel()[cells] = arrays["original_height_m"].ravel()[cells] + change
    if (not np.array_equal(arrays["height_m"], expected) or
            not np.array_equal(arrays["delta_m"], expected - arrays["original_height_m"])):
        raise ValueError("conditioning bed differs from atomic treatment replay")
    if np.any(arrays["delta_m"][arrays["open_boundary_mask"]] != 0):
        raise ValueError("conditioning changes open boundary geometry")
    ledger = _ledger(arrays["delta_m"], metadata["spacing_m"], material)
    if (ledger != metadata["geometry_ledger"] or ledger["cut_geometry_m3"] > config["max_cut_m3"] or
            ledger["fill_geometry_m3"] > config["max_fill_m3"]):
        raise ValueError("conditioning global geometry/solid budget mismatch")
    return True


def save_conditioning(path, result):
    save_bundle(path, result, validator=validate_conditioning)


def _headers(headers):
    if set(headers) != FLOAT_ARRAYS | MASK_ARRAYS | INT_ARRAYS | {"manifest"}:
        raise ValueError("conditioning archive names mismatch")
    for name, (shape, dtype) in headers.items():
        if name == "manifest":
            if len(shape) != 1 or dtype != np.uint8 or math.prod(shape) > MAX_METADATA:
                raise ValueError("invalid conditioning manifest header")
        else:
            expected = np.float64 if name in FLOAT_ARRAYS else (bool if name in MASK_ARRAYS else np.int64)
            if len(shape) != 2 or not 1 <= math.prod(shape) <= MAX_CELLS or dtype != expected:
                raise ValueError("invalid conditioning array header")


def load_conditioning(path, *, expected_sha256, expected_identity):
    _sha(expected_sha256)
    _sha(expected_identity)
    result = load_bundle(path, expected_sha256=expected_sha256, validator=validate_conditioning,
                         header_validator=_headers)
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external conditioning identity mismatch")
    return result
