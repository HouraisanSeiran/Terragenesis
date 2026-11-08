"""Explicit dynamic forest over every accepted prepared surface domain."""

from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline import dynamic_surface_hydraulics as hydraulics
from terrain_pipeline import surface_dynamic_prepare as adapter
from terrain_pipeline import surface_fine_mosaic as mosaic
from terrain_pipeline.surface_domain_prepare import _hash, validate_surface_domains
from terrain_pipeline.surface_network_consumer import _payload

VERSION = "surface-multidomain-dynamic-v1"
MAX_BYTES = 128 * 1024 * 1024
LEDGER_COLUMNS = hydraulics.LEDGER_COLUMNS


@dataclass(frozen=True)
class ForestResources:
    max_domains: int = 64
    max_wet_cells: int = 100000
    max_assignment_work: int = 2000000
    max_retained_bytes: int = MAX_BYTES
    max_working_bytes: int = MAX_BYTES

    def __post_init__(self):
        ceilings = (64, 100000, 2000000, MAX_BYTES, MAX_BYTES)
        for field, ceiling in zip(fields(self), ceilings):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid forest resource: " + field.name)


def _domains(evaluation, resources=None, *, full_validation=False):
    if resources is not None:
        if mosaic._size(evaluation) > resources.max_retained_bytes:
            raise ValueError("forest source retained bytes exceeded")
        if len(evaluation["domains"]) > resources.max_domains:
            raise ValueError("forest domain count exceeded")
    if full_validation:
        validate_surface_domains(evaluation)
    else:
        if _hash({key: value for key, value in evaluation.items() if key != "identity_sha256"}) != evaluation["identity_sha256"]:
            raise ValueError("evaluation identity mismatch")
        validate_surface_domains(evaluation["candidate"], allow_unprepared=True)
    if evaluation["kind"] != "evaluation" or evaluation["status"] != "prepared":
        raise ValueError("all declared domains must be prepared")
    domains = evaluation["domains"]
    ids = [entry["domain_id"] for entry in domains]
    if (not ids or ids != [entry["domain_id"] for entry in evaluation["candidate"]["domains"]] or
            set(evaluation["configurations"]) != {str(domain_id) for domain_id in ids} or
            any(type(domain_id) is not int or domain_id <= 0 for domain_id in ids) or
            ids != sorted(set(ids)) or
            any(entry["status"] != "prepared" or entry["recovery"] is None or
                entry["recovery"]["accepted"] is not True for entry in domains)):
        raise ValueError("every declared domain requires accepted recovery")
    return ids


def _layout(bindings, ids):
    offsets = [0]
    edge_offsets = [0]
    for binding in bindings:
        offsets.append(offsets[-1] + len(binding["node_flat_ids"]))
        edge_offsets.append(edge_offsets[-1] + len(binding["edges"]))
    keys = np.concatenate([np.column_stack((np.full(len(binding["node_flat_ids"]), domain_id, np.int64),
                                             binding["node_flat_ids"]))
                           for domain_id, binding in zip(ids, bindings)])
    edges = np.concatenate([binding["edges"] + offsets[index]
                            for index, binding in enumerate(bindings)]).reshape(-1, 2)
    return np.asarray(offsets, np.int64), np.asarray(edge_offsets, np.int64), keys, edges


def _input(bindings, offsets, edges, conductance_m2_s, local_q_m3_s, tailwater_m,
           dt_s, max_depth_m, limits, source, datum):
    count = int(offsets[-1])
    boundary = np.concatenate([binding["boundary_mask"] for binding in bindings])
    local = np.asarray(local_q_m3_s)
    tailwater = np.asarray(tailwater_m)
    if local.ndim != 2 or local.shape[1] != count or local.shape[0] < 1:
        raise ValueError("explicit local Q[T,globalN] required")
    if tailwater.shape != (len(local) + 1, int(boundary.sum())):
        raise ValueError("explicit tailwater[T+1,all outlets] required")
    hydraulics._preflight(count, len(edges), len(local), limits)
    boundary_stage = np.zeros((len(local) + 1, count))
    boundary_stage[:, boundary] = tailwater
    return hydraulics.HydraulicsInput(
        bed_m=np.concatenate([binding["bed_m"] for binding in bindings]),
        area_m2=np.concatenate([binding["area_m2"] for binding in bindings]),
        initial_stage_m=np.concatenate([binding["initial_stage_m"] for binding in bindings]),
        edges=edges, conductance_m2_s=conductance_m2_s, local_q_m3_s=local,
        boundary_mask=boundary, boundary_stage_m=boundary_stage,
        dt_s=dt_s, max_depth_m=max_depth_m, valid_mask=np.ones(count, bool),
        protected_mask=np.zeros(count, bool),
        coords_m=np.concatenate([binding["coords_xz_m"] for binding in bindings]),
        source=source, datum=datum, coords="metric-xz-m", limits=limits)


def _domain_ledgers(dynamic, offsets, edge_offsets):
    inputs = dynamic.inputs
    rows = np.empty((dynamic.committed_steps, len(offsets) - 1, 6))
    for step in range(dynamic.committed_steps):
        for index in range(len(offsets) - 1):
            start, stop = int(offsets[index]), int(offsets[index + 1])
            first, last = int(edge_offsets[index]), int(edge_offsets[index + 1])
            net = np.zeros(stop - start)
            edges = inputs.edges[first:last] - start
            flux = dynamic.qedges_m3_s[step, first:last]
            np.add.at(net, edges[:, 0], -flux)
            np.add.at(net, edges[:, 1], flux)
            before = float(dynamic.storage_m3[step, start:stop].sum())
            after = float(dynamic.storage_m3[step + 1, start:stop].sum())
            boundary = inputs.boundary_mask[start:stop]
            local = float(inputs.dt_s * inputs.local_q_m3_s[step, start:stop][~boundary].sum())
            inward = float(-inputs.dt_s * net[boundary].sum())
            rows[step, index] = (before, local, inward, after, after - before,
                                  after - before - local - inward)
    return rows


def _gate(record):
    required = {"algorithm_version", "kind", "evaluation", "bindings", "resources", "domain_ids",
                "node_offsets", "edge_offsets", "node_keys", "edges", "dynamic", "domain_ledger_m3",
                "identity_sha256", "natural_outlets_certified", "full_dynamic_wave_prepared"}
    if (set(record) != required or record["algorithm_version"] != VERSION or record["kind"] != "forest" or
            record["natural_outlets_certified"] is not False or record["full_dynamic_wave_prepared"] is not False or
            record["identity_sha256"] != mosaic._identity({key: value for key, value in record.items()
                                                            if key != "identity_sha256"})):
        raise ValueError("forest schema/identity mismatch")
    resources = ForestResources(**record["resources"])
    if mosaic._size(record) > resources.max_retained_bytes or mosaic._size(record) * 2 > resources.max_working_bytes:
        raise ValueError("forest retained/working bytes exceeded")
    return resources


def validate_surface_multidomain_dynamic(record):
    """Static verification of source, mapping, dynamics, prefix and per-domain accounts."""
    try:
        resources = _gate(record)
        ids = _domains(record["evaluation"], resources)
        bindings = record["bindings"]
        if (len(ids) > resources.max_domains or len(bindings) != len(ids) or
                any(type(value) is not int or value <= 0 for value in record["domain_ids"]) or
                list(record["domain_ids"]) != ids):
            raise ValueError("omitted or duplicate domain")
        datum = record["evaluation"]["candidate"]["inputs"]["vertical_datum"]
        wet_count = 0
        assignment_work = 0
        for domain_id, binding, entry in zip(ids, bindings, record["evaluation"]["domains"]):
            adapter.validate_surface_dynamic_binding(binding)
            sources = binding["source_mosaic"]["sources"]
            if (binding["source_proof_sha256"] != entry["recovery"]["identity_sha256"] or
                    binding["vertical_datum"] != datum or len(sources) != 1 or
                    sources[0]["domain_id"] != domain_id or
                    binding["source_mosaic"]["proofs"][binding["source_proof_sha256"]]["identity_sha256"] !=
                    entry["recovery"]["identity_sha256"]):
                raise ValueError("binding does not belong to declared domain/proof")
            wet_count += len(binding["wet_cell_ids"])
            assignment_work += len(binding["wet_cell_ids"]) * len(binding["node_flat_ids"])
        if wet_count > resources.max_wet_cells or assignment_work > resources.max_assignment_work:
            raise ValueError("forest wet assignment resource exceeded")
        offsets, edge_offsets, keys, edges = _layout(bindings, ids)
        for name, expected in (("node_offsets", offsets), ("edge_offsets", edge_offsets),
                               ("node_keys", keys), ("edges", edges)):
            actual = record[name]
            if actual.dtype != np.dtype("int64") or not np.array_equal(actual, expected):
                raise ValueError("forest mapping differs: " + name)
        dynamic = adapter._unpack_dynamic(record["dynamic"])
        usage = hydraulics.validate(dynamic)
        inputs = dynamic.inputs
        if inputs.source != record["evaluation"]["identity_sha256"] or inputs.datum != datum:
            raise ValueError("global source/datum mismatch")
        for name, expected in (("bed_m", np.concatenate([item["bed_m"] for item in bindings])),
                               ("area_m2", np.concatenate([item["area_m2"] for item in bindings])),
                               ("initial_stage_m", np.concatenate([item["initial_stage_m"] for item in bindings])),
                               ("boundary_mask", np.concatenate([item["boundary_mask"] for item in bindings])),
                               ("coords_m", np.concatenate([item["coords_xz_m"] for item in bindings])),
                               ("edges", edges)):
            if not np.array_equal(getattr(inputs, name), expected):
                raise ValueError("global input differs from source: " + name)
        if (inputs.coords != "metric-xz-m" or not np.all(inputs.valid_mask) or
                np.any(inputs.protected_mask) or record["dynamic"]["status"] != dynamic.status):
            raise ValueError("global input geometry/status differs")
        if np.any(inputs.boundary_stage_m[:, ~inputs.boundary_mask] != 0):
            raise ValueError("non-boundary tailwater")
        expected = _domain_ledgers(dynamic, offsets, edge_offsets)
        actual = record["domain_ledger_m3"]
        if actual.dtype != np.dtype("float64") or actual.shape != expected.shape or not np.allclose(
                actual, expected, atol=1e-10, rtol=0):
            raise ValueError("per-domain ledger differs")
        if not np.allclose(actual.sum(axis=1), dynamic.ledger_m3, atol=1e-10, rtol=0):
            raise ValueError("domain ledgers do not sum to global ledger")
        if mosaic._size(record) + usage["resources"]["retained_bytes_upper_bound"] > resources.max_working_bytes:
            raise ValueError("forest dynamic working bytes exceeded")
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("invalid saved forest") from error


def prepare_surface_multidomain_dynamic(evaluation, *, conductance_m2_s, local_q_m3_s,
                                        tailwater_m, dt_s, max_depth_m,
                                        resources=ForestResources(), limits=hydraulics.ResourceLimits(), cancel=None):
    """Bind all accepted domains, then advance one synchronous global graph."""
    if not isinstance(resources, ForestResources):
        raise ValueError("ForestResources required")
    ids = _domains(evaluation, resources, full_validation=True)
    node_count = 0
    edge_count = 0
    for entry in evaluation["domains"]:
        payload = _payload(mosaic._plain(entry["recovery"]))
        active = np.flatnonzero(payload["active_mask"])
        node_count += len(active)
        edge_count += int(np.count_nonzero(payload["receiver"][active] >= 0))
    usage = hydraulics._preflight(node_count, edge_count, len(np.asarray(local_q_m3_s)), limits)
    if mosaic._size(evaluation) + usage["retained_bytes_upper_bound"] > resources.max_working_bytes:
        raise ValueError("forest planned working bytes exceeded")
    datum = evaluation["candidate"]["inputs"]["vertical_datum"]
    bound_resources = adapter.DynamicPrepareResources(
        max_wet_cells=resources.max_wet_cells, max_assignment_work=resources.max_assignment_work,
        max_retained_bytes=resources.max_retained_bytes, max_working_bytes=resources.max_working_bytes)
    bindings = []
    wet_count = 0
    assignment_work = 0
    for domain_id in ids:
        if cancel is not None and cancel():
            raise InterruptedError("forest binding cancelled")
        bindings.append(adapter.bind_surface_dynamic_source(evaluation, domain_id=domain_id,
                                                             vertical_datum=datum, resources=bound_resources))
        wet_count += len(bindings[-1]["wet_cell_ids"])
        assignment_work += len(bindings[-1]["wet_cell_ids"]) * len(bindings[-1]["node_flat_ids"])
        if wet_count > resources.max_wet_cells or assignment_work > resources.max_assignment_work:
            raise ValueError("forest total wet assignment resource exceeded")
        if mosaic._size({"evaluation": evaluation, "bindings": bindings}) * 2 > resources.max_working_bytes:
            raise ValueError("forest binding working bytes exceeded")
    offsets, edge_offsets, keys, edges = _layout(bindings, ids)
    usage = hydraulics._preflight(len(keys), len(edges), len(np.asarray(local_q_m3_s)), limits)
    if (mosaic._size({"evaluation": evaluation, "bindings": bindings}) +
            usage["retained_bytes_upper_bound"]) * 2 > resources.max_working_bytes:
        raise ValueError("forest dynamic working bytes exceeded")
    inputs = _input(bindings, offsets, edges, conductance_m2_s, local_q_m3_s, tailwater_m,
                    dt_s, max_depth_m, limits, evaluation["identity_sha256"], datum)
    dynamic = hydraulics.evaluate(inputs, cancel=cancel)
    record = {"algorithm_version": VERSION, "kind": "forest", "evaluation": evaluation,
              "bindings": bindings, "resources": asdict(resources), "domain_ids": ids,
              "node_offsets": offsets, "edge_offsets": edge_offsets, "node_keys": keys, "edges": edges,
              "dynamic": adapter._pack_dynamic(dynamic),
              "domain_ledger_m3": _domain_ledgers(dynamic, offsets, edge_offsets),
              "natural_outlets_certified": False, "full_dynamic_wave_prepared": False}
    sealed = adapter._seal(record)
    validate_surface_multidomain_dynamic(sealed)
    return sealed


def query_surface_multidomain_dynamic(record, *, state_index=None):
    validate_surface_multidomain_dynamic(record)
    dynamic = record["dynamic"]
    if state_index is not None and (type(state_index) is not int or
                                    not 0 <= state_index <= dynamic["committed_steps"]):
        raise ValueError("state index outside committed prefix")
    selection = slice(None) if state_index is None else state_index
    return mosaic._freeze({"node_keys": record["node_keys"], "stage_m": dynamic["stage_m"][selection],
                           "storage_m3": dynamic["storage_m3"][selection], "time_s": dynamic["time_s"][selection],
                           "status": dynamic["status"]})


def save_surface_multidomain_dynamic(record, path):
    validate_surface_multidomain_dynamic(record)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = mosaic._tree(record, arrays)
    manifest = mosaic._json({"format_version": 1, "tree": tree, "tree_sha256": mosaic._identity(tree)})
    descriptor, temporary = tempfile.mkstemp(prefix=".forest-", suffix=".tmp", dir=destination.parent)
    try:
        stream = os.fdopen(descriptor, "w+b")
        descriptor = None
        with stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", manifest)
                for name, array in arrays.items():
                    with archive.open(name, "w") as member:
                        np.lib.format.write_array(member, np.ascontiguousarray(array), version=(1, 0),
                                                  allow_pickle=False)
            if stream.tell() > MAX_BYTES:
                raise ValueError("forest bundle cap")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        return destination
    finally:
        if descriptor is not None:
            os.close(descriptor)
        Path(temporary).unlink(missing_ok=True)


def load_surface_multidomain_dynamic(path):
    """Bounded static ZIP/NPY read; never bind, prepare or advance."""
    try:
        with Path(path).open("rb") as retained, zipfile.ZipFile(retained) as archive:
            if os.fstat(retained.fileno()).st_size > MAX_BYTES:
                raise ValueError("forest bundle cap")
            mosaic._preflight_archive(archive)
            manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=mosaic._pairs,
                                  parse_constant=mosaic._constant)
            if (set(manifest) != {"format_version", "tree", "tree_sha256"} or manifest["format_version"] != 1 or
                    manifest["tree_sha256"] != mosaic._identity(manifest["tree"])):
                raise ValueError("forest manifest identity mismatch")
            tree = manifest["tree"]
            resources = ForestResources(**tree["resources"])
            if set(tree) != {"algorithm_version", "kind", "evaluation", "bindings", "resources", "domain_ids",
                             "node_offsets", "edge_offsets", "node_keys", "edges", "dynamic", "domain_ledger_m3",
                             "identity_sha256", "natural_outlets_certified", "full_dynamic_wave_prepared"}:
                raise ValueError("forest tree schema mismatch")
            count = tree["node_keys"]["shape"][0]
            edges = tree["edges"]["shape"][0]
            steps = tree["dynamic"]["inputs"]["local_q_m3_s"]["shape"][0]
            limits = hydraulics.ResourceLimits(**tree["dynamic"]["inputs"]["limits"])
            usage = hydraulics._preflight(count, edges, steps, limits)
            size = sum(info.file_size for info in archive.infolist())
            if (size > resources.max_retained_bytes or size * 2 > resources.max_working_bytes or
                    usage["retained_bytes_upper_bound"] > resources.max_working_bytes or
                    len(tree["bindings"]) > resources.max_domains):
                raise ValueError("forest JSON resource preflight")
            references = {}
            def collect(value):
                if isinstance(value, dict) and "$array" in value:
                    name = value["$array"]
                    if set(value) != {"$array", "shape", "dtype", "sha256"} or name in references:
                        raise ValueError("duplicate/invalid array reference")
                    references[name] = value
                elif isinstance(value, dict):
                    for child in value.values():
                        collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)
            collect(tree)
            if set(references) != set(archive.namelist()) - {"manifest.json"}:
                raise ValueError("missing/unused array")
            for name, reference in references.items():
                with archive.open(name) as member:
                    if np.lib.format.read_magic(member) != (1, 0):
                        raise ValueError("NPY v1 required")
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(member, max_header_size=8192)
                    if (list(shape) != reference["shape"] or dtype.str != reference["dtype"] or fortran or
                            dtype.hasobject or dtype.kind not in "biuf" or
                            member.tell() + int(np.prod(shape, dtype=np.int64)) * dtype.itemsize != archive.getinfo(name).file_size):
                        raise ValueError("array header differs")
            def decode(value):
                if isinstance(value, dict) and "$array" in value:
                    with archive.open(value["$array"]) as member:
                        array = np.load(member, allow_pickle=False)
                    if mosaic.array_hash(array) != value["sha256"]:
                        raise ValueError("array hash differs")
                    return array
                if isinstance(value, dict):
                    return {key: decode(child) for key, child in value.items()}
                if isinstance(value, list):
                    return [decode(child) for child in value]
                return value
            record = decode(tree)
        validate_surface_multidomain_dynamic(record)
        return mosaic._freeze(record)
    except (OSError, KeyError, TypeError, IndexError, AttributeError, EOFError,
            zipfile.BadZipFile) as error:
        raise ValueError("invalid forest bundle") from error
