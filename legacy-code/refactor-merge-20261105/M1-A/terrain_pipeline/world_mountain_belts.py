"""Finite coarse mountain belts on an immutable tectonic background.

This is declared procedural geomorphology, not a tectonic history, erosion
simulation or TD surface. Absolute metre coordinates use X east, Z south.
Preparation freezes a spacing-independent inventory; query only reads a DEM.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType

import numpy as np
from scipy.ndimage import gaussian_filter1d, label

from diffusion.geographic_noise import field as noise_field
from terrain_pipeline.tectonic_product import FrozenTectonicProduct
from terrain_pipeline.common_infra import WORLD_SEED


SCHEMA = "world-mountain-belts-v1"
ALGORITHM_VERSION = "curved-world-belts-3"
FLOAT_FIELDS = ("raw_elevation_m", "base_elevation_m", "mountain_height_m",
                "basin_depth_m", "elevation_m", "continental_fraction", "crust_thickness_m")
MASK_FIELDS = ("ocean_connected", "inland_depression", "valid")
BASE_FIELDS = ("elevation_m", "continental_fraction", "crust_thickness_m",
               "ocean_connected", "plate_id")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _seed(world_seed, purpose):
    return int.from_bytes(hashlib.sha256(
        (str(world_seed) + ":world-mountain-belts:" + purpose).encode()).digest()[:8], "big")


def _integer(value, minimum):
    return isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)) and value >= minimum


@dataclass(frozen=True)
class WorldMountainConfig:
    spacing_m: float = 5000.0
    world_seed: int = WORLD_SEED
    flatten_base: bool = True
    amplitude_scale: float = 1.0
    thick_crust_threshold_m: float = 40000.0
    min_belt_length_m: float = 40000.0
    max_belts: int = 24
    max_cells: int = 1000000
    max_source_cells: int = 2000000
    max_segments: int = 4096

    def __post_init__(self):
        for name in ("spacing_m", "amplitude_scale", "thick_crust_threshold_m", "min_belt_length_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not np.isfinite(value) or value < 0:
                raise ValueError("invalid " + name)
        if self.spacing_m < 1000 or self.thick_crust_threshold_m <= 0 or self.min_belt_length_m <= 0:
            raise ValueError("spacing must be >=1000 m and physical thresholds positive")
        if not _integer(self.world_seed, 0) or not isinstance(self.flatten_base, bool):
            raise ValueError("invalid seed or base policy")
        for name in ("max_belts", "max_cells", "max_source_cells", "max_segments"):
            if not _integer(getattr(self, name), 1):
                raise ValueError("invalid " + name)


def _immutable(array):
    return np.frombuffer(array.tobytes(order="C"), dtype=array.dtype).reshape(array.shape)


def _summary(array):
    return {"shape": list(array.shape), "dtype": array.dtype.str,
            "sha256": _digest(array.tobytes(order="C"))}


def _coordinates(x_m, z_m, grid):
    x, z = np.broadcast_arrays(np.asarray(x_m, dtype=float), np.asarray(z_m, dtype=float))
    if not np.isfinite(x).all() or not np.isfinite(z).all():
        raise ValueError("coordinates must be finite")
    ox, oz = grid["origin_x_m"], grid["origin_z_m"]
    width, height = grid["extent_m"]
    if np.any((x < ox) | (x >= ox + width) | (z < oz) | (z >= oz + height)):
        raise ValueError("query outside prepared finite domain")
    return x, z


def _sample_arrays(arrays, grid, x, z, categorical=()):
    """Clamp BOTH neighbors before indexing; never borrow opposite-edge data."""
    nz, nx = grid["shape"]
    gx = np.clip((x - grid["origin_x_m"]) / grid["spacing_m"] - .5, 0, nx - 1)
    gz = np.clip((z - grid["origin_z_m"]) / grid["spacing_m"] - .5, 0, nz - 1)
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    fx, fz = gx - ix, gz - iz
    right, below = np.minimum(ix + 1, nx - 1), np.minimum(iz + 1, nz - 1)
    result = {}
    for name, array in arrays.items():
        if name in categorical:
            value = array[np.floor(gz + .5).astype(int), np.floor(gx + .5).astype(int)]
        else:
            value = ((1 - fz) * ((1 - fx) * array[iz, ix] + fx * array[iz, right])
                     + fz * ((1 - fx) * array[below, ix] + fx * array[below, right]))
        result[name] = np.array(value, copy=True)
    return result


def _base_grid(config):
    nz, nx = config["shape"]
    spacing = config["cell_size_m"]
    return {"shape": [nz, nx], "spacing_m": spacing,
            "origin_x_m": config["origin_x_m"], "origin_z_m": config["origin_z_m"],
            "extent_m": [nx * spacing, nz * spacing]}


def _candidate(points, weights, evidence, minimum_length, spacing):
    centre = np.average(points, axis=0, weights=weights)
    offset = points - centre
    eigenvalues, vectors = np.linalg.eigh(offset.T @ (offset * weights[:, None]))
    direction = vectors[:, -1]
    if direction[0] < 0 or (direction[0] == 0 and direction[1] < 0):
        direction = -direction
    along = offset @ direction
    span = float(np.ptp(along))
    aspect = float(np.sqrt(max(eigenvalues[-1], 1) / max(eigenvalues[0], 1)))
    record = {**evidence, "point_count": len(points), "span_m": span, "aspect": aspect}
    if span < minimum_length:
        return None, {**record, "reason": "too_short"}
    if evidence["kind"] == "thick_crust_morphology_prior" and aspect < 1.4:
        return None, {**record, "reason": "broad_thick_crust_retained_as_base"}
    # A component has already been split at ocean/gaps; PCA orders that component only.
    bins = min(20, max(3, int(span / (2 * spacing)) + 1))
    edges = np.linspace(float(along.min()) - .01, float(along.max()) + .01, bins + 1)
    vertices = []
    for low, high in zip(edges[:-1], edges[1:]):
        take = (along >= low) & (along < high)
        if np.any(take):
            vertices.append(np.average(points[take], axis=0, weights=weights[take]))
    vertices = np.asarray(vertices)
    vertices = gaussian_filter1d(vertices, .65, axis=0, mode="nearest")
    record["vertices_m"] = vertices.tolist()
    record["strength"] = float(np.average(weights))
    return record, None


def _extract_candidates(base, config):
    arrays = base.arrays
    source = base.manifest["config"]
    ids = arrays["final/plate_id"]
    fraction = arrays["final/continental_fraction"]
    thickness = arrays["final/crust_thickness_m"]
    ocean = arrays["final/ocean_connected"].astype(bool)
    velocity = arrays["final/velocities_m_per_step"]
    spacing = source["cell_size_m"]
    ox, oz = source["origin_x_m"], source["origin_z_m"]
    masks = {}
    counts = {"convergent_faces": 0, "divergent_faces": 0, "transform_faces": 0,
              "continental_convergent_faces": 0}
    for axis, component in ((1, 0), (0, 1)):
        left = (slice(None), slice(None, -1)) if axis == 1 else (slice(None, -1), slice(None))
        right = (slice(None), slice(1, None)) if axis == 1 else (slice(1, None), slice(None))
        a, b = ids[left], ids[right]
        boundary = a != b
        normal = velocity[b, component] - velocity[a, component]
        for name, selected in (("convergent_faces", normal < -1e-10),
                               ("divergent_faces", normal > 1e-10),
                               ("transform_faces", abs(normal) <= 1e-10)):
            counts[name] += int(np.count_nonzero(boundary & selected))
        continental = ((fraction[left] + fraction[right]) * .5 > .5) & (~ocean[left] | ~ocean[right])
        rows, cols = np.nonzero(boundary & (normal < -1e-10) & continental)
        counts["continental_convergent_faces"] += len(rows)
        for row, col in zip(rows, cols):
            pair = tuple(sorted((int(a[row, col]), int(b[row, col]))))
            mask = masks.setdefault(pair, np.zeros(ids.shape, dtype=bool))
            mask[row, col] = True
            mask[row + (axis == 0), col + (axis == 1)] = True
    candidates, rejected = [], []
    for pair, mask in sorted(masks.items()):
        # Eight-neighbor connects stair steps but does not dilate across spatial gaps.
        components, count = label(mask, np.ones((3, 3), dtype=int))
        for index in range(1, count + 1):
            rows, cols = np.nonzero(components == index)
            points = np.column_stack((ox + (cols + .5) * spacing, oz + (rows + .5) * spacing))
            candidate, refusal = _candidate(points, np.ones(len(points)),
                {"kind": "convergent_boundary", "plate_pair": list(pair),
                 "source_id": "convergence-%d-%d-%d" % (*pair, int(rows[0] * ids.shape[1] + cols[0]))},
                config.min_belt_length_m, spacing)
            (candidates if candidate else rejected).append(candidate or refusal)
    thick = (~ocean) & (fraction > .5) & (thickness > config.thick_crust_threshold_m)
    components, count = label(thick)
    counts["thick_crust_cells"] = int(thick.sum())
    counts["thick_crust_components"] = int(count)
    for index in range(1, count + 1):
        rows, cols = np.nonzero(components == index)
        points = np.column_stack((ox + (cols + .5) * spacing, oz + (rows + .5) * spacing))
        weights = np.maximum(1, thickness[rows, cols] / config.thick_crust_threshold_m)
        candidate, refusal = _candidate(points, weights,
            {"kind": "thick_crust_morphology_prior", "threshold_m": config.thick_crust_threshold_m,
             "source_id": "thick-%d" % int(rows[0] * ids.shape[1] + cols[0])},
            config.min_belt_length_m, spacing)
        (candidates if candidate else rejected).append(candidate or refusal)
    candidates.sort(key=lambda c: (-c["span_m"] * min(c["strength"], 2), c["source_id"]))
    rejected.extend({**c, "reason": "belt_budget"} for c in candidates[config.max_belts:])
    return candidates[:config.max_belts], rejected, counts


def _normals(points):
    tangent = np.gradient(points, axis=0)
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1)[:, None], 1)
    return np.column_stack((-tangent[:, 1], tangent[:, 0]))


def _ridge_record(points, source_id, role, width, amplitude, rng, style):
    powers = {"folded_ranges": (1.25, 1.8), "block_plateau_margin": (3.2, 4.2),
              "worn_ranges": (2., 2.6)}
    return {"source_id": source_id, "role": role, "style": style,
            "vertices_m": points.tolist(), "width_m": float(width),
            "amplitude_m": float(amplitude), "peak_spacing_m": float(rng.uniform(45000, 85000)),
            "phase": float(rng.uniform(0, 2 * np.pi)), "cross_power": float(rng.uniform(*powers[style]))}


def _inventory(base, config):
    candidates, rejected, counts = _extract_candidates(base, config)
    ridges, basins, seeds = [], [], {}
    for index, candidate in enumerate(candidates):
        source_id = candidate["source_id"]
        seed = _seed(config.world_seed, source_id)
        seeds[source_id] = seed
        rng = np.random.default_rng(seed)
        points = np.asarray(candidate["vertices_m"])
        normal = _normals(points)
        style = ("folded_ranges", "block_plateau_margin", "worn_ranges")[index % 3]
        width = float(rng.uniform(14000, 22000))
        amplitude = float(rng.uniform(1500, 2600))
        if style == "block_plateau_margin":
            width *= 1.4
            amplitude *= 1.2
        elif style == "worn_ranges":
            width *= 1.3
            amplitude *= .55
        amplitude *= config.amplitude_scale
        t = np.linspace(0, 1, len(points))
        points = points + normal * (np.sin(t * 2 * np.pi + rng.uniform(0, 6)) * width * .25)[:, None]
        # The parent curve follows its actual connected candidate; no end extension.
        ridges.append(_ridge_record(points, source_id, "main", width, amplitude, rng, style))
        normal = _normals(points)
        parallel_sides = (-1,) if style == "block_plateau_margin" else (-1, 1)
        parallel_amplitude = .32 if style == "worn_ranges" else .68
        for side in parallel_sides:
            offset = width * float(rng.uniform(1.65, 2.05))
            parallel = points + side * offset * normal
            ridges.append(_ridge_record(parallel, source_id, "parallel", width * .58,
                                        amplitude * parallel_amplitude, rng, style))
            centre = points[len(points) // 2] + side * offset * .55 * normal[len(points) // 2]
            tangent = points[-1] - points[0]
            tangent /= max(np.linalg.norm(tangent), 1)
            basins.append({"source_id": source_id, "centre_m": centre.tolist(),
                           "axis": tangent.tolist(), "semi_length_m": max(25000., candidate["span_m"] * .19),
                           "semi_width_m": width * .5, "depth_m": amplitude * .22,
                           "kind": "declared_intermontane_lowland_not_lake"})
        for branch_index, position in enumerate((.28, .68)):
            anchor_index = int(position * (len(points) - 1))
            anchor = points[anchor_index]
            tangent = points[min(anchor_index + 1, len(points) - 1)] - points[max(0, anchor_index - 1)]
            tangent /= max(np.linalg.norm(tangent), 1)
            side = 1 if branch_index else -1
            branch_t = np.linspace(0, 1, 5)
            length = min(candidate["span_m"] * .30, width * 4.0)
            branch = (anchor + branch_t[:, None] * length * (.55 * tangent + side * normal[anchor_index])
                      + np.sin(branch_t * np.pi)[:, None] * normal[anchor_index] * width * .25)
            branch_amplitude = .25 if style == "worn_ranges" else .55
            ridges.append(_ridge_record(branch, source_id, "oblique_branch", width * .50,
                                        amplitude * branch_amplitude, rng, style))
    segments = sum(len(r["vertices_m"]) - 1 for r in ridges)
    if segments > config.max_segments:
        raise ValueError("curve segment budget exceeded before geometry evaluation")
    return {"candidates": candidates, "rejected_candidates": rejected, "boundary_counts": counts,
            "ridges": ridges, "basins": basins, "segments": segments,
            "purpose_seeds": seeds,
            "limitation": "raster face normals and thick-crust priors; no reconstructed tectonic history"}


def _ridge_height(ridge, points, x, z):
    """Maximum of continuous segment heights, including their along-axis attributes.

    Selecting only a nearest segment before evaluating peak phase is discontinuous
    on segment bisectors. Each clamped projection here is continuous on its own,
    and a finite maximum of continuous heights remains C0 (not necessarily C1).
    """
    lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = float(lengths.sum())
    height = np.zeros(x.shape)
    if total <= 0:
        return height
    cumulative = 0.
    width = ridge["width_m"]
    power = ridge["cross_power"]
    cutoff = np.exp(-3 ** power)
    for start, stop, length in zip(points[:-1], points[1:], lengths):
        if length <= 0:
            continue
        delta = stop - start
        t = np.clip(((x - start[0]) * delta[0] + (z - start[1]) * delta[1]) / length ** 2, 0, 1)
        distance = np.hypot(x - start[0] - t * delta[0], z - start[1] - t * delta[1])
        along = cumulative + t * length
        profile = np.maximum(0, (np.exp(-(distance / width) ** power) - cutoff) / (1 - cutoff))
        # Clip tiny sine roundoff at the final endpoint before the fractional power.
        end = np.maximum(0, np.sin(np.pi * np.clip(along / total, 0, 1))) ** .45
        peaks = (.62 + .28 * np.cos(along * 2 * np.pi / ridge["peak_spacing_m"] + ridge["phase"])
                 + .10 * np.cos(along * 2 * np.pi / (ridge["peak_spacing_m"] * .47) + ridge["phase"]))
        height = np.maximum(height, ridge["amplitude_m"] * profile * end * peaks)
        cumulative += float(length)
    return height


def _coast_gate(ocean, grid, x, z):
    """Continuous distance to the union of frozen ocean-cell rectangles.

    The gate saturates one source cell inland, so a fixed 3x3 neighborhood
    contains every rectangle able to affect it. Nearest-cell ocean categories
    may switch at a face; this geometric distance is zero on both sides there.
    No ocean beyond this finite source rectangle is invented or wrapped in.
    """
    spacing = grid["spacing_m"]
    nz, nx = grid["shape"]
    ix = np.floor((x - grid["origin_x_m"]) / spacing).astype(int)
    iz = np.floor((z - grid["origin_z_m"]) / spacing).astype(int)
    distance = np.full(x.shape, spacing)
    for row_offset in (-1, 0, 1):
        row = iz + row_offset
        for col_offset in (-1, 0, 1):
            col = ix + col_offset
            inside = (row >= 0) & (row < nz) & (col >= 0) & (col < nx)
            is_ocean = inside & ocean[np.clip(row, 0, nz - 1), np.clip(col, 0, nx - 1)]
            west = grid["origin_x_m"] + col * spacing
            north = grid["origin_z_m"] + row * spacing
            dx = np.maximum(0, np.maximum(west - x, x - west - spacing))
            dz = np.maximum(0, np.maximum(north - z, z - north - spacing))
            distance = np.minimum(distance, np.where(is_ocean, np.hypot(dx, dz), spacing))
    normalized = distance / spacing
    return normalized * normalized * (3 - 2 * normalized)


def _evaluate(base_arrays, grid, config, inventory, x, z):
    values = _sample_arrays(base_arrays, grid, x, z, ("ocean_connected", "plate_id"))
    raw = values.pop("elevation_m")
    ocean = values["ocean_connected"].astype(bool)
    inland_negative = (~ocean) & (raw < 0)
    fraction = values["continental_fraction"]
    coast_distance_gate = _coast_gate(base_arrays["ocean_connected"], grid, x, z)
    # Preserve coastline signs and all sea/negative basin levels. Compress only positive land.
    base_height = raw.copy()
    if config["flatten_base"]:
        compressed = 420 * (1 - np.exp(-np.maximum(raw, 0) / 1800)) + .025 * np.maximum(raw, 0)
        base_height = raw + np.where(raw > 0, coast_distance_gate * (compressed - raw), 0)
    mountain = np.zeros(x.shape)
    basin = np.zeros(x.shape)
    texture_seed = _seed(config["world_seed"], "relief_texture")
    # Noise wavelengths are fixed physical scales; 5 km sampling remains a coarse approximation.
    for ridge in inventory["ridges"]:
        points = np.asarray(ridge["vertices_m"])
        width = ridge["width_m"]
        reach = width * 3
        take = ((x >= points[:, 0].min() - reach) & (x <= points[:, 0].max() + reach)
                & (z >= points[:, 1].min() - reach) & (z <= points[:, 1].max() + reach))
        if not np.any(take):
            continue
        local_x, local_z = x[take], z[take]
        texture = noise_field(local_x, local_z, texture_seed, 71,
                              ((65000., 1.), (25000., .45), (15000., .2)))
        height = _ridge_height(ridge, points, local_x, local_z) * (1 + .18 * texture)
        # A max envelope does not turn crossings into spuriously doubled isolated peaks.
        mountain[take] = np.maximum(mountain[take], height)
    for depression in inventory["basins"]:
        cx, cz = depression["centre_m"]
        ux, uz = depression["axis"]
        dx, dz = x - cx, z - cz
        radial = (((dx * ux + dz * uz) / depression["semi_length_m"]) ** 2
                  + ((-dx * uz + dz * ux) / depression["semi_width_m"]) ** 2)
        depth = depression["depth_m"] * np.maximum(0, 1 - radial) ** 2
        basin = np.maximum(basin, depth)
    gate = np.clip((fraction - .45) / .4, 0, 1)
    gate = gate * gate * (3 - 2 * gate)
    # A continuous coast gate removes added relief near zero without relocating the coast.
    coast_gate = np.clip(np.maximum(raw, 0) / 500., 0, 1)
    coast_gate = coast_gate * coast_gate * (3 - 2 * coast_gate)
    gate *= coast_gate * coast_distance_gate
    mountain *= gate
    basin *= gate
    # Positive land stays positive; original inland negative depressions are preserved.
    basin = np.minimum(basin, np.maximum(base_height + mountain - 1, 0))
    elevation = base_height + mountain - basin
    values.update({"raw_elevation_m": raw, "base_elevation_m": base_height,
                   "mountain_height_m": mountain, "basin_depth_m": basin,
                   "elevation_m": elevation, "ocean_connected": ocean,
                   "inland_depression": inland_negative, "valid": np.ones(x.shape, dtype=bool)})
    return values


class FrozenWorldMountainBelts:
    """Immutable DEM, frozen inventory and small frozen background for geometry checks."""
    def __init__(self, manifest, arrays, base_arrays):
        payload = dict(manifest)
        identity = payload.pop("identity", None)
        if identity != _digest(_json(payload).encode()):
            raise ValueError("world mountain identity mismatch")
        if manifest["schema"] != SCHEMA or manifest["algorithm_version"] != ALGORITHM_VERSION:
            raise ValueError("unsupported world mountain schema or algorithm")
        WorldMountainConfig(**manifest["config"])
        required = set((*FLOAT_FIELDS, *MASK_FIELDS, "plate_id"))
        if set(arrays) != required or set(base_arrays) != set(BASE_FIELDS):
            raise ValueError("world mountain fields mismatch")
        for group, summaries, shape in ((arrays, manifest["arrays"], manifest["grid"]["shape"]),
                                        (base_arrays, manifest["base_arrays"], manifest["base_grid"]["shape"])):
            for name, array in group.items():
                if list(array.shape) != shape or not np.isfinite(array).all() or _summary(array) != summaries[name]:
                    raise ValueError("world mountain array integrity mismatch: " + name)
        if not np.all(arrays["valid"]) or np.any(arrays["mountain_height_m"] < 0) or np.any(arrays["basin_depth_m"] < 0):
            raise ValueError("invalid world mountain field values")
        if np.any(arrays["inland_depression"] & arrays["ocean_connected"]):
            raise ValueError("ocean and inland depression overlap")
        self._manifest_json = _json(manifest)
        self.arrays = MappingProxyType({k: _immutable(v) for k, v in arrays.items()})
        self._base_arrays = MappingProxyType({k: _immutable(v) for k, v in base_arrays.items()})

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def identity(self):
        return self.manifest["identity"]

    def query(self, x_m, z_m):
        grid = self.manifest["grid"]
        x, z = _coordinates(x_m, z_m, grid)
        return _sample_arrays(self.arrays, grid, x, z, (*MASK_FIELDS, "plate_id"))

    def evaluate_geometry(self, x_m, z_m):
        """Read frozen geometry directly; unlike query, recomputes procedural samples."""
        manifest = self.manifest
        x, z = _coordinates(x_m, z_m, manifest["base_grid"])
        return _evaluate(self._base_arrays, manifest["base_grid"], manifest["config"],
                         manifest["source_inventory"], x, z)


def prepare_world_mountain_belts(base, config=WorldMountainConfig()):
    """Explicit bounded preparation. Never evolves, mutates or samples with wrap."""
    if not isinstance(base, FrozenTectonicProduct) or not isinstance(config, WorldMountainConfig):
        raise TypeError("expected a frozen tectonic product and WorldMountainConfig")
    source = base.manifest["config"]
    base_grid = _base_grid(source)
    if np.prod(source["shape"]) > config.max_source_cells:
        raise ValueError("source cell budget exceeded")
    width, height = base_grid["extent_m"]
    nx_float, nz_float = width / config.spacing_m, height / config.spacing_m
    if not np.isclose(nx_float, round(nx_float), atol=1e-9, rtol=0) or not np.isclose(nz_float, round(nz_float), atol=1e-9, rtol=0):
        raise ValueError("spacing must divide the complete source rectangle")
    nx, nz = int(round(nx_float)), int(round(nz_float))
    if nx < 2 or nz < 2 or nx * nz > config.max_cells:
        raise ValueError("output cell budget exceeded or grid too small")
    inventory = _inventory(base, config)
    grid = {**base_grid, "shape": [nz, nx], "spacing_m": config.spacing_m}
    x, z = np.meshgrid(grid["origin_x_m"] + (np.arange(nx) + .5) * config.spacing_m,
                       grid["origin_z_m"] + (np.arange(nz) + .5) * config.spacing_m)
    base_arrays = {name: base.arrays["final/" + name] for name in BASE_FIELDS}
    values = _evaluate(base_arrays, base_grid, asdict(config), inventory, x, z)
    arrays = {k: np.asarray(v, dtype=np.float32 if k in FLOAT_FIELDS else
                            (np.int64 if k == "plate_id" else bool)) for k, v in values.items()}
    manifest = {"schema": SCHEMA, "algorithm_version": ALGORITHM_VERSION,
                "world_seed": config.world_seed, "base_world_seed": source["world_seed"],
                "base_source": {"schema": base.manifest["schema"], "identity": base.identity,
                                "world_seed": source["world_seed"], "state": "final"},
                "source_type": "procedural_world_coarse_geomorphology_non_td",
                "config": asdict(config), "grid": grid, "base_grid": base_grid,
                "coordinates": {"axes": "X east, Z south", "array_order": "z,x", "length_unit": "m",
                                "height_datum_m": 0, "grid_origin": "lower corner; centres at origin+(index+.5)*spacing",
                                "boundary": "finite half-open rectangle; clamped edge interpolation"},
                "source_inventory": inventory,
                "seed_derivation": "SHA256(str(world_seed)+':world-mountain-belts:'+purpose), first 8 bytes big-endian",
                "purpose_seeds": {**inventory["purpose_seeds"], "relief_texture": _seed(config.world_seed, "relief_texture")},
                "base_transform": "positive land 420*(1-exp(-raw/1800))+.025*raw; mix by smooth distance from frozen ocean-cell rectangles over one source spacing; ocean/negative unchanged" if config.flatten_base else "disabled",
                "limitations": ["finite whole-source prepare; no unbounded-world macro coordination",
                                "procedural ranges and lowlands, no erosion or river/lake topology",
                                "query interpolates a DEM; evaluate_geometry directly samples fixed geometry"],
                "arrays": {k: _summary(v) for k, v in arrays.items()},
                "base_arrays": {k: _summary(v) for k, v in base_arrays.items()}}
    manifest["identity"] = _digest(_json(manifest).encode())
    return FrozenWorldMountainBelts(manifest, arrays, base_arrays)


def save_product(product, path):
    """Atomically publish without overwriting; validate a cold read first."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".world-mountains-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            fields = {**product.arrays, **{"base/" + k: v for k, v in product._base_arrays.items()}}
            np.savez_compressed(stream, manifest_json=np.array(_json(product.manifest)), **fields)
            stream.flush()
            os.fsync(stream.fileno())
        loaded = load_product(temporary, expected_identity=product.identity)
        os.link(temporary, path)
        return loaded
    finally:
        Path(temporary).unlink(missing_ok=True)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest field")
        result[key] = value
    return result


def load_product(path, *, expected_identity=None):
    with np.load(path, allow_pickle=False) as archive:
        if len(archive.files) != len(set(archive.files)):
            raise ValueError("duplicate product fields")
        manifest = json.loads(str(archive["manifest_json"]), object_pairs_hook=_unique_object)
        arrays = {k: archive[k] for k in archive.files if k != "manifest_json" and not k.startswith("base/")}
        base_arrays = {k[5:]: archive[k] for k in archive.files if k.startswith("base/")}
    product = FrozenWorldMountainBelts(manifest, arrays, base_arrays)
    if expected_identity is not None and expected_identity != product.identity:
        raise ValueError("unexpected world mountain product identity")
    return product
