"""Prepared same-world G3/G4 climate on one fixed, bounded 30 m domain.

Terrain is pinned only during preparation. Subsequent steps consume saved monthly
temperature and ridge gradients, preserve vapour kg, and declare external moisture.
Subwindow queries crop a completed fixed-domain result, never invent new boundaries.
"""

from pathlib import Path
import json
import math

import numpy as np

from terrain_pipeline.common_infra import (
    checked_archive,
    file_sha256,
    identity,
    load_bundle,
    readonly,
    save_bundle,
)
from terrain_pipeline.climate_transport import depth_mm, transport_step
from terrain_pipeline.environment_seasonal_air import (
    MAX_TIME_S, _interval_mean_monthly, _validate_time_edges, calendar, sample_seasonal_air,
)
from terrain_pipeline.surface_rivers.metric_climate_refinement import (
    RefinedClimateParameters, latitude_norm, ridge_height, wind_unit,
)


DRIVER_SCHEMA = "environment-climate-driver-v1"
STATE_SCHEMA = "environment-climate-state-v1"
MAX_CELLS = 4096
MAX_SUBSTEPS = 100_000
SPACING_M = 30.0
DRIVER_FIELDS = {
    "x_m", "z_m", "elevation_m", "ridge_height_m", "upwind_ridge_height_m",
    "orographic_gradient", "wind_bearing_x", "wind_bearing_z", "monthly_temperature_c",
}


def _bundle(arrays, metadata):
    return {"arrays": {name: readonly(value) for name, value in arrays.items()},
            "metadata": metadata, "identity_sha256": identity(arrays, metadata)}


def _shape(shape):
    if (not isinstance(shape, (list, tuple)) or len(shape) != 2 or
            any(type(side) is not int or side < 1 for side in shape) or
            math.prod(shape) > MAX_CELLS):
        raise ValueError("climate domain must contain 1..4096 cells in a 2D grid")
    return tuple(shape)


def _mass(value, shape, name):
    value = np.broadcast_to(np.asarray(value, np.float64), shape).copy()
    if not np.isfinite(value).all() or np.any(value < 0.):
        raise ValueError("finite nonnegative %s required" % name)
    return value


def _time(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_TIME_S:
        raise ValueError("bounded nonnegative physical time_s required")
    return float(value)


def _saved_terrain_support(store, bounds):
    """Read only saved TD tiles intersecting the exact original ridge support."""
    store = Path(store)
    registry_path = store / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry["world"]["layout"]["world_seed"] != 20261020:
        raise ValueError("fixed world seed20261020 required")
    left, top, right, bottom = bounds
    component = next((item for item in registry["components"]
                      if item["bounds"][0] <= left and item["bounds"][1] <= top and
                      item["bounds"][2] >= right and item["bounds"][3] >= bottom), None)
    if component is None:
        raise ValueError("actual saved terrain does not cover the original 15km ridge support")
    root = store / "versions" / component["version"]
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.pop("identity_sha256")
    if (expected != component["identity_sha256"] or identity({}, manifest) != expected or
            manifest["world_identity"] != registry["world_identity"]):
        raise ValueError("saved terrain manifest identity mismatch")
    height = np.empty((bottom - top, right - left), np.float64)
    covered = np.zeros(height.shape, bool)
    records = []
    for tile in manifest["composition_tiles"]:
        tx, tz = tile["origin_native_xz"]
        rows, cols = tile["shape_zx"]
        x0, z0, x1, z1 = max(left, tx), max(top, tz), min(right, tx + cols), min(bottom, tz + rows)
        if x0 >= x1 or z0 >= z1:
            continue
        path = root / tile["file"]
        data = checked_archive(path, expected_sha256=tile["sha256"])
        src = np.s_[z0 - tz:z1 - tz, x0 - tx:x1 - tx]
        dst = np.s_[z0 - top:z1 - top, x0 - left:x1 - left]
        if not data["valid_mask"][src].all():
            raise ValueError("unresolved saved TD ridge support")
        height[dst] = data["composed_elevation_m"][src]
        covered[dst] = True
        records.append({"path": str(path.resolve()), "sha256": tile["sha256"]})
    if not covered.all() or not np.isfinite(height).all():
        raise ValueError("actual saved TD ridge support has missing or nonfinite cells")
    source = {"registry_path": str(registry_path.resolve()), "registry_sha256": file_sha256(registry_path),
              "manifest_sha256": file_sha256(manifest_path), "world_identity": registry["world_identity"],
              "component_identity_sha256": expected, "tiles": records, "source_pages": registry["pages"],
              "height_field": "saved composed_elevation_m; generated TD-derived bed, equals network node_raw_bed_m",
              "support_bounds_native_xz_exclusive": list(bounds)}

    def sample(x_m, z_m):
        x, z = np.broadcast_arrays(np.asarray(x_m, np.float64), np.asarray(z_m, np.float64))
        ix, iz = x / SPACING_M, z / SPACING_M
        if (not np.isfinite(x).all() or not np.isfinite(z).all() or
                np.any(ix != np.rint(ix)) or np.any(iz != np.rint(iz)) or
                np.any(ix < left) or np.any(ix >= right) or np.any(iz < top) or np.any(iz >= bottom)):
            raise ValueError("ridge query outside actual prepared TD support or off native grid")
        return height[iz.astype(np.int64) - top, ix.astype(np.int64) - left]
    return sample, source


def build_climate_driver(store, origin_native_xz=(43700, 42100), shape_zx=(64, 64)):
    """Pin real terrain once, using the unmodified 15 km / three-tap G3/G4 rules."""
    shape = _shape(shape_zx)
    if len(origin_native_xz) != 2 or any(type(value) is not int for value in origin_native_xz):
        raise ValueError("integer native origin pair required")
    cols, rows = np.meshgrid(np.arange(shape[1]), np.arange(shape[0]))
    x = (origin_native_xz[0] + cols) * SPACING_M
    z = (origin_native_xz[1] + rows) * SPACING_M
    parameters = RefinedClimateParameters()
    bearings = {wind_unit(float(value)) for value in np.asarray(latitude_norm(20261020, z)).ravel()}
    if len(bearings) != 1:
        raise ValueError("fixed climate domain crosses the original constant-wind band")
    wind = bearings.pop()
    taps = parameters.ridge_offsets_m
    scale = parameters.orographic_scale_m
    bounds = (int((x.min() + min(taps) + min(0., -wind[0] * scale)) / SPACING_M),
              int((z.min() + min(taps) + min(0., -wind[1] * scale)) / SPACING_M),
              int((x.max() + max(taps) + max(0., -wind[0] * scale)) / SPACING_M) + 1,
              int((z.max() + max(taps) + max(0., -wind[1] * scale)) / SPACING_M) + 1)
    sampler, source = _saved_terrain_support(store, bounds)
    elevation = sampler(x, z)
    air = sample_seasonal_air(20261020, x, z, elevation_m=elevation, elevation_sampler=sampler)
    here = ridge_height(20261020, x, z, parameters=parameters, elevation_sampler=sampler)
    upwind = ridge_height(20261020, x - wind[0] * scale, z - wind[1] * scale,
                          parameters=parameters, elevation_sampler=sampler)
    arrays = {"x_m": x, "z_m": z, "elevation_m": elevation, "ridge_height_m": here,
              "upwind_ridge_height_m": upwind, "orographic_gradient": (here - upwind) / scale,
              "monthly_temperature_c": air["monthly_temperature_c"],
              "wind_bearing_x": air["wind_bearing_x"], "wind_bearing_z": air["wind_bearing_z"]}
    metadata = {"schema": DRIVER_SCHEMA, "world_seed": 20261020, "origin_native_xz": list(origin_native_xz),
                "shape_zx": list(shape), "spacing_m": SPACING_M, "source": source,
                "calendar": calendar(), "air_identity_sha256": air["identity"]["identity_sha256"],
                "air_code_identities": air["code_identities"], "wind_bearing": list(wind),
                "orographic_scale_m": scale, "ridge_offsets_m": list(taps),
                "parameter_identity_sha256": parameters.identity_sha256,
                "random_streams": {"world_seed": 20261020,
                    "method": "original geographic_noise.field(seed,salt); octave salt increment811",
                    "thermal_salt": 1401, "moisture_salt": 1503,
                    "continentality_salt": 1607, "seasonal_phase_salt": 1709,
                    "new_driver_random_process": False},
                "code_sha256": {name: file_sha256(Path(__file__).with_name(name)) for name in (
                    "environment_climate_driver.py", "climate_transport.py")},
                "wind_semantics": "original G3 synthetic band axial direction; speed is separate declared m/s",
                "boundary_semantics": "fixed full-domain upstream external kg/s per face; open downstream export",
                "recycle_semantics": "caller owns previous-macrostep ET; supplied kg recycled once over next interval",
                "precipitation_semantics": "G4 finite vapour condensation, not the v2 climatological rain multiplier",
                "time_semantics": "physical seconds, G3 fixed365 monthly calendar; no Minecraft tick or wall clock"}
    result = _bundle(arrays, metadata)
    validate_climate_driver(result)
    return result


def validate_climate_driver(driver):
    arrays, metadata = driver["arrays"], driver["metadata"]
    shape = _shape(metadata["shape_zx"])
    if (metadata["schema"] != DRIVER_SCHEMA or metadata["world_seed"] != 20261020 or
            metadata["spacing_m"] != SPACING_M or metadata["calendar"] != calendar() or
            metadata["orographic_scale_m"] != 15000. or metadata["ridge_offsets_m"] != [-7500., 0., 7500.] or
            set(arrays) != DRIVER_FIELDS):
        raise ValueError("climate driver schema or original climate parameters mismatch")
    for name, array in arrays.items():
        expected = (12,) + shape if name == "monthly_temperature_c" else shape
        if array.shape != expected or array.dtype.kind not in "fiu" or not np.isfinite(array).all():
            raise ValueError("invalid prepared climate field: " + name)
    rows, cols = np.indices(shape)
    origin = metadata["origin_native_xz"]
    if (not np.array_equal(arrays["x_m"], (origin[0] + cols) * SPACING_M) or
            not np.array_equal(arrays["z_m"], (origin[1] + rows) * SPACING_M) or
            not np.all(arrays["wind_bearing_x"] == metadata["wind_bearing"][0]) or
            not np.all(arrays["wind_bearing_z"] == metadata["wind_bearing"][1]) or
            tuple(metadata["wind_bearing"]) not in ((-1, 0), (1, 0)) or
            not np.array_equal(arrays["orographic_gradient"],
                               (arrays["ridge_height_m"] - arrays["upwind_ridge_height_m"]) / 15000.)):
        raise ValueError("prepared climate geometry or original axial wind mismatch")
    if driver["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("climate driver identity mismatch")
    return True


def initial_climate_state(driver, *, time_s=0., vapour_kg=0.):
    validate_climate_driver(driver)
    return _bundle({"vapour_kg": _mass(vapour_kg, tuple(driver["metadata"]["shape_zx"]), "vapour kg")},
                   {"schema": STATE_SCHEMA, "driver_identity_sha256": driver["identity_sha256"],
                    "shape_zx": driver["metadata"]["shape_zx"], "time_s": _time(time_s)})


def validate_climate_state(state, driver=None):
    arrays, metadata = state["arrays"], state["metadata"]
    shape = _shape(metadata["shape_zx"])
    if metadata["schema"] != STATE_SCHEMA or set(arrays) != {"vapour_kg"}:
        raise ValueError("climate state schema mismatch")
    _time(metadata["time_s"])
    if arrays["vapour_kg"].shape != shape or arrays["vapour_kg"].dtype != np.dtype("float64"):
        raise ValueError("climate state shape mismatch")
    _mass(arrays["vapour_kg"], shape, "vapour kg")
    if state["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("climate state identity mismatch")
    if driver is not None and (metadata["driver_identity_sha256"] != driver["identity_sha256"] or
                               list(shape) != driver["metadata"]["shape_zx"]):
        raise ValueError("climate state belongs to another fixed driver")
    return True


def advance_climate_driver(driver, state, end_time_s, *, external_inflow_kg_per_s,
                           wind_speed_m_s, uplift_gain, et_recycle_kg=None):
    """Advance persistent vapour with CFL substeps and explicit per-upstream-face kg/s.

    ET belongs to the caller's previous macrostep, supplied once as kg per cell.
    It is distributed uniformly over this interval; this driver has no pending ET.
    """
    validate_climate_driver(driver)
    validate_climate_state(state, driver)
    start, end = state["metadata"]["time_s"], _time(end_time_s)
    shape = tuple(driver["metadata"]["shape_zx"])
    _validate_time_edges([start, end], math.prod(shape))
    for name, value in (("wind_speed_m_s", wind_speed_m_s), ("uplift_gain", uplift_gain)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("finite nonnegative " + name + " required")
    duration = end - start
    substeps = max(1, math.ceil(wind_speed_m_s * duration / SPACING_M))
    if substeps > MAX_SUBSTEPS:
        raise ValueError("climate CFL substep budget exceeded")
    dt = duration / substeps
    wind = tuple(driver["metadata"]["wind_bearing"])
    faces = shape[0] if wind[0] else shape[1]
    rate = _mass(external_inflow_kg_per_s, (faces,), "upstream external kg/s per face")
    recycle = _mass(0. if et_recycle_kg is None else et_recycle_kg, shape, "previous-step ET kg")
    vapour = state["arrays"]["vapour_kg"]
    precipitation = np.zeros(shape, np.float64)
    ledger = dict.fromkeys(("inflow_kg", "recycle_kg", "precipitation_kg", "outflow_kg", "nondepositing_kg"), 0.)
    for _index in range(substeps):
        step = transport_step(vapour, wind_bearing=wind, wind_speed_m_s=wind_speed_m_s, dt_s=dt,
                              uplift_gain=uplift_gain, gradient=driver["arrays"]["orographic_gradient"],
                              inflow_kg=rate * dt, recycle_kg=recycle / substeps)
        if not step["ledger"]["closure_ok"] or not step["boundary"]["certified"]:
            raise ValueError("uncertified climate substep")
        vapour = step["vapour_kg"]
        precipitation += step["precipitation_kg"]
        for name in ledger:
            ledger[name] += step["ledger"][name]
    ledger["storage_change_kg"] = float(vapour.sum() - state["arrays"]["vapour_kg"].sum())
    ledger["closure_residual_kg"] = (ledger["inflow_kg"] + ledger["recycle_kg"] -
                                     ledger["precipitation_kg"] - ledger["outflow_kg"] -
                                     ledger["nondepositing_kg"] - ledger["storage_change_kg"])
    ledger["closure_tolerance_kg"] = 1e-9 * max(ledger["inflow_kg"] + ledger["recycle_kg"],
                                             ledger["precipitation_kg"], ledger["outflow_kg"], 1.)
    ledger["closure_ok"] = abs(ledger["closure_residual_kg"]) <= ledger["closure_tolerance_kg"]
    if not ledger["closure_ok"]:
        raise ValueError("aggregate climate moisture ledger does not close")
    ledger["substeps"] = substeps
    ledger["max_cfl"] = wind_speed_m_s * dt / SPACING_M
    temperature = _interval_mean_monthly(driver["arrays"]["monthly_temperature_c"].reshape(12, -1),
                                         start, end).reshape(shape)
    new_state = _bundle({"vapour_kg": vapour}, dict(state["metadata"], time_s=end))
    forcing = {"precipitation_mm": depth_mm(precipitation),
               "rainfall_m_s": depth_mm(precipitation) / 1000. / duration,
               "air_temperature_c": temperature, "ledger": ledger,
               "seasonal_source": {"driver_identity_sha256": driver["identity_sha256"],
                                   "state_before_identity_sha256": state["identity_sha256"],
                                   "state_after_identity_sha256": new_state["identity_sha256"],
                                   "time_edges_s": [start, end], "wind_bearing": list(wind),
                                   "wind_speed_m_s": wind_speed_m_s, "uplift_gain": uplift_gain,
                                   "external_inflow_kg_per_s_per_face": rate.tolist(),
                                   "recycle_semantics": driver["metadata"]["recycle_semantics"]}}
    return new_state, forcing


def crop_climate_result(forcing, *, row, col, shape_zx):
    """Query an already calculated fixed-domain result; preserve its full-domain ledger."""
    shape = _shape(shape_zx)
    full = forcing["precipitation_mm"].shape
    if (type(row) is not int or type(col) is not int or min(row, col) < 0 or
            row + shape[0] > full[0] or col + shape[1] > full[1]):
        raise ValueError("climate crop outside calculated fixed domain")
    result = dict(forcing)
    for name in ("precipitation_mm", "rainfall_m_s", "air_temperature_c"):
        result[name] = readonly(forcing[name][row:row + shape[0], col:col + shape[1]])
    result["query"] = {"row": row, "col": col, "shape_zx": list(shape),
                       "ledger_scope": "unchanged full fixed calculation domain"}
    return result


def save_climate_driver(path, driver):
    save_bundle(path, driver, validator=validate_climate_driver)


def _driver_headers(headers):
    if set(headers) != DRIVER_FIELDS | {"manifest"}:
        raise ValueError("climate driver archive fields mismatch")
    shape = _shape(list(headers["elevation_m"][0]))
    for name in DRIVER_FIELDS:
        expected = (12,) + shape if name == "monthly_temperature_c" else shape
        if headers[name][0] != expected or headers[name][1].kind not in "fiu":
            raise ValueError("climate driver allocation shape/dtype mismatch")


def load_climate_driver(path, *, expected_sha256):
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_climate_driver,
                       header_validator=_driver_headers)


def save_climate_state(path, state):
    save_bundle(path, state, validator=validate_climate_state)


def load_climate_state(path, *, expected_sha256):
    def headers(record):
        if set(record) != {"vapour_kg", "manifest"}:
            raise ValueError("climate state archive fields mismatch")
        _shape(list(record["vapour_kg"][0]))
        if record["vapour_kg"][1] != np.dtype("float64"):
            raise ValueError("climate state allocation dtype mismatch")
    return load_bundle(path, expected_sha256=expected_sha256, validator=validate_climate_state,
                       header_validator=headers)
