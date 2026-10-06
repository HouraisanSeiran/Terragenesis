"""Bounded native-cell moving weather, without hydrological advancement."""

from dataclasses import asdict
import math
import re

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from terrain_pipeline.mountain_storm_forcing import StormParameters, interval_mean_mm_h
from terrain_pipeline.td_basin_source import load_td_source_bundle

SCHEMA = "td-native-moving-storm-v1"
MAX_BYTES = 128 * 1024 * 1024
MAX_SAMPLES = 4_000_000
MAX_EVALUATIONS = 50_000_000
SOURCE_RECORD = {
    "path": "verification/td-basin-generation/A-20261001T184113155960Z/source.npz",
    "expected_sha256": "d09d2df4df86423547f5aa8e04efa14e98a285b0873124dd82982040434f7697",
    "expected_identity": "8600fde239cc5b8d83a0f66c0eaa7974e2f68badc14dee341a9656d6911f199c",
}


def preflight(shape, steps, spatial_subsamples):
    if (len(shape) != 2 or any(type(size) is not int or size < 1 for size in shape) or
            type(steps) is not int or steps < 1 or type(spatial_subsamples) is not int or
            spatial_subsamples not in (1, 2, 4)):
        raise ValueError("invalid bounded dimensions/subsampling")
    cells = math.prod(shape)
    samples = cells * steps
    evaluations = samples * spatial_subsamples ** 2
    workspace = 40 * samples + 256 * cells + 65536
    if cells > 250000 or samples > MAX_SAMPLES or evaluations > MAX_EVALUATIONS or workspace > MAX_BYTES:
        raise ValueError("native storm preallocation resource budget exceeded")
    return dict(samples=samples, evaluations=evaluations, workspace_bytes=workspace)


def _sha(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("external SHA256/identity required")
    return value


def _source(record):
    if not isinstance(record, dict) or set(record) != {"path", "expected_sha256", "expected_identity"}:
        raise ValueError("source external dual-pin record required")
    _sha(record["expected_sha256"])
    _sha(record["expected_identity"])
    return load_td_source_bundle(**record)


def fixed_storm(source, direction):
    if direction not in ("eastward", "westward"):
        raise ValueError("unknown moving storm direction")
    spacing = source["metadata"]["spacing_m"]
    rows, columns = source["arrays"]["height_m"].shape
    origin_x, origin_z = source["metadata"]["origin_m_xz"]
    span = max(spacing, (columns - 1) * spacing)
    center_x = origin_x if direction == "eastward" else origin_x + (columns - 1) * spacing
    velocity = span / 21600 if direction == "eastward" else -span / 21600
    return StormParameters(center_x, origin_z + (rows - 1) * spacing / 2,
                           velocity, 0., max(1., span / 4), 30., 0., 21600.)


def _plan(source, source_record, parameters, steps, dt_s, start_s, spatial_subsamples, window):
    shape = source["arrays"]["height_m"].shape
    if window is None:
        window = [0, shape[0], 0, shape[1]]
    if (not isinstance(window, (list, tuple)) or len(window) != 4 or
            any(type(value) is not int for value in window) or
            not 0 <= window[0] < window[1] <= shape[0] or not 0 <= window[2] < window[3] <= shape[1]):
        raise ValueError("invalid source-index window")
    resources = preflight((window[1] - window[0], window[3] - window[2]), steps, spatial_subsamples)
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in (dt_s, start_s)) or
            not 1e-3 <= dt_s <= 1e7 or start_s < 0 or start_s + steps * dt_s > 1e9):
        raise ValueError("invalid physical time coverage")
    if not isinstance(parameters, StormParameters):
        raise ValueError("StormParameters required")
    parameters.__post_init__()
    metadata = dict(schema=SCHEMA, source_sha256=source_record["expected_sha256"],
        source_identity=source_record["expected_identity"], source_shape=list(shape),
        origin_m_xz=source["metadata"]["origin_m_xz"], spacing_m=source["metadata"]["spacing_m"],
        window=list(window), parameters=asdict(parameters), steps=steps, dt_s=float(dt_s), start_s=float(start_s),
        spatial_subsamples=spatial_subsamples, resources=resources,
        coordinates="x east, z south; source cell centers; rain [time,z,x]",
        spatial_integration="equal_area_midpoint_subcells_no_window_normalization",
        temporal_integration="mountain_storm_forcing.interval_mean_mm_h",
        unknown_policy="zero", protection_policy="preserved_not_hydrology_permission",
        water_solved=False, hydraulic_ready=False, publishable=False,
        status="parameterized_weather_scenario_not_forecast")
    return metadata


def _volumes(rain, spacing, dt_s):
    factor = dt_s / 3600 * spacing ** 2 / 1000
    return np.array([math.fsum(float(value) * factor for value in frame.flat) for frame in rain], np.float64)


def generate_native_storm(source_record, *, parameters, steps=24, dt_s=3600., start_s=0.,
                          spatial_subsamples=2, window=None):
    source = _source(source_record)
    plan = _plan(source, source_record, parameters, steps, dt_s, start_s, spatial_subsamples, window)
    row0, row1, col0, col1 = plan["window"]
    valid = source["arrays"]["valid_mask"][row0:row1, col0:col1]
    protected = source["arrays"]["protected_mask"][row0:row1, col0:col1]
    rain = np.zeros((steps, *valid.shape), np.float64)
    offsets = (np.arange(spatial_subsamples) + .5) / spatial_subsamples - .5
    origin_x, origin_z = plan["origin_m_xz"]
    spacing = plan["spacing_m"]
    columns = np.arange(col0, col1)[None, :]
    rows = np.arange(row0, row1)[:, None]
    for step in range(steps):
        lower = start_s + step * dt_s
        for delta_z in offsets:
            for delta_x in offsets:
                rain[step] += interval_mean_mm_h(origin_x + (columns + delta_x) * spacing,
                    origin_z + (rows + delta_z) * spacing, lower, lower + dt_s, parameters) / spatial_subsamples ** 2
        rain[step, ~valid] = 0.
    arrays = dict(rain_mm_h=rain, time_edges_s=start_s + np.arange(steps + 1) * dt_s,
        valid_mask=valid.copy(), protected_mask=protected.copy(), interval_rain_m3=_volumes(rain, spacing, dt_s))
    metadata = dict(plan=plan, plan_identity=identity({}, plan),
                    forcing_identity=identity({"rain_mm_h": rain}, {"dt_s": float(dt_s)}))
    result = dict(arrays=arrays, metadata=metadata, identity_sha256=identity(arrays, metadata))
    validate_native_storm(result, source_record=source_record, expected_plan=plan)
    result["arrays"] = {name: readonly(values) for name, values in arrays.items()}
    return result


def _headers(headers):
    if set(headers) != {"rain_mm_h", "time_edges_s", "valid_mask", "protected_mask", "interval_rain_m3", "manifest"}:
        raise ValueError("native weather archive layout mismatch")
    shape, dtype = headers["rain_mm_h"]
    if len(shape) != 3 or dtype != np.float64:
        raise ValueError("native weather rain header mismatch")
    preflight(tuple(shape[1:]), shape[0], 1)
    for name, expected_shape, expected_dtype in (("time_edges_s", (shape[0] + 1,), np.float64),
            ("interval_rain_m3", (shape[0],), np.float64), ("valid_mask", shape[1:], bool),
            ("protected_mask", shape[1:], bool)):
        if headers[name] != (expected_shape, np.dtype(expected_dtype)):
            raise ValueError("native weather vector/mask header mismatch")
    manifest_shape, manifest_dtype = headers["manifest"]
    if len(manifest_shape) != 1 or not 1 <= manifest_shape[0] <= 65536 or manifest_dtype != np.uint8:
        raise ValueError("native weather manifest budget mismatch")


def validate_native_storm(result, *, source_record=None, expected_plan=None):
    arrays, metadata = result["arrays"], result["metadata"]
    _headers({**{name: (values.shape, values.dtype) for name, values in arrays.items()},
              "manifest": ((1,), np.dtype("uint8"))})
    if set(metadata) != {"plan", "plan_identity", "forcing_identity"} or result["identity_sha256"] != identity(arrays, metadata):
        raise ValueError("weather bundle identity/schema mismatch")
    plan = metadata["plan"]
    if source_record is not None:
        source = _source(source_record)
        canonical = _plan(source, source_record, StormParameters(**plan["parameters"]), plan["steps"],
                          plan["dt_s"], plan["start_s"], plan["spatial_subsamples"], plan["window"])
        if plan != canonical:
            raise ValueError("weather source/plan semantic mismatch")
        row0, row1, col0, col1 = plan["window"]
        for name in ("valid_mask", "protected_mask"):
            if not np.array_equal(arrays[name], source["arrays"][name][row0:row1, col0:col1]):
                raise ValueError("weather source mask mismatch")
    if expected_plan is not None and plan != expected_plan:
        raise ValueError("external predeclared weather plan mismatch")
    if plan["schema"] != SCHEMA or metadata["plan_identity"] != identity({}, plan):
        raise ValueError("weather plan identity mismatch")
    resources = preflight(tuple(arrays["valid_mask"].shape), plan["steps"], plan["spatial_subsamples"])
    if resources != plan["resources"]:
        raise ValueError("weather resource metadata mismatch")
    parameters = StormParameters(**plan["parameters"])
    rain = arrays["rain_mm_h"]
    edges = plan["start_s"] + np.arange(plan["steps"] + 1) * plan["dt_s"]
    if rain.shape[0] != plan["steps"] or not np.array_equal(edges, arrays["time_edges_s"]):
        raise ValueError("weather time coverage mismatch")
    if not np.isfinite(rain).all() or (rain < 0).any() or (rain > parameters.peak_mm_h + 1e-10).any() or (rain[:, ~arrays["valid_mask"]] != 0).any():
        raise ValueError("invalid native rainfall")
    inactive = (edges[1:] <= parameters.start_s) | (edges[:-1] >= parameters.end_s)
    if (rain[inactive] != 0).any():
        raise ValueError("rain outside declared active interval")
    if metadata["forcing_identity"] != identity({"rain_mm_h": rain}, {"dt_s": float(plan["dt_s"])}):
        raise ValueError("full numerical forcing identity mismatch")
    if not np.array_equal(_volumes(rain, plan["spacing_m"], plan["dt_s"]), arrays["interval_rain_m3"]):
        raise ValueError("native interval rain volume mismatch")
    return dict(total_rain_m3=math.fsum(arrays["interval_rain_m3"]), max_rain_mm_h=float(rain.max()))


def save_native_storm(path, result):
    save_bundle(path, result, validator=validate_native_storm)


def load_native_storm(path, *, expected_sha256, expected_identity, source_record, expected_plan):
    _sha(expected_sha256)
    _sha(expected_identity)
    if not isinstance(expected_plan, dict):
        raise ValueError("external predeclared weather plan required")
    result = load_bundle(path, expected_sha256=expected_sha256, max_bytes=MAX_BYTES, header_validator=_headers,
        validator=lambda bundle: validate_native_storm(bundle, source_record=source_record, expected_plan=expected_plan))
    if result["identity_sha256"] != expected_identity:
        raise ValueError("external weather identity mismatch")
    return result
