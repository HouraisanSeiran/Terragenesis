"""Explicit, bounded composition of accepted surface engineering products."""

from dataclasses import asdict, dataclass
import ast
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline import surface_coast_drop as coast
from terrain_pipeline import surface_domain_mosaic as mosaic
from terrain_pipeline import surface_multidomain_dynamic as forest
from terrain_pipeline.surface_domain_prepare import validate_surface_domains
from terrain_pipeline.surface_network_consumer import _payload


VERSION = "surface-engineering-prepare-v1"
MAX_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class EngineeringResources:
    max_retained_bytes: int = MAX_BYTES
    max_working_bytes: int = MAX_BYTES
    max_archive_members: int = 2048

    def __post_init__(self):
        for name, ceiling in (("max_retained_bytes", MAX_BYTES), ("max_working_bytes", MAX_BYTES),
                              ("max_archive_members", 2048)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid engineering resource: " + name)


def _cancel(cancel):
    if cancel is not None and cancel():
        raise InterruptedError("engineering prepare cancelled")


def _ids(evaluation, *, full_validation=False, saved_support=None):
    if full_validation:
        validate_surface_domains(evaluation)
    elif saved_support is not None:
        validate_surface_domains(evaluation, saved_support=saved_support)
    else:
        forest._domains(evaluation, full_validation=False)
    if evaluation["kind"] != "evaluation" or evaluation["status"] != "prepared":
        raise ValueError("accepted domain evaluation required")
    ids = [item["domain_id"] for item in evaluation["domains"]]
    if (not ids or any(type(domain_id) is not int for domain_id in ids) or
            ids != sorted(set(ids)) or ids != [item["domain_id"] for item in evaluation["candidate"]["domains"]]):
        raise ValueError("all declared domains required")
    return ids




def _size(record):
    return coast._retained(record, MAX_BYTES)


def _strict_header(header):
    try:
        expression = ast.parse(header.decode("latin1").strip(), mode="eval").body
        if not isinstance(expression, ast.Dict) or len(expression.keys) != 3:
            raise ValueError("NPY header dictionary required")
        keys = [ast.literal_eval(key) for key in expression.keys]
        if any(type(key) is not str for key in keys) or set(keys) != {"descr", "fortran_order", "shape"}:
            raise ValueError("NPY header duplicate/unknown keys")
        values = {key: ast.literal_eval(value) for key, value in zip(keys, expression.values)}
        if (type(values["descr"]) is not str or type(values["fortran_order"]) is not bool or
                values["fortran_order"] is not False or type(values["shape"]) is not tuple or
                len(values["shape"]) > 4 or any(type(size) is not int or not 0 <= size <= 1000000
                                               for size in values["shape"])):
            raise ValueError("NPY strict header types")
        return values["shape"], values["fortran_order"], np.dtype(values["descr"])
    except (SyntaxError, TypeError, UnicodeError, RecursionError) as error:
        raise ValueError("invalid NPY header") from error


def _planned_bytes(evaluation, outlets, local_q, variable_forcing):
    source = _size(evaluation)
    declared = []
    fine_cells = nodes = edges = 0
    drop_bytes = 0
    for entry in evaluation["domains"]:
        fine = entry["recovery"]["inputs"]["fine"]
        rows, columns = fine["shape_zx"]
        fine_cells += (rows - 1) * (columns - 1)
        declared.append({"grid": {"origin_x_m": fine["origin_x_m"], "origin_z_m": fine["origin_z_m"],
            "spacing_x_m": fine["spacing_x_m"], "spacing_z_m": fine["spacing_z_m"],
            "bbox_xz_m": [fine["origin_x_m"], fine["origin_x_m"] + (columns - 1) * fine["spacing_x_m"],
                          fine["origin_z_m"], fine["origin_z_m"] + (rows - 1) * fine["spacing_z_m"]]}})
        payload = _payload(entry["recovery"])
        active = np.flatnonzero(payload["active_mask"])
        nodes += len(active)
        edges += int(np.count_nonzero(payload["receiver"][active] >= 0))
        supplied = outlets[entry["domain_id"]]
        attachment = supplied["attachment"]
        record = {"prepared": attachment.prepared, "domain_id": attachment.domain_id,
                  "cross_section_xz_m": attachment.cross_section_xz_m,
                  "center_index": attachment.center_index, "datum": attachment.datum}
        usage = coast._preflight(record, coast._source_record(supplied["corridor"]),
                                coast._source_record(supplied["sea"]),
                                np.asarray(supplied["stations_z_m"]), coast.DropResources())
        drop_bytes += usage["retained_bytes_upper_bound"]
    cells = math.prod(mosaic._grid(declared)["shape_cells_zx"])
    local = np.asarray(local_q)
    if local.ndim != 2 or local.shape[1] != nodes or not len(local):
        raise ValueError("explicit global local Q required")
    dynamic = forest.hydraulics._preflight(nodes, edges, len(local), forest.hydraulics.ResourceLimits())
    mosaic_bytes = 2 * source + (cells + fine_cells) * 800
    forest_bytes = (len(declared) + 1) * source + fine_cells * 800 + dynamic["retained_bytes_upper_bound"]
    retained = source + mosaic_bytes + drop_bytes + forest_bytes
    if variable_forcing is not None:
        variable_local = np.asarray(variable_forcing["local_q_m3_s"])
        if variable_local.ndim != 2 or variable_local.shape[1] != nodes or not len(variable_local):
            raise ValueError("explicit variable global local Q required")
        steps = len(variable_local)
        retained += forest_bytes + fine_cells * 6 * 32 + (steps + 1) * nodes * 32
        retained += steps * (edges + 6 * len(declared) + nodes) * 16
        retained += _size({key: asdict(value) if key == "resources" else value
                           for key, value in variable_forcing.items()})
    return retained, retained * 2


def compose_surface_engineering(evaluation, domain_mosaic, drops, dynamic_forest, *, variable_storage=None,
                                resources=EngineeringResources(), cancel=None):
    """Compose already prepared components without replaying any preparation."""
    _cancel(cancel)
    if not isinstance(resources, EngineeringResources):
        raise ValueError("EngineeringResources required")
    ids = _ids(evaluation, full_validation=True)
    source_size = _size({"evaluation": evaluation, "mosaic": domain_mosaic, "drops": drops,
                         "forest": dynamic_forest, "variable_storage": variable_storage})
    if source_size > resources.max_retained_bytes or source_size * 2 > resources.max_working_bytes:
        raise ValueError("engineering retained preflight")
    record = {"algorithm_version": VERSION, "status": "prepared", "evaluation": evaluation,
              "domain_mosaic": domain_mosaic, "drops": list(drops), "dynamic_forest": dynamic_forest,
              "variable_storage": variable_storage,
              "domain_ids": ids, "resources": asdict(resources),
              "declared_node_envelope_complete": True, "physical_footprint_complete": False,
              "natural_outlets_certified": False, "full_dynamic_wave_prepared": False,
              "ready_for_3d": False}
    sealed = coast._freeze({**record, "identity_sha256": coast.fingerprint(record)})
    validate_surface_engineering(sealed)
    _cancel(cancel)
    return sealed


def prepare_surface_engineering(evaluation, outlets, *, conductance_m2_s, local_q_m3_s,
                                tailwater_m, dt_s, max_depth_m,
                                resources=EngineeringResources(), mosaic_resources=None,
                                forest_resources=forest.ForestResources(), variable_forcing=None,
                                cancel=None):
    """Build the complete mosaic, one real coast attachment per domain, and global forest."""
    if not isinstance(resources, EngineeringResources) or (cancel is not None and not callable(cancel)):
        raise ValueError("invalid engineering resources or cancel")
    _cancel(cancel)
    ids = _ids(evaluation, full_validation=True)
    if (not isinstance(outlets, dict) or len(outlets) != len(ids) or
            any(type(domain_id) is not int for domain_id in outlets) or set(outlets) != set(ids)):
        raise ValueError("exactly one explicit outlet per declared domain required")
    if (not isinstance(forest_resources, forest.ForestResources) or
            any(not isinstance(outlets[domain_id], dict) or
                set(outlets[domain_id]) != {"attachment", "corridor", "sea", "stations_z_m", "budget"} or
                not isinstance(outlets[domain_id]["attachment"], coast.RiverAttachment) or
                outlets[domain_id]["attachment"].domain_id != domain_id or
                outlets[domain_id]["attachment"].prepared["identity_sha256"] != evaluation["identity_sha256"]
                for domain_id in ids)):
        raise ValueError("explicit same-source outlets and resources required")
    if variable_forcing is not None and (not isinstance(variable_forcing, dict) or
            not {"conductance_m2_s", "local_q_m3_s", "tailwater_m", "dt_s", "max_depth_m"} <= set(variable_forcing) or
            set(variable_forcing) - {"conductance_m2_s", "local_q_m3_s", "tailwater_m", "dt_s", "max_depth_m", "resources"}):
        raise ValueError("explicit variable forcing required")
    input_size = _size({"evaluation": evaluation, "outlets": [
        {"attachment": outlets[domain_id]["attachment"].prepared,
         "corridor": coast._source_record(outlets[domain_id]["corridor"]),
         "sea": coast._source_record(outlets[domain_id]["sea"]),
         "stations": np.asarray(outlets[domain_id]["stations_z_m"])} for domain_id in ids],
         "conductance": np.asarray(conductance_m2_s), "local": np.asarray(local_q_m3_s),
         "tailwater": np.asarray(tailwater_m)})
    if input_size > resources.max_retained_bytes or input_size * 2 > resources.max_working_bytes:
        raise ValueError("engineering working preflight")
    retained, working = _planned_bytes(evaluation, outlets, local_q_m3_s, variable_forcing)
    if retained > resources.max_retained_bytes or working + input_size > resources.max_working_bytes:
        raise ValueError("engineering generated retained/working preflight")
    _cancel(cancel)
    options = {"cancel": cancel}
    if mosaic_resources is not None:
        options["resources"] = mosaic_resources
    domain_mosaic = mosaic.prepare_domain_mosaic(evaluation, **options)
    drops = []
    for domain_id in ids:
        _cancel(cancel)
        supplied = outlets[domain_id]
        if set(supplied) != {"attachment", "corridor", "sea", "stations_z_m", "budget"}:
            raise ValueError("explicit outlet attachment/sources/stations/budget required")
        if supplied["attachment"].domain_id != domain_id:
            raise ValueError("outlet domain mismatch")
        drops.append(coast.prepare_coast_drop(**supplied))
    _cancel(cancel)
    dynamic_forest = forest.prepare_surface_multidomain_dynamic(
        evaluation, conductance_m2_s=conductance_m2_s, local_q_m3_s=local_q_m3_s,
        tailwater_m=tailwater_m, dt_s=dt_s, max_depth_m=max_depth_m,
        resources=forest_resources, cancel=cancel)
    variable_storage = None
    if variable_forcing is not None:
        from terrain_pipeline import surface_variable_storage as variable
        variable_storage = variable.prepare_surface_variable_storage(dynamic_forest, **variable_forcing, cancel=cancel)
    return compose_surface_engineering(evaluation, domain_mosaic, drops, dynamic_forest,
                                       variable_storage=variable_storage, resources=resources, cancel=cancel)


def validate_surface_engineering(result):
    """Check nested static proofs and cross-product source, outlet and ledger binding."""
    required = {"algorithm_version", "status", "evaluation", "domain_mosaic", "drops", "variable_storage",
                "dynamic_forest", "domain_ids", "resources", "declared_node_envelope_complete",
                "physical_footprint_complete", "natural_outlets_certified", "full_dynamic_wave_prepared",
                "ready_for_3d", "identity_sha256"}
    if (set(result) != required or result["algorithm_version"] != VERSION or result["status"] != "prepared" or
            result["identity_sha256"] != coast.fingerprint({key: value for key, value in result.items()
                                                           if key != "identity_sha256"})):
        raise ValueError("engineering schema/identity mismatch")
    resources = EngineeringResources(**result["resources"])
    if _size(result) > resources.max_retained_bytes or _size(result) * 2 > resources.max_working_bytes:
        raise ValueError("engineering resource exceeded")
    if result["declared_node_envelope_complete"] is not True or any(result[name] is not False for name in
            ("physical_footprint_complete", "natural_outlets_certified", "full_dynamic_wave_prepared", "ready_for_3d")):
        raise ValueError("engineering scope mismatch")
    evaluation = result["evaluation"]
    saved_support = {}
    for mesh in result["domain_mosaic"]["domain_meshes"]:
        for identity, support in mesh["proof_h0_support"].items():
            if identity in saved_support:
                raise ValueError("duplicate engineering recovery support")
            saved_support[identity] = support
    ids = _ids(evaluation, saved_support=saved_support)
    if (any(type(value) is not int for value in result["domain_ids"]) or
            list(result["domain_ids"]) != ids or len(result["drops"]) != len(ids)):
        raise ValueError("omitted or duplicate domain")
    mosaic.validate_domain_mosaic(result["domain_mosaic"])
    forest.validate_surface_multidomain_dynamic(result["dynamic_forest"])
    identity = evaluation["identity_sha256"]
    domain_mosaic = result["domain_mosaic"]
    dynamic_forest = result["dynamic_forest"]
    if (domain_mosaic["declared_node_envelope_complete"] is not True or
            domain_mosaic["physical_footprint_complete"] is not False or
            domain_mosaic["natural_outlets_certified"] is not False or
            dynamic_forest["natural_outlets_certified"] is not False or
            dynamic_forest["full_dynamic_wave_prepared"] is not False):
        raise ValueError("nested engineering scope mismatch")
    if (domain_mosaic["evaluation"]["identity_sha256"] != identity or
            dynamic_forest["evaluation"]["identity_sha256"] != identity or
            domain_mosaic["candidate_identity_sha256"] != evaluation["candidate"]["identity_sha256"] or
            list(dynamic_forest["domain_ids"]) != ids):
        raise ValueError("mixed evaluation/candidate source")
    datum = evaluation["candidate"]["inputs"]["vertical_datum"]
    sea_level = evaluation["candidate"]["inputs"]["sea_level_elevation_m"]
    for domain_id, drop, entry in zip(ids, result["drops"], evaluation["domains"]):
        coast.validate_coast_drop(drop)
        attachment = drop["inputs"]["attachment"]
        terminal = drop["attachment"]
        if (type(attachment["domain_id"]) is not int or type(attachment["center_index"]) is not int or
                type(terminal["terminal_node"]) is not int or
                any(type(value) is not int for value in drop["usage"].values())):
            raise ValueError("strict outlet integer identity required")
        if (attachment["domain_id"] != domain_id or attachment["datum"] != datum or
                attachment["prepared"]["identity_sha256"] != identity or
                terminal["recovery_sha256"] != entry["recovery"]["identity_sha256"] or
                drop["inputs"]["sea"]["sea_level_m"] != sea_level or
                drop["inputs"]["corridor"]["sea_level_m"] != sea_level or
                not np.allclose(terminal["sea_water_xyz_m"][:, 1], sea_level, atol=1e-9, rtol=0)):
            raise ValueError("mixed domain/proof/datum/sea outlet")
        binding = dynamic_forest["bindings"][ids.index(domain_id)]
        boundary = np.flatnonzero(binding["boundary_mask"])
        center = attachment["center_index"]
        river = terminal["river_water_xyz_m"][center]
        if (binding["source_proof_sha256"] != terminal["recovery_sha256"] or len(boundary) != 1 or
                not np.allclose(binding["coords_xz_m"][boundary[0]], river[[0, 2]], atol=1e-9, rtol=0) or
                not np.isclose(binding["initial_stage_m"][boundary[0]], river[1], atol=1e-9, rtol=0)):
            raise ValueError("forest/drop terminal geometry or stage mismatch")
    if result["variable_storage"] is not None:
        from terrain_pipeline import surface_variable_storage as variable
        variable.validate_surface_variable_storage(result["variable_storage"])
        if result["variable_storage"]["source"]["identity_sha256"] != dynamic_forest["identity_sha256"]:
            raise ValueError("variable storage source differs from forest")
    return True


def query_surface_engineering(result, *, state_index=None, variable_state_index=None):
    validate_surface_engineering(result)
    dynamic = forest.query_surface_multidomain_dynamic(result["dynamic_forest"], state_index=state_index)
    variable_result = None
    if result["variable_storage"] is not None:
        from terrain_pipeline import surface_variable_storage as variable
        variable_result = variable.query_surface_variable_storage(result["variable_storage"],
                                                                  state_index=variable_state_index)
    elif variable_state_index is not None:
        raise ValueError("variable state requested without saved variable storage")
    domain_mosaic = result["domain_mosaic"]
    return coast._freeze({"domain_ids": result["domain_ids"], "mosaic_summary": domain_mosaic["summary"],
                          "surface_geometry": {"nodes": domain_mosaic["nodes"], "cells": domain_mosaic["cells"],
                                               "triangles": domain_mosaic["triangles"],
                                               "wet_cells": domain_mosaic["wet_cells"],
                                               "hydrologic_domain_owner": domain_mosaic["hydrologic_domain_owner"]},
                          "outlet_geometry": [drop["arrays"] for drop in result["drops"]],
                          "outlets": [drop["attachment"] for drop in result["drops"]],
                          "drop_ledgers": [drop["ledger"] for drop in result["drops"]],
                          "dynamic": dynamic, "domain_ledger_m3": result["dynamic_forest"]["domain_ledger_m3"],
                          "constant_signed_edge_q_m3_s": result["dynamic_forest"]["dynamic"]["qedges_m3_s"],
                          "variable_signed_edge_q_m3_s": None if result["variable_storage"] is None else
                          result["variable_storage"]["qedges_m3_s"],
                          "variable_domain_ledger_m3": None if result["variable_storage"] is None else
                          result["variable_storage"]["domain_ledger_m3"],
                          "node_graph": {"node_keys": result["dynamic_forest"]["node_keys"],
                                         "edges": result["dynamic_forest"]["edges"],
                                         "coords_xz_m": result["dynamic_forest"]["dynamic"]["inputs"]["coords_m"]},
                          "variable_storage": variable_result})


def save_surface_engineering(result, path):
    validate_surface_engineering(result)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = coast._tree(result, arrays)
    metadata = coast._json({"format": VERSION + "-npy-v1", "tree": tree}).encode("ascii")
    if (len(arrays) + 1 > result["resources"]["max_archive_members"] or len(metadata) > 8 * 1024 * 1024 or
            _size(result) > result["resources"]["max_retained_bytes"] or
            _size(result) * 2 > result["resources"]["max_working_bytes"]):
        raise ValueError("engineering archive metadata/member cap")
    descriptor, temporary = tempfile.mkstemp(prefix=".engineering-", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("metadata.json", metadata)
                for name, array in arrays.items():
                    with archive.open(name, "w") as member:
                        np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            if stream.tell() > MAX_BYTES:
                raise ValueError("engineering file cap")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination


def load_surface_engineering(path):
    """Preflight every ZIP/NPY header before allocating nested array payloads."""
    with Path(path).open("rb") as retained, zipfile.ZipFile(retained) as archive:
        if os.fstat(retained.fileno()).st_size > MAX_BYTES:
            raise ValueError("engineering file cap")
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if (len(names) > 2048 or len(names) != len(set(names)) or
                any(info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1 for info in infos) or
                sum(info.file_size for info in infos) > MAX_BYTES or "metadata.json" not in names or
                archive.getinfo("metadata.json").file_size > 8 * 1024 * 1024):
            raise ValueError("engineering ZIP preflight")
        metadata = json.loads(archive.read("metadata.json"), object_pairs_hook=coast._pairs,
                              parse_constant=coast._constant)
        if set(metadata) != {"format", "tree"} or metadata["format"] != VERSION + "-npy-v1":
            raise ValueError("engineering metadata mismatch")
        references = {}
        def inspect(value, depth=0):
            if depth > 80:
                raise ValueError("engineering nesting cap")
            if isinstance(value, dict) and "$array" in value:
                name = value["$array"]
                shape = value["shape"]
                if (set(value) != {"$array", "shape", "dtype", "sha256"} or not isinstance(name, str) or
                        name in references or not name.startswith("array_") or not name.endswith(".npy") or
                        "/" in name or "\\" in name or not isinstance(shape, list) or len(shape) > 4 or
                        any(type(size) is not int or size < 0 or size > 1000000 for size in shape) or
                        math.prod(shape) > 1000000):
                    raise ValueError("engineering array reference cap")
                if (not isinstance(value["dtype"], str) or not isinstance(value["sha256"], str) or
                        len(value["sha256"]) != 64 or any(character not in "0123456789abcdef"
                                                           for character in value["sha256"])):
                    raise ValueError("engineering dtype/hash metadata mismatch")
                dtype = np.dtype(value["dtype"])
                if dtype.kind not in "bifu" or dtype.itemsize > 8:
                    raise ValueError("pickle/object or unsupported dtype")
                references[name] = value
            elif isinstance(value, dict):
                for child in value.values():
                    inspect(child, depth + 1)
            elif isinstance(value, list):
                for child in value:
                    inspect(child, depth + 1)
        inspect(metadata["tree"])
        if set(names) != {"metadata.json"} | set(references):
            raise ValueError("engineering archive members mismatch")
        resources = EngineeringResources(**metadata["tree"]["resources"])
        if (len(names) > resources.max_archive_members or
                sum(info.file_size for info in infos) > resources.max_retained_bytes or
                sum(info.file_size for info in infos) * 2 > resources.max_working_bytes):
            raise ValueError("engineering saved resource preflight")
        for name, reference in references.items():
            with archive.open(name) as member:
                if np.lib.format.read_magic(member) != (1, 0):
                    raise ValueError("NPY v1 required")
                length = member.read(2)
                if len(length) != 2 or int.from_bytes(length, "little") > 2038:
                    raise ValueError("NPY header cap")
                header = member.read(int.from_bytes(length, "little"))
                if len(header) != int.from_bytes(length, "little"):
                    raise ValueError("truncated NPY header")
                shape, fortran, dtype = _strict_header(header)
                if (list(shape) != reference["shape"] or dtype.str != reference["dtype"] or
                        dtype.kind not in "bifu" or fortran or
                        member.tell() + math.prod(shape) * dtype.itemsize != archive.getinfo(name).file_size):
                    raise ValueError("NPY header/payload mismatch")
        arrays = {}
        for name, reference in references.items():
            with archive.open(name) as member:
                array = np.load(member, allow_pickle=False)
            if coast._array_hash(array) != reference["sha256"]:
                raise ValueError("engineering array hash mismatch")
            arrays[name] = array
    def decode(value):
        if isinstance(value, dict) and "$array" in value:
            return arrays[value["$array"]]
        if isinstance(value, dict):
            return {key: decode(child) for key, child in value.items()}
        if isinstance(value, list):
            return [decode(child) for child in value]
        return value
    result = coast._freeze(decode(metadata["tree"]))
    validate_surface_engineering(result)
    return result
