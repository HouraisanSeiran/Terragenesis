"""Stage-dependent lumped storage on the complete accepted surface forest."""

from dataclasses import dataclass
from collections.abc import Mapping
import ast
import json
import math
import os
from pathlib import Path
import tempfile
import struct
import zipfile

import numpy as np

from terrain_pipeline import surface_fine_mosaic as mosaic
from terrain_pipeline import surface_multidomain_dynamic as forest

VERSION = "surface-variable-storage-v1"
GEOMETRY = "wet-cell-triangle-vertex-lumped-prisms"
MAX_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class StorageResources:
    max_nodes: int = 4096
    max_edges: int = 16384
    max_steps: int = 4096
    max_wet_cells: int = 100000
    max_work: int = 2000000
    max_retained_bytes: int = MAX_BYTES
    max_working_bytes: int = MAX_BYTES

    def __post_init__(self):
        ceilings = (4096, 16384, 4096, 100000, 2000000, MAX_BYTES, MAX_BYTES)
        for value, ceiling in zip(vars(self).values(), ceilings):
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid storage resource")


def _geometry(source):
    beds = []
    weights = []
    owners = []
    offsets = [0]
    for binding in source["bindings"]:
        fine = binding["source_mosaic"]
        triangle_ids = (2 * binding["wet_cell_ids"][:, None] + np.arange(2)).ravel()
        corners = fine["triangles"][triangle_ids]
        heights = fine["nodes"]["h2_m"][corners].reshape(-1, 6)
        area = fine["grid"]["spacing_x_m"] * fine["grid"]["spacing_z_m"]
        for node in range(len(binding["node_flat_ids"])):
            values = heights[binding["wet_cell_owner"] == node].ravel()
            if not len(values) or not np.all(np.isfinite(values)):
                raise ValueError("empty or nonfinite node support")
            beds.append(values)
            weights.append(np.full(len(values), area / 6))
            owners.append(np.full(len(values), len(offsets) - 1, np.int64))
            offsets.append(offsets[-1] + len(values))
    return (np.asarray(offsets, np.int64), np.concatenate(beds).astype(float),
            np.concatenate(weights).astype(float), np.concatenate(owners))


def _knots(offsets, beds, weights):
    stages = []
    volumes = []
    knot_offsets = [0]
    for index in range(len(offsets) - 1):
        start, stop = offsets[index:index + 2]
        node_beds = beds[start:stop]
        node_weights = weights[start:stop]
        unique = np.unique(node_beds)
        stages.append(unique)
        volumes.append(np.asarray([volume(stage, node_beds, node_weights) for stage in unique]))
        knot_offsets.append(knot_offsets[-1] + len(unique))
    return np.asarray(knot_offsets, np.int64), np.concatenate(stages), np.concatenate(volumes)


def volume(stage, beds, weights):
    return float(np.dot(weights, np.maximum(stage - beds, 0)))


def _invert(amount, beds, weights):
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("nonfinite or negative storage cannot be inverted")
    if amount == 0:
        return float(np.min(beds))
    order = np.argsort(beds)
    sorted_beds = beds[order]
    sorted_weights = weights[order]
    active_weight = 0.
    previous_bed = float(sorted_beds[0])
    accumulated = 0.
    for bed, weight in zip(sorted_beds, sorted_weights):
        bed = float(bed)
        candidate = accumulated + active_weight * (bed - previous_bed)
        if amount <= candidate and active_weight > 0:
            return previous_bed + (amount - accumulated) / active_weight
        accumulated = candidate
        active_weight += float(weight)
        previous_bed = bed
    return previous_bed + (amount - accumulated) / active_weight


def _inputs(source, conductance_m2_s, local_q_m3_s, tailwater_m, dt_s, max_depth_m, resources):
    if (type(dt_s) not in (int, float) or type(max_depth_m) not in (int, float)):
        raise ValueError("physical time and maximum depth must be real scalars, not booleans")
    nodes = len(source["node_keys"])
    edges = len(source["edges"])
    local = np.asarray(local_q_m3_s)
    tailwater = np.asarray(tailwater_m)
    boundary = source["dynamic"]["inputs"]["boundary_mask"]
    initial = source["dynamic"]["inputs"]["initial_stage_m"]
    conductance = np.asarray(conductance_m2_s)
    if (local.ndim != 2 or local.shape[1] != nodes or not 1 <= len(local) <= resources.max_steps or
            tailwater.shape != (len(local) + 1, int(boundary.sum())) or
            conductance.shape != (edges,) or any(value.dtype.kind not in "fiu" for value in
            (local, tailwater, conductance)) or nodes > resources.max_nodes or edges > resources.max_edges or
            len(local) * (nodes + edges) > resources.max_work):
        raise ValueError("forcing shape or resource limit")
    if (not all(np.all(np.isfinite(value)) for value in (local, tailwater, conductance)) or
            np.any(conductance <= 0) or np.any(local[:, boundary] != 0) or
            not np.array_equal(tailwater[0], initial[boundary]) or
            type(dt_s) is bool or type(max_depth_m) is bool or
            not math.isfinite(dt_s) or dt_s <= 0 or not math.isfinite(max_depth_m) or max_depth_m <= 0 or
            not math.isfinite(dt_s * len(local))):
        raise ValueError("invalid forcing, tailwater or physical time")
    if sum(len(item["wet_cell_ids"]) for item in source["bindings"]) > resources.max_wet_cells:
        raise ValueError("wet-cell resource limit")
    return (np.asarray(conductance, dtype=float), np.asarray(local, dtype=float),
            np.asarray(tailwater, dtype=float), boundary, initial)


def _preflight(source, local_q_m3_s, resources):
    if not isinstance(source, dict) and not hasattr(source, "keys"):
        raise ValueError("saved forest required")
    bindings = source["bindings"]
    nodes = len(source["node_keys"])
    edges = len(source["edges"])
    local = np.asarray(local_q_m3_s)
    if local.ndim != 2:
        raise ValueError("local Q must be two dimensional")
    steps = len(local)
    wet = sum(len(binding["wet_cell_ids"]) for binding in bindings)
    if (nodes > resources.max_nodes or edges > resources.max_edges or
            wet > resources.max_wet_cells or steps > resources.max_steps or
            steps * (nodes + edges) > resources.max_work):
        raise ValueError("storage resource limit")
    source_bytes = mosaic._size(source)
    support_bytes = wet * 6 * 48 + 2 * (nodes + 1) * 8
    state_bytes = (steps + 1) * nodes * 16 + steps * (edges + 6 * len(bindings)) * 8
    forcing_bytes = steps * nodes * 8 + (steps + 1) * len(bindings) * 8
    if (source_bytes + support_bytes + state_bytes + forcing_bytes > resources.max_retained_bytes or
            2 * source_bytes + 3 * support_bytes + 2 * state_bytes + 2 * forcing_bytes >
            resources.max_working_bytes):
        raise ValueError("storage byte resource preflight")


def _advance(source, offsets, beds, weights, conductance, local, tailwater, dt_s, max_depth_m, cancel):
    edges = source["edges"]
    boundary = source["dynamic"]["inputs"]["boundary_mask"]
    initial = source["dynamic"]["inputs"]["initial_stage_m"]
    node_bed = source["dynamic"]["inputs"]["bed_m"]
    count = len(initial)
    min_bed = np.array([beds[offsets[index]:offsets[index + 1]].min() for index in range(count)])
    minimum_area = np.array([weights[offsets[index]:offsets[index + 1]][
        beds[offsets[index]:offsets[index + 1]] == min_bed[index]].sum() for index in range(count)])
    incident = np.zeros(count)
    np.add.at(incident, edges[:, 0], conductance)
    np.add.at(incident, edges[:, 1], conductance)
    if np.any(dt_s * incident[~boundary] / minimum_area[~boundary] > 1):
        raise ValueError("dt*incident K/minimum effective area exceeds one")
    if np.any(initial < min_bed) or np.any(initial - node_bed > max_depth_m):
        raise ValueError("initial stage outside support/depth")
    stages = [np.array(initial, float)]
    storage = np.array([volume(initial[index], beds[offsets[index]:offsets[index + 1]],
                               weights[offsets[index]:offsets[index + 1]]) for index in range(count)])
    storage[boundary] = 0
    storages = [storage]
    fluxes = []
    ledgers = []
    domain_ledgers = []
    status = "completed"
    failure = None
    for step in range(len(local)):
        if cancel is not None and cancel():
            status = "cancelled"
            break
        with np.errstate(over="ignore", invalid="ignore"):
            flux = conductance * (stages[-1][edges[:, 0]] - stages[-1][edges[:, 1]])
            net = np.zeros(count)
            np.add.at(net, edges[:, 0], -flux)
            np.add.at(net, edges[:, 1], flux)
            next_storage = storages[-1] + dt_s * (local[step] + net)
            next_storage[boundary] = 0
        reason = None
        if not np.all(np.isfinite(flux)) or not np.all(np.isfinite(next_storage)):
            reason = "arithmetic_nonfinite"
        elif np.any(next_storage[~boundary] < 0):
            reason = "negative_storage"
        next_stage = np.full(count, np.nan)
        if reason is None:
            for index in np.flatnonzero(~boundary):
                start, stop = offsets[index:index + 2]
                next_stage[index] = _invert(next_storage[index], beds[start:stop], weights[start:stop])
            next_stage[boundary] = tailwater[step + 1]
            if not np.all(np.isfinite(next_stage)):
                reason = "arithmetic_nonfinite"
            elif np.any(next_stage < min_bed) or np.any(next_stage - node_bed > max_depth_m):
                reason = "max_depth_or_boundary_bed"
        if reason is not None:
            status = "failed"
            failure = {"step_n": step, "reason": reason}
            break
        rows = []
        for domain in range(len(source["domain_ids"])):
            first, last = source["node_offsets"][domain:domain + 2]
            domain_boundary = boundary[first:last]
            before = float(storages[-1][first:last].sum())
            after = float(next_storage[first:last].sum())
            local_volume = float(dt_s * local[step, first:last][~domain_boundary].sum())
            boundary_volume = float(-dt_s * net[first:last][domain_boundary].sum())
            rows.append((before, local_volume, boundary_volume, after, after - before,
                         after - before - local_volume - boundary_volume))
        domain_ledgers.append(rows)
        ledgers.append(np.sum(rows, axis=0))
        stages.append(next_stage)
        storages.append(next_storage)
        fluxes.append(flux)
    return {"status": status, "committed_steps": len(fluxes), "failed_step": failure,
            "stage_m": np.asarray(stages), "storage_m3": np.asarray(storages),
            "qedges_m3_s": np.asarray(fluxes).reshape(-1, len(edges)),
            "time_s": np.arange(len(stages), dtype=float) * dt_s,
            "ledger_m3": np.asarray(ledgers).reshape(-1, 6),
            "domain_ledger_m3": np.asarray(domain_ledgers).reshape(-1, len(source["domain_ids"]), 6)}


def prepare_surface_variable_storage(source, *, conductance_m2_s, local_q_m3_s, tailwater_m,
                                     dt_s, max_depth_m, resources=StorageResources(), cancel=None):
    """Build vertex-prism storage from a validated saved forest, then advance all domains."""
    if not isinstance(resources, StorageResources) or (cancel is not None and not callable(cancel)):
        raise ValueError("invalid resources or cancel callback")
    _preflight(source, local_q_m3_s, resources)
    forest.validate_surface_multidomain_dynamic(source)
    conductance, local, tailwater, _, _ = _inputs(source, conductance_m2_s, local_q_m3_s,
                                                   tailwater_m, dt_s, max_depth_m, resources)
    offsets, beds, weights, owners = _geometry(source)
    knot_offsets, knot_stage, knot_volume = _knots(offsets, beds, weights)
    estimate = mosaic._size(source) + local.nbytes * 4 + tailwater.nbytes + beds.nbytes * 6
    if estimate > resources.max_retained_bytes or estimate * 2 > resources.max_working_bytes:
        raise ValueError("storage retained/working resource limit")
    result = _advance(source, offsets, beds, weights, conductance, local, tailwater,
                      dt_s, max_depth_m, cancel)
    record = {"algorithm_version": VERSION, "geometry": GEOMETRY, "source": source,
              "resources": vars(resources), "support_offsets": offsets, "support_bed_m": beds,
              "support_weight_m2": weights, "support_owner": owners,
              "knot_offsets": knot_offsets, "knot_stage_m": knot_stage, "knot_volume_m3": knot_volume,
              "conductance_m2_s": conductance,
              "local_q_m3_s": local, "tailwater_m": tailwater, "dt_s": float(dt_s),
              "max_depth_m": float(max_depth_m), "natural_outlets_certified": False,
              "full_dynamic_wave_prepared": False, **result}
    sealed = mosaic._seal(record)
    validate_surface_variable_storage(sealed)
    return sealed


def validate_surface_variable_storage(record):
    """Prove saved support and step equations without preparing or advancing."""
    try:
        resources = StorageResources(**record["resources"])
        _preflight(record["source"], record["local_q_m3_s"], resources)
        retained_bytes = mosaic._size(record)
        if retained_bytes > resources.max_retained_bytes or retained_bytes * 2 > resources.max_working_bytes:
            raise ValueError("storage byte resource limit")
        required = {"algorithm_version", "geometry", "source", "resources", "support_offsets",
                    "support_bed_m", "support_weight_m2", "support_owner", "knot_offsets",
                    "knot_stage_m", "knot_volume_m3", "conductance_m2_s", "local_q_m3_s",
                    "tailwater_m", "dt_s", "max_depth_m", "natural_outlets_certified",
                    "full_dynamic_wave_prepared", "status", "committed_steps", "failed_step",
                    "stage_m", "storage_m3", "qedges_m3_s", "time_s", "ledger_m3",
                    "domain_ledger_m3", "identity_sha256"}
        if (set(record) != required or record["algorithm_version"] != VERSION or
                record["geometry"] != GEOMETRY or record["natural_outlets_certified"] is not False or
                record["full_dynamic_wave_prepared"] is not False or
                record["identity_sha256"] != mosaic._identity({key: value for key, value in record.items()
                                                               if key != "identity_sha256"})):
            raise ValueError("storage schema or identity mismatch")
        forest.validate_surface_multidomain_dynamic(record["source"])
        source = record["source"]
        nodes = len(source["node_keys"])
        offsets = record["support_offsets"]
        beds = record["support_bed_m"]
        weights = record["support_weight_m2"]
        owners = record["support_owner"]
        knot_offsets = record["knot_offsets"]
        knot_stages = record["knot_stage_m"]
        knot_volumes = record["knot_volume_m3"]
        wet_count = sum(len(binding["wet_cell_ids"]) for binding in source["bindings"])
        if (wet_count > resources.max_wet_cells or nodes > resources.max_nodes or
                len(source["edges"]) > resources.max_edges or
                offsets.dtype != np.dtype("int64") or offsets.shape != (nodes + 1,) or
                not np.array_equal(offsets[[0, -1]], [0, 6 * wet_count]) or
                beds.dtype != np.dtype("float64") or beds.shape != (6 * wet_count,) or
                weights.dtype != np.dtype("float64") or weights.shape != beds.shape or
                owners.dtype != np.dtype("int64") or owners.shape != beds.shape or
                knot_offsets.dtype != np.dtype("int64") or knot_offsets.shape != offsets.shape or
                knot_stages.dtype != np.dtype("float64") or knot_volumes.dtype != np.dtype("float64") or
                knot_stages.ndim != 1 or knot_volumes.shape != knot_stages.shape or
                knot_offsets[0] != 0 or knot_offsets[-1] != len(knot_stages) or
                np.any(np.diff(offsets) <= 0) or np.any(np.diff(knot_offsets) <= 0) or
                not np.all(np.isfinite(beds)) or not np.all(np.isfinite(weights)) or
                not np.all(np.isfinite(knot_stages)) or not np.all(np.isfinite(knot_volumes))):
            raise ValueError("invalid saved support dimensions")
        position = 0
        for binding in source["bindings"]:
            fine = binding["source_mosaic"]
            triangle_ids = (2 * binding["wet_cell_ids"][:, None] + np.arange(2)).ravel()
            triangle_beds = fine["nodes"]["h2_m"][fine["triangles"][triangle_ids]].reshape(-1, 6)
            area = fine["grid"]["spacing_x_m"] * fine["grid"]["spacing_z_m"]
            for local_node in range(len(binding["node_flat_ids"])):
                start, stop = offsets[position:position + 2]
                contribution = triangle_beds[binding["wet_cell_owner"] == local_node].ravel()
                if (not np.array_equal(beds[start:stop], contribution) or
                        not np.all(weights[start:stop] == area / 6) or
                        not np.all(owners[start:stop] == position)):
                    raise ValueError("saved support differs from source triangles")
                first, last = knot_offsets[position:position + 2]
                stages = knot_stages[first:last]
                curve = knot_volumes[first:last]
                if (not np.array_equal(stages, np.unique(contribution)) or curve[0] != 0 or
                        not np.all(np.diff(curve) > 0) or
                        not np.allclose(curve, [volume(stage, beds[start:stop], weights[start:stop])
                                                for stage in stages], rtol=1e-12, atol=1e-12)):
                    raise ValueError("saved knot curve differs from support")
                position += 1
        for name in ("conductance_m2_s", "local_q_m3_s", "tailwater_m", "stage_m", "storage_m3",
                     "qedges_m3_s", "time_s", "ledger_m3", "domain_ledger_m3"):
            if record[name].dtype != np.dtype("float64"):
                raise ValueError("storage array dtype mismatch: " + name)
        if (type(record["committed_steps"]) is not int or type(record["dt_s"]) is not float or
                type(record["max_depth_m"]) is not float):
            raise ValueError("storage scalar type mismatch")
        conductance, local, tailwater, _, _ = _inputs(record["source"], record["conductance_m2_s"],
            record["local_q_m3_s"], record["tailwater_m"], record["dt_s"], record["max_depth_m"], resources)
        committed = record["committed_steps"]
        if not 0 <= committed <= len(local):
            raise ValueError("invalid committed prefix")
        status = record["status"]
        failure = record["failed_step"]
        if (status not in ("completed", "cancelled", "failed") or
                (status == "completed" and committed != len(local)) or
                (status == "cancelled" and committed >= len(local)) or
                (status == "failed" and (committed >= len(local) or
                 not isinstance(failure, Mapping) or set(failure) != {"step_n", "reason"} or
                 type(failure["step_n"]) is not int or failure["step_n"] != committed or
                 failure["reason"] not in ("arithmetic_nonfinite", "negative_storage", "max_depth_or_boundary_bed"))) or
                (status != "failed" and failure is not None)):
            raise ValueError("invalid prefix status")
        boundary = source["dynamic"]["inputs"]["boundary_mask"]
        initial = source["dynamic"]["inputs"]["initial_stage_m"]
        node_bed = source["dynamic"]["inputs"]["bed_m"]
        edges = source["edges"]
        dt_s = record["dt_s"]
        min_bed = np.array([beds[offsets[index]:offsets[index + 1]].min() for index in range(nodes)])
        min_area = np.array([weights[offsets[index]:offsets[index + 1]][
            beds[offsets[index]:offsets[index + 1]] == min_bed[index]].sum() for index in range(nodes)])
        incident = np.zeros(nodes)
        np.add.at(incident, edges[:, 0], conductance)
        np.add.at(incident, edges[:, 1], conductance)
        if (np.any(dt_s * incident[~boundary] / min_area[~boundary] > 1) or
                np.any(initial < min_bed) or np.any(initial - node_bed > record["max_depth_m"])):
            raise ValueError("invalid stability or initial support")
        expected_shapes = {"stage_m": (committed + 1, nodes), "storage_m3": (committed + 1, nodes),
            "qedges_m3_s": (committed, len(edges)), "time_s": (committed + 1,),
            "ledger_m3": (committed, 6), "domain_ledger_m3": (committed, len(source["domain_ids"]), 6)}
        if any(record[name].shape != shape for name, shape in expected_shapes.items()):
            raise ValueError("saved state dimensions")
        if (not np.all(np.isfinite(record["stage_m"])) or not np.all(np.isfinite(record["storage_m3"])) or
                not np.all(np.isfinite(record["qedges_m3_s"])) or
                np.any(record["storage_m3"] < 0) or
                np.any(record["stage_m"] < min_bed) or
                np.any(record["stage_m"] - node_bed > record["max_depth_m"]) or
                not np.array_equal(record["time_s"], np.arange(committed + 1) * dt_s) or
                not np.array_equal(record["stage_m"][0], initial) or
                not np.array_equal(record["stage_m"][:, boundary], tailwater[:committed + 1]) or
                np.any(record["storage_m3"][:, boundary] != 0)):
            raise ValueError("saved stage/time/boundary mismatch")
        for index in range(nodes):
            start, stop = offsets[index:index + 2]
            for stage, amount in zip(record["stage_m"][:, index], record["storage_m3"][:, index]):
                if not boundary[index] and not math.isclose(amount, volume(stage, beds[start:stop], weights[start:stop]),
                                                            abs_tol=1e-10, rel_tol=1e-12):
                    raise ValueError("saved stage-volume mismatch")
                if not boundary[index] and amount == 0 and stage != min_bed[index]:
                    raise ValueError("noncanonical dry stage")
        for step in range(committed + (status == "failed")):
            stage = record["stage_m"][step]
            flux = conductance * (stage[edges[:, 0]] - stage[edges[:, 1]])
            net = np.zeros(nodes)
            np.add.at(net, edges[:, 0], -flux)
            np.add.at(net, edges[:, 1], flux)
            prediction = record["storage_m3"][step] + dt_s * (local[step] + net)
            prediction[boundary] = 0
            if step == committed:
                reason = "arithmetic_nonfinite" if (not np.all(np.isfinite(flux)) or
                    not np.all(np.isfinite(prediction))) else None
                if reason is None and np.any(prediction[~boundary] < 0):
                    reason = "negative_storage"
                if reason is None:
                    predicted_stage = np.array([_invert(prediction[index], beds[offsets[index]:offsets[index + 1]],
                                                        weights[offsets[index]:offsets[index + 1]])
                                                if not boundary[index] else tailwater[step + 1, list(np.flatnonzero(boundary)).index(index)]
                                                for index in range(nodes)])
                    if not np.all(np.isfinite(predicted_stage)):
                        reason = "arithmetic_nonfinite"
                    elif np.any(predicted_stage < min_bed) or np.any(predicted_stage - node_bed > record["max_depth_m"]):
                        reason = "max_depth_or_boundary_bed"
                if reason != failure["reason"]:
                    raise ValueError("failed-step reason mismatch")
                break
            if (not np.allclose(record["qedges_m3_s"][step], flux, atol=1e-12, rtol=1e-12) or
                    not np.allclose(record["storage_m3"][step + 1], prediction, atol=1e-10, rtol=1e-12)):
                raise ValueError("edge flux or Euler volume mismatch")
            rows = []
            for domain in range(len(source["domain_ids"])):
                first, last = source["node_offsets"][domain:domain + 2]
                domain_boundary = boundary[first:last]
                before = float(record["storage_m3"][step, first:last].sum())
                after = float(prediction[first:last].sum())
                local_volume = float(dt_s * local[step, first:last][~domain_boundary].sum())
                inward = float(-dt_s * net[first:last][domain_boundary].sum())
                rows.append((before, local_volume, inward, after, after - before,
                             after - before - local_volume - inward))
            if (not np.allclose(record["domain_ledger_m3"][step], rows, atol=1e-10, rtol=1e-12) or
                    not np.allclose(record["ledger_m3"][step], np.sum(rows, axis=0), atol=1e-10, rtol=1e-12)):
                raise ValueError("domain or global ledger mismatch")
            if np.any(np.abs(record["domain_ledger_m3"][step, :, 5]) > 1e-9) or abs(record["ledger_m3"][step, 5]) > 1e-9:
                raise ValueError("ledger residual exceeds tolerance")
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("invalid variable storage record") from error


def query_surface_variable_storage(record, *, state_index=None):
    validate_surface_variable_storage(record)
    if state_index is not None and (type(state_index) is not int or
                                    not 0 <= state_index <= record["committed_steps"]):
        raise ValueError("state index outside committed prefix")
    selection = slice(None) if state_index is None else state_index
    return mosaic._freeze({"node_keys": record["source"]["node_keys"],
                           "stage_m": record["stage_m"][selection],
                           "storage_m3": record["storage_m3"][selection],
                           "time_s": record["time_s"][selection], "status": record["status"]})


def save_surface_variable_storage(record, path):
    validate_surface_variable_storage(record)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = mosaic._tree(record, arrays)
    manifest = mosaic._json({"format_version": 1, "tree": tree, "tree_sha256": mosaic._identity(tree)})
    descriptor, temporary = tempfile.mkstemp(prefix=".variable-storage-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w+b") as stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", manifest)
                for name, array in arrays.items():
                    with archive.open(name, "w") as member:
                        np.lib.format.write_array(member, np.ascontiguousarray(array), version=(1, 0),
                                                  allow_pickle=False)
            if stream.tell() > MAX_BYTES:
                raise ValueError("storage bundle cap")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        return destination
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_surface_variable_storage(path):
    """Read a bounded, strict archive and prove its saved algebra; no generation."""
    try:
        with Path(path).open("rb") as retained, zipfile.ZipFile(retained) as archive:
            if os.fstat(retained.fileno()).st_size > MAX_BYTES:
                raise ValueError("storage bundle cap")
            mosaic._preflight_archive(archive)
            manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=mosaic._pairs,
                                  parse_constant=mosaic._constant)
            if (set(manifest) != {"format_version", "tree", "tree_sha256"} or
                    type(manifest["format_version"]) is not int or manifest["format_version"] != 1 or
                    manifest["tree_sha256"] != mosaic._identity(manifest["tree"])):
                raise ValueError("storage manifest mismatch")
            tree = manifest["tree"]
            if set(tree) != {"algorithm_version", "geometry", "source", "resources", "support_offsets",
                             "support_bed_m", "support_weight_m2", "support_owner", "knot_offsets",
                             "knot_stage_m", "knot_volume_m3", "conductance_m2_s", "local_q_m3_s",
                             "tailwater_m", "dt_s", "max_depth_m", "natural_outlets_certified",
                             "full_dynamic_wave_prepared", "status", "committed_steps", "failed_step",
                             "stage_m", "storage_m3", "qedges_m3_s", "time_s", "ledger_m3",
                             "domain_ledger_m3", "identity_sha256"}:
                raise ValueError("storage tree schema")
            resources = StorageResources(**tree["resources"])
            archive_bytes = sum(info.file_size for info in archive.infolist())
            if (archive_bytes > resources.max_retained_bytes or
                    archive_bytes * 2 > resources.max_working_bytes):
                raise ValueError("storage archive resource")
            references = {}
            def collect(value):
                if isinstance(value, dict) and "$array" in value:
                    name = value["$array"]
                    if (set(value) != {"$array", "shape", "dtype", "sha256"} or
                            type(name) is not str or name in references or
                            type(value["shape"]) is not list or len(value["shape"]) > 5 or
                            any(type(size) is not int or size < 0 for size in value["shape"]) or
                            type(value["dtype"]) is not str or type(value["sha256"]) is not str):
                        raise ValueError("invalid array reference")
                    references[name] = value
                elif isinstance(value, dict):
                    for child in value.values():
                        collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
            collect(tree)
            if set(references) != set(archive.namelist()) - {"manifest.json"}:
                raise ValueError("missing or unused array")
            for name, reference in references.items():
                with archive.open(name) as member:
                    shape, fortran, dtype = _strict_header(member, archive.getinfo(name).file_size)
                    if (list(shape) != reference["shape"] or dtype.str != reference["dtype"] or
                            fortran or dtype.hasobject or dtype.kind not in "biuf" or
                            member.tell() + math.prod(shape) * dtype.itemsize != archive.getinfo(name).file_size):
                        raise ValueError("array header mismatch")
            def decode(value):
                if isinstance(value, dict) and "$array" in value:
                    with archive.open(value["$array"]) as member:
                        array = np.load(member, allow_pickle=False)
                    if mosaic.array_hash(array) != value["sha256"]:
                        raise ValueError("array hash mismatch")
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            record = decode(tree)
        validate_surface_variable_storage(record)
        return mosaic._freeze(record)
    except (OSError, KeyError, TypeError, IndexError, AttributeError, EOFError,
            OverflowError, RecursionError, SyntaxError, json.JSONDecodeError, zipfile.BadZipFile) as error:
        raise ValueError("invalid variable storage bundle") from error


def _strict_header(member, member_bytes):
    if np.lib.format.read_magic(member) != (1, 0):
        raise ValueError("NPY v1 required")
    raw_length = member.read(2)
    if len(raw_length) != 2:
        raise ValueError("truncated NPY header")
    length = struct.unpack("<H", raw_length)[0]
    if length > 8192 or member.tell() + length > member_bytes:
        raise ValueError("NPY header resource limit")
    raw = member.read(length)
    if len(raw) != length or not raw.endswith(b"\n"):
        raise ValueError("invalid NPY header framing")
    expression = ast.parse(raw.decode("latin1").strip(), mode="eval").body
    if not isinstance(expression, ast.Dict):
        raise ValueError("NPY header must be a literal dictionary")
    keys = [ast.literal_eval(key) for key in expression.keys]
    if len(keys) != 3 or set(keys) != {"descr", "fortran_order", "shape"}:
        raise ValueError("NPY header keys")
    header = ast.literal_eval(expression)
    shape = header["shape"]
    if (type(header["fortran_order"]) is not bool or header["fortran_order"] is not False or
            type(shape) is not tuple or len(shape) > 5 or
            any(type(size) is not int or size < 0 for size in shape) or
            type(header["descr"]) is not str):
        raise ValueError("NPY header types")
    dtype = np.dtype(header["descr"])
    if (dtype.str != header["descr"] or dtype.hasobject or dtype.kind not in "biuf" or
            math.prod(shape) * dtype.itemsize > MAX_BYTES or
            member.tell() + math.prod(shape) * dtype.itemsize != member_bytes):
        raise ValueError("NPY dtype/payload mismatch")
    return shape, False, dtype
