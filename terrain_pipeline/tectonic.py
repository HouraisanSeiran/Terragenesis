"""板块构造演化、冻结宏观产品与板块条件 TD 源（A 类）。

合并自 `tectonic_shapes`、`tectonic_formation`、`tectonic_evolution`、`tectonic_product`、
`plate_td_product` 五个旧实现。代码逐块原样保留，只对同组重名符号起命名变体：
`prepare_frozen_product`（原 tectonic_product.prepare）、`prepare_plate_source` /
`read_plate_source`（原 plate_td_product.prepare / read_product）、
`TECTONIC_ALGORITHM`（原 tectonic_product.ALGORITHM）。
"""


from terrain_pipeline.common_infra import published_algorithm_matches, published_algorithm_hashes

# ========================================================================
# 外部依赖（合并前各旧文件的 import，去重后集中在此）
# ========================================================================
import hashlib
import numpy as np
import heapq
from dataclasses import asdict, dataclass
from copy import deepcopy
from collections import deque
from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
import zipfile
import shutil
import math
import psutil
from diffusion.physical_config import PhysicalGenerationConfig



# ------------------------------------------------------------------------
# 原 terrain_pipeline/tectonic_shapes.py
# ------------------------------------------------------------------------

MAX_ASPECT = 6.


MAX_PERIODIC_IMAGES = 4096


SHAPE_PURPOSE = "formation-shapes"


def shape_parameters(world_seed, plate_count):
    """Independent fixed stream, balanced mixed families without seed retries."""
    seed = int.from_bytes(hashlib.sha256(
        f"{world_seed}:tectonic:{SHAPE_PURPOSE}".encode()).digest()[:8], "little")
    rng = np.random.default_rng(seed)
    families = np.resize(np.array(["circle", "ellipse", "triangle"]), plate_count)
    rng.shuffle(families)
    result = []
    for family in families:
        angle = float(rng.uniform(0, 2 * np.pi))
        aspect = float(rng.uniform(4, 6) if family == "ellipse" else
                       rng.uniform(1, 2) if family == "triangle" else 1.)
        result.append(dict(family=str(family), angle_rad=angle, aspect_ratio=aspect,
                           scale_cells=1.))
    return seed, result


def validate_shape(parameters):
    if not isinstance(parameters, dict) or set(parameters) != {
            "family", "angle_rad", "aspect_ratio", "scale_cells"}:
        raise ValueError("invalid shape parameters")
    if parameters["family"] not in ("circle", "ellipse", "triangle"):
        raise ValueError("unknown growth shape")
    for name in ("angle_rad", "aspect_ratio", "scale_cells"):
        value = parameters[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise ValueError("shape parameters must be finite numbers")
    if (not 0 <= parameters["angle_rad"] < 2 * np.pi or
            not 1 <= parameters["aspect_ratio"] <= MAX_ASPECT or
            not .25 <= parameters["scale_cells"] <= 4 or
            parameters["family"] == "circle" and parameters["aspect_ratio"] != 1):
        raise ValueError("shape parameters outside bounded range")


def _gauge(delta_xz, parameters):
    if parameters["family"] == "circle":
        return np.hypot(delta_xz[..., 0], delta_xz[..., 1]) / parameters["scale_cells"]
    angle = parameters["angle_rad"]
    cosine, sine = np.cos(angle), np.sin(angle)
    stretch = np.sqrt(parameters["aspect_ratio"])
    u = (delta_xz[..., 0] * cosine + delta_xz[..., 1] * sine) / stretch
    v = (-delta_xz[..., 0] * sine + delta_xz[..., 1] * cosine) * stretch
    if parameters["family"] == "triangle":
        # Outward normals of the three edges, with one vertex at (+1, 0).
        distance = np.maximum.reduce((u + np.sqrt(3) * v, -2 * u,
                                      u - np.sqrt(3) * v))
    else:
        distance = np.hypot(u, v)
    return distance / parameters["scale_cells"]


def periodic_shape_distance(delta_xz, period_xz, parameters):
    """Exact minimum gauge over a bounded set of periodic images.

    Every gauge >= Euclidean norm/(sqrt(aspect)*scale). The Euclidean
    nearest image supplies an upper bound B, so an improving image lies
    inside radius B*sqrt(aspect)*scale. Search that finite rectangle,
    rejecting requests above 4096 images before allocating the search.
    Storage is O(points); no [image,point] array is constructed.
    """
    validate_shape(parameters)
    delta = np.asarray(delta_xz, dtype=float)
    period = np.asarray(period_xz, dtype=float)
    if (delta.ndim < 1 or delta.shape[-1] != 2 or not np.isfinite(delta).all() or
            period.shape != (2,) or not np.isfinite(period).all() or np.any(period <= 0)):
        raise ValueError("finite XZ deltas and positive periods required")
    delta = (delta + period / 2) % period - period / 2
    best = _gauge(delta, parameters)
    radius = float(np.max(best, initial=0)) * np.sqrt(parameters["aspect_ratio"]) * parameters["scale_cells"]
    with np.errstate(over="ignore", invalid="ignore"):
        bounds = np.ceil(radius / period + .5)
        image_count = np.prod(2 * bounds + 1)
    if not np.isfinite(image_count) or image_count > MAX_PERIODIC_IMAGES:
        raise ValueError("periodic shape image resource budget exceeded")
    bounds = bounds.astype(int)
    for ix in range(-bounds[0], bounds[0] + 1):
        for iz in range(-bounds[1], bounds[1] + 1):
            if ix == 0 and iz == 0:
                continue
            candidate = _gauge(delta + period * (ix, iz), parameters)
            best = np.minimum(best, candidate)
    return best


def formation_image_budget(period_xz, shapes):
    """Conservative per-node image visits, using worst nearest-image norm.

    Rectangle diagonal/2 bounds that norm. The gauge's upper factor is
    sqrt(aspect)/scale for ellipses and twice that for triangles.
    """
    period = np.asarray(period_xz, dtype=float)
    total = 0
    for parameters in shapes:
        validate_shape(parameters)
        factor = 2 if parameters["family"] == "triangle" else 1
        radius = factor * parameters["aspect_ratio"] * np.linalg.norm(period / 2)
        bounds = np.ceil(radius / period + .5)
        images = float(np.prod(2 * bounds + 1))
        if not np.isfinite(images) or images > MAX_PERIODIC_IMAGES:
            raise ValueError("periodic shape image resource budget exceeded")
        total += int(images)
    return total



# ------------------------------------------------------------------------
# 原 terrain_pipeline/tectonic_formation.py
# ------------------------------------------------------------------------

LEGACY_FORMATION_VERSION = "periodic-voronoi-adjacency-1"


COMPACT_FORMATION_VERSION = "periodic-voronoi-core-growth-1"


FORMATION_VERSION = "periodic-voronoi-shaped-core-growth-1"


PATH_WEIGHT = .15


def core_growth(nodes, source_sites, sites_zx, edges, shape, plate_count, shapes=None):
    """Connected competitive growth; distances in resolved cell widths.

    Cores use deterministic farthest-point sampling of site-containing
    fragments, starting at site zero. Split fragments cannot anchor a core
    at a source site outside their own resolved cells.
    Ties use fragment/plate IDs. All cores are reserved before expansion;
    every claim has an already owned face neighbour. No raster masks or
    post-growth reassignment alter material ownership.
    """
    positions = sites_zx[np.asarray(source_sites)]
    shape = np.asarray(shape)

    def distances(point):
        delta = (positions - point + shape / 2) % shape - shape / 2
        return np.linalg.norm(delta, axis=1)

    cores = [int(nodes[tuple(sites_zx[0])])]
    candidates = np.unique(nodes[sites_zx[:, 0], sites_zx[:, 1]])
    nearest = distances(positions[cores[0]])
    while len(cores) < plate_count:
        nearest[~np.isin(np.arange(len(source_sites)), candidates)] = -1
        nearest[cores] = -1
        core = int(np.argmax(nearest))
        cores.append(core)
        nearest = np.minimum(nearest, distances(positions[core]))
    neighbors = [set() for _ in source_sites]
    for a, b in edges:
        neighbors[a].add(int(b))
        neighbors[b].add(int(a))
    owners = np.full(len(source_sites), -1, dtype=np.int32)
    owners[cores] = np.arange(plate_count)
    if shapes is None:
        radial = np.array([distances(positions[core]) for core in cores])
    else:
        if len(shapes) != plate_count:
            raise ValueError("one growth shape required per core")
        radial = np.array([periodic_shape_distance(
            (positions - positions[core])[:, ::-1], shape[::-1], parameters)
            for core, parameters in zip(cores, shapes)])
    frontier = []

    def offer(plate, node, path, priority):
        for other in sorted(neighbors[node]):
            if owners[other] >= 0:
                continue
            delta = (positions[other] - positions[node] + shape / 2) % shape - shape / 2
            next_path = path + float(np.linalg.norm(delta))
            cost = (1 - PATH_WEIGHT) * radial[plate, other] + PATH_WEIGHT * next_path
            heapq.heappush(frontier, (max(priority, cost), plate, other, next_path))

    for plate, core in enumerate(cores):
        offer(plate, core, 0., 0.)
    while frontier:
        priority, plate, node, path = heapq.heappop(frontier)
        if owners[node] >= 0:
            continue
        owners[node] = plate
        offer(plate, node, path, priority)
    if np.any(owners < 0):
        raise ValueError("unreachable microfragment")
    return owners.tolist(), cores


def validate_formation(config):
    for name, minimum in (("microcells_per_plate", 2), ("min_plate_cells", 1)):
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    if config.plate_count * config.min_plate_cells > int(np.prod(config.shape)):
        raise ValueError("infeasible minimum resolved plate area")


def microcell_count(config):
    cells = int(np.prod(config.shape))
    return min(cells, max(config.plate_count, min(config.plate_count * config.microcells_per_plate,
                                                cells // 4)))


def components(labels):
    """Return deterministic face-connected torus components and source labels."""
    nz, nx = labels.shape
    result = np.full(labels.shape, -1, dtype=np.int32)
    sources = []
    for z in range(nz):
        for x in range(nx):
            if result[z, x] >= 0:
                continue
            node = len(sources)
            source = labels[z, x]
            sources.append(int(source))
            result[z, x] = node
            queue = [(z, x)]
            for qz, qx in queue:
                for az, ax in (((qz - 1) % nz, qx), ((qz + 1) % nz, qx),
                               (qz, (qx - 1) % nx), (qz, (qx + 1) % nx)):
                    if result[az, ax] < 0 and labels[az, ax] == source:
                        result[az, ax] = node
                        queue.append((az, ax))
    return result, sources


def adjacency(labels):
    pairs = []
    for axis in (0, 1):
        other = np.roll(labels, -1, axis)
        mask = labels != other
        pairs.append(np.sort(np.column_stack((labels[mask], other[mask])), axis=1))
    return np.unique(np.concatenate(pairs), axis=0)


def geometry_metrics(ids, cell_size_m):
    """Resolved face counts and connectivity; no smoothing or display geometry."""
    _, sources = components(ids)
    count = int(ids.max()) + 1
    area = np.bincount(ids.ravel(), minlength=count)
    perimeter = np.zeros(count, dtype=int)
    faces = 0
    for axis in (0, 1):
        other = np.roll(ids, -1, axis)
        mask = ids != other
        faces += int(mask.sum())
        perimeter += np.bincount(ids[mask], minlength=count)
        perimeter += np.bincount(other[mask], minlength=count)
    return {"plate_area_cells": area.tolist(), "plate_area_m2": (area * cell_size_m**2).tolist(),
            "periodic_components_per_plate": np.bincount(sources, minlength=count).tolist(),
            "boundary_faces": faces, "plate_perimeter_m": (perimeter * cell_size_m).tolist()}


def voronoi_complexity(sites_zx, shape, source_sites, owners):
    """Continuous edges/concave vertices, excluding grid staircase artifacts.

    A vertex joining two cells of one plate and one of another is a reflex
    corner of the two-cell union. Ambiguous split-site ownership is excluded
    from this continuous statistic and explicitly counted; resolved connectivity
    and coverage always use the complete fragment raster.
    """
    from scipy.spatial import Voronoi
    ownership = {}
    for source, owner in zip(source_sites, owners):
        ownership.setdefault(source, set()).add(owner)
    unambiguous = {s: next(iter(p)) for s, p in ownership.items() if len(p) == 1}
    points = np.concatenate([sites_zx + np.array((dz, dx)) * shape
                             for dz in (-1, 0, 1) for dx in (-1, 0, 1)])
    diagram = Voronoi(points)
    vertex_sites = [set() for _ in diagram.vertices]
    segments = 0
    for (a, b), vertices in zip(diagram.ridge_points, diagram.ridge_vertices):
        sa, sb = int(a % len(sites_zx)), int(b % len(sites_zx))
        for v in vertices:
            if v >= 0:
                vertex_sites[v].update((sa, sb))
        if len(vertices) == 2 and min(vertices) >= 0:
            midpoint = diagram.vertices[vertices].mean(axis=0)
            if (np.all(midpoint >= 0) and np.all(midpoint < shape) and
                    sa in unambiguous and sb in unambiguous and unambiguous[sa] != unambiguous[sb]):
                segments += 1
    concave = np.zeros(max(owners) + 1, dtype=int)
    for point, sources in zip(diagram.vertices, vertex_sites):
        if not (np.all(point >= 0) and np.all(point < shape)) or len(sources) != 3:
            continue
        if not sources.issubset(unambiguous):
            continue
        plates = [unambiguous[s] for s in sources]
        if len(set(plates)) == 2:
            majority = max(set(plates), key=plates.count)
            concave[majority] += 1
    return {"continuous_boundary_segments": segments,
            "continuous_concave_vertices_per_plate": concave.tolist(),
            "continuous_metrics_excluded_split_sites": len(ownership) - len(unambiguous)}


def form_plates(config, seed):
    validate_formation(config)
    rng = np.random.default_rng(seed)
    nz, nx = config.shape
    count = microcell_count(config)
    sites = rng.choice(nz * nx, count, replace=False)
    sites_zx = np.column_stack((sites // nx, sites % nx))
    z, x = np.indices(config.shape)
    best = np.full(config.shape, np.inf)
    micro = np.zeros(config.shape, dtype=np.int32)
    for site, (sz, sx) in enumerate(sites_zx):
        dx = (x - sx + nx / 2) % nx - nx / 2
        dz = (z - sz + nz / 2) % nz - nz / 2
        distance = dx * dx + dz * dz
        closer = distance < best
        micro[closer] = site
        best[closer] = distance[closer]
    nodes, source_sites = components(micro)
    edges = adjacency(nodes)
    areas = np.bincount(nodes.ravel())
    shape_seed, shapes = shape_parameters(config.world_seed, config.plate_count)
    owners, cores = core_growth(nodes, source_sites, sites_zx, edges, config.shape, config.plate_count, shapes)
    plate_areas = np.bincount(np.asarray(owners)[nodes].ravel(), minlength=config.plate_count)
    if plate_areas.min() < config.min_plate_cells:
        raise ValueError("infeasible sampled core growth: minimum resolved plate area; no reseeding")
    ids = np.asarray(owners, dtype=np.int32)[nodes]
    # Anchors are representative initial resolved cells, not Voronoi generators.
    anchors = np.array([sites_zx[source_sites[cores[plate]]][::-1] + .5
                        for plate in range(config.plate_count)]) * config.cell_size_m
    cross = sum(owners[a] != owners[b] for a, b in edges)
    metadata = {"version": FORMATION_VERSION, "minimum_resolved_plate_area_m2":
                config.min_plate_cells * config.cell_size_m**2,
                "microcell_count": count, "connected_microfragment_count": len(areas),
                "split_microfragment_count": len(areas) - count,
                "micro_sites_local_xz_m": ((sites_zx[:, ::-1] + .5) * config.cell_size_m).tolist(),
                "microfragment_source_site": source_sites, "microfragment_id_zx": nodes.tolist(),
                "microfragment_plate": owners, "microfragment_adjacency": edges.tolist(),
                "cross_plate_microfragment_interfaces": int(cross),
                "core_microfragment_per_plate": cores,
                "growth_shapes": shapes, "shape_purpose_seed": shape_seed,
                "shape_seed_derivation": "SHA256(f'{world_seed}:tectonic:formation-shapes'), first 8 bytes little-endian",
                "shape_semantics": "generation prior only; X east/Z south; angle +X toward +Z; triangle tip; unit circumradius before area-preserving stretch",
                "periodic_shape_search": "gauge >= norm/(sqrt(aspect)*scale); nearest-image upper bound; at most 4096 images; streamed",

                "growth_cost": {"distance_unit": "cell widths", "path_weight": PATH_WEIGHT,
                                "priority": "max(parent priority, 0.85*periodic shape gauge + 0.15*site path length)",
                                "core_selection": "farthest periodic site distance among site-containing fragments; site zero first; fragment ID ties"},
                "fragment_policy": "split periodic 4-connected samples; grow only across adjacent nodes; retain all cells",
                "plate_anchor_semantics": "core microcell site, not single-site plate Voronoi generator",
                **voronoi_complexity(sites_zx, np.array(config.shape), source_sites, owners),
                **geometry_metrics(ids, config.cell_size_m)}
    return ids, anchors, metadata


def validate_geometry(config, geometry, initial_ids, source):
    """Validate saved resolved geometry without generating or evolving terrain."""
    if source == "injected" and geometry is None:
        return
    if source not in ("generated", "injected") or not isinstance(geometry, dict) or geometry.get("version") not in (FORMATION_VERSION, COMPACT_FORMATION_VERSION, LEGACY_FORMATION_VERSION):
        raise ValueError("invalid formation provenance")
    try:
        nodes = np.asarray(geometry["microfragment_id_zx"])
        owners = np.asarray(geometry["microfragment_plate"])
        sites = np.asarray(geometry["micro_sites_local_xz_m"])
        sources = np.asarray(geometry["microfragment_source_site"])
        count = geometry["microcell_count"]
        from types import SimpleNamespace
        expected_count = microcell_count(SimpleNamespace(**config))
        if (nodes.shape != tuple(config["shape"]) or nodes.dtype.kind not in "iu" or
                owners.ndim != 1 or owners.dtype.kind not in "iu" or len(owners) == 0 or
                nodes.min() < 0 or nodes.max() >= len(owners) or
                owners.min() < 0 or owners.max() >= config["plate_count"] or
                sites.shape != (count, 2) or not np.isfinite(sites).all() or
                sources.shape != owners.shape or sources.dtype.kind not in "iu" or
                sources.min() < 0 or sources.max() >= count or count != expected_count or
                len(np.unique(sources)) != count or
                geometry["connected_microfragment_count"] != len(owners) or
                geometry["split_microfragment_count"] != len(owners) - count):
            raise ValueError("invalid saved microcell geometry")
        if not np.array_equal(owners[nodes], initial_ids):
            raise ValueError("formation ownership inconsistent with initial crust")
        site_cells_xz = sites / config["cell_size_m"] - .5
        if (not np.allclose(site_cells_xz, np.round(site_cells_xz), rtol=0, atol=1e-9) or
                np.any(site_cells_xz < 0) or np.any(site_cells_xz >= np.array(config["shape"])[::-1]) or
                len(np.unique(site_cells_xz, axis=0)) != count):
            raise ValueError("invalid microcell sites")
        site_cells_xz = np.round(site_cells_xz).astype(int)
        sampled_sources = sources[nodes[site_cells_xz[:, 1], site_cells_xz[:, 0]]]
        if not np.array_equal(sampled_sources, np.arange(count)):
            raise ValueError("microcell sites inconsistent with fragments")
        if geometry["version"] in (FORMATION_VERSION, COMPACT_FORMATION_VERSION):
            shapes = None
            priority = "max(parent priority, 0.85*periodic core distance + 0.15*site path length)"
            if geometry["version"] == FORMATION_VERSION:
                seed, shapes = shape_parameters(config["world_seed"], config["plate_count"])
                if (geometry.get("growth_shapes") != shapes or geometry.get("shape_purpose_seed") != seed or
                        geometry.get("shape_seed_derivation") != "SHA256(f'{world_seed}:tectonic:formation-shapes'), first 8 bytes little-endian" or
                        geometry.get("shape_semantics") != "generation prior only; X east/Z south; angle +X toward +Z; triangle tip; unit circumradius before area-preserving stretch" or
                        geometry.get("periodic_shape_search") != "gauge >= norm/(sqrt(aspect)*scale); nearest-image upper bound; at most 4096 images; streamed"):
                    raise ValueError("invalid growth shape provenance")
                priority = "max(parent priority, 0.85*periodic shape gauge + 0.15*site path length)"
            expected_owners, cores = core_growth(nodes, sources.tolist(), site_cells_xz[:, ::-1],
                                                 adjacency(nodes), config["shape"], config["plate_count"], shapes)
            if (expected_owners != owners.tolist() or geometry.get("core_microfragment_per_plate") != cores or
                    geometry.get("growth_cost") != {
                        "distance_unit": "cell widths", "path_weight": PATH_WEIGHT,
                        "priority": priority,
                        "core_selection": "farthest periodic site distance among site-containing fragments; site zero first; fragment ID ties"}):
                raise ValueError("invalid core growth geometry")
        connected, _ = components(nodes)
        if len(np.unique(connected)) != len(owners) or len(np.unique(nodes)) != len(owners):
            raise ValueError("disconnected or empty microfragment")
        edges = adjacency(nodes)
        if edges.tolist() != geometry["microfragment_adjacency"]:
            raise ValueError("invalid microfragment adjacency")
        cross = int(np.count_nonzero(owners[edges[:, 0]] != owners[edges[:, 1]])) if len(edges) else 0
        if cross != geometry["cross_plate_microfragment_interfaces"]:
            raise ValueError("invalid microfragment interface count")
        continuous = voronoi_complexity(site_cells_xz[:, ::-1], np.array(config["shape"]),
                                       sources.tolist(), owners.tolist())
        if any(continuous[key] != geometry[key] for key in continuous):
            raise ValueError("invalid continuous formation metrics")
        metrics = geometry_metrics(initial_ids, config["cell_size_m"])
        if any(metrics[key] != geometry[key] for key in metrics):
            raise ValueError("invalid formation metrics")
        if (metrics["periodic_components_per_plate"] != [1] * config["plate_count"] or
                min(metrics["plate_area_cells"]) < config["min_plate_cells"] or
                geometry["minimum_resolved_plate_area_m2"] != config["min_plate_cells"] * config["cell_size_m"]**2):
            raise ValueError("unresolved or disconnected initial plate")
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("invalid formation geometry") from error



# ------------------------------------------------------------------------
# 原 terrain_pipeline/tectonic_evolution.py
# ------------------------------------------------------------------------

ALGORITHM_VERSION = "kinematic-crust-4"


_BUDGET_RELATIVE_TOLERANCE = 1e-12


_BUDGET_ABSOLUTE_TOLERANCE_M3 = 1e-12


@dataclass(frozen=True)
class TectonicConfig:
    shape: tuple = (128, 128)
    cell_size_m: float = 10000.0
    origin_x_m: float = 0.0
    origin_z_m: float = 0.0
    plate_count: int = 8
    microcells_per_plate: int = 64
    min_plate_cells: int = 4
    world_seed: int = 20261020
    steps: int = 40
    time_step: float = 1.0
    max_speed_m_per_step: float = 2000.0
    continental_thickness_m: float = 35000.0
    oceanic_thickness_m: float = 7000.0
    subduction_fraction: float = 1.0
    rift_fraction: float = 1.0


@dataclass
class CrustState:
    plate_coverage: np.ndarray
    continental_m: np.ndarray
    oceanic_m: np.ndarray
    plate_seeds_m: np.ndarray
    velocities_m_per_step: np.ndarray
    step: int = 0
    formation: dict | None = None


@dataclass
class EvolutionResult:
    initial: CrustState
    final: CrustState
    initial_elevation_m: np.ndarray
    elevation_m: np.ndarray
    plate_id: np.ndarray
    continental_fraction: np.ndarray
    crust_thickness_m: np.ndarray
    budgets: list
    metadata: dict


def _integer(value, minimum):
    return isinstance(value, (int, np.integer)) and not isinstance(value, bool) and value >= minimum


def _validate_config(config):
    if len(config.shape) != 2 or not all(_integer(n, 2) for n in config.shape):
        raise ValueError("shape must contain two integers >= 2")
    if not _integer(config.plate_count, 1) or config.plate_count > np.prod(config.shape):
        raise ValueError("plate_count outside grid capacity")
    validate_formation(config)
    if not _integer(config.steps, 0) or not _integer(config.world_seed, 0):
        raise ValueError("steps and world_seed must be nonnegative integers")
    for name in ("cell_size_m", "time_step", "continental_thickness_m", "oceanic_thickness_m"):
        value = getattr(config, name)
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name in ("origin_x_m", "origin_z_m", "max_speed_m_per_step", "subduction_fraction", "rift_fraction"):
        if not np.isfinite(getattr(config, name)):
            raise ValueError(f"{name} must be finite")
    if config.max_speed_m_per_step < 0:
        raise ValueError("max_speed_m_per_step must be nonnegative")
    if any(not 0 <= value <= 1 for value in (config.subduction_fraction, config.rift_fraction)):
        raise ValueError("mechanism fractions must lie in [0,1]")
    with np.errstate(over="ignore", invalid="ignore"):
        area = np.float64(config.cell_size_m) ** 2
        extent = np.array(config.shape, dtype=float) * config.cell_size_m
    if not np.isfinite(area) or not np.isfinite(extent).all():
        raise ValueError("nonfinite domain dimensions or cell area")


def _purpose_seed(world_seed, purpose):
    digest = hashlib.sha256(f"{world_seed}:tectonic:{purpose}".encode()).digest()
    return int.from_bytes(digest[:8], "little")


def _coordinates(config):
    z, x = np.indices(config.shape, dtype=float)
    return (x + 0.5) * config.cell_size_m, (z + 0.5) * config.cell_size_m


def _periodic_distance(delta, length):
    return (delta + length / 2) % length - length / 2


def initialize(config):
    """Return connected aggregated microcells and independent continental embryos."""
    _validate_config(config)
    width = config.shape[1] * config.cell_size_m
    height = config.shape[0] * config.cell_size_m
    ids, seeds, formation = form_plates(config, _purpose_seed(config.world_seed, "plates"))
    x, z = _coordinates(config)
    coverage = np.arange(config.plate_count)[:, None, None] == ids
    rng = np.random.default_rng(_purpose_seed(config.world_seed, "crust"))
    continent = np.zeros(config.shape)
    for _ in range(max(2, config.plate_count // 2)):
        cx, cz = rng.random(2) * (width, height)
        radius_x, radius_z = rng.uniform(0.12, 0.26, 2) * (width, height)
        radius = (_periodic_distance(x - cx, width) / radius_x) ** 2
        radius += (_periodic_distance(z - cz, height) / radius_z) ** 2
        continent = np.maximum(continent, np.clip((1.15 - radius) / 0.3, 0, 1))
    rng = np.random.default_rng(_purpose_seed(config.world_seed, "velocity"))
    angle = rng.uniform(0, 2 * np.pi, config.plate_count)
    speed = rng.uniform(0.4, 1, config.plate_count) * config.max_speed_m_per_step
    velocities = np.column_stack((np.cos(angle) * speed, np.sin(angle) * speed))
    state = CrustState(coverage.astype(float), coverage * continent * config.continental_thickness_m,
                       coverage * (1 - continent) * config.oceanic_thickness_m,
                       seeds + (config.origin_x_m, config.origin_z_m), velocities, formation=formation)
    _validate_state(config, state)
    return state


def _validate_state(config, state):
    expected = (config.plate_count, *config.shape)
    for name in ("plate_coverage", "continental_m", "oceanic_m"):
        field = np.asarray(getattr(state, name))
        if field.shape != expected or not np.isfinite(field).all() or (field < 0).any():
            raise ValueError(f"invalid {name}: expected finite nonnegative {expected}")
    if not np.allclose(np.sum(state.plate_coverage, axis=0), 1, rtol=0, atol=1e-12):
        raise ValueError("plate coverage must partition unity")
    empty = np.asarray(state.plate_coverage) == 0
    if (np.asarray(state.continental_m)[empty] > 0).any() or (np.asarray(state.oceanic_m)[empty] > 0).any():
        raise ValueError("material cannot exist on an absent plate")
    for name in ("plate_seeds_m", "velocities_m_per_step"):
        values = np.asarray(getattr(state, name))
        if values.shape != (config.plate_count, 2) or not np.isfinite(values).all():
            raise ValueError(f"invalid {name}")
    seeds = np.asarray(state.plate_seeds_m) - (config.origin_x_m, config.origin_z_m)
    extent = np.array(config.shape[::-1]) * config.cell_size_m
    if (seeds < 0).any() or (seeds >= extent).any():
        raise ValueError("plate seeds outside periodic domain")
    _displacement(config, state)
    if not _integer(state.step, 0):
        raise ValueError("invalid offline step index")
    with np.errstate(over="ignore", invalid="ignore"):
        volume = (np.sum(state.continental_m) + np.sum(state.oceanic_m)) * config.cell_size_m ** 2
    if not np.isfinite(volume):
        raise ValueError("nonfinite material volume")


def _copy_state(state):
    return CrustState(*(np.array(getattr(state, name), dtype=float, copy=True) for name in
                        ("plate_coverage", "continental_m", "oceanic_m", "plate_seeds_m",
                         "velocities_m_per_step")), step=int(state.step), formation=deepcopy(state.formation))


def _displacement(config, state):
    # Validate the exact dimensionless values used by transport, with no slack.
    with np.errstate(over="ignore", invalid="ignore"):
        displacement = state.velocities_m_per_step * config.time_step / config.cell_size_m
        courant = np.abs(displacement).sum(axis=1)
    if not np.isfinite(courant).all() or (courant > 1).any():
        raise ValueError("CFL requires time_step*(abs(vx)+abs(vz))/cell_size_m <= 1")
    return displacement


def surface_fields(state):
    """Derive cell surface from current material, never from a boundary ridge."""
    continental = np.sum(state.continental_m, axis=0)
    oceanic = np.sum(state.oceanic_m, axis=0)
    thickness = continental + oceanic
    fraction = np.divide(continental, thickness, out=np.zeros_like(thickness), where=thickness > 0)
    density = fraction * 2800.0 + (1 - fraction) * 3000.0
    return {"elevation_m": continental * (1 - 2800 / 3300) + oceanic * (1 - 3000 / 3300) - 4500,
            "plate_id": np.argmax(state.plate_coverage, axis=0).astype(np.int32),
            "continental_fraction": fraction, "crust_thickness_m": thickness,
            "density_kg_m3": density}


def _advect(field, displacement):
    result = np.empty_like(field)
    for plate, (dx, dz) in enumerate(displacement):
        # Unsplit first-order donor cell: positive weights under the L1 CFL.
        source = field[plate]
        result[plate] = ((1 - (abs(dx) + abs(dz))) * source
                         + abs(dx) * np.roll(source, 1 if dx >= 0 else -1, axis=1)
                         + abs(dz) * np.roll(source, 1 if dz >= 0 else -1, axis=0))
    return result


def _boundaries(coverage, velocities):
    ids = coverage.argmax(axis=0)
    counts = {"convergent_faces": 0, "divergent_faces": 0, "transform_faces": 0}
    for axis, component in ((1, 0), (0, 1)):
        neighbor = np.roll(ids, -1, axis=axis)
        boundary = ids != neighbor
        normal = velocities[neighbor, component] - velocities[ids, component]
        tangent = velocities[neighbor, 1 - component] - velocities[ids, 1 - component]
        counts["convergent_faces"] += int(np.count_nonzero(boundary & (normal < -1e-10)))
        counts["divergent_faces"] += int(np.count_nonzero(boundary & (normal > 1e-10)))
        counts["transform_faces"] += int(np.count_nonzero(boundary & (abs(normal) <= 1e-10) & (abs(tangent) > 1e-10)))
    return counts


def _step(config, state):
    area = config.cell_size_m ** 2
    before_c = float(state.continental_m.sum() * area)
    before_o = float(state.oceanic_m.sum() * area)
    displacement = _displacement(config, state)
    coverage = _advect(state.plate_coverage, displacement)
    continental = _advect(state.continental_m, displacement)
    oceanic = _advect(state.oceanic_m, displacement)
    transport_c = float(continental.sum() * area - before_c)
    transport_o = float(oceanic.sum() * area - before_o)
    # Loss of squared concentration at fixed conserved volume measures mixing.
    diffusion = float(max(0, np.square(state.continental_m).sum() - np.square(continental).sum()) * area)
    oceanic_diffusion = float(max(0, np.square(state.oceanic_m).sum() - np.square(oceanic).sum()) * area)
    moved_fraction = np.abs(displacement).sum(axis=1)[:, None, None]
    moved_continental = float((state.continental_m * moved_fraction).sum() * area)
    moved_oceanic = float((state.oceanic_m * moved_fraction).sum() * area)
    removed = 0.0
    sutured = 0.0
    for first in range(config.plate_count):
        grad_z = (np.roll(coverage[first], -1, 0) - np.roll(coverage[first], 1, 0)) / 2
        grad_x = (np.roll(coverage[first], -1, 1) - np.roll(coverage[first], 1, 1)) / 2
        for second in range(first + 1, config.plate_count):
            relative = displacement[second] - displacement[first]
            convergence = relative[0] * grad_x + relative[1] * grad_z
            # -grad(coverage A) points from A to B, so this is approaching.
            overlap = np.minimum(coverage[first], coverage[second])
            overlap = np.where(convergence > 1e-14, overlap, 0)
            excess = np.maximum(coverage.sum(axis=0) - 1, 0)
            overlap = np.minimum(overlap, excess)
            # Ocean-rich side goes down. Equal composition ties use stable ID.
            ratio_first = oceanic[first] / np.maximum(continental[first] + oceanic[first], 1e-30)
            ratio_second = oceanic[second] / np.maximum(continental[second] + oceanic[second], 1e-30)
            down_first = ratio_first >= ratio_second
            for donor, receiver, selected in ((first, second, down_first), (second, first, ~down_first)):
                fraction = np.divide(overlap, coverage[donor], out=np.zeros(config.shape), where=coverage[donor] > 0)
                fraction *= selected
                subducted = oceanic[donor] * fraction * config.subduction_fraction
                oceanic[donor] -= subducted
                removed += float(subducted.sum() * area)
                # Continental accretion transfers ownership and retains all crust.
                joined = continental[donor] * fraction
                continental[donor] -= joined
                continental[receiver] += joined
                sutured += float(joined.sum() * area)
    total_coverage = coverage.sum(axis=0)
    gap = np.maximum(1 - total_coverage, 0)
    owner = coverage.argmax(axis=0)
    addition = gap * config.oceanic_thickness_m * config.rift_fraction
    for plate in range(config.plate_count):
        selected = owner == plate
        oceanic[plate] += addition * selected
        coverage[plate] += gap * selected
    coverage /= coverage.sum(axis=0)
    origin = np.array((config.origin_x_m, config.origin_z_m))
    extent = np.array(config.shape[::-1]) * config.cell_size_m
    seeds = (state.plate_seeds_m - origin + state.velocities_m_per_step * config.time_step) % extent + origin
    final = CrustState(coverage, continental, oceanic, seeds, state.velocities_m_per_step.copy(), state.step + 1, state.formation)
    final_c = float(continental.sum() * area)
    final_o = float(oceanic.sum() * area)
    added = float(addition.sum() * area)
    budget = {"step": final.step, "initial_continental_m3": before_c, "initial_oceanic_m3": before_o,
              "final_continental_m3": final_c, "final_oceanic_m3": final_o,
              "rift_oceanic_added_m3": added, "subducted_oceanic_m3": removed,
              "sutured_continental_m3": sutured,
              "advection_continental_residual_m3": transport_c,
              "advection_oceanic_residual_m3": transport_o,
              "advected_continental_m3": moved_continental,
              "advected_oceanic_m3": moved_oceanic,
              "continental_balance_residual_m3": final_c - before_c,
              "oceanic_balance_residual_m3": final_o - before_o - added + removed,
              "advection_continental_l2_loss_m4": diffusion,
              "advection_oceanic_l2_loss_m4": oceanic_diffusion,
              "max_coverage_overlap": float(np.maximum(total_coverage - 1, 0).max()),
              "gap_area_m2": float(gap.sum() * area)}
    budget.update(_boundaries(state.plate_coverage, state.velocities_m_per_step))
    return final, budget


def _validate_budget(config, before, after, budget):
    if not all(np.isfinite(value) for value in budget.values()):
        raise ValueError("nonfinite evolution budget")
    area = config.cell_size_m ** 2
    for material in ("continental", "oceanic"):
        initial = float(getattr(before, f"{material}_m").sum() * area)
        final = float(getattr(after, f"{material}_m").sum() * area)
        added = budget["rift_oceanic_added_m3"] if material == "oceanic" else 0.0
        removed = budget["subducted_oceanic_m3"] if material == "oceanic" else 0.0
        # Separate inventories: abundant continental crust cannot mask an
        # oceanic error. Fluxes set the oceanic scale even after depletion.
        scale = max(initial, final, added, removed)
        tolerance = max(_BUDGET_ABSOLUTE_TOLERANCE_M3,
                        _BUDGET_RELATIVE_TOLERANCE * scale)
        transport_tolerance = max(_BUDGET_ABSOLUTE_TOLERANCE_M3,
                                  _BUDGET_RELATIVE_TOLERANCE * initial)
        residuals = (final - initial - added + removed,
                     budget[f"{material}_balance_residual_m3"],
                     budget[f"initial_{material}_m3"] - initial,
                     budget[f"final_{material}_m3"] - final)
        if any(not np.isfinite(value) or abs(value) > tolerance for value in residuals):
            raise ValueError(f"step {after.step}: {material} material budget exceeded")
        if abs(budget[f"advection_{material}_residual_m3"]) > transport_tolerance:
            raise ValueError(f"step {after.step}: {material} advection budget exceeded")


def evolve(config, initial_state=None, *, stage_callback=None):
    """Prepare a complete isolated result; no caller arrays or files are changed."""
    _validate_config(config)
    supplied = initialize(config) if initial_state is None else initial_state
    _validate_state(config, supplied)
    initial = _copy_state(supplied)
    state = _copy_state(initial)
    budgets = []
    if stage_callback is not None:
        stage_callback(0, surface_fields(state))
    for _ in range(config.steps):
        next_state, budget = _step(config, state)
        _validate_state(config, next_state)
        _validate_budget(config, state, next_state, budget)
        state = next_state
        budgets.append(budget)
        if stage_callback is not None:
            stage_callback(len(budgets), surface_fields(state))
    fields = surface_fields(state)
    metadata = {"algorithm_version": ALGORITHM_VERSION, "config": asdict(config),
                "boundary": "periodic_plane", "array_order": "z,x", "axes": "X east, Z south",
                "velocity_unit": "m/offline-step", "time_unit": "uncalibrated offline-step",
                "seed_derivation": "SHA256(f'{world_seed}:tectonic:{purpose}'), first 8 bytes little-endian",
                "purpose_seeds": {name: _purpose_seed(config.world_seed, name) for name in ("plates", "crust", "velocity")},
                "formation": initial.formation,
                "initial_state_source": "generated" if initial_state is None else "injected",
                "status": "mechanism prototype / candidate; not TD coupled",
                "densities_kg_m3": {"mantle": 3300, "continental": 2800, "oceanic": 3000},
                "elevation_offset_m": -4500, "budget_unit": "m3",
                "numerical_error_relative_tolerance": _BUDGET_RELATIVE_TOLERANCE,
                "transport": "periodic unsplit donor-cell; L1 CFL <= 1; diffusive"}
    return EvolutionResult(initial, state, surface_fields(initial)["elevation_m"],
                           fields["elevation_m"], fields["plate_id"], fields["continental_fraction"],
                           fields["crust_thickness_m"], budgets, metadata)



# ------------------------------------------------------------------------
# 原 terrain_pipeline/tectonic_product.py
# ------------------------------------------------------------------------

SCHEMA = "tectonic-frozen-product-v2"


LEGACY_SCHEMA = "tectonic-frozen-product-v1"


LEGACY_ALGORITHM = "kinematic-crust-1"


AGGREGATE_ALGORITHM = "kinematic-crust-2"


COMPACT_ALGORITHM = "kinematic-crust-3"


TECTONIC_ALGORITHM = "kinematic-crust-4"


WORLD_SEED = 20261020


STATE_FIELDS = ("plate_coverage", "continental_m", "oceanic_m", "plate_seeds_m",
                "velocities_m_per_step")


SURFACE_FIELDS = ("elevation_m", "plate_id", "continental_fraction", "crust_thickness_m")


CORE_METADATA_FIELDS = ("algorithm_version", "config", "boundary", "array_order", "axes",
                        "velocity_unit", "time_unit", "seed_derivation", "purpose_seeds",
                        "initial_state_source", "status", "densities_kg_m3", "elevation_offset_m",
                        "budget_unit", "numerical_error_relative_tolerance", "transport")


BUDGET_FIELDS = {"step", "initial_continental_m3", "initial_oceanic_m3", "final_continental_m3",
                 "final_oceanic_m3", "rift_oceanic_added_m3", "subducted_oceanic_m3",
                 "sutured_continental_m3", "advection_continental_residual_m3",
                 "advection_oceanic_residual_m3", "continental_balance_residual_m3",
                 "oceanic_balance_residual_m3", "advection_continental_l2_loss_m4",
                 "max_coverage_overlap", "gap_area_m2", "convergent_faces", "divergent_faces",
                 "transform_faces"}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _config(config, *, legacy=False):
    values = asdict(config) if not isinstance(config, dict) else dict(config)
    values = json.loads(_json(values))
    expected = {"shape", "cell_size_m", "origin_x_m", "origin_z_m", "plate_count", "world_seed",
                "steps", "time_step", "max_speed_m_per_step", "continental_thickness_m",
                "oceanic_thickness_m", "subduction_fraction", "rift_fraction"}
    if not legacy:
        expected.update(("microcells_per_plate", "min_plate_cells"))
    if set(values) != expected:
        raise ValueError("incomplete or unsupported configuration")
    shape = values.get("shape")
    if (not isinstance(shape, list) or len(shape) != 2 or
            any(type(n) is not int or n < 2 for n in shape)):
        raise ValueError("shape must contain two integers >= 2")
    if values.get("world_seed") != WORLD_SEED:
        raise ValueError("world_seed must be 20261020")
    for name in ("cell_size_m", "time_step", "continental_thickness_m", "oceanic_thickness_m"):
        if not isinstance(values.get(name), (int, float)) or not np.isfinite(values[name]) or values[name] <= 0:
            raise ValueError(name + " must be finite and positive")
    for name in ("origin_x_m", "origin_z_m"):
        if not isinstance(values.get(name), (int, float)) or not np.isfinite(values[name]):
            raise ValueError(name + " must be finite")
    if type(values.get("plate_count")) is not int or not 1 <= values["plate_count"] <= shape[0] * shape[1]:
        raise ValueError("plate_count outside grid capacity")
    if type(values.get("steps")) is not int or values["steps"] < 0:
        raise ValueError("steps must be a nonnegative integer")
    for name in ("max_speed_m_per_step", "subduction_fraction", "rift_fraction"):
        if not isinstance(values[name], (int, float)) or not np.isfinite(values[name]) or values[name] < 0:
            raise ValueError("invalid " + name)
    if any(values[name] > 1 for name in ("subduction_fraction", "rift_fraction")):
        raise ValueError("mechanism fractions must be <= 1")
    with np.errstate(over="ignore", invalid="ignore"):
        extent = np.array(shape, dtype=float) * values["cell_size_m"]
        area = np.float64(values["cell_size_m"]) ** 2
        upper = extent[::-1] + [values["origin_x_m"], values["origin_z_m"]]
    if not np.isfinite(extent).all() or not np.isfinite(area) or not np.isfinite(upper).all():
        raise ValueError("nonfinite background extent or area")
    if values["time_step"] * values["max_speed_m_per_step"] * np.sqrt(2) > values["cell_size_m"]:
        raise ValueError("configured maximum speed exceeds conservative L1 CFL bound")
    if not legacy:
        from types import SimpleNamespace
        validate_formation(SimpleNamespace(**values))
    return values


def plan(config, *, max_memory_bytes=2_000_000_000, max_cell_plate_steps=200_000_000):
    """Conservative CPU allocation/work estimate, not a wall-clock guarantee."""
    config = _config(config)
    cells = int(config["shape"][0]) * int(config["shape"][1])
    # Two snapshots, solver temporaries, frozen copies/hash IO, flood-fill queue.
    from types import SimpleNamespace
    microcells = microcell_count(SimpleNamespace(**config))
    # Fragment graph/JSON audit and heap worst case are bounded by resolved cells.
    memory = cells * (config["plate_count"] * 8 * 40 + 2048) + microcells * 16384
    # Pairwise collision loops are quadratic in plate count.
    plate_passes = config["plate_count"] * (config["plate_count"] + 1) // 2
    geometry_work = 9 * microcells * max(1, (9 * microcells).bit_length()) + cells * max(1, cells.bit_length())
    _, shapes = shape_parameters(config["world_seed"], config["plate_count"])
    # Every resolved cell may be a split fragment: use cells, not site count.
    shape_image_visits = cells * formation_image_budget(config["shape"][::-1], shapes)
    work = cells * (plate_passes * (config["steps"] + 1) + microcells) + geometry_work + shape_image_visits
    if (not np.isfinite(max_memory_bytes) or not np.isfinite(max_cell_plate_steps) or
            max_memory_bytes <= 0 or max_cell_plate_steps <= 0):
        raise ValueError("resource budgets must be positive")
    return {"estimated_peak_memory_bytes": memory, "cell_plate_steps": work,
            "formation_microcells": microcells, "formation_shape_image_visits_bound": shape_image_visits, "formation_distance_cell_visits": cells * microcells,
            "allowed": memory <= max_memory_bytes and work <= max_cell_plate_steps,
            "max_memory_bytes": max_memory_bytes, "max_cell_plate_steps": max_cell_plate_steps,
            "estimate_basis": "40 float64 plate grids + 2048 bytes/cell graph/audit + 16384 bytes/site (9-tile Voronoi audit); streamed site/shape distances and plate pairs; shape search bound uses one fragment per cell; CPU only",
            "background_extent_m": [n * config["cell_size_m"] for n in config["shape"]],
            "config": config}


def connected_ocean(elevation_m, seed_zx=None):
    """4-neighbour periodic flood fill below datum 0.

    With no exterior on a torus, the deepest wet cell is the explicit ocean
    seed (row-major ties). Other wet components are enclosed depressions.
    """
    elevation = np.asarray(elevation_m)
    if elevation.ndim != 2 or not np.isfinite(elevation).all():
        raise ValueError("finite 2D elevation required")
    wet = elevation < 0
    ocean = np.zeros(wet.shape, dtype=np.bool_)
    if not wet.any():
        return ocean, None
    if seed_zx is None:
        seed_zx = list(np.unravel_index(np.argmin(elevation), elevation.shape))
    z, x = map(int, seed_zx)
    if not (0 <= z < wet.shape[0] and 0 <= x < wet.shape[1]) or not wet[z, x]:
        raise ValueError("ocean seed must be a submerged cell")
    queue = deque([(z, x)])
    ocean[z, x] = True
    while queue:
        z, x = queue.popleft()
        for nz, nx in (((z - 1) % wet.shape[0], x), ((z + 1) % wet.shape[0], x),
                       (z, (x - 1) % wet.shape[1]), (z, (x + 1) % wet.shape[1])):
            if wet[nz, nx] and not ocean[nz, nx]:
                ocean[nz, nx] = True
                queue.append((nz, nx))
    return ocean, [int(v) for v in seed_zx]


def _summary(array):
    return {"shape": list(array.shape), "dtype": array.dtype.str,
            "sha256": _digest(array.tobytes(order="C")),
            "min": array.min().item(), "max": array.max().item()}


def _immutable(array):
    # bytes-backed arrays cannot be made writable again by setflags().
    return np.frombuffer(array.tobytes(order="C"), dtype=array.dtype).reshape(array.shape)


class FrozenTectonicProduct:
    """Validated immutable snapshot. Construct via freeze() or load_product()."""

    def __init__(self, manifest, arrays):
        _validate(manifest, arrays)
        self._manifest_json = _json(manifest)
        self.arrays = MappingProxyType({key: _immutable(value) for key, value in arrays.items()})

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def identity(self):
        return self.manifest["identity"]

    def sample(self, x_m, z_m, *, outside="wrap", state="final"):
        """Broadcast queries; bilinear continuous fields, nearest categorical.

        outside='reject' accepts the half-open background rectangle only;
        outside='wrap' repeats the declared periodic plane in both axes.
        """
        if outside not in ("wrap", "reject") or state not in ("initial", "final"):
            raise ValueError("invalid sampling policy or state")
        config = self.manifest["config"]
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=float), np.asarray(z_m, dtype=float))
        if not np.isfinite(x).all() or not np.isfinite(z).all():
            raise ValueError("sample coordinates must be finite")
        spacing = config["cell_size_m"]
        nz, nx = config["shape"]
        local_x = (x - config["origin_x_m"]) / spacing
        local_z = (z - config["origin_z_m"]) / spacing
        if not np.isfinite(local_x).all() or not np.isfinite(local_z).all():
            raise ValueError("coordinates exceed finite grid index range")
        if outside == "reject" and (np.any((local_x < 0) | (local_x >= nx)) or
                                     np.any((local_z < 0) | (local_z >= nz))):
            raise ValueError("query outside background domain")
        gx = np.remainder(local_x, nx) - .5
        gz = np.remainder(local_z, nz) - .5
        ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
        fx, fz = gx - ix, gz - iz
        result = {}
        for name in (*SURFACE_FIELDS, "ocean_connected"):
            field = self.arrays[state + "/" + name]
            if name in ("plate_id", "ocean_connected"):
                value = field[np.floor(gz + .5).astype(np.int64) % nz,
                              np.floor(gx + .5).astype(np.int64) % nx]
            else:
                value = ((1 - fz) * ((1 - fx) * field[iz % nz, ix % nx] +
                                    fx * field[iz % nz, (ix + 1) % nx]) +
                         fz * ((1 - fx) * field[(iz + 1) % nz, ix % nx] +
                               fx * field[(iz + 1) % nz, (ix + 1) % nx]))
            result[name] = np.array(value, copy=True)
        return result


def _validate(manifest, arrays):
    if not isinstance(manifest, dict) or set(manifest) != {
            "schema", "algorithm", "config", "coordinates", "core_metadata", "steps", "budgets",
            "material_unit", "ocean_seeds_zx", "arrays", "identity"}:
        raise ValueError("incomplete or unsupported manifest")
    legacy = manifest.get("schema") == LEGACY_SCHEMA and manifest.get("algorithm") == LEGACY_ALGORITHM
    if not legacy and (manifest.get("schema") != SCHEMA or manifest.get("algorithm") not in (TECTONIC_ALGORITHM, COMPACT_ALGORITHM, AGGREGATE_ALGORITHM)):
        raise ValueError("unsupported schema or algorithm")
    config = _config(manifest["config"], legacy=legacy)
    metadata = manifest["core_metadata"]
    if (not isinstance(metadata, dict) or set(metadata) != (set(CORE_METADATA_FIELDS) if legacy else set(CORE_METADATA_FIELDS) | {"formation"}) or
            metadata["algorithm_version"] != manifest["algorithm"] or _config(metadata["config"], legacy=legacy) != config or
            metadata["boundary"] != "periodic_plane" or metadata["array_order"] != "z,x" or
            metadata["time_unit"] != "uncalibrated offline-step" or
            metadata["velocity_unit"] != "m/offline-step" or
            metadata["densities_kg_m3"] != {"mantle": 3300, "continental": 2800, "oceanic": 3000} or
            metadata["elevation_offset_m"] != -4500 or metadata["budget_unit"] != "m3"):
        raise ValueError("invalid core provenance or material units")
    expected_seeds = {purpose: int.from_bytes(hashlib.sha256(
        f"{WORLD_SEED}:tectonic:{purpose}".encode()).digest()[:8], "little")
        for purpose in ("plates", "crust", "velocity")}
    if metadata["purpose_seeds"] != expected_seeds:
        raise ValueError("invalid purpose seeds")
    if metadata["seed_derivation"] != "SHA256(f'{world_seed}:tectonic:{purpose}'), first 8 bytes little-endian":
        raise ValueError("unsupported purpose seed derivation")
    steps = manifest["steps"]
    if (not isinstance(steps, dict) or set(steps) != {"initial", "final"} or
            any(type(v) is not int or v < 0 for v in steps.values()) or
            steps["final"] - steps["initial"] != config["steps"]):
        raise ValueError("invalid offline steps")
    if (not isinstance(manifest["budgets"], list) or len(manifest["budgets"]) != config["steps"] or
            manifest["material_unit"] != "m3 per material; equivalent thickness m"):
        raise ValueError("invalid material ledger")
    for offset, row in enumerate(manifest["budgets"], 1):
        if (not isinstance(row, dict) or not BUDGET_FIELDS.issubset(row) or row.get("step") != steps["initial"] + offset or
                any(type(v) not in (int, float) or not np.isfinite(v) for v in row.values())):
            raise ValueError("invalid budget row")
        for name in ("initial_continental_m3", "initial_oceanic_m3", "final_continental_m3",
                     "final_oceanic_m3", "rift_oceanic_added_m3", "subducted_oceanic_m3",
                     "sutured_continental_m3"):
            if row[name] < 0:
                raise ValueError("negative material ledger quantity")
    if manifest.get("coordinates") != COORDINATES:
        raise ValueError("unsupported coordinate/boundary semantics")
    expected = {f"{state}/{name}" for state in ("initial", "final")
                for name in (*STATE_FIELDS, *SURFACE_FIELDS, "ocean_connected")}
    if set(arrays) != expected or set(manifest["arrays"]) != expected:
        raise ValueError("missing or unexpected product fields")
    shape = tuple(config["shape"])
    plates = config["plate_count"]
    for key, array in arrays.items():
        name = key.split("/")[1]
        target_shape = shape
        if name in STATE_FIELDS[:3]:
            target_shape = (plates, *shape)
        elif name in STATE_FIELDS[3:]:
            target_shape = (plates, 2)
        dtype = np.dtype("float64")
        if name == "plate_id":
            dtype = np.dtype("int64")
        elif name == "ocean_connected":
            dtype = np.dtype("bool")
        if array.shape != target_shape or array.dtype != dtype or not np.isfinite(array).all():
            raise ValueError("invalid field " + key)
        if _summary(array) != manifest["arrays"][key]:
            raise ValueError("field hash/summary mismatch: " + key)
        if name in ("continental_m", "oceanic_m", "crust_thickness_m") and np.any(array < 0):
            raise ValueError("negative material thickness")
        if name in ("continental_fraction", "plate_coverage") and np.any((array < 0) | (array > 1 + 1e-12)):
            raise ValueError("invalid fraction")
        if name == "plate_id" and np.any((array < 0) | (array >= plates)):
            raise ValueError("invalid plate ID")
    for state in ("initial", "final"):
        prefix = state + "/"
        if not np.allclose(arrays[prefix + "plate_coverage"].sum(axis=0), 1, rtol=0, atol=1e-9):
            raise ValueError("coverage must partition unity")
        continental = arrays[prefix + "continental_m"].sum(axis=0)
        oceanic = arrays[prefix + "oceanic_m"].sum(axis=0)
        thickness = continental + oceanic
        fraction = np.divide(continental, thickness, out=np.zeros_like(thickness), where=thickness > 0)
        derived = {"elevation_m": continental * (1 - 2800 / 3300) + oceanic * (1 - 3000 / 3300) - 4500,
                   "plate_id": arrays[prefix + "plate_coverage"].argmax(axis=0),
                   "continental_fraction": fraction, "crust_thickness_m": thickness}
        for name, expected_field in derived.items():
            if not np.array_equal(arrays[prefix + name], expected_field):
                raise ValueError("surface inconsistent with crust: " + name)
        seed_positions = arrays[prefix + "plate_seeds_m"] - [config["origin_x_m"], config["origin_z_m"]]
        if np.any(seed_positions < 0) or np.any(seed_positions >= np.array(shape[::-1]) * config["cell_size_m"]):
            raise ValueError("plate seeds outside background")
        ocean, seed = connected_ocean(arrays[prefix + "elevation_m"])
        if seed != manifest["ocean_seeds_zx"][state] or not np.array_equal(ocean, arrays[prefix + "ocean_connected"]):
            raise ValueError("invalid ocean connectivity")
    if not legacy:
        geometry = metadata["formation"]
        expected_formation = ({TECTONIC_ALGORITHM: "periodic-voronoi-shaped-core-growth-1",
                               COMPACT_ALGORITHM: "periodic-voronoi-core-growth-1",
                               AGGREGATE_ALGORITHM: "periodic-voronoi-adjacency-1"}[manifest["algorithm"]])
        if geometry is not None and (not isinstance(geometry, dict) or geometry.get("version") != expected_formation):
            raise ValueError("algorithm and formation geometry disagree")
        validate_geometry(config, metadata["formation"], arrays["initial/plate_id"], metadata["initial_state_source"])
    previous = {material: float(arrays["initial/" + material + "_m"].sum() * config["cell_size_m"] ** 2)
                for material in ("continental", "oceanic")}
    for row in manifest["budgets"]:
        for material in previous:
            if not np.isclose(row["initial_" + material + "_m3"], previous[material], rtol=1e-12, atol=1e-3):
                raise ValueError("disconnected material ledger")
            previous[material] = row["final_" + material + "_m3"]
        for material, change in (("continental", 0.),
                                 ("oceanic", row["rift_oceanic_added_m3"] - row["subducted_oceanic_m3"])):
            if not np.isclose(row["final_" + material + "_m3"],
                              row["initial_" + material + "_m3"] + change, rtol=1e-12, atol=1e-3):
                raise ValueError("material ledger does not close")
    for material, volume in previous.items():
        actual = float(arrays["final/" + material + "_m"].sum() * config["cell_size_m"] ** 2)
        if not np.isclose(actual, volume, rtol=1e-12, atol=1e-3):
            raise ValueError("final material volume does not match ledger")
    payload = dict(manifest)
    identity = payload.pop("identity", None)
    if identity != _digest(_json(payload).encode()):
        raise ValueError("product identity mismatch")


COORDINATES = {"axes": "X east, Z south; arrays [z,x]", "length_unit": "m",
               "height_datum_m": 0, "grid": "cell centres at origin+(index+0.5)*spacing",
               "boundary": "periodic-plane", "time_unit": "uncalibrated offline step",
               "ocean_rule": "4-neighbour periodic component of deepest submerged cell; row-major tie"}


def freeze(config, result):
    """Copy and validate a core EvolutionResult into a stable content identity."""
    config = _config(config)
    arrays = {}
    ocean_seeds = {}
    for label, state in (("initial", result.initial), ("final", result.final)):
        for name in STATE_FIELDS:
            arrays[label + "/" + name] = np.array(getattr(state, name), dtype=np.float64, copy=True)
        fields = surface_fields(state)
        for name in SURFACE_FIELDS:
            arrays[label + "/" + name] = np.array(fields[name], dtype=np.int64 if name == "plate_id" else np.float64)
        ocean, seed = connected_ocean(fields["elevation_m"])
        arrays[label + "/ocean_connected"] = ocean
        ocean_seeds[label] = seed
    manifest = {"schema": SCHEMA, "algorithm": TECTONIC_ALGORITHM, "config": config,
                "coordinates": COORDINATES,
                "core_metadata": {key: result.metadata[key] for key in (*CORE_METADATA_FIELDS, "formation")},
                "steps": {"initial": result.initial.step, "final": result.final.step},
                "budgets": result.budgets, "material_unit": "m3 per material; equivalent thickness m",
                "ocean_seeds_zx": ocean_seeds, "arrays": {k: _summary(v) for k, v in arrays.items()}}
    manifest = json.loads(_json(manifest))
    manifest["identity"] = _digest(_json(manifest).encode())
    return FrozenTectonicProduct(manifest, arrays)


def save_product(product, path):
    """Validate a cold read before atomic no-overwrite hard-link publication."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".tectonic-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            np.savez(stream, manifest_json=np.array(_json(product.manifest)), **product.arrays)
            stream.flush()
            os.fsync(stream.fileno())
        loaded = load_product(temporary, expected_identity=product.identity)
        os.link(temporary, path)
        return loaded
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_product(path, *, expected_identity=None):
    try:
        with np.load(path, allow_pickle=False) as archive:
            if len(archive.files) != len(set(archive.files)):
                raise ValueError("duplicate archive fields")
            raw = archive["manifest_json"]
            if raw.shape != () or raw.dtype.kind != "U":
                raise ValueError("invalid manifest encoding")
            manifest = json.loads(str(raw), object_pairs_hook=_unique_object)
            arrays = {k: archive[k] for k in archive.files if k != "manifest_json"}
        product = FrozenTectonicProduct(manifest, arrays)
    except (KeyError, TypeError, OSError, EOFError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid frozen tectonic product") from error
    if expected_identity is not None and product.identity != expected_identity:
        raise ValueError("unexpected product identity")
    return product


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key: " + key)
        result[key] = value
    return result


def prepare_frozen_product(config, path, **budgets):
    """Explicit offline generation; resource rejection precedes core invocation."""
    report = plan(config, **budgets)
    if not report["allowed"]:
        raise ValueError("CPU resource budget exceeded: " + _json(report))
    if Path(path).exists():
        raise FileExistsError(path)
    return save_product(freeze(config, evolve(config)), path)



# ------------------------------------------------------------------------
# 原 terrain_pipeline/plate_td_product.py
# ------------------------------------------------------------------------

def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _identity(record):
    # Runtime and locations are provenance, not numerical content identity.
    canonical = json.loads(json.dumps(record))
    canonical.pop("source_path", None)
    generation = canonical.get("generation", {})
    generation.get("record", {}).pop("source", None)
    # These opaque IDs include model_dir before normalization. Their full
    # metadata stays below, and _check_generation validates both provenance IDs.
    generation.pop("physical_generation_identity", None)
    generation.get("physical_generation", {}).pop("conditioning_identity", None)
    generation.get("record", {}).get("config", {}).pop("model_dir", None)
    generation.get("physical_generation", {}).get("config", {}).pop("model_dir", None)
    generation.get("physical_generation", {}).get("upstream", {}).pop("source", None)
    for key in ("wall_clock_s", "peak_child_rss_mib", "peak_child_gpu_mib", "allocated_peak_mib", "reserved_peak_mib"):
        generation.pop(key, None)
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _validate_model(config, metadata):
    from diffusion.paths import inside
    model_dir = inside(config.model_dir)
    for name, entry in metadata["model"]["files"].items():
        file = (model_dir / name).resolve()
        if not file.is_relative_to(model_dir.resolve()) or not file.is_file() or file.stat().st_size != entry["bytes"] or digest(file) != entry["sha256"]:
            raise ValueError("model content mismatch: " + name)


def _check_generation(generation):
    config = PhysicalGenerationConfig.from_record(generation["record"]["config"])
    identity, metadata = config.generation_identity()
    if generation["physical_generation_identity"] != identity or generation["physical_generation"] != json.loads(json.dumps(metadata)):
        raise ValueError("model or physical generation identity mismatch")
    files = [Path(__file__).parents[1] / "diffusion/plate_td_backend.py",
             Path(__file__).parents[1] / "diffusion/plate_td_conditioning.py",
             Path(__file__), Path(__file__).with_name("coastal_terrain.py"),
             Path(__file__).parents[1] / "diffusion/geographic_noise.py"]
    _validate_model(config, metadata)
    if not published_algorithm_matches("plate_td_product", generation["source_sha256"], {p.name: digest(p) for p in files}):
        raise ValueError("source implementation identity mismatch")


def _macro(product, origin, side):
    out = np.empty((side, side), np.float32)
    x = (origin[0] + np.arange(side))[None, :] * 30.0
    for start in range(0, side, 32):
        z = (origin[1] + np.arange(start, min(start + 32, side)))[:, None] * 30.0
        out[start:start + len(z)] = product.sample(x, z, outside="reject")["elevation_m"]
    return out


def prepare_plate_source(source, output, origin, side, config, *, compose_coast, expected_identity, relief_strength=0.0):
    from terrain_pipeline.coastal_terrain import relief, CoastalParameters, coastal_support, compose, classify
    from diffusion.plate_td_backend import generate
    from diffusion.physical_config import PhysicalGenerationConfig
    """Run real TD and stage a new directory; never overwrite an existing product."""
    if type(compose_coast) is not bool or type(relief_strength) not in (int, float) or not math.isfinite(relief_strength) or not 0 <= relief_strength <= 1 or (not compose_coast and relief_strength != 0):
        raise ValueError("invalid coastal relief strength")
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if type(side) is not int or not 1 <= side <= 1337 or len(origin) != 2 or any(type(v) is not int for v in origin):
        raise ValueError("invalid source window")
    if compose_coast and side <= 400:
        raise ValueError("coastal product needs 200 cells of support on each side")
    # Conservative bounded working set, separate from worker's existing 4 GiB cap.
    estimated = 300_000_000 + side * side * 160
    if psutil.virtual_memory().available < estimated:
        raise ValueError("insufficient available host memory for staging")
    parent = output.parent.resolve()
    if not parent.is_dir() or shutil.disk_usage(parent).free < 100_000_000 + side * side * 50:
        raise ValueError("missing parent or insufficient disk space")
    product = load_product(source, expected_identity=expected_identity)
    # Verify extent before starting a GPU worker.
    product.sample(np.array([origin[0], origin[0] + side - 1]) * 30.,
                   np.array([origin[1], origin[1] + side - 1]) * 30., outside="reject")
    _, model_metadata = config.generation_identity()
    _validate_model(config, model_metadata)
    raw, climate, generation = generate(source, origin, side, config, expected_identity=expected_identity)
    macro = _macro(product, origin, side)
    arrays = {"raw_td": raw, "td_climate": climate, "macro": macro}
    parameters = asdict(CoastalParameters())
    anchor = None
    if compose_coast:
        # Anchors are certified by the frozen macro ocean mask, then checked wet
        # on the composed bed. Choose deterministically within the valid core.
        x = (origin[0] + np.arange(200, side - 200))[None, :] * 30.
        z = (origin[1] + np.arange(200, side - 200))[:, None] * 30.
        connected = product.sample(x, z, outside="reject")["ocean_connected"]
        candidates = np.argwhere(connected & (macro[200:-200, 200:-200] < 0))
        if not len(candidates):
            raise ValueError("no certified ocean anchor in valid core")
        macro_anchor = tuple((candidates[0] + 200).tolist())
        params = CoastalParameters()
        support = coastal_support(macro, params, anchors=[macro_anchor])
        bed = compose(raw, macro, params, support=support)
        margin = 200 - params.validate()
        valid = np.ones(bed.shape, dtype=bool)
        valid[:margin, :] = valid[-margin:, :] = False
        valid[:, :margin] = valid[:, -margin:] = False
        relief_array = relief(bed, valid, support[96:-96, 96:-96],
                              ((origin[0] + 96) * 30., (origin[1] + 96) * 30.), strength=relief_strength)
        bed = (bed + relief_array).astype(np.float32)
        arrays["relief"] = relief_array
        for candidate in candidates:
            az, ax = (candidate + margin).tolist()
            if bed[az, ax] < 0:
                anchor = [az, ax]
                break
        if anchor is None:
            raise ValueError("no certified ocean anchor remains wet in final bed")
        codes, shore = classify(bed, valid, [anchor])
        arrays.update(bed=bed, valid=valid, classification=codes, shoreline=shore)
    tmp = Path(tempfile.mkdtemp(prefix=".plate-td-", dir=parent))
    try:
        hashes = {}
        for name, array in arrays.items():
            np.save(tmp / (name + ".npy"), array, allow_pickle=False)
            hashes[name] = digest(tmp / (name + ".npy"))
        manifest = {"schema": "plate-td-source-v1", "source_path": str(Path(source).resolve()),
                    "plate_identity": expected_identity, "world_seed": WORLD_SEED,
                    "origin_native_xz": list(origin), "source_shape_zx": [side, side],
                    "spacing_m": 30, "sea_m": 0, "generation": generation,
                    "parameters": parameters, "coastal": compose_coast, "relief_strength": relief_strength, "anchor_bed_zx": anchor,
                    "bed_origin_native_xz": [origin[0] + 96, origin[1] + 96] if compose_coast else None,
                    "valid_margin_bed_cells": 104 if compose_coast else None,
                    "climate_support_note": "TD climate; conditioning uses approximate rebase of clipped physical climate, retaining procedural maritime and orographic terms. No tectonic wind model or 22.5km downstream halo claimed.",
                    "files": hashes}
        manifest["identity"] = _identity(manifest)
        (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        read_plate_source(tmp)
        os.rename(tmp, output)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return read_plate_source(output)


def read_plate_source(path, expected_identity=None):
    from terrain_pipeline.coastal_terrain import relief, CoastalParameters, coastal_support, compose, classify
    from diffusion.plate_td_conditioning import WORLD_SEED
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    identity = manifest.pop("identity")
    if identity != _identity(manifest) or (expected_identity is not None and identity != expected_identity):
        raise ValueError("manifest identity mismatch")
    manifest["identity"] = identity
    if (manifest["schema"] != "plate-td-source-v1" or manifest["world_seed"] != WORLD_SEED or manifest["spacing_m"] != 30 or manifest["sea_m"] != 0 or type(manifest["coastal"]) is not bool or len(manifest["origin_native_xz"]) != 2 or any(type(v) is not int for v in manifest["origin_native_xz"]) or manifest["parameters"] != asdict(CoastalParameters())):
        raise ValueError("source contract mismatch")
    strength = manifest["relief_strength"]
    if type(strength) not in (int, float) or not math.isfinite(strength) or not 0 <= strength <= 1 or (not manifest["coastal"] and strength != 0):
        raise ValueError("invalid relief strength")
    if not manifest["coastal"] and any(manifest[k] is not None for k in ("anchor_bed_zx", "bed_origin_native_xz", "valid_margin_bed_cells")):
        raise ValueError("unexpected coastal metadata")
    record = manifest["generation"]["record"]
    if (record["source"] != manifest["source_path"] or record["plate_identity"] != manifest["plate_identity"] or record["seed"] != WORLD_SEED or record["origin"] != manifest["origin_native_xz"] or record["side"] != manifest["source_shape_zx"][0]):
        raise ValueError("generation record mismatch")
    _check_generation(manifest["generation"])
    names = {"raw_td", "td_climate", "macro"}
    if manifest["coastal"]:
        names |= {"bed", "valid", "classification", "shoreline", "relief"}
    if set(manifest["files"]) != names:
        raise ValueError("wrong product files")
    arrays = {}
    for name in names:
        file = path / (name + ".npy")
        if digest(file) != manifest["files"][name]:
            raise ValueError("array hash mismatch")
        arrays[name] = np.load(file, mmap_mode="r", allow_pickle=False)
    side, cols = manifest["source_shape_zx"]
    if type(side) is not int or side != cols or not 1 <= side <= 1337 or arrays["raw_td"].shape != (side, side) or arrays["macro"].shape != (side, side) or arrays["td_climate"].shape != (5, side, side):
        raise ValueError("source shape mismatch")
    for name in ("raw_td", "macro", "td_climate"):
        if arrays[name].dtype != np.float32 or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid source array")
    product = load_product(manifest["source_path"], expected_identity=manifest["plate_identity"])
    if product.manifest["config"]["world_seed"] != WORLD_SEED:
        raise ValueError("plate seed mismatch")
    origin = manifest["origin_native_xz"]
    if not np.array_equal(arrays["macro"], _macro(product, origin, side)):
        raise ValueError("macro source mismatch")
    if manifest["coastal"]:
        params = CoastalParameters(**manifest["parameters"])
        if side <= 400 or manifest["valid_margin_bed_cells"] != 104 or params != CoastalParameters() or manifest["bed_origin_native_xz"] != [v + 96 for v in manifest["origin_native_xz"]]:
            raise ValueError("coastal coordinates or parameters mismatch")
        shape = (side - 192, side - 192)
        if any(arrays[name].shape != shape for name in ("bed", "valid", "classification", "shoreline", "relief")) or arrays["relief"].dtype != np.float32 or not np.isfinite(arrays["relief"]).all():
            raise ValueError("invalid coastal array shapes or relief")
        if (arrays["bed"].shape != (side - 192, side - 192) or arrays["bed"].dtype != np.float32 or not np.isfinite(arrays["bed"]).all() or arrays["valid"].dtype != np.bool_ or arrays["classification"].dtype != np.uint8 or arrays["shoreline"].dtype != np.bool_):
            raise ValueError("invalid coastal arrays")
        valid = np.ones((side - 192, side - 192), bool)
        valid[:104, :] = valid[-104:, :] = False
        valid[:, :104] = valid[:, -104:] = False
        if not np.array_equal(arrays["valid"], valid):
            raise ValueError("invalid support")
        x = (origin[0] + np.arange(200, side - 200))[None, :] * 30.
        z = (origin[1] + np.arange(200, side - 200))[:, None] * 30.
        connected = product.sample(x, z, outside="reject")["ocean_connected"]
        candidates = np.argwhere(connected & (arrays["macro"][200:-200, 200:-200] < 0))
        if not len(candidates):
            raise ValueError("missing macro ocean anchor")
        macro_anchor = tuple((candidates[0] + 200).tolist())
        support = coastal_support(arrays["macro"], params, anchors=[macro_anchor])
        expected_bed = compose(arrays["raw_td"], arrays["macro"], params, support=support)
        expected_relief = relief(expected_bed, valid, support[96:-96, 96:-96],
                                 ((origin[0] + 96) * 30., (origin[1] + 96) * 30.), strength=strength)
        if not np.array_equal(expected_relief, arrays["relief"]):
            raise ValueError("relief derivation mismatch")
        expected_bed = (expected_bed + expected_relief).astype(np.float32)
        if not np.array_equal(expected_bed, arrays["bed"]):
            raise ValueError("bed derivation mismatch")
        anchor = manifest["anchor_bed_zx"]
        if not any(np.array_equal(candidate + 104, anchor) for candidate in candidates):
            raise ValueError("anchor is not certified macro ocean")
        codes, shore = classify(arrays["bed"], valid, [manifest["anchor_bed_zx"]])
        if not np.array_equal(codes, arrays["classification"]) or not np.array_equal(shore, arrays["shoreline"]):
            raise ValueError("classification mismatch")
    return manifest, arrays

CATEGORY = "A"

