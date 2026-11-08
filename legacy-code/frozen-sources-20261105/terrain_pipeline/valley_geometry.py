"""Explicit valley surface before independent fixed-route bed planning."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.local_channel_sections import _source_surface


VERSION = "valley-geometry-v1"


@dataclass(frozen=True)
class ValleyGeometryRecipe:
    max_valley_depth_m: float
    max_valley_area_m2: float
    max_valley_volume_m3: float
    max_total_cut_volume_m3: float
    max_total_cut_area_m2: float = 1e12

    def __post_init__(self):
        if any(isinstance(v, bool) or not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError("valley budgets must be finite and nonnegative")


def prepare_valley_geometry(plan, centerline_world_xz_m, floor_elevation_m, width_m,
                            domain_mask, protected_mask, valley_recipe: ValleyGeometryRecipe,
                            channel_recipe: ChannelRecipe):
    """Create H1 from an independent floor profile, then replan the bed on H1."""
    if not isinstance(valley_recipe, ValleyGeometryRecipe) or not isinstance(channel_recipe, ChannelRecipe):
        raise ValueError("valley and channel recipes required")
    if ArtifactIdentity(**plan["identity"]).sha256 != plan["identity_sha256"] or plan["identity"]["algorithm"] != "metric-channel-plan":
        raise ValueError("invalid source plan identity")
    source = np.asarray(plan["arrays"]["source_height_m"])
    shape = source.shape
    source_params = plan["identity"]["parameters"]
    for name, field in (("source_height_m", "source_height_sha256"),
                        ("discharge_m3_s", "source_discharge_sha256"),
                        ("receiver", "source_route_sha256"),
                        ("order", "source_order_sha256"),
                        ("outlet_mask", "source_outlet_sha256")):
        if array_hash(np.ascontiguousarray(plan["arrays"][name])) != source_params[field]:
            raise ValueError("source plan inputs differ from identity")
    points = np.asarray(centerline_world_xz_m, dtype=np.float64)
    floors = np.asarray(floor_elevation_m, dtype=np.float64)
    widths = np.asarray(width_m, dtype=np.float64)
    domain = np.asarray(domain_mask)
    protected = np.asarray(protected_mask)
    if (points.ndim != 2 or points.shape[1] != 2 or len(points) < 2 or
            floors.shape != (len(points),) or widths.shape != floors.shape or
            not np.isfinite(points).all() or not np.isfinite(floors).all() or
            not np.isfinite(widths).all() or np.any(widths <= 0) or
            domain.shape != shape or protected.shape != shape or
            domain.dtype != bool or protected.dtype != bool):
        raise ValueError("invalid explicit valley geometry or masks")
    params = plan["identity"]["parameters"]
    requested = _rasterize_valley_edges(source, params,
        np.stack((points[:-1], points[1:]), axis=1),
        np.stack((floors[:-1], floors[1:]), axis=1),
        np.stack((widths[:-1], widths[1:]), axis=1))
    arrays, replanned, summary = _prepare_valley_cut(plan, requested, domain, protected,
        valley_recipe, channel_recipe, plan["identity_sha256"])
    identity = ArtifactIdentity("Terragenesis", "valley-geometry", VERSION, 0,
        {**asdict(valley_recipe), "source_plan_sha256": plan["identity_sha256"],
         "replanned_sha256": replanned["identity_sha256"],
         "centerline_sha256": array_hash(points), "floor_sha256": array_hash(floors),
         "width_sha256": array_hash(widths), "domain_sha256": array_hash(domain),
         "protected_sha256": array_hash(protected),
         "arrays_sha256": digest({name: array_hash(value) for name, value in arrays.items()}),
         "summary_sha256": digest(summary)})
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": arrays, "replanned_plan": replanned,
            "summary": summary}


def _rasterize_valley_edges(source, params, edges, floors, widths, local_bounds=False):
    """Rasterize independent metric segments using the maximum cut on overlaps."""
    shape = source.shape
    grid_x = params["origin_x_m"] + np.arange(shape[1]) * params["spacing_x_m"]
    grid_z = params["origin_z_m"] + np.arange(shape[0]) * params["spacing_z_m"]
    requested = np.zeros(shape, dtype=np.float64)
    for points, edge_floors, edge_widths in zip(edges, floors, widths):
        ax, az = points[0]
        bx, bz = points[1]
        length2 = (bx - ax) ** 2 + (bz - az) ** 2
        if length2 <= 0: raise ValueError("valley centerline has duplicate points")
        if local_bounds:
            reach = .5 * max(edge_widths)
            start_x = np.searchsorted(grid_x, min(ax, bx) - reach, side="left")
            stop_x = np.searchsorted(grid_x, max(ax, bx) + reach, side="right")
            start_z = np.searchsorted(grid_z, min(az, bz) - reach, side="left")
            stop_z = np.searchsorted(grid_z, max(az, bz) + reach, side="right")
            region = (slice(start_z, stop_z), slice(start_x, stop_x))
        else:
            region = (slice(None), slice(None))
        gx, gz = np.meshgrid(grid_x[region[1]], grid_z[region[0]])
        t = np.clip(((gx - ax) * (bx - ax) + (gz - az) * (bz - az)) / length2, 0., 1.)
        distance = np.hypot(gx - (ax + t * (bx - ax)), gz - (az + t * (bz - az)))
        radius = .5 * ((1 - t) * edge_widths[0] + t * edge_widths[1])
        inside = distance < radius
        floor = (1 - t) * edge_floors[0] + t * edge_floors[1]
        cut = np.zeros(gx.shape, dtype=np.float64)
        cut[inside] = np.maximum(0., source[region][inside] - floor[inside]) * (
            .5 * (1 + np.cos(np.pi * distance[inside] / radius[inside])))
        requested[region] = np.maximum(requested[region], cut)
    return requested


def _prepare_valley_cut(plan, requested, domain, protected, valley_recipe,
                       channel_recipe, parent_identity):
    """Shared H0/H1/H2 coarse diagnostic; requested cuts are never budget-clipped."""
    source = plan["arrays"]["source_height_m"]
    shape = source.shape
    params = plan["identity"]["parameters"]
    changed = requested > 1e-9
    cell_area = params["spacing_x_m"] * params["spacing_z_m"]
    weights = np.ones(shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    area = float(np.sum(changed * weights) * cell_area)
    valley_volume = float(np.sum(requested * weights) * cell_area)
    valley_surface = source - requested
    replanned = plan_channel(valley_surface, plan["arrays"]["receiver"], plan["arrays"]["order"],
        plan["arrays"]["outlet_mask"], plan["arrays"]["discharge_m3_s"],
        params["spacing_x_m"], params["spacing_z_m"], params["origin_x_m"], params["origin_z_m"],
        params["sea_level_elevation_m"], parent_identity, channel_recipe)
    bed_cut = valley_surface - replanned["arrays"]["bounded_bed_m"]
    total = requested + bed_cut
    total_volume = float(np.sum(total * weights) * cell_area)
    total_area = float(np.sum((total > 1e-9) * weights) * cell_area)
    failures = {"valley_depth": bool(np.any(requested > valley_recipe.max_valley_depth_m + 1e-9)),
                "valley_area": area > valley_recipe.max_valley_area_m2 + 1e-9,
                "valley_volume": valley_volume > valley_recipe.max_valley_volume_m3 + 1e-9,
                "total_volume": total_volume > valley_recipe.max_total_cut_volume_m3 + 1e-9,
                "domain": bool(np.any(changed & ~domain)),
                "protection": bool(np.any(changed & protected)),
                "bed_domain": bool(np.any((bed_cut > 1e-9) & ~domain)),
                "bed_protection": bool(np.any((bed_cut > 1e-9) & protected)),
                "bed_depth": bool(np.any(bed_cut > channel_recipe.max_cut_m + 1e-9)),
                "bed_plan": bool(np.any(replanned["arrays"]["over_budget_mask"] |
                                         replanned["arrays"]["failed_slope_edge_donor_mask"]))}
    arrays = {"source_height_m": source.copy(), "valley_surface_m": valley_surface,
              "final_bed_m": replanned["arrays"]["bounded_bed_m"].copy(),
              "valley_cut_m": requested, "bed_cut_m": bed_cut, "total_cut_m": total}
    for value in arrays.values(): value.flags.writeable = False
    summary = {"valley_area_m2": area, "valley_cut_volume_m3": valley_volume,
                        "bed_cut_volume_m3": float(np.sum(bed_cut * weights) * cell_area),
                        "total_cut_volume_m3": total_volume, "total_cut_area_m2": total_area,
                        "geometry_scope": "coarse_node_diagnostic_only",
                        "failures": failures,
                        "geometry_feasible": not any(failures.values())}
    return arrays, replanned, summary


def evaluate_fine_valley_ledger(valley_result, surface_result):
    """Account H0/H1/H2 on the same fine grid after the replanned bed sweep."""
    if valley_result["identity"]["algorithm"] == "network-valley":
        from terrain_pipeline.network_valley import validate_network_valley
        from terrain_pipeline.surface_network_prepare import validate_surface_network
        validate_network_valley(valley_result)
        validate_surface_network(surface_result, allow_diagnostic=True)
    if valley_result["replanned_plan"]["identity_sha256"] != surface_result["identity"]["parameters"]["plan_sha256"]:
        raise ValueError("surface preparation did not use the replanned valley bed")
    params = surface_result["identity"]["parameters"]
    coarse = valley_result["replanned_plan"]["identity"]["parameters"]
    shape = surface_result["arrays"]["final_surface_m"].shape
    x = params["fine_origin_x_m"] + np.arange(shape[1]) * params["fine_spacing_x_m"]
    z = params["fine_origin_z_m"] + np.arange(shape[0]) * params["fine_spacing_z_m"]
    gx, gz = np.meshgrid(x, z)
    fx = (gx - coarse["origin_x_m"]) / coarse["spacing_x_m"]
    fz = (gz - coarse["origin_z_m"]) / coarse["spacing_z_m"]
    coarse_shape = valley_result["arrays"]["source_height_m"].shape
    if (np.any(fx < -1e-8) or np.any(fx > coarse_shape[1] - 1 + 1e-8) or
            np.any(fz < -1e-8) or np.any(fz > coarse_shape[0] - 1 + 1e-8)):
        raise ValueError("fine grid leaves valley source extent")
    fx = np.clip(fx, 0, coarse_shape[1] - 1)
    fz = np.clip(fz, 0, coarse_shape[0] - 1)
    h0 = _source_surface(valley_result["arrays"]["source_height_m"], fx, fz)
    h1 = _source_surface(valley_result["arrays"]["valley_surface_m"], fx, fz)
    h2 = surface_result["arrays"]["final_surface_m"]
    if not np.allclose(h1, surface_result["arrays"]["source_surface_m"], rtol=0, atol=1e-8):
        raise ValueError("fine bed source is not the valley surface")
    valley_cut = h0 - h1
    bed_cut = h1 - h2
    total = h0 - h2
    if np.any(valley_cut < -1e-8) or np.any(bed_cut < -1e-8):
        raise ValueError("fine valley or bed raises terrain")
    weights = np.ones(shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    area_unit = params["fine_spacing_x_m"] * params["fine_spacing_z_m"]
    recipe = valley_result["identity"]["parameters"]
    valley_area = float(np.sum((valley_cut > 1e-9) * weights) * area_unit)
    valley_volume = float(np.sum(valley_cut * weights) * area_unit)
    bed_volume = float(np.sum(bed_cut * weights) * area_unit)
    total_volume = float(np.sum(total * weights) * area_unit)
    total_area = float(np.sum((total > 1e-9) * weights) * area_unit)
    fine_domain = surface_result["arrays"]["domain_mask"]
    coarse_valley_cells = np.argwhere(valley_result["arrays"]["valley_cut_m"] > 1e-9)
    if len(coarse_valley_cells):
        min_z, min_x = coarse_valley_cells.min(axis=0)
        max_z, max_x = coarse_valley_cells.max(axis=0)
        support_min_x, support_min_z = max(0, min_x - 1), max(0, min_z - 1)
        support_max_x = min(coarse_shape[1] - 1, max_x + 1)
        support_max_z = min(coarse_shape[0] - 1, max_z + 1)
        if (params["fine_origin_x_m"] > coarse["origin_x_m"] + support_min_x * coarse["spacing_x_m"] + 1e-8 or
                params["fine_origin_z_m"] > coarse["origin_z_m"] + support_min_z * coarse["spacing_z_m"] + 1e-8 or
                x[-1] < coarse["origin_x_m"] + support_max_x * coarse["spacing_x_m"] - 1e-8 or
                z[-1] < coarse["origin_z_m"] + support_max_z * coarse["spacing_z_m"] - 1e-8):
            raise ValueError("fine grid omits requested valley geometry")
    failures = {"valley_depth": bool(np.any(valley_cut > recipe["max_valley_depth_m"] + 1e-9)),
                "valley_area": valley_area > recipe["max_valley_area_m2"] + 1e-9,
                "valley_volume": valley_volume > recipe["max_valley_volume_m3"] + 1e-9,
                "total_volume": total_volume > recipe["max_total_cut_volume_m3"] + 1e-9,
                "total_area": total_area > recipe["max_total_cut_area_m2"] + 1e-9,
                "valley_domain": bool(np.any((valley_cut > 1e-9) & ~fine_domain)),
                "valley_protection": bool(np.any((valley_cut > 1e-9) & surface_result["arrays"]["protected_mask"])),
                "coarse_valley": not valley_result["summary"]["geometry_feasible"],
                "surface_joint": surface_result["status"] != "prepared"}
    summary = {"valley_area_m2": valley_area, "valley_cut_volume_m3": valley_volume,
               "bed_cut_volume_m3": bed_volume, "total_cut_volume_m3": total_volume,
               "total_cut_area_m2": total_area, "failures": failures}
    arrays = {"source_surface_m": h0, "valley_surface_m": h1,
              "final_surface_m": h2, "valley_cut_m": valley_cut,
              "bed_cut_m": bed_cut, "total_cut_m": total}
    if valley_result["identity"]["algorithm"] == "network-valley":
        arrays = {name: np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape)
                  for name, value in arrays.items()}
    identity = ArtifactIdentity("Terragenesis", "valley-fine-ledger", "valley-fine-ledger-v1", 0,
        {"valley_identity_sha256": valley_result["identity_sha256"],
         "surface_identity_sha256": surface_result["identity_sha256"],
         "origin_x_m": params["fine_origin_x_m"], "origin_z_m": params["fine_origin_z_m"],
         "spacing_x_m": params["fine_spacing_x_m"], "spacing_z_m": params["fine_spacing_z_m"],
         "shape_zx": list(shape),
         "max_valley_depth_m": recipe["max_valley_depth_m"],
         "max_valley_area_m2": recipe["max_valley_area_m2"],
         "max_valley_volume_m3": recipe["max_valley_volume_m3"],
         "max_total_cut_area_m2": recipe["max_total_cut_area_m2"],
         "max_total_cut_volume_m3": recipe["max_total_cut_volume_m3"],
         "summary_sha256": digest(summary),
         "arrays_sha256": digest({name: array_hash(value) for name, value in arrays.items()})})
    return {"status": "diagnostic_not_publishable" if any(failures.values()) else "prepared",
            "identity": identity.record(), "identity_sha256": identity.sha256,
            "summary": summary, "arrays": arrays}


def save_fine_valley_ledger(result, path):
    if result["status"] != "prepared":
        raise ValueError("failed fine valley ledger cannot be published")
    destination = Path(path)
    if destination.exists(): raise FileExistsError(destination)
    if not destination.parent.is_dir(): raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ("identity", "identity_sha256", "status", "summary")}
    record["format_version"] = 1
    record["array_sha256"] = {name: array_hash(value) for name, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False, suffix=".npz") as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_fine_valley_ledger(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return destination


def load_fine_valley_ledger(path):
    expected = {"source_surface_m", "valley_surface_m", "final_surface_m",
                "valley_cut_m", "bed_cut_m", "total_cut_m"}
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        if set(archive.files) != expected | {"manifest"} or set(record["array_sha256"]) != expected:
            raise ValueError("invalid fine valley array set")
        arrays = {name: archive[name].copy() for name in expected}
    identity = ArtifactIdentity(**record["identity"])
    if (record["format_version"] != 1 or record["status"] != "prepared" or
            identity.algorithm != "valley-fine-ledger" or identity.algorithm_version != "valley-fine-ledger-v1" or
            identity.sha256 != record["identity_sha256"] or
            any(array_hash(arrays[name]) != record["array_sha256"][name] for name in expected) or
            digest({name: array_hash(value) for name, value in arrays.items()}) !=
            identity.record()["parameters"]["arrays_sha256"] or
            digest(record["summary"]) != identity.record()["parameters"]["summary_sha256"]):
        raise ValueError("invalid fine valley identity or hashes")
    shape = arrays["source_surface_m"].shape
    if (len(shape) != 2 or any(arrays[name].shape != shape or arrays[name].dtype != np.float64 or
            not np.isfinite(arrays[name]).all() for name in expected) or
            any(np.any(arrays[name] < -1e-9) for name in ("valley_cut_m", "bed_cut_m", "total_cut_m")) or
            not np.allclose(arrays["source_surface_m"] - arrays["valley_surface_m"], arrays["valley_cut_m"], rtol=0, atol=1e-8) or
            not np.allclose(arrays["valley_surface_m"] - arrays["final_surface_m"], arrays["bed_cut_m"], rtol=0, atol=1e-8) or
            not np.allclose(arrays["valley_cut_m"] + arrays["bed_cut_m"], arrays["total_cut_m"], rtol=0, atol=1e-8) or
            any(record["summary"]["failures"].values())):
        raise ValueError("invalid fine valley ledger")
    params = identity.record()["parameters"]
    if (params["shape_zx"] != list(shape) or params["spacing_x_m"] <= 0 or
            params["spacing_z_m"] <= 0 or any(not math.isfinite(params[name]) for name in
                ("origin_x_m", "origin_z_m", "spacing_x_m", "spacing_z_m"))):
        raise ValueError("invalid fine valley grid")
    weights = np.ones(shape)
    weights[[0, -1], :] *= .5
    weights[:, [0, -1]] *= .5
    cell_area = params["spacing_x_m"] * params["spacing_z_m"]
    summary = record["summary"]
    computed = {"valley_area_m2": float(np.sum((arrays["valley_cut_m"] > 1e-9) * weights) * cell_area),
                "valley_cut_volume_m3": float(np.sum(arrays["valley_cut_m"] * weights) * cell_area),
                "bed_cut_volume_m3": float(np.sum(arrays["bed_cut_m"] * weights) * cell_area),
                "total_cut_volume_m3": float(np.sum(arrays["total_cut_m"] * weights) * cell_area),
                "total_cut_area_m2": float(np.sum((arrays["total_cut_m"] > 1e-9) * weights) * cell_area)}
    if any(not math.isclose(value, summary[name], abs_tol=1e-7) for name, value in computed.items()):
        raise ValueError("fine valley accounting mismatch")
    if (np.any(arrays["valley_cut_m"] > params["max_valley_depth_m"] + 1e-9) or
            computed["valley_area_m2"] > params["max_valley_area_m2"] + 1e-9 or
            computed["valley_cut_volume_m3"] > params["max_valley_volume_m3"] + 1e-9 or
            computed["total_cut_area_m2"] > params["max_total_cut_area_m2"] + 1e-9 or
            computed["total_cut_volume_m3"] > params["max_total_cut_volume_m3"] + 1e-9):
        raise ValueError("fine valley exceeds budget")
    for value in arrays.values(): value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": record["status"], "summary": record["summary"], "arrays": arrays}


def save_valley_geometry(result, path):
    destination = Path(path)
    if destination.exists(): raise FileExistsError(destination)
    if not destination.parent.is_dir(): raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ("identity", "identity_sha256", "status", "summary")}
    record["format_version"] = 1
    record["array_sha256"] = {name: array_hash(value) for name, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, delete=False, suffix=".npz") as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_valley_geometry(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)
    return destination


def load_valley_geometry(path):
    expected = {"source_height_m", "valley_surface_m", "final_bed_m",
                "valley_cut_m", "bed_cut_m", "total_cut_m"}
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        if set(archive.files) != expected | {"manifest"} or set(record["array_sha256"]) != expected:
            raise ValueError("invalid valley array set")
        arrays = {name: archive[name].copy() for name in expected}
    identity = ArtifactIdentity(**record["identity"])
    if (record["format_version"] != 1 or record["status"] != "diagnostic_not_publishable" or
            identity.algorithm != "valley-geometry" or identity.algorithm_version != VERSION or
            identity.sha256 != record["identity_sha256"] or
            any(array_hash(arrays[name]) != record["array_sha256"][name] for name in expected) or
            digest({name: array_hash(value) for name, value in arrays.items()}) !=
            identity.record()["parameters"]["arrays_sha256"] or
            digest(record["summary"]) != identity.record()["parameters"]["summary_sha256"]):
        raise ValueError("invalid valley identity or hashes")
    shape = arrays["source_height_m"].shape
    if (len(shape) != 2 or any(arrays[name].shape != shape or arrays[name].dtype != np.float64 or
            not np.isfinite(arrays[name]).all() for name in expected) or
            any(np.any(arrays[name] < -1e-9) for name in ("valley_cut_m", "bed_cut_m", "total_cut_m")) or
            not np.allclose(arrays["source_height_m"] - arrays["valley_surface_m"], arrays["valley_cut_m"], rtol=0, atol=1e-9) or
            not np.allclose(arrays["valley_surface_m"] - arrays["final_bed_m"], arrays["bed_cut_m"], rtol=0, atol=1e-9) or
            not np.allclose(arrays["valley_cut_m"] + arrays["bed_cut_m"], arrays["total_cut_m"], rtol=0, atol=1e-9)):
        raise ValueError("invalid valley geometry ledger")
    for value in arrays.values(): value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": record["status"], "arrays": arrays, "summary": record["summary"]}
