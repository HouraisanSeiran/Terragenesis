"""Conservative independent-cell runoff; no river routing or terrain mutation."""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np


ALGORITHM = "rainfall-runoff-v1"
SCHEMA = "rainfall-runoff-npz-v1"
MAX_STEPS = 100_000
MAX_CELLS = 100_000
MAX_ENTRIES = 1_000_000
MAX_BYTES = 256 * 1024 * 1024
STEP_KEYS = (
    "rain_mm_h", "local_q_m3_s", "infiltration_mm", "actual_et_mm",
    "percolation_mm", "excess_mm", "fast_release_mm", "slow_release_mm",
    "rain_volume_m3", "et_volume_m3", "outflow_volume_m3",
    "storage_change_m3", "balance_residual_m3",
)
STATE_KEYS = ("soil_mm", "fast_mm", "slow_mm")
ARRAY_KEYS = STEP_KEYS + STATE_KEYS + ("area_m2",)
CELL_ORDER = "input area/rain column order; no coordinates inferred"
Q_SEMANTICS = "timestep-average local discharge; not river-routed"
METADATA_KEYS = {"algorithm", "schema", "source_id", "dt_s", "parameters",
                 "parameter_sha256", "cell_order", "q_semantics"}


def _scalar(value, name, maximum, positive=False):
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.integer, np.floating))
            or not math.isfinite(value) or value < 0 or value > maximum
            or (positive and value == 0)):
        raise ValueError(f"invalid {name}: finite {'positive' if positive else 'nonnegative'} <= {maximum} required")


@dataclass(frozen=True)
class RunoffParameters:
    """Spatially uniform illustrative parameters, not a calibrated catchment."""

    infiltration_capacity_mm_h: float = 15.0
    soil_capacity_mm: float = 150.0
    potential_et_mm_h: float = 0.15
    percolation_mm_h: float = 1.0
    fast_tau_s: float = 3600.0
    slow_tau_s: float = 259200.0
    initial_soil_mm: float = 30.0
    initial_fast_mm: float = 0.0
    initial_slow_mm: float = 0.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            _scalar(value, name, 1e12 if name.endswith("tau_s") else 1e6,
                    positive=name.endswith("tau_s"))
        if self.initial_soil_mm > self.soil_capacity_mm:
            raise ValueError("initial soil exceeds capacity")


def _budget(steps, cells):
    if (steps < 1 or cells < 1 or steps > MAX_STEPS or cells > MAX_CELLS
            or steps * cells > MAX_ENTRIES
            or 24 * 8 * (steps + 1) * cells > MAX_BYTES):
        raise ValueError("rainfall-runoff resource budget exceeded")


def _array(value, name, shape):
    if (not isinstance(value, np.ndarray) or value.shape != shape
            or value.dtype.kind not in "fiu" or not np.isfinite(value).all()
            or np.any(value < 0)):
        raise ValueError(f"invalid nonnegative finite numeric array: {name}")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _strict_json(payload):
    def pairs(items):
        parsed = {}
        for key, value in items:
            if key in parsed:
                raise ValueError("duplicate JSON key")
            parsed[key] = value
        return parsed

    def constant(value):
        raise ValueError(f"invalid JSON constant: {value}")

    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)


def _hash(array):
    digest = hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _release(storage, incoming, dt_s, tau_s):
    ratio = dt_s / tau_s
    fraction = -math.expm1(-ratio)
    inflow_release = (ratio / 2 - ratio**2 / 6 + ratio**3 / 24
                      if ratio < 1e-4 else 1 - fraction / ratio)
    released = storage * fraction + incoming * inflow_release
    return storage + incoming - released, released


def simulate_rainfall_runoff(rain_mm_h, area_m2, *, dt_s, source_id,
                            parameters=None):
    """Return independent arrays; rates are constant over each physical timestep."""
    if not isinstance(rain_mm_h, np.ndarray) or rain_mm_h.ndim != 2:
        raise ValueError("rain_mm_h must be an ndarray [T,N]")
    steps, cells = rain_mm_h.shape
    _budget(steps, cells)
    _array(rain_mm_h, "rain_mm_h", (steps, cells))
    _array(area_m2, "area_m2", (cells,))
    if np.any(area_m2 <= 0) or np.any(area_m2 > 1e12) or np.any(rain_mm_h > 1e6):
        raise ValueError("area or rain outside supported bounds")
    _scalar(dt_s, "dt_s", 1e7, positive=True)
    if dt_s < 1e-6:
        raise ValueError("dt_s must be >= 1e-6")
    if not isinstance(source_id, str) or not source_id.strip() or len(source_id) > 4096:
        raise ValueError("source_id must be a nonempty string of at most 4096 characters")
    if parameters is None:
        parameters = RunoffParameters()
    if not isinstance(parameters, RunoffParameters):
        raise ValueError("parameters must be RunoffParameters")
    parameters.__post_init__()
    result = {key: np.zeros((steps, cells), dtype=np.float64) for key in STEP_KEYS}
    result["rain_mm_h"] = rain_mm_h.astype(np.float64, copy=True)
    result["area_m2"] = area_m2.astype(np.float64, copy=True)
    for key, initial in zip(STATE_KEYS, (parameters.initial_soil_mm,
                                        parameters.initial_fast_mm, parameters.initial_slow_mm)):
        result[key] = np.zeros((steps + 1, cells), dtype=np.float64)
        result[key][0] = initial
    hours = dt_s / 3600.0
    volume_factor = result["area_m2"] / 1000.0
    for step in range(steps):
        rain_depth = result["rain_mm_h"][step] * hours
        soil_before = result["soil_mm"][step]
        infiltrated = np.minimum(np.minimum(rain_depth, parameters.infiltration_capacity_mm_h * hours),
                                  np.maximum(parameters.soil_capacity_mm - soil_before, 0.0))
        soil = soil_before + infiltrated
        actual_et = np.minimum(soil, parameters.potential_et_mm_h * hours)
        soil = soil - actual_et
        percolated = np.minimum(soil, parameters.percolation_mm_h * hours)
        soil = soil - percolated
        excess = rain_depth - infiltrated
        fast, fast_release = _release(result["fast_mm"][step], excess, dt_s, parameters.fast_tau_s)
        slow, slow_release = _release(result["slow_mm"][step], percolated, dt_s, parameters.slow_tau_s)
        result["soil_mm"][step + 1] = soil
        result["fast_mm"][step + 1] = fast
        result["slow_mm"][step + 1] = slow
        for key, value in (("infiltration_mm", infiltrated), ("actual_et_mm", actual_et),
                           ("percolation_mm", percolated), ("excess_mm", excess),
                           ("fast_release_mm", fast_release), ("slow_release_mm", slow_release)):
            result[key][step] = value
        outflow = (fast_release + slow_release) * volume_factor
        change = ((soil - soil_before) + (fast - result["fast_mm"][step])
                  + (slow - result["slow_mm"][step])) * volume_factor
        result["rain_volume_m3"][step] = rain_depth * volume_factor
        result["et_volume_m3"][step] = actual_et * volume_factor
        result["outflow_volume_m3"][step] = outflow
        result["storage_change_m3"][step] = change
        result["balance_residual_m3"][step] = rain_depth * volume_factor - actual_et * volume_factor - outflow - change
        result["local_q_m3_s"][step] = outflow / dt_s
    parameter_values = asdict(parameters)
    result["metadata"] = {
        "algorithm": ALGORITHM, "schema": SCHEMA, "source_id": source_id,
        "dt_s": float(dt_s), "parameters": parameter_values,
        "parameter_sha256": hashlib.sha256(_json(parameter_values).encode("utf-8")).hexdigest(),
        "cell_order": CELL_ORDER,
        "q_semantics": Q_SEMANTICS,
    }
    validate_rainfall_runoff_result(result)
    return result


def validate_rainfall_runoff_result(result):
    """Recompute saved component balances and volume ledger, without simulation."""
    if not isinstance(result, dict) or set(result) != set(ARRAY_KEYS) | {"metadata"}:
        raise ValueError("unexpected result keys")
    metadata = result["metadata"]
    if (not isinstance(metadata, dict) or set(metadata) != METADATA_KEYS
            or metadata.get("schema") != SCHEMA or metadata.get("algorithm") != ALGORITHM
            or metadata.get("cell_order") != CELL_ORDER or metadata.get("q_semantics") != Q_SEMANTICS):
        raise ValueError("unsupported schema or algorithm")
    try:
        if not isinstance(metadata["parameters"], dict) or set(metadata["parameters"]) != set(asdict(RunoffParameters())):
            raise ValueError("invalid parameter keys")
        parameters = RunoffParameters(**metadata["parameters"])
        dt_s = metadata["dt_s"]
        source = metadata["source_id"]
        expected_hash = hashlib.sha256(_json(metadata["parameters"]).encode("utf-8")).hexdigest()
        if expected_hash != metadata["parameter_sha256"]:
            raise ValueError("parameter identity mismatch")
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("invalid metadata") from error
    _scalar(dt_s, "dt_s", 1e7, positive=True)
    if dt_s < 1e-6 or not isinstance(source, str) or not source.strip() or len(source) > 4096:
        raise ValueError("invalid timestep/source")
    rain = result["rain_mm_h"]
    if not isinstance(rain, np.ndarray) or rain.ndim != 2:
        raise ValueError("invalid rain shape")
    steps, cells = rain.shape
    _budget(steps, cells)
    for key in ARRAY_KEYS:
        shape = (cells,) if key == "area_m2" else ((steps + 1, cells) if key in STATE_KEYS else (steps, cells))
        array = result[key]
        if not isinstance(array, np.ndarray) or array.shape != shape or array.dtype != np.dtype("float64") or not np.isfinite(array).all():
            raise ValueError(f"invalid saved array {key}")
        if key not in ("storage_change_m3", "balance_residual_m3") and np.any(array < 0):
            raise ValueError(f"negative saved array {key}")
    if np.any(result["area_m2"] <= 0) or np.any(result["area_m2"] > 1e12) or np.any(rain > 1e6):
        raise ValueError("invalid saved forcing bounds")

    def equal(actual, expected, name):
        if not np.allclose(actual, expected, rtol=1e-10, atol=1e-8):
            raise ValueError(f"saved balance/ledger mismatch: {name}")

    for key, initial in zip(STATE_KEYS, (parameters.initial_soil_mm, parameters.initial_fast_mm, parameters.initial_slow_mm)):
        equal(result[key][0], initial, key + " initial")
    if np.any(result["soil_mm"] > parameters.soil_capacity_mm + 1e-8):
        raise ValueError("saved soil exceeds capacity")
    rain_depth = rain * (dt_s / 3600.0)
    hours = dt_s / 3600.0
    equal(result["infiltration_mm"], np.minimum(np.minimum(rain_depth, parameters.infiltration_capacity_mm_h * hours),
          np.maximum(parameters.soil_capacity_mm - result["soil_mm"][:-1], 0.0)), "infiltration limits")
    available_soil = result["soil_mm"][:-1] + result["infiltration_mm"]
    equal(result["actual_et_mm"], np.minimum(available_soil, parameters.potential_et_mm_h * hours), "ET limits")
    equal(result["percolation_mm"], np.minimum(available_soil - result["actual_et_mm"],
          parameters.percolation_mm_h * hours), "percolation limits")
    equal(rain_depth, result["infiltration_mm"] + result["excess_mm"], "rain partition")
    equal(np.diff(result["soil_mm"], axis=0), result["infiltration_mm"] - result["actual_et_mm"] - result["percolation_mm"], "soil")
    equal(np.diff(result["fast_mm"], axis=0), result["excess_mm"] - result["fast_release_mm"], "fast")
    equal(np.diff(result["slow_mm"], axis=0), result["percolation_mm"] - result["slow_release_mm"], "slow")
    for state_key, incoming_key, release_key, tau_s in (
            ("fast_mm", "excess_mm", "fast_release_mm", parameters.fast_tau_s),
            ("slow_mm", "percolation_mm", "slow_release_mm", parameters.slow_tau_s)):
        ratio = dt_s / tau_s
        fraction = -np.expm1(-ratio)
        incoming_fraction = (ratio / 2 - ratio**2 / 6 + ratio**3 / 24
                             if ratio < 1e-4 else 1 - fraction / ratio)
        expected_release = result[state_key][:-1] * fraction + result[incoming_key] * incoming_fraction
        equal(result[release_key], expected_release, release_key + " constitutive equation")
    factor = result["area_m2"] / 1000.0
    rain_volume = rain_depth * factor
    et_volume = result["actual_et_mm"] * factor
    outflow = (result["fast_release_mm"] + result["slow_release_mm"]) * factor
    change = sum(np.diff(result[key], axis=0) for key in STATE_KEYS) * factor
    for key, expected in (("rain_volume_m3", rain_volume), ("et_volume_m3", et_volume),
                          ("outflow_volume_m3", outflow), ("storage_change_m3", change),
                          ("local_q_m3_s", outflow / dt_s)):
        equal(result[key], expected, key)
    residual = rain_volume - et_volume - outflow - change
    equal(result["balance_residual_m3"], residual, "residual ledger")
    if np.any(np.abs(residual) > 1e-8 + 1e-10 * (rain_volume + et_volume + outflow + np.abs(change))):
        raise ValueError("nonconservative saved step")
    return {"valid": True, "max_abs_balance_residual_m3": float(np.max(np.abs(residual)))}


def save_rainfall_runoff_npz(path, result):
    """Publish a complete archive atomically; an existing path is never replaced."""
    validate_rainfall_runoff_result(result)
    manifest = {"metadata": result["metadata"],
                "metadata_sha256": hashlib.sha256(_json(result["metadata"]).encode("utf-8")).hexdigest(),
                "hashes": {key: _hash(result[key]) for key in ARRAY_KEYS}}
    payload = _json(manifest).encode("utf-8")
    if len(payload) > 65536:
        raise ValueError("metadata too large")
    target = Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = tempfile.mkstemp(prefix=".runoff-", suffix=".npz", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            np.savez(stream, manifest=np.frombuffer(payload, dtype=np.uint8),
                     **{key: result[key] for key in ARRAY_KEYS})
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def load_rainfall_runoff_npz(path):
    """Bound ZIP/NPY sizes before allocation, verify hashes, then static balances."""
    expected_names = {key + ".npy" for key in ARRAY_KEYS} | {"manifest.npy"}
    with open(path, "rb") as stream:
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(expected_names) or {member.filename for member in members} != expected_names:
                raise ValueError("unexpected archive members")
            if sum(member.file_size for member in members) > MAX_BYTES:
                raise ValueError("archive resource budget exceeded")
            shapes = {}
            for member in members:
                with archive.open(member) as array_stream:
                    version = np.lib.format.read_magic(array_stream)
                    if version != (1, 0):
                        raise ValueError("unsupported NPY version")
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(array_stream, max_header_size=4096)
                    header_bytes = array_stream.tell()
                    if member.filename == "manifest.npy":
                        if dtype != np.dtype("uint8") or len(shape) != 1 or not 0 < shape[0] <= 65536:
                            raise ValueError("invalid manifest")
                    elif dtype != np.dtype("float64") or len(shape) not in (1, 2) or any(size < 1 or size > MAX_STEPS + 1 for size in shape):
                        raise ValueError("invalid archive array header")
                    if fortran or math.prod(shape) * dtype.itemsize + header_bytes != member.file_size:
                        raise ValueError("invalid archive array size")
                    shapes[member.filename] = shape
            rain_shape = shapes["rain_mm_h.npy"]
            if len(rain_shape) != 2:
                raise ValueError("invalid archive rain shape")
            steps, cells = rain_shape
            _budget(steps, cells)
            for key in ARRAY_KEYS:
                expected_shape = (cells,) if key == "area_m2" else ((steps + 1, cells) if key in STATE_KEYS else (steps, cells))
                if shapes[key + ".npy"] != expected_shape:
                    raise ValueError("inconsistent archive shapes")
        stream.seek(0)
        with np.load(stream, allow_pickle=False) as archive:
            try:
                manifest = _strict_json(archive["manifest"].tobytes().decode("utf-8"))
                if set(manifest) != {"metadata", "metadata_sha256", "hashes"} or set(manifest["hashes"]) != set(ARRAY_KEYS):
                    raise ValueError("invalid manifest keys")
                if hashlib.sha256(_json(manifest["metadata"]).encode("utf-8")).hexdigest() != manifest["metadata_sha256"]:
                    raise ValueError("metadata hash mismatch")
                result = {key: archive[key] for key in ARRAY_KEYS}
                result["metadata"] = manifest["metadata"]
                if any(_hash(result[key]) != manifest["hashes"][key] for key in ARRAY_KEYS):
                    raise ValueError("archive hash mismatch")
            except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
                raise ValueError("invalid archive manifest") from error
    validate_rainfall_runoff_result(result)
    return result
