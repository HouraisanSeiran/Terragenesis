"""Sample diagnostic hydrology states and integrate interval-average release."""

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_product import SCHEMA as PRODUCT_SCHEMA, TERMINAL_TOTALS


SCHEMA = "terragenesis-river-diagnostic-output-v1"
MAX_BYTES = 1024 * 1024 * 1024
STATE_SEMANTICS = "initial_and_end_of_selected_forcing_intervals"
Q_SEMANTICS = "interval_average_local_release_volume_divided_by_elapsed_seconds_not_river_routed"
SOURCE_INTERVAL_SEMANTICS = "every_forcing_interval_integrated_before_sampling"
LEDGER_NAMES = ("rain_volume_m3", "et_volume_m3", "storage_change_m3",
                "balance_residual_m3", "local_release_volume_m3")
TERMINAL_NAMES = tuple(TERMINAL_TOTALS)


def _indices(values, steps):
    indices = np.asarray(values)
    if (indices.ndim != 1 or indices.dtype.kind not in "iu" or indices.size < 2
            or indices[0] != 0 or indices[-1] != steps
            or np.any(indices[1:] <= indices[:-1])):
        raise ValueError("state_indices must be strictly increasing integers including 0 and T")
    return indices.astype(np.int64, copy=True)


def sample_diagnostic_output(product, state_indices, *, product_sha256=None):
    """Aggregate every native forcing interval between selected state indices."""
    source_arrays, source_meta = product["arrays"], product["metadata"]
    if (source_meta.get("schema") != PRODUCT_SCHEMA or source_meta.get("status") != "diagnostic_runoff"
            or any(source_meta.get(key) is not False for key in
                   ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or product["identity_sha256"] != identity(source_arrays, source_meta)):
        raise ValueError("v1 diagnostic product required")
    if product_sha256 is not None and (not isinstance(product_sha256, str)
                                      or len(product_sha256) != 64
                                      or any(char not in "0123456789abcdef" for char in product_sha256)):
        raise ValueError("external product SHA256 required")
    source_times = source_arrays["time_seconds"]
    steps = len(source_times) - 1
    indices = _indices(state_indices, steps)
    valid_ids = source_arrays["valid_cell_ids"]
    shape = source_arrays["elevation_m"].shape
    duration = np.diff(source_times[indices])
    if (np.any(duration <= 0.) or np.any(np.diff(source_times) != np.diff(source_times)[0])):
        raise ValueError("positive fixed source hydrology intervals required")
    arrays = {"state_indices": indices, "state_time_seconds": source_times[indices].copy(),
              "source_time_seconds": source_times,
              "interval_seconds": duration.astype(np.float64),
              "valid_cell_ids": valid_ids}
    for key in ("soil_mm", "fast_mm", "slow_mm"):
        arrays[key] = source_arrays["runoff_" + key][indices].copy()
    groups = len(indices) - 1
    q = np.zeros((groups,) + shape, dtype=np.float64)
    ledger = {key: np.zeros(groups, dtype=np.float64) for key in LEDGER_NAMES}
    terminals = {name: np.zeros(groups, dtype=np.float64) for name in TERMINAL_NAMES}
    for output_step, (start, stop) in enumerate(zip(indices[:-1], indices[1:])):
        volume_cells = np.sum(source_arrays["runoff_outflow_volume_m3"][start:stop],
                              axis=0, dtype=np.float64)
        q[output_step].ravel()[valid_ids] = volume_cells / duration[output_step]
        for key, source_key in (("rain_volume_m3", "rain_volume_m3"),
                                ("et_volume_m3", "et_volume_m3"),
                                ("storage_change_m3", "storage_change_m3"),
                                ("balance_residual_m3", "balance_residual_m3"),
                                ("local_release_volume_m3", "outflow_volume_m3")):
            ledger[key][output_step] = float(np.sum(source_arrays["runoff_" + source_key][start:stop],
                                                     dtype=np.float64))
        for name in TERMINAL_NAMES:
            terminals[name][output_step] = float(np.sum(source_arrays[name + "_volume_interval_m3"][start:stop],
                                                       dtype=np.float64))
    arrays["local_q_m3_s"] = q
    arrays.update(ledger)
    arrays.update({name + "_volume_m3": value for name, value in terminals.items()})
    arrays["cumulative_local_release_m3"] = np.r_[0., np.cumsum(ledger["local_release_volume_m3"])]
    for name, values in terminals.items():
        arrays["cumulative_" + name + "_m3"] = np.r_[0., np.cumsum(values)]
    metadata = {"schema": SCHEMA, "status": "diagnostic_output",
                "source_product_identity_sha256": product["identity_sha256"],
                "source_product_sha256": product_sha256,
                "source_water_budget_m3": source_meta["water_budget_m3"],
                "cell_area_m2": float(source_arrays["runoff_area_m2"][0]),
                "grid_shape_zx": list(shape),
                "source_solver_dt_seconds": float(np.diff(source_times)[0]),
                "state_semantics": STATE_SEMANTICS,
                "q_semantics": Q_SEMANTICS,
                "source_interval_semantics": SOURCE_INTERVAL_SEMANTICS,
                "hydraulic_ready": False, "natural_outlet_verified": False,
                "publishable": False}
    arrays = {key: readonly(value) for key, value in arrays.items()}
    sampled = {"arrays": arrays, "metadata": metadata,
               "identity_sha256": identity(arrays, metadata)}
    validate_diagnostic_output(sampled)
    return sampled


def validate_diagnostic_output(sampled):
    arrays, meta = sampled["arrays"], sampled["metadata"]
    expected = {"state_indices", "state_time_seconds", "source_time_seconds", "interval_seconds", "valid_cell_ids",
                "soil_mm", "fast_mm", "slow_mm", "local_q_m3_s", "cumulative_local_release_m3"}
    expected.update(LEDGER_NAMES)
    expected.update(name + "_volume_m3" for name in TERMINAL_NAMES)
    expected.update("cumulative_" + name + "_m3" for name in TERMINAL_NAMES)
    if (set(arrays) != expected or set(meta) != {"schema", "status", "source_product_identity_sha256",
            "source_product_sha256", "source_water_budget_m3", "cell_area_m2", "grid_shape_zx",
            "source_solver_dt_seconds", "state_semantics", "q_semantics", "source_interval_semantics",
            "hydraulic_ready", "natural_outlet_verified", "publishable"}
            or meta.get("schema") != SCHEMA
            or meta.get("status") != "diagnostic_output"
            or meta.get("state_semantics") != STATE_SEMANTICS
            or meta.get("q_semantics") != Q_SEMANTICS
            or meta.get("source_interval_semantics") != SOURCE_INTERVAL_SEMANTICS
            or any(meta.get(key) is not False for key in
                   ("hydraulic_ready", "natural_outlet_verified", "publishable"))
            or sampled["identity_sha256"] != identity(arrays, meta)):
        raise ValueError("diagnostic output schema/identity mismatch")
    for key in ("source_product_identity_sha256", "source_product_sha256"):
        value = meta[key]
        if value is None and key == "source_product_sha256":
            continue
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("invalid source product identity")
    indices = arrays["state_indices"]
    times = arrays["state_time_seconds"]
    source_times = arrays["source_time_seconds"]
    dt = arrays["interval_seconds"]
    if (source_times.dtype != np.float64 or source_times.ndim != 1 or not 2 <= source_times.size <= 100001
            or not np.isfinite(source_times).all() or source_times[0] < 0.
            or np.any(np.diff(source_times) <= 0.)
            or np.any(np.diff(source_times) != np.diff(source_times)[0])
            or meta["source_solver_dt_seconds"] != float(np.diff(source_times)[0])
            or indices.dtype != np.int64 or indices.ndim != 1 or indices.size < 2 or indices[0] != 0
            or indices[-1] != source_times.size - 1
            or np.any(indices[1:] <= indices[:-1]) or times.dtype != np.float64
            or times.shape != indices.shape or not np.isfinite(times).all()
            or np.any(times[1:] <= times[:-1]) or dt.dtype != np.float64
            or dt.shape != (indices.size - 1,) or not np.array_equal(dt, np.diff(times))
            or not np.array_equal(times, source_times[indices])):
        raise ValueError("invalid sampled physical times")
    shape = meta["grid_shape_zx"]
    if (not isinstance(shape, list) or len(shape) != 2 or
            any(type(value) is not int or not 1 <= value <= 1024 for value in shape)):
        raise ValueError("invalid sampled grid shape")
    rows, columns = shape
    cells = rows * columns
    valid_ids = arrays["valid_cell_ids"]
    if (not 1 <= cells <= 1024 * 1024 or valid_ids.dtype != np.int64 or valid_ids.ndim != 1
            or valid_ids.size == 0 or valid_ids[0] < 0 or valid_ids[-1] >= cells
            or np.any(valid_ids[1:] <= valid_ids[:-1])
            or not np.isfinite(meta["cell_area_m2"]) or not 0. < meta["cell_area_m2"] <= 1e12):
        raise ValueError("invalid sampled cell census")
    state_shape = (indices.size, valid_ids.size)
    for key in ("soil_mm", "fast_mm", "slow_mm"):
        value = arrays[key]
        if value.dtype != np.float64 or value.shape != state_shape or not np.isfinite(value).all() or np.any(value < 0.):
            raise ValueError("invalid sampled state: " + key)
    q = arrays["local_q_m3_s"]
    if (q.dtype != np.float64 or q.shape != (dt.size, rows, columns)
            or not np.isfinite(q).all() or np.any(q < 0.)):
        raise ValueError("invalid sampled local Q")
    if np.any(q.reshape(dt.size, -1)[:, np.setdiff1d(np.arange(cells), valid_ids)] != 0.):
        raise ValueError("sampled Q crosses unknown cells")
    for key in LEDGER_NAMES + tuple(name + "_volume_m3" for name in TERMINAL_NAMES):
        value = arrays[key]
        if (value.dtype != np.float64 or value.shape != (dt.size,)
                or not np.isfinite(value).all()):
            raise ValueError("invalid sampled ledger: " + key)
        if key not in ("storage_change_m3", "balance_residual_m3") and np.any(value < 0.):
            raise ValueError("negative sampled ledger: " + key)
    area = meta["cell_area_m2"] / 1000.
    total_storage = sum(np.sum(arrays[key], axis=1, dtype=np.float64) for key in ("soil_mm", "fast_mm", "slow_mm")) * area
    if not np.allclose(arrays["storage_change_m3"], np.diff(total_storage), rtol=1e-10, atol=1e-8):
        raise ValueError("sampled storage change mismatch")
    release = np.sum(q, axis=(1, 2), dtype=np.float64) * dt
    if not np.allclose(release, arrays["local_release_volume_m3"], rtol=1e-10, atol=1e-8):
        raise ValueError("sampled local release mismatch")
    terminal_total = sum(arrays[name + "_volume_m3"] for name in TERMINAL_NAMES)
    if not np.allclose(terminal_total, arrays["local_release_volume_m3"], rtol=1e-10, atol=1e-8):
        raise ValueError("sampled terminal volume mismatch")
    residual = (arrays["rain_volume_m3"] - arrays["et_volume_m3"]
                - arrays["storage_change_m3"] - arrays["local_release_volume_m3"])
    if not np.allclose(residual, arrays["balance_residual_m3"], rtol=1e-10, atol=1e-8):
        raise ValueError("sampled hydrology balance mismatch")
    scale = np.maximum(1., arrays["rain_volume_m3"] + arrays["et_volume_m3"]
                       + arrays["local_release_volume_m3"] + np.abs(arrays["storage_change_m3"]))
    if np.any(np.abs(arrays["balance_residual_m3"]) > 1e-10 * scale):
        raise ValueError("sampled hydrology residual exceeds tolerance")
    for cumulative, intervals in (("cumulative_local_release_m3", arrays["local_release_volume_m3"]),
                                  *(("cumulative_" + name + "_m3", arrays[name + "_volume_m3"])
                                    for name in TERMINAL_NAMES)):
        expected_cumulative = np.r_[0., np.cumsum(intervals)]
        if not np.allclose(arrays[cumulative], expected_cumulative, rtol=1e-12, atol=1e-10):
            raise ValueError("sampled cumulative ledger mismatch: " + cumulative)
    budget = meta["source_water_budget_m3"]
    budget_keys = {"rain_input", "evapotranspiration", "hydrology_storage_change",
                   "local_release", "combined_residual", *TERMINAL_NAMES}
    if (not isinstance(budget, dict) or set(budget) != budget_keys
            or any(type(value) not in (int, float) or not np.isfinite(value)
                   for value in budget.values())):
        raise ValueError("invalid source global budget")
    if (any(budget[name] < 0. for name in ("rain_input", "evapotranspiration", "local_release", *TERMINAL_NAMES))
            or abs(budget["combined_residual"] -
                   (budget["rain_input"] - budget["evapotranspiration"]
                    - budget["hydrology_storage_change"]
                    - sum(budget[name] for name in TERMINAL_NAMES))) >
            1e-10 * max(1., budget["rain_input"], abs(budget["hydrology_storage_change"]))
            or abs(budget["combined_residual"]) >
            1e-10 * max(1., budget["rain_input"], abs(budget["hydrology_storage_change"]))):
        raise ValueError("source global budget balance mismatch")
    for output_key, source_key in (("rain_volume_m3", "rain_input"),
                                   ("et_volume_m3", "evapotranspiration"),
                                   ("storage_change_m3", "hydrology_storage_change"),
                                   ("local_release_volume_m3", "local_release"),
                                   *((name + "_volume_m3", name) for name in TERMINAL_NAMES)):
        if not np.isclose(np.sum(arrays[output_key], dtype=np.float64), budget[source_key], rtol=1e-10, atol=1e-8):
            raise ValueError("sampled global ledger mismatch: " + output_key)
    return True


def save_diagnostic_output(path, sampled):
    save_bundle(path, sampled, validator=validate_diagnostic_output)


def load_diagnostic_output(path, *, expected_sha256, expected_identity,
                           expected_product_identity, expected_product_sha256=None):
    sampled = load_bundle(path, expected_sha256=expected_sha256,
                          validator=validate_diagnostic_output, max_bytes=MAX_BYTES)
    if (sampled["identity_sha256"] != expected_identity
            or sampled["metadata"]["source_product_identity_sha256"] != expected_product_identity
            or sampled["metadata"]["source_product_sha256"] != expected_product_sha256):
        raise ValueError("external output or source-product identity mismatch")
    return sampled
