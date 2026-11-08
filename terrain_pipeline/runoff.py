"""runoff: merged M4 implementation; source locations precede each statement."""
from __future__ import annotations

from collections import deque as _m4_mountain_runoff_routing_deque
from dataclasses import asdict as _m4_hydrology_seasonal_asdict
from dataclasses import asdict as _m4_hydrology_seasonal_validation_asdict
from dataclasses import asdict as _m4_lowland_runoff_asdict
from dataclasses import asdict as _m4_native_30m_runoff_asdict
from dataclasses import asdict as _m4_rainfall_runoff_asdict
from dataclasses import asdict as _m4_real_dem_rainfall_routing_asdict
from dataclasses import dataclass as _m4_hydrology_seasonal_dataclass
from dataclasses import dataclass as _m4_lowland_runoff_dataclass
from dataclasses import dataclass as _m4_rainfall_runoff_dataclass
from dataclasses import replace as _m4_hydrology_seasonal_validation_replace
from diffusion.physical_config import PhysicalGenerationConfig as _m4_native_30m_runoff_PhysicalGenerationConfig
from numba import njit as _m4_lowland_runoff_njit
from pathlib import Path as _m4_hydrology_seasonal_Path
from pathlib import Path as _m4_hydrology_seasonal_hybrid_Path
from pathlib import Path as _m4_hydrology_seasonal_validation_Path
from pathlib import Path as _m4_mountain_runoff_routing_Path
from pathlib import Path as _m4_rainfall_runoff_Path
from scipy.ndimage import maximum_filter as _m4_lowland_runoff_maximum_filter
from scipy.ndimage import minimum_filter as _m4_lowland_runoff_minimum_filter
from terrain_pipeline.climate_forcing import MONTH_DAYS as _m4_lowland_runoff_MONTH_DAYS
import argparse as _m4_hydrology_seasonal_validation_argparse
import hashlib as _m4_hydrology_seasonal_hybrid_hashlib
import hashlib as _m4_mountain_runoff_routing_hashlib
import hashlib as _m4_native_30m_runoff_hashlib
import hashlib as _m4_rainfall_runoff_hashlib
import heapq as _m4_hydrology_seasonal_hybrid_heapq
import json as _m4_hydrology_seasonal_hybrid_json
import json as _m4_hydrology_seasonal_json
import json as _m4_hydrology_seasonal_validation_json
import json as _m4_native_30m_runoff_json
import json as _m4_rainfall_runoff_json
import math as _m4_hydrology_seasonal_math
import math as _m4_mountain_runoff_routing_math
import math as _m4_rainfall_runoff_math
import math as _m4_real_dem_rainfall_routing_math
import numpy as _m4_hydrology_seasonal_hybrid_np
import numpy as _m4_hydrology_seasonal_np
import numpy as _m4_hydrology_seasonal_validation_np
import numpy as _m4_large_runoff_np
import numpy as _m4_lowland_runoff_np
import numpy as _m4_mountain_runoff_routing_np
import numpy as _m4_native_30m_runoff_np
import numpy as _m4_rainfall_runoff_np
import numpy as _m4_real_dem_rainfall_routing_np
import numpy as _m4_runoff_np
import numpy as _m4_saved_graph_lowland_np
import os as _m4_hydrology_seasonal_os
import os as _m4_mountain_runoff_routing_os
import os as _m4_rainfall_runoff_os
import shutil as _m4_hydrology_seasonal_hybrid_shutil
import string as _m4_native_30m_runoff_string
import tempfile as _m4_hydrology_seasonal_tempfile
import tempfile as _m4_mountain_runoff_routing_tempfile
import tempfile as _m4_rainfall_runoff_tempfile
import zipfile as _m4_mountain_runoff_routing_zipfile
import zipfile as _m4_rainfall_runoff_zipfile

CATEGORY = "B"

# --- terrain_pipeline/rainfall_runoff.py:15 ---
RUNOFF_ALGORITHM = "rainfall-runoff-v1"

# --- terrain_pipeline/rainfall_runoff.py:16 ---
RUNOFF_SCHEMA = "rainfall-runoff-npz-v1"

# --- terrain_pipeline/rainfall_runoff.py:17 ---
RUNOFF_MAX_STEPS = 100_000

# --- terrain_pipeline/rainfall_runoff.py:18 ---
RUNOFF_MAX_CELLS = 100_000

# --- terrain_pipeline/rainfall_runoff.py:19 ---
RUNOFF_MAX_ENTRIES = 1_000_000

# --- terrain_pipeline/rainfall_runoff.py:20 ---
RUNOFF_MAX_BYTES = 256 * 1024 * 1024

# --- terrain_pipeline/rainfall_runoff.py:21 ---
STEP_KEYS = (
    "rain_mm_h", "local_q_m3_s", "infiltration_mm", "actual_et_mm",
    "percolation_mm", "excess_mm", "fast_release_mm", "slow_release_mm",
    "rain_volume_m3", "et_volume_m3", "outflow_volume_m3",
    "storage_change_m3", "balance_residual_m3",
)

# --- terrain_pipeline/rainfall_runoff.py:27 ---
RUNOFF_STATE_KEYS = ("soil_mm", "fast_mm", "slow_mm")

# --- terrain_pipeline/rainfall_runoff.py:28 ---
RUNOFF_ARRAY_KEYS = STEP_KEYS + RUNOFF_STATE_KEYS + ("area_m2",)

# --- terrain_pipeline/rainfall_runoff.py:29 ---
CELL_ORDER = "input area/rain column order; no coordinates inferred"

# --- terrain_pipeline/rainfall_runoff.py:30 ---
Q_SEMANTICS = "timestep-average local discharge; not river-routed"

# --- terrain_pipeline/rainfall_runoff.py:31 ---
METADATA_KEYS = {"algorithm", "schema", "source_id", "dt_s", "parameters",
                 "parameter_sha256", "cell_order", "q_semantics"}

# --- terrain_pipeline/rainfall_runoff.py:35 ---
def _scalar(value, name, maximum, positive=False):
    if (isinstance(value, (bool, _m4_rainfall_runoff_np.bool_)) or not isinstance(value, (int, float, _m4_rainfall_runoff_np.integer, _m4_rainfall_runoff_np.floating))
            or not _m4_rainfall_runoff_math.isfinite(value) or value < 0 or value > maximum
            or (positive and value == 0)):
        raise ValueError(f"invalid {name}: finite {'positive' if positive else 'nonnegative'} <= {maximum} required")

# --- terrain_pipeline/rainfall_runoff.py:43 ---
@_m4_rainfall_runoff_dataclass(frozen=True)
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
        for name, value in _m4_rainfall_runoff_asdict(self).items():
            _scalar(value, name, 1e12 if name.endswith("tau_s") else 1e6,
                    positive=name.endswith("tau_s"))
        if self.initial_soil_mm > self.soil_capacity_mm:
            raise ValueError("initial soil exceeds capacity")

# --- terrain_pipeline/rainfall_runoff.py:64 ---
def _budget(steps, cells):
    if (steps < 1 or cells < 1 or steps > RUNOFF_MAX_STEPS or cells > RUNOFF_MAX_CELLS
            or steps * cells > RUNOFF_MAX_ENTRIES
            or 24 * 8 * (steps + 1) * cells > RUNOFF_MAX_BYTES):
        raise ValueError("rainfall-runoff resource budget exceeded")

# --- terrain_pipeline/rainfall_runoff.py:71 ---
def _array(value, name, shape):
    if (not isinstance(value, _m4_rainfall_runoff_np.ndarray) or value.shape != shape
            or value.dtype.kind not in "fiu" or not _m4_rainfall_runoff_np.isfinite(value).all()
            or _m4_rainfall_runoff_np.any(value < 0)):
        raise ValueError(f"invalid nonnegative finite numeric array: {name}")

# --- terrain_pipeline/rainfall_runoff.py:78 ---
def _json(value):
    return _m4_rainfall_runoff_json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

# --- terrain_pipeline/rainfall_runoff.py:82 ---
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

    return _m4_rainfall_runoff_json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)

# --- terrain_pipeline/rainfall_runoff.py:97 ---
def _hash(array):
    digest = _m4_rainfall_runoff_hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()

# --- terrain_pipeline/rainfall_runoff.py:105 ---
def _release(storage, incoming, dt_s, tau_s):
    ratio = dt_s / tau_s
    fraction = -_m4_rainfall_runoff_math.expm1(-ratio)
    inflow_release = (ratio / 2 - ratio**2 / 6 + ratio**3 / 24
                      if ratio < 1e-4 else 1 - fraction / ratio)
    released = storage * fraction + incoming * inflow_release
    return storage + incoming - released, released

# --- terrain_pipeline/rainfall_runoff.py:114 ---
def simulate_rainfall_runoff(rain_mm_h, area_m2, *, dt_s, source_id,
                            parameters=None):
    """Return independent arrays; rates are constant over each physical timestep."""
    if not isinstance(rain_mm_h, _m4_rainfall_runoff_np.ndarray) or rain_mm_h.ndim != 2:
        raise ValueError("rain_mm_h must be an ndarray [T,N]")
    steps, cells = rain_mm_h.shape
    _budget(steps, cells)
    _array(rain_mm_h, "rain_mm_h", (steps, cells))
    _array(area_m2, "area_m2", (cells,))
    if _m4_rainfall_runoff_np.any(area_m2 <= 0) or _m4_rainfall_runoff_np.any(area_m2 > 1e12) or _m4_rainfall_runoff_np.any(rain_mm_h > 1e6):
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
    result = {key: _m4_rainfall_runoff_np.zeros((steps, cells), dtype=_m4_rainfall_runoff_np.float64) for key in STEP_KEYS}
    result["rain_mm_h"] = rain_mm_h.astype(_m4_rainfall_runoff_np.float64, copy=True)
    result["area_m2"] = area_m2.astype(_m4_rainfall_runoff_np.float64, copy=True)
    for key, initial in zip(RUNOFF_STATE_KEYS, (parameters.initial_soil_mm,
                                        parameters.initial_fast_mm, parameters.initial_slow_mm)):
        result[key] = _m4_rainfall_runoff_np.zeros((steps + 1, cells), dtype=_m4_rainfall_runoff_np.float64)
        result[key][0] = initial
    hours = dt_s / 3600.0
    volume_factor = result["area_m2"] / 1000.0
    for step in range(steps):
        rain_depth = result["rain_mm_h"][step] * hours
        soil_before = result["soil_mm"][step]
        infiltrated = _m4_rainfall_runoff_np.minimum(_m4_rainfall_runoff_np.minimum(rain_depth, parameters.infiltration_capacity_mm_h * hours),
                                  _m4_rainfall_runoff_np.maximum(parameters.soil_capacity_mm - soil_before, 0.0))
        soil = soil_before + infiltrated
        actual_et = _m4_rainfall_runoff_np.minimum(soil, parameters.potential_et_mm_h * hours)
        soil = soil - actual_et
        percolated = _m4_rainfall_runoff_np.minimum(soil, parameters.percolation_mm_h * hours)
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
    parameter_values = _m4_rainfall_runoff_asdict(parameters)
    result["metadata"] = {
        "algorithm": RUNOFF_ALGORITHM, "schema": RUNOFF_SCHEMA, "source_id": source_id,
        "dt_s": float(dt_s), "parameters": parameter_values,
        "parameter_sha256": _m4_rainfall_runoff_hashlib.sha256(_json(parameter_values).encode("utf-8")).hexdigest(),
        "cell_order": CELL_ORDER,
        "q_semantics": Q_SEMANTICS,
    }
    validate_rainfall_runoff_result(result)
    return result

# --- terrain_pipeline/rainfall_runoff.py:185 ---
def validate_rainfall_runoff_result(result):
    """Recompute saved component balances and volume ledger, without simulation."""
    if not isinstance(result, dict) or set(result) != set(RUNOFF_ARRAY_KEYS) | {"metadata"}:
        raise ValueError("unexpected result keys")
    metadata = result["metadata"]
    if (not isinstance(metadata, dict) or set(metadata) != METADATA_KEYS
            or metadata.get("schema") != RUNOFF_SCHEMA or metadata.get("algorithm") != RUNOFF_ALGORITHM
            or metadata.get("cell_order") != CELL_ORDER or metadata.get("q_semantics") != Q_SEMANTICS):
        raise ValueError("unsupported schema or algorithm")
    try:
        if not isinstance(metadata["parameters"], dict) or set(metadata["parameters"]) != set(_m4_rainfall_runoff_asdict(RunoffParameters())):
            raise ValueError("invalid parameter keys")
        parameters = RunoffParameters(**metadata["parameters"])
        dt_s = metadata["dt_s"]
        source = metadata["source_id"]
        expected_hash = _m4_rainfall_runoff_hashlib.sha256(_json(metadata["parameters"]).encode("utf-8")).hexdigest()
        if expected_hash != metadata["parameter_sha256"]:
            raise ValueError("parameter identity mismatch")
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("invalid metadata") from error
    _scalar(dt_s, "dt_s", 1e7, positive=True)
    if dt_s < 1e-6 or not isinstance(source, str) or not source.strip() or len(source) > 4096:
        raise ValueError("invalid timestep/source")
    rain = result["rain_mm_h"]
    if not isinstance(rain, _m4_rainfall_runoff_np.ndarray) or rain.ndim != 2:
        raise ValueError("invalid rain shape")
    steps, cells = rain.shape
    _budget(steps, cells)
    for key in RUNOFF_ARRAY_KEYS:
        shape = (cells,) if key == "area_m2" else ((steps + 1, cells) if key in RUNOFF_STATE_KEYS else (steps, cells))
        array = result[key]
        if not isinstance(array, _m4_rainfall_runoff_np.ndarray) or array.shape != shape or array.dtype != _m4_rainfall_runoff_np.dtype("float64") or not _m4_rainfall_runoff_np.isfinite(array).all():
            raise ValueError(f"invalid saved array {key}")
        if key not in ("storage_change_m3", "balance_residual_m3") and _m4_rainfall_runoff_np.any(array < 0):
            raise ValueError(f"negative saved array {key}")
    if _m4_rainfall_runoff_np.any(result["area_m2"] <= 0) or _m4_rainfall_runoff_np.any(result["area_m2"] > 1e12) or _m4_rainfall_runoff_np.any(rain > 1e6):
        raise ValueError("invalid saved forcing bounds")

    def equal(actual, expected, name):
        if not _m4_rainfall_runoff_np.allclose(actual, expected, rtol=1e-10, atol=1e-8):
            raise ValueError(f"saved balance/ledger mismatch: {name}")

    for key, initial in zip(RUNOFF_STATE_KEYS, (parameters.initial_soil_mm, parameters.initial_fast_mm, parameters.initial_slow_mm)):
        equal(result[key][0], initial, key + " initial")
    if _m4_rainfall_runoff_np.any(result["soil_mm"] > parameters.soil_capacity_mm + 1e-8):
        raise ValueError("saved soil exceeds capacity")
    rain_depth = rain * (dt_s / 3600.0)
    hours = dt_s / 3600.0
    equal(result["infiltration_mm"], _m4_rainfall_runoff_np.minimum(_m4_rainfall_runoff_np.minimum(rain_depth, parameters.infiltration_capacity_mm_h * hours),
          _m4_rainfall_runoff_np.maximum(parameters.soil_capacity_mm - result["soil_mm"][:-1], 0.0)), "infiltration limits")
    available_soil = result["soil_mm"][:-1] + result["infiltration_mm"]
    equal(result["actual_et_mm"], _m4_rainfall_runoff_np.minimum(available_soil, parameters.potential_et_mm_h * hours), "ET limits")
    equal(result["percolation_mm"], _m4_rainfall_runoff_np.minimum(available_soil - result["actual_et_mm"],
          parameters.percolation_mm_h * hours), "percolation limits")
    equal(rain_depth, result["infiltration_mm"] + result["excess_mm"], "rain partition")
    equal(_m4_rainfall_runoff_np.diff(result["soil_mm"], axis=0), result["infiltration_mm"] - result["actual_et_mm"] - result["percolation_mm"], "soil")
    equal(_m4_rainfall_runoff_np.diff(result["fast_mm"], axis=0), result["excess_mm"] - result["fast_release_mm"], "fast")
    equal(_m4_rainfall_runoff_np.diff(result["slow_mm"], axis=0), result["percolation_mm"] - result["slow_release_mm"], "slow")
    for state_key, incoming_key, release_key, tau_s in (
            ("fast_mm", "excess_mm", "fast_release_mm", parameters.fast_tau_s),
            ("slow_mm", "percolation_mm", "slow_release_mm", parameters.slow_tau_s)):
        ratio = dt_s / tau_s
        fraction = -_m4_rainfall_runoff_np.expm1(-ratio)
        incoming_fraction = (ratio / 2 - ratio**2 / 6 + ratio**3 / 24
                             if ratio < 1e-4 else 1 - fraction / ratio)
        expected_release = result[state_key][:-1] * fraction + result[incoming_key] * incoming_fraction
        equal(result[release_key], expected_release, release_key + " constitutive equation")
    factor = result["area_m2"] / 1000.0
    rain_volume = rain_depth * factor
    et_volume = result["actual_et_mm"] * factor
    outflow = (result["fast_release_mm"] + result["slow_release_mm"]) * factor
    change = sum(_m4_rainfall_runoff_np.diff(result[key], axis=0) for key in RUNOFF_STATE_KEYS) * factor
    for key, expected in (("rain_volume_m3", rain_volume), ("et_volume_m3", et_volume),
                          ("outflow_volume_m3", outflow), ("storage_change_m3", change),
                          ("local_q_m3_s", outflow / dt_s)):
        equal(result[key], expected, key)
    residual = rain_volume - et_volume - outflow - change
    equal(result["balance_residual_m3"], residual, "residual ledger")
    if _m4_rainfall_runoff_np.any(_m4_rainfall_runoff_np.abs(residual) > 1e-8 + 1e-10 * (rain_volume + et_volume + outflow + _m4_rainfall_runoff_np.abs(change))):
        raise ValueError("nonconservative saved step")
    return {"valid": True, "max_abs_balance_residual_m3": float(_m4_rainfall_runoff_np.max(_m4_rainfall_runoff_np.abs(residual)))}

# --- terrain_pipeline/rainfall_runoff.py:268 ---
def save_rainfall_runoff_npz(path, result):
    """Publish a complete archive atomically; an existing path is never replaced."""
    validate_rainfall_runoff_result(result)
    manifest = {"metadata": result["metadata"],
                "metadata_sha256": _m4_rainfall_runoff_hashlib.sha256(_json(result["metadata"]).encode("utf-8")).hexdigest(),
                "hashes": {key: _hash(result[key]) for key in RUNOFF_ARRAY_KEYS}}
    payload = _json(manifest).encode("utf-8")
    if len(payload) > 65536:
        raise ValueError("metadata too large")
    target = _m4_rainfall_runoff_Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = _m4_rainfall_runoff_tempfile.mkstemp(prefix=".runoff-", suffix=".npz", dir=target.parent)
    try:
        with _m4_rainfall_runoff_os.fdopen(descriptor, "wb") as stream:
            _m4_rainfall_runoff_np.savez(stream, manifest=_m4_rainfall_runoff_np.frombuffer(payload, dtype=_m4_rainfall_runoff_np.uint8),
                     **{key: result[key] for key in RUNOFF_ARRAY_KEYS})
            stream.flush()
            _m4_rainfall_runoff_os.fsync(stream.fileno())
        _m4_rainfall_runoff_os.link(temporary, target)
    finally:
        _m4_rainfall_runoff_os.unlink(temporary)

# --- terrain_pipeline/rainfall_runoff.py:292 ---
def load_rainfall_runoff_npz(path):
    """Bound ZIP/NPY sizes before allocation, verify hashes, then static balances."""
    expected_names = {key + ".npy" for key in RUNOFF_ARRAY_KEYS} | {"manifest.npy"}
    with open(path, "rb") as stream:
        with _m4_rainfall_runoff_zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(expected_names) or {member.filename for member in members} != expected_names:
                raise ValueError("unexpected archive members")
            if sum(member.file_size for member in members) > RUNOFF_MAX_BYTES:
                raise ValueError("archive resource budget exceeded")
            shapes = {}
            for member in members:
                with archive.open(member) as array_stream:
                    version = _m4_rainfall_runoff_np.lib.format.read_magic(array_stream)
                    if version != (1, 0):
                        raise ValueError("unsupported NPY version")
                    shape, fortran, dtype = _m4_rainfall_runoff_np.lib.format.read_array_header_1_0(array_stream, max_header_size=4096)
                    header_bytes = array_stream.tell()
                    if member.filename == "manifest.npy":
                        if dtype != _m4_rainfall_runoff_np.dtype("uint8") or len(shape) != 1 or not 0 < shape[0] <= 65536:
                            raise ValueError("invalid manifest")
                    elif dtype != _m4_rainfall_runoff_np.dtype("float64") or len(shape) not in (1, 2) or any(size < 1 or size > RUNOFF_MAX_STEPS + 1 for size in shape):
                        raise ValueError("invalid archive array header")
                    if fortran or _m4_rainfall_runoff_math.prod(shape) * dtype.itemsize + header_bytes != member.file_size:
                        raise ValueError("invalid archive array size")
                    shapes[member.filename] = shape
            rain_shape = shapes["rain_mm_h.npy"]
            if len(rain_shape) != 2:
                raise ValueError("invalid archive rain shape")
            steps, cells = rain_shape
            _budget(steps, cells)
            for key in RUNOFF_ARRAY_KEYS:
                expected_shape = (cells,) if key == "area_m2" else ((steps + 1, cells) if key in RUNOFF_STATE_KEYS else (steps, cells))
                if shapes[key + ".npy"] != expected_shape:
                    raise ValueError("inconsistent archive shapes")
        stream.seek(0)
        with _m4_rainfall_runoff_np.load(stream, allow_pickle=False) as archive:
            try:
                manifest = _strict_json(archive["manifest"].tobytes().decode("utf-8"))
                if set(manifest) != {"metadata", "metadata_sha256", "hashes"} or set(manifest["hashes"]) != set(RUNOFF_ARRAY_KEYS):
                    raise ValueError("invalid manifest keys")
                if _m4_rainfall_runoff_hashlib.sha256(_json(manifest["metadata"]).encode("utf-8")).hexdigest() != manifest["metadata_sha256"]:
                    raise ValueError("metadata hash mismatch")
                result = {key: archive[key] for key in RUNOFF_ARRAY_KEYS}
                result["metadata"] = manifest["metadata"]
                if any(_hash(result[key]) != manifest["hashes"][key] for key in RUNOFF_ARRAY_KEYS):
                    raise ValueError("archive hash mismatch")
            except (KeyError, TypeError, UnicodeError, _m4_rainfall_runoff_json.JSONDecodeError) as error:
                raise ValueError("invalid archive manifest") from error
    validate_rainfall_runoff_result(result)
    return result

# --- terrain_pipeline/surface_rivers/metric_runoff.py:9 ---
RUNOFF_LEDGER_KEYS = ("rain_volume_m3", "et_volume_m3", "outflow_volume_m3",
               "storage_change_m3", "balance_residual_m3")

# --- terrain_pipeline/surface_rivers/metric_runoff.py:11 ---
METRIC_STATE_KEYS = ("soil_mm", "fast_mm", "slow_mm")

# --- terrain_pipeline/surface_rivers/metric_runoff.py:14 ---
def _output_state_indices(output_indices, steps):
    if output_indices is None:
        return _m4_runoff_np.arange(steps + 1, dtype=_m4_runoff_np.int64)
    if not isinstance(output_indices, (list, tuple, _m4_runoff_np.ndarray)):
        raise ValueError("output_indices must be increasing end-state indices")
    indices = _m4_runoff_np.asarray(output_indices)
    if indices.ndim != 1 or indices.dtype.kind not in "iu" or indices.size == 0:
        raise ValueError("output_indices must be nonempty integer end-state indices")
    if _m4_runoff_np.any(indices < 1) or _m4_runoff_np.any(indices > steps) or _m4_runoff_np.any(indices[1:] <= indices[:-1]):
        raise ValueError("output_indices must be strictly increasing in 1..T")
    return indices.astype(_m4_runoff_np.int64, copy=True)

# --- terrain_pipeline/surface_rivers/metric_runoff.py:27 ---
def runoff_from_forcing(terrain, forcing, *, parameters=None, output_indices=None):
    """Run every forcing interval; optionally sample state frames after solving."""
    from terrain_pipeline.common_infra import RainfallForcing as _m4_runoff_RainfallForcing
    from terrain_pipeline.common_infra import TerrainGrid as _m4_runoff_TerrainGrid
    if not isinstance(terrain, _m4_runoff_TerrainGrid) or not isinstance(forcing, _m4_runoff_RainfallForcing):
        raise ValueError("TerrainGrid and RainfallForcing required")
    if parameters is not None and not isinstance(parameters, RunoffParameters):
        raise ValueError("parameters must be RunoffParameters")
    if forcing.rain_mm_h.shape[1:] != terrain.valid_mask.shape:
        raise ValueError("forcing grid shape must match terrain")
    if _m4_runoff_np.any(forcing.rain_mm_h[:, ~terrain.valid_mask] != 0.):
        raise ValueError("rain on invalid terrain cells is unsupported")
    intervals = forcing.interval_seconds
    if _m4_runoff_np.any(intervals != intervals[0]):
        raise ValueError("uniform forcing intervals required by fixed-dt solver")
    indices = _output_state_indices(output_indices, intervals.size)
    cell_ids = _m4_runoff_np.flatnonzero(terrain.valid_mask).astype(_m4_runoff_np.int64)
    rain = forcing.rain_mm_h.reshape(intervals.size, -1)[:, cell_ids]
    area = _m4_runoff_np.full(cell_ids.size, terrain.cell_area_m2, dtype=_m4_runoff_np.float64)
    native = simulate_rainfall_runoff(rain, area, dt_s=float(intervals[0]),
                                     source_id=forcing.source_id, parameters=parameters)
    with _m4_runoff_np.errstate(over="ignore", invalid="ignore"):
        per_step = {key: _m4_runoff_np.sum(native[key], axis=1, dtype=_m4_runoff_np.float64) for key in RUNOFF_LEDGER_KEYS}
        totals = {key: float(_m4_runoff_np.sum(values, dtype=_m4_runoff_np.float64))
                  for key, values in per_step.items()}
    if any(not _m4_runoff_np.isfinite(values).all() for values in per_step.values()) or any(
            not _m4_runoff_np.isfinite(value) for value in totals.values()):
        raise ValueError("runoff ledger overflow: finite totals required")
    ledger = per_step | {"totals_m3": totals}
    output_times = forcing.time_seconds[indices].copy()
    return {
        "native_result": native,
        "valid_cell_ids": cell_ids,
        "state_time_seconds": forcing.time_seconds.copy(),
        "output_time_seconds": output_times,
        "output_state_indices": indices,
        "output_states_mm": {key: native[key][indices].copy() for key in METRIC_STATE_KEYS},
        "ledger": ledger,
        "metadata": {
            "terrain_identity_sha256": terrain.identity_sha256,
            "forcing_identity_sha256": forcing.identity_sha256,
            "dt_solver_seconds": float(intervals[0]),
            "solver_role": "independent_cell_hydrology_no_channel_hydraulics",
            "dt_output_seconds": _m4_runoff_np.diff(output_times),
            "q_semantics": "interval_average_local_release_not_river_routed",
            "state_semantics": "end_of_interval",
            "status": "diagnostic_runoff",
            "hydraulic_ready": False,
            "natural_outlet_verified": False,
            "publishable": False,
        },
    }

# --- terrain_pipeline/surface_rivers/metric_runoff.py:79 ---
def boundary_flux(boundary, proposed_q_m3_s):
    """Apply outward-positive boundary conditions to proposed cell fluxes.

    This filters proposals only; it does not solve for a physical boundary flux.
    """
    from terrain_pipeline.common_infra import BoundaryGrid as _m4_runoff_BoundaryGrid
    if not isinstance(boundary, _m4_runoff_BoundaryGrid):
        raise ValueError("BoundaryGrid required")
    proposal = _m4_runoff_np.asarray(proposed_q_m3_s)
    if (proposal.shape != boundary.kind.shape or proposal.dtype.kind not in "fiu"
            or not _m4_runoff_np.isfinite(proposal).all()):
        raise ValueError("finite numeric proposed_q_m3_s matching boundary shape required")
    if _m4_runoff_np.any((boundary.kind == "unknown_boundary") & (proposal != 0.)):
        raise ValueError("nonzero flux on unknown boundary is unresolved")
    result = _m4_runoff_np.zeros(boundary.kind.shape, dtype=_m4_runoff_np.float64)
    open_mask = boundary.kind == "open_outflow"
    result[open_mask] = _m4_runoff_np.maximum(proposal[open_mask], 0.)
    stage_mask = boundary.kind == "prescribed_stage"
    result[stage_mask] = _m4_runoff_np.where(boundary.allow_inflow[stage_mask], proposal[stage_mask],
                                  _m4_runoff_np.maximum(proposal[stage_mask], 0.))
    discharge_mask = boundary.kind == "prescribed_discharge"
    if boundary.discharge_m3_s is not None:
        result[discharge_mask] = boundary.discharge_m3_s[discharge_mask]
    return result

# --- terrain_pipeline/surface_rivers/metric_large_runoff.py:14 ---
MAX_LARGE_CELLS = 1024 * 1024

# --- terrain_pipeline/surface_rivers/metric_large_runoff.py:15 ---
MAX_LARGE_STEPS = 3

# --- terrain_pipeline/surface_rivers/metric_large_runoff.py:16 ---
MAX_LARGE_BYTES = 1024 * 1024 * 1024

# --- terrain_pipeline/surface_rivers/metric_large_runoff.py:19 ---
def _batch_size(steps, requested):
    limit = min(RUNOFF_MAX_CELLS, RUNOFF_MAX_ENTRIES // steps,
                RUNOFF_MAX_BYTES // (24 * 8 * (steps + 1)))
    if requested is None:
        return limit
    if type(requested) is not int or not 1 <= requested <= limit:
        raise ValueError("chunk_size exceeds fixed-dt solver budget")
    return requested

# --- terrain_pipeline/surface_rivers/metric_large_runoff.py:29 ---
def _large_budget(steps, cells, grid_cells, sampled_states, batch_size):
    if not 1 <= steps <= MAX_LARGE_STEPS or not 1 <= cells <= grid_cells <= MAX_LARGE_CELLS:
        raise ValueError("large runoff cells/steps budget exceeded")
    native_bytes = 8 * cells * (len(STEP_KEYS) * steps + len(RUNOFF_STATE_KEYS) * (steps + 1) + 1)
    chunk_bytes = 8 * min(cells, batch_size) * (len(STEP_KEYS) * steps + len(RUNOFF_STATE_KEYS) * (steps + 1) + 1)
    estimated_peak = (native_bytes + 8 * grid_cells * (steps + 2)
                      + 8 * cells * (len(RUNOFF_STATE_KEYS) * sampled_states + 1)
                      + 2 * chunk_bytes)
    if estimated_peak > MAX_LARGE_BYTES:
        raise ValueError("large runoff estimated memory budget exceeded")

# --- terrain_pipeline/surface_rivers/metric_large_runoff.py:41 ---
def validate_large_rainfall_runoff_result(native, *, chunk_size=None):
    """Validate a full native result with the frozen validator in bounded columns."""
    if not isinstance(native, dict) or set(native) != set(RUNOFF_ARRAY_KEYS) | {"metadata"}:
        raise ValueError("unexpected large native result keys")
    rain = native["rain_mm_h"]
    if not isinstance(rain, _m4_large_runoff_np.ndarray) or rain.ndim != 2:
        raise ValueError("invalid large native rain shape")
    steps, cells = rain.shape
    batch_size = _batch_size(steps, chunk_size) if steps > 0 else 0
    _large_budget(steps, cells, cells, 0, batch_size)
    for key in RUNOFF_ARRAY_KEYS:
        expected = (cells,) if key == "area_m2" else (
            (steps + 1, cells) if key in RUNOFF_STATE_KEYS else (steps, cells))
        value = native[key]
        if not isinstance(value, _m4_large_runoff_np.ndarray) or value.dtype != _m4_large_runoff_np.float64 or value.shape != expected:
            raise ValueError("invalid large native shape/dtype: " + key)
    maximum_residual = 0.
    for start in range(0, cells, batch_size):
        stop = min(start + batch_size, cells)
        subset = {key: (native[key][start:stop] if key == "area_m2"
                        else native[key][:, start:stop]) for key in RUNOFF_ARRAY_KEYS}
        subset["metadata"] = native["metadata"]
        report = validate_rainfall_runoff_result(subset)
        maximum_residual = max(maximum_residual, report["max_abs_balance_residual_m3"])
    return {"valid": True, "max_abs_balance_residual_m3": maximum_residual}

# --- terrain_pipeline/surface_rivers/metric_large_runoff.py:68 ---
def runoff_from_forcing_large(terrain, forcing, *, parameters=None,
                              output_indices=None, chunk_size=None):
    """Return the regular adapter shape while solving bounded valid-cell batches."""
    from terrain_pipeline.common_infra import RainfallForcing as _m4_large_runoff_RainfallForcing
    from terrain_pipeline.common_infra import TerrainGrid as _m4_large_runoff_TerrainGrid
    if not isinstance(terrain, _m4_large_runoff_TerrainGrid) or not isinstance(forcing, _m4_large_runoff_RainfallForcing):
        raise ValueError("TerrainGrid and RainfallForcing required")
    if parameters is not None and not isinstance(parameters, RunoffParameters):
        raise ValueError("parameters must be RunoffParameters")
    if forcing.rain_mm_h.shape[1:] != terrain.valid_mask.shape:
        raise ValueError("forcing grid shape must match terrain")
    if _m4_large_runoff_np.any(forcing.rain_mm_h[:, ~terrain.valid_mask] != 0.):
        raise ValueError("rain on invalid terrain cells is unsupported")
    intervals = forcing.interval_seconds
    if _m4_large_runoff_np.any(intervals != intervals[0]):
        raise ValueError("uniform forcing intervals required by fixed-dt solver")
    indices = _output_state_indices(output_indices, intervals.size)
    batch_size = _batch_size(intervals.size, chunk_size)
    cell_ids = _m4_large_runoff_np.flatnonzero(terrain.valid_mask).astype(_m4_large_runoff_np.int64)
    steps, cells = intervals.size, cell_ids.size
    _large_budget(steps, cells, terrain.elevation_m.size, indices.size, batch_size)
    native = {key: _m4_large_runoff_np.empty((steps, cells), dtype=_m4_large_runoff_np.float64) for key in STEP_KEYS}
    native.update({key: _m4_large_runoff_np.empty((steps + 1, cells), dtype=_m4_large_runoff_np.float64) for key in RUNOFF_STATE_KEYS})
    native["area_m2"] = _m4_large_runoff_np.empty(cells, dtype=_m4_large_runoff_np.float64)
    flattened_rain = forcing.rain_mm_h.reshape(steps, -1)
    for start in range(0, cells, batch_size):
        stop = min(start + batch_size, cells)
        batch_rain = flattened_rain[:, cell_ids[start:stop]]
        batch_area = _m4_large_runoff_np.full(stop - start, terrain.cell_area_m2, dtype=_m4_large_runoff_np.float64)
        batch = simulate_rainfall_runoff(batch_rain, batch_area, dt_s=float(intervals[0]),
                                        source_id=forcing.source_id, parameters=parameters)
        for key in RUNOFF_ARRAY_KEYS:
            if key == "area_m2":
                native[key][start:stop] = batch[key]
            else:
                native[key][:, start:stop] = batch[key]
        if start == 0:
            native["metadata"] = batch["metadata"]
        del batch
    with _m4_large_runoff_np.errstate(over="ignore", invalid="ignore"):
        per_step = {key: _m4_large_runoff_np.sum(native[key], axis=1, dtype=_m4_large_runoff_np.float64) for key in RUNOFF_LEDGER_KEYS}
        totals = {key: float(_m4_large_runoff_np.sum(values, dtype=_m4_large_runoff_np.float64)) for key, values in per_step.items()}
    if any(not _m4_large_runoff_np.isfinite(values).all() for values in per_step.values()) or any(
            not _m4_large_runoff_np.isfinite(value) for value in totals.values()):
        raise ValueError("runoff ledger overflow: finite totals required")
    output_times = forcing.time_seconds[indices].copy()
    return {
        "native_result": native,
        "valid_cell_ids": cell_ids,
        "state_time_seconds": forcing.time_seconds.copy(),
        "output_time_seconds": output_times,
        "output_state_indices": indices,
        "output_states_mm": {key: native[key][indices].copy() for key in RUNOFF_STATE_KEYS},
        "ledger": per_step | {"totals_m3": totals},
        "metadata": {
            "terrain_identity_sha256": terrain.identity_sha256,
            "forcing_identity_sha256": forcing.identity_sha256,
            "dt_solver_seconds": float(intervals[0]),
            "solver_role": "independent_cell_hydrology_no_channel_hydraulics",
            "dt_output_seconds": _m4_large_runoff_np.diff(output_times),
            "q_semantics": "interval_average_local_release_not_river_routed",
            "state_semantics": "end_of_interval", "status": "diagnostic_runoff",
            "hydraulic_ready": False, "natural_outlet_verified": False,
            "publishable": False,
        },
    }

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:11 ---
LOWLAND_ALGORITHM = "td_lowland_runoff_channel_separation_v1"

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:12 ---
OBJECT_FLAGS = {"river": 1, "wetland": 2, "shallow_lake": 4,
                "seasonal_swale": 8, "floodplain": 16}

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:14 ---
MONTH_SECONDS = _m4_lowland_runoff_MONTH_DAYS * 86400.

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:15 ---
YEAR_SECONDS = float(MONTH_SECONDS.sum())

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:19 ---
@_m4_lowland_runoff_dataclass(frozen=True)
class LowlandRunoffConfig:
    relief_radius_m: float = 300.
    lowland_relief_m: float = 20.
    lowland_slope: float = .025
    upland_initiation_area_m2: float = 1000000.
    lowland_initiation_area_m2: float = 4000000.
    channel_q_threshold_m3_s: float = .015
    persistent_months: int = 8
    seasonal_months: int = 2
    simulation_years: int = 3
    shallow_lake_min_raise_m: float = .5
    shallow_lake_max_depth_m: float = 4.
    wetland_min_raise_m: float = .03
    floodplain_storage_depth_m: float = .04
    swale_storage_depth_m: float = .02
    wetland_storage_depth_m: float = .12
    monthly_release_fraction: float = .35
    monthly_evaporation_depth_m: float = .015
    floodplain_max_dag_distance_m: float = 300.
    floodplain_max_height_above_channel_m: float = 1.

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:42 ---
@_m4_lowland_runoff_njit(cache=True)
def _accumulate(local, receiver, order):
    routed = local.astype(_m4_lowland_runoff_np.float64)
    for cell in order:
        target = receiver[cell]
        if target >= 0:
            routed[target] += routed[cell]
    return routed

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:52 ---
@_m4_lowland_runoff_njit(cache=True)
def _monthly_storage(local, receiver, order, capacity, storage, evaporation,
                     release_fraction, perimeter):
    inflow = local.astype(_m4_lowland_runoff_np.float64)
    routed = _m4_lowland_runoff_np.zeros(local.size, _m4_lowland_runoff_np.float64)
    et_cells = _m4_lowland_runoff_np.zeros(local.size, _m4_lowland_runoff_np.float64)
    evaporated = 0.
    released = 0.
    overflow_total = 0.
    unknown = 0.
    unresolved = 0.
    for cell in order:
        water = inflow[cell] + storage[cell]
        if capacity[cell] > 0.:
            # Overflow bypasses retention; evaporation and release act on the
            # finite retained reservoir, including this month's incoming water.
            overflow = max(0., water - capacity[cell])
            retained = min(water, capacity[cell])
            loss = min(retained, evaporation)
            retained -= loss
            release = retained * release_fraction
            storage[cell] = retained - release
            out = overflow + release
            evaporated += loss
            et_cells[cell] = loss
            released += release
            overflow_total += overflow
        else:
            out = water
            storage[cell] = 0.
        routed[cell] = out
        target = receiver[cell]
        if target >= 0:
            inflow[target] += out
        elif perimeter[cell]:
            unknown += out
        else:
            unresolved += out
    return routed, et_cells, evaporated, released, overflow_total, unknown, unresolved

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:92 ---
class EventRunoffRouter:
    """Finite saved DAG state, with immutable classification owned by caller.

    Each step admits its local runoff, then routes upstream to downstream in
    the same step. This bucket approximation has no channel travel-time model.
    Monthly rates use an explicit reference month of 30 days by default.
    """

    def __init__(self, receiver, topological_order, capacity_m3, initial_storage_m3,
                 perimeter_mask, spacing_m, *, config=None):
        self.config = LowlandRunoffConfig() if config is None else config
        if not isinstance(self.config, LowlandRunoffConfig):
            raise ValueError("LowlandRunoffConfig required")
        capacity = _m4_lowland_runoff_np.asarray(capacity_m3, _m4_lowland_runoff_np.float64)
        storage = _m4_lowland_runoff_np.asarray(initial_storage_m3, _m4_lowland_runoff_np.float64)
        receiver = _m4_lowland_runoff_np.asarray(receiver)
        order = _m4_lowland_runoff_np.asarray(topological_order)
        perimeter = _m4_lowland_runoff_np.asarray(perimeter_mask)
        if (capacity.ndim not in (1, 2) or not 1 <= capacity.size <= 4_000_000
                or storage.shape != capacity.shape or perimeter.shape != capacity.shape
                or perimeter.dtype.kind != "b"
                or receiver.size != capacity.size or order.size != capacity.size
                or receiver.dtype.kind not in "iu" or order.dtype.kind not in "iu"):
            raise ValueError("bounded storage arrays, boolean perimeter and integer saved DAG required")
        receiver, order = receiver.ravel(), order.ravel()
        if (_m4_lowland_runoff_np.any(receiver < -1) or _m4_lowland_runoff_np.any(receiver >= capacity.size)
                or not _m4_lowland_runoff_np.array_equal(_m4_lowland_runoff_np.sort(order), _m4_lowland_runoff_np.arange(capacity.size))):
            raise ValueError("receiver range or topological permutation invalid")
        rank = _m4_lowland_runoff_np.empty(capacity.size, _m4_lowland_runoff_np.int64)
        rank[order] = _m4_lowland_runoff_np.arange(capacity.size)
        sources = _m4_lowland_runoff_np.flatnonzero(receiver >= 0)
        if _m4_lowland_runoff_np.any(rank[sources] >= rank[receiver[sources]]):
            raise ValueError("saved DAG must be upstream to downstream")
        if (not _m4_lowland_runoff_np.isfinite(capacity).all() or not _m4_lowland_runoff_np.isfinite(storage).all()
                or _m4_lowland_runoff_np.any(capacity < 0.) or _m4_lowland_runoff_np.any(storage < 0.) or _m4_lowland_runoff_np.any(storage > capacity)
                or not _m4_lowland_runoff_np.isfinite(storage.sum()) or not _m4_lowland_runoff_np.isfinite(capacity.sum())
                or not _m4_lowland_runoff_np.isfinite(spacing_m) or not 0. < spacing_m <= 1e6
                or not _m4_lowland_runoff_np.isfinite(self.config.monthly_release_fraction)
                or not 0. <= self.config.monthly_release_fraction <= 1.
                or not _m4_lowland_runoff_np.isfinite(self.config.monthly_evaporation_depth_m)
                or self.config.monthly_evaporation_depth_m < 0.):
            raise ValueError("finite physical capacity, storage and event rates required")
        self.shape = capacity.shape
        self.receiver = receiver.astype(_m4_lowland_runoff_np.int64, copy=True)
        self.order = order.astype(_m4_lowland_runoff_np.int64, copy=True)
        self.capacity = capacity.ravel().copy()
        self.storage = storage.ravel().copy()
        self.perimeter = perimeter.ravel().copy()
        self.cell_area_m2 = float(spacing_m) ** 2

    def step(self, local_runoff_m3, interval_seconds, *, reference_month_seconds=30. * 86400.):
        """Advance one bounded interval; return per-cell volumes and a ledger."""
        local = _m4_lowland_runoff_np.asarray(local_runoff_m3, _m4_lowland_runoff_np.float64)
        if (local.shape != self.shape or not _m4_lowland_runoff_np.isfinite(local).all() or _m4_lowland_runoff_np.any(local < 0.)
                or not _m4_lowland_runoff_np.isfinite(local.sum())
                or not _m4_lowland_runoff_np.isfinite(interval_seconds) or not 0. < interval_seconds <= 32. * 86400.
                or not _m4_lowland_runoff_np.isfinite(reference_month_seconds) or reference_month_seconds <= 0.):
            raise ValueError("finite nonnegative runoff and bounded positive physical interval required")
        ratio = interval_seconds / reference_month_seconds
        release = self.config.monthly_release_fraction
        release_fraction = (1. if release == 1. else
                            -_m4_lowland_runoff_np.expm1(_m4_lowland_runoff_np.log1p(-release) * ratio))
        evaporation = self.config.monthly_evaporation_depth_m * self.cell_area_m2 * ratio
        before = float(self.storage.sum())
        input_volume = float(local.sum())
        if not _m4_lowland_runoff_np.isfinite(evaporation) or not _m4_lowland_runoff_np.isfinite(before + input_volume):
            raise ValueError("finite aggregate event water and evaporation required")
        routed, et_cells, et, released, overflow, unknown, unresolved = _monthly_storage(
            local.ravel(), self.receiver, self.order, self.capacity, self.storage,
            evaporation, release_fraction, self.perimeter)
        after = float(self.storage.sum())
        ledger = dict(interval_seconds=float(interval_seconds),
                      reference_month_seconds=float(reference_month_seconds),
                      input_runoff_m3=input_volume, storage_before_m3=before,
                      storage_after_m3=after, evaporation_m3=float(et),
                      storage_release_m3=float(released), overflow_m3=float(overflow),
                      unknown_boundary_export_m3=float(unknown),
                      unresolved_terminal_export_m3=float(unresolved),
                      balance_residual_m3=input_volume + before - after - et - unknown - unresolved)
        return dict(arrays=dict(outflow_m3=routed.reshape(self.shape),
                                routed_q_m3_s=(routed / interval_seconds).reshape(self.shape),
                                storage_m3=self.storage.reshape(self.shape).copy(),
                                evaporation_m3=et_cells.reshape(self.shape)), ledger=ledger)

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:177 ---
def prepare_event_routing(receiver, topological_order, capacity_m3, initial_storage_m3,
                          perimeter_mask, spacing_m, *, config=None):
    """Validate and copy a saved routing state once for a streamed event run."""
    return EventRunoffRouter(receiver, topological_order, capacity_m3, initial_storage_m3,
                             perimeter_mask, spacing_m, config=config)

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:185 ---
@_m4_lowland_runoff_njit(cache=True)
def _close(mask, receiver, order):
    result = mask.copy()
    for cell in order:
        if result[cell] and receiver[cell] >= 0:
            result[receiver[cell]] = True
    return result

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:194 ---
@_m4_lowland_runoff_njit(cache=True)
def _first_object(flags, receiver, order):
    owner = _m4_lowland_runoff_np.full(flags.size, -1, _m4_lowland_runoff_np.int64)
    received_flags = _m4_lowland_runoff_np.zeros(flags.size, _m4_lowland_runoff_np.uint8)
    for k in range(order.size - 1, -1, -1):
        cell = order[k]
        if flags[cell] != 0:
            owner[cell] = cell
            received_flags[cell] = flags[cell]
        elif receiver[cell] >= 0:
            owner[cell] = owner[receiver[cell]]
            received_flags[cell] = received_flags[receiver[cell]]
    return owner, received_flags

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:209 ---
@_m4_lowland_runoff_njit(cache=True)
def _channel_corridor(channel, receiver, order, work, cols, spacing,
                      max_distance, max_hand):
    distance = _m4_lowland_runoff_np.full(channel.size, _m4_lowland_runoff_np.inf)
    channel_height = _m4_lowland_runoff_np.zeros(channel.size, _m4_lowland_runoff_np.float64)
    corridor = _m4_lowland_runoff_np.zeros(channel.size, _m4_lowland_runoff_np.bool_)
    for k in range(order.size - 1, -1, -1):
        cell = order[k]
        if channel[cell]:
            distance[cell] = 0.
            channel_height[cell] = work[cell]
        elif receiver[cell] >= 0:
            target = receiver[cell]
            dr = cell // cols - target // cols
            dc = cell % cols - target % cols
            distance[cell] = distance[target] + spacing * _m4_lowland_runoff_np.sqrt(dr * dr + dc * dc)
            channel_height[cell] = channel_height[target]
        corridor[cell] = (distance[cell] <= max_distance
                          and work[cell] - channel_height[cell] <= max_hand)
    return corridor

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:230 ---
def _validate(height, raises, receiver, order, area, spacing, runoff, config):
    if height.ndim != 2 or height.size == 0 or height.size > 4_000_000:
        raise ValueError("bounded nonempty 2D terrain required")
    if raises.shape != height.shape or area.size != height.size:
        raise ValueError("terrain, raise and contributing area shapes must match")
    if (receiver.shape != (height.size,) or order.shape != receiver.shape
            or receiver.dtype.kind not in "iu" or order.dtype.kind not in "iu"):
        raise ValueError("integer receiver and topological_order [N] required")
    if runoff.shape not in ((12, *height.shape), (12, height.size)):
        raise ValueError("12 months of local runoff volumes required")
    if not _m4_lowland_runoff_np.isfinite(spacing) or spacing <= 0.:
        raise ValueError("positive finite spacing_m required")
    for values in (height, raises, area, runoff):
        if not _m4_lowland_runoff_np.isfinite(values).all():
            raise ValueError("finite terrain and runoff required")
    if _m4_lowland_runoff_np.any(raises < 0.) or _m4_lowland_runoff_np.any(area < spacing ** 2) or _m4_lowland_runoff_np.any(runoff < 0.):
        raise ValueError("nonnegative raise/runoff and physical cell areas required")
    if not _m4_lowland_runoff_np.isfinite(runoff.sum(dtype=_m4_lowland_runoff_np.float64)):
        raise ValueError("finite aggregate runoff volume required")
    if (_m4_lowland_runoff_np.any(receiver < -1) or _m4_lowland_runoff_np.any(receiver >= height.size)
            or not _m4_lowland_runoff_np.array_equal(_m4_lowland_runoff_np.sort(order), _m4_lowland_runoff_np.arange(height.size))):
        raise ValueError("receiver range or topological permutation invalid")
    rank = _m4_lowland_runoff_np.empty(height.size, _m4_lowland_runoff_np.int64)
    rank[order] = _m4_lowland_runoff_np.arange(height.size)
    sources = _m4_lowland_runoff_np.flatnonzero(receiver >= 0)
    targets = receiver[sources]
    if _m4_lowland_runoff_np.any(rank[sources] >= rank[targets]):
        raise ValueError("topological_order must be upstream to downstream")
    rows, cols = height.shape
    if (_m4_lowland_runoff_np.any(_m4_lowland_runoff_np.abs(sources // cols - targets // cols) > 1)
            or _m4_lowland_runoff_np.any(_m4_lowland_runoff_np.abs(sources % cols - targets % cols) > 1)):
        raise ValueError("saved routing edges must connect neighboring terrain cells")
    work = (height + raises).ravel()
    if _m4_lowland_runoff_np.any(work[targets] > work[sources] + 1e-7):
        raise ValueError("saved routing must not climb its working surface")
    values = _m4_lowland_runoff_asdict(config)
    if any(not _m4_lowland_runoff_np.isfinite(v) or v < 0. for v in values.values()):
        raise ValueError("finite nonnegative configuration required")
    if (not 1 <= config.simulation_years <= 5 or type(config.simulation_years) is not int
            or not 1 <= config.seasonal_months <= config.persistent_months <= 12
            or type(config.persistent_months) is not int or type(config.seasonal_months) is not int
            or config.channel_q_threshold_m3_s <= 0.
            or not 0. <= config.monthly_release_fraction <= 1.
            or config.shallow_lake_min_raise_m > config.shallow_lake_max_depth_m):
        raise ValueError("invalid bounded monthly/storage configuration")

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:277 ---
def lowland_geometry(height, spacing_m, config):
    """Original-surface local relief, slope and lowland mask on a regular sample."""
    window = 2 * max(1, int(_m4_lowland_runoff_np.ceil(config.relief_radius_m / spacing_m))) + 1
    relief = _m4_lowland_runoff_maximum_filter(height, size=window, mode="nearest") - _m4_lowland_runoff_minimum_filter(
        height, size=window, mode="nearest")
    gradients = []
    for axis in range(2):
        gradients.append(_m4_lowland_runoff_np.gradient(height, spacing_m, axis=axis)
                         if height.shape[axis] > 1 else _m4_lowland_runoff_np.zeros_like(height))
    slope = _m4_lowland_runoff_np.hypot(*gradients)
    lowland = (relief <= config.lowland_relief_m) & (slope <= config.lowland_slope)
    return relief, slope, lowland

# --- terrain_pipeline/surface_rivers/metric_lowland_runoff.py:291 ---
def classify_and_route(original_td_m, working_raise_m, receiver, topological_order,
                       contributing_area_m2, spacing_m, monthly_local_runoff_m3,
                       *, config=None):
    """Separate channel evidence from conserved runoff; never modify routing.

    Volumes are already runoff, not gross rain. Repeated synthetic years start
    with empty candidate storage; the last year is diagnostic, not equilibrium
    or evidence of calibrated perennial flow. Object IDs are flat cell IDs.
    """
    config = LowlandRunoffConfig() if config is None else config
    if not isinstance(config, LowlandRunoffConfig):
        raise ValueError("LowlandRunoffConfig required")
    height = _m4_lowland_runoff_np.asarray(original_td_m, _m4_lowland_runoff_np.float64)
    raises = _m4_lowland_runoff_np.asarray(working_raise_m, _m4_lowland_runoff_np.float64)
    receiver = _m4_lowland_runoff_np.asarray(receiver)
    order = _m4_lowland_runoff_np.asarray(topological_order)
    area = _m4_lowland_runoff_np.asarray(contributing_area_m2, _m4_lowland_runoff_np.float64)
    runoff = _m4_lowland_runoff_np.asarray(monthly_local_runoff_m3)
    _validate(height, raises, receiver, order, area, spacing_m, runoff, config)
    receiver = receiver.astype(_m4_lowland_runoff_np.int64, copy=False)
    order = order.astype(_m4_lowland_runoff_np.int64, copy=False)
    runoff = runoff.reshape(12, -1)
    relief, slope, lowland = lowland_geometry(height, spacing_m, config)
    perimeter = _m4_lowland_runoff_np.zeros(height.shape, bool)
    perimeter[[0, -1], :] = True
    perimeter[:, [0, -1]] = True
    concentration = area.ravel() >= _m4_lowland_runoff_np.where(lowland.ravel(),
        config.lowland_initiation_area_m2, config.upland_initiation_area_m2)
    full_mean = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.float64)
    raw_wet_count = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.uint8)
    for month in range(12):
        routed = _accumulate(runoff[month], receiver, order)
        full_mean += routed / YEAR_SECONDS
        raw_wet_count += routed >= config.channel_q_threshold_m3_s * MONTH_SECONDS[month]
    provisional_permanent = _close(concentration & (
        raw_wet_count >= config.persistent_months), receiver, order)
    provisional_seasonal = _close(concentration & (
        raw_wet_count >= config.seasonal_months), receiver, order) & ~provisional_permanent
    corridor = _channel_corridor(provisional_permanent, receiver, order,
        (height + raises).ravel(), height.shape[1], spacing_m,
        config.floodplain_max_dag_distance_m,
        config.floodplain_max_height_above_channel_m).reshape(height.shape)
    # Storage class describes terrain geometry independently of channel
    # visibility. River and storage flags can coexist at a single location.
    storage_flags = _m4_lowland_runoff_np.zeros(height.shape, _m4_lowland_runoff_np.uint8)
    floodplain = lowland & corridor
    swale = lowland & provisional_seasonal.reshape(height.shape)
    storage_flags[floodplain] = OBJECT_FLAGS["floodplain"]
    storage_flags[swale] = OBJECT_FLAGS["seasonal_swale"]
    wetland = lowland & (raises >= config.wetland_min_raise_m)
    lake = lowland & (raises >= config.shallow_lake_min_raise_m) & (
        raises <= config.shallow_lake_max_depth_m)
    storage_flags[wetland] = OBJECT_FLAGS["wetland"]
    storage_flags[lake] = OBJECT_FLAGS["shallow_lake"]
    depth = _m4_lowland_runoff_np.zeros(height.shape, _m4_lowland_runoff_np.float64)
    depth[floodplain] = config.floodplain_storage_depth_m
    depth[swale] = config.swale_storage_depth_m
    depth[wetland] = config.wetland_storage_depth_m
    depth[lake] = raises[lake]
    depth[perimeter] = 0.
    capacity = (depth * spacing_m ** 2).ravel()
    storage = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.float64)
    routed_mean = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.float64)
    wet_count = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.uint8)
    annual_et = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.float64)
    annual_local = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.float64)
    annual_out = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.float64)
    initial_last_year_storage = _m4_lowland_runoff_np.zeros(height.size, _m4_lowland_runoff_np.float64)
    ledger = []
    for step in range(config.simulation_years * 12):
        before = float(storage.sum())
        if step == (config.simulation_years - 1) * 12:
            initial_last_year_storage[:] = storage
        local = runoff[step % 12]
        routed, et_cells, et, release, overflow, unknown, unresolved = _monthly_storage(
            local, receiver, order, capacity, storage,
            config.monthly_evaporation_depth_m * spacing_m ** 2,
            config.monthly_release_fraction, perimeter.ravel())
        after = float(storage.sum())
        input_volume = float(local.sum(dtype=_m4_lowland_runoff_np.float64))
        residual = input_volume + before - after - et - unknown - unresolved
        ledger.append(dict(year=step // 12 + 1, month=step % 12 + 1,
                           interval_seconds=float(MONTH_SECONDS[step % 12]),
                           input_runoff_m3=input_volume, storage_before_m3=before,
                           storage_after_m3=after, evaporation_m3=float(et),
                           storage_release_m3=float(release), overflow_m3=float(overflow),
                           unknown_boundary_export_m3=float(unknown),
                           unresolved_terminal_export_m3=float(unresolved),
                           balance_residual_m3=float(residual)))
        if step >= (config.simulation_years - 1) * 12:
            routed_mean += routed / YEAR_SECONDS
            wet_count += routed >= config.channel_q_threshold_m3_s * MONTH_SECONDS[step % 12]
            annual_et += et_cells
            annual_local += local
            annual_out += routed
    permanent_seeds = concentration & (wet_count >= config.persistent_months)
    seasonal_seeds = concentration & (wet_count >= config.seasonal_months)
    permanent = _close(permanent_seeds, receiver, order)
    seasonal = _close(seasonal_seeds, receiver, order) & ~permanent
    flags = storage_flags.ravel().copy()
    flags[permanent | seasonal] |= OBJECT_FLAGS["river"]
    owner, received_flags = _first_object(flags, receiver, order)
    arrays = dict(receiver=receiver.copy(), topological_order=order.copy())
    grids = dict(lowland_mask=lowland, local_relief_m=relief, slope=slope,
                 permanent_channel_mask=permanent, seasonal_channel_mask=seasonal,
                 permanent_initiation_mask=permanent_seeds,
                 seasonal_initiation_mask=seasonal_seeds & ~permanent_seeds,
                 object_flags=flags, first_receiving_object_id=owner,
                 first_receiving_object_flags=received_flags,
                 storage_capacity_m3=capacity, final_storage_m3=storage,
                 mean_routed_q_m3_s=routed_mean,
                 mean_full_network_q_m3_s=full_mean,
                 wet_month_count=wet_count, full_network_wet_month_count=raw_wet_count)
    grids.update(last_year_initial_storage_m3=initial_last_year_storage,
                 last_year_local_runoff_m3=annual_local,
                 last_year_outflow_m3=annual_out, last_year_evaporation_m3=annual_et,
                 provisional_permanent_channel_mask=provisional_permanent,
                 provisional_seasonal_channel_mask=provisional_seasonal)
    arrays.update({key: value.reshape(height.shape) for key, value in grids.items()})
    metadata = dict(algorithm=LOWLAND_ALGORITHM, config=_m4_lowland_runoff_asdict(config),
        object_flag_codes=OBJECT_FLAGS.copy(), month_ledger=ledger,
        monthly_seconds=MONTH_SECONDS.tolist(), runoff_network_intact=True,
        receiver_policy="saved adjacent working-surface DAG; no routing edits",
        receiving_object_policy="first flagged cell on saved DAG, including self; co-located flags have equal priority",
        storage_policy="per-cell candidate buckets, shallow raise footprint or explicit retention depths; no excavation or verified water surface",
        channel_policy="persistent-flow/seasonal candidates from last synthetic year; downstream closure preserves upland-origin trunks",
        climate_policy="12 supplied synthetic runoff months repeated from empty storage; no annual equilibrium claim",
        rain_balance_scope="input is runoff only; rainfall partition losses must be accounted by the forcing producer",
        unresolved_terminal_policy="interior residual outflow remains unresolved, never accepted lake/ocean discharge",
        illustrative=True, calibrated=False, hydraulic_ready=False, publishable=False)
    return dict(arrays=arrays, metadata=metadata)

# --- terrain_pipeline/mountain_runoff_routing.py:17 ---
MOUNTAIN_ROUTING_ALGORITHM = "mountain-cell-anchor-reach-backward-euler-v2"

# --- terrain_pipeline/mountain_runoff_routing.py:18 ---
MOUNTAIN_ROUTING_SCHEMA = "mountain-reach-routing-npz-v1"

# --- terrain_pipeline/mountain_runoff_routing.py:19 ---
MOUNTAIN_ROUTING_MAX_CELLS = 250_000

# --- terrain_pipeline/mountain_runoff_routing.py:20 ---
MAX_HRUS = 256

# --- terrain_pipeline/mountain_runoff_routing.py:21 ---
MAX_REACHES = 2048

# --- terrain_pipeline/mountain_runoff_routing.py:22 ---
MOUNTAIN_ROUTING_MAX_STEPS = 3000

# --- terrain_pipeline/mountain_runoff_routing.py:23 ---
MOUNTAIN_ROUTING_MAX_ENTRIES = 8_000_000

# --- terrain_pipeline/mountain_runoff_routing.py:24 ---
MAX_WORK = 30_000_000

# --- terrain_pipeline/mountain_runoff_routing.py:25 ---
MOUNTAIN_ROUTING_MAX_BYTES = 768 * 1024 * 1024

# --- terrain_pipeline/mountain_runoff_routing.py:26 ---
INPUT_KEYS = ("height_m", "receiver", "flowline_mask", "outlet_mask", "cell_owner",
              "area_m2", "local_q_m3_s")

# --- terrain_pipeline/mountain_runoff_routing.py:28 ---
MAP_KEYS = ("river_reach", "cell_reach", "reach_downstream", "reach_order",
            "reach_length_m", "allocation_counts", "tau_s")

# --- terrain_pipeline/mountain_runoff_routing.py:30 ---
FLUX_KEYS = ("lateral_volume_m3", "upstream_volume_m3", "outflow_volume_m3",
             "storage_change_m3", "balance_residual_m3")

# --- terrain_pipeline/mountain_runoff_routing.py:32 ---
MOUNTAIN_ROUTING_ARRAY_KEYS = INPUT_KEYS + MAP_KEYS + FLUX_KEYS + ("storage_m3", "outlet_q_m3_s")

# --- terrain_pipeline/mountain_runoff_routing.py:33 ---
INT_KEYS = {"receiver", "cell_owner", "river_reach", "cell_reach",
            "reach_downstream", "reach_order", "allocation_counts"}

# --- terrain_pipeline/mountain_runoff_routing.py:35 ---
BOOL_KEYS = {"flowline_mask", "outlet_mask"}

# --- terrain_pipeline/mountain_runoff_routing.py:36 ---
META_KEYS = {"algorithm", "schema", "dt_s", "spacing_m", "speed_m_s",
             "minimum_length_m", "source_binding", "input_hashes", "parameter_sha256"}

# --- terrain_pipeline/mountain_runoff_routing.py:40 ---
def _positive(value, name, maximum):
    if (isinstance(value, (bool, _m4_mountain_runoff_routing_np.bool_)) or not isinstance(value, (int, float, _m4_mountain_runoff_routing_np.number))
            or not _m4_mountain_runoff_routing_math.isfinite(value) or not 0 < value <= maximum):
        raise ValueError(f"invalid {name}")

# --- terrain_pipeline/mountain_runoff_routing.py:46 ---
def preflight(steps, cells, hrus, reaches):
    """New routing-specific limits; not the obsolete 2M surface work ceiling."""
    if (not all(isinstance(value, (int, _m4_mountain_runoff_routing_np.integer)) and not isinstance(value, bool)
                for value in (steps, cells, hrus, reaches))
            or not 1 <= steps <= MOUNTAIN_ROUTING_MAX_STEPS or not 1 <= cells <= MOUNTAIN_ROUTING_MAX_CELLS
            or not 1 <= hrus <= MAX_HRUS or not 1 <= reaches <= MAX_REACHES
            or steps * reaches > MOUNTAIN_ROUTING_MAX_ENTRIES
            or steps * reaches * (hrus + 1) + cells * 8 > MAX_WORK):
        raise ValueError("routing resource budget exceeded")
    estimated_bytes = 8 * (12 * cells + steps * hrus + 8 * (steps + 1) * reaches)
    if estimated_bytes > MOUNTAIN_ROUTING_MAX_BYTES:
        raise ValueError("routing byte budget exceeded")
    return {"steps": int(steps), "cells": int(cells), "hrus": int(hrus),
            "reaches": int(reaches), "estimated_bytes": int(estimated_bytes),
            "work_units": int(steps * reaches * (hrus + 1) + cells * 8),
            "max_work_units": MAX_WORK, "max_bytes": MOUNTAIN_ROUTING_MAX_BYTES}

# --- terrain_pipeline/mountain_runoff_routing.py:64 ---
def _order(receiver):
    if (receiver.ndim != 1 or receiver.dtype != _m4_mountain_runoff_routing_np.dtype("int64")
            or (receiver < -1).any() or (receiver >= receiver.size).any()):
        raise ValueError("invalid receiver indices/type")
    donors = _m4_mountain_runoff_routing_np.bincount(receiver[receiver >= 0], minlength=receiver.size)
    queue = _m4_mountain_runoff_routing_deque(_m4_mountain_runoff_routing_np.flatnonzero(donors == 0).tolist())
    order = []
    while queue:
        current = queue.popleft()
        order.append(current)
        downstream = int(receiver[current])
        if downstream >= 0:
            donors[downstream] -= 1
            if donors[downstream] == 0:
                queue.append(downstream)
    if len(order) != receiver.size:
        raise ValueError("cyclic receiver graph")
    return _m4_mountain_runoff_routing_np.asarray(order, dtype=_m4_mountain_runoff_routing_np.int64)

# --- terrain_pipeline/mountain_runoff_routing.py:84 ---
def build_reaches(height_m, receiver, flowline_mask, outlet_mask, cell_owner,
                  area_m2, *, spacing_m, speed_m_s=1.0, minimum_length_m=30.0):
    """Vertex-disjoint maximal reaches; junction cell belongs to downstream reach."""
    _positive(spacing_m, "spacing_m", 1e5)
    _positive(speed_m_s, "speed_m_s", 100)
    _positive(minimum_length_m, "minimum_length_m", 1e6)
    height = _m4_mountain_runoff_routing_np.asarray(height_m)
    if (height.ndim != 2 or height.dtype != _m4_mountain_runoff_routing_np.dtype("float64")
            or not 1 <= height.size <= MOUNTAIN_ROUTING_MAX_CELLS or not _m4_mountain_runoff_routing_np.isfinite(height).all()):
        raise ValueError("invalid height grid")
    for array, dtype in ((receiver, "int64"), (cell_owner, "int64"),
                         (flowline_mask, "bool"), (outlet_mask, "bool")):
        if not isinstance(array, _m4_mountain_runoff_routing_np.ndarray) or array.shape != height.shape or array.dtype != _m4_mountain_runoff_routing_np.dtype(dtype):
            raise ValueError("invalid typed grid")
    if (not isinstance(area_m2, _m4_mountain_runoff_routing_np.ndarray) or area_m2.ndim != 1
            or area_m2.dtype != _m4_mountain_runoff_routing_np.dtype("float64") or not 1 <= area_m2.size <= MAX_HRUS
            or not _m4_mountain_runoff_routing_np.isfinite(area_m2).all() or (area_m2 <= 0).any()):
        raise ValueError("invalid HRU areas")
    land = height.ravel() > 0
    owner = cell_owner.ravel()
    if (not land.any() or (owner[~land] != -1).any() or (owner[land] < 0).any()
            or (owner[land] >= area_m2.size).any()):
        raise ValueError("every land cell must have exactly one HRU")
    counts = _m4_mountain_runoff_routing_np.bincount(owner[land], minlength=area_m2.size)
    if not _m4_mountain_runoff_routing_np.array_equal(counts * spacing_m ** 2, area_m2):
        raise ValueError("HRU area/count mismatch")
    flat_receiver = receiver.ravel()
    order = _order(flat_receiver)
    outlets = outlet_mask.ravel()
    if not _m4_mountain_runoff_routing_np.array_equal(flat_receiver == -1, outlets):
        raise ValueError("receiver/outlet mismatch")
    river = flowline_mask.ravel() | outlets
    river_receivers = flat_receiver[river & ~outlets]
    if not river[river_receivers].all():
        raise ValueError("legacy river not downstream closed")
    moving = _m4_mountain_runoff_routing_np.flatnonzero(flat_receiver >= 0)
    downstream = flat_receiver[moving]
    width = height.shape[1]
    if _m4_mountain_runoff_routing_np.any(moving == downstream):
        raise ValueError("receiver must identify a distinct graph node")
    river_donors = _m4_mountain_runoff_routing_np.bincount(river_receivers, minlength=height.size)
    starts = _m4_mountain_runoff_routing_np.flatnonzero(river & ((river_donors != 1) | outlets))
    if not 1 <= starts.size <= MAX_REACHES:
        raise ValueError("reach count exceeds budget")
    river_reach = _m4_mountain_runoff_routing_np.full(height.size, -1, dtype=_m4_mountain_runoff_routing_np.int64)
    lengths = _m4_mountain_runoff_routing_np.zeros(starts.size, dtype=_m4_mountain_runoff_routing_np.float64)
    ends = _m4_mountain_runoff_routing_np.empty(starts.size, dtype=_m4_mountain_runoff_routing_np.int64)
    for reach, start in enumerate(starts):
        current = int(start)
        while True:
            river_reach[current] = reach
            target = int(flat_receiver[current])
            if target >= 0:
                lengths[reach] += spacing_m * _m4_mountain_runoff_routing_math.hypot(
                    current // width - target // width, current % width - target % width)
            if target < 0 or river_donors[target] != 1 or outlets[target]:
                ends[reach] = target
                break
            current = target
    reach_downstream = _m4_mountain_runoff_routing_np.full(starts.size, -1, dtype=_m4_mountain_runoff_routing_np.int64)
    reach_downstream[ends >= 0] = river_reach[ends[ends >= 0]]
    reach_order = _order(reach_downstream)
    cell_reach = river_reach.copy()
    for current in order[::-1]:
        if cell_reach[current] < 0:
            cell_reach[current] = cell_reach[flat_receiver[current]]
    if (cell_reach[land] < 0).any():
        raise ValueError("unmapped land cell")
    allocation = _m4_mountain_runoff_routing_np.bincount(cell_reach[land] * area_m2.size + owner[land],
                             minlength=starts.size * area_m2.size).reshape(starts.size, area_m2.size)
    return {"river_reach": river_reach.reshape(height.shape),
            "cell_reach": cell_reach.reshape(height.shape),
            "reach_downstream": reach_downstream, "reach_order": reach_order,
            "reach_length_m": lengths, "allocation_counts": allocation,
            "tau_s": _m4_mountain_runoff_routing_np.maximum(lengths, minimum_length_m) / speed_m_s}

# --- terrain_pipeline/mountain_runoff_routing.py:161 ---
def route_local_discharge(inputs, *, dt_s, spacing_m, source_binding,
                          speed_m_s=1.0, minimum_length_m=30.0):
    """Route interval volumes once, never instantaneous accumulated discharge."""
    _positive(dt_s, "dt_s", 1e7)
    if set(inputs) != set(INPUT_KEYS):
        raise ValueError("invalid input keys")
    local = inputs["local_q_m3_s"]
    if (not isinstance(local, _m4_mountain_runoff_routing_np.ndarray) or local.ndim != 2 or local.dtype != _m4_mountain_runoff_routing_np.dtype("float64")
            or local.shape[1] != inputs["area_m2"].size
            or not _m4_mountain_runoff_routing_np.isfinite(local).all() or (local < 0).any() or (local > 1e9).any()):
        raise ValueError("invalid local discharge")
    steps, hrus = local.shape
    preflight(steps, inputs["height_m"].size, hrus, 1)
    mapping = build_reaches(**{key: inputs[key] for key in INPUT_KEYS if key != "local_q_m3_s"},
                            spacing_m=spacing_m, speed_m_s=speed_m_s,
                            minimum_length_m=minimum_length_m)
    reaches = mapping["tau_s"].size
    preflight(steps, inputs["height_m"].size, hrus, reaches)
    if not isinstance(source_binding, dict) or not source_binding:
        raise ValueError("explicit source binding required")
    parameters = {"dt_s": float(dt_s), "spacing_m": float(spacing_m),
                  "speed_m_s": float(speed_m_s), "minimum_length_m": float(minimum_length_m)}
    result = {key: value.copy() for key, value in inputs.items()}
    result.update(mapping)
    result["metadata"] = dict(parameters, algorithm=MOUNTAIN_ROUTING_ALGORITHM, schema=MOUNTAIN_ROUTING_SCHEMA,
        source_binding=_strict_json(_json(source_binding)),
        input_hashes={key: _hash(inputs[key]) for key in INPUT_KEYS},
        parameter_sha256=_m4_mountain_runoff_routing_hashlib.sha256(_json(parameters).encode("ascii")).hexdigest())
    fractions = mapping["allocation_counts"] * spacing_m ** 2 / inputs["area_m2"][None, :]
    result.update({key: _m4_mountain_runoff_routing_np.zeros((steps, reaches), dtype=_m4_mountain_runoff_routing_np.float64) for key in FLUX_KEYS})
    result["lateral_volume_m3"] = (local @ fractions.T) * dt_s
    result["storage_m3"] = _m4_mountain_runoff_routing_np.zeros((steps + 1, reaches), dtype=_m4_mountain_runoff_routing_np.float64)
    result["outlet_q_m3_s"] = _m4_mountain_runoff_routing_np.zeros(steps, dtype=_m4_mountain_runoff_routing_np.float64)
    for reach in mapping["reach_order"]:
        tau = mapping["tau_s"][reach]
        for step in range(steps):
            incoming = result["lateral_volume_m3"][step, reach] + result["upstream_volume_m3"][step, reach]
            before = result["storage_m3"][step, reach]
            after = (before + incoming) / (1 + dt_s / tau)
            released = dt_s / tau * after
            result["storage_m3"][step + 1, reach] = after
            result["outflow_volume_m3"][step, reach] = released
        target = mapping["reach_downstream"][reach]
        if target >= 0:
            result["upstream_volume_m3"][:, target] += result["outflow_volume_m3"][:, reach]
        else:
            result["outlet_q_m3_s"] += result["outflow_volume_m3"][:, reach] / dt_s
    result["storage_change_m3"] = _m4_mountain_runoff_routing_np.diff(result["storage_m3"], axis=0)
    result["balance_residual_m3"] = (result["lateral_volume_m3"] + result["upstream_volume_m3"]
        - result["outflow_volume_m3"] - result["storage_change_m3"])
    validate_routing_result(result)
    return result

# --- terrain_pipeline/mountain_runoff_routing.py:215 ---
def _equal(actual, expected, name):
    if not _m4_mountain_runoff_routing_np.allclose(actual, expected, rtol=2e-11, atol=1e-8):
        raise ValueError(f"saved equation mismatch: {name}")

# --- terrain_pipeline/mountain_runoff_routing.py:220 ---
def _validate_saved_map(result, meta):
    height = result["height_m"]
    shape = height.shape
    for key in ("receiver", "cell_owner", "flowline_mask", "outlet_mask", "river_reach", "cell_reach"):
        if result[key].shape != shape:
            raise ValueError("saved grid shape mismatch")
    receiver = result["receiver"].ravel()
    _order(receiver)
    outlets = result["outlet_mask"].ravel()
    if not _m4_mountain_runoff_routing_np.array_equal(receiver == -1, outlets):
        raise ValueError("saved outlet mismatch")
    river = result["flowline_mask"].ravel() | outlets
    moving = _m4_mountain_runoff_routing_np.flatnonzero(receiver >= 0)
    target = receiver[moving]
    width = shape[1]
    if _m4_mountain_runoff_routing_np.any(moving == target):
        raise ValueError("saved graph edge has identical endpoints")
    if not river[receiver[river & ~outlets]].all():
        raise ValueError("saved river not closed")
    donors = _m4_mountain_runoff_routing_np.bincount(receiver[river & ~outlets], minlength=height.size)
    starts = _m4_mountain_runoff_routing_np.flatnonzero(river & ((donors != 1) | outlets))
    reaches = result["tau_s"].size
    if starts.size != reaches:
        raise ValueError("saved reach count mismatch")
    river_reach = result["river_reach"].ravel()
    cell_reach = result["cell_reach"].ravel()
    if ((river_reach[~river] != -1).any() or (river_reach[river] < 0).any()
            or (river_reach[river] >= reaches).any()
            or not _m4_mountain_runoff_routing_np.array_equal(river_reach[starts], _m4_mountain_runoff_routing_np.arange(reaches))
            or (cell_reach < 0).any() or (cell_reach >= reaches).any()
            or not _m4_mountain_runoff_routing_np.array_equal(cell_reach[river], river_reach[river])
            or not _m4_mountain_runoff_routing_np.array_equal(cell_reach[~river], cell_reach[receiver[~river]])):
        raise ValueError("saved first-downstream mapping mismatch")
    edges = _m4_mountain_runoff_routing_np.flatnonzero(river & ~outlets)
    destinations = receiver[edges]
    boundaries = (donors[destinations] != 1) | outlets[destinations]
    if not _m4_mountain_runoff_routing_np.array_equal(river_reach[edges[~boundaries]], river_reach[destinations[~boundaries]]):
        raise ValueError("saved maximal path ownership mismatch")
    ends = _m4_mountain_runoff_routing_np.concatenate((edges[boundaries], _m4_mountain_runoff_routing_np.flatnonzero(outlets)))
    if not _m4_mountain_runoff_routing_np.array_equal(_m4_mountain_runoff_routing_np.sort(river_reach[ends]), _m4_mountain_runoff_routing_np.arange(reaches)):
        raise ValueError("saved reach endpoints mismatch")
    downstream = result["reach_downstream"]
    order = result["reach_order"]
    if (downstream.shape != (reaches,) or order.shape != (reaches,)
            or (downstream < -1).any() or (downstream >= reaches).any()
            or not _m4_mountain_runoff_routing_np.array_equal(_m4_mountain_runoff_routing_np.sort(order), _m4_mountain_runoff_routing_np.arange(reaches))):
        raise ValueError("saved reach topology shape")
    endpoint_target = receiver[ends]
    expected_targets = _m4_mountain_runoff_routing_np.full(reaches, -1, dtype=_m4_mountain_runoff_routing_np.int64)
    valid = endpoint_target >= 0
    expected_targets[river_reach[ends[valid]]] = river_reach[endpoint_target[valid]]
    if not _m4_mountain_runoff_routing_np.array_equal(downstream, expected_targets):
        raise ValueError("saved reach links mismatch")
    position = _m4_mountain_runoff_routing_np.argsort(order)
    if (position[_m4_mountain_runoff_routing_np.flatnonzero(downstream >= 0)] >= position[downstream[downstream >= 0]]).any():
        raise ValueError("saved order not topological")
    lengths = _m4_mountain_runoff_routing_np.bincount(river_reach[edges], weights=meta["spacing_m"] * _m4_mountain_runoff_routing_np.hypot(
        edges // width - destinations // width, edges % width - destinations % width), minlength=reaches)
    for key in ("reach_length_m", "tau_s"):
        if result[key].shape != (reaches,):
            raise ValueError("saved length shape")
    _equal(result["reach_length_m"], lengths, "original edge lengths")
    _equal(result["tau_s"], _m4_mountain_runoff_routing_np.maximum(lengths, meta["minimum_length_m"]) / meta["speed_m_s"], "residence time")
    owner = result["cell_owner"].ravel()
    land = height.ravel() > 0
    area = result["area_m2"]
    hrus = result["local_q_m3_s"].shape[1]
    if (area.shape != (hrus,) or (area <= 0).any() or not land.any()
            or (owner[~land] != -1).any() or (owner[land] < 0).any() or (owner[land] >= hrus).any()):
        raise ValueError("saved HRU ownership")
    counts = _m4_mountain_runoff_routing_np.bincount(cell_reach[land] * hrus + owner[land], minlength=reaches * hrus).reshape(reaches, hrus)
    if (not _m4_mountain_runoff_routing_np.array_equal(counts, result["allocation_counts"])
            or not _m4_mountain_runoff_routing_np.array_equal(counts.sum(axis=0) * meta["spacing_m"] ** 2, area)):
        raise ValueError("saved allocation count/area mismatch")

# --- terrain_pipeline/mountain_runoff_routing.py:296 ---
def validate_routing_result(result, *, trusted_inputs=None, source_binding=None):
    """Static vectorized equation replay, not prepare, runoff or time advancement."""
    if set(result) != set(MOUNTAIN_ROUTING_ARRAY_KEYS) | {"metadata"}:
        raise ValueError("invalid result keys")
    meta = result["metadata"]
    if (not isinstance(meta, dict) or set(meta) != META_KEYS or meta["algorithm"] != MOUNTAIN_ROUTING_ALGORITHM
            or meta["schema"] != MOUNTAIN_ROUTING_SCHEMA or not isinstance(meta["source_binding"], dict)
            or not meta["source_binding"] or set(meta["input_hashes"]) != set(INPUT_KEYS)):
        raise ValueError("invalid metadata")
    for key in ("dt_s", "spacing_m", "speed_m_s", "minimum_length_m"):
        _positive(meta[key], key, {"dt_s": 1e7, "spacing_m": 1e5,
                                 "speed_m_s": 100, "minimum_length_m": 1e6}[key])
    parameter_hash = _m4_mountain_runoff_routing_hashlib.sha256(_json({key: meta[key] for key in
        ("dt_s", "spacing_m", "speed_m_s", "minimum_length_m")}).encode("ascii")).hexdigest()
    if parameter_hash != meta["parameter_sha256"]:
        raise ValueError("parameter identity mismatch")
    if trusted_inputs is not None:
        if source_binding != meta["source_binding"] or set(trusted_inputs) != set(INPUT_KEYS):
            raise ValueError("trusted source binding mismatch")
        for key in INPUT_KEYS:
            if _hash(trusted_inputs[key]) != meta["input_hashes"][key]:
                raise ValueError("external input identity mismatch")
    for key in MOUNTAIN_ROUTING_ARRAY_KEYS:
        value = result[key]
        dtype = "int64" if key in INT_KEYS else "bool" if key in BOOL_KEYS else "float64"
        if (not isinstance(value, _m4_mountain_runoff_routing_np.ndarray) or value.dtype != _m4_mountain_runoff_routing_np.dtype(dtype)
                or not _m4_mountain_runoff_routing_np.isfinite(value).all()):
            raise ValueError(f"invalid typed array: {key}")
    local = result["local_q_m3_s"]
    if local.ndim != 2 or result["height_m"].ndim != 2 or result["tau_s"].ndim != 1:
        raise ValueError("invalid dimensions")
    steps, hrus = local.shape
    reaches = result["tau_s"].size
    preflight(steps, result["height_m"].size, hrus, reaches)
    for key in INPUT_KEYS:
        if _hash(result[key]) != meta["input_hashes"][key]:
            raise ValueError("input hash mismatch")
    _validate_saved_map(result, meta)
    for key in FLUX_KEYS + ("storage_m3", "outlet_q_m3_s"):
        shape = (steps + 1, reaches) if key == "storage_m3" else (steps,) if key == "outlet_q_m3_s" else (steps, reaches)
        if result[key].shape != shape:
            raise ValueError(f"invalid shape: {key}")
        if key not in ("storage_change_m3", "balance_residual_m3") and (result[key] < 0).any():
            raise ValueError(f"negative saved water: {key}")
    if (local < 0).any() or (local > 1e9).any() or hrus != result["area_m2"].size:
        raise ValueError("invalid local input")
    _equal(result["storage_m3"][0], 0.0, "initial zero storage")
    dt = meta["dt_s"]
    lateral = local @ (result["allocation_counts"] * meta["spacing_m"] ** 2 / result["area_m2"]).T * dt
    _equal(result["lateral_volume_m3"], lateral, "complete area allocation")
    upstream = _m4_mountain_runoff_routing_np.zeros((steps, reaches), dtype=_m4_mountain_runoff_routing_np.float64)
    for reach, target in enumerate(result["reach_downstream"]):
        if target >= 0:
            upstream[:, target] += result["outflow_volume_m3"][:, reach]
    _equal(result["upstream_volume_m3"], upstream, "upstream transfers")
    storage = result["storage_m3"]
    expected_after = (storage[:-1] + lateral + upstream) / (1 + dt / result["tau_s"])
    _equal(storage[1:], expected_after, "backward Euler storage")
    _equal(result["outflow_volume_m3"], storage[1:] * dt / result["tau_s"], "reservoir release")
    change = _m4_mountain_runoff_routing_np.diff(storage, axis=0)
    _equal(result["storage_change_m3"], change, "storage ledger")
    residual = lateral + upstream - result["outflow_volume_m3"] - change
    _equal(result["balance_residual_m3"], residual, "reach residual ledger")
    outlet = result["outflow_volume_m3"][:, result["reach_downstream"] < 0].sum(axis=1)
    _equal(result["outlet_q_m3_s"], outlet / dt, "outlet")
    global_residual = local.sum(axis=1) * dt - outlet - change.sum(axis=1)
    _equal(global_residual, 0.0, "global interval volume")
    _equal(residual, 0.0, "reach interval volume")
    return {"max_reach_residual_m3": float(_m4_mountain_runoff_routing_np.abs(residual).max()),
            "max_global_interval_residual_m3": float(_m4_mountain_runoff_routing_np.abs(global_residual).max()),
            "global_residual_m3": float(local.sum() * dt - outlet.sum() - storage[-1].sum())}

# --- terrain_pipeline/mountain_runoff_routing.py:369 ---
def save_routing_npz(path, result):
    """Atomic same-filesystem hard-link publication, no overwrite even in a race."""
    validate_routing_result(result)
    manifest = {"metadata": result["metadata"], "hashes": {key: _hash(result[key]) for key in MOUNTAIN_ROUTING_ARRAY_KEYS}}
    payload = _json(manifest).encode("utf-8")
    if len(payload) > 65536:
        raise ValueError("manifest exceeds budget")
    target = _m4_mountain_runoff_routing_Path(path)
    if target.exists():
        raise FileExistsError(target)
    descriptor, temporary = _m4_mountain_runoff_routing_tempfile.mkstemp(prefix=".reach-", suffix=".npz", dir=target.parent)
    try:
        with _m4_mountain_runoff_routing_os.fdopen(descriptor, "wb") as stream:
            _m4_mountain_runoff_routing_np.savez_compressed(stream, manifest=_m4_mountain_runoff_routing_np.frombuffer(payload, dtype=_m4_mountain_runoff_routing_np.uint8),
                                **{key: result[key] for key in MOUNTAIN_ROUTING_ARRAY_KEYS})
            stream.flush()
            _m4_mountain_runoff_routing_os.fsync(stream.fileno())
        _m4_mountain_runoff_routing_os.link(temporary, target)
    finally:
        _m4_mountain_runoff_routing_os.unlink(temporary)

# --- terrain_pipeline/mountain_runoff_routing.py:391 ---
def load_routing_npz(path, *, trusted_inputs, source_binding):
    """Require external trusted input; hashes alone do not authenticate a forgery."""
    names = {key + ".npy" for key in MOUNTAIN_ROUTING_ARRAY_KEYS} | {"manifest.npy"}
    with open(path, "rb") as stream:
        with _m4_mountain_runoff_routing_zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) != len(names) or {member.filename for member in members} != names:
                raise ValueError("unexpected/duplicate archive members")
            if sum(member.file_size for member in members) > MOUNTAIN_ROUTING_MAX_BYTES:
                raise ValueError("archive byte budget exceeded")
            shapes = {}
            for member in members:
                key = member.filename[:-4]
                with archive.open(member) as array_stream:
                    if _m4_mountain_runoff_routing_np.lib.format.read_magic(array_stream) != (1, 0):
                        raise ValueError("unsupported NPY version")
                    shape, fortran, dtype = _m4_mountain_runoff_routing_np.lib.format.read_array_header_1_0(array_stream, max_header_size=4096)
                    expected_dtype = "uint8" if key == "manifest" else "int64" if key in INT_KEYS else "bool" if key in BOOL_KEYS else "float64"
                    if (dtype != _m4_mountain_runoff_routing_np.dtype(expected_dtype) or fortran or len(shape) not in (1, 2)
                            or any(size < 1 or size > MOUNTAIN_ROUTING_MAX_CELLS for size in shape)
                            or _m4_mountain_runoff_routing_math.prod(shape) * dtype.itemsize + array_stream.tell() != member.file_size):
                        raise ValueError("invalid typed NPY header/size")
                    if key == "manifest" and (len(shape) != 1 or shape[0] > 65536):
                        raise ValueError("invalid manifest header")
                    shapes[key] = shape
            if len(shapes["local_q_m3_s"]) != 2 or len(shapes["tau_s"]) != 1:
                raise ValueError("invalid preflight dimensions")
            steps, hrus = shapes["local_q_m3_s"]
            reaches = shapes["tau_s"][0]
            grid = shapes["height_m"]
            if len(grid) != 2:
                raise ValueError("invalid grid header")
            preflight(steps, _m4_mountain_runoff_routing_math.prod(grid), hrus, reaches)
            grid_keys = {"height_m", "receiver", "cell_owner", "flowline_mask", "outlet_mask", "river_reach", "cell_reach"}
            for key in MOUNTAIN_ROUTING_ARRAY_KEYS:
                if key in grid_keys:
                    expected_shape = grid
                elif key == "area_m2":
                    expected_shape = (hrus,)
                elif key == "local_q_m3_s":
                    expected_shape = (steps, hrus)
                elif key == "allocation_counts":
                    expected_shape = (reaches, hrus)
                elif key in FLUX_KEYS:
                    expected_shape = (steps, reaches)
                elif key == "storage_m3":
                    expected_shape = (steps + 1, reaches)
                elif key == "outlet_q_m3_s":
                    expected_shape = (steps,)
                else:
                    expected_shape = (reaches,)
                if shapes[key] != expected_shape:
                    raise ValueError(f"inconsistent header shape: {key}")
        stream.seek(0)
        with _m4_mountain_runoff_routing_np.load(stream, allow_pickle=False) as archive:
            manifest = _strict_json(archive["manifest"].tobytes().decode("utf-8"))
            if set(manifest) != {"metadata", "hashes"} or set(manifest["hashes"]) != set(MOUNTAIN_ROUTING_ARRAY_KEYS):
                raise ValueError("invalid manifest schema")
            result = {key: archive[key] for key in MOUNTAIN_ROUTING_ARRAY_KEYS}
            result["metadata"] = manifest["metadata"]
            if any(_hash(result[key]) != manifest["hashes"][key] for key in MOUNTAIN_ROUTING_ARRAY_KEYS):
                raise ValueError("array hash mismatch")
    validate_routing_result(result, trusted_inputs=trusted_inputs, source_binding=source_binding)
    return result

# --- terrain_pipeline/hydrology_seasonal.py:20 ---
SEASONAL_ALGORITHM = "hydrology-seasonal-planning-v1"

# --- terrain_pipeline/hydrology_seasonal.py:21 ---
PERIODIC_SOLVER = "hydrology-periodic-shooting-full-trajectory-v2"

# --- terrain_pipeline/hydrology_seasonal.py:22 ---
WATER_STEP_ALGORITHM = "hydrology-conservative-real-shore-events-v2"

# --- terrain_pipeline/hydrology_seasonal.py:23 ---
SHORE_EVENT_SCHEMA = "hydrology-shore-events-domain-step-v1"

# --- terrain_pipeline/hydrology_seasonal.py:24 ---
MONTH_DAYS = _m4_hydrology_seasonal_np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])

# --- terrain_pipeline/hydrology_seasonal.py:25 ---
LAKE_NEIGHBORS = tuple((dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if dr or dc)

# --- terrain_pipeline/hydrology_seasonal.py:26 ---
SEASONAL_LEDGER_KEYS = ("land_rain_m3", "lake_rain_m3", "land_et_m3", "lake_evaporation_m3",
               "runoff_to_terminal_m3", "coastal_outflow_m3", "soil_change_m3",
               "lake_change_m3")

# --- terrain_pipeline/hydrology_seasonal.py:39 ---
@_m4_hydrology_seasonal_dataclass(frozen=True)
class SeasonalConfig:
    soil_capacity_mm: float = 120.0
    soil_drainage_days: float = 45.0
    pet_base_mm_per_day: float = 0.5
    pet_temperature_mm_per_day_c: float = 0.12
    climate_noise_scale_m: float = 60000.0
    substeps_per_day: int = 1
    max_years: int = 150
    convergence_depth_mm: float = 0.01
    convergence_lake_level_m: float = 0.001
    max_cells: int = 100000

    def __post_init__(self):
        for name, value in _m4_hydrology_seasonal_asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not _m4_hydrology_seasonal_math.isfinite(value) or value <= 0:
                raise ValueError(f"invalid seasonal parameter {name}")
        for name in ("substeps_per_day", "max_years", "max_cells"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.substeps_per_day > 24 or self.max_years > 1000:
            raise ValueError("seasonal work budget exceeded")

# --- terrain_pipeline/hydrology_seasonal.py:62 ---
def seasonal_climate(plan, config=None):
    """Monthly depths [12,z,x]; month identity repeats every simulation year."""
    from terrain_pipeline.climate_forcing import NoiseClimateParameters as _m4_hydrology_seasonal_NoiseClimateParameters
    from terrain_pipeline.climate_forcing import sample_climate as _m4_hydrology_seasonal_sample_climate
    config = config or SeasonalConfig()
    height = _m4_hydrology_seasonal_np.asarray(plan["height_m"])
    z, x = _m4_hydrology_seasonal_np.indices(height.shape)
    origin = plan["origin_xz_m"]
    x = origin[0] + x * plan["spacing_m"]
    z = origin[1] + z * plan["spacing_m"]
    sampled = _m4_hydrology_seasonal_sample_climate(plan["seed"], x, z, height,
                             parameters=_m4_hydrology_seasonal_NoiseClimateParameters(regional_scale_m=config.climate_noise_scale_m))
    temperature = sampled["monthly_temperature_c"]
    # Explicit illustrative temperature-index PET; no observed radiation/humidity.
    pet = (config.pet_base_mm_per_day + config.pet_temperature_mm_per_day_c * _m4_hydrology_seasonal_np.maximum(temperature, 0))
    return {"precipitation_mm": sampled["monthly_precipitation_mm"],
            "potential_et_mm": pet * MONTH_DAYS[:, None, None],
            "temperature_c": temperature}

# --- terrain_pipeline/hydrology_seasonal.py:80 ---
class LakeGeometry:
    """Exact piecewise linear volume from connected raster bed columns."""
    def __init__(self, height, owner, domain, cell_area):
        self.spill_m = float(domain["lake_spill_elevation_m"])
        terminal = int(domain["lake_terminal_index"])
        flat = height.ravel()
        if not _m4_hydrology_seasonal_math.isfinite(self.spill_m) or terminal < 0 or terminal >= flat.size:
            raise ValueError("invalid lake terminal or spill")
        eligible = (owner == domain["domain_id"]) & (height < self.spill_m)
        if not eligible.ravel()[terminal]:
            raise ValueError("lake terminal must lie below its spill")
        self.mask = _m4_hydrology_seasonal_np.zeros(height.shape, dtype=bool)
        stack = [terminal]
        width = height.shape[1]
        self.mask.ravel()[terminal] = True
        while stack:
            index = stack.pop()
            row, col = divmod(index, width)
            for dr, dc in LAKE_NEIGHBORS:
                rr, cc = row + dr, col + dc
                if 0 <= rr < height.shape[0] and 0 <= cc < width and eligible[rr, cc] and not self.mask[rr, cc]:
                    self.mask[rr, cc] = True
                    stack.append(rr * width + cc)
        self.beds = _m4_hydrology_seasonal_np.sort(height[self.mask])
        # This first version supports one simple depression only. Reject nested
        # low pockets separated by a saddle rather than flooding disconnected beds.
        indices = _m4_hydrology_seasonal_np.flatnonzero(self.mask)
        order = indices[_m4_hydrology_seasonal_np.argsort(flat[indices], kind="stable")]
        parent = _m4_hydrology_seasonal_np.full(flat.size, -1, dtype=_m4_hydrology_seasonal_np.int64)
        components = 0
        def root(index):
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index
        offset = 0
        while offset < len(order):
            end = offset + 1
            while end < len(order) and flat[order[end]] == flat[order[offset]]:
                end += 1
            group = order[offset:end]
            for index in group:
                parent[index] = index
                components += 1
            for index in group:
                row, col = divmod(int(index), width)
                for dr, dc in LAKE_NEIGHBORS:
                    rr, cc = row + dr, col + dc
                    if 0 <= rr < height.shape[0] and 0 <= cc < width:
                        neighbor = rr * width + cc
                        if parent[neighbor] >= 0:
                            a, b = root(index), root(neighbor)
                            if a != b:
                                parent[a] = b
                                components -= 1
            if components != 1 or parent[terminal] < 0:
                raise ValueError("nested disconnected lake pockets require unsupported multi-pool routing")
            offset = end
        self.cell_area_m2 = cell_area
        self.prefix = _m4_hydrology_seasonal_np.concatenate(([0.0], _m4_hydrology_seasonal_np.cumsum(self.beds)))
        self.break_volumes = (self.beds * _m4_hydrology_seasonal_np.arange(len(self.beds)) - self.prefix[:-1]) * cell_area
        self.capacity_m3 = self.volume(self.spill_m)

    def volume(self, level_m):
        return float(_m4_hydrology_seasonal_np.maximum(level_m - self.beds, 0).sum() * self.cell_area_m2)

    def level(self, volume_m3):
        if volume_m3 < 0 or not _m4_hydrology_seasonal_math.isfinite(volume_m3):
            raise ValueError("invalid lake storage")
        count = min(int(_m4_hydrology_seasonal_np.searchsorted(self.break_volumes, volume_m3, side="right")), len(self.beds))
        return float((volume_m3 / self.cell_area_m2 + self.prefix[count]) / count)

# --- terrain_pipeline/hydrology_seasonal.py:153 ---
def _inputs(plan, config, climate):
    height = _m4_hydrology_seasonal_np.asarray(plan["height_m"], dtype=float)
    owner = _m4_hydrology_seasonal_np.asarray(plan["owner_domain_id"])
    if height.ndim != 2 or height.size > config.max_cells or owner.shape != height.shape or not _m4_hydrology_seasonal_np.isfinite(height).all():
        raise ValueError("invalid or over-budget seasonal terrain")
    spacing = float(plan["spacing_m"])
    if not _m4_hydrology_seasonal_math.isfinite(spacing) or spacing <= 0:
        raise ValueError("invalid spacing")
    domains = plan["domains"]
    ids = [d["domain_id"] for d in domains]
    if not ids or len(set(ids)) != len(ids) or _m4_hydrology_seasonal_np.any(~_m4_hydrology_seasonal_np.isin(owner, [-2, -1] + ids)):
        raise ValueError("invalid seasonal ownership")
    area = _m4_hydrology_seasonal_np.full(height.shape, spacing**2)
    hybrid = plan.get("seasonal_hybrid")
    lakes = {}
    if hybrid is not None:
        from terrain_pipeline.runoff import hybrid_column_inputs as hybrid_column_inputs
        area, lakes = hybrid_column_inputs(plan)
    for column, domain in enumerate(domains):
        if domain["kind"] == "inland":
            if hybrid is None:
                lakes[column] = LakeGeometry(height, owner, domain, spacing**2)
        elif domain["kind"] != "coastal":
            raise ValueError("unsupported terminal type")
    climate = seasonal_climate(plan, config) if climate is None else climate
    for name in ("precipitation_mm", "potential_et_mm"):
        value = _m4_hydrology_seasonal_np.asarray(climate[name], dtype=float)
        if value.shape != (12,) + height.shape or not _m4_hydrology_seasonal_np.isfinite(value).all() or _m4_hydrology_seasonal_np.any(value < 0):
            raise ValueError(f"invalid climate {name}")
    if hybrid is not None:
        hybrid_column_inputs(plan, climate)
    return height, owner, domains, lakes, area, climate

# --- terrain_pipeline/hydrology_seasonal.py:187 ---
def _area_sum(values, mask, area):
    return float(_m4_hydrology_seasonal_np.sum(values[mask] * area[mask]))

# --- terrain_pipeline/hydrology_seasonal.py:191 ---
def _year_discrete(height, owner, domains, lakes, area, climate, config, soil, lake_volume, retain=False):
    count = len(domains)
    monthly = {key: _m4_hydrology_seasonal_np.zeros((12, count)) for key in SEASONAL_LEDGER_KEYS}
    soil_months, volume_months = [soil.copy()], [lake_volume.copy()]
    steps, inventories = [], []
    masks = [owner == domain["domain_id"] for domain in domains]
    drainage_fraction = -_m4_hydrology_seasonal_math.expm1(-1 / (config.substeps_per_day * config.soil_drainage_days))
    def inventory():
        return _m4_hydrology_seasonal_np.array([_area_sum(soil, mask, area) / 1000 + lake_volume[c] for c, mask in enumerate(masks)])
    inventories.append(inventory())
    for month, days in enumerate(MONTH_DAYS):
        for unused_step in range(int(days) * config.substeps_per_day):
            wet = _m4_hydrology_seasonal_np.zeros(height.shape, dtype=bool)
            for column, lake in lakes.items():
                if lake_volume[column] > 0:
                    wet |= lake.mask & (height < lake.level(lake_volume[column]))
            land = (owner >= 0) & ~wet
            rain = climate["precipitation_mm"][month] / (days * config.substeps_per_day)
            pet = climate["potential_et_mm"][month] / (days * config.substeps_per_day)
            before_soil = soil.copy()
            available = soil + _m4_hydrology_seasonal_np.where(land, rain, 0)
            excess = _m4_hydrology_seasonal_np.where(land, _m4_hydrology_seasonal_np.maximum(available - config.soil_capacity_mm, 0), 0)
            available -= excess
            et = _m4_hydrology_seasonal_np.where(land, _m4_hydrology_seasonal_np.minimum(available, pet), 0)
            available -= et
            drainage = _m4_hydrology_seasonal_np.where(land, available * drainage_fraction, 0)
            soil = available - drainage
            runoff = (excess + drainage) * area / 1000
            ledger = {key: _m4_hydrology_seasonal_np.zeros(count) for key in SEASONAL_LEDGER_KEYS}
            for column, mask in enumerate(masks):
                ledger["land_rain_m3"][column] = _area_sum(rain, mask & land, area) / 1000
                ledger["land_et_m3"][column] = _area_sum(et, mask, area) / 1000
                ledger["runoff_to_terminal_m3"][column] = runoff[mask].sum()
                ledger["soil_change_m3"][column] = _area_sum(soil - before_soil, mask, area) / 1000
                if column not in lakes:
                    ledger["coastal_outflow_m3"][column] = runoff[mask].sum()
                    continue
                direct = _area_sum(rain, mask & wet, area) / 1000
                supply = lake_volume[column] + runoff[mask].sum() + direct
                evaporation = min(supply, _area_sum(pet, mask & wet, area) / 1000)
                after = supply - evaporation
                lake = lakes[column]
                if after >= lake.capacity_m3:
                    raise ValueError("inland lake reaches spill: no certified in-domain downstream outlet")
                ledger["lake_rain_m3"][column] = direct
                ledger["lake_evaporation_m3"][column] = evaporation
                ledger["lake_change_m3"][column] = after - lake_volume[column]
                lake_volume[column] = after
            for key in SEASONAL_LEDGER_KEYS:
                monthly[key][month] += ledger[key]
            if retain:
                steps.append(ledger)
                inventories.append(inventory())
        if retain:
            soil_months.append(soil.copy())
            volume_months.append(lake_volume.copy())
    return soil, lake_volume, monthly, soil_months, volume_months, steps, inventories

# --- terrain_pipeline/hydrology_seasonal.py:250 ---
def _shore_segment(soil, volume, rain, pet, area, wet_fraction, dt_days, config):
    land = 1 - wet_fraction
    supplied = soil + rain * dt_days
    excess = _m4_hydrology_seasonal_np.maximum(supplied - config.soil_capacity_mm, 0)
    available = supplied - excess
    et = _m4_hydrology_seasonal_np.minimum(available, pet * dt_days)
    available -= et
    drainage = available * -_m4_hydrology_seasonal_math.expm1(-dt_days / config.soil_drainage_days)
    after_soil = soil + land * (available - drainage - soil)
    summed = lambda values: float(_m4_hydrology_seasonal_np.sum(values * area) / 1000)
    runoff = summed(land * (excess + drainage))
    direct = summed(wet_fraction * rain * dt_days)
    evaporation = min(volume + runoff + direct, summed(wet_fraction * pet * dt_days))
    after_volume = volume + runoff + direct - evaporation
    ledger = {"land_rain_m3": summed(land * rain * dt_days), "lake_rain_m3": direct,
              "land_et_m3": summed(land * et), "lake_evaporation_m3": evaporation,
              "runoff_to_terminal_m3": runoff, "coastal_outflow_m3": 0.,
              "soil_change_m3": summed(after_soil - soil), "lake_change_m3": after_volume - volume}
    return after_soil, after_volume, ledger

# --- terrain_pipeline/hydrology_seasonal.py:271 ---
def _shore_step(beds, membership, soil, volume, rain, pet, area, lake, dt_days, config):
    """Split only at real bed-volume thresholds; stationary ties mix fluxes."""
    from scipy.optimize import brentq
    if not hasattr(lake, "shore_thresholds"):
        levels = _m4_hydrology_seasonal_np.concatenate((_m4_hydrology_seasonal_np.unique(lake.beds), [lake.spill_m]))
        thresholds = _m4_hydrology_seasonal_np.array([lake.volume(float(level)) for level in levels])
        thresholds, indices = _m4_hydrology_seasonal_np.unique(thresholds, return_index=True)
        lake.shore_thresholds = thresholds, levels[indices]
    thresholds, levels = lake.shore_thresholds
    remaining = dt_days
    ledger = {key: 0. for key in SEASONAL_LEDGER_KEYS}
    events = []
    for unused in range(1024):
        level = lake.level(volume)
        wet = (membership & (beds < level)).astype(float)
        near = _m4_hydrology_seasonal_np.flatnonzero(_m4_hydrology_seasonal_np.abs(thresholds - volume) <= max(1e-7, abs(volume) * 8 * _m4_hydrology_seasonal_np.finfo(float).eps))
        if len(near):
            threshold_index = int(near[_m4_hydrology_seasonal_np.argmin(_m4_hydrology_seasonal_np.abs(thresholds[near] - volume))])
            threshold = float(thresholds[threshold_index])
            ties = membership & (beds == levels[threshold_index])
            if ties.any() and volume > 0:
                dry = wet.copy()
                dry[ties] = 0
                submerged = dry.copy()
                submerged[ties] = 1
                first = _shore_segment(soil, volume, rain, pet, area, dry, remaining, config)
                second = _shore_segment(soil, volume, rain, pet, area, submerged, remaining, config)
                low, high = first[1] - volume, second[1] - volume
                if low >= 0 and high <= 0 and low != high:
                    fraction = low / (low - high)
                    wet = dry + ties * fraction
                    after, end, account = _shore_segment(soil, volume, rain, pet, area, wet, remaining, config)
                    if abs(end - volume) > max(1e-6, abs(volume) * 16 * _m4_hydrology_seasonal_np.finfo(float).eps):
                        raise ValueError("shoreline fractional flux does not conserve threshold storage")
                    events.append({"kind": "stationary_real_shore", "level_m": float(levels[threshold_index]),
                                   "dt_days": remaining, "wet_fraction": float(fraction),
                                   "tied_area_m2": float(area[ties].sum())})
                    for key in ledger:
                        ledger[key] += account[key]
                    return after, end, ledger, events
                wet = submerged if low >= 0 and high >= 0 else dry
        after, end, account = _shore_segment(soil, volume, rain, pet, area, wet, remaining, config)
        tolerance = max(1e-7, abs(volume) * 8 * _m4_hydrology_seasonal_np.finfo(float).eps)
        if end > volume:
            crossings = thresholds[(thresholds > volume + tolerance) & (thresholds < end)]
            target = float(crossings[0]) if len(crossings) else None
        else:
            crossings = thresholds[(thresholds < volume - tolerance) & (thresholds > end)]
            target = float(crossings[-1]) if len(crossings) else None
        if target is None:
            if end >= lake.capacity_m3:
                raise ValueError("inland lake reaches spill: no certified in-domain downstream outlet")
            for key in ledger:
                ledger[key] += account[key]
            return after, end, ledger, events
        dt = brentq(lambda duration: _shore_segment(soil, volume, rain, pet, area, wet, duration, config)[1] - target,
                    0., remaining, xtol=1e-12, maxiter=64)
        if dt <= 0 or dt >= remaining:
            raise ValueError("shore crossing failed to advance physical time")
        soil, volume, account = _shore_segment(soil, volume, rain, pet, area, wet, dt, config)
        events.append({"kind": "real_bed_crossing", "level_m": float(lake.level(target)), "dt_days": dt})
        for key in ledger:
            ledger[key] += account[key]
        remaining -= dt
    raise ValueError("shoreline event work budget exceeded; remaining time not discarded",
                               {"remaining_dt_days": remaining, "event_limit": 1024})

# --- terrain_pipeline/hydrology_seasonal.py:339 ---
def _year(height, owner, domains, lakes, area, climate, config, soil, lake_volume, retain=False):
    count = len(domains)
    masks = [owner == domain["domain_id"] for domain in domains]
    monthly = {key: _m4_hydrology_seasonal_np.zeros((12, count)) for key in SEASONAL_LEDGER_KEYS}
    soils, volumes, steps = [soil.copy()], [lake_volume.copy()], []
    inventory = lambda: _m4_hydrology_seasonal_np.array([float(_m4_hydrology_seasonal_np.sum(soil[mask] * area[mask]) / 1000) + lake_volume[c]
                                 for c, mask in enumerate(masks)])
    inventories = [inventory()]
    dt = 1 / config.substeps_per_day
    for month, days in enumerate(MONTH_DAYS):
        rain = climate["precipitation_mm"][month] / days
        pet = climate["potential_et_mm"][month] / days
        for unused in range(int(days) * config.substeps_per_day):
            account = {key: _m4_hydrology_seasonal_np.zeros(count) for key in SEASONAL_LEDGER_KEYS}
            step_events = []
            for column, mask in enumerate(masks):
                if column in lakes:
                    lake = lakes[column]
                    after, end, part, witness = _shore_step(height[mask], lake.mask[mask], soil[mask],
                        lake_volume[column], rain[mask], pet[mask], area[mask], lake, dt, config)
                    soil[mask], lake_volume[column] = after, end
                    if retain:
                        step_events.extend(dict(event, domain_id=domains[column]["domain_id"]) for event in witness)
                else:
                    after, unused_volume, part = _shore_segment(soil[mask], 0., rain[mask], pet[mask],
                        area[mask], _m4_hydrology_seasonal_np.zeros(_m4_hydrology_seasonal_np.count_nonzero(mask)), dt, config)
                    soil[mask] = after
                    part["coastal_outflow_m3"] = part["runoff_to_terminal_m3"]
                    part["lake_change_m3"] = 0.
                for key in SEASONAL_LEDGER_KEYS:
                    account[key][column] = part[key]
            for key in monthly:
                monthly[key][month] += account[key]
            if retain:
                account["shore_events"] = step_events
                steps.append(account)
                inventories.append(inventory())
        if retain:
            soils.append(soil.copy())
            volumes.append(lake_volume.copy())
    return soil, lake_volume, monthly, soils, volumes, steps, inventories

# --- terrain_pipeline/hydrology_seasonal.py:382 ---
def simulate_seasonal_water_balance(plan, config=None, climate=None, *, initial_soil_mm=None, initial_lake_volume_m3=None):
    """Converge the complete annual soil/lake state or fail within max_years."""
    config = config or SeasonalConfig()
    height, owner, domains, lakes, area, climate = _inputs(plan, config, climate)
    soil = _m4_hydrology_seasonal_np.zeros(height.shape) if initial_soil_mm is None else _m4_hydrology_seasonal_np.asarray(initial_soil_mm, dtype=float).copy()
    volumes = _m4_hydrology_seasonal_np.zeros(len(domains)) if initial_lake_volume_m3 is None else _m4_hydrology_seasonal_np.asarray(initial_lake_volume_m3, dtype=float).copy()
    if soil.shape != height.shape or not _m4_hydrology_seasonal_np.isfinite(soil).all() or _m4_hydrology_seasonal_np.any(soil < 0) or _m4_hydrology_seasonal_np.any(soil > config.soil_capacity_mm):
        raise ValueError("invalid initial soil storage")
    if volumes.shape != (len(domains),) or not _m4_hydrology_seasonal_np.isfinite(volumes).all() or _m4_hydrology_seasonal_np.any(volumes < 0):
        raise ValueError("invalid initial lake storage")
    soil[owner < 0] = 0
    for column in range(len(domains)):
        if (column not in lakes and volumes[column] != 0) or (column in lakes and volumes[column] >= lakes[column].capacity_m3):
            raise ValueError("invalid terminal initial storage")
    domain_areas = _m4_hydrology_seasonal_np.array([area[owner == d["domain_id"]].sum() for d in domains])
    if _m4_hydrology_seasonal_np.any(domain_areas <= 0):
        raise ValueError("empty planning domain")
    evaluations = 0
    shooting_iterations = 0
    shooting_trials = []
    # A deep lake may need thousands of dry-start years. Solve its annual map
    # instead; soil is itself cycled at each trial boundary volume. Trial resets
    # are boundary-value evaluations, never part of the accepted water ledger.
    if lakes and initial_lake_volume_m3 is None:
        if len(lakes) != 1:
            raise ValueError("periodic shooting currently requires one inland lake")
        column, lake = next(iter(lakes.items()))
        low, high = 0.0, lake.capacity_m3
        best = None
        while evaluations < config.max_years - 3:
            if shooting_iterations and _m4_hydrology_seasonal_np.nextafter(low, _m4_hydrology_seasonal_np.inf) >= high:
                reason = "no annual lake fixed point below spill: positive drift meets overflow or discrete wet-area jump"
                raise ValueError(reason, {"status": "failed", "reason": reason,
                    "algorithm": SEASONAL_ALGORITHM, "source_plan_identity_sha256": plan.get("identity_sha256"),
                    "parameters": _m4_hydrology_seasonal_asdict(config), "annual_map_evaluations": evaluations,
                    "shooting_iterations": shooting_iterations, "lake_spill_m": lake.spill_m,
                    "lower_level_m": lake.level(low), "upper_level_m": lake.level(high),
                    "trials": shooting_trials})
            trial = low if shooting_iterations == 0 else (low + high) / 2
            trial_soil = soil.copy()
            trial_volumes = _m4_hydrology_seasonal_np.zeros(len(domains))
            trial_volumes[column] = trial
            overflow = False
            soil_stable = False
            previous_trial_soil = previous_residual = None
            for unused_cycle in range(12):
                if evaluations >= config.max_years - 3:
                    break
                before_soil = trial_soil.copy()
                evaluations += 1
                try:
                    trial_soil, end_volumes, *_ = _year(height, owner, domains, lakes, area, climate,
                                                       config, trial_soil, trial_volumes.copy())
                except ValueError:
                    overflow = True
                    break
                residual = trial_soil - before_soil
                if _m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(residual)) <= config.convergence_depth_mm:
                    soil_stable = True
                    break
                # The frozen submerged store can expose for only one day/year.
                # A bounded diagonal secant proposal avoids centuries of plain
                # soil iteration. Every proposal is verified by another year.
                if previous_residual is not None:
                    denominator = residual - previous_residual
                    usable = _m4_hydrology_seasonal_np.abs(denominator) > 1e-10
                    proposal = before_soil.copy()
                    _m4_hydrology_seasonal_np.divide(residual * (before_soil - previous_trial_soil), denominator,
                              out=proposal, where=usable)
                    proposal = before_soil - proposal
                    admissible = usable & (proposal >= 0) & (proposal <= config.soil_capacity_mm)
                    trial_soil = _m4_hydrology_seasonal_np.where(admissible, proposal, trial_soil)
                previous_trial_soil, previous_residual = before_soil, residual
            shooting_iterations += 1
            if overflow:
                shooting_trials.append({"initial_level_m": lake.level(trial), "status": "spill_failure",
                                        "annual_map_evaluations": evaluations})
                high = trial
                if trial == 0:
                    raise ValueError("dry lake reaches spill within one annual forcing cycle")
                continue
            if not soil_stable:
                reason = "shooting soil cycle did not converge within annual work budget"
                raise ValueError(reason, {"status": "failed", "reason": reason,
                    "periodic_solver_algorithm": PERIODIC_SOLVER, "parameters": _m4_hydrology_seasonal_asdict(config),
                    "source_plan_identity_sha256": plan.get("identity_sha256"),
                    "annual_map_evaluations": evaluations, "trial_level_m": lake.level(trial),
                    "soil_cycle_error_mm": float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(residual))),
                    "shooting_trials": shooting_trials})
            drift = end_volumes[column] - trial
            level_drift = abs(lake.level(end_volumes[column]) - lake.level(trial))
            shooting_trials.append({"initial_level_m": lake.level(trial), "status": "soil_cycle_verified",
                                    "annual_storage_drift_m3": float(drift), "annual_level_drift_m": lake.level(end_volumes[column]) - lake.level(trial),
                                    "soil_cycle_error_mm": float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(trial_soil - before_soil))),
                                    "annual_map_evaluations": evaluations})
            if (abs(drift) / domain_areas[column] * 1000 <= config.convergence_depth_mm
                    and level_drift <= config.convergence_lake_level_m and evaluations + 2 < config.max_years - 3):
                # Wet/dry events can amplify a small boundary drift into a
                # nonperiodic soil trajectory. Check the actual map before
                # accepting this root and spending the remaining budget.
                first = _year(height, owner, domains, lakes, area, climate,
                              config, before_soil.copy(), trial_volumes.copy(), retain=True)
                second = _year(height, owner, domains, lakes, area, climate,
                               config, first[0].copy(), first[1].copy(), retain=True)
                evaluations += 2
                trajectory_soil_error = float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(_m4_hydrology_seasonal_np.array(first[3]) - _m4_hydrology_seasonal_np.array(second[3]))))
                trajectory_level_error = max(abs(lake.level(a[column]) - lake.level(b[column]))
                                             for a, b in zip(first[4], second[4]))
                shooting_trials[-1].update(full_trajectory_soil_error_mm=trajectory_soil_error,
                    full_trajectory_level_error_m=trajectory_level_error,
                    annual_map_evaluations=evaluations)
                if (trajectory_soil_error <= config.convergence_depth_mm
                        and trajectory_level_error <= config.convergence_lake_level_m):
                    best = (before_soil, trial_volumes)
                    break
            if drift > 0:
                low = trial
            else:
                high = trial
            soil = trial_soil
        if best is None:
            reason = "annual lake shooting did not converge within max_years"
            raise ValueError(reason, {"status": "failed", "reason": reason,
                "periodic_solver_algorithm": PERIODIC_SOLVER, "annual_map_evaluations": evaluations,
                "parameters": _m4_hydrology_seasonal_asdict(config), "source_plan_identity_sha256": plan.get("identity_sha256"),
                "shooting_trials": shooting_trials, "lower_level_m": lake.level(low), "upper_level_m": lake.level(high)})
        soil, volumes = best
    annual_evaluations = evaluations
    soil_error = lake_error = level_error = None
    for year in range(1, config.max_years - evaluations - 1):
        initial_soil, initial_volumes = soil.copy(), volumes.copy()
        soil, volumes, *_ = _year(height, owner, domains, lakes, area, climate, config, soil, volumes)
        annual_evaluations += 1
        soil_error = float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(soil - initial_soil)))
        lake_error = float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(volumes - initial_volumes) / domain_areas * 1000))
        level_error = max((abs(lake.level(volumes[c]) - lake.level(initial_volumes[c]))
                           for c, lake in lakes.items()), default=0.0)
        if max(soil_error, lake_error) <= config.convergence_depth_mm and level_error <= config.convergence_lake_level_m:
            break
    else:
        reason = "annual soil and lake state did not converge within max_years"
        raise ValueError(reason, {"status": "failed", "reason": reason,
            "annual_map_evaluations": annual_evaluations,
            "annual_boundary_soil_error_mm": soil_error,
            "annual_boundary_lake_error_equivalent_mm": lake_error,
            "annual_boundary_lake_level_error_m": level_error,
            "parameters": _m4_hydrology_seasonal_asdict(config), "source_plan_identity_sha256": plan.get("identity_sha256")})
    soil, volumes, monthly, soils, lake_volumes, steps, inventories = _year(
        height, owner, domains, lakes, area, climate, config, soil, volumes, retain=True)
    annual_evaluations += 1
    previous_soils, previous_volumes = _m4_hydrology_seasonal_np.array(soils), _m4_hydrology_seasonal_np.array(lake_volumes)
    trajectory_checks = []
    # Small annual endpoint drift can still cross a fine wet/dry threshold in
    # midyear. Keep advancing actual years until the complete trajectories and
    # their endpoints agree, consuming the original annual-map work budget.
    while annual_evaluations < config.max_years:
        initial_soil, initial_volumes = soil.copy(), volumes.copy()
        soil, volumes, monthly, soils, lake_volumes, steps, inventories = _year(
            height, owner, domains, lakes, area, climate, config, soil, volumes, retain=True)
        annual_evaluations += 1
        period_soil_error = float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(_m4_hydrology_seasonal_np.array(soils) - previous_soils)))
        period_level_error = max((max(abs(lake.level(a[c]) - lake.level(b[c]))
                                     for a, b in zip(lake_volumes, previous_volumes))
                                  for c, lake in lakes.items()), default=0.0)
        soil_error = float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(soil - initial_soil)))
        lake_error = float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(volumes - initial_volumes) / domain_areas * 1000))
        level_error = max((abs(lake.level(volumes[c]) - lake.level(initial_volumes[c]))
                           for c, lake in lakes.items()), default=0.0)
        trajectory_checks.append({"annual_map_evaluations": annual_evaluations,
            "successive_year_soil_max_error_mm": period_soil_error,
            "successive_year_level_max_error_m": period_level_error,
            "annual_boundary_soil_error_mm": soil_error,
            "annual_boundary_lake_error_equivalent_mm": lake_error,
            "annual_boundary_lake_level_error_m": level_error})
        if (max(period_soil_error, soil_error, lake_error) <= config.convergence_depth_mm
                and max(period_level_error, level_error) <= config.convergence_lake_level_m):
            break
        previous_soils, previous_volumes = _m4_hydrology_seasonal_np.array(soils), _m4_hydrology_seasonal_np.array(lake_volumes)
    else:
        reason = "successive annual seasonal trajectories did not converge within max_years"
        raise ValueError(reason, {"status": "failed", "reason": reason,
            "algorithm": plan.get("seasonal_hybrid", {}).get("algorithm", SEASONAL_ALGORITHM),
            "source_plan_identity_sha256": plan.get("identity_sha256"), "parameters": _m4_hydrology_seasonal_asdict(config),
            **(trajectory_checks[-1] if trajectory_checks else {"annual_map_evaluations": annual_evaluations}),
            "trajectory_checks": trajectory_checks, "shooting_iterations": shooting_iterations,
            "shooting_trials": shooting_trials})
    levels = _m4_hydrology_seasonal_np.full((13, len(domains)), _m4_hydrology_seasonal_np.nan)
    for column, lake in lakes.items():
        levels[:, column] = [lake.level(v[column]) for v in lake_volumes]
    result = {"metadata": {"algorithm": plan.get("seasonal_hybrid", {}).get("algorithm", SEASONAL_ALGORITHM),
                           "periodic_solver_algorithm": PERIODIC_SOLVER,
                           "water_step_algorithm": WATER_STEP_ALGORITHM,
                           "shore_event_schema": SHORE_EVENT_SCHEMA,
                           "status": "converged", "parameters": _m4_hydrology_seasonal_asdict(config),
                           "spinup_years": year, "annual_map_evaluations": annual_evaluations,
                           "trajectory_verification_years": annual_evaluations - evaluations - year,
                           "trajectory_checks": trajectory_checks,
                           "shooting_iterations": shooting_iterations,
                           "shooting_trials": shooting_trials,
                           "shooting_bracket": "lower positive storage drift; upper negative drift or spill failure; spill alone is not a root",
                           "domain_ids": [d["domain_id"] for d in domains],
                           "model": "capacity soil bucket; instantaneous terminal routing; dynamic raster lake area; fixed bed; submerged soil retained and frozen; no groundwater leakage",
                           "climate_model": "metric_noise_forcing.sample_climate; temperature-index planning PET",
                           "lake_connectivity": "coarse D8 matching frozen drainage; not certified fine face connectivity",
                           "soil_cycle_error_mm": float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(soils[-1] - soils[0]))),
                           "lake_cycle_error_equivalent_mm": float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(lake_volumes[-1] - lake_volumes[0]) / domain_areas * 1000)),
                           "successive_year_soil_max_error_mm": period_soil_error,
                           "successive_year_level_max_error_m": period_level_error},
              "climate": {key: _m4_hydrology_seasonal_np.asarray(value).copy() for key, value in climate.items()},
              "monthly": monthly, "soil_mm": _m4_hydrology_seasonal_np.array(soils), "lake_volume_m3": _m4_hydrology_seasonal_np.array(lake_volumes),
              "lake_level_m": levels, "step_inventory_m3": _m4_hydrology_seasonal_np.array(inventories),
              "previous_year_soil_mm": previous_soils, "previous_year_lake_volume_m3": previous_volumes,
              "steps": {key: _m4_hydrology_seasonal_np.array([step[key] for step in steps]) for key in SEASONAL_LEDGER_KEYS},
              "shore_events": [step.get("shore_events", []) for step in steps],
              "lake_geometry": {str(domains[c]["domain_id"]): {"bed_elevations_m": lake.beds.copy(),
                                "cell_area_m2": lake.cell_area_m2, "spill_m": lake.spill_m,
                                "capacity_m3": lake.capacity_m3,
                                **({"bed_areas_m2": lake.areas.copy()} if hasattr(lake, "areas") else {})}
                                for c, lake in lakes.items()}}
    if "seasonal_hybrid" in plan:
        result["metadata"]["seasonal_hybrid"] = plan["seasonal_hybrid"]
        result["metadata"]["lake_connectivity"] = "mixed coarse basin/fine column assumption; all-stage fine face connectivity unverified"
    validate_seasonal_water_balance(plan, result)
    return result

# --- terrain_pipeline/hydrology_seasonal.py:608 ---
def validate_seasonal_water_balance(plan, result):
    """Cold arithmetic audit of saved step and monthly water inventories."""
    config = SeasonalConfig(**result["metadata"]["parameters"])
    height, owner, domains, lakes, area, climate = _inputs(plan, config, result["climate"])
    count = len(domains)
    steps = result["steps"]
    nsteps = int(MONTH_DAYS.sum()) * config.substeps_per_day
    if result["metadata"].get("algorithm") != plan.get("seasonal_hybrid", {}).get("algorithm", SEASONAL_ALGORITHM):
        raise ValueError("unknown seasonal algorithm")
    if result["metadata"].get("periodic_solver_algorithm") not in (None, PERIODIC_SOLVER):
        raise ValueError("unknown seasonal periodic solver")
    if result["metadata"].get("water_step_algorithm") not in (None, WATER_STEP_ALGORITHM):
        raise ValueError("unknown seasonal water step")
    event_schema = result["metadata"].get("shore_event_schema")
    if event_schema not in (None, SHORE_EVENT_SCHEMA):
        raise ValueError("unknown shoreline event record schema")
    if result["metadata"].get("water_step_algorithm") == WATER_STEP_ALGORITHM:
        witnesses = result.get("shore_events")
        if not isinstance(witnesses, list) or len(witnesses) != nsteps:
            raise ValueError("missing seasonal shoreline event audit")
        for step_events in witnesses:
            for event in step_events:
                if event_schema == SHORE_EVENT_SCHEMA and event.get("domain_id") not in [domains[c]["domain_id"] for c in lakes]:
                    raise ValueError("shoreline event lacks its registered inland domain")
                if event.get("kind") not in ("stationary_real_shore", "real_bed_crossing"):
                    raise ValueError("unknown shoreline event")
                if not _m4_hydrology_seasonal_np.isfinite(event["level_m"]) or not 0 < event["dt_days"] <= 1 / config.substeps_per_day:
                    raise ValueError("invalid shoreline event time or level")
                if event["kind"] == "stationary_real_shore" and (not 0 <= event["wet_fraction"] <= 1 or event["tied_area_m2"] <= 0):
                    raise ValueError("invalid stationary shoreline mixture")
    if result["metadata"].get("seasonal_hybrid") != plan.get("seasonal_hybrid"):
        raise ValueError("seasonal hybrid provenance mismatch")
    for name, shape in (("soil_mm", (13,) + height.shape), ("lake_volume_m3", (13, count)),
                        ("previous_year_soil_mm", (13,) + height.shape), ("previous_year_lake_volume_m3", (13, count)),
                        ("lake_level_m", (13, count)), ("step_inventory_m3", (nsteps + 1, count))):
        value = _m4_hydrology_seasonal_np.asarray(result[name])
        if value.shape != shape or (name != "lake_level_m" and not _m4_hydrology_seasonal_np.isfinite(value).all()):
            raise ValueError(f"invalid saved seasonal state {name}")
    for key in SEASONAL_LEDGER_KEYS:
        values = _m4_hydrology_seasonal_np.asarray(steps[key])
        if values.shape != (nsteps, count) or not _m4_hydrology_seasonal_np.isfinite(values).all():
            raise ValueError("invalid saved seasonal ledger")
        if key not in ("soil_change_m3", "lake_change_m3") and _m4_hydrology_seasonal_np.any(values < 0):
            raise ValueError("negative seasonal flux")
    rain = steps["land_rain_m3"] + steps["lake_rain_m3"]
    losses = steps["land_et_m3"] + steps["lake_evaporation_m3"] + steps["coastal_outflow_m3"]
    delta = steps["soil_change_m3"] + steps["lake_change_m3"]
    tolerance = max(1e-7, float(rain.max()) * 1e-9)
    if not _m4_hydrology_seasonal_np.allclose(rain - losses, delta, rtol=1e-9, atol=tolerance):
        raise ValueError("step seasonal water budget mismatch")
    if not _m4_hydrology_seasonal_np.allclose(steps["land_rain_m3"] - steps["land_et_m3"] - steps["runoff_to_terminal_m3"],
                       steps["soil_change_m3"], rtol=1e-9, atol=tolerance):
        raise ValueError("soil runoff ledger mismatch")
    for column in range(count):
        if column in lakes:
            expected = steps["runoff_to_terminal_m3"][:, column] + steps["lake_rain_m3"][:, column] - steps["lake_evaporation_m3"][:, column]
            if _m4_hydrology_seasonal_np.any(steps["coastal_outflow_m3"][:, column] != 0) or not _m4_hydrology_seasonal_np.allclose(expected, steps["lake_change_m3"][:, column], rtol=1e-9, atol=tolerance):
                raise ValueError("inland terminal ledger mismatch")
        elif (_m4_hydrology_seasonal_np.any(result["lake_volume_m3"][:, column] != 0) or
              any(_m4_hydrology_seasonal_np.any(steps[key][:, column] != 0) for key in ("lake_rain_m3", "lake_evaporation_m3", "lake_change_m3")) or
              not _m4_hydrology_seasonal_np.allclose(steps["coastal_outflow_m3"][:, column], steps["runoff_to_terminal_m3"][:, column], rtol=1e-9, atol=tolerance)):
            raise ValueError("coastal terminal ledger mismatch")
    if not _m4_hydrology_seasonal_np.allclose(_m4_hydrology_seasonal_np.diff(result["step_inventory_m3"], axis=0), delta, rtol=1e-9, atol=tolerance):
        raise ValueError("step inventory mismatch")
    offset = 0
    for month, days in enumerate(MONTH_DAYS):
        end = offset + int(days) * config.substeps_per_day
        for key in SEASONAL_LEDGER_KEYS:
            if not _m4_hydrology_seasonal_np.allclose(steps[key][offset:end].sum(axis=0), result["monthly"][key][month], rtol=1e-9, atol=tolerance):
                raise ValueError("monthly aggregation mismatch")
        for column, domain in enumerate(domains):
            mask = owner == domain["domain_id"]
            expected_rain = _area_sum(climate["precipitation_mm"][month], mask, area) / 1000
            if not _m4_hydrology_seasonal_np.isclose(rain[offset:end, column].sum(), expected_rain, rtol=1e-9, atol=tolerance):
                raise ValueError("rain partition mismatch: lake rain counted twice or omitted")
            soil_delta = _area_sum(result["soil_mm"][month + 1] - result["soil_mm"][month], mask, area) / 1000
            lake_delta = result["lake_volume_m3"][month + 1, column] - result["lake_volume_m3"][month, column]
            for boundary, state_index in ((offset, month), (end, month + 1)):
                inventory = (_area_sum(result["soil_mm"][state_index], mask, area) / 1000
                             + result["lake_volume_m3"][state_index, column])
                if not _m4_hydrology_seasonal_np.isclose(result["step_inventory_m3"][boundary, column], inventory, rtol=1e-9, atol=tolerance):
                    raise ValueError("step inventory does not match monthly state")
            if not _m4_hydrology_seasonal_np.isclose(soil_delta, steps["soil_change_m3"][offset:end, column].sum(), rtol=1e-9, atol=tolerance):
                raise ValueError("monthly soil inventory mismatch")
            if not _m4_hydrology_seasonal_np.isclose(lake_delta, steps["lake_change_m3"][offset:end, column].sum(), rtol=1e-9, atol=tolerance):
                raise ValueError("monthly lake inventory mismatch")
        offset = end
    soils = result["soil_mm"]
    volumes = result["lake_volume_m3"]
    if not _m4_hydrology_seasonal_np.isfinite(soils).all() or _m4_hydrology_seasonal_np.any(soils < 0) or _m4_hydrology_seasonal_np.any(soils > config.soil_capacity_mm + 1e-9):
        raise ValueError("invalid soil state")
    domain_areas = _m4_hydrology_seasonal_np.array([area[owner == d["domain_id"]].sum() for d in domains])
    if _m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(soils[-1] - soils[0])) > config.convergence_depth_mm or _m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(volumes[-1] - volumes[0]) / domain_areas * 1000) > config.convergence_depth_mm:
        raise ValueError("saved annual full state is not cyclic")
    if _m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(soils - result["previous_year_soil_mm"])) > config.convergence_depth_mm:
        raise ValueError("successive annual soil trajectories differ")
    for column, lake in lakes.items():
        saved_geometry = result["lake_geometry"][str(domains[column]["domain_id"])]
        if (not _m4_hydrology_seasonal_np.array_equal(saved_geometry["bed_elevations_m"], lake.beds)
                or saved_geometry["capacity_m3"] != lake.capacity_m3
                or saved_geometry["spill_m"] != lake.spill_m
                or saved_geometry["cell_area_m2"] != lake.cell_area_m2
                or (hasattr(lake, "areas") and not _m4_hydrology_seasonal_np.array_equal(saved_geometry.get("bed_areas_m2"), lake.areas))):
            raise ValueError("saved lake geometry differs from current source geometry")
        if not _m4_hydrology_seasonal_np.isfinite(result["lake_level_m"][:, column]).all():
            raise ValueError("nonfinite lake level")
        if abs(result["lake_level_m"][-1, column] - result["lake_level_m"][0, column]) > config.convergence_lake_level_m:
            raise ValueError("annual lake level has not converged")
        if _m4_hydrology_seasonal_np.any(volumes[:, column] < 0) or _m4_hydrology_seasonal_np.any(volumes[:, column] >= lake.capacity_m3):
            raise ValueError("lake storage crosses uncertified spill")
        for volume, level in zip(volumes[:, column], result["lake_level_m"][:, column]):
            if not _m4_hydrology_seasonal_np.isclose(lake.volume(level), volume, rtol=1e-9, atol=tolerance):
                raise ValueError("lake level/bed/volume mismatch")
        previous = result["previous_year_lake_volume_m3"][:, column]
        if _m4_hydrology_seasonal_np.any(previous < 0) or _m4_hydrology_seasonal_np.any(previous >= lake.capacity_m3):
            raise ValueError("invalid previous annual lake storage")
        if max(abs(lake.level(a) - lake.level(b)) for a, b in zip(volumes[:, column], previous)) > config.convergence_lake_level_m:
            raise ValueError("successive annual lake level trajectories differ")
    return {"status": "verified", "max_step_residual_m3": float(_m4_hydrology_seasonal_np.max(_m4_hydrology_seasonal_np.abs(rain - losses - delta)))}

# --- terrain_pipeline/hydrology_seasonal.py:729 ---
def save_seasonal_water_balance(plan, result, path):
    """Publish only a cold-audited periodic product; failure reports stay separate."""
    validate_seasonal_water_balance(plan, result)
    payload = {key: result[key] for key in ("soil_mm", "lake_volume_m3", "lake_level_m", "step_inventory_m3",
               "previous_year_soil_mm", "previous_year_lake_volume_m3")}
    metadata = dict(result["metadata"])
    if "shore_events" in result:
        metadata["shore_events"] = result["shore_events"]
    metadata["source_plan_identity_sha256"] = plan.get("identity_sha256")
    metadata["lake_geometry"] = {key: {name: value for name, value in geometry.items() if name not in ("bed_elevations_m", "bed_areas_m2")}
                                 for key, geometry in result["lake_geometry"].items()}
    payload["metadata_json"] = _m4_hydrology_seasonal_np.array(_m4_hydrology_seasonal_json.dumps(metadata, allow_nan=False))
    for group in ("climate", "monthly", "steps"):
        for key, value in result[group].items():
            payload[group + "__" + key] = value
    for key, geometry in result["lake_geometry"].items():
        payload["lake_beds__" + key] = geometry["bed_elevations_m"]
        if "bed_areas_m2" in geometry:
            payload["lake_areas__" + key] = geometry["bed_areas_m2"]
    path = _m4_hydrology_seasonal_Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("seasonal products are immutable; use a new output path")
    descriptor, temporary = _m4_hydrology_seasonal_tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with _m4_hydrology_seasonal_os.fdopen(descriptor, "wb") as stream:
            _m4_hydrology_seasonal_np.savez_compressed(stream, **payload)
            stream.flush()
            _m4_hydrology_seasonal_os.fsync(stream.fileno())
        # Hard-link publication is atomic and refuses a concurrent existing path.
        _m4_hydrology_seasonal_os.link(temporary, path)
    finally:
        _m4_hydrology_seasonal_Path(temporary).unlink(missing_ok=True)

# --- terrain_pipeline/hydrology_seasonal.py:764 ---
def load_seasonal_water_balance(plan, path):
    """Read saved accounts; new event physics also replays the pinned final year."""
    with _m4_hydrology_seasonal_np.load(path, allow_pickle=False) as archive:
        metadata = _m4_hydrology_seasonal_json.loads(str(archive["metadata_json"]))
        if metadata.pop("source_plan_identity_sha256", None) != plan.get("identity_sha256"):
            raise ValueError("seasonal parent plan identity mismatch")
        geometry = metadata.pop("lake_geometry")
        result = {"metadata": metadata, "lake_geometry": geometry, "climate": {}, "monthly": {}, "steps": {}}
        if "shore_events" in metadata:
            result["shore_events"] = metadata.pop("shore_events")
        for key in archive.files:
            if key == "metadata_json":
                continue
            if "__" not in key:
                result[key] = archive[key].copy()
                continue
            group, name = key.split("__", 1)
            if group == "lake_beds":
                result["lake_geometry"][name]["bed_elevations_m"] = archive[key].copy()
            elif group == "lake_areas":
                result["lake_geometry"][name]["bed_areas_m2"] = archive[key].copy()
            elif group in ("climate", "monthly", "steps"):
                result[group][name] = archive[key].copy()
            else:
                raise ValueError("unknown seasonal archive array")
    validate_seasonal_water_balance(plan, result)
    if result["metadata"].get("water_step_algorithm") == WATER_STEP_ALGORITHM:
        config = SeasonalConfig(**result["metadata"]["parameters"])
        inputs = _inputs(plan, config, result["climate"])
        replay = _year(*inputs[:5], inputs[5], config, result["soil_mm"][0].copy(),
                       result["lake_volume_m3"][0].copy(), retain=True)
        for name, actual in (("soil_mm", replay[3]), ("lake_volume_m3", replay[4]),
                             ("step_inventory_m3", replay[6])):
            if not _m4_hydrology_seasonal_np.allclose(result[name], actual, rtol=0, atol=1e-7):
                raise ValueError("saved shoreline physics differs from replay: " + name)
        for key in SEASONAL_LEDGER_KEYS:
            actual = _m4_hydrology_seasonal_np.array([step[key] for step in replay[5]])
            if not _m4_hydrology_seasonal_np.allclose(result["steps"][key], actual, rtol=0, atol=1e-7):
                raise ValueError("saved shoreline flux differs from replay: " + key)
        replay_events = [step.get("shore_events", []) for step in replay[5]]
        if result["metadata"].get("shore_event_schema") is None:
            if len(inputs[3]) > 1:
                raise ValueError("legacy multi-lake shoreline events cannot verify per-step attribution")
            replay_events = [[{key: value for key, value in event.items() if key != "domain_id"}
                              for event in step] for step in replay_events]
        if result["shore_events"] != replay_events:
            raise ValueError("saved shoreline events differ from physical replay")
    return result

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:20 ---
HYBRID_SEASONAL_ALGORITHM = "hydrology-seasonal-hybrid-lake-v1"

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:21 ---
COLUMN_ARRAYS = ("height_m", "owner_domain_id", "seasonal_column_area_m2",
                 "seasonal_parent_cell_id", "seasonal_lake_domain_id")

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:25 ---
def _digest(record):
    return _m4_hydrology_seasonal_hybrid_hashlib.sha256(_m4_hydrology_seasonal_hybrid_json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:29 ---
def _array_hash(array):
    array = _m4_hydrology_seasonal_hybrid_np.ascontiguousarray(array)
    return _digest({"shape": list(array.shape), "dtype": array.dtype.str,
                    "bytes_sha256": _m4_hydrology_seasonal_hybrid_hashlib.sha256(array.tobytes()).hexdigest()})

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:35 ---
class WeightedLakeGeometry:
    """Exact weighted column hypsometry, with zero-storage level at lowest bed."""

    def __init__(self, height, area, mask, spill_m):
        height, area, mask = _m4_hydrology_seasonal_hybrid_np.asarray(height), _m4_hydrology_seasonal_hybrid_np.asarray(area), _m4_hydrology_seasonal_hybrid_np.asarray(mask)
        if (height.shape != area.shape or height.shape != mask.shape or mask.dtype != bool
                or not mask.any() or not _m4_hydrology_seasonal_hybrid_np.isfinite(height).all() or not _m4_hydrology_seasonal_hybrid_np.isfinite(area).all()
                or _m4_hydrology_seasonal_hybrid_np.any(area <= 0) or not _m4_hydrology_seasonal_hybrid_np.isfinite(spill_m) or _m4_hydrology_seasonal_hybrid_np.any(height[mask] >= spill_m)):
            raise ValueError("finite positive weighted lake columns below spill required")
        order = _m4_hydrology_seasonal_hybrid_np.argsort(height[mask], kind="stable")
        self.beds = height[mask][order].astype(float)
        self.areas = area[mask][order].astype(float)
        self.mask = mask.copy()
        self.spill_m = float(spill_m)
        self.cell_area_m2 = None
        self.prefix_area = _m4_hydrology_seasonal_hybrid_np.concatenate(([0.], _m4_hydrology_seasonal_hybrid_np.cumsum(self.areas)))
        self.prefix_bed_volume = _m4_hydrology_seasonal_hybrid_np.concatenate(([0.], _m4_hydrology_seasonal_hybrid_np.cumsum(self.beds * self.areas)))
        self.break_volumes = self.beds * self.prefix_area[:-1] - self.prefix_bed_volume[:-1]
        self.capacity_m3 = self.volume(self.spill_m)

    def volume(self, level_m):
        if not _m4_hydrology_seasonal_hybrid_np.isfinite(level_m):
            raise ValueError("finite lake level required")
        return float(_m4_hydrology_seasonal_hybrid_np.sum(_m4_hydrology_seasonal_hybrid_np.maximum(level_m - self.beds, 0) * self.areas))

    def area(self, level_m):
        if not _m4_hydrology_seasonal_hybrid_np.isfinite(level_m):
            raise ValueError("finite lake level required")
        return float(self.areas[self.beds < level_m].sum())

    def level(self, volume_m3):
        if not _m4_hydrology_seasonal_hybrid_np.isfinite(volume_m3) or volume_m3 < 0:
            raise ValueError("finite nonnegative lake storage required")
        count = min(int(_m4_hydrology_seasonal_hybrid_np.searchsorted(self.break_volumes, volume_m3, side="right")), len(self.beds))
        return float((volume_m3 + self.prefix_bed_volume[count]) / self.prefix_area[count])

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:72 ---
def load_hybrid_lake_detail(path, expected_sha256):
    """Read one pinned derived TD product; no generation or projection."""
    from terrain_pipeline.common_infra import checked_archive
    archive = checked_archive(path, expected_sha256=expected_sha256)
    return {"arrays": {key: value for key, value in archive.items() if key != "metadata_json"},
            "metadata": _m4_hydrology_seasonal_hybrid_json.loads(str(archive["metadata_json"].item()))}

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:80 ---
def _checked_detail(plan, detail, source_sha256):
    from terrain_pipeline.hydrology_detail import _digest as detail_digest
    metadata, arrays = detail["metadata"], detail["arrays"]
    if (not isinstance(source_sha256, str) or len(source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in source_sha256)):
        raise ValueError("pinned fine detail SHA256 required")
    unsigned = {key: value for key, value in metadata.items() if key != "identity"}
    expected = detail_digest({"metadata": unsigned, "arrays": {
        name: _m4_hydrology_seasonal_hybrid_hashlib.sha256(_m4_hydrology_seasonal_hybrid_np.asarray(value).tobytes()).hexdigest() for name, value in sorted(arrays.items())}})
    if metadata.get("identity") != expected or metadata.get("plan_identity") != plan.get("identity_sha256"):
        raise ValueError("fine detail content or frozen parent identity mismatch")
    generated = metadata.get("raw_provenance", {}).get("generation_metadata", {})
    if (generated.get("artifact_kind") != "terrain_diffusion_output"
            or generated.get("schema") != "hydrology-canonical-td-window-v1"
            or int(generated.get("seed", -1)) != plan["seed"]
            or not generated.get("tile_assembly") or not generated.get("identity")):
        raise ValueError("genuine pinned canonical TD provenance required")
    heights = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["derived_height_m"])
    owners = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["owner_domain_id"])
    spacing = float(metadata["spacing_m"])
    origin = _m4_hydrology_seasonal_hybrid_np.asarray(metadata["origin_xz_m"], dtype=float)
    if (heights.ndim != 2 or heights.size > 250000 or owners.shape != heights.shape
            or owners.dtype.kind not in "iu" or not _m4_hydrology_seasonal_hybrid_np.isfinite(heights).all()
            or not _m4_hydrology_seasonal_hybrid_np.isfinite(spacing) or not 0 < spacing <= plan["spacing_m"]
            or origin.shape != (2,) or not _m4_hydrology_seasonal_hybrid_np.isfinite(origin).all()):
        raise ValueError("aligned bounded fine lake raster and physical coordinates required")
    if metadata.get("schema") == "hydrology-local-connected-lake-basin-v1":
        _audit_lake_correction(detail)
    return metadata, heights, owners, spacing, origin

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:111 ---
def prepare_hybrid_lake_plan(plan, detail, *, source_sha256, domain_id, coarse_climate):
    """Replace a single nonoverlapping fine raster footprint, retaining remainder.

    Climate depths are inherited from each fragment's frozen parent coarse cell.
    Fine soil states are separate, so temporarily wet fractions never duplicate
    coarse soil/rain. Lake membership inherits the connected coarse basin and is
    explicitly an assumption until all-stage fine connectivity is supplied.
    """
    metadata, fine, fine_owner, fine_spacing, fine_origin = _checked_detail(plan, detail, source_sha256)
    domains = plan["domains"]
    matches = [d for d in domains if d["domain_id"] == domain_id and d["kind"] == "inland"]
    if len(matches) != 1 or sum(d["kind"] == "inland" for d in domains) != 1:
        raise ValueError("one explicit registered inland lake required")
    domain = matches[0]
    coarse = _m4_hydrology_seasonal_hybrid_np.asarray(plan["height_m"])
    owner = _m4_hydrology_seasonal_hybrid_np.asarray(plan["owner_domain_id"])
    spacing = float(plan["spacing_m"])
    origin = _m4_hydrology_seasonal_hybrid_np.asarray(plan["origin_xz_m"], float)
    coarse_area = spacing**2
    lake = LakeGeometry(coarse, owner, domain, coarse_area)
    if _m4_hydrology_seasonal_hybrid_np.any(fine_owner != domain_id):
        raise ValueError("fine replacement footprint must remain inside its frozen inland owner")
    for key in ("precipitation_mm", "potential_et_mm"):
        values = _m4_hydrology_seasonal_hybrid_np.asarray(coarse_climate[key])
        if values.shape != (12,) + coarse.shape or not _m4_hydrology_seasonal_hybrid_np.isfinite(values).all() or _m4_hydrology_seasonal_hybrid_np.any(values < 0):
            raise ValueError("finite parent coarse forcing required")
    # Rectangles are half-open; measure-zero shared edges never own area twice.
    fragments, replaced = [], _m4_hydrology_seasonal_hybrid_np.zeros(coarse.size)
    width = coarse.shape[1]
    for fz, fx in _m4_hydrology_seasonal_hybrid_np.ndindex(fine.shape):
        center = fine_origin + _m4_hydrology_seasonal_hybrid_np.array([fx, fz]) * fine_spacing
        lower, upper = center - fine_spacing / 2, center + fine_spacing / 2
        first = _m4_hydrology_seasonal_hybrid_np.floor((lower - origin + spacing / 2) / spacing).astype(int)
        last = _m4_hydrology_seasonal_hybrid_np.ceil((upper - origin + spacing / 2) / spacing).astype(int) - 1
        if (first < 0).any() or last[0] >= coarse.shape[1] or last[1] >= coarse.shape[0]:
            raise ValueError("fine footprint extends beyond finite coarse control volumes")
        for cz in range(first[1], last[1] + 1):
            for cx in range(first[0], last[0] + 1):
                coarse_center = origin + _m4_hydrology_seasonal_hybrid_np.array([cx, cz]) * spacing
                overlap = _m4_hydrology_seasonal_hybrid_np.minimum(upper, coarse_center + spacing / 2) - _m4_hydrology_seasonal_hybrid_np.maximum(lower, coarse_center - spacing / 2)
                area = float(_m4_hydrology_seasonal_hybrid_np.prod(_m4_hydrology_seasonal_hybrid_np.maximum(overlap, 0)))
                if area == 0:
                    continue
                if owner[cz, cx] != domain_id:
                    raise ValueError("fine fragment crosses frozen coarse owner")
                parent_id = int(cz * width + cx)
                replaced[parent_id] += area
                membership = domain_id if lake.mask[cz, cx] and fine[fz, fx] < lake.spill_m else -1
                fragments.append((float(fine[fz, fx]), area, parent_id, membership))
    if not _m4_hydrology_seasonal_hybrid_np.any(replaced[lake.mask.ravel()] > 0) or _m4_hydrology_seasonal_hybrid_np.any(replaced > coarse_area + 1e-7):
        raise ValueError("replacement must cover the connected coarse basin without duplicate area")
    remainder = _m4_hydrology_seasonal_hybrid_np.maximum(coarse_area - replaced, 0)
    retained = _m4_hydrology_seasonal_hybrid_np.flatnonzero(remainder > 1e-7)
    heights = _m4_hydrology_seasonal_hybrid_np.concatenate((coarse.ravel()[retained], [f[0] for f in fragments]))[None, :]
    areas = _m4_hydrology_seasonal_hybrid_np.concatenate((remainder[retained], [f[1] for f in fragments]))[None, :]
    parents = _m4_hydrology_seasonal_hybrid_np.concatenate((retained, [f[2] for f in fragments])).astype(_m4_hydrology_seasonal_hybrid_np.int64)[None, :]
    memberships = _m4_hydrology_seasonal_hybrid_np.concatenate((_m4_hydrology_seasonal_hybrid_np.where(lake.mask.ravel()[retained], domain_id, -1),
                                  [f[3] for f in fragments])).astype(_m4_hydrology_seasonal_hybrid_np.int32)[None, :]
    column_plan = {"height_m": heights, "owner_domain_id": owner.ravel()[parents],
                   "seasonal_column_area_m2": areas, "seasonal_parent_cell_id": parents,
                   "seasonal_lake_domain_id": memberships, "seed": plan["seed"],
                   "origin_xz_m": [0., 0.], "spacing_m": spacing, "domains": domains}
    climate = {key: _m4_hydrology_seasonal_hybrid_np.asarray(values).reshape((12, -1))[:, parents.ravel()][:, None, :]
               for key, values in coarse_climate.items()}
    source = metadata["raw_provenance"]
    record = {"algorithm": HYBRID_SEASONAL_ALGORITHM, "parent_plan_identity_sha256": plan["identity_sha256"],
              "seed": int(plan["seed"]), "parent_domains": _m4_hydrology_seasonal_hybrid_json.loads(_m4_hydrology_seasonal_hybrid_json.dumps(domains, allow_nan=False)),
              "parent_origin_xz_m": origin.tolist(), "parent_spacing_m": spacing,
              "fine_detail_identity_sha256": metadata["identity"], "fine_detail_archive_sha256": source_sha256,
              "raw_td_archive_sha256": source["archive_sha256"],
              "canonical_td_identity_sha256": source["generation_metadata"]["identity"],
              "fine_lake_support": metadata.get("fine_lake_support"),
              "fine_connected_wet_mask_sha256": (_array_hash(detail["arrays"]["connected_lake_wet_mask"])
                                                  if "connected_lake_wet_mask" in detail["arrays"] else None),
              "domain_id": domain_id, "fine_shape": list(fine.shape), "fine_origin_xz_m": fine_origin.tolist(),
              "fine_spacing_m": fine_spacing, "fine_footprint_area_m2": float(replaced.sum()),
              "coarse_cell_area_m2": coarse_area, "parent_cell_count": int(coarse.size),
              "parent_owner_sha256": _array_hash(owner.ravel()),
              "replacement_cell_ids": _m4_hydrology_seasonal_hybrid_np.flatnonzero(replaced).tolist(),
              "replacement_areas_m2": replaced[replaced > 0].tolist(),
              "coarse_basin_area_m2": float(lake.mask.sum() * coarse_area),
              "replaced_coarse_basin_area_m2": float(replaced[lake.mask.ravel()].sum()),
              "retained_coarse_basin_area_m2": float(remainder[lake.mask.ravel()].sum()),
              "fine_basin_area_below_spill_m2": float(areas[0, len(retained):][memberships[0, len(retained):] == domain_id].sum()),
              "column_count": int(heights.size), "retained_coarse_column_count": int(len(retained)),
              "fine_fragment_count": len(fragments), "area_ownership": "node-centred half-open square control-volume intersection; subtract covered coarse area exactly once",
              "forcing": "each weighted column inherits monthly depths from its frozen parent coarse cell",
              "connectivity_assumption": "fine beds below spill in replaced connected coarse lake cells share one pool; disconnected fine pockets unverified",
              "seasonal_certification_inherited": False, "fine_geometry_certified": False,
              "global_hydrology_certified": False,
              "column_array_sha256": {key: _array_hash(column_plan[key]) for key in COLUMN_ARRAYS},
              "climate_sha256": {key: _array_hash(value) for key, value in climate.items()}}
    column_plan["seasonal_hybrid"] = record
    column_plan["identity_sha256"] = _digest(record)
    hybrid_column_inputs(column_plan)
    return {"plan": column_plan, "climate": climate, "audit": record}

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:209 ---
def hybrid_column_inputs(plan, climate=None):
    """Cold-check disjoint column area, domain membership and frozen provenance."""
    record = plan["seasonal_hybrid"]
    if record.get("algorithm") != HYBRID_SEASONAL_ALGORITHM or plan.get("identity_sha256") != _digest(record):
        raise ValueError("hybrid column scientific identity mismatch")
    if record["parent_domains"] != plan["domains"] or record["seed"] != plan["seed"]:
        raise ValueError("hybrid frozen domain or seed differs")
    height, owner = _m4_hydrology_seasonal_hybrid_np.asarray(plan["height_m"]), _m4_hydrology_seasonal_hybrid_np.asarray(plan["owner_domain_id"])
    areas, parents = _m4_hydrology_seasonal_hybrid_np.asarray(plan["seasonal_column_area_m2"]), _m4_hydrology_seasonal_hybrid_np.asarray(plan["seasonal_parent_cell_id"])
    membership = _m4_hydrology_seasonal_hybrid_np.asarray(plan["seasonal_lake_domain_id"])
    if (height.ndim != 2 or any(_m4_hydrology_seasonal_hybrid_np.asarray(plan[key]).shape != height.shape for key in COLUMN_ARRAYS)
            or not _m4_hydrology_seasonal_hybrid_np.isfinite(areas).all() or _m4_hydrology_seasonal_hybrid_np.any(areas <= 0) or parents.dtype.kind not in "iu"
            or _m4_hydrology_seasonal_hybrid_np.any(parents < 0) or _m4_hydrology_seasonal_hybrid_np.any(parents >= record["parent_cell_count"])):
        raise ValueError("aligned positive hybrid area and parent columns required")
    if any(record["column_array_sha256"][key] != _array_hash(plan[key]) for key in COLUMN_ARRAYS):
        raise ValueError("hybrid column source arrays differ from frozen declaration")
    if climate is not None and {key: _array_hash(value) for key, value in climate.items()} != record["climate_sha256"]:
        raise ValueError("hybrid climate differs from frozen parent forcing")
    totals = _m4_hydrology_seasonal_hybrid_np.bincount(parents.ravel(), weights=areas.ravel(), minlength=record["parent_cell_count"])
    if not _m4_hydrology_seasonal_hybrid_np.allclose(totals, record["coarse_cell_area_m2"], rtol=1e-12, atol=1e-7):
        raise ValueError("covered coarse area duplicated or omitted")
    if _m4_hydrology_seasonal_hybrid_np.any((membership >= 0) & (membership != owner)):
        raise ValueError("hybrid lake column crosses parent ownership")
    parent_owners = _m4_hydrology_seasonal_hybrid_np.empty(record["parent_cell_count"], dtype=owner.dtype)
    parent_owners[parents.ravel()] = owner.ravel()
    if (not _m4_hydrology_seasonal_hybrid_np.array_equal(parent_owners[parents], owner)
            or _array_hash(parent_owners) != record["parent_owner_sha256"]):
        raise ValueError("hybrid columns differ from frozen parent ownership")
    lakes = {}
    for column, domain in enumerate(plan["domains"]):
        if domain["kind"] == "inland":
            lakes[column] = WeightedLakeGeometry(height, areas, membership == domain["domain_id"], domain["lake_spill_elevation_m"])
    return areas, lakes

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:244 ---
def simulate_hybrid_lake_water_balance(plan, detail, *, source_sha256, domain_id, config=None, climate=None):
    """Recompute periodic soil/lake state with new geometry and no warm-start claim."""
    from terrain_pipeline.runoff import seasonal_climate as seasonal_climate
    from terrain_pipeline.runoff import simulate_seasonal_water_balance as simulate_seasonal_water_balance
    config = config or SeasonalConfig()
    climate = seasonal_climate(plan, config) if climate is None else climate
    prepared = prepare_hybrid_lake_plan(plan, detail, source_sha256=source_sha256,
                                       domain_id=domain_id, coarse_climate=climate)
    result = simulate_seasonal_water_balance(prepared["plan"], config, prepared["climate"])
    connectivity = validate_hybrid_lake_connectivity(plan, detail, prepared, result)
    return {**prepared, "result": result, "connectivity": connectivity}

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:256 ---
def _face_component_roots(mask):
    """Return one component label per true raster cell, using physical faces."""
    labels = _m4_hydrology_seasonal_hybrid_np.full(mask.shape, -1, _m4_hydrology_seasonal_hybrid_np.int32)
    component = 0
    rows, columns = mask.shape
    for row, column in zip(*_m4_hydrology_seasonal_hybrid_np.where(mask)):
        if labels[row, column] >= 0:
            continue
        labels[row, column] = component
        stack = [(int(row), int(column))]
        while stack:
            r, c = stack.pop()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < columns and mask[rr, cc] and labels[rr, cc] < 0:
                    labels[rr, cc] = component
                    stack.append((rr, cc))
        component += 1
    return labels, component

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:277 ---
def validate_hybrid_lake_connectivity(parent_plan, detail, prepared, result):
    """Certify every actual cycle topology between critical fine bed elevations.

    This first local contract requires a rectangular fine patch strictly inside
    one coarse lake control volume. Its uncovered constant-bed ring is explicit
    known support. It must be wet at the cycle minimum and connected by coarse
    faces to the registered terminal. All fine wet components must meet that
    ring at every topology change, not merely at the maximum saved stage.
    """
    from terrain_pipeline.runoff import validate_seasonal_water_balance as validate_seasonal_water_balance
    validate_seasonal_water_balance(prepared["plan"], result)
    record = prepared["audit"]
    metadata, fine, _, spacing, origin = _checked_detail(parent_plan, detail, record["fine_detail_archive_sha256"])
    if (record != prepared["plan"]["seasonal_hybrid"]
            or metadata["identity"] != record["fine_detail_identity_sha256"]):
        raise ValueError("cycle connectivity source differs from hybrid preparation")
    _, lakes = hybrid_column_inputs(prepared["plan"], prepared["climate"])
    columns = result["metadata"]["domain_ids"]
    column = columns.index(record["domain_id"])
    volumes = result["lake_volume_m3"][0, column] + _m4_hydrology_seasonal_hybrid_np.concatenate(([0.], _m4_hydrology_seasonal_hybrid_np.cumsum(result["steps"]["lake_change_m3"][:, column])))
    levels = _m4_hydrology_seasonal_hybrid_np.array([lakes[column].level(float(v)) for v in volumes])
    minimum, maximum = float(levels.min()), float(levels.max())
    report = {"algorithm": "hybrid-local-lake-cycle-face-connectivity-v1",
              "parent_plan_identity_sha256": parent_plan["identity_sha256"],
              "hybrid_plan_identity_sha256": prepared["plan"]["identity_sha256"],
              "fine_detail_identity_sha256": metadata["identity"],
              "minimum_cycle_level_m": minimum, "maximum_cycle_level_m": maximum,
              "step_boundary_count": len(levels), "fine_geometry_certified": False,
              "global_hydrology_certified": False,
              "scope": "rectangular local fine footprint and retained coarse basin; actual converged cycle range only"}
    def reject(reason, **extra):
        return {**report, "status": "rejected", "reason": reason, **extra}
    replacements = record["replacement_cell_ids"]
    if len(replacements) != 1:
        return reject("fine footprint needs explicit retained support geometry across multiple coarse cells")
    parent_id = replacements[0]
    coarse = _m4_hydrology_seasonal_hybrid_np.asarray(parent_plan["height_m"])
    coarse_owner = _m4_hydrology_seasonal_hybrid_np.asarray(parent_plan["owner_domain_id"])
    row, col = divmod(parent_id, coarse.shape[1])
    coarse_spacing = float(parent_plan["spacing_m"])
    coarse_center = _m4_hydrology_seasonal_hybrid_np.asarray(parent_plan["origin_xz_m"]) + _m4_hydrology_seasonal_hybrid_np.array([col, row]) * coarse_spacing
    lower = origin - spacing / 2
    upper = origin + _m4_hydrology_seasonal_hybrid_np.array([fine.shape[1] - 1, fine.shape[0] - 1]) * spacing + spacing / 2
    if not _m4_hydrology_seasonal_hybrid_np.all(lower > coarse_center - coarse_spacing / 2) or not _m4_hydrology_seasonal_hybrid_np.all(upper < coarse_center + coarse_spacing / 2):
        return reject("fine footprint lacks a strictly interior connected retained coarse ring")
    report.update(retained_support_parent_cell_id=parent_id, retained_support_bed_m=float(coarse[row, col]),
                  retained_support_area_m2=coarse_spacing**2 - record["fine_footprint_area_m2"],
                  retained_support_geometry="coarse square minus strictly interior fine rectangle; connected constant-bed ring")
    if coarse[row, col] >= minimum:
        return reject("retained coarse ring is dry at actual cycle minimum; unknown external fine terrain is not lake support")
    domain = next(d for d in parent_plan["domains"] if d["domain_id"] == record["domain_id"])
    coarse_lake = LakeGeometry(coarse, coarse_owner, domain, coarse_spacing**2)
    coarse_wet = coarse_lake.mask & (coarse < minimum)
    coarse_labels, _ = _face_component_roots(coarse_wet)
    terminal_row, terminal_col = divmod(domain["lake_terminal_index"], coarse.shape[1])
    if (coarse_labels[row, col] < 0 or coarse_labels[terminal_row, terminal_col] != coarse_labels[row, col]):
        return reject("retained wet coarse support lacks a face-connected registered-terminal path at cycle minimum")
    critical = _m4_hydrology_seasonal_hybrid_np.unique(fine[(fine >= minimum) & (fine <= maximum)])
    stages = _m4_hydrology_seasonal_hybrid_np.unique(_m4_hydrology_seasonal_hybrid_np.concatenate(([minimum, maximum], critical, _m4_hydrology_seasonal_hybrid_np.nextafter(critical, _m4_hydrology_seasonal_hybrid_np.inf))))
    stages = stages[(stages >= minimum) & (stages <= maximum)]
    boundary = _m4_hydrology_seasonal_hybrid_np.zeros(fine.shape, bool)
    boundary[[0, -1], :] = True
    boundary[:, [0, -1]] = True
    maximum_components = 0
    for stage in stages:
        wet = fine < stage
        labels, count = _face_component_roots(wet)
        reached = _m4_hydrology_seasonal_hybrid_np.unique(labels[boundary & wet])
        reached = reached[reached >= 0]
        if len(reached) != count:
            disconnected = wet & ~_m4_hydrology_seasonal_hybrid_np.isin(labels, reached)
            return reject("fine wet component does not meet known wet retained coarse ring at a cycle-critical stage",
                          failing_stage_m=float(stage), disconnected_pixel_count=int(disconnected.sum()),
                          tested_stage_count=len(stages), critical_bed_count=len(critical))
        maximum_components = max(maximum_components, count)
    return {**report, "status": "verified_local_actual_cycle_connectivity",
            "fine_geometry_certified": True, "critical_bed_count": len(critical),
            "tested_stage_count": len(stages), "maximum_fine_wet_component_count": maximum_components,
            "coarse_terminal_index": domain["lake_terminal_index"],
            "proof": "wet coarse ring and face path persist above cycle minimum; fine wet masks change only at bed elevations, checked with strict< on both sides"}

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:359 ---
def fill_lake_patch_to_boundary_saddles(height):
    """Minimum D4 depression fill with every boundary bed held immutable."""
    height = _m4_hydrology_seasonal_hybrid_np.asarray(height, dtype=float)
    if height.ndim != 2 or min(height.shape) < 3 or height.size > 250000 or not _m4_hydrology_seasonal_hybrid_np.isfinite(height).all():
        raise ValueError("finite bounded lake patch with an outer ring required")
    rows, columns = height.shape
    filled = height.copy()
    visited = _m4_hydrology_seasonal_hybrid_np.zeros(height.shape, bool)
    visited[[0, -1], :] = True
    visited[:, [0, -1]] = True
    heap = [(float(height[r, c]), int(r), int(c)) for r, c in zip(*_m4_hydrology_seasonal_hybrid_np.where(visited))]
    _m4_hydrology_seasonal_hybrid_heapq.heapify(heap)
    while heap:
        level, row, column = _m4_hydrology_seasonal_hybrid_heapq.heappop(heap)
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            r, c = row + dr, column + dc
            if 0 <= r < rows and 0 <= c < columns and not visited[r, c]:
                visited[r, c] = True
                filled[r, c] = max(level, height[r, c])
                _m4_hydrology_seasonal_hybrid_heapq.heappush(heap, (float(filled[r, c]), r, c))
    return filled

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:382 ---
def _audit_lake_correction(detail):
    """Cold-recompute the fill witness and its combined frozen budget."""
    from terrain_pipeline.hydrology_detail import DetailBudget
    arrays, metadata = detail["arrays"], detail["metadata"]
    height = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["derived_height_m"])
    fill = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["lake_depression_fill_m"])
    raw, macro = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["original_td_m"]), _m4_hydrology_seasonal_hybrid_np.asarray(arrays["macro_delta_m"])
    channel, protected = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["local_channel_delta_m"]), _m4_hydrology_seasonal_hybrid_np.asarray(arrays["shared_boundary_protected"])
    if (any(a.shape != height.shape for a in (fill, raw, macro, channel, protected))
            or protected.dtype != bool or not all(_m4_hydrology_seasonal_hybrid_np.isfinite(a).all() for a in (fill, raw, macro, channel))
            or _m4_hydrology_seasonal_hybrid_np.any(fill < 0) or _m4_hydrology_seasonal_hybrid_np.any(fill[protected] != 0) or _m4_hydrology_seasonal_hybrid_np.any(fill[[0, -1], :] != 0)
            or _m4_hydrology_seasonal_hybrid_np.any(fill[:, [0, -1]] != 0)
            or not _m4_hydrology_seasonal_hybrid_np.allclose(height, raw + macro + channel, rtol=0, atol=1e-6)
            or not _m4_hydrology_seasonal_hybrid_np.allclose(height, fill_lake_patch_to_boundary_saddles(height - fill), rtol=0, atol=1e-10)):
        raise ValueError("saved lake correction is not the minimum fill with immutable protected boundary")
    budget = DetailBudget(**metadata["budget"])
    area = float(metadata["spacing_m"])**2
    total = height - raw
    ledger = {"macro_max_abs_m": float(_m4_hydrology_seasonal_hybrid_np.abs(macro).max()), "total_max_abs_m": float(_m4_hydrology_seasonal_hybrid_np.abs(total).max()),
              "macro_absolute_volume_m3": float(_m4_hydrology_seasonal_hybrid_np.abs(macro).sum() * area),
              "total_absolute_volume_m3": float(_m4_hydrology_seasonal_hybrid_np.abs(total).sum() * area),
              "channel_max_cut_m": float(max(0., -channel.min()))}
    correction = metadata["lake_correction"]
    def same_reduction(first, second):
        return bool(_m4_hydrology_seasonal_hybrid_np.isclose(first, second, rtol=8 * _m4_hydrology_seasonal_hybrid_np.finfo(float).eps, atol=0))
    recorded_ledger_matches = all(
        key in metadata["ledger"] and key in correction["combined_ledger"]
        and same_reduction(value, metadata["ledger"][key])
        and same_reduction(value, correction["combined_ledger"][key]) for key, value in ledger.items())
    if (any(value > getattr(budget, key) for key, value in ledger.items())
            or not recorded_ledger_matches
            or correction["budget"] != metadata["budget"]
            or correction["filled_pixel_count"] != int(_m4_hydrology_seasonal_hybrid_np.count_nonzero(fill))
            or correction["filled_area_m2"] != float(_m4_hydrology_seasonal_hybrid_np.count_nonzero(fill) * area)
            or correction["maximum_fill_m"] != float(fill.max())
            or not same_reduction(correction["fill_volume_m3"], float(fill.sum() * area))
            or correction["canonical_core_exact_crop"] is not False):
        raise ValueError("saved lake fill or combined budget ledger mismatch")

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:422 ---
def prepare_connected_hybrid_lake_detail(plan, detail, *, source_sha256, domain_id):
    """New bounded lake-only correction layer; parent/source/boundary unchanged.

    No canonical core crop identity is claimed. D4 priority flood raises only
    internal depressions to the minimum real patch-boundary saddle. The coarse
    ring must subsequently be wet across the freshly solved periodic range.
    """
    from terrain_pipeline.hydrology_detail import DetailBudget
    from terrain_pipeline.hydrology_detail import _digest as detail_digest
    metadata, height, owners, spacing, origin = _checked_detail(plan, detail, source_sha256)
    domains = [d for d in plan["domains"] if d["domain_id"] == domain_id and d["kind"] == "inland"]
    if len(domains) != 1 or _m4_hydrology_seasonal_hybrid_np.any(owners != domain_id):
        raise ValueError("one immutable inland owner across the local lake correction required")
    arrays = detail["arrays"]
    raw = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["original_td_m"])
    macro = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["macro_delta_m"])
    channel = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["local_channel_delta_m"])
    protected = _m4_hydrology_seasonal_hybrid_np.asarray(arrays["shared_boundary_protected"])
    if (any(a.shape != height.shape for a in (raw, macro, channel, protected)) or protected.dtype != bool
            or not all(_m4_hydrology_seasonal_hybrid_np.isfinite(a).all() for a in (raw, macro, channel))
            or not _m4_hydrology_seasonal_hybrid_np.allclose(raw + macro + channel, height, rtol=0, atol=1e-6)):
        raise ValueError("matched raw/macro/channel source arrays and shared-boundary protection required")
    coarse_spacing = float(plan["spacing_m"])
    coarse_origin = _m4_hydrology_seasonal_hybrid_np.asarray(plan["origin_xz_m"])
    lower = origin - spacing / 2
    upper = origin + _m4_hydrology_seasonal_hybrid_np.array([height.shape[1] - 1, height.shape[0] - 1]) * spacing + spacing / 2
    low_parent = _m4_hydrology_seasonal_hybrid_np.floor((lower - coarse_origin + coarse_spacing / 2) / coarse_spacing).astype(int)
    high_parent = _m4_hydrology_seasonal_hybrid_np.ceil((upper - coarse_origin + coarse_spacing / 2) / coarse_spacing).astype(int) - 1
    if (not _m4_hydrology_seasonal_hybrid_np.array_equal(low_parent, high_parent) or (low_parent < 0).any()
            or low_parent[0] >= plan["height_m"].shape[1] or low_parent[1] >= plan["height_m"].shape[0]):
        raise ValueError("local correction requires a patch strictly inside one coarse lake cell")
    coarse_center = coarse_origin + low_parent * coarse_spacing
    if not _m4_hydrology_seasonal_hybrid_np.all(lower > coarse_center - coarse_spacing / 2) or not _m4_hydrology_seasonal_hybrid_np.all(upper < coarse_center + coarse_spacing / 2):
        raise ValueError("fine patch boundary must preserve a known uncovered coarse support ring")
    lake = LakeGeometry(plan["height_m"], plan["owner_domain_id"], domains[0], coarse_spacing**2)
    if not lake.mask[low_parent[1], low_parent[0]]:
        raise ValueError("local correction lacks registered coarse lake support")
    filled = fill_lake_patch_to_boundary_saddles(height)
    delta = filled - height
    if _m4_hydrology_seasonal_hybrid_np.any(delta[protected] != 0):
        raise ValueError("minimum lake depression fill would alter a protected shared boundary")
    if not _m4_hydrology_seasonal_hybrid_np.array_equal(filled[[0, -1], :], height[[0, -1], :]) or not _m4_hydrology_seasonal_hybrid_np.array_equal(filled[:, [0, -1]], height[:, [0, -1]]):
        raise ValueError("lake correction changed immutable patch boundary")
    new_macro = macro + delta
    total = filled - raw
    budget = DetailBudget(**metadata["budget"])
    ledger = {"macro_max_abs_m": float(_m4_hydrology_seasonal_hybrid_np.abs(new_macro).max()),
              "total_max_abs_m": float(_m4_hydrology_seasonal_hybrid_np.abs(total).max()),
              "macro_absolute_volume_m3": float(_m4_hydrology_seasonal_hybrid_np.abs(new_macro).sum() * spacing**2),
              "total_absolute_volume_m3": float(_m4_hydrology_seasonal_hybrid_np.abs(total).sum() * spacing**2),
              "channel_max_cut_m": float(max(0., -channel.min()))}
    violations = [name for name, value in ledger.items() if value > getattr(budget, name)]
    if violations:
        raise ValueError("combined local lake correction exceeds frozen budget: " + ", ".join(violations))
    new_arrays = {"original_td_m": raw.copy(), "derived_height_m": filled,
                  "owner_domain_id": owners.copy(), "macro_delta_m": new_macro,
                  "local_channel_delta_m": channel.copy(), "total_delta_m": total,
                  "shared_boundary_protected": protected.copy(), "lake_depression_fill_m": delta}
    correction = {"algorithm": "local-lake-d4-minimum-boundary-saddle-fill-v1",
                  "source_detail_identity_sha256": metadata["identity"], "source_detail_archive_sha256": source_sha256,
                  "parent_coarse_cell_id": int(low_parent[1] * plan["height_m"].shape[1] + low_parent[0]),
                  "filled_pixel_count": int(_m4_hydrology_seasonal_hybrid_np.count_nonzero(delta)),
                  "filled_area_m2": float(_m4_hydrology_seasonal_hybrid_np.count_nonzero(delta) * spacing**2),
                  "maximum_fill_m": float(delta.max()), "fill_volume_m3": float(delta.sum() * spacing**2),
                  "patch_boundary_unchanged": True, "parent_coarse_plan_unchanged": True,
                  "raw_td_unchanged": True, "canonical_core_exact_crop": False,
                  "budget": metadata["budget"], "combined_ledger": ledger,
                  "scope": "new lake-only correction above frozen derived TD; no changed seasonal water-level clamp"}
    new_metadata = {"schema": "hydrology-local-connected-lake-basin-v1",
                    "algorithm": correction["algorithm"], "window_kind": "lake_shore",
                    "plan_identity": plan["identity_sha256"], "origin_xz_m": origin.tolist(), "spacing_m": spacing,
                    "budget": metadata["budget"], "raw_provenance": metadata["raw_provenance"],
                    "lake_correction": correction, "ledger": ledger,
                    "status": "budget_verified_periodic_cycle_and_connectivity_pending",
                    "fine_geometry_certified": False, "global_hydrology_certified": False}
    new_metadata["identity"] = detail_digest({"metadata": new_metadata, "arrays": {
        name: _m4_hydrology_seasonal_hybrid_hashlib.sha256(value.tobytes()).hexdigest() for name, value in sorted(new_arrays.items())}})
    return {"arrays": new_arrays, "metadata": new_metadata}

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:501 ---
def save_hybrid_lake_bundle(parent_plan, detail, bundle, output, *, source_path, source_sha256):
    """Publish a new pinned bundle, including exact fine source and column plan."""
    from terrain_pipeline.hydrology_detail import file_sha256
    from terrain_pipeline.runoff import save_seasonal_water_balance as save_seasonal_water_balance
    source_path = _m4_hydrology_seasonal_hybrid_Path(source_path)
    if file_sha256(source_path) != source_sha256:
        raise ValueError("fine source archive changed before bundle publication")
    if source_sha256 != bundle["audit"]["fine_detail_archive_sha256"]:
        raise ValueError("bundle fine source pin differs from the prepared lake")
    connectivity = validate_hybrid_lake_connectivity(parent_plan, detail, bundle, bundle["result"])
    if connectivity != bundle["connectivity"]:
        raise ValueError("bundle connectivity differs from actual periodic geometry")
    output = _m4_hydrology_seasonal_hybrid_Path(output)
    output.mkdir(parents=True, exist_ok=False)
    fine_path = output / "fine-detail.npz"
    with source_path.open("rb") as source, fine_path.open("xb") as target:
        _m4_hydrology_seasonal_hybrid_shutil.copyfileobj(source, target)
    plan = bundle["plan"]
    plan_metadata = {key: plan[key] for key in ("seed", "origin_xz_m", "spacing_m", "domains",
                                               "seasonal_hybrid", "identity_sha256")}
    payload = {key: _m4_hydrology_seasonal_hybrid_np.ascontiguousarray(plan[key]) for key in COLUMN_ARRAYS}
    payload.update({"climate__" + key: _m4_hydrology_seasonal_hybrid_np.ascontiguousarray(value) for key, value in bundle["climate"].items()})
    payload["metadata_json"] = _m4_hydrology_seasonal_hybrid_np.array(_m4_hydrology_seasonal_hybrid_json.dumps(plan_metadata, allow_nan=False))
    plan_path = output / "column-plan-climate.npz"
    with plan_path.open("xb") as stream:
        _m4_hydrology_seasonal_hybrid_np.savez_compressed(stream, **payload)
    seasonal_path = output / "seasonal.npz"
    save_seasonal_water_balance(plan, bundle["result"], seasonal_path)
    manifest = {"schema": "hydrology-hybrid-lake-seasonal-bundle-v1",
                "water_step_algorithm": bundle["result"]["metadata"].get("water_step_algorithm"),
                "periodic_solver_algorithm": bundle["result"]["metadata"].get("periodic_solver_algorithm"),
                "shore_event_schema": bundle["result"]["metadata"].get("shore_event_schema"),
                "parent_plan_identity_sha256": parent_plan["identity_sha256"],
                "hybrid_plan_identity_sha256": plan["identity_sha256"],
                "fine_source_original_path": str(source_path.resolve()),
                "fine_source_sha256": source_sha256,
                "column_plan_climate_sha256": file_sha256(plan_path),
                "seasonal_sha256": file_sha256(seasonal_path), "replacement_audit": bundle["audit"],
                "connectivity": connectivity,
                "status": ("verified_local_periodic_lake" if connectivity["fine_geometry_certified"]
                           else "periodic_accounts_converged_local_geometry_rejected"),
                "global_hydrology_certified": False}
    manifest["identity_sha256"] = _digest(manifest)
    manifest_path = output / "hybrid-bundle.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        _m4_hydrology_seasonal_hybrid_json.dump(manifest, stream, indent=2, allow_nan=False)
    with manifest_path.with_suffix(".sha256").open("x", encoding="ascii") as stream:
        stream.write(file_sha256(manifest_path))
    return manifest

# --- terrain_pipeline/hydrology_seasonal_hybrid.py:552 ---
def load_hybrid_lake_bundle(parent_plan, output):
    """Rebuild replacement geometry from pinned source and cold-audit the cycle."""
    from terrain_pipeline.hydrology_detail import file_sha256
    from terrain_pipeline.runoff import load_seasonal_water_balance as load_seasonal_water_balance
    from terrain_pipeline.common_infra import checked_archive
    output = _m4_hydrology_seasonal_hybrid_Path(output)
    manifest_path = output / "hybrid-bundle.json"
    if file_sha256(manifest_path) != manifest_path.with_suffix(".sha256").read_text(encoding="ascii").strip():
        raise ValueError("hybrid bundle manifest pin mismatch")
    manifest = _m4_hydrology_seasonal_hybrid_json.loads(manifest_path.read_text(encoding="utf-8"))
    unsigned = {key: value for key, value in manifest.items() if key != "identity_sha256"}
    if (manifest.get("schema") != "hydrology-hybrid-lake-seasonal-bundle-v1"
            or manifest["identity_sha256"] != _digest(unsigned)
            or manifest["parent_plan_identity_sha256"] != parent_plan["identity_sha256"]):
        raise ValueError("hybrid bundle schema, identity or parent mismatch")
    archive = checked_archive(output / "column-plan-climate.npz", expected_sha256=manifest["column_plan_climate_sha256"])
    plan = _m4_hydrology_seasonal_hybrid_json.loads(str(archive["metadata_json"].item()))
    plan.update({key: archive[key] for key in COLUMN_ARRAYS})
    climate = {key.split("__", 1)[1]: value for key, value in archive.items() if key.startswith("climate__")}
    hybrid_column_inputs(plan, climate)
    detail = load_hybrid_lake_detail(output / "fine-detail.npz", manifest["fine_source_sha256"])
    parents = plan["seasonal_parent_cell_id"].ravel()
    coarse_climate = {}
    for name, values in climate.items():
        coarse_values = _m4_hydrology_seasonal_hybrid_np.empty((12, parent_plan["height_m"].size), dtype=values.dtype)
        coarse_values[:, parents] = values[:, 0, :]
        if not _m4_hydrology_seasonal_hybrid_np.array_equal(coarse_values[:, parents], values[:, 0, :]):
            raise ValueError("saved hybrid forcing does not inherit one parent climate per cell")
        coarse_climate[name] = coarse_values.reshape((12,) + parent_plan["height_m"].shape)
    prepared = prepare_hybrid_lake_plan(parent_plan, detail, source_sha256=manifest["fine_source_sha256"],
        domain_id=manifest["replacement_audit"]["domain_id"], coarse_climate=coarse_climate)
    if (prepared["audit"] != manifest["replacement_audit"] or prepared["audit"] != plan["seasonal_hybrid"]
            or prepared["plan"]["identity_sha256"] != manifest["hybrid_plan_identity_sha256"]):
        raise ValueError("saved hybrid replacement differs from the real fine source and parent geometry")
    seasonal_path = output / "seasonal.npz"
    if file_sha256(seasonal_path) != manifest["seasonal_sha256"]:
        raise ValueError("saved hybrid seasonal archive pin mismatch")
    result = load_seasonal_water_balance(prepared["plan"], seasonal_path)
    for name in ("water_step_algorithm", "periodic_solver_algorithm", "shore_event_schema"):
        if name in manifest and manifest[name] != result["metadata"].get(name):
            raise ValueError("hybrid manifest seasonal algorithm differs: " + name)
    connectivity = validate_hybrid_lake_connectivity(parent_plan, detail, prepared, result)
    if connectivity != manifest["connectivity"]:
        raise ValueError("saved hybrid cycle connectivity report differs from cold geometry")
    return {**prepared, "result": result, "connectivity": connectivity, "manifest": manifest, "detail": detail}

# --- terrain_pipeline/hydrology_seasonal_validation.py:18 ---
def _write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(_m4_hydrology_seasonal_validation_json.dumps(report, indent=2, allow_nan=False))

# --- terrain_pipeline/hydrology_seasonal_validation.py:24 ---
def failure_evidence(plan, error, config, output):
    """Store one genuine nonperiodic year and cold-read every step water account."""
    report = dict(error.diagnostics)
    report["pet_calibration"] = "illustrative temperature-index PET; not calibrated or observed"
    lower = report.get("lower_level_m")
    if lower is None:
        _write_report(output.with_suffix(".json"), report)
        return report
    height, owner, domains, lakes, area, climate = _inputs(plan, config, None)
    column, lake = next(iter(lakes.items()))
    volumes = _m4_hydrology_seasonal_validation_np.zeros(len(domains))
    diagnostic_level = max(float(lake.beds[0]), lower - 10.0)
    volumes[column] = lake.volume(diagnostic_level)
    report["diagnostic_initial_lake_level_m"] = diagnostic_level
    soil = _m4_hydrology_seasonal_validation_np.zeros(height.shape)
    previous_x = previous_residual = None
    used = 0
    for unused in range(min(12, config.max_years - report["annual_map_evaluations"] - 1)):
        before = soil.copy()
        soil, _, *_ = _year(height, owner, domains, lakes, area, climate, config, soil, volumes.copy())
        used += 1
        residual = soil - before
        if _m4_hydrology_seasonal_validation_np.max(_m4_hydrology_seasonal_validation_np.abs(residual)) <= config.convergence_depth_mm:
            break
        if previous_residual is not None:
            denominator = residual - previous_residual
            usable = _m4_hydrology_seasonal_validation_np.abs(denominator) > 1e-10
            proposal = _m4_hydrology_seasonal_validation_np.zeros_like(soil)
            _m4_hydrology_seasonal_validation_np.divide(residual * (before - previous_x), denominator, out=proposal, where=usable)
            proposal = before - proposal
            good = usable & (proposal >= 0) & (proposal <= config.soil_capacity_mm)
            soil = _m4_hydrology_seasonal_validation_np.where(good, proposal, soil)
        previous_x, previous_residual = before, residual
    soil, end, monthly, soil_months, lake_months, steps, inventories = _year(
        height, owner, domains, lakes, area, climate, config, soil, volumes.copy(), retain=True)
    arrays = {key: _m4_hydrology_seasonal_validation_np.array([step[key] for step in steps]) for key in SEASONAL_LEDGER_KEYS}
    arrays["inventory_m3"] = _m4_hydrology_seasonal_validation_np.array(inventories)
    arrays["soil_mm"] = _m4_hydrology_seasonal_validation_np.array(soil_months)
    arrays["lake_volume_m3"] = _m4_hydrology_seasonal_validation_np.array(lake_months)
    arrays["precipitation_mm"] = climate["precipitation_mm"]
    arrays["potential_et_mm"] = climate["potential_et_mm"]
    arrays["metadata_json"] = _m4_hydrology_seasonal_validation_np.array(_m4_hydrology_seasonal_validation_json.dumps({"status": "nonperiodic_diagnostic_only",
          "source_plan_identity_sha256": plan["identity_sha256"], "parameters": _m4_hydrology_seasonal_validation_asdict(config)}, allow_nan=False))
    with output.with_suffix(".npz").open("xb") as stream:
        _m4_hydrology_seasonal_validation_np.savez_compressed(stream, **arrays)
    # This audit reads the written arrays; it does not rerun climate or time.
    with _m4_hydrology_seasonal_validation_np.load(output.with_suffix(".npz"), allow_pickle=False) as saved:
        rain = saved["land_rain_m3"] + saved["lake_rain_m3"]
        loss = saved["land_et_m3"] + saved["lake_evaporation_m3"] + saved["coastal_outflow_m3"]
        delta = saved["soil_change_m3"] + saved["lake_change_m3"]
        residual = rain - loss - delta
        inventory_residual = _m4_hydrology_seasonal_validation_np.diff(saved["inventory_m3"], axis=0) - delta
        rain_total = _m4_hydrology_seasonal_validation_np.array([saved["precipitation_mm"][:, owner == d["domain_id"]].sum() * area / 1000 for d in domains])
        partition_residual = rain.sum(axis=0) - rain_total
        finite = all(_m4_hydrology_seasonal_validation_np.isfinite(saved[key]).all() for key in saved.files if key != "metadata_json")
        annual_inventory = saved["inventory_m3"][-1] - saved["inventory_m3"][0]
    tolerance = max(1e-6, float(rain.max()) * 1e-9)
    cold_passed = finite and _m4_hydrology_seasonal_validation_np.max(_m4_hydrology_seasonal_validation_np.abs(residual)) <= tolerance and _m4_hydrology_seasonal_validation_np.max(_m4_hydrology_seasonal_validation_np.abs(inventory_residual)) <= tolerance and _m4_hydrology_seasonal_validation_np.max(_m4_hydrology_seasonal_validation_np.abs(partition_residual)) <= tolerance * len(steps)
    report["diagnostic_evaluations"] = used + 1
    report["cold_annual_account_audit"] = {"status": "passed" if cold_passed else "failed",
        "meaning": "nonperiodic annual arithmetic verified; seasonal acceptance remains failed",
        "max_step_residual_m3": float(_m4_hydrology_seasonal_validation_np.max(_m4_hydrology_seasonal_validation_np.abs(residual))),
        "max_step_inventory_residual_m3": float(_m4_hydrology_seasonal_validation_np.max(_m4_hydrology_seasonal_validation_np.abs(inventory_residual))),
        "rain_partition_residual_m3": partition_residual.tolist(),
        "annual_inventory_change_m3": annual_inventory.tolist(), "finite": finite}
    _write_report(output.with_suffix(".json"), report)
    return report

# --- terrain_pipeline/hydrology_seasonal_validation.py:93 ---
def main():
    from terrain_pipeline.hydrology_planning import load_plan as _m4_hydrology_seasonal_validation_load_plan
    parser = _m4_hydrology_seasonal_validation_argparse.ArgumentParser()
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    plan = _m4_hydrology_seasonal_validation_load_plan(args.plan)
    folder = _m4_hydrology_seasonal_validation_Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    failures = []
    results = []
    for substeps in (1, 2):
        config = _m4_hydrology_seasonal_validation_replace(SeasonalConfig(), substeps_per_day=substeps)
        try:
            result = simulate_seasonal_water_balance(plan, config)
            path = folder / f"seasonal-{substeps}step.npz"
            save_seasonal_water_balance(plan, result, path)
            cold = load_seasonal_water_balance(plan, path)
            report = validate_seasonal_water_balance(plan, cold)
            report["metadata"] = cold["metadata"]
            report["lake_level_m"] = cold["lake_level_m"][:, 1].tolist()
            _write_report(folder / f"seasonal-{substeps}step-audit.json", report)
            results.append(cold)
        except ValueError as error:
            failures.append(failure_evidence(plan, error, config, folder / f"seasonal-failure-{substeps}step"))
    if failures:
        _write_report(folder / "seasonal-step-comparison.json", {
            "status": "failed_at_least_one_step", "source_plan_identity_sha256": plan["identity_sha256"],
            "failures": [{"substeps_per_day": f["parameters"]["substeps_per_day"],
                          "annual_map_evaluations": f.get("annual_map_evaluations"), "reason": f["reason"],
                          "lower_level_m": f.get("lower_level_m")} for f in failures],
            "climate_and_pet_parameters_changed": False})
        print("actual failure and nonperiodic cold accounts retained")
        return
    daily, halfday = results
    _write_report(folder / "seasonal-step-comparison.json", {
        "status": "both_periodic_accounts_verified", "scope": "development candidate; planning visuals/catalog still need acceptance",
        "max_monthly_lake_level_difference_m": float(_m4_hydrology_seasonal_validation_np.max(_m4_hydrology_seasonal_validation_np.abs(daily["lake_level_m"][:, 1] - halfday["lake_level_m"][:, 1]))),
        "daily_monthly_lake_level_m": daily["lake_level_m"][:, 1].tolist(),
        "halfday_monthly_lake_level_m": halfday["lake_level_m"][:, 1].tolist(),
        "pet_calibration": "illustrative temperature-index PET; not calibrated or observed"})
    print("daily/halfday periodic accounts saved and cold-audited")

# --- terrain_pipeline/real_dem_rainfall_routing.py:18 ---
DEM_RAINFALL_ALGORITHM = "real-dem-irregular-metric-delayed-linear-storage-v2"

# --- terrain_pipeline/real_dem_rainfall_routing.py:19 ---
DEM_RAINFALL_MAX_BYTES = 512 * 1024 * 1024

# --- terrain_pipeline/real_dem_rainfall_routing.py:20 ---
DEM_RAINFALL_MAX_STEPS = 96

# --- terrain_pipeline/real_dem_rainfall_routing.py:21 ---
DEM_RAINFALL_MAX_ENTRIES = 24_000_000

# --- terrain_pipeline/real_dem_rainfall_routing.py:22 ---
RUNOFF_KEYS = ("rain_volume_m3", "et_volume_m3", "local_runoff_m3", "soil_change_m3",
               "fast_change_m3", "slow_change_m3", "runoff_residual_m3")

# --- terrain_pipeline/real_dem_rainfall_routing.py:24 ---
ROUTING_KEYS = ("channel_storage_change_m3", "engineering_discharge_m3", "verified_external_m3",
                "unknown_retained_m3", "internal_retained_m3", "whole_system_residual_m3")

# --- terrain_pipeline/real_dem_rainfall_routing.py:26 ---
DEM_RAINFALL_ARRAY_KEYS = {"valid_cell_ids", "rain_mm_h", "local_volume", "channel_storage",
              "final_soil_mm", "final_fast_mm", "final_slow_mm"}

# --- terrain_pipeline/real_dem_rainfall_routing.py:30 ---
def dem_scalar(value, name, minimum, maximum):
    if (isinstance(value, (bool, _m4_real_dem_rainfall_routing_np.bool_)) or not isinstance(value, (int, float, _m4_real_dem_rainfall_routing_np.integer, _m4_real_dem_rainfall_routing_np.floating))
            or not _m4_real_dem_rainfall_routing_math.isfinite(value) or not minimum <= value <= maximum):
        raise ValueError(f"invalid finite {name} range")
    return float(value)

# --- terrain_pipeline/real_dem_rainfall_routing.py:37 ---
def _flat_digest(flat_result):
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_real_dem_rainfall_routing_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _m4_real_dem_rainfall_routing_digest
    network = flat_result["network"]
    return _m4_real_dem_rainfall_routing_digest({"arrays": {name: _m4_real_dem_rainfall_routing_array_hash(getattr(network, name)) for name in
                              ("receiver", "order", "accumulation_cells", "boundary_outlet", "unknown_adjacent_terminal")},
                   "component_id": _m4_real_dem_rainfall_routing_array_hash(flat_result["component_id"]),
                   "distance_to_exit": _m4_real_dem_rainfall_routing_array_hash(flat_result["distance_to_exit"]),
                   "components": flat_result["components"], "summary": flat_result["summary"]})

# --- terrain_pipeline/real_dem_rainfall_routing.py:46 ---
def dem_inputs(candidate, flat_result, rain, dt_s, parameters, batch_cells, speed, engineering):
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_real_dem_rainfall_routing_array_hash
    from terrain_pipeline.artifacts.contracts import digest as _m4_real_dem_rainfall_routing_digest
    from terrain_pipeline.drainage import arrays_from_candidate as _m4_real_dem_rainfall_routing_arrays
    from terrain_pipeline.drainage import candidate_mesh as _m4_real_dem_rainfall_routing_candidate_mesh
    from terrain_pipeline.drainage import validate_flat_routing as _m4_real_dem_rainfall_routing_validate_flat_routing
    height, valid = _m4_real_dem_rainfall_routing_arrays(candidate)
    if type(batch_cells) is not int or batch_cells <= 0:
        raise ValueError("batch_cells must be a positive integer, not bool")
    dt_s = dem_scalar(dt_s, "dt_s", 1e-6, 1e7)
    speed = dem_scalar(speed, "speed_m_s", 1e-9, 1e6)
    if parameters is None:
        parameters = RunoffParameters()
    if not isinstance(parameters, RunoffParameters):
        raise ValueError("parameters must be RunoffParameters")
    parameters.__post_init__()
    ids = _m4_real_dem_rainfall_routing_np.flatnonzero(valid.ravel())
    if (not isinstance(rain, _m4_real_dem_rainfall_routing_np.ndarray) or rain.ndim not in (1, 2) or rain.dtype.kind not in "fiu"
            or (rain.ndim == 2 and rain.shape[1] != len(ids))):
        raise ValueError("rain_mm_h requires numeric [T] or [T,N] valid-ID order")
    steps = rain.shape[0]
    if not 1 <= steps <= DEM_RAINFALL_MAX_STEPS or steps * len(ids) > DEM_RAINFALL_MAX_ENTRIES:
        raise ValueError("rainfall graph/step entry budget exceeded")
    retained_bytes = 8 * ((2 * steps + 5) * len(ids) + rain.size + (len(RUNOFF_KEYS) + len(ROUTING_KEYS)) * steps)
    if retained_bytes > DEM_RAINFALL_MAX_BYTES:
        raise ValueError("rainfall retained array budget exceeds 512MiB")
    if not _m4_real_dem_rainfall_routing_np.isfinite(rain).all() or _m4_real_dem_rainfall_routing_np.any(rain < 0) or _m4_real_dem_rainfall_routing_np.any(rain > 1e6):
        raise ValueError("rain must be finite nonnegative <= 1e6 mm/h")
    _m4_real_dem_rainfall_routing_validate_flat_routing(candidate, flat_result)
    if "manifest" in candidate:
        grid = candidate["manifest"]["identity"]["grid"]
    else:
        grid = candidate.get("grid")
    if (not isinstance(grid, dict) or "spacing_x_m" not in grid or "spacing_z_m" not in grid
            or ("manifest" not in candidate and (grid.get("crs") != "EPSG:32651" or grid.get("units") != "metres"))):
        raise ValueError("explicit metric grid spacing_x_m/spacing_z_m required; no implicit 90m")
    spacing_x, spacing_z = grid["spacing_x_m"], grid["spacing_z_m"]
    spacing_x = dem_scalar(spacing_x, "spacing_x_m", 1e-6, 1e6)
    spacing_z = dem_scalar(spacing_z, "spacing_z_m", 1e-6, 1e6)
    if not isinstance(engineering, (tuple, list)):
        raise ValueError("engineering_terminal_ids must be explicit list/tuple")
    if any(type(cell) is not int or cell < 0 or cell >= height.size for cell in engineering) or len(set(engineering)) != len(engineering):
        raise ValueError("invalid or duplicate engineering terminal IDs")
    receiver = flat_result["network"].receiver.ravel()
    component = flat_result["component_id"].ravel()
    records = {record["component_id"]: record for record in flat_result["components"]}
    for cell in engineering:
        if not valid.ravel()[cell] or receiver[cell] != -1:
            raise ValueError("engineering discharge requires valid terminal")
        record = records[int(component[cell])]
        if (record["touches_unknown"] or not record["touches_boundary"]
                or record["classification"] != "closed_flat_retention" or record["root_cell_id"] != cell):
            raise ValueError("engineering discharge requires closed boundary component without unknown risk")
    mapping = _m4_real_dem_rainfall_routing_np.full(height.size, -1, _m4_real_dem_rainfall_routing_np.int64)
    mapping[ids] = _m4_real_dem_rainfall_routing_np.arange(len(ids))
    global_targets = receiver[ids]
    local_targets = _m4_real_dem_rainfall_routing_np.full(len(ids), -1, _m4_real_dem_rainfall_routing_np.int64)
    routed = global_targets >= 0
    local_targets[routed] = mapping[global_targets[routed]]
    mesh = _m4_real_dem_rainfall_routing_candidate_mesh(candidate)
    lengths = _m4_real_dem_rainfall_routing_np.full(len(ids), spacing_x)
    lengths[routed] = _m4_real_dem_rainfall_routing_np.hypot(mesh.node_x_m[ids[routed]] - mesh.node_x_m[global_targets[routed]],
                               mesh.node_z_m[ids[routed]] - mesh.node_z_m[global_targets[routed]])
    fraction = -_m4_real_dem_rainfall_routing_np.expm1(-dt_s * speed / lengths)
    external = _m4_real_dem_rainfall_routing_np.isin(ids, _m4_real_dem_rainfall_routing_np.asarray(engineering, _m4_real_dem_rainfall_routing_np.int64))
    fraction[~routed & ~external] = 0.
    terminal_unknown = _m4_real_dem_rainfall_routing_np.array([records[int(component[cell])]["touches_unknown"] for cell in ids], bool) & ~routed
    internal = ~routed & ~terminal_unknown & ~external
    metadata = {"algorithm": DEM_RAINFALL_ALGORITHM, "runoff_algorithm": "rainfall-runoff-v1", "dt_s": dt_s,
                "parameters": _m4_real_dem_rainfall_routing_asdict(parameters), "parameter_sha256": _m4_real_dem_rainfall_routing_digest(_m4_real_dem_rainfall_routing_asdict(parameters)),
                "speed_m_s": speed, "batch_cells": batch_cells,
                "effective_batch_cells": min(batch_cells, 100000, 1000000 // steps),
                "spacing_x_m": spacing_x, "spacing_z_m": spacing_z, "projected_crs": "EPSG:32651", "spacing_units": "metres",
                "engineering_terminal_ids": sorted(engineering), "cell_order": "ascending_valid_global_cell_id",
                "candidate_height_sha256": _m4_real_dem_rainfall_routing_array_hash(height), "valid_mask_sha256": _m4_real_dem_rainfall_routing_array_hash(valid),
                "candidate_content_sha256": candidate.get("manifest", {}).get("content_sha256"),
                "flat_result_sha256": _flat_digest(flat_result), "rain_sha256": _m4_real_dem_rainfall_routing_array_hash(rain),
                "rain_shape": list(rain.shape), "retained_array_budget_bytes": retained_bytes,
                "model": "one_way_linear_reservoir_not_Saint_Venant_no_backwater",
                "release": "old_storage*(-expm1(-dt_s/(edge_length_m/speed_m_s)))",
                "length_coordinates": "absolute_world_irregular_graph_nodes",
                "terminal_release_length": "declared_native_spacing_x_for_explicit_engineering_terminal",
                "arrival": "local_and_upstream_release_stored_until_next_step",
                "engineering_assumption": "explicit_closed_boundary_terminal_no_unknown_component",
                "global_graph_state": True, "natural_outlet_verified": False, "ocean_outlet_certified": False}
    return ids, local_targets, fraction, external, terminal_unknown, internal, parameters, metadata

# --- terrain_pipeline/real_dem_rainfall_routing.py:129 ---
def _runoff(rain, ids, metadata, parameters, local=None, finals=None):
    steps, cells = rain.shape[0], len(ids)
    ledger = {key: _m4_real_dem_rainfall_routing_np.zeros(steps) for key in RUNOFF_KEYS}
    area = metadata["spacing_x_m"] * metadata["spacing_z_m"]
    for start in range(0, cells, metadata["effective_batch_cells"]):
        stop = min(cells, start + metadata["effective_batch_cells"])
        batch_rain = _m4_real_dem_rainfall_routing_np.broadcast_to(rain[:, None], (steps, stop - start)) if rain.ndim == 1 else rain[:, start:stop]
        batch = simulate_rainfall_runoff(batch_rain, _m4_real_dem_rainfall_routing_np.full(stop - start, area), dt_s=metadata["dt_s"],
                                         source_id="real-dem-valid-global-id-batch", parameters=parameters)
        volume = batch["outflow_volume_m3"]
        if local is not None:
            dem_equal(local[:, start:stop], volume, "local runoff batch equations")
        else:
            yield start, stop, volume, {key: batch[key][-1].copy() for key in ("soil_mm", "fast_mm", "slow_mm")}
        for output, field in (("rain_volume_m3", "rain_volume_m3"), ("et_volume_m3", "et_volume_m3"),
                              ("local_runoff_m3", "outflow_volume_m3"), ("runoff_residual_m3", "balance_residual_m3")):
            ledger[output] += batch[field].sum(axis=1)
        for name in ("soil", "fast", "slow"):
            ledger[name + "_change_m3"] += (_m4_real_dem_rainfall_routing_np.diff(batch[name + "_mm"], axis=0) * (area / 1000.)).sum(axis=1)
            if finals is not None:
                dem_equal(finals["final_" + name + "_mm"][start:stop], batch[name + "_mm"][-1], name + " final runoff state")
        del batch
    yield ledger

# --- terrain_pipeline/real_dem_rainfall_routing.py:154 ---
def dem_equal(actual, expected, label):
    if not _m4_real_dem_rainfall_routing_np.allclose(actual, expected, rtol=1e-10, atol=1e-8):
        raise ValueError(f"rainfall equation/ledger mismatch: {label}")

# --- terrain_pipeline/real_dem_rainfall_routing.py:159 ---
def _routing_ledger(storage, local, targets, fraction, external, unknown, internal, runoff):
    steps, cells = local.shape
    ledger = {key: _m4_real_dem_rainfall_routing_np.zeros(steps) for key in ROUTING_KEYS}
    routed = targets >= 0
    for step in range(steps):
        release = storage[step] * fraction
        incoming = _m4_real_dem_rainfall_routing_np.bincount(targets[routed], weights=release[routed], minlength=cells)
        expected = storage[step] - release + incoming + local[step]
        dem_equal(storage[step + 1], expected, "channel storage one-edge delayed propagation")
        ledger["channel_storage_change_m3"][step] = (storage[step + 1] - storage[step]).sum()
        ledger["engineering_discharge_m3"][step] = release[external].sum()
        ledger["unknown_retained_m3"][step] = storage[step + 1, unknown].sum()
        ledger["internal_retained_m3"][step] = storage[step + 1, internal].sum()
    ledger["whole_system_residual_m3"] = (runoff["rain_volume_m3"] - runoff["et_volume_m3"]
        - runoff["soil_change_m3"] - runoff["fast_change_m3"] - runoff["slow_change_m3"]
        - ledger["channel_storage_change_m3"] - ledger["engineering_discharge_m3"])
    scale = runoff["rain_volume_m3"] + runoff["et_volume_m3"] + _m4_real_dem_rainfall_routing_np.abs(ledger["channel_storage_change_m3"])
    if _m4_real_dem_rainfall_routing_np.any(abs(ledger["whole_system_residual_m3"]) > 1e-7 + 1e-10 * scale):
        raise ValueError("whole system water balance failed")
    return ledger

# --- terrain_pipeline/real_dem_rainfall_routing.py:181 ---
def _summary(result):
    ledger = result["ledger"]
    return {"steps": result["local_volume"].shape[0], "valid_cells": len(result["valid_cell_ids"]),
            "rain_volume_m3": float(ledger["rain_volume_m3"].sum()),
            "local_runoff_m3": float(ledger["local_runoff_m3"].sum()),
            "et_volume_m3": float(ledger["et_volume_m3"].sum()),
            "engineering_discharge_m3": float(ledger["engineering_discharge_m3"].sum()),
            "verified_external_m3": 0., "final_channel_storage_m3": float(result["channel_storage"][-1].sum()),
            "max_abs_whole_system_residual_m3": float(abs(ledger["whole_system_residual_m3"]).max()),
            "retained_array_nbytes": sum(result[key].nbytes for key in DEM_RAINFALL_ARRAY_KEYS) + sum(value.nbytes for value in ledger.values()),
            "retention_semantics": "unknown/internal_retained are end-step inventories, not repeated losses",
            "memory_scope": "retained arrays only; candidate/flat graph/runoff batch/temporaries excluded",
            "natural_outlet_verified": False, "ocean_outlet_certified": False}

# --- terrain_pipeline/real_dem_rainfall_routing.py:196 ---
def simulate_dem_rainfall(candidate, flat_result, rain_mm_h, *, dt_s, parameters=None,
                          batch_cells=100000, speed_m_s=1.0, engineering_terminal_ids=()) -> dict:
    from terrain_pipeline.artifacts.contracts import array_hash as _m4_real_dem_rainfall_routing_array_hash
    ids, targets, fraction, external, unknown, internal, parameters, metadata = dem_inputs(
        candidate, flat_result, rain_mm_h, dt_s, parameters, batch_cells, speed_m_s, engineering_terminal_ids)
    rain = rain_mm_h.astype(_m4_real_dem_rainfall_routing_np.float64, copy=True)
    metadata["rain_sha256"] = _m4_real_dem_rainfall_routing_array_hash(rain)
    steps, cells = rain.shape[0], len(ids)
    local = _m4_real_dem_rainfall_routing_np.zeros((steps, cells))
    result = {"valid_cell_ids": ids, "rain_mm_h": rain, "local_volume": local,
              "channel_storage": _m4_real_dem_rainfall_routing_np.zeros((steps + 1, cells)), "metadata": metadata,
              **{"final_" + name + "_mm": _m4_real_dem_rainfall_routing_np.zeros(cells) for name in ("soil", "fast", "slow")}}
    for item in _runoff(rain, ids, metadata, parameters):
        if isinstance(item, dict):
            runoff = item
        else:
            start, stop, volume, final = item
            local[:, start:stop] = volume
            for name in ("soil", "fast", "slow"):
                result["final_" + name + "_mm"][start:stop] = final[name + "_mm"]
    storage = result["channel_storage"]
    routed = targets >= 0
    for step in range(steps):
        release = storage[step] * fraction
        storage[step + 1] = storage[step] - release + local[step]
        storage[step + 1] += _m4_real_dem_rainfall_routing_np.bincount(targets[routed], weights=release[routed], minlength=cells)
    result["ledger"] = {**runoff, **_routing_ledger(storage, local, targets, fraction, external, unknown, internal, runoff)}
    result["summary"] = _summary(result)
    return result

# --- terrain_pipeline/real_dem_rainfall_routing.py:226 ---
def validate_dem_rainfall(candidate, flat_result, result) -> dict:
    """Replay bounded runoff batches, then audit saved propagation equations."""
    from terrain_pipeline.artifacts.contracts import canonical_json as _m4_real_dem_rainfall_routing_canonical_json
    if not isinstance(result, dict) or set(result) != DEM_RAINFALL_ARRAY_KEYS | {"metadata", "ledger", "summary"}:
        raise ValueError("invalid rainfall result schema")
    metadata = result["metadata"]
    try:
        parameters = RunoffParameters(**metadata["parameters"])
        ids, targets, fraction, external, unknown, internal, parameters, expected_metadata = dem_inputs(
            candidate, flat_result, result["rain_mm_h"], metadata["dt_s"], parameters,
            metadata["batch_cells"], metadata["speed_m_s"], metadata["engineering_terminal_ids"])
    except (KeyError, TypeError) as error:
        raise ValueError("invalid rainfall metadata") from error
    if _m4_real_dem_rainfall_routing_canonical_json(metadata) != _m4_real_dem_rainfall_routing_canonical_json(expected_metadata):
        raise ValueError("rainfall source/parameter/rain/risk binding mismatch")
    if not _m4_real_dem_rainfall_routing_np.array_equal(result["valid_cell_ids"], ids) or result["valid_cell_ids"].dtype != _m4_real_dem_rainfall_routing_np.dtype(_m4_real_dem_rainfall_routing_np.int64):
        raise ValueError("valid ID order mismatch")
    steps, cells = result["rain_mm_h"].shape[0], len(ids)
    for key in DEM_RAINFALL_ARRAY_KEYS - {"valid_cell_ids"}:
        values = result[key]
        shape = (steps, cells) if key == "local_volume" else (steps + 1, cells) if key == "channel_storage" else (cells,)
        if key == "rain_mm_h":
            shape = tuple(metadata["rain_shape"])
        if (not isinstance(values, _m4_real_dem_rainfall_routing_np.ndarray) or values.dtype != _m4_real_dem_rainfall_routing_np.dtype(_m4_real_dem_rainfall_routing_np.float64) or values.shape != shape
                or not _m4_real_dem_rainfall_routing_np.isfinite(values).all() or _m4_real_dem_rainfall_routing_np.any(values < 0)):
            raise ValueError(f"invalid rainfall array {key}")
    if _m4_real_dem_rainfall_routing_np.any(result["channel_storage"][0] != 0):
        raise ValueError("initial channel storage must be zero")
    for runoff in _runoff(result["rain_mm_h"], ids, metadata, parameters, local=result["local_volume"], finals=result):
        pass
    expected_ledger = {**runoff, **_routing_ledger(result["channel_storage"], result["local_volume"], targets,
                                                 fraction, external, unknown, internal, runoff)}
    if set(result["ledger"]) != set(expected_ledger):
        raise ValueError("invalid rainfall ledger keys")
    for key, expected in expected_ledger.items():
        values = result["ledger"][key]
        if (not isinstance(values, _m4_real_dem_rainfall_routing_np.ndarray) or values.dtype != _m4_real_dem_rainfall_routing_np.dtype(_m4_real_dem_rainfall_routing_np.float64)
                or values.shape != (steps,) or not _m4_real_dem_rainfall_routing_np.isfinite(values).all()):
            raise ValueError("invalid ledger array")
        dem_equal(values, expected, key)
    if _m4_real_dem_rainfall_routing_canonical_json(result["summary"]) != _m4_real_dem_rainfall_routing_canonical_json(_summary(result)):
        raise ValueError("rainfall summary mismatch")
    return {"verified": True, "summary": dict(result["summary"]), "verified_external_m3": 0.,
            "natural_outlet_verified": False, "ocean_outlet_certified": False}

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:94 ---
__all__ = [
    "ALGORITHM",
    "DESIGN_Q_SEMANTICS",
    "INSTANTANEOUS_Q_SEMANTICS",
    "NATIVE_SPACING_M",
    "RAIN_SEMANTICS",
    "SCHEMA",
    "TERMINAL_SEMANTICS",
    "run_catchment_event",
]

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:106 ---
NATIVE_30M_RUNOFF_ALGORITHM = "native-30m-catchment-event-irregular-v2"

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:107 ---
NATIVE_30M_RUNOFF_SCHEMA = "native-30m-catchment-event-dict-v1"

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:110 ---
NATIVE_SPACING_M = _m4_native_30m_runoff_PhysicalGenerationConfig().native_resolution_m

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:111 ---
DIAGNOSTIC_TERMINAL_LABEL = "retained"

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:113 ---
RAIN_SEMANTICS = (
    "declared interval rain series: one mm/h value per physical interval of dt_s, "
    "applied uniformly to every active catchment cell and passed through the "
    "existing soil bucket (rainfall_runoff.simulate_rainfall_runoff). It is a "
    "rainfall rate, not a runoff rate: no bare rainfall-to-runoff conversion is "
    "applied and none may be substituted for the bucket")

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:119 ---
INSTANTANEOUS_Q_SEMANTICS = (
    "instantaneous topological sum of per-cell local m3/s on the declared finite "
    "graph (metric_network_accumulation.accumulate_network_discharge); no travel "
    "delay, no storage, every sub-catchment simultaneously at peak. Diagnostic "
    "upper envelope only; never a design discharge")

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:124 ---
DESIGN_Q_SEMANTICS = (
    "event peak of the routed terminal-reach outflow "
    "(mountain_runoff_routing.route_local_discharge: interval volumes through a "
    "linear-reservoir cascade, tau = max(reach_length, minimum_length)/speed). "
    "event_design_q_not_bankfull: it is the peak of a declared synthetic storm "
    "event, not bankfull, not a return-period flood, not calibrated")

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:130 ---
TERMINAL_SEMANTICS = (
    "the single receiver == -1 cell of the catchment is a declared finite reach "
    "boundary and the retained endpoint of this event. It is not a certified "
    "natural outlet, not an ocean or lake connection, and no external upstream "
    "contribution is declared")

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:135 ---
NATIVE_30M_CELL_ORDER = ("active_cells holds flat row-major cell ids (row * columns + column) "
              "in ascending order; local_q_m3_s columns follow that order")

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:137 ---
OUTSIDE_SCOPE = (
    "cells outside catchment_mask contribute local Q of exactly 0.0 m3/s. That is "
    "a declared event scope, not a measurement of those cells")

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:146 ---
def _canonical(value):
    return _m4_native_30m_runoff_json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:150 ---
def _array_sha256(array):
    digest = _m4_native_30m_runoff_hashlib.sha256()
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(_m4_native_30m_runoff_np.ascontiguousarray(array).tobytes(order="C"))
    return digest.hexdigest()

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:158 ---
def _typed_grid(value, name, dtype):
    if (not isinstance(value, _m4_native_30m_runoff_np.ndarray) or value.ndim != 2
            or value.dtype != _m4_native_30m_runoff_np.dtype(dtype) or value.size < 1):
        raise ValueError(
            "invalid_%s: a nonempty 2-D %s ndarray is required" % (name, dtype))
    return value

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:166 ---
def _positive_scalar(value, name, maximum):
    if (isinstance(value, (bool, _m4_native_30m_runoff_np.bool_))
            or not isinstance(value, (int, float, _m4_native_30m_runoff_np.integer, _m4_native_30m_runoff_np.floating))
            or not _m4_native_30m_runoff_np.isfinite(value) or not 0 < value <= maximum):
        raise ValueError("invalid_%s: finite positive <= %r required" % (name, maximum))

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:173 ---
def _topological_order(flat_receiver):
    """Upstream-first order of one acyclic flat receiver graph (Kahn)."""
    size = flat_receiver.size
    pending = _m4_native_30m_runoff_np.bincount(flat_receiver[flat_receiver >= 0], minlength=size)
    frontier = list(_m4_native_30m_runoff_np.flatnonzero(pending == 0).tolist())
    order = []
    position = 0
    while position < len(frontier):
        cell = frontier[position]
        position += 1
        order.append(cell)
        target = int(flat_receiver[cell])
        if target >= 0:
            pending[target] -= 1
            if pending[target] == 0:
                frontier.append(target)
    if len(order) != size:
        raise ValueError("receiver_cycle: the receiver graph is not acyclic")
    return _m4_native_30m_runoff_np.asarray(order, dtype=_m4_native_30m_runoff_np.int64)

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:194 ---
def _terminal_reached(flat_receiver):
    """Flat id of the terminal each cell ultimately drains to (path doubling)."""
    size = flat_receiver.size
    self_id = _m4_native_30m_runoff_np.arange(size, dtype=_m4_native_30m_runoff_np.int64)
    reached = _m4_native_30m_runoff_np.where(flat_receiver < 0, self_id, _m4_native_30m_runoff_np.int64(-1))
    hop = _m4_native_30m_runoff_np.where(flat_receiver < 0, self_id, flat_receiver)
    while True:
        updated = _m4_native_30m_runoff_np.where(reached >= 0, reached, reached[hop])
        if _m4_native_30m_runoff_np.array_equal(updated, reached):
            return reached
        reached = updated

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:207 ---
def _receiver_diagnostics(receiver, shape, origin=(0, 0), seed=20261020):
    """Reject bad topology here, with a reason code, before any allocation."""
    size = receiver.size
    flat = receiver.ravel()
    if (flat < -1).any() or (flat >= size).any():
        raise ValueError(
            "receiver_index_out_of_range: receiver entries must be -1 or a valid "
            "flat id in [0, %d)" % size)
    sources = _m4_native_30m_runoff_np.flatnonzero(flat >= 0)
    targets = flat[sources]
    if (sources == targets).any():
        raise ValueError("receiver_self_loop: a cell cannot receive itself")
    from terrain_pipeline.drainage import grid_mesh as grid_mesh
    from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid
    mesh = grid_mesh(shape, x0_m=origin[0] * 30., z0_m=origin[1] * 30.,
                     dx_m=30., world_seed=seed)
    if not receiver_edges_valid(receiver, mesh):
        raise ValueError("receiver_not_graph_edge: every receiver must follow the irregular graph")
    order = _topological_order(flat)
    return {"flat": flat, "order": order, "size": int(size)}

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:228 ---
def _catchment_diagnostics(flat, catchment, elevation_flat):
    inside = catchment.ravel()
    if not inside.any():
        raise ValueError("catchment_empty: at least one catchment cell is required")
    donors = flat >= 0
    leak = inside & donors & ~_m4_native_30m_runoff_np.where(donors, inside[_m4_native_30m_runoff_np.where(donors, flat, 0)], True)
    if leak.any():
        raise ValueError(
            "catchment_leaks_outside: %d catchment cell(s) drain to a receiver "
            "outside catchment_mask, so no external water may be substituted"
            % int(leak.sum()))
    terminals = _m4_native_30m_runoff_np.flatnonzero(inside & ~donors)
    if terminals.size != 1:
        raise ValueError(
            "catchment_terminal_count: the catchment must hold exactly one "
            "receiver == -1 cell, found %d" % int(terminals.size))
    terminal = int(terminals[0])
    not_land = inside & (elevation_flat <= 0)
    if not_land.any():
        raise ValueError(
            "catchment_cell_not_land: %d catchment cell(s) have elevation <= 0; the "
            "reach router only allocates HRUs to cells with height > 0"
            % int(not_land.sum()))
    return {"mask": inside, "terminal": terminal}

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:254 ---
def _flowline_diagnostics(flowline, inside, flat, terminal):
    line = flowline.ravel()
    if not line.any():
        raise ValueError("flowline_empty: at least one flowline cell is required")
    outside = line & ~inside
    if outside.any():
        raise ValueError(
            "flowline_outside_catchment: %d flowline cell(s) lie outside "
            "catchment_mask" % int(outside.sum()))
    donors = flat >= 0
    target_inside_line = _m4_native_30m_runoff_np.where(donors, line[_m4_native_30m_runoff_np.where(donors, flat, 0)], True)
    broken = line & donors & ~target_inside_line
    if broken.any():
        raise ValueError(
            "flowline_not_downstream_closed: %d flowline cell(s) drain to a cell "
            "outside the flowline and outside the declared terminals"
            % int(broken.sum()))
    reached = _terminal_reached(flat)
    detached = line & (reached != terminal)
    if detached.any():
        raise ValueError(
            "flowline_not_connected_to_terminal: %d flowline cell(s) do not reach "
            "the declared catchment terminal" % int(detached.sum()))
    return {"mask": line, "cells": int(line.sum())}

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:280 ---
def _origin(value):
    if (not isinstance(value, (tuple, list)) or len(value) != 2
            or any(isinstance(item, (bool, _m4_native_30m_runoff_np.bool_)) for item in value)
            or any(not isinstance(item, (int, _m4_native_30m_runoff_np.integer)) for item in value)):
        raise ValueError(
            "invalid_origin_native_xz: a two-entry integer (x, z) native-cell "
            "origin is required")
    return [int(value[0]), int(value[1])]

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:290 ---
def _source_identity(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(character not in _m4_native_30m_runoff_string.hexdigits for character in value)):
        raise ValueError(
            "invalid_source_identity_sha256: a 64-character hex digest is required")
    return value.lower()

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:298 ---
def _world_seed(value):
    if isinstance(value, (bool, _m4_native_30m_runoff_np.bool_)) or not isinstance(value, (int, _m4_native_30m_runoff_np.integer)):
        raise ValueError("invalid_world_seed: a nonnegative integer is required")
    if value < 0:
        raise ValueError("invalid_world_seed: a nonnegative integer is required")
    return int(value)

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:310 ---
def _rainfall_budget(steps, cells):
    if steps > RUNOFF_MAX_STEPS:
        raise ValueError(
            "budget_rainfall_steps: %d intervals exceed the soil-bucket "
            "MAX_STEPS=%d" % (steps, RUNOFF_MAX_STEPS))
    if cells > RUNOFF_MAX_CELLS:
        raise ValueError(
            "budget_rainfall_cells: %d catchment cells exceed the soil-bucket "
            "MAX_CELLS=%d" % (cells, RUNOFF_MAX_CELLS))
    entries = steps * cells
    if entries > RUNOFF_MAX_ENTRIES:
        raise ValueError(
            "budget_rainfall_entries: %d catchment cells x %d intervals = %d "
            "entries exceed the soil-bucket MAX_ENTRIES=%d; the data is not "
            "truncated and no limit is raised"
            % (cells, steps, entries, RUNOFF_MAX_ENTRIES))
    estimate = 24 * 8 * (steps + 1) * cells
    if estimate > RUNOFF_MAX_BYTES:
        raise ValueError(
            "budget_rainfall_bytes: estimated %d bytes exceed the soil-bucket "
            "MAX_BYTES=%d" % (estimate, RUNOFF_MAX_BYTES))
    return {"steps": int(steps), "cells": int(cells), "entries": int(entries),
            "estimated_bytes": int(estimate),
            "limits": {"max_steps": RUNOFF_MAX_STEPS, "max_cells": RUNOFF_MAX_CELLS,
                       "max_entries": RUNOFF_MAX_ENTRIES,
                       "max_bytes": RUNOFF_MAX_BYTES}}

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:338 ---
def _route_budget(steps, cells, hrus, reaches):
    try:
        return preflight(steps, cells, hrus, reaches)
    except ValueError as error:
        raise ValueError(
            "budget_route: %d steps x %d grid cells with %d HRU(s) and %d reach(es) "
            "exceed the reach-router budget (%s); the sub-window is not shrunk and "
            "no limit is raised" % (steps, cells, hrus, reaches, error)) from error

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:348 ---
def _diagnostic_budget(steps, cells):
    entries = steps * cells
    if entries > MOUNTAIN_ROUTING_MAX_ENTRIES:
        raise ValueError(
            "budget_diagnostic_entries: %d intervals x %d cells = %d entries exceed "
            "the existing %d entry ceiling reused for the per-interval diagnostic "
            "accumulation" % (steps, cells, entries, MOUNTAIN_ROUTING_MAX_ENTRIES))
    return {"steps": int(steps), "cells": int(cells), "entries": int(entries),
            "max_entries": MOUNTAIN_ROUTING_MAX_ENTRIES}

# --- terrain_pipeline/surface_rivers/native_30m_runoff.py:363 ---
def run_catchment_event(elevation_m, receiver, catchment_mask, flowline_mask, *,
                        origin_native_xz, source_identity_sha256, world_seed,
                        rain_mm_h, dt_s, runoff_parameters,
                        travel_speed_m_s=1.0, minimum_reach_length_m=30.0):
    """Run one declared storm over one closed native-30 m catchment.

    Returns a plain dict of arrays and declarations; nothing is written to disk.
    Every rejection happens before the first allocation and carries a stable
    reason token as the first word of the message.
    """
    from terrain_pipeline.drainage import accumulate_network_discharge as _m4_native_30m_runoff_accumulate_network_discharge
    elevation = _typed_grid(elevation_m, "elevation_m", "float64")
    if not _m4_native_30m_runoff_np.isfinite(elevation).all():
        raise ValueError("invalid_elevation_m: every elevation must be finite")
    receiver_array = _typed_grid(receiver, "receiver", "int64")
    catchment = _typed_grid(catchment_mask, "catchment_mask", "bool")
    flowline = _typed_grid(flowline_mask, "flowline_mask", "bool")
    if not (receiver_array.shape == catchment.shape == flowline.shape):
        raise ValueError(
            "invalid_shape: elevation, receiver and both masks must share one shape")
    shape = elevation.shape
    routing_cells = int(elevation.size)
    if routing_cells > MOUNTAIN_ROUTING_MAX_CELLS:
        raise ValueError(
            "budget_route: the route grid holds %d cells, above the reach-router "
            "MAX_CELLS=%d; declare a smaller routing sub-window instead of "
            "shrinking the data" % (routing_cells, MOUNTAIN_ROUTING_MAX_CELLS))

    origin = _origin(origin_native_xz)
    binding_identity = _source_identity(source_identity_sha256)
    seed = _world_seed(world_seed)

    graph = _receiver_diagnostics(receiver_array, shape, origin, seed)
    flat_receiver = graph["flat"]
    basin = _catchment_diagnostics(flat_receiver, catchment, elevation.ravel())
    line = _flowline_diagnostics(flowline, basin["mask"], flat_receiver,
                                 basin["terminal"])
    terminal = basin["terminal"]

    if not isinstance(rain_mm_h, _m4_native_30m_runoff_np.ndarray) or rain_mm_h.ndim != 1:
        raise ValueError(
            "rain_not_interval_series: rain_mm_h must be a 1-D interval series, one "
            "value per physical interval; a cumulative table or a per-cell field "
            "cannot be declared here")
    if rain_mm_h.dtype.kind not in "fiu" or not _m4_native_30m_runoff_np.isfinite(rain_mm_h).all():
        raise ValueError(
            "invalid_rain: the interval series must be finite and real-valued")
    if (rain_mm_h < 0).any() or (rain_mm_h > 1e6).any():
        raise ValueError("invalid_rain: interval rain must lie in [0, 1e6] mm/h")
    rain = _m4_native_30m_runoff_np.ascontiguousarray(rain_mm_h, dtype=_m4_native_30m_runoff_np.float64)
    intervals = int(rain.size)
    if intervals < 1:
        raise ValueError("invalid_rain: at least one interval is required")

    _positive_scalar(dt_s, "dt_s", 1e7)
    if dt_s < 1e-6:
        raise ValueError("invalid_dt_s: dt_s must be >= 1e-6 s")
    _positive_scalar(travel_speed_m_s, "travel_speed_m_s", 100.0)
    _positive_scalar(minimum_reach_length_m, "minimum_reach_length_m", 1e6)
    if not isinstance(runoff_parameters, RunoffParameters):
        raise ValueError(
            "runoff_parameters_required: an explicit RunoffParameters instance is "
            "required; no default soil bucket is assumed")
    runoff_parameters.__post_init__()

    active = _m4_native_30m_runoff_np.flatnonzero(basin["mask"])
    active_cells = int(active.size)
    spacing = float(NATIVE_SPACING_M)
    cell_area = spacing * spacing
    land = elevation.ravel() > 0

    bucket_budget = _rainfall_budget(intervals, active_cells)
    _route_budget(intervals, routing_cells, 1, 1)
    diagnostic_budget = _diagnostic_budget(intervals, routing_cells)

    # --- soil bucket, catchment cells only ---------------------------------- #
    rain_block = _m4_native_30m_runoff_np.broadcast_to(rain[:, None], (intervals, active_cells)).copy()
    areas = _m4_native_30m_runoff_np.full(active_cells, cell_area, dtype=_m4_native_30m_runoff_np.float64)
    source_id = "native-30m-catchment-event:%s:terminal-%d" % (
        binding_identity[:16], terminal)
    bucket = simulate_rainfall_runoff(rain_block, areas, dt_s=float(dt_s),
                                     source_id=source_id,
                                     parameters=runoff_parameters)
    local_q = bucket["local_q_m3_s"]

    # --- reach mapping, once, to learn which reach each catchment cell owns -- #
    outlet_mask = (receiver_array < 0)
    provisional_owner = _m4_native_30m_runoff_np.full(routing_cells, -1, dtype=_m4_native_30m_runoff_np.int64)
    provisional_owner[land] = 0
    provisional_area = _m4_native_30m_runoff_np.array([float(_m4_native_30m_runoff_np.count_nonzero(land)) * cell_area],
                                dtype=_m4_native_30m_runoff_np.float64)
    provisional = {"height_m": elevation, "receiver": receiver_array,
                   "flowline_mask": flowline, "outlet_mask": outlet_mask,
                   "cell_owner": provisional_owner.reshape(shape),
                   "area_m2": provisional_area}
    try:
        mapping = build_reaches(**provisional, spacing_m=spacing,
                               speed_m_s=float(travel_speed_m_s),
                               minimum_length_m=float(minimum_reach_length_m))
    except ValueError as error:
        raise ValueError("route_mapping_rejected: %s" % (error,)) from error
    cell_reach = mapping["cell_reach"].ravel()

    reach_ids, group_of_active = _m4_native_30m_runoff_np.unique(cell_reach[active], return_inverse=True)
    groups = int(reach_ids.size)
    outside_cells = int(_m4_native_30m_runoff_np.count_nonzero(land & ~basin["mask"]))
    outside_group = 1 if outside_cells else 0
    hrus = groups + outside_group
    if hrus > MAX_HRUS:
        raise ValueError(
            "budget_hru: %d catchment cells occupy %d distinct reaches, plus %d "
            "outside HRU(s), which exceeds the reach-router MAX_HRUS=%d; per-cell "
            "HRUs would need %d and are not available either"
            % (active_cells, groups, outside_group, MAX_HRUS, active_cells))

    owner = _m4_native_30m_runoff_np.full(routing_cells, -1, dtype=_m4_native_30m_runoff_np.int64)
    owner[active] = group_of_active
    if outside_group:
        owner[land & ~basin["mask"]] = groups
    counts = _m4_native_30m_runoff_np.bincount(owner[land], minlength=hrus)
    hru_area = counts.astype(_m4_native_30m_runoff_np.float64) * cell_area

    hru_q = _m4_native_30m_runoff_np.zeros((intervals, hrus), dtype=_m4_native_30m_runoff_np.float64)
    for step in range(intervals):
        hru_q[step, :groups] = _m4_native_30m_runoff_np.bincount(group_of_active, weights=local_q[step],
                                           minlength=groups)

    binding = {
        "algorithm": NATIVE_30M_RUNOFF_ALGORITHM,
        "origin_native_xz": origin,
        "source_identity_sha256": binding_identity,
        "world_seed": seed,
        "spacing_m": spacing,
        "grid_shape": [int(shape[0]), int(shape[1])],
        "elevation_sha256": _array_sha256(elevation),
        "receiver_sha256": _array_sha256(receiver_array),
        "catchment_mask_sha256": _array_sha256(catchment),
        "flowline_mask_sha256": _array_sha256(flowline),
        "terminal_flat_cell": int(terminal),
        "terminal_native_xz": [origin[0] + int(terminal % shape[1]),
                               origin[1] + int(terminal // shape[1])],
        "rain_mm_h_sha256": _array_sha256(rain),
        "runoff_parameter_sha256": bucket["metadata"]["parameter_sha256"],
        "dt_s": float(dt_s),
        "travel_speed_m_s": float(travel_speed_m_s),
        "minimum_reach_length_m": float(minimum_reach_length_m),
    }

    # --- reach routing: the only quantity with travel delay ------------------ #
    route_inputs = {"height_m": elevation, "receiver": receiver_array,
                    "flowline_mask": flowline, "outlet_mask": outlet_mask,
                    "cell_owner": owner.reshape(shape),
                    "area_m2": hru_area, "local_q_m3_s": hru_q}
    routed = route_local_discharge(route_inputs, dt_s=float(dt_s),
                                  spacing_m=spacing, source_binding=binding,
                                  speed_m_s=float(travel_speed_m_s),
                                  minimum_length_m=float(minimum_reach_length_m))

    # The pre-pass mapping must be the mapping the router actually used. Only the
    # HRU-independent keys are compared: `allocation_counts` is [reach, HRU] and
    # therefore differs in width by construction, and the fraction assertion
    # below is what checks it.
    for key in ("river_reach", "cell_reach", "reach_downstream", "reach_length_m",
                "tau_s"):
        if not _m4_native_30m_runoff_np.array_equal(_m4_native_30m_runoff_np.asarray(mapping[key]), _m4_native_30m_runoff_np.asarray(routed[key])):
            raise ValueError(
                "route_mapping_rejected: the %s mapping changed between the "
                "attribution pre-pass and the routing call" % key)

    fractions = ((routed["allocation_counts"] * spacing ** 2)
                 / routed["area_m2"][None, :])
    own_fraction = fractions[reach_ids, _m4_native_30m_runoff_np.arange(groups)]
    if not _m4_native_30m_runoff_np.all(own_fraction == 1.0):
        raise ValueError(
            "hru_fraction_not_unit: a catchment HRU is rescale-weighted by the "
            "router (own-reach fraction not exactly 1.0), so its water would be "
            "spread over reaches it does not drain to")
    if not _m4_native_30m_runoff_np.all(fractions[:, :groups].sum(axis=0) == 1.0):
        raise ValueError(
            "hru_fraction_not_unit: a catchment HRU does not allocate exactly its "
            "whole unit fraction to its own reach")
    if outside_group and _m4_native_30m_runoff_np.any(hru_q[:, groups:] != 0):
        raise ValueError(
            "hru_fraction_not_unit: the outside-catchment HRU would carry nonzero "
            "declared local Q")

    terminal_reach = int(routed["river_reach"].ravel()[terminal])
    if terminal_reach < 0:
        raise ValueError(
            "terminal_not_on_a_flowline: the declared terminal has no routed reach")
    if int(routed["reach_downstream"][terminal_reach]) != -1:
        raise ValueError(
            "terminal_reach_not_terminal: the reach holding the declared terminal "
            "does not end there")
    routed_q = routed["outflow_volume_m3"][:, terminal_reach] / float(dt_s)
    design_interval = int(_m4_native_30m_runoff_np.argmax(routed_q))
    design_q = float(routed_q[design_interval])

    # --- instantaneous diagnostic accumulation on the same graph ------------ #
    valid_mask = _m4_native_30m_runoff_np.ones(shape, dtype=bool)
    terminal_kind = _m4_native_30m_runoff_np.full(shape, "interior", dtype="U24")
    terminal_kind[outlet_mask] = DIAGNOSTIC_TERMINAL_LABEL
    unknown = _m4_native_30m_runoff_np.zeros(shape, dtype=bool)
    input_total = _m4_native_30m_runoff_np.zeros(intervals, dtype=_m4_native_30m_runoff_np.float64)
    retained = _m4_native_30m_runoff_np.zeros(intervals, dtype=_m4_native_30m_runoff_np.float64)
    open_outflow = _m4_native_30m_runoff_np.zeros(intervals, dtype=_m4_native_30m_runoff_np.float64)
    unknown_pending = _m4_native_30m_runoff_np.zeros(intervals, dtype=_m4_native_30m_runoff_np.float64)
    residual = _m4_native_30m_runoff_np.zeros(intervals, dtype=_m4_native_30m_runoff_np.float64)
    instantaneous = _m4_native_30m_runoff_np.zeros(intervals, dtype=_m4_native_30m_runoff_np.float64)
    other_terminal_peak = 0.0
    terminal_field = _m4_native_30m_runoff_np.zeros(routing_cells, dtype=_m4_native_30m_runoff_np.float64)
    peak_payload = None
    for step in range(intervals):
        terminal_field[:] = 0.0
        terminal_field[active] = local_q[step]
        try:
            ledger = _m4_native_30m_runoff_accumulate_network_discharge(
                receiver_array, terminal_field.reshape(shape), valid_mask,
                terminal_kind=terminal_kind)
        except ValueError as error:
            raise ValueError("diagnostic_graph_rejected: %s" % (error,)) from error
        input_total[step] = ledger["input_total_m3_s"]
        retained[step] = ledger["retained_m3_s"]
        open_outflow[step] = ledger["open_outflow_m3_s"]
        unknown_pending[step] = ledger["unknown_pending_m3_s"]
        residual[step] = ledger["residual_m3_s"]
        terminal_series = ledger["terminal_q_m3_s"].ravel()
        instantaneous[step] = float(terminal_series[terminal])
        other = float(_m4_native_30m_runoff_np.abs(terminal_series).sum() - abs(terminal_series[terminal]))
        other_terminal_peak = max(other_terminal_peak, other)
        if step == design_interval:
            peak_payload = {
                "interval_index": int(step),
                "interval_seconds": [float(step) * float(dt_s),
                                     float(step + 1) * float(dt_s)],
                "receiver": receiver_array.copy(),
                "local_q_m3_s": terminal_field.reshape(shape).copy(),
                "valid_mask": valid_mask.copy(),
                "terminal_kind": terminal_kind.copy(),
                "upstream_unknown_mask": unknown.copy(),
                "known_routed_q_m3_s": ledger["known_routed_q_m3_s"].copy(),
                "complete_mask": ledger["complete_mask"].copy(),
                "terminal_q_m3_s": ledger["terminal_q_m3_s"].copy(),
            }
    instantaneous_interval = int(_m4_native_30m_runoff_np.argmax(instantaneous))

    # --- cross-checks: water budget, attribution, terminal isolation -------- #
    injected = float(routed["lateral_volume_m3"].sum())
    expected_injected = float(local_q.sum() * float(dt_s))
    injection_gap = injected - expected_injected
    if abs(injection_gap) > 1e-12 * max(1.0, expected_injected):
        raise ValueError(
            "routing_injection_mismatch: the reach router injected %.6e m3 but the "
            "soil bucket released %.6e m3" % (injected, expected_injected))
    outlet_gap = float(_m4_native_30m_runoff_np.abs(routed["outlet_q_m3_s"] - routed_q).max())
    if outlet_gap > 1e-12 * max(1.0, float(_m4_native_30m_runoff_np.abs(routed_q).max())):
        raise ValueError(
            "routing_injection_mismatch: a reach other than the terminal one "
            "discharges to the outlet, so outside-catchment water leaked in")
    bucket_outflow = float(bucket["outflow_volume_m3"].sum())
    diagnostic_retained_gap = float(_m4_native_30m_runoff_np.abs(retained - input_total).max())
    if diagnostic_retained_gap > 1e-12 * max(1.0, float(input_total.max(initial=0.0))):
        raise ValueError(
            "diagnostic_graph_rejected: the instantaneous accumulation lost water "
            "to other terminals or to an undeclared outflow")
    # Interval volume account, recomputed independently of the router's own
    # ledger: bucket release = terminal outlet volume + total storage change.
    # `outlet_q_m3_s` is a rate, so it is converted back to a volume here.
    global_residual = (local_q.sum(axis=1) * float(dt_s)
                       - routed["outlet_q_m3_s"] * float(dt_s)
                       - routed["storage_change_m3"].sum(axis=1))
    accumulated_storage = float(routed["storage_m3"][-1].sum())
    if float(_m4_native_30m_runoff_np.abs(global_residual).max(initial=0.0)) > 1e-12 * max(
        1.0, float(expected_injected)):
        raise ValueError(
            "routing_injection_mismatch: the interval volume account does not close "
            "(max |release - outlet - storage change| = %.6e m3)"
            % float(_m4_native_30m_runoff_np.abs(global_residual).max()))

    identity = {
        "algorithm": NATIVE_30M_RUNOFF_ALGORITHM,
        "schema": NATIVE_30M_RUNOFF_SCHEMA,
        "source": binding,
        "time_edges_s": [float(index) * float(dt_s) for index in range(intervals + 1)],
        "rain_mm_h_sha256": binding["rain_mm_h_sha256"],
        "local_q_m3_s_sha256": _array_sha256(local_q),
        "active_cells_sha256": _array_sha256(active.astype(_m4_native_30m_runoff_np.int64)),
        "routed_terminal_q_sha256": _array_sha256(routed_q),
        "instantaneous_terminal_q_sha256": _array_sha256(instantaneous),
        "terminal_reach": int(terminal_reach),
        "reach_parameter_sha256": routed["metadata"]["parameter_sha256"],
    }

    return {
        "algorithm": NATIVE_30M_RUNOFF_ALGORITHM,
        "schema": NATIVE_30M_RUNOFF_SCHEMA,
        "event_identity_sha256": _m4_native_30m_runoff_hashlib.sha256(
            _canonical(identity).encode("utf-8")).hexdigest(),
        "identity": identity,
        "source": dict(binding),
        "time": {
            "dt_s": float(dt_s),
            "intervals": intervals,
            "time_edges_s": _m4_native_30m_runoff_np.arange(intervals + 1, dtype=_m4_native_30m_runoff_np.float64) * float(dt_s),
            "rain_semantics": RAIN_SEMANTICS,
            "rain_scope": "uniform over every active catchment cell",
            "cell_order": NATIVE_30M_CELL_ORDER,
            "outside_catchment_scope": OUTSIDE_SCOPE,
        },
        "rain_mm_h": rain.copy(),
        "active_cells": active.astype(_m4_native_30m_runoff_np.int64),
        "active_cell_area_m2": cell_area,
        "local_q_m3_s": local_q.copy(),
        "instantaneous_terminal_q_m3_s": instantaneous,
        "routed_terminal_q_m3_s": routed_q.copy(),
        "design_q_m3_s": design_q,
        "design_q_interval_index": design_interval,
        "design_q_peak_time_s": float(design_interval + 1) * float(dt_s),
        "design_q_semantics": DESIGN_Q_SEMANTICS,
        "instantaneous_q_semantics": INSTANTANEOUS_Q_SEMANTICS,
        "instantaneous_peak_m3_s": float(instantaneous[instantaneous_interval]),
        "instantaneous_peak_interval_index": instantaneous_interval,
        "instantaneous_over_routed_peak_ratio": (
            float(instantaneous[instantaneous_interval] / design_q)
            if design_q > 0 else None),
        "event_design_q_not_bankfull": True,
        "terminal": {
            "flat_cell": int(terminal),
            "rc": [int(terminal // shape[1]), int(terminal % shape[1])],
            "native_xz": binding["terminal_native_xz"],
            "semantics": TERMINAL_SEMANTICS,
            "on_flowline": bool(line["mask"][terminal]),
            "reach": int(terminal_reach),
            "reach_length_m": float(routed["reach_length_m"][terminal_reach]),
            "reach_tau_s": float(routed["tau_s"][terminal_reach]),
            "catchment_cells": active_cells,
            "flowline_cells": line["cells"],
            "terminal_count_in_grid": int(outlet_mask.sum()),
        },
        "runoff": {
            "kernel": "terrain_pipeline.rainfall_runoff.simulate_rainfall_runoff",
            "source_id": bucket["metadata"]["source_id"],
            "parameters": _m4_native_30m_runoff_asdict(runoff_parameters),
            "parameter_sha256": bucket["metadata"]["parameter_sha256"],
            "q_semantics": bucket["metadata"]["q_semantics"],
            "rain_volume_m3": bucket["rain_volume_m3"].sum(axis=1),
            "et_volume_m3": bucket["et_volume_m3"].sum(axis=1),
            "outflow_volume_m3": bucket["outflow_volume_m3"].sum(axis=1),
            "storage_change_m3": bucket["storage_change_m3"].sum(axis=1),
            "balance_residual_m3": bucket["balance_residual_m3"].sum(axis=1),
            "terminal_storage_mm": {
                "soil_mm": float(bucket["soil_mm"][-1, 0]),
                "fast_mm": float(bucket["fast_mm"][-1, 0]),
                "slow_mm": float(bucket["slow_mm"][-1, 0]),
                "note": "every active cell is identical, so cell 0 is the whole state",
            },
            "total_outflow_volume_m3": bucket_outflow,
        },
        "routing": routed,
        "diagnostic": {
            "kernel": ("terrain_pipeline.surface_rivers.metric_network_accumulation"
                       ".accumulate_network_discharge"),
            "semantics": INSTANTANEOUS_Q_SEMANTICS,
            "terminal_label": DIAGNOSTIC_TERMINAL_LABEL,
            "input_total_m3_s": input_total,
            "retained_m3_s": retained,
            "open_outflow_m3_s": open_outflow,
            "unknown_pending_m3_s": unknown_pending,
            "residual_m3_s": residual,
            "peak_interval_index": design_interval,
            "peak_interval_payload": peak_payload,
            "payload_note": ("one declared interval only; no per-interval product "
                             "is retained here and no file is written"),
        },
        "checks": {
            "injected_volume_m3": injected,
            "bucket_local_volume_m3": expected_injected,
            "injection_gap_m3": float(injection_gap),
            "routing_outlet_gap_m3_s": float(outlet_gap),
            "routing_max_abs_reach_residual_m3": float(
                _m4_native_30m_runoff_np.abs(routed["balance_residual_m3"]).max()),
            "routing_max_abs_global_residual_m3": float(_m4_native_30m_runoff_np.abs(global_residual).max()),
            "diagnostic_max_abs_residual_m3_s": float(_m4_native_30m_runoff_np.abs(residual).max()),
            "diagnostic_retained_minus_input_m3_s": diagnostic_retained_gap,
            "non_terminal_terminal_q_sum_max_m3_s": float(other_terminal_peak),
            "hru_own_reach_fraction_deviation": float(_m4_native_30m_runoff_np.abs(own_fraction - 1.0).max()),
            "routed_peak_not_above_instantaneous_peak": bool(design_q <=
                                                            instantaneous.max()),
            "outside_catchment_local_q_max_m3_s": 0.0,
            "terminal_instantaneous_equals_bucket_total_max_m3_s": float(
                _m4_native_30m_runoff_np.abs(instantaneous - local_q.sum(axis=1)).max()),
        },
        "budget": {
            "rainfall_runoff": bucket_budget,
            "route": _route_budget(intervals, routing_cells, hrus,
                                   int(routed["tau_s"].size)),
            "diagnostic": diagnostic_budget,
            "hru_plan": {
                "catchment_cells": active_cells,
                "groups": groups,
                "outside_groups": outside_group,
                "total_hrus": hrus,
                "max_hrus": MAX_HRUS,
                "per_cell_hrus_possible": bool(active_cells <= MAX_HRUS),
                "attribution": ("one HRU per reach that owns at least one catchment "
                                "cell, so each HRU's area equals its cell count "
                                "times the cell area and its own-reach fraction is "
                                "exactly 1"),
            },
            "reach_count": int(routed["tau_s"].size),
            "max_reaches": MAX_REACHES,
            "max_route_steps": MOUNTAIN_ROUTING_MAX_STEPS,
        },
        "capabilities": {
            "natural_outlet_certified": False,
            "hydraulic_ready": False,
            "bankfull": False,
            "calibrated": False,
            "publishable": False,
            "bundle_written": False,
            "topology_window_invariance_verified": False,
            "finite_graph_only": True,
            "spatially_variable_forcing_supported": False,
        },
    }

# --- terrain_pipeline/surface_rivers/saved_graph_lowland.py:6 ---
def classify_saved_graph(height, land, receiver, upstream_order, contributing_cells, spacing_m, *, config=None):
    """Return channels and first downstream capture; all runoff stays on the saved DAG.

    Area is a unit-runoff proxy, not evidence of calibrated perennial discharge.
    The supplied order must be upstream first. No receiver is changed.
    """
    config = config or LowlandRunoffConfig()
    height = _m4_saved_graph_lowland_np.asarray(height)
    land = _m4_saved_graph_lowland_np.asarray(land, dtype=bool).ravel()
    receiver = _m4_saved_graph_lowland_np.asarray(receiver).ravel()
    order = _m4_saved_graph_lowland_np.asarray(upstream_order).ravel()
    area = _m4_saved_graph_lowland_np.asarray(contributing_cells).ravel()
    if height.ndim != 2 or any(a.size != height.size for a in (land, receiver, order, area)):
        raise ValueError('incompatible graph and terrain')
    relief, slope, lowland = lowland_geometry(height, spacing_m, config)
    threshold = _m4_saved_graph_lowland_np.where(lowland.ravel(), config.lowland_initiation_area_m2,
                         config.upland_initiation_area_m2)
    seeds = land & (area * float(spacing_m ** 2) >= threshold)
    channel = _close(seeds, receiver, order) & land
    owner, _ = _first_object(channel.astype(_m4_saved_graph_lowland_np.uint8), receiver, order)
    return dict(lowland=lowland, relief=relief, slope=slope,
                channel=channel, capture=owner)
