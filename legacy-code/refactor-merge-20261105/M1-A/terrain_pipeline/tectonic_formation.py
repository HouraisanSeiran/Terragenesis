"""Resolved periodic Voronoi aggregation (geometry only, no moving microplates).

Sites are unique cell centres. Nearest-site ties use site ID. Raster components
use four face neighbours including torus seams: disconnected samples of one
continuous Voronoi cell become separate nodes, each retained and merged along
a real resolved face. No material is discarded. The minimum resolved plate
area is min_plate_cells * spacing**2 (default four full grid cells); this is
a resolution floor, not a claim about a physical minimum plate size.

Dispersed core microfragments grow across real faces, prioritized by periodic
core shape gauge (85%) plus accumulated neighbour-site path length (15%). This
keeps multi-edge polygon outlines with mixed circle/ellipse/triangle priors.
Shape parameters use an independent world-seed stream; long plates are allowed. If the
remaining minimum area is too small, fail explicitly, without reseeding or
retrying. A feasible cell-count bound alone does not guarantee that a particular
sampled microcell graph can satisfy the requested floor. Sites/assignment,
component raster, adjacency and ownership are saved for independent audit.
Nearest-site work is streamed in O(grid cells) storage, never [site,z,x].
"""
import heapq

from terrain_pipeline.tectonic_shapes import shape_parameters, periodic_shape_distance

import numpy as np

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
