"""Explicit storage/conductance graph; not Saint-Venant or legacy river integration."""

from dataclasses import asdict, dataclass, fields
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np


ALGORITHM = "dynamic-surface-storage-conductance-v1"
FORMAT = "dynamic-surface-hydraulics-npy-v1"
GEOMETRY_MODE = "explicit-storage-graph-not-legacy-integrated"
LEDGER_COLUMNS = (
    "storage_before_m3", "local_volume_m3", "boundary_into_storage_m3",
    "storage_after_m3", "storage_change_m3", "residual_m3",
)
MAX_METADATA_BYTES = 16384
MAX_HEADER_BYTES = 2048
MAX_MEMBERS = 24
MAX_FILE_BYTES = 65 * 1024 * 1024


@dataclass(frozen=True)
class ResourceLimits:
    max_nodes: int = 4096
    max_edges: int = 16384
    max_steps: int = 4096
    max_work: int = 2000000
    max_retained_bytes: int = 64 * 1024 * 1024

    def __post_init__(self):
        hard = (4096, 16384, 4096, 2000000, 64 * 1024 * 1024)
        for field, ceiling in zip(fields(self), hard):
            value = getattr(self, field.name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError("invalid resource limit: " + field.name)


def _preflight(node_count, edge_count, step_count, limits):
    if not isinstance(limits, ResourceLimits):
        raise ValueError("limits must be ResourceLimits")
    ResourceLimits(**asdict(limits))
    if not 1 <= node_count <= limits.max_nodes:
        raise ValueError("node resource cap")
    if not 0 <= edge_count <= limits.max_edges:
        raise ValueError("edge resource cap")
    if not 1 <= step_count <= limits.max_steps:
        raise ValueError("time resource cap")
    work = step_count * (node_count + edge_count)
    if work > limits.max_work:
        raise ValueError("work resource cap")
    input_bytes = 8 * (5 * node_count + edge_count +
                       (2 * step_count + 1) * node_count) + 16 * edge_count + 3 * node_count
    state_bytes = 8 * ((step_count + 1) * (2 * node_count + 1) +
                       step_count * (edge_count + 6))
    failure_bytes = 8 * (3 * node_count + edge_count + 6)
    retained_bytes = input_bytes + state_bytes + failure_bytes + MAX_METADATA_BYTES
    if retained_bytes > limits.max_retained_bytes:
        raise ValueError("retained resource cap")
    return {"nodes": node_count, "edges": edge_count, "steps": step_count,
            "work": work, "retained_bytes_upper_bound": retained_bytes}


def _immutable(value, dtype=None):
    array = np.asarray(value, dtype=dtype, order="C")
    return np.frombuffer(array.tobytes(order="C"), dtype=array.dtype).reshape(array.shape)


def _finite_scalar(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(name + " must be a finite positive scalar")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(name + " must be a finite positive scalar")
    return float(value)


@dataclass(frozen=True)
class HydraulicsInput:
    bed_m: np.ndarray
    area_m2: np.ndarray
    initial_stage_m: np.ndarray
    edges: np.ndarray
    conductance_m2_s: np.ndarray
    local_q_m3_s: np.ndarray
    boundary_mask: np.ndarray
    boundary_stage_m: np.ndarray
    dt_s: float
    max_depth_m: float
    valid_mask: np.ndarray
    protected_mask: np.ndarray
    coords_m: np.ndarray
    source: str
    datum: str
    coords: str
    limits: ResourceLimits = ResourceLimits()
    geometry_mode: str = GEOMETRY_MODE

    def __post_init__(self):
        bed = np.asarray(self.bed_m)
        edges = np.asarray(self.edges)
        local = np.asarray(self.local_q_m3_s)
        if bed.ndim != 1 or edges.ndim != 2 or edges.shape[1] != 2 or local.ndim != 2:
            raise ValueError("expected bed[N], edges[E,2], local_q[T,N]")
        node_count, edge_count, step_count = len(bed), len(edges), len(local)
        _preflight(node_count, edge_count, step_count, self.limits)
        expected = {
            "bed_m": (node_count,), "area_m2": (node_count,),
            "initial_stage_m": (node_count,), "edges": (edge_count, 2),
            "conductance_m2_s": (edge_count,), "local_q_m3_s": (step_count, node_count),
            "boundary_mask": (node_count,), "boundary_stage_m": (step_count + 1, node_count),
            "valid_mask": (node_count,), "protected_mask": (node_count,),
            "coords_m": (node_count, 2),
        }
        frozen = {}
        for name, shape in expected.items():
            array = np.asarray(getattr(self, name))
            if array.shape != shape:
                raise ValueError(name + " shape mismatch")
            if name.endswith("mask"):
                if array.dtype != np.dtype(bool):
                    raise ValueError(name + " must be boolean")
                dtype = np.dtype(bool)
            elif name == "edges":
                if array.dtype.kind not in "iu" or np.any(array < 0) or np.any(array >= node_count):
                    raise ValueError("edges must be in-range integer indices")
                dtype = np.dtype("<i8")
            else:
                if array.dtype.kind not in "fiu" or not np.all(np.isfinite(array)):
                    raise ValueError(name + " must be finite real numbers")
                dtype = np.dtype("<f8")
            frozen[name] = _immutable(array, dtype)
        for name, value in frozen.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "dt_s", _finite_scalar(self.dt_s, "dt_s"))
        object.__setattr__(self, "max_depth_m", _finite_scalar(self.max_depth_m, "max_depth_m"))
        for name in ("source", "datum", "coords"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 1024:
                raise ValueError("explicit provenance required: " + name)
        if self.geometry_mode != GEOMETRY_MODE:
            raise ValueError("only explicit storage graph geometry is supported")
        if not np.all(self.valid_mask) or np.any(self.protected_mask):
            raise ValueError("unknown or protected support is unsupported")
        if np.all(self.boundary_mask):
            raise ValueError("at least one internal storage node is required")
        if np.any(self.area_m2 <= 0) or np.any(self.conductance_m2_s <= 0):
            raise ValueError("area and conductance must be positive")
        if np.any(self.edges[:, 0] == self.edges[:, 1]):
            raise ValueError("selfloop is not allowed")
        unique_edges = np.sort(self.edges, axis=1)
        if len(np.unique(unique_edges, axis=0)) != edge_count:
            raise ValueError("duplicate undirected edge")
        depth = self.initial_stage_m - self.bed_m
        if np.any(depth < 0) or np.any(depth > self.max_depth_m):
            raise ValueError("initial depth outside [0,max_depth_m]")
        if not np.array_equal(self.initial_stage_m[self.boundary_mask],
                              self.boundary_stage_m[0, self.boundary_mask]):
            raise ValueError("initial stage must equal time-zero boundary stage")
        if np.any(self.local_q_m3_s[:, self.boundary_mask] != 0):
            raise ValueError("signed local Q is only supported on internal storage nodes")
        sum_conductance = np.zeros(node_count)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            np.add.at(sum_conductance, self.edges[:, 0], self.conductance_m2_s)
            np.add.at(sum_conductance, self.edges[:, 1], self.conductance_m2_s)
            ratio = self.dt_s * sum_conductance / self.area_m2
            initial_storage = self.area_m2 * depth
            final_time = self.dt_s * step_count
        if not np.all(np.isfinite(ratio)) or np.any(ratio[~self.boundary_mask] > 1):
            raise ValueError("diffusive stability requires dt*sumK/area <= 1 (not CFL)")
        if not np.all(np.isfinite(initial_storage)) or not math.isfinite(final_time):
            raise ValueError("initial storage or time arithmetic is nonfinite")


@dataclass(frozen=True)
class FailedStep:
    step_n: int
    reason: str
    previous_stage_m: np.ndarray
    next_stage_m: np.ndarray
    next_storage_m3: np.ndarray
    qedges_m3_s: np.ndarray
    ledger_m3: np.ndarray

    def __post_init__(self):
        if type(self.step_n) is not int or not 0 <= self.step_n < 4096:
            raise ValueError("invalid failed step index")
        if self.reason not in ("negative_depth", "max_depth", "arithmetic_nonfinite"):
            raise ValueError("invalid failed reason")
        previous = np.asarray(self.previous_stage_m)
        if previous.ndim != 1 or not 1 <= len(previous) <= 4096:
            raise ValueError("failed node resource cap")
        for name in ("next_stage_m", "next_storage_m3"):
            if np.asarray(getattr(self, name)).shape != previous.shape:
                raise ValueError("failed candidate node shape mismatch")
        flux = np.asarray(self.qedges_m3_s)
        if flux.ndim != 1 or len(flux) > 16384 or np.asarray(self.ledger_m3).shape != (6,):
            raise ValueError("failed edge cap or ledger shape mismatch")
        for field in fields(self):
            if field.name not in ("step_n", "reason"):
                object.__setattr__(self, field.name, _immutable(getattr(self, field.name), "<f8"))


@dataclass(frozen=True)
class HydraulicsResult:
    inputs: HydraulicsInput
    status: str
    committed_steps: int
    stage_m: np.ndarray
    storage_m3: np.ndarray
    qedges_m3_s: np.ndarray
    time_s: np.ndarray
    ledger_m3: np.ndarray
    failed_step: FailedStep | None = None
    identity_sha256: str = ""

    def __post_init__(self):
        if not isinstance(self.inputs, HydraulicsInput):
            raise ValueError("result requires HydraulicsInput")
        _preflight(len(self.inputs.bed_m), len(self.inputs.edges),
                   len(self.inputs.local_q_m3_s), self.inputs.limits)
        expected = _array_specs(len(self.inputs.bed_m), len(self.inputs.edges),
                                len(self.inputs.local_q_m3_s), self.committed_steps,
                                self.failed_step is not None)
        for name in ("stage_m", "storage_m3", "qedges_m3_s", "time_s", "ledger_m3"):
            if np.asarray(getattr(self, name)).shape != expected[name][0]:
                raise ValueError(name + " result shape mismatch")
        for name in ("stage_m", "storage_m3", "qedges_m3_s", "time_s", "ledger_m3"):
            object.__setattr__(self, name, _immutable(getattr(self, name), "<f8"))
        if not self.identity_sha256:
            object.__setattr__(self, "identity_sha256", fingerprint(self))


def _arrays(result):
    arrays = {}
    for field in fields(result.inputs):
        value = getattr(result.inputs, field.name)
        if isinstance(value, np.ndarray):
            arrays["input_" + field.name] = value
    for name in ("stage_m", "storage_m3", "qedges_m3_s", "time_s", "ledger_m3"):
        arrays[name] = getattr(result, name)
    if result.failed_step is not None:
        for field in fields(result.failed_step):
            value = getattr(result.failed_step, field.name)
            if isinstance(value, np.ndarray):
                arrays["failed_" + field.name] = value
    return arrays


def _metadata(result):
    inputs = result.inputs
    return {"algorithm": ALGORITHM, "format": FORMAT, "geometry_mode": inputs.geometry_mode,
            "source": inputs.source, "datum": inputs.datum, "coords": inputs.coords,
            "dt_s": inputs.dt_s, "max_depth_m": inputs.max_depth_m,
            "limits": asdict(inputs.limits), "nodes": len(inputs.bed_m),
            "edges": len(inputs.edges), "steps": len(inputs.local_q_m3_s),
            "status": result.status, "committed_steps": result.committed_steps,
            "failed_step": None if result.failed_step is None else
            {"step_n": result.failed_step.step_n, "reason": result.failed_step.reason}}


def fingerprint(result):
    digest = hashlib.sha256()
    digest.update(json.dumps(_metadata(result), sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8"))
    for name, array in sorted(_arrays(result).items()):
        digest.update(json.dumps([name, array.dtype.str, list(array.shape)],
                                 separators=(",", ":")).encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _ledger(previous_storage, next_storage, local_q, net_q, inputs):
    internal = ~inputs.boundary_mask
    before = float(np.sum(previous_storage))
    after = float(np.sum(next_storage))
    local = float(inputs.dt_s * np.sum(local_q[internal]))
    boundary = float(-inputs.dt_s * np.sum(net_q[inputs.boundary_mask]))
    change = after - before
    return np.array([before, local, boundary, after, change, change - local - boundary])


def _failure_reason(stage, storage, flux, ledger, inputs):
    if not all(np.all(np.isfinite(array)) for array in (stage, storage, flux, ledger)):
        return "arithmetic_nonfinite"
    depth = stage - inputs.bed_m
    if np.any(depth < 0) or np.any(storage < 0):
        return "negative_depth"
    if np.any(depth > inputs.max_depth_m):
        return "max_depth"
    return None


def evaluate(inputs, *, cancel=None):
    """Advance synchronously; rejected steps and cancellation never commit state."""
    if not isinstance(inputs, HydraulicsInput):
        raise ValueError("inputs must be HydraulicsInput")
    if cancel is not None and not callable(cancel):
        raise ValueError("cancel must be a callable")
    inputs = HydraulicsInput(**{field.name: getattr(inputs, field.name) for field in fields(inputs)})
    node_count, edge_count, step_count = len(inputs.bed_m), len(inputs.edges), len(inputs.local_q_m3_s)
    stages = np.empty((step_count + 1, node_count))
    storages = np.empty_like(stages)
    fluxes = np.empty((step_count, edge_count))
    ledgers = np.empty((step_count, 6))
    stages[0] = inputs.initial_stage_m
    storages[0] = inputs.area_m2 * (stages[0] - inputs.bed_m)
    storages[0, inputs.boundary_mask] = 0
    committed = 0
    status = "completed"
    failed = None
    for step_n in range(step_count):
        if cancel is not None and cancel():
            status = "cancelled"
            break
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            flux = inputs.conductance_m2_s * (stages[step_n, inputs.edges[:, 0]] -
                                             stages[step_n, inputs.edges[:, 1]])
            net_q = np.zeros(node_count)
            np.add.at(net_q, inputs.edges[:, 0], -flux)
            np.add.at(net_q, inputs.edges[:, 1], flux)
            next_storage = storages[step_n] + inputs.dt_s * (inputs.local_q_m3_s[step_n] + net_q)
            next_storage[inputs.boundary_mask] = 0
            next_stage = inputs.bed_m + next_storage / inputs.area_m2
            next_stage[inputs.boundary_mask] = inputs.boundary_stage_m[step_n + 1, inputs.boundary_mask]
            ledger = _ledger(storages[step_n], next_storage, inputs.local_q_m3_s[step_n], net_q, inputs)
            reason = _failure_reason(next_stage, next_storage, flux, ledger, inputs)
        if reason is not None:
            status = "failed"
            failed = FailedStep(step_n, reason, stages[step_n], next_stage, next_storage,
                                flux, ledger)
            break
        stages[step_n + 1] = next_stage
        storages[step_n + 1] = next_storage
        fluxes[step_n] = flux
        ledgers[step_n] = ledger
        committed += 1
    result = HydraulicsResult(inputs, status, committed, stages[:committed + 1],
                              storages[:committed + 1], fluxes[:committed],
                              np.arange(committed + 1, dtype=float) * inputs.dt_s,
                              ledgers[:committed], failed)
    validate(result)
    return result


def _array_specs(node_count, edge_count, step_count, committed, failed):
    if type(committed) is not int or not 0 <= committed <= step_count:
        raise ValueError("invalid committed step count")
    float_type = np.dtype("<f8")
    specs = {}
    for name in ("bed_m", "area_m2", "initial_stage_m"):
        specs["input_" + name] = ((node_count,), float_type)
    for name in ("boundary_mask", "valid_mask", "protected_mask"):
        specs["input_" + name] = ((node_count,), np.dtype(bool))
    specs.update({
        "input_edges": ((edge_count, 2), np.dtype("<i8")),
        "input_conductance_m2_s": ((edge_count,), float_type),
        "input_local_q_m3_s": ((step_count, node_count), float_type),
        "input_boundary_stage_m": ((step_count + 1, node_count), float_type),
        "input_coords_m": ((node_count, 2), float_type),
        "stage_m": ((committed + 1, node_count), float_type),
        "storage_m3": ((committed + 1, node_count), float_type),
        "qedges_m3_s": ((committed, edge_count), float_type),
        "time_s": ((committed + 1,), float_type),
        "ledger_m3": ((committed, 6), float_type),
    })
    if failed:
        for name in ("previous_stage_m", "next_stage_m", "next_storage_m3"):
            specs["failed_" + name] = ((node_count,), float_type)
        specs["failed_qedges_m3_s"] = ((edge_count,), float_type)
        specs["failed_ledger_m3"] = ((6,), float_type)
    return specs


def _same(actual, expected, name, *, nonfinite=False):
    if not np.allclose(actual, expected, rtol=1e-12, atol=1e-12, equal_nan=nonfinite):
        raise ValueError("static equation mismatch: " + name)


def _prove_step(inputs, step_n, previous_stage, previous_storage,
                next_stage, next_storage, flux, ledger, *, failed=False):
    internal = ~inputs.boundary_mask
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        expected_flux = inputs.conductance_m2_s * (
            previous_stage[inputs.edges[:, 0]] - previous_stage[inputs.edges[:, 1]])
        _same(flux, expected_flux, "edge conductance", nonfinite=failed)
        incidence_q = np.zeros(len(inputs.bed_m))
        np.add.at(incidence_q, inputs.edges[:, 0], -flux)
        np.add.at(incidence_q, inputs.edges[:, 1], flux)
        expected_storage = np.zeros(len(inputs.bed_m))
        expected_storage[internal] = previous_storage[internal] + inputs.dt_s * (
            inputs.local_q_m3_s[step_n, internal] + incidence_q[internal])
        _same(next_storage, expected_storage, "Euler storage", nonfinite=failed)
        expected_stage = inputs.bed_m + next_storage / inputs.area_m2
        expected_stage[inputs.boundary_mask] = inputs.boundary_stage_m[step_n + 1, inputs.boundary_mask]
        _same(next_stage, expected_stage, "next stage/boundary indexing", nonfinite=failed)
        before = float(previous_storage.sum())
        after = float(next_storage.sum())
        local = float(inputs.dt_s * inputs.local_q_m3_s[step_n, internal].sum())
        external = float(-inputs.dt_s * incidence_q[inputs.boundary_mask].sum())
        expected_ledger = [before, local, external, after, after - before,
                           after - before - local - external]
        _same(ledger, expected_ledger, "ledger", nonfinite=failed)
        reason = _failure_reason(next_stage, next_storage, flux, ledger, inputs)
    if not failed:
        if reason is not None:
            raise ValueError("illegal committed state: " + reason)
        scale = max(1., abs(before), abs(after), abs(local), abs(external))
        if abs(ledger[5]) > 1e-12 * scale:
            raise ValueError("volume conservation residual")
    return reason


def validate(result):
    """Static proof against saved prev/next states. Never calls evaluate/advance."""
    if not isinstance(result, HydraulicsResult):
        raise ValueError("expected HydraulicsResult")
    inputs = HydraulicsInput(**{field.name: getattr(result.inputs, field.name)
                                for field in fields(result.inputs)})
    node_count, edge_count, step_count = len(inputs.bed_m), len(inputs.edges), len(inputs.local_q_m3_s)
    _preflight(node_count, edge_count, step_count, inputs.limits)
    committed = result.committed_steps
    specs = _array_specs(node_count, edge_count, step_count, committed, result.failed_step is not None)
    arrays = _arrays(result)
    if set(arrays) != set(specs):
        raise ValueError("array members mismatch")
    for name, array in arrays.items():
        shape, dtype = specs[name]
        if array.shape != shape or array.dtype != dtype or array.flags.writeable:
            raise ValueError("array contract mismatch: " + name)
        if not name.startswith("failed_") and not np.all(np.isfinite(array)):
            raise ValueError("nonfinite committed/input array: " + name)
    if result.status not in ("completed", "failed", "cancelled"):
        raise ValueError("invalid result status")
    if result.status == "completed" and (committed != step_count or result.failed_step is not None):
        raise ValueError("incomplete completed result")
    if result.status != "completed" and committed >= step_count:
        raise ValueError("terminal prefix exceeds horizon")
    if (result.status == "failed") != (result.failed_step is not None):
        raise ValueError("failed record/status mismatch")
    if not isinstance(result.identity_sha256, str) or result.identity_sha256 != fingerprint(result):
        raise ValueError("identity hash mismatch")
    _same(result.stage_m[0], inputs.initial_stage_m, "initial stage")
    initial_storage = inputs.area_m2 * (inputs.initial_stage_m - inputs.bed_m)
    initial_storage[inputs.boundary_mask] = 0
    _same(result.storage_m3[0], initial_storage, "initial storage")
    _same(result.time_s, np.arange(committed + 1) * inputs.dt_s, "physical time")
    for step_n in range(committed):
        _prove_step(inputs, step_n, result.stage_m[step_n], result.storage_m3[step_n],
                    result.stage_m[step_n + 1], result.storage_m3[step_n + 1],
                    result.qedges_m3_s[step_n], result.ledger_m3[step_n])
    if result.failed_step is not None:
        failed = result.failed_step
        if type(failed.step_n) is not int or failed.step_n != committed:
            raise ValueError("failed step is not immediately after committed prefix")
        _same(failed.previous_stage_m, result.stage_m[-1], "failed previous state")
        reason = _prove_step(inputs, committed, failed.previous_stage_m, result.storage_m3[-1],
                             failed.next_stage_m, failed.next_storage_m3,
                             failed.qedges_m3_s, failed.ledger_m3, failed=True)
        if reason is None or reason != failed.reason:
            raise ValueError("failed reason not supported by saved equations")
    return {"valid": True, "identity_sha256": result.identity_sha256,
            "committed_steps": committed, "static_equations_verified": True,
            "resources": _preflight(node_count, edge_count, step_count, inputs.limits)}


def save(result, path):
    """Validate, fsync, publish with atomic no-overwrite hardlink; always close fd."""
    validate(result)
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    metadata = _metadata(result)
    metadata["identity_sha256"] = result.identity_sha256
    payload = json.dumps(metadata, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(payload) > MAX_METADATA_BYTES:
        raise ValueError("metadata cap")
    descriptor, temporary = tempfile.mkstemp(prefix=".dynamic-hydro-", dir=path.parent)
    try:
        stream = os.fdopen(descriptor, "w+b")
        descriptor = None
        with stream:
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("metadata.json", payload)
                for name, array in _arrays(result).items():
                    with archive.open(name + ".npy", "w") as member:
                        np.lib.format.write_array(member, array, version=(1, 0), allow_pickle=False)
            if stream.tell() > MAX_FILE_BYTES:
                raise ValueError("bundle cap")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.unlink(temporary)
    return path


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _read_header(stream, info, shape, dtype):
    if np.lib.format.read_magic(stream) != (1, 0):
        raise ValueError("only NPY v1 headers supported")
    length_bytes = stream.read(2)
    if len(length_bytes) != 2 or int.from_bytes(length_bytes, "little") > MAX_HEADER_BYTES - 10:
        raise ValueError("NPY header byte cap")
    header_length = int.from_bytes(length_bytes, "little")
    header_payload = stream.read(header_length)
    if len(header_payload) != header_length:
        raise ValueError("truncated NPY header")
    header_stream = io.BytesIO(length_bytes + header_payload)
    actual_shape, fortran, actual_dtype = np.lib.format.read_array_header_1_0(
        header_stream, max_header_size=MAX_HEADER_BYTES)
    if actual_shape != shape or fortran or actual_dtype != dtype or actual_dtype.hasobject:
        raise ValueError("NPY header shape/dtype/order mismatch")
    payload_bytes = math.prod(shape) * dtype.itemsize
    if stream.tell() > MAX_HEADER_BYTES or info.file_size != stream.tell() + payload_bytes:
        raise ValueError("NPY exact payload size mismatch")
    return payload_bytes


def load(path):
    """Bounded static read: all headers inspected before payload arrays are allocated."""
    with Path(path).open("rb") as file:
        if os.fstat(file.fileno()).st_size > MAX_FILE_BYTES:
            raise ValueError("bundle file cap")
        with zipfile.ZipFile(file) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(infos) > MAX_MEMBERS or len(set(names)) != len(names):
                raise ValueError("duplicate members or member cap")
            if any(info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1 or
                   info.is_dir() for info in infos):
                raise ValueError("only unencrypted stored file members supported")
            if sum(info.file_size for info in infos) > MAX_FILE_BYTES:
                raise ValueError("bundle payload cap")
            if "metadata.json" not in names or archive.getinfo("metadata.json").file_size > MAX_METADATA_BYTES:
                raise ValueError("metadata absent or cap exceeded")
            meta = json.loads(archive.read("metadata.json"), object_pairs_hook=_unique_json,
                              parse_constant=_reject_constant)
            keys = {"algorithm", "format", "geometry_mode", "source", "datum", "coords", "dt_s",
                    "max_depth_m", "limits", "nodes", "edges", "steps", "status", "committed_steps",
                    "failed_step", "identity_sha256"}
            if not isinstance(meta, dict) or set(meta) != keys:
                raise ValueError("metadata schema mismatch")
            if meta["algorithm"] != ALGORITHM or meta["format"] != FORMAT:
                raise ValueError("algorithm/format mismatch")
            identity = meta["identity_sha256"]
            if (not isinstance(identity, str) or len(identity) != 64 or
                    any(character not in "0123456789abcdef" for character in identity)):
                raise ValueError("invalid identity hash")
            if any(type(meta[name]) is not int for name in ("nodes", "edges", "steps")):
                raise ValueError("dimensions must be integers")
            if not isinstance(meta["limits"], dict) or set(meta["limits"]) != {field.name for field in fields(ResourceLimits)}:
                raise ValueError("limits schema mismatch")
            limits = ResourceLimits(**meta["limits"])
            _preflight(meta["nodes"], meta["edges"], meta["steps"], limits)
            failed_meta = meta["failed_step"]
            if failed_meta is not None and (not isinstance(failed_meta, dict) or
                                           set(failed_meta) != {"step_n", "reason"}):
                raise ValueError("failed metadata schema mismatch")
            specs = _array_specs(meta["nodes"], meta["edges"], meta["steps"],
                                 meta["committed_steps"], failed_meta is not None)
            if set(names) != {"metadata.json"} | {name + ".npy" for name in specs}:
                raise ValueError("unexpected or missing archive members")
            for name, (shape, dtype) in specs.items():
                info = archive.getinfo(name + ".npy")
                with archive.open(info) as stream:
                    _read_header(stream, info, shape, dtype)
            arrays = {}
            for name, (shape, dtype) in specs.items():
                info = archive.getinfo(name + ".npy")
                with archive.open(info) as stream:
                    payload_bytes = _read_header(stream, info, shape, dtype)
                    payload = stream.read(payload_bytes + 1)
                    if len(payload) != payload_bytes:
                        raise ValueError("NPY truncated or trailing payload")
                    arrays[name] = np.frombuffer(payload, dtype=dtype).reshape(shape)
    kwargs = {name.removeprefix("input_"): array for name, array in arrays.items()
              if name.startswith("input_")}
    kwargs.update({name: meta[name] for name in ("source", "datum", "coords", "dt_s",
                                                "max_depth_m", "geometry_mode")})
    inputs = HydraulicsInput(**kwargs, limits=limits)
    failed = None
    if failed_meta is not None:
        failed = FailedStep(**failed_meta, **{name.removeprefix("failed_"): array
                                              for name, array in arrays.items() if name.startswith("failed_")})
    result = HydraulicsResult(inputs, meta["status"], meta["committed_steps"],
                              **{name: arrays[name] for name in ("stage_m", "storage_m3", "qedges_m3_s",
                                                                "time_s", "ledger_m3")},
                              failed_step=failed, identity_sha256=meta["identity_sha256"])
    validate(result)
    return result
