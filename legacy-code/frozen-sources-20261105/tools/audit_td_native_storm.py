"""Independent bounded space/time quadrature of pinned native moving rainfall."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import psutil
from scipy.integrate import quad

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terrain_pipeline.mountain_source_adapter import file_sha256, publish_bytes
from tools.audit_td_candidate_coupling import read_record

MAX_EVALUATIONS = 100_000_000


def numerical_identity(rain, dt_s):
    digest = hashlib.sha256()
    digest.update(str(rain.shape).encode("ascii"))
    digest.update(rain.dtype.str.encode("ascii"))
    digest.update(rain.tobytes(order="C"))
    payload = {"metadata": {"dt_s": float(dt_s)}, "arrays": {"rain_mm_h": digest.hexdigest()}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode("utf-8")).hexdigest()


def instantaneous(east, south, time_s, parameters):
    elapsed = time_s - parameters["start_s"]
    distance_x = east - parameters["center_x_m"] - parameters["velocity_x_m_s"] * elapsed
    distance_z = south - parameters["center_z_m"] - parameters["velocity_z_m_s"] * elapsed
    if parameters["spatial_mode"] == "uniform":
        return np.zeros(np.broadcast_shapes(np.shape(east), np.shape(south))) + parameters["peak_mm_h"]
    return parameters["peak_mm_h"] * np.exp(-(distance_x ** 2 + distance_z ** 2) /
                                           (2 * parameters["sigma_m"] ** 2))


def independent_mean(east, south, lower, upper, parameters):
    active_lower = max(lower, parameters["start_s"])
    active_upper = min(upper, parameters["end_s"])
    if active_upper <= active_lower:
        return np.zeros(np.broadcast_shapes(np.shape(east), np.shape(south)))
    speed = math.hypot(parameters["velocity_x_m_s"], parameters["velocity_z_m_s"])
    panels = max(1, math.ceil(speed * (active_upper - active_lower) / (2 * parameters["sigma_m"])))
    nodes, weights = np.polynomial.legendre.leggauss(24)
    integral = np.zeros(np.broadcast_shapes(np.shape(east), np.shape(south)))
    boundaries = np.linspace(active_lower, active_upper, panels + 1)
    for first, last in zip(boundaries[:-1], boundaries[1:]):
        midpoint = (first + last) / 2
        half_width = (last - first) / 2
        for node, weight in zip(nodes, weights):
            integral += instantaneous(east, south, midpoint + half_width * node, parameters) * weight * half_width
    return integral / (upper - lower)


def adaptive_mean(east, south, lower, upper, parameters):
    first, last = max(lower, parameters["start_s"]), min(upper, parameters["end_s"])
    if last <= first:
        return 0.
    velocity_x, velocity_z = parameters["velocity_x_m_s"], parameters["velocity_z_m_s"]
    speed_squared = velocity_x ** 2 + velocity_z ** 2
    points = []
    if speed_squared:
        peak_time = parameters["start_s"] + ((east - parameters["center_x_m"]) * velocity_x +
                    (south - parameters["center_z_m"]) * velocity_z) / speed_squared
        width_s = parameters["sigma_m"] / math.sqrt(speed_squared)
        points = [peak_time + offset * width_s for offset in (-6, -3, -1, 0, 1, 3, 6)
                  if first < peak_time + offset * width_s < last]
    integral, error = quad(lambda time_s: float(instantaneous(east, south, time_s, parameters)),
                           first, last, points=points, epsabs=1e-8, epsrel=2e-12, limit=100)
    if error / (upper - lower) > 1e-9:
        raise ValueError("adaptive rainfall reference has insufficient precision")
    return integral / (upper - lower)


def audit_fields(arrays, metadata, source, source_metadata, expected_plan):
    plan = metadata["plan"]
    if plan != expected_plan or plan["schema"] != "td-native-moving-storm-v1":
        raise ValueError("external native storm plan mismatch")
    row0, row1, col0, col1 = plan["window"]
    shape = (row1 - row0, col1 - col0)
    steps, dt_s, subsamples = plan["steps"], plan["dt_s"], plan["spatial_subsamples"]
    if (steps < 1 or math.prod(shape) > 250000 or math.prod(shape) * steps > 4000000 or
            subsamples not in (1, 2, 4) or not math.isfinite(dt_s) or dt_s <= 0):
        raise ValueError("independent storm audit resource dimensions exceeded")
    if (list(source["height_m"].shape) != plan["source_shape"] or
            source_metadata["spacing_m"] != plan["spacing_m"] or
            list(source_metadata["origin_m_xz"]) != plan["origin_m_xz"]):
        raise ValueError("native storm absolute source grid mismatch")
    for name in ("valid_mask", "protected_mask"):
        np.testing.assert_array_equal(arrays[name], source[name][row0:row1, col0:col1])
    valid = arrays["valid_mask"]
    rain = arrays["rain_mm_h"]
    if rain.dtype != np.float64 or rain.shape != (steps, *shape) or not np.isfinite(rain).all():
        raise ValueError("native storm typed finite array mismatch")
    if np.any(rain < 0) or np.any(rain[:, ~valid] != 0):
        raise ValueError("native storm negative or unknown rainfall")
    edges = plan["start_s"] + np.arange(steps + 1) * dt_s
    np.testing.assert_array_equal(arrays["time_edges_s"], edges)
    parameters = plan["parameters"]
    if parameters["spatial_mode"] not in ("gaussian", "uniform"):
        raise ValueError("unsupported weather spatial mode")
    if not all(math.isfinite(value) for name, value in parameters.items() if name != "spatial_mode"):
        raise ValueError("nonfinite independent weather parameter")
    if parameters["sigma_m"] <= 0 or parameters["peak_mm_h"] < 0:
        raise ValueError("invalid independent weather scale")
    speed = math.hypot(parameters["velocity_x_m_s"], parameters["velocity_z_m_s"])
    evaluations = 0
    for lower, upper in zip(edges[:-1], edges[1:]):
        duration = max(0., min(upper, parameters["end_s"]) - max(lower, parameters["start_s"]))
        if duration:
            panels = max(1, math.ceil(speed * duration / (2 * parameters["sigma_m"])))
            evaluations += math.prod(shape) * subsamples ** 2 * 24 * panels
    if evaluations > MAX_EVALUATIONS:
        raise ValueError("independent rainfall quadrature work budget exceeded")
    spacing = plan["spacing_m"]
    origin_x, origin_z = plan["origin_m_xz"]
    offsets = (np.arange(subsamples) + .5) / subsamples - .5
    columns = np.arange(col0, col1)[None, :]
    rows = np.arange(row0, row1)[:, None]
    samples = set(np.linspace(0, math.prod(shape) - 1, min(19, math.prod(shape)), dtype=int).tolist())
    maximum_error = 0.
    adaptive_error = 0.
    adaptive_samples = 0
    volumes = []
    for step, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        reference = np.zeros(shape)
        for delta_z in offsets:
            for delta_x in offsets:
                reference += independent_mean(origin_x + (columns + delta_x) * spacing,
                    origin_z + (rows + delta_z) * spacing, lower, upper, parameters) / subsamples ** 2
        reference[~valid] = 0.
        difference = np.abs(rain[step] - reference)
        maximum_error = max(maximum_error, float(difference.max()))
        if np.any(difference > 1e-10 + 2e-12 * np.abs(reference)):
            raise ValueError("saved rain differs from independent full-grid time quadrature")
        for cell in samples | {int(reference.argmax()), int(difference.argmax())}:
            row, column = divmod(cell, shape[1])
            value = 0.
            if valid[row, column]:
                for delta_z in offsets:
                    for delta_x in offsets:
                        value += adaptive_mean(origin_x + (col0 + column + delta_x) * spacing,
                            origin_z + (row0 + row + delta_z) * spacing, lower, upper, parameters) / subsamples ** 2
            error = abs(value - rain[step, row, column])
            adaptive_error = max(adaptive_error, error)
            adaptive_samples += 1
            if error > 1e-10 + 2e-12 * abs(value):
                raise ValueError("saved rain differs from independent adaptive time integral")
        volumes.append(math.fsum(float(value) * dt_s / 3600 * spacing ** 2 / 1000
                                 for value in rain[step].flat))
    np.testing.assert_allclose(arrays["interval_rain_m3"], volumes, rtol=2e-15, atol=1e-9)
    if numerical_identity(rain, dt_s) != metadata["forcing_identity"]:
        raise ValueError("independent full numerical forcing identity mismatch")
    return dict(full_grid_time_quadrature_passed=True, evaluations=evaluations,
                max_rain_error_mm_h=maximum_error, adaptive_samples=adaptive_samples,
                max_adaptive_error_mm_h=adaptive_error, total_rain_m3=math.fsum(volumes),
                interval_rain_m3=volumes, numerical_forcing_identity=metadata["forcing_identity"])


def audit(index_path, expected_sha256):
    index_path = Path(index_path).resolve(strict=True)
    if file_sha256(index_path) != expected_sha256:
        raise ValueError("external storm index SHA mismatch")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index["schema"] != "td-native-storm-forcing-index-v1" or set(index["cases"]) != {"eastward", "westward"}:
        raise ValueError("fixed native storm two-direction coverage mismatch")
    resource = index["resource"]
    if (index["within_1GiB"] is not True or any(type(resource.get(name)) is not int or
            not 0 < resource[name] <= 1073741824 for name in ("peak_rss_bytes", "peak_private_bytes"))):
        raise ValueError("weather job requires complete bounded resource evidence")
    source, source_metadata = read_record(index["source"])
    results = {}
    cumulative = {}
    for direction, case in index["cases"].items():
        arrays, metadata = read_record(case["record"])
        plan = case["plan"]
        if (plan["source_sha256"] != index["source"]["expected_sha256"] or
                plan["source_identity"] != index["source"]["expected_identity"] or
                plan["window"] != [0, 256, 0, 256] or plan["steps"] != 24 or
                plan["dt_s"] != 3600. or plan["start_s"] != 0. or plan["spatial_subsamples"] != 2):
            raise ValueError("fixed full TD native storm coverage mismatch")
        parameters = plan["parameters"]
        span = 255 * source_metadata["spacing_m"]
        origin_x, origin_z = source_metadata["origin_m_xz"]
        eastward = direction == "eastward"
        expected_parameters = dict(center_x_m=origin_x if eastward else origin_x + span,
            center_z_m=origin_z + span / 2, velocity_x_m_s=(span if eastward else -span) / 21600,
            velocity_z_m_s=0., sigma_m=max(1., span / 4), peak_mm_h=30., start_s=0.,
            end_s=21600., spatial_mode="gaussian")
        if parameters != expected_parameters:
            raise ValueError("fixed independent storm parameters mismatch")
        result = audit_fields(arrays, metadata, source, source_metadata, plan)
        if result["numerical_forcing_identity"] != case["forcing_identity"]:
            raise ValueError("index numerical forcing identity mismatch")
        np.testing.assert_allclose(result["interval_rain_m3"], case["interval_rain_m3"], rtol=0, atol=0)
        if result["total_rain_m3"] != case["total_rain_m3"]:
            raise ValueError("index total rainfall differs from independent reduction")
        results[direction] = result
        cumulative[direction] = arrays["rain_mm_h"].sum(axis=0)
    symmetry = False
    if source["valid_mask"].all():
        np.testing.assert_allclose(cumulative["eastward"], cumulative["westward"][:, ::-1], rtol=2e-12, atol=1e-10)
        symmetry = True
    if (file_sha256(index_path) != expected_sha256 or
            file_sha256(index["source"]["path"]) != index["source"]["expected_sha256"] or
            any(file_sha256(case["record"]["path"]) != case["record"]["expected_sha256"]
                for case in index["cases"].values())):
        raise ValueError("weather inputs changed during independent audit")
    info = psutil.Process().memory_info()
    resource = dict(peak_rss_bytes=int(getattr(info, "peak_wset", info.rss)),
                    peak_private_bytes=getattr(info, "peak_pagefile", None))
    if resource["peak_private_bytes"] is None or max(resource.values()) > 1073741824:
        raise MemoryError("independent weather audit requires bounded RSS/private evidence")
    return dict(schema="td-independent-native-storm-audit-v1", index=str(index_path),
        index_sha256=expected_sha256, cases=results, all_native_weather_gates_passed=True,
        cumulative_mirror_symmetry_checked=symmetry, water_solved=False, hydraulic_ready=False,
        natural_outlet_verified=False, publishable=False,
        resource=resource,
        auditor_sha256=file_sha256(__file__),
        scope="Parameterized rainfall on original native cells, independently integrated; no hydrological solution.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--index-sha256", required=True)
    args = parser.parse_args()
    report = audit(args.index, args.index_sha256)
    output = ROOT / "verification/td-native-storm-forcing" / ("independent-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")) / "report.json"
    publish_bytes(output, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
    print(json.dumps(dict(path=str(output), sha256=file_sha256(output), passed=True), ensure_ascii=False))
