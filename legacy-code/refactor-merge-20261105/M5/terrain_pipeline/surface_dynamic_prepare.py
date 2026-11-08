"""Accepted recovery to fixed-area storage graph, with generation-free static reads."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
import io
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline import dynamic_surface_hydraulics as hydraulics
from terrain_pipeline import surface_fine_mosaic as mosaic
from terrain_pipeline.surface_network_consumer import _payload
from terrain_pipeline.surface_network_recovery import VERSION as RECOVERY_VERSION

VERSION = "surface-dynamic-prepare-v1"
AREA_SEMANTICS = "fixed_lumped_actual_wet_cell_area_nearest_active_node_not_section_V_of_h"
MAX_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class DynamicPrepareResources:
    max_wet_cells: int = 100000
    max_assignment_work: int = 2000000
    max_retained_bytes: int = MAX_BYTES
    max_working_bytes: int = MAX_BYTES

    def __post_init__(self):
        ceilings = (100000, 2000000, MAX_BYTES, MAX_BYTES)
        for field, ceiling in zip(fields(self), ceilings):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid dynamic prepare resource: " + field.name)


def _seal(record):
    record["identity_sha256"] = mosaic._identity(record)
    return mosaic._freeze(record)


def _source_mosaic(source, domain_id, vertical_datum, resources):
    if isinstance(source, Mapping) and source.get("algorithm_version") == mosaic.VERSION:
        mosaic.validate_fine_mosaic(source)
        if domain_id is not None:
            raise ValueError("domain selection is only supported for domain evaluations")
        if source["vertical_datum"] != vertical_datum:
            raise ValueError("source mosaic datum differs")
        return source
    if isinstance(source, Mapping) and source.get("kind") == "evaluation":
        candidates = mosaic.sources_from_surface_domains(source)
        if source["candidate"]["inputs"]["vertical_datum"] != vertical_datum:
            raise ValueError("prepared domain datum differs")
        selected = [item for item in candidates if domain_id is None or item.domain_id == domain_id]
        if len(selected) != 1:
            raise ValueError("select exactly one prepared domain_id")
        bound_source = selected[0]
    elif isinstance(source, mosaic.DomainFineSource):
        if domain_id is not None:
            raise ValueError("explicit source already declares a domain id")
        bound_source = source
    elif isinstance(source, Mapping) and source.get("algorithm_version") == RECOVERY_VERSION:
        bound_source = mosaic.DomainFineSource(source, 1 if domain_id is None else domain_id)
    else:
        raise ValueError("accepted recovery, prepared domain or saved prepared mosaic required")
    proof = bound_source.proof
    sea = proof["inputs"]["plan"]["identity"]["parameters"]["sea_level_elevation_m"]
    return mosaic.prepare_fine_mosaic((bound_source,), metric_grid={"coordinate_system": "metric-xz-m"},
        vertical_datum=vertical_datum, source_identity="dynamic-source:" + proof["identity_sha256"],
        sea_level_elevation_m=sea,
        resources=mosaic.MosaicResources(max_cells=resources.max_wet_cells,
            max_retained_bytes=resources.max_retained_bytes, max_working_bytes=resources.max_working_bytes))


def bind_surface_dynamic_source(source, *, vertical_datum, domain_id=None,
                                resources=DynamicPrepareResources()):
    """Explicit source preparation, never time advancement. Node order is coarse flat id."""
    if not isinstance(resources, DynamicPrepareResources):
        raise ValueError("DynamicPrepareResources required")
    retained_source = source.proof if isinstance(source, mosaic.DomainFineSource) else source
    if mosaic._size(retained_source) > resources.max_retained_bytes:
        raise ValueError("source retained resource preflight")
    prepared = _source_mosaic(source, domain_id, vertical_datum, resources)
    if mosaic._size(prepared) * 2 > min(resources.max_retained_bytes, resources.max_working_bytes):
        raise ValueError("embedded source retained/working resource preflight")
    if len(prepared["proofs"]) != 1 or len(prepared["sources"]) != 1:
        raise ValueError("dynamic adapter scope requires one complete accepted recovery graph")
    proof_identity, proof = next(iter(prepared["proofs"].items()))
    payload = _payload(mosaic._plain(proof))
    node_flat_ids = np.flatnonzero(payload["active_mask"]).astype(np.int64)
    if not len(node_flat_ids) or len(node_flat_ids) > 4096:
        raise ValueError("active node resource bound")
    lookup = {int(flat_id): index for index, flat_id in enumerate(node_flat_ids)}
    edges = []
    for flat_id in node_flat_ids:
        target = int(payload["receiver"][flat_id])
        if target >= 0:
            if target not in lookup:
                raise ValueError("actual channel edge leaves active source graph")
            edges.append((lookup[int(flat_id)], lookup[target]))
    edges = np.asarray(edges, np.int64).reshape(-1, 2)
    boundary = payload["outlet_mask"].ravel()[node_flat_ids]
    if not boundary.any() or boundary.all():
        raise ValueError("actual active outlet and internal storage nodes required")
    coordinates = payload["world_xz_m"][node_flat_ids]
    grid = prepared["grid"]
    rows, columns = grid["shape_cells_zx"]
    fine_columns = np.rint((coordinates[:, 0] - grid["origin_x_m"]) / grid["spacing_x_m"]).astype(np.int64)
    fine_rows = np.rint((coordinates[:, 1] - grid["origin_z_m"]) / grid["spacing_z_m"]).astype(np.int64)
    if (np.any(fine_columns < 0) or np.any(fine_columns > columns) or np.any(fine_rows < 0) or
            np.any(fine_rows > rows) or
            not np.allclose(coordinates[:, 0], grid["origin_x_m"] + fine_columns * grid["spacing_x_m"], atol=1e-8, rtol=0) or
            not np.allclose(coordinates[:, 1], grid["origin_z_m"] + fine_rows * grid["spacing_z_m"], atol=1e-8, rtol=0)):
        raise ValueError("source slice does not cover complete active graph")
    fine_node_ids = fine_rows * (columns + 1) + fine_columns
    wet_cell_ids = np.flatnonzero(prepared["wet_cells"]).astype(np.int64)
    work = len(wet_cell_ids) * len(node_flat_ids)
    if not len(wet_cell_ids) or len(wet_cell_ids) > resources.max_wet_cells or work > resources.max_assignment_work:
        raise ValueError("wet-cell assignment resource preflight")
    if mosaic._size(prepared) + len(wet_cell_ids) * 32 + len(node_flat_ids) * 128 > resources.max_working_bytes:
        raise ValueError("source mapping working resource preflight")
    owner = np.empty(len(wet_cell_ids), np.int64)
    for index, cell_id in enumerate(wet_cell_ids):
        corners = prepared["cells"][cell_id]
        center = np.array([prepared["nodes"]["x_m"][corners].mean(), prepared["nodes"]["z_m"][corners].mean()])
        owner[index] = int(np.argmin(((coordinates - center) ** 2).sum(axis=1)))
    cell_area = grid["spacing_x_m"] * grid["spacing_z_m"]
    area = np.bincount(owner, minlength=len(node_flat_ids)).astype(float) * cell_area
    if np.any(area <= 0):
        raise ValueError("A0: active source node has no uniquely assigned actual wet cell")
    nodes = prepared["nodes"]
    record = {"algorithm_version": VERSION, "kind": "binding", "area_semantics": AREA_SEMANTICS,
              "source_mosaic": prepared, "source_proof_sha256": proof_identity,
              "vertical_datum": vertical_datum, "resources": asdict(resources),
              "node_flat_ids": node_flat_ids, "fine_node_ids": fine_node_ids,
              "coords_xz_m": coordinates, "edges": edges, "boundary_mask": boundary,
              "wet_cell_ids": wet_cell_ids, "wet_cell_owner": owner, "area_m2": area,
              "bed_m": nodes["h2_m"][fine_node_ids], "initial_stage_m": nodes["water_surface_m"][fine_node_ids],
              "natural_outlets_certified": False, "full_dynamic_wave_prepared": False}
    sealed = _seal(record)
    validate_surface_dynamic_binding(sealed)
    return sealed


def _pack_dynamic(result):
    inputs = {field.name: getattr(result.inputs, field.name) for field in fields(result.inputs)}
    inputs["limits"] = asdict(result.inputs.limits)
    failed = None if result.failed_step is None else {
        field.name: getattr(result.failed_step, field.name) for field in fields(result.failed_step)}
    return {"inputs": inputs, "status": result.status, "committed_steps": result.committed_steps,
            "stage_m": result.stage_m, "storage_m3": result.storage_m3,
            "qedges_m3_s": result.qedges_m3_s, "time_s": result.time_s,
            "ledger_m3": result.ledger_m3, "failed_step": failed, "identity_sha256": result.identity_sha256}


def _unpack_dynamic(record):
    inputs = dict(record["inputs"])
    inputs["limits"] = hydraulics.ResourceLimits(**inputs["limits"])
    inputs = hydraulics.HydraulicsInput(**inputs)
    failed = record["failed_step"]
    failed = None if failed is None else hydraulics.FailedStep(**failed)
    return hydraulics.HydraulicsResult(inputs=inputs, status=record["status"],
        committed_steps=record["committed_steps"], stage_m=record["stage_m"], storage_m3=record["storage_m3"],
        qedges_m3_s=record["qedges_m3_s"], time_s=record["time_s"], ledger_m3=record["ledger_m3"],
        failed_step=failed, identity_sha256=record["identity_sha256"])


def prepare_surface_dynamic(source, *, conductance_m2_s, local_q_m3_s, tailwater_m,
                            dt_s, max_depth_m, vertical_datum=None, domain_id=None,
                            resources=DynamicPrepareResources(), limits=hydraulics.ResourceLimits(), cancel=None):
    """The only adapter entrypoint that advances time; caller K/Q/tailwater stay explicit."""
    if isinstance(source, Mapping) and source.get("kind") == "binding":
        binding = source
        validate_surface_dynamic_binding(binding)
        if domain_id is not None or (vertical_datum is not None and vertical_datum != binding["vertical_datum"]):
            raise ValueError("binding selection/datum differs")
        resources = DynamicPrepareResources(**binding["resources"])
    else:
        binding = bind_surface_dynamic_source(source, vertical_datum=vertical_datum,
                                              domain_id=domain_id, resources=resources)
    local = np.asarray(local_q_m3_s)
    tailwater = np.asarray(tailwater_m)
    count = len(binding["node_flat_ids"])
    if local.ndim != 2 or local.shape[1] != count:
        raise ValueError("explicit local Q[T,N] in saved node order required")
    if tailwater.shape != (len(local) + 1, int(binding["boundary_mask"].sum())):
        raise ValueError("explicit tailwater[T+1,actual outlets] required")
    usage = hydraulics._preflight(count, len(binding["edges"]), len(local), limits)
    estimate = mosaic._size(binding) + usage["retained_bytes_upper_bound"]
    if estimate * 2 > min(resources.max_retained_bytes, resources.max_working_bytes):
        raise ValueError("dynamic retained/working resource preflight")
    boundary_stage = np.zeros((len(local) + 1, count))
    boundary_stage[:, binding["boundary_mask"]] = tailwater
    inputs = hydraulics.HydraulicsInput(bed_m=binding["bed_m"], area_m2=binding["area_m2"],
        initial_stage_m=binding["initial_stage_m"], edges=binding["edges"], conductance_m2_s=conductance_m2_s,
        local_q_m3_s=local, boundary_mask=binding["boundary_mask"], boundary_stage_m=boundary_stage,
        dt_s=dt_s, max_depth_m=max_depth_m, valid_mask=np.ones(count, bool),
        protected_mask=np.zeros(count, bool), coords_m=binding["coords_xz_m"],
        source=binding["identity_sha256"], datum=binding["vertical_datum"], coords="metric-xz-m", limits=limits)
    dynamic = hydraulics.evaluate(inputs, cancel=cancel)
    record = {"algorithm_version": VERSION, "kind": "dynamic", "binding": binding,
              "dynamic": _pack_dynamic(dynamic), "status": dynamic.status,
              "caller_tailwater_m": tailwater, "resources": asdict(resources),
              "natural_outlets_certified": False, "full_dynamic_wave_prepared": False}
    sealed = _seal(record)
    validate_surface_dynamic(sealed)
    return sealed


def _record_gate(record, kind):
    if (record["algorithm_version"] != VERSION or record["kind"] != kind or
            record["natural_outlets_certified"] is not False or record["full_dynamic_wave_prepared"] is not False or
            record["identity_sha256"] != mosaic._identity({key: value for key, value in record.items() if key != "identity_sha256"})):
        raise ValueError("dynamic prepare identity/scope mismatch")
    resources = DynamicPrepareResources(**record["resources"])
    size = mosaic._size(record)
    if size > resources.max_retained_bytes or size * 2 > resources.max_working_bytes:
        raise ValueError("dynamic prepare retained/working resource limit")
    return resources


def validate_surface_dynamic_binding(binding):
    """Validate saved ownership algebraically; never construct or resample mappings."""
    try:
        resources = _record_gate(binding, "binding")
        source = binding["source_mosaic"]
        mosaic.validate_fine_mosaic(source)
        if (binding["area_semantics"] != AREA_SEMANTICS or binding["vertical_datum"] != source["vertical_datum"] or
                len(source["proofs"]) != 1 or len(source["sources"]) != 1):
            raise ValueError("dynamic source/area semantics invalid")
        identity, proof = next(iter(source["proofs"].items()))
        if identity != binding["source_proof_sha256"]:
            raise ValueError("binding proof identity differs")
        payload = _payload(mosaic._plain(proof))
        flat_ids = binding["node_flat_ids"]
        count = len(flat_ids)
        if (flat_ids.dtype != np.dtype("int64") or flat_ids.ndim != 1 or not 0 < count <= 4096 or
                not np.array_equal(flat_ids, np.flatnonzero(payload["active_mask"]))):
            raise ValueError("saved active node ids not complete/unique")
        coordinates = binding["coords_xz_m"]
        if (coordinates.dtype != np.dtype("float64") or coordinates.shape != (count, 2) or
                not np.array_equal(coordinates, payload["world_xz_m"][flat_ids]) or
                len(set(map(tuple, coordinates))) != count):
            raise ValueError("saved source node coordinates invalid/duplicate")
        boundary = binding["boundary_mask"]
        if (boundary.dtype != bool or boundary.shape != (count,) or
                not np.array_equal(boundary, payload["outlet_mask"].ravel()[flat_ids]) or
                not boundary.any() or boundary.all()):
            raise ValueError("saved boundary is not actual active outlet mask")
        edges = binding["edges"]
        edge_count = int(np.count_nonzero(payload["receiver"][flat_ids] >= 0))
        if edges.dtype != np.dtype("int64") or edges.shape != (edge_count, 2):
            raise ValueError("saved graph edge shape/dtype invalid")
        edge_index = 0
        for node_id, flat_id in enumerate(flat_ids):
            target = int(payload["receiver"][flat_id])
            if target >= 0:
                if (edges[edge_index, 0] != node_id or not 0 <= edges[edge_index, 1] < count or
                        flat_ids[edges[edge_index, 1]] != target):
                    raise ValueError("saved edge differs from actual active source topology")
                edge_index += 1
        fine_ids = binding["fine_node_ids"]
        nodes = source["nodes"]
        if (fine_ids.dtype != np.dtype("int64") or fine_ids.shape != (count,) or np.any(fine_ids < 0) or
                np.any(fine_ids >= len(nodes["x_m"])) or len(set(fine_ids.tolist())) != count or
                not np.array_equal(nodes["x_m"][fine_ids], coordinates[:, 0]) or
                not np.array_equal(nodes["z_m"][fine_ids], coordinates[:, 1])):
            raise ValueError("saved fine node mapping differs from actual source world coordinates")
        if not np.all(nodes["wet_mask"][fine_ids]) or np.any(nodes["protected_mask"][fine_ids]):
            raise ValueError("active node has unknown/protected/dry source support")
        if (not np.allclose(nodes["water_surface_m"][fine_ids], payload["node_stage_m"][flat_ids], atol=1e-8, rtol=0) or
                not np.allclose(nodes["h2_m"][fine_ids], proof["final_plan"]["arrays"]["bounded_bed_m"].ravel()[flat_ids],
                                atol=proof["inputs"]["budget"]["bed_match_tolerance_m"], rtol=0) or
                np.any(nodes["water_surface_m"][fine_ids] <= nodes["h2_m"][fine_ids])):
            raise ValueError("saved node actual fine depth/stage/bed differs from source graph")
        for name, actual in (("bed_m", nodes["h2_m"][fine_ids]), ("initial_stage_m", nodes["water_surface_m"][fine_ids])):
            value = binding[name]
            if value.dtype != np.dtype("float64") or value.shape != (count,) or not np.array_equal(value, actual):
                raise ValueError("saved node bed/stage differs from actual fine H2/water")
        wet_ids, owner = binding["wet_cell_ids"], binding["wet_cell_owner"]
        if (wet_ids.dtype != np.dtype("int64") or wet_ids.ndim != 1 or
                not np.array_equal(wet_ids, np.flatnonzero(source["wet_cells"])) or not len(wet_ids) or
                len(wet_ids) > resources.max_wet_cells or len(wet_ids) * count > resources.max_assignment_work or
                owner.dtype != np.dtype("int64") or owner.shape != wet_ids.shape or np.any(owner < 0) or np.any(owner >= count)):
            raise ValueError("saved wet cell assignment set/resource/owner invalid")
        for index, cell_id in enumerate(wet_ids):
            corners = source["cells"][cell_id]
            center_x, center_z = nodes["x_m"][corners].mean(), nodes["z_m"][corners].mean()
            distances = (coordinates[:, 0] - center_x) ** 2 + (coordinates[:, 1] - center_z) ** 2
            chosen = int(owner[index])
            if np.any(distances < distances[chosen]) or np.any(distances[:chosen] == distances[chosen]):
                raise ValueError("saved wet cell ownership is not nearest active node with stable tie")
        cell_area = source["grid"]["spacing_x_m"] * source["grid"]["spacing_z_m"]
        expected_area = np.bincount(owner, minlength=count) * cell_area
        area = binding["area_m2"]
        if (area.dtype != np.dtype("float64") or area.shape != (count,) or not np.isfinite(area).all() or
                np.any(area <= 0) or not np.array_equal(area, expected_area) or
                not math.isclose(float(area.sum()), len(wet_ids) * cell_area, rel_tol=0, abs_tol=1e-8)):
            raise ValueError("saved A0/area differs from unique actual wet cell ownership")
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("invalid saved dynamic source binding") from error


def validate_surface_dynamic(result):
    try:
        resources = _record_gate(result, "dynamic")
        binding = result["binding"]
        validate_surface_dynamic_binding(binding)
        if result["resources"] != binding["resources"]:
            raise ValueError("dynamic resources differ from binding")
        dynamic = _unpack_dynamic(result["dynamic"])
        usage = hydraulics.validate(dynamic)
        inputs = dynamic.inputs
        estimate = mosaic._size(binding) + usage["resources"]["retained_bytes_upper_bound"]
        if estimate * 2 > min(resources.max_retained_bytes, resources.max_working_bytes):
            raise ValueError("saved dynamic resource upper bound exceeded")
        for name, expected in (("bed_m", binding["bed_m"]), ("area_m2", binding["area_m2"]),
                               ("initial_stage_m", binding["initial_stage_m"]), ("edges", binding["edges"]),
                               ("boundary_mask", binding["boundary_mask"]), ("coords_m", binding["coords_xz_m"])):
            if not np.array_equal(getattr(inputs, name), expected):
                raise ValueError("dynamic input differs from source binding: " + name)
        if (inputs.source != binding["identity_sha256"] or inputs.datum != binding["vertical_datum"] or
                inputs.coords != "metric-xz-m" or result["status"] != dynamic.status or
                np.any(inputs.boundary_stage_m[:, ~inputs.boundary_mask] != 0) or
                not np.array_equal(result["caller_tailwater_m"], inputs.boundary_stage_m[:, inputs.boundary_mask])):
            raise ValueError("saved dynamic provenance/status/tailwater differs")
        return True
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError) as error:
        raise ValueError("invalid saved dynamic prepare result") from error


def query_surface_dynamic(result, *, state_index=None):
    validate_surface_dynamic(result)
    dynamic = result["dynamic"]
    if state_index is not None and (type(state_index) is not int or not 0 <= state_index <= dynamic["committed_steps"]):
        raise ValueError("state index outside saved committed prefix")
    selection = slice(None) if state_index is None else state_index
    return mosaic._freeze({"stage_m": dynamic["stage_m"][selection], "storage_m3": dynamic["storage_m3"][selection],
                           "time_s": dynamic["time_s"][selection], "node_flat_ids": result["binding"]["node_flat_ids"],
                           "status": result["status"]})


def save_surface_dynamic(result, path):
    validate_surface_dynamic(result)
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    arrays = {}
    tree = mosaic._tree(result, arrays)
    metadata = mosaic._json({"format_version": 1, "tree": tree, "tree_sha256": mosaic._identity(tree)})
    descriptor, temporary = tempfile.mkstemp(prefix=".surface-dynamic-", suffix=".tmp", dir=destination.parent)
    try:
        stream = os.fdopen(descriptor, "w+b")
        descriptor = None
        with stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", metadata)
                for name, array in arrays.items():
                    with archive.open(name, "w") as member:
                        np.lib.format.write_array(member, np.ascontiguousarray(array), allow_pickle=False)
            if stream.tell() > MAX_BYTES:
                raise ValueError("dynamic prepare file cap")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        return destination
    finally:
        if descriptor is not None:
            os.close(descriptor)
        Path(temporary).unlink(missing_ok=True)


def load_surface_dynamic(path):
    """Static source support, ownership and dynamic equations; no generation/replay."""
    try:
        with Path(path).open("rb") as retained:
            if os.fstat(retained.fileno()).st_size > MAX_BYTES:
                raise ValueError("dynamic prepare file cap")
            with zipfile.ZipFile(retained) as archive:
                mosaic._preflight_archive(archive)
                manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=mosaic._pairs, parse_constant=mosaic._constant)
                if (set(manifest) != {"format_version", "tree", "tree_sha256"} or manifest["format_version"] != 1 or
                        manifest["tree_sha256"] != mosaic._identity(manifest["tree"])):
                    raise ValueError("dynamic prepare manifest identity differs")
                tree = manifest["tree"]
                resources = DynamicPrepareResources(**tree["resources"])
                binding = tree["binding"]
                if binding["resources"] != tree["resources"] or tree["algorithm_version"] != VERSION or tree["kind"] != "dynamic":
                    raise ValueError("archive JSON resource/schema mismatch")
                dynamic_inputs = tree["dynamic"]["inputs"]
                limits = hydraulics.ResourceLimits(**dynamic_inputs["limits"])
                count = binding["node_flat_ids"]["shape"][0]
                wet_count = binding["wet_cell_ids"]["shape"][0]
                usage = hydraulics._preflight(count, binding["edges"]["shape"][0],
                                               dynamic_inputs["local_q_m3_s"]["shape"][0], limits)
                size = sum(entry.file_size for entry in archive.infolist())
                if (wet_count > resources.max_wet_cells or wet_count * count > resources.max_assignment_work or
                        size > resources.max_retained_bytes or size * 2 > resources.max_working_bytes or
                        usage["retained_bytes_upper_bound"] > resources.max_retained_bytes):
                    raise ValueError("dynamic prepare JSON resource preflight")
                references = {}
                def collect(value):
                    if isinstance(value, dict) and "$array" in value:
                        name = value["$array"]
                        if (set(value) != {"$array", "shape", "dtype", "sha256"} or name in references or
                                name not in archive.namelist() or not name.endswith(".npy")):
                            raise ValueError("invalid/duplicate dynamic array reference")
                        references[name] = value
                    elif isinstance(value, dict):
                        for child in value.values():
                            collect(child)
                    elif isinstance(value, list):
                        for child in value:
                            collect(child)
                collect(tree)
                if set(references) != set(archive.namelist()) - {"manifest.json"}:
                    raise ValueError("unused dynamic prepare archive arrays")
                for name, reference in references.items():
                    with archive.open(name) as member:
                        version = np.lib.format.read_magic(member)
                        reader = np.lib.format.read_array_header_1_0 if version == (1, 0) else np.lib.format.read_array_header_2_0
                        shape, fortran, dtype = reader(member)
                        if reference["shape"] != list(shape) or reference["dtype"] != dtype.str or fortran:
                            raise ValueError("NPY actual header differs from saved resource metadata")
                arrays = {}
                used = set()
                def decode(value):
                    if isinstance(value, dict) and "$array" in value:
                        name = value["$array"]
                        if set(value) != {"$array", "shape", "dtype", "sha256"} or name in used or name not in archive.namelist():
                            raise ValueError("invalid/duplicate dynamic array reference")
                        with archive.open(name) as member:
                            array = np.load(member, allow_pickle=False)
                        if value["shape"] != list(array.shape) or value["dtype"] != array.dtype.str or value["sha256"] != mosaic.array_hash(array):
                            raise ValueError("dynamic prepare array hash/shape differs")
                        used.add(name)
                        arrays[name] = array
                        return array
                    if isinstance(value, dict):
                        return {key: decode(child) for key, child in value.items()}
                    if isinstance(value, list):
                        return [decode(child) for child in value]
                    return value
                result = decode(tree)
                if used != set(archive.namelist()) - {"manifest.json"}:
                    raise ValueError("unused dynamic prepare archive arrays")
        validate_surface_dynamic(result)
        return mosaic._freeze(result)
    except (KeyError, TypeError, IndexError, AttributeError, OSError, EOFError, zipfile.BadZipFile) as error:
        raise ValueError("invalid dynamic prepare bundle") from error
