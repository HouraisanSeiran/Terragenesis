"""Explicitly prepared ocean landforms on a finite, immutable plate background.

Coordinates are metres, X east / Z south; ages are uncalibrated offline steps.
This is a geometric game-terrain model, not a magma or coral-growth simulation.
"""

import hashlib
import json
import math
import os
import tempfile
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from types import MappingProxyType

import numpy as np

from .common_infra import WORLD_SEED, array_sha256_raw, canonical_json, strict_json
from .island_volcanoes import VOLCANO_STAGES, volcano_profile, volcano_authority
from .island_volcanoes_v4 import volcano_profile as volcano_profile_v4, volcano_authority as volcano_authority_v4


LEGACY_ALGORITHM = "ocean-islands-absolute-slots-v1"
CURVED_ALGORITHM = "ocean-islands-curved-valleys-v2"
METRIC_ALGORITHM = "ocean-islands-metric-detail-smooth-seabed-v3"
VOLCANIC_ALGORITHM = "ocean-islands-volcanic-stages-v4"
ALGORITHM = "ocean-islands-volcanic-edifices-v5"
VOLCANIC_ALGORITHMS = (VOLCANIC_ALGORITHM, ALGORITHM)
SUPPORTED_ALGORITHMS = (LEGACY_ALGORITHM, CURVED_ALGORITHM, METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS)
LAYOUT_RANDOM_DOMAIN = LEGACY_ALGORITHM
VALLEY_RANDOM_DOMAIN = "ocean-island-curved-valley-paths-v2"
DETAIL_RANDOM_DOMAIN = "ocean-island-metric-detail-v3"
SCHEMA = "ocean-islands-frozen-v1"
SOURCE_FIELDS = ("elevation_m", "plate_id", "continental_fraction", "ocean_connected", "velocities_m_per_step")
MAX_SOURCE_CELLS = 262144
MAX_ARCHIVE_BYTES = 536870912


def _identity(record):
    return hashlib.sha256(canonical_json(record).encode()).hexdigest()


def _frozen_array(value):
    value = np.ascontiguousarray(value)
    return np.frombuffer(value.tobytes(), dtype=value.dtype).reshape(value.shape)


def _summary(value):
    return {"shape": list(value.shape), "dtype": value.dtype.str, "sha256": array_sha256_raw(value)}


def _unit(seed, purpose, *keys):
    digest = hashlib.sha256(canonical_json([LAYOUT_RANDOM_DOMAIN, seed, purpose, *keys]).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _inside(bounds, x, z):
    return bounds[0] <= x < bounds[2] and bounds[1] <= z < bounds[3]


def _archive(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("source archive missing or exceeds byte budget")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != len({item.filename for item in members}):
            raise ValueError("duplicate archive members")
        if sum(item.file_size for item in members) > MAX_ARCHIVE_BYTES:
            raise ValueError("expanded archive exceeds byte budget")
    with np.load(path, allow_pickle=False) as archive:
        raw = archive["manifest_json"]
        if raw.shape != () or raw.dtype.kind != "U" or raw.nbytes > 16777216:
            raise ValueError("invalid manifest encoding")
        manifest = strict_json(str(raw))
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be a JSON object")
        arrays = {key: archive[key] for key in archive.files if key != "manifest_json"}
    return manifest, arrays


@dataclass(frozen=True, slots=True, init=False)
class PlateOceanSource:
    """Validated finite source. Origin is the lower corner, samples are cell centres.

    ``identity`` is the original plate product identity; ``world_seed`` retains
    its true seed even when the island configuration uses a newer seed.
    """

    grid: object
    identity: str
    world_seed: int
    source_kind: str
    elevation_m: np.ndarray
    plate_id: np.ndarray
    continental_fraction: np.ndarray
    ocean_connected: np.ndarray
    velocities_m_per_step: np.ndarray
    _provenance_json: str

    def __init__(self, grid, arrays, identity, world_seed, source_kind="declared-test-source", provenance=None):
        if set(grid) != {"origin_x_m", "origin_z_m", "spacing_m", "shape_zx"}:
            raise ValueError("invalid source grid")
        shape = tuple(grid["shape_zx"])
        if (len(shape) != 2 or any(type(v) is not int or v < 2 for v in shape)
                or math.prod(shape) > MAX_SOURCE_CELLS):
            raise ValueError("source grid exceeds cell budget or is invalid")
        if any(type(grid[k]) not in (int, float) or not math.isfinite(grid[k]) for k in ("origin_x_m", "origin_z_m", "spacing_m")) or grid["spacing_m"] <= 0:
            raise ValueError("invalid source coordinates")
        if type(world_seed) is not int or not 0 <= world_seed < 2**63:
            raise ValueError("invalid source world seed")
        if not isinstance(identity, str) or len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("invalid source identity")
        if set(arrays) != set(SOURCE_FIELDS):
            raise ValueError("missing or unexpected source fields")
        for name in SOURCE_FIELDS:
            value = np.asarray(arrays[name])
            if name == "velocities_m_per_step":
                valid = value.ndim == 2 and value.shape[1] == 2 and 1 <= len(value) <= 4096 and value.dtype.kind == "f"
            else:
                valid = value.shape == shape and value.dtype.kind in "fiu" and name not in ("plate_id", "ocean_connected")
                if name == "plate_id":
                    valid = value.shape == shape and value.dtype.kind in "iu"
                if name == "ocean_connected":
                    valid = value.shape == shape and value.dtype == np.dtype(bool)
            if not valid or not np.isfinite(value).all():
                raise ValueError("invalid source field: " + name)
            object.__setattr__(self, name, _frozen_array(value))
        if np.any((self.plate_id < 0) | (self.plate_id >= len(self.velocities_m_per_step))):
            raise ValueError("source plate index outside velocity table")
        if np.any((self.continental_fraction < 0) | (self.continental_fraction > 1)):
            raise ValueError("source continental fraction outside [0,1]")
        if np.any(self.ocean_connected & (self.elevation_m >= 0)):
            raise ValueError("source ocean includes land")
        clean_grid = dict(grid, shape_zx=shape)
        endpoints = (grid["origin_x_m"], grid["origin_z_m"], grid["origin_x_m"] + shape[1] * grid["spacing_m"], grid["origin_z_m"] + shape[0] * grid["spacing_m"])
        if any(not math.isfinite(v) or abs(v) > 1e12 for v in endpoints):
            raise ValueError("source coordinate precision/domain bound exceeded")
        if endpoints[2] <= endpoints[0] or endpoints[3] <= endpoints[1] or grid["spacing_m"] < max(1., *(abs(v) for v in endpoints)) * np.finfo(float).eps * 16:
            raise ValueError("source spacing is below absolute-coordinate precision")
        object.__setattr__(self, "grid", MappingProxyType(clean_grid))
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "world_seed", world_seed)
        object.__setattr__(self, "source_kind", source_kind)
        object.__setattr__(self, "_provenance_json", canonical_json(provenance or {}))

    @property
    def bounds_m(self):
        g = self.grid
        return (g["origin_x_m"], g["origin_z_m"], g["origin_x_m"] + g["spacing_m"] * g["shape_zx"][1], g["origin_z_m"] + g["spacing_m"] * g["shape_zx"][0])

    @property
    def sea_level_m(self):
        return 0.0

    @classmethod
    def _from_validated(cls, manifest, arrays, kind):
        config = manifest["config"]
        grid = {"origin_x_m": config["origin_x_m"], "origin_z_m": config["origin_z_m"], "spacing_m": config["cell_size_m"], "shape_zx": config["shape"]}
        return cls(grid, {name: arrays["final/" + name] for name in SOURCE_FIELDS}, manifest["identity"], config["world_seed"], kind, manifest)

    @classmethod
    def from_product(cls, frozen):
        from .tectonic import FrozenTectonicProduct

        if not isinstance(frozen, FrozenTectonicProduct):
            raise TypeError("expected FrozenTectonicProduct")
        checked = FrozenTectonicProduct(frozen.manifest, frozen.arrays)
        return cls._from_validated(checked.manifest, checked.arrays, "tectonic-frozen")

    @classmethod
    def from_npz(cls, path, expected_identity=None):
        manifest, arrays = _archive(path)
        if manifest.get("schema") == "dream-world-skeleton-plate-v1":
            payload = dict(manifest)
            identity = payload.pop("identity", None)
            if identity != _identity(payload):
                raise ValueError("source manifest identity mismatch")
            if set(arrays) != set(manifest["arrays"]):
                raise ValueError("source array inventory mismatch")
            for key, value in arrays.items():
                expected = manifest["arrays"][key]
                if (expected != {"shape": list(value.shape), "dtype": str(value.dtype), "sha256": array_sha256_raw(value)} or not np.isfinite(value).all()):
                    raise ValueError("source array SHA/shape/dtype mismatch: " + key)
            source = cls._from_validated(manifest, arrays, "dream-skeleton")
        else:
            from .tectonic import FrozenTectonicProduct

            source = cls.from_product(FrozenTectonicProduct(manifest, arrays))
        if expected_identity is not None and source.identity != expected_identity:
            raise ValueError("unexpected source identity")
        return source

    def sample(self, x_m, z_m):
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=float), np.asarray(z_m, dtype=float))
        xmin, zmin, xmax, zmax = self.bounds_m
        if (not np.isfinite(x).all() or not np.isfinite(z).all() or np.any((x < xmin) | (x >= xmax) | (z < zmin) | (z >= zmax))):
            raise ValueError("query outside finite source domain or nonfinite")
        spacing = self.grid["spacing_m"]
        nz, nx = self.grid["shape_zx"]
        gx = np.clip((x - xmin) / spacing - .5, 0, nx - 1)
        gz = np.clip((z - zmin) / spacing - .5, 0, nz - 1)
        ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
        jx, jz = np.minimum(ix + 1, nx - 1), np.minimum(iz + 1, nz - 1)
        fx, fz = gx - ix, gz - iz
        result = {}
        for name in SOURCE_FIELDS[:-1]:
            field = getattr(self, name)
            if name in ("plate_id", "ocean_connected"):
                value = field[np.floor(gz + .5).astype(np.int64), np.floor(gx + .5).astype(np.int64)]
            else:
                value = (1 - fz) * ((1 - fx) * field[iz, ix] + fx * field[iz, jx]) + fz * ((1 - fx) * field[jz, ix] + fx * field[jz, jx])
            result[name] = np.array(value)
        # The continuous confidence avoids a nearest-ocean discontinuity at coasts.
        field = self.ocean_connected
        result["ocean_confidence"] = (1 - fz) * ((1 - fx) * field[iz, ix] + fx * field[iz, jx]) + fz * ((1 - fx) * field[jz, ix] + fx * field[jz, jx])
        return result


@dataclass(frozen=True, slots=True)
class OceanIslandConfig:
    world_seed: int = WORLD_SEED
    world_type: str = "balanced"
    density: str = "medium"
    hotspot_count: int | None = None
    arcs: bool = True
    ridge: bool = True
    atolls: bool = False
    warm_water_scenario: bool = False
    candidate_cell_m: float = 160000.0
    min_hotspot_spacing_m: float = 110000.0
    stages: int = 7
    max_age_steps: float = 80.0
    max_chain_length_m: float = 300000.0
    max_support_radius_m: float = 90000.0
    max_speed_m_per_step: float = 20000.0
    boundary_spacing_m: float = 65000.0
    arc_offset_m: float = 45000.0
    max_candidates: int = 100000
    max_boundary_segments: int = 100000
    max_features: int = 10000
    max_local_features: int = 64
    max_source_cells: int = MAX_SOURCE_CELLS
    max_query_points: int = 4194304
    max_working_bytes: int = 268435456
    valley_strength: float = 1.0
    detail_strength: float = 1.0
    seabed_join_softness_m: float = 320.0
    volcanic_fraction: float = .2
    volcanic_lava_strength: float = 1.

    def __post_init__(self):
        if type(self.volcanic_lava_strength) not in (int, float) or not math.isfinite(self.volcanic_lava_strength) or not 0 <= self.volcanic_lava_strength <= 2:
            raise ValueError("volcanic_lava_strength must be finite in [0,2]")
        if type(self.volcanic_fraction) not in (int, float) or not math.isfinite(self.volcanic_fraction) or not 0 <= self.volcanic_fraction <= 1:
            raise ValueError("volcanic_fraction must be finite in [0,1]")
        if type(self.world_seed) is not int or not 0 <= self.world_seed < 2**63:
            raise ValueError("world_seed must be an integer in [0,2**63)")
        if self.world_type not in ("balanced", "archipelago", "continental", "oceanic", "waterworld", "islands", "multi-continent", "pangaea", "two-continents", "inland-sea") or self.density not in ("none", "low", "medium", "high"):
            raise ValueError("unsupported world_type or density")
        for name in ("arcs", "ridge", "atolls", "warm_water_scenario"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(name + " must be boolean")
        if self.atolls and not self.warm_water_scenario:
            raise ValueError("atolls require an explicitly declared warm_water_scenario")
        if self.hotspot_count is not None and (type(self.hotspot_count) is not int or not 0 <= self.hotspot_count <= 10000):
            raise ValueError("invalid finite hotspot_count")
        for name in ("candidate_cell_m", "min_hotspot_spacing_m", "max_age_steps", "max_chain_length_m", "max_support_radius_m", "max_speed_m_per_step", "boundary_spacing_m", "arc_offset_m"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
                raise ValueError(name + " must be finite and positive")
        for name, upper in (("stages", 16), ("max_candidates", 1000000), ("max_boundary_segments", 1000000), ("max_features", 20000), ("max_local_features", 512), ("max_source_cells", MAX_SOURCE_CELLS), ("max_query_points", 8388608), ("max_working_bytes", 1073741824)):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError(name + " outside budget range")
        if self.stages < 3 or self.max_support_radius_m > 200000 or self.max_chain_length_m > 1000000 or self.max_age_steps > 10000 or self.max_speed_m_per_step > 100000:
            raise ValueError("stage, support, age, speed or chain hard limit exceeded")
        if not 1 <= self.candidate_cell_m <= 1e9 or self.boundary_spacing_m > 1e6 or self.arc_offset_m > 1e6:
            raise ValueError("candidate cell, boundary spacing or arc offset outside coordinate budget")
        if self.min_hotspot_spacing_m > 4 * self.candidate_cell_m:
            raise ValueError("hotspot neighbour stencil exceeds fixed five-cell halo")
        if type(self.valley_strength) not in (int, float) or not math.isfinite(self.valley_strength) or not 0 <= self.valley_strength <= 2:
            raise ValueError("valley_strength must be finite in [0,2]")
        if type(self.detail_strength) not in (int, float) or not math.isfinite(self.detail_strength) or not 0 <= self.detail_strength <= 2:
            raise ValueError("detail_strength must be finite in [0,2]")
        if type(self.seabed_join_softness_m) not in (int, float) or not math.isfinite(self.seabed_join_softness_m) or not 0 <= self.seabed_join_softness_m <= 320:
            raise ValueError("seabed_join_softness_m must be finite in [0,320]")


@dataclass(frozen=True, slots=True)
class OceanIslandFeature:
    feature_id: str
    chain_id: str
    kind: str
    center_x_m: float
    center_z_m: float
    support_radius_m: float
    peak_elevation_m: float
    base_elevation_m: float
    stage: int
    age_steps: float
    plate_id: int
    boundary_id: str | None
    boundary_kind: str | None
    basis: str
    subseed: int
    orientation_rad: float
    axis_ratio: float
    hotspot_x_m: float
    hotspot_z_m: float
    velocity_x_m_per_step: float
    velocity_z_m_per_step: float
    source_identity: str
    parameter_identity: str
    algorithm: str = ALGORITHM
    declared_generated: bool = True
    volcano_stage: str = "none"
    boundary_anchor_x_m: float | None = None
    boundary_anchor_z_m: float | None = None
    boundary_normal_x: float | None = None
    boundary_normal_z: float | None = None
    boundary_tangent_x: float | None = None
    boundary_tangent_z: float | None = None
    upper_plate_id: int | None = None
    boundary_relative_velocity_m_per_step: float | None = None


def _feature_record(feature, algorithm):
    record = asdict(feature)
    if algorithm not in VOLCANIC_ALGORITHMS:
        record.pop("volcano_stage")
    return record


def _config_record(config, algorithm):
    record = asdict(config)
    if algorithm != ALGORITHM or config.volcanic_lava_strength == 0:
        record.pop("volcanic_lava_strength")
    if algorithm not in VOLCANIC_ALGORITHMS:
        record.pop("volcanic_fraction")
    if algorithm not in (METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS):
        record.pop("detail_strength")
        record.pop("seabed_join_softness_m")
    if algorithm == LEGACY_ALGORITHM:
        record.pop("valley_strength")
    return record


@dataclass(frozen=True, slots=True)
class OceanIslandValleyPath:
    """Bounded normalized-local polyline; branches join an exact parent node.

    Points rotate by feature.orientation_rad and scale by support_radius_m.
    Path derivation uses only the immutable feature subseed and this v2 domain.
    """
    path_id: str
    parent_path_id: str | None
    join_parent_node: int | None
    points_local: tuple
    half_widths_local: tuple
    depth_fraction: float


@dataclass(frozen=True, slots=True)
class OceanIslandValleyDomain:
    feature_id: str
    estimated_emerged_area_m2: float
    equivalent_emerged_diameter_m: float
    estimated_exposed_relief_m: float
    activation: float


def _valley_domains(source, features, algorithm, detail_strength=1., volcanic_lava_strength=1.):
    if algorithm not in (CURVED_ALGORITHM, METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS):
        return {}
    result = {}
    angles = (np.arange(48) + .5) * 2 * math.pi / 48
    radial_edges = np.linspace(0., 1., 97)
    radii = (radial_edges[:-1] + radial_edges[1:]) * .5
    normalized_area = np.pi / 48 * np.diff(radial_edges**2)[:, None]
    bounds = source.bounds_m
    for feature in features:
        area, relief = 0., 0.
        if feature.kind != "atoll" and feature.peak_elevation_m > 0:
            r = feature.support_radius_m
            x = feature.center_x_m + r * radii[:, None] * np.cos(angles)[None, :]
            z = feature.center_z_m + r * radii[:, None] * np.sin(angles)[None, :]
            valid = (x >= bounds[0]) & (x < bounds[2]) & (z >= bounds[1]) & (z < bounds[3])
            if np.any(valid):
                fields = source.sample(x[valid], z[valid])
                weight = _feature_weight(feature, _coastal_weight(fields))
                uncut, _ = _shape(feature, x[valid], z[valid], fields["elevation_m"], valley_strength=0.,
                                  surface_weight=weight, detail_strength=detail_strength, volcanic_lava_strength=volcanic_lava_strength)
                height = fields["elevation_m"] + weight * uncut
                emerged = (fields["elevation_m"] < 0) & (height >= 0) & (weight > 0)
                area = float(np.sum(np.broadcast_to(normalized_area * r*r, x.shape)[valid][emerged]))
                if np.any(emerged):
                    relief = max(0., float(np.max(height[emerged])))
                # Include the exact centre in the summit estimate (its area is
                # zero); polar quadrature's first finite ring can miss a peak.
                center = source.sample(feature.center_x_m, feature.center_z_m)
                center_weight = _feature_weight(feature, _coastal_weight(center))
                center_up = _shape(feature, np.array(feature.center_x_m), np.array(feature.center_z_m), center["elevation_m"], valley_strength=0.,
                                   surface_weight=center_weight, detail_strength=detail_strength, volcanic_lava_strength=volcanic_lava_strength)[0]
                if center["elevation_m"] < 0:
                    relief = max(relief, float(center["elevation_m"] + center_up * center_weight))
        diameter = 2 * math.sqrt(area / math.pi)
        activation = float(_smooth((diameter - 20000.) / 20000.) * _smooth((relief - 600.) / 900.))
        result[feature.feature_id] = OceanIslandValleyDomain(feature.feature_id, area, diameter, relief, activation)
    return result


def _valley_unit(feature, purpose, *keys):
    digest = hashlib.sha256(canonical_json([VALLEY_RANDOM_DOMAIN, feature.subseed, purpose, *keys]).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def valley_paths(feature):
    """Reconstruct at most 15 fixed seven-node curves, with no growing cache.

    This is a declared geometric drainage proxy, not flow routing. Main valleys
    follow different lengths and bends from separate heads around the summit;
    two tributaries merge into each main valley at distinct mid-slope nodes.
    """
    if not isinstance(feature, OceanIslandFeature):
        raise TypeError("expected OceanIslandFeature")
    if feature.algorithm not in (CURVED_ALGORITHM, METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS) or feature.kind == "atoll" or feature.peak_elevation_m <= 0:
        return ()
    count = 3 + int(3 * _valley_unit(feature, "main-count"))
    # Irregular cumulative gaps, rather than sectors with equal angle spacing.
    gaps = np.array([.4 + 1.3 * _valley_unit(feature, "main-angle-gap", i) for i in range(count)])
    angles = 2 * math.pi * np.r_[0., np.cumsum(gaps[:-1])] / gaps.sum()
    angles += 2 * math.pi * _valley_unit(feature, "network-orientation")
    paths = []
    for index, angle in enumerate(angles):
        head = .025 + .03 * _valley_unit(feature, "head-radius", index)
        end = .17 + .065 * _valley_unit(feature, "outlet-radius", index)
        radial = np.linspace(head, end, 7)
        phase = _valley_unit(feature, "bend-sign", index) * 2 - 1
        bend = (.22 + .3 * _valley_unit(feature, "bend-size", index)) * (1 if phase >= 0 else -1)
        t = np.linspace(0, 1, 7)
        curved_angle = angle + bend * t + .11 * np.sin(np.pi * t) * (2 * _valley_unit(feature, "head-bend", index) - 1)
        offset = np.array([.025 * (2 * _valley_unit(feature, "head-x", index) - 1), .025 * (2 * _valley_unit(feature, "head-z", index) - 1)])
        points = np.column_stack((radial * np.cos(curved_angle), radial * np.sin(curved_angle))) + offset
        widths = (.006 + .007 * _valley_unit(feature, "width", index)) * (.55 + .7 * t)
        path_id = f"main:{index}"
        paths.append(OceanIslandValleyPath(path_id, None, None, tuple(map(tuple, points.tolist())), tuple(widths.tolist()), .75 + .25 * _valley_unit(feature, "depth", index)))
        for branch in range(2):
            node = 2 + branch
            join = points[node]
            join_radius = float(np.linalg.norm(join))
            join_angle = math.atan2(join[1], join[0])
            sign = -1 if branch == 0 else 1
            head_angle = join_angle + sign * (.32 + .36 * _valley_unit(feature, "tributary-angle", index, branch))
            head_radius = join_radius * (.38 + .16 * _valley_unit(feature, "tributary-length", index, branch))
            branch_head = head_radius * np.array([math.cos(head_angle), math.sin(head_angle)])
            chord = join - branch_head
            perpendicular = np.array([-chord[1], chord[0]])
            control = (branch_head + join) / 2 + perpendicular * (.22 + .18 * _valley_unit(feature, "tributary-bend", index, branch)) * sign
            branch_points = ((1-t)**2)[:, None] * branch_head + (2*t*(1-t))[:, None] * control + (t*t)[:, None] * join
            # Endpoint joins the exact node, avoiding numerical drift at a fork.
            branch_points[-1] = join
            branch_widths = widths[node] * (.43 + .57 * t)
            paths.append(OceanIslandValleyPath(f"branch:{index}:{branch}", path_id, node,
                         tuple(map(tuple, branch_points.tolist())), tuple(branch_widths.tolist()),
                         .5 + .2 * _valley_unit(feature, "tributary-depth", index, branch)))
    return tuple(paths)


def _valley_storage_bound(features):
    # Conservative Python-object estimate: each point owns two float objects,
    # tuple references, a width value and path bookkeeping. The derived tuple
    # is fixed once per frozen product, never an expanding point-query cache.
    eligible = sum(feature.algorithm in (CURVED_ALGORITHM, METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS) and feature.kind != "atoll" and feature.peak_elevation_m > 0 for feature in features)
    return eligible * 15 * 7 * 192


def _valley_incision(feature, along, across, uncut_height, strength, paths=None):
    result = np.zeros(along.shape)
    if strength == 0 or feature.peak_elevation_m <= 0:
        return result
    active = uncut_height > 0
    if not np.any(active):
        return result
    qx, qz = along[active], across[active]
    influence = np.zeros(qx.shape)
    for path in valley_paths(feature) if paths is None else paths:
        points = path.points_local
        nsegments = len(points) - 1
        for index in range(nsegments):
            ax, az = points[index]
            bx, bz = points[index + 1]
            vx, vz = bx - ax, bz - az
            width_a, width_b = path.half_widths_local[index:index + 2]
            max_width = max(width_a, width_b)
            selected = ((qx > min(ax, bx) - max_width) & (qx < max(ax, bx) + max_width)
                        & (qz > min(az, bz) - max_width) & (qz < max(az, bz) + max_width))
            if not np.any(selected):
                continue
            fraction = np.clip(((qx[selected] - ax) * vx + (qz[selected] - az) * vz) / (vx*vx + vz*vz), 0., 1.)
            distance = np.hypot(qx[selected] - ax - fraction * vx, qz[selected] - az - fraction * vz)
            width = width_a + (width_b - width_a) * fraction
            progress = (index + fraction) / nsegments
            taper = _smooth(progress / .2)
            if path.parent_path_id is None:
                taper *= _smooth((1 - progress) / .25)
            depth = path.depth_fraction * taper * _kernel(distance / width)
            influence[selected] = np.maximum(influence[selected], depth)
    # A subaerial incision cannot scale with the several-km submarine pedestal.
    # It is bounded by exposed summit relief, horizontal slope scale, and local
    # positive height; smoothly zero at sea level and never cuts seabed rays.
    cap = min(240., .16 * max(0., feature.peak_elevation_m), .004 * feature.support_radius_m)
    local_cap = np.minimum(cap * _smooth(uncut_height[active] / max(50., .2 * feature.peak_elevation_m)), .3 * uncut_height[active])
    result[active] = strength * local_cap * influence
    return result


def _check_source_budget(source, config):
    cells = math.prod(source.grid["shape_zx"])
    source_bytes = sum(getattr(source, name).nbytes for name in SOURCE_FIELDS)
    if cells > config.max_source_cells or source_bytes * 4 > config.max_working_bytes:
        raise ValueError("source/working memory budget exceeded")
    if float(np.max(np.linalg.norm(source.velocities_m_per_step, axis=1))) > config.max_speed_m_per_step:
        raise ValueError("source velocity exceeds configured bound")
    return cells, source_bytes


def _check_overlap_budget(features, config):
    # Conservative bin support counts include square-circle false positives.
    overlap = {}
    bin_size = config.max_support_radius_m
    for feature in features:
        r = feature.support_radius_m
        for bz in range(math.floor((feature.center_z_m - r) / bin_size), math.floor((feature.center_z_m + r) / bin_size) + 1):
            for bx in range(math.floor((feature.center_x_m - r) / bin_size), math.floor((feature.center_x_m + r) / bin_size) + 1):
                key = (bx, bz)
                overlap[key] = overlap.get(key, 0) + 1
                if overlap[key] > config.max_local_features:
                    raise ValueError("local overlapping support budget exceeded")
    return max(overlap.values(), default=0)


def _dependencies(source, config):
    spacing = source.grid["spacing_m"]
    halo_cells = math.ceil(config.min_hotspot_spacing_m / config.candidate_cell_m) + 1
    halo_m = math.sqrt(2) * (halo_cells + 1) * config.candidate_cell_m
    local_boundary_radius = max(3 * spacing, config.boundary_spacing_m)
    interpolation = math.sqrt(2) * spacing
    hotspot = config.max_chain_length_m + config.max_support_radius_m + halo_m + interpolation
    boundary = config.arc_offset_m + config.max_support_radius_m + local_boundary_radius + interpolation
    return {
        "hotspot_trajectory_m": config.max_chain_length_m,
        "feature_support_m": config.max_support_radius_m,
        "source_interpolation_m": interpolation,
        "hotspot_competition_distance_m": config.min_hotspot_spacing_m,
        "hotspot_hash_stencil_halo_cells": halo_cells,
        "hotspot_hash_stencil_radius_bound_m": halo_m,
        "boundary_pca_and_thinning_m": local_boundary_radius,
        "arc_offset_m": config.arc_offset_m,
        "conservative_geometry_and_hash_radius_m": max(hotspot, boundary),
        "hotspot_selection_scope": "entire finite source priority ranking" if config.hotspot_count is not None else "absolute cell threshold and fixed neighbour priorities",
        "finite_count_global_dependency": config.hotspot_count is not None,
        "preparation_scope": "whole finite frozen source; no per-window preparation API",
    }


def _validate_boundary_record(feature, source, config):
    fields = (feature.boundary_anchor_x_m, feature.boundary_anchor_z_m, feature.boundary_normal_x, feature.boundary_normal_z,
              feature.boundary_tangent_x, feature.boundary_tangent_z, feature.boundary_relative_velocity_m_per_step)
    if feature.kind not in ("arc", "ridge"):
        if feature.boundary_id is not None or feature.boundary_kind is not None or feature.upper_plate_id is not None or any(value is not None for value in fields):
            raise ValueError("non-boundary feature has boundary fields")
        return
    if (any(type(value) not in (int, float) or not math.isfinite(value) for value in fields)
            or not isinstance(feature.boundary_id, str) or not feature.boundary_id.startswith("face:")):
        raise ValueError("invalid boundary provenance")
    normal = np.array([feature.boundary_normal_x, feature.boundary_normal_z])
    tangent = np.array([feature.boundary_tangent_x, feature.boundary_tangent_z])
    if abs(np.linalg.norm(normal) - 1) > 1e-9 or abs(np.linalg.norm(tangent) - 1) > 1e-9 or abs(np.dot(normal, tangent)) > 1e-9:
        raise ValueError("invalid boundary tangent/normal")
    if not _inside(source.bounds_m, feature.boundary_anchor_x_m, feature.boundary_anchor_z_m):
        raise ValueError("boundary anchor outside finite source")
    if feature.kind == "arc":
        delta = np.array([feature.center_x_m - feature.boundary_anchor_x_m, feature.center_z_m - feature.boundary_anchor_z_m])
        if (feature.boundary_kind != "convergent" or feature.boundary_relative_velocity_m_per_step >= -5
                or type(feature.upper_plate_id) is not int or feature.upper_plate_id != feature.plate_id
                or not np.allclose(delta, normal * config.arc_offset_m, rtol=0, atol=1e-7)):
            raise ValueError("invalid overriding-side arc record")
    elif (feature.boundary_kind != "divergent" or feature.boundary_relative_velocity_m_per_step <= 5 or feature.upper_plate_id is not None
          or feature.center_x_m != feature.boundary_anchor_x_m or feature.center_z_m != feature.boundary_anchor_z_m):
        raise ValueError("invalid divergent ridge record")


def _smooth(value):
    value = np.clip(value, 0., 1.)
    return value * value * (3 - 2 * value)


def _kernel(radius):
    radius = np.clip(radius, 0., 1.)
    return (1 - radius)**4 * (1 + 4 * radius)


def _coastal_weight(fields):
    return (_smooth((-fields["elevation_m"] - 30) / 900) * _smooth((.45 - fields["continental_fraction"]) / .35) * _smooth(fields["ocean_confidence"]))


def _feature_weight(feature, coastal_weight):
    # A qualified reef platform has an absolute -35m lagoon / +5..11m rim.
    # Multiplying its several-kilometre uplift by even 0.95 would drown that rim.
    # Saturate inside the same >=.88 suitability used to admit the platform;
    # outside that envelope the full seabed/reef transition remains continuous.
    return _smooth(coastal_weight / .88) if feature.kind == "atoll" else coastal_weight


def _metric_noise(x, z, spacing_m, seed, purpose):
    """Bounded C2 lattice value noise in absolute metric coordinates, no cache."""
    gx, gz = np.asarray(x, dtype=float) / spacing_m, np.asarray(z, dtype=float) / spacing_m
    ix, iz = np.floor(gx).astype(np.int64), np.floor(gz).astype(np.int64)
    fx, fz = gx - ix, gz - iz
    fx = fx**3 * (fx * (fx * 6 - 15) + 10)
    fz = fz**3 * (fz * (fz * 6 - 15) + 10)
    salt = int.from_bytes(hashlib.sha256(canonical_json([DETAIL_RANDOM_DOMAIN, seed, purpose]).encode()).digest()[:8], "little")
    def corner(dx, dz):
        # uint64 modular arithmetic intentionally wraps; scalar numpy versions
        # otherwise warn even though this is the specified hash operation.
        with np.errstate(over="ignore"):
            value = (ix + dx).astype(np.uint64) * np.uint64(0x9E3779B185EBCA87) ^ (iz + dz).astype(np.uint64) * np.uint64(0xC2B2AE3D27D4EB4F) ^ np.uint64(salt)
            value ^= value >> np.uint64(30)
            value *= np.uint64(0xBF58476D1CE4E5B9)
            value ^= value >> np.uint64(27)
            value *= np.uint64(0x94D049BB133111EB)
            value ^= value >> np.uint64(31)
        return (value >> np.uint64(11)).astype(float) * (2. / 2**53) - 1.
    return (1-fz)*((1-fx)*corner(0,0)+fx*corner(1,0)) + fz*((1-fx)*corner(0,1)+fx*corner(1,1))


def _query_batch_size(point_count, feature_count, fixed_bytes, max_working_bytes):
    """Bound contributor stacks, sort/projection temporaries and output arrays.

    Count all catalog rows: an arbitrary scattered batch need not share the
    per-location overlap bound. The 192-byte row allowance covers both cut and
    uncut stacks plus the sorted active-set solve, with 512 bytes/point for
    source interpolation, shape evaluation and chunk/result handoff.
    """
    available = max_working_bytes - fixed_bytes - 224 * point_count
    per_point = 512 + 192 * max(1, feature_count)
    if available < per_point:
        raise ValueError("query exceeds combined source/output/temporary working-memory budget; split into tiles")
    return min(16384, max(1, point_count), available // per_point)


def _smooth_seabed_envelope(heights, base, softness_m, reef_mask=None):
    """One global simplex quadratic smooth-max, never pairwise accumulation.

    h are nonnegative already coast-weighted uplifts. Coexistence and the
    conservative p16 height bound are C1 away from an inactive all-zero field.
    tau shrinks continuously; S itself is used, not an interpolation with max.
    """
    maximum = np.array(np.max(heights, axis=0))
    if softness_m == 0 or heights.shape[0] < 2:
        return maximum
    total = np.sum(heights, axis=0)
    norm2 = np.sqrt(np.sum(heights**2, axis=0))
    coexist = np.maximum(0., total - norm2)
    # Scaling avoids overflow in the p16 conservative smooth upper bound.
    scale = np.maximum(maximum, 1.)
    upper = base + scale * np.sum((heights / scale)**16, axis=0)**(1/16)
    tau = softness_m * _smooth(coexist / 640.) * _smooth((-30. - upper) / 200.)
    if reef_mask is not None:
        tau *= (1 - reef_mask)
    selected = tau > 1e-10
    result = maximum.copy()
    if not np.any(selected):
        return result
    h = np.sort(heights[:, selected], axis=0)[::-1]
    t = tau[selected]
    # Centre heights to avoid cancellation; sparse simplex projection gives
    # the active set exactly after sorting all bounded local contributors.
    shifted = h - h[0]
    rank = np.arange(1, len(h)+1, dtype=float)[:, None]
    threshold = (np.cumsum(shifted, axis=0) - t) / rank
    active = shifted > threshold
    rho = np.sum(active, axis=0) - 1
    lam = threshold[rho, np.arange(h.shape[1])]
    p = np.maximum((shifted-lam)/t, 0.)
    correction = np.sum(p * shifted, axis=0) + .5*t*(1-np.sum(p*p,axis=0))
    result[selected] += correction
    return result


def _volcano_functions(algorithm):
    if algorithm == VOLCANIC_ALGORITHM:
        return volcano_authority_v4, volcano_profile_v4
    return volcano_authority, volcano_profile


def _shape(feature, x, z, base, *, valley_strength=1., paths=None, surface_weight=1., return_uncut=False, detail_strength=1., volcanic_lava_strength=1.):
    dx = (x - feature.center_x_m) / feature.support_radius_m
    dz = (z - feature.center_z_m) / feature.support_radius_m
    radius = np.hypot(dx, dz)
    angle = np.arctan2(dz, dx) - feature.orientation_rad
    if feature.kind == "atoll":
        ring_radius = .235 * (1 + .09 * np.sin(3 * angle + feature.orientation_rad) + .035 * np.sin(7 * angle))
        platform = _smooth((1 - radius) / .7)
        height = base + np.maximum(0, -35 - base) * platform
        ring = _kernel(np.abs(radius - ring_radius) / .047)
        height += (feature.peak_elevation_m + 35) * ring
        lagoon = radius < ring_radius - .047
        uplift = np.maximum(0, height - base)
        return (uplift, lagoon, uplift) if return_uncut else (uplift, lagoon)
    along, across = radius * np.cos(angle), radius * np.sin(angle)
    if feature.algorithm in (METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS):
        coarse = sum(weight * _metric_noise(x, z, spacing, feature.subseed, "contour") for spacing, weight in ((20000., .5), (8000., .32), (3000., .18)))
        distorted = radius * (1 + .09 * detail_strength * coarse * _smooth(radius / .07))
    else:
        distorted = radius * (1 + .075 * np.sin(3 * angle) + .04 * np.cos(5 * angle + feature.orientation_rad))
    pedestal = _kernel(distorted) * _smooth((1 - radius) / .12)
    ellipse = np.hypot(along / .46, across / (.46 * feature.axis_ratio))
    cone = _kernel(ellipse)
    # Off-centre secondary vents share the same bottom; max prevents additive dams.
    second = .74 * _kernel(np.hypot((along - .16) / .36, (across + .065) / (.32 * feature.axis_ratio)))
    third = .52 * _kernel(np.hypot((along + .15) / .3, (across - .09) / .28))
    summit = np.maximum(cone, np.maximum(second, third))
    amplitude = max(0., feature.peak_elevation_m - feature.base_elevation_m)
    uplift = amplitude * (.64 * pedestal + .36 * summit)
    collapse = .08 * max(0., feature.peak_elevation_m) * _kernel(np.hypot(along - .025, across + .012) / .085)
    if feature.algorithm in VOLCANIC_ALGORITHMS and feature.volcano_stage != "none":
        authority_fn, profile_fn = _volcano_functions(feature.algorithm)
        authority = authority_fn(radius)
        profile = (profile_fn(feature, radius, angle, lava_strength=volcanic_lava_strength)
                   if feature.algorithm == ALGORITHM else profile_fn(feature, radius, angle))
        target = np.maximum(0., feature.peak_elevation_m * profile - base)
        uplift = (1 - authority) * np.maximum(0., uplift - collapse) + authority * target
        collapse = np.zeros_like(radius)
    if feature.algorithm in (METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS) and detail_strength > 0 and feature.peak_elevation_m > 0:
        actual_weight = np.broadcast_to(np.asarray(surface_weight, dtype=float), np.shape(uplift))
        height = base + np.maximum(0., uplift-collapse) * actual_weight
        selected = height > 0
        if np.any(selected):
            detail = sum(weight * _metric_noise(np.asarray(x)[selected], np.asarray(z)[selected], spacing, feature.subseed, "surface")
                         for spacing, weight in ((700., .5), (240., .32), (80., .18)))
            amplitude_m = np.minimum(min(30., .025*feature.peak_elevation_m), .12*np.maximum(0., height[selected]))
            delta = detail_strength * amplitude_m * _smooth(height[selected]/100.) * detail
            addition = np.zeros_like(uplift)
            addition[selected] = np.divide(delta, actual_weight[selected], out=np.zeros_like(delta), where=actual_weight[selected]>0)
            uplift += addition
    if feature.algorithm == LEGACY_ALGORITHM:
        # Historical v1 byte/value replay only. New preparation never selects it.
        valleys = .055 * amplitude * np.maximum(0., np.cos(4 * angle + .8))**8 * _kernel(radius / .65) * _smooth(radius / .12)
    elif feature.algorithm == ALGORITHM and feature.volcano_stage != "none":
        # The v5 edifice already contains its local erosion geometry. Ordinary
        # island drainage paths would recut the intact low lava apron.
        valleys = np.zeros_like(radius)
    elif feature.algorithm in (CURVED_ALGORITHM, METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS):
        actual_weight = np.broadcast_to(np.asarray(surface_weight, dtype=float), np.shape(uplift))
        actual_uncut_height = base + np.maximum(0., uplift - collapse) * actual_weight
        actual_cut = _valley_incision(feature, along, across, actual_uncut_height, valley_strength, paths)
        # query applies this weight after shape composition. Convert the limited
        # *final* metre incision to raw uplift units, preserving the depth cap
        # and zero submarine change after coastal fading.
        valleys = np.divide(actual_cut, actual_weight, out=np.zeros_like(actual_cut), where=actual_weight > 0)
    else:
        raise ValueError("unsupported shape algorithm")
    result = (np.maximum(0., uplift - valleys - collapse), np.zeros(radius.shape, dtype=bool))
    return (*result, np.maximum(0., uplift - collapse)) if return_uncut else result


@dataclass(frozen=True, slots=True, init=False)
class FrozenOceanIslands:
    source: PlateOceanSource
    features: tuple
    config: OceanIslandConfig
    _manifest_json: str
    _valley_networks: object
    _valley_domains: object
    _algorithm: str

    def __init__(self, source, config, features, manifest):
        if not isinstance(source, PlateOceanSource) or not isinstance(config, OceanIslandConfig):
            raise TypeError("expected validated source and config")
        if not isinstance(manifest, dict) or manifest.get("algorithm") not in SUPPORTED_ALGORITHMS:
            raise ValueError("unsupported shape algorithm")
        algorithm = manifest["algorithm"]
        features = tuple(features)
        if not all(isinstance(feature, OceanIslandFeature) for feature in features):
            raise ValueError("invalid feature record")
        if len(features) > config.max_features or len({f.feature_id for f in features}) != len(features):
            raise ValueError("feature budget or duplicate ID")
        if tuple(sorted(features, key=lambda f: f.feature_id)) != features:
            raise ValueError("feature inventory must be sorted by stable ID")
        for feature in features:
            if feature.volcano_stage not in ("none", *VOLCANO_STAGES) or (feature.volcano_stage != "none" and (algorithm not in VOLCANIC_ALGORITHMS or feature.kind not in ("hotspot", "arc") or feature.peak_elevation_m <= 0)):
                raise ValueError("invalid volcanic morphology stage")
            record = asdict(feature)
            canonical_json(record)
            numeric_fields = ("center_x_m", "center_z_m", "support_radius_m", "peak_elevation_m", "base_elevation_m", "age_steps", "orientation_rad", "axis_ratio", "hotspot_x_m", "hotspot_z_m", "velocity_x_m_per_step", "velocity_z_m_per_step")
            if (any(type(record[name]) not in (float, int) or not math.isfinite(record[name]) for name in numeric_fields)
                    or any(type(record[name]) is not int for name in ("plate_id", "stage", "subseed"))
                    or any(not isinstance(record[name], str) or not record[name] for name in ("feature_id", "chain_id", "basis"))
                    or type(feature.declared_generated) is not bool):
                raise ValueError("invalid feature field types")
            if (feature.kind not in ("hotspot", "seamount", "arc", "ridge", "atoll") or feature.algorithm != algorithm or not feature.declared_generated
                    or feature.source_identity != source.identity or feature.parameter_identity != _identity(_config_record(config, algorithm))
                    or not 0 < feature.support_radius_m <= config.max_support_radius_m or not _inside(source.bounds_m, feature.center_x_m, feature.center_z_m)
                    or not 0 <= feature.plate_id < len(source.velocities_m_per_step) or not 0 <= feature.stage < config.stages
                    or not 0 <= feature.age_steps <= config.max_age_steps or not .5 <= feature.axis_ratio <= 1):
                raise ValueError("feature outside generation contract")
            if feature.kind == "atoll" and not (config.atolls and config.warm_water_scenario):
                raise ValueError("atoll without warm scenario")
            _validate_boundary_record(feature, source, config)
        cells, source_bytes = _check_source_budget(source, config)
        if _valley_storage_bound(features) + source_bytes * 4 > config.max_working_bytes:
            raise ValueError("fixed valley network exceeds working-memory budget")
        local_support_count = _check_overlap_budget(features, config)
        if not isinstance(manifest, dict) or not isinstance(manifest.get("preparation"), dict):
            raise ValueError("invalid preparation record")
        preparation = manifest["preparation"]
        if preparation:
            if (preparation.get("source_cells") != cells or preparation.get("source_bytes") != source_bytes
                    or preparation.get("feature_count") != len(features) or preparation.get("max_local_support_count") != local_support_count
                    or preparation.get("dependencies") != _dependencies(source, config)):
                raise ValueError("preparation budget/dependency record mismatch")
        domains = _valley_domains(source, features, algorithm, config.detail_strength, config.volcanic_lava_strength)
        expected = _manifest(source, config, features, manifest.get("preparation", {}), algorithm=algorithm, valley_domains=domains)
        if manifest != expected:
            raise ValueError("island manifest/content identity mismatch")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "features", features)
        object.__setattr__(self, "_manifest_json", canonical_json(manifest))
        object.__setattr__(self, "_algorithm", algorithm)
        object.__setattr__(self, "_valley_domains", MappingProxyType(domains))
        object.__setattr__(self, "_valley_networks", MappingProxyType({feature.feature_id: valley_paths(feature) if domains and domains[feature.feature_id].activation > 0 else () for feature in features}))

    @property
    def manifest(self):
        return json.loads(self._manifest_json)

    @property
    def identity(self):
        return self.manifest["identity"]

    @property
    def valley_domains(self):
        """Read-only, fixed single-feature estimates; paths may remain inactive."""
        return self._valley_domains

    def query(self, x_m, z_m):
        x, z = np.broadcast_arrays(np.asarray(x_m, dtype=float), np.asarray(z_m, dtype=float))
        if x.size > self.config.max_query_points or x.size * 224 > self.config.max_working_bytes:
            raise ValueError("query exceeds point/working-memory budget; split into tiles")
        if self._algorithm in (METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS):
            fixed_bytes = 4 * sum(getattr(self.source, key).nbytes for key in SOURCE_FIELDS) + _valley_storage_bound(self.features)
            batch_size = _query_batch_size(x.size, len(self.features), fixed_bytes, self.config.max_working_bytes)
        else:
            batch_size = max(1, x.size)
        if x.size > batch_size:
            # Scattered points can touch every catalog feature even when the
            # local overlap bound is small. Budget against the full catalog.
            result = None
            for start in range(0, x.size, batch_size):
                stop = min(x.size, start+batch_size)
                chunk = self._query_direct(x.flat[start:stop], z.flat[start:stop])
                if result is None:
                    result = {key: np.empty(x.size, dtype=value.dtype) for key,value in chunk.items()}
                for key,value in chunk.items():
                    result[key][start:stop] = value
            return {key: value.reshape(x.shape) for key,value in result.items()}
        return self._query_direct(x, z)

    def _query_direct(self, x, z):
        fields = self.source.sample(x, z)
        base = np.asarray(fields["elevation_m"], dtype=float)
        relief = np.zeros(x.shape)
        track_uncut = bool(self._valley_domains)
        uncut_relief = np.zeros(x.shape) if track_uncut else None
        protection_weight = np.zeros(x.shape)
        lagoon = np.zeros(x.shape, dtype=bool)
        weight = _coastal_weight(fields)
        contributions, uncut_contributions = [], []
        reef_mask = np.zeros(x.shape)
        for feature in self.features:
            r = feature.support_radius_m
            selected = (np.abs(x - feature.center_x_m) < r) & (np.abs(z - feature.center_z_m) < r)
            if not np.any(selected):
                continue
            feature_weight = _feature_weight(feature, weight[selected])
            activation = self._valley_domains[feature.feature_id].activation if track_uncut else 1.
            shaped = _shape(feature, x[selected], z[selected], base[selected], valley_strength=self.config.valley_strength * activation,
                            paths=self._valley_networks[feature.feature_id], surface_weight=feature_weight, return_uncut=track_uncut,
                            detail_strength=self.config.detail_strength, volcanic_lava_strength=self.config.volcanic_lava_strength)
            upl, wet_hole = shaped[:2]
            radius = np.hypot(x[selected] - feature.center_x_m, z[selected] - feature.center_z_m) / r
            envelope = _smooth((1 - radius) / .35) * feature_weight
            relief[selected] = np.maximum(relief[selected], upl * feature_weight)
            if track_uncut:
                uncut_relief[selected] = np.maximum(uncut_relief[selected], shaped[2] * feature_weight)
            if self._algorithm in (METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS) and self.config.seabed_join_softness_m > 0:
                item = np.zeros(x.shape)
                item[selected] = upl * feature_weight
                contributions.append(item)
                item_uncut = np.zeros(x.shape)
                item_uncut[selected] = shaped[2] * feature_weight
                uncut_contributions.append(item_uncut)
                if feature.kind == "atoll":
                    reef_mask[selected] = np.maximum(reef_mask[selected], envelope)
            protection_weight[selected] = np.maximum(protection_weight[selected], envelope)
            lagoon[selected] |= wet_hole
        if contributions:
            relief = _smooth_seabed_envelope(np.asarray(contributions), base, self.config.seabed_join_softness_m, reef_mask)
            uncut_relief = _smooth_seabed_envelope(np.asarray(uncut_contributions), base, self.config.seabed_join_softness_m, reef_mask)
        # A special cone owns its bounded summit beneath overlapping platforms.
        if self._algorithm in VOLCANIC_ALGORITHMS:
            for feature in self.features:
                if feature.volcano_stage == "none":
                    continue
                r = feature.support_radius_m
                limit = .30 if self._algorithm == VOLCANIC_ALGORITHM else .55
                selected = (np.abs(x-feature.center_x_m) < limit*r) & (np.abs(z-feature.center_z_m) < limit*r)
                if not np.any(selected):
                    continue
                shaped = _shape(feature, x[selected], z[selected], base[selected], valley_strength=0., surface_weight=weight[selected], return_uncut=True, detail_strength=self.config.detail_strength, volcanic_lava_strength=self.config.volcanic_lava_strength)
                radius = np.hypot(x[selected]-feature.center_x_m, z[selected]-feature.center_z_m)/r
                authority_fn, _ = _volcano_functions(self._algorithm)
                authority = authority_fn(radius)
                target = shaped[0]*weight[selected]
                relief[selected] -= authority*np.maximum(0., relief[selected]-target)
                if track_uncut:
                    uncut_relief[selected] -= authority*np.maximum(0., uncut_relief[selected]-target)
        # Atoll interiors have authority over the associated old volcanic platform
        # and overlapping vents; their submerged lagoon cannot be max-filled.
        for feature in self.features:
            if feature.kind != "atoll":
                continue
            r = feature.support_radius_m
            selected = (np.abs(x - feature.center_x_m) < .6 * r) & (np.abs(z - feature.center_z_m) < .6 * r)
            if np.any(selected):
                upl, wet_hole = _shape(feature, x[selected], z[selected], base[selected])
                old = relief[selected]
                radius = np.hypot(x[selected] - feature.center_x_m, z[selected] - feature.center_z_m) / r
                authority = _smooth((.6 - radius) / .3)
                old -= authority * np.maximum(0., old - upl * _feature_weight(feature, weight[selected]))
                relief[selected] = old
                if track_uncut:
                    old_uncut = uncut_relief[selected]
                    old_uncut -= authority * np.maximum(0., old_uncut - upl * _feature_weight(feature, weight[selected]))
                    uncut_relief[selected] = old_uncut
        if track_uncut:
            uncut_height = base + uncut_relief
            # Lagoon authority can submerge an otherwise exposed overlapping
            # volcano. Final composition still never incises submerged terrain.
            cut = np.maximum(0., uncut_relief - relief) * _smooth(uncut_height / 100.)
            cut = np.minimum(cut, .3 * np.maximum(0., uncut_height))
            relief = uncut_relief - cut
        elevation = base + relief
        protected = protection_weight > 0
        result = {"base_elevation_m": base.copy(), "elevation_m": elevation, "relief_m": relief, "land": elevation >= 0, "protected": protected, "protection_weight": protection_weight, "lagoon": lagoon & protected & (elevation < 0)}
        if self._algorithm in VOLCANIC_ALGORITHMS:
            volcano_weight = np.zeros(x.shape)
            for feature in self.features:
                if feature.volcano_stage != "none":
                    radius = np.hypot(x-feature.center_x_m, z-feature.center_z_m)/feature.support_radius_m
                    limit = .30 if self._algorithm == VOLCANIC_ALGORITHM else .55
                    selected = radius < limit
                    if np.any(selected):
                        uplift, _ = _shape(feature, x[selected], z[selected], base[selected], valley_strength=0., surface_weight=weight[selected], detail_strength=self.config.detail_strength, volcanic_lava_strength=self.config.volcanic_lava_strength)
                        own_height = base[selected] + uplift*weight[selected]
                        authority_fn, _ = _volcano_functions(self._algorithm)
                        local = authority_fn(radius[selected])*weight[selected]*_smooth(own_height/80.)
                        volcano_weight[selected] = np.maximum(volcano_weight[selected], local)
            volcano_weight *= _smooth(elevation/80.)
            volcano_weight = np.asarray(np.where((base >= 0) | (elevation <= 0) | lagoon, 0., volcano_weight))
            result["volcano_weight"] = volcano_weight
        return result


def _manifest(source, config, features, preparation, *, algorithm=ALGORITHM, valley_domains=None):
    manifest = {
        "schema": SCHEMA, "algorithm": algorithm, "config": _config_record(config, algorithm),
        "source": {"identity": source.identity, "world_seed": source.world_seed, "kind": source.source_kind,
                   "grid": dict(source.grid), "original_manifest": json.loads(source._provenance_json)},
        "arrays": {name: _summary(getattr(source, name)) for name in SOURCE_FIELDS},
        "features": [_feature_record(feature, algorithm) for feature in features], "preparation": preparation,
        "coordinates": "X east, Z south; metres; cell-centre source; half-open finite bounds; clamp interpolation",
        "age_unit": "uncalibrated offline-step", "composition": "max uplift; smooth coast protection; atoll lagoon authority",
        "reef_coast_rule": "absolute platform inside admitted coastal suitability>=0.88; smoothstep fade below that threshold; no uplift on original land",
        "peak_elevation_semantics": "target absolute summit before caldera, valleys, coastal fade and max composition; raster maximum may differ",
        "limitations": ["Finite source only; no periodic query or implicit preparation", "Arc polarity is a deterministic composition/plate-ID approximation, not a resolved slab", "Warm-water atolls are declared geometry, not coral ecology", "No magma/material conservation simulation", "Density controls candidates; no window quantile or sea-level adjustment"],
    }
    if algorithm in (CURVED_ALGORITHM, METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS):
        valley_domains = _valley_domains(source, features, algorithm, config.detail_strength, config.volcanic_lava_strength) if valley_domains is None else valley_domains
        manifest["valley_model"] = {
            "random_domain": VALLEY_RANDOM_DOMAIN, "layout_random_domain": LAYOUT_RANDOM_DOMAIN,
            "geometry": "3..5 irregular curved main paths, two curved tributaries/main; fixed seven-node local polylines; exact parent-node joins",
            "derivation": "SHA256([domain, feature.subseed, purpose, slot]); independent of valley_strength and query order",
            "limits": "at most15 paths x6 segments per feature; only positive uncut height; max cut strength*min(240m,0.16*peak,0.004*radius,0.3*local_height)",
            "semantics": "bounded geometric valley incision, not water routing or erosion simulation; submarine platforms unchanged",
            "fixed_network_storage_upper_bound_bytes": _valley_storage_bound(features),
            "activation": "game morphology gate: diameter<=20km off,20..40km smoothstep; exposed relief<=600m off,600..1500m smoothstep; multiply both and valley_strength",
            "domain_estimation": "fixed48 angles x96 radial midpoint annuli (4608 points/feature), exact annular area weights inside support; source base/coast weight and uncut single-feature surface; only newly emerged original seabed; exact centre also sampled for relief; independent of request grid",
            "domains": [asdict(value) for value in valley_domains.values()],
        }
    if algorithm in (METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS):
        manifest["composition"] = "global simplex quadratic smooth-max on submerged overlapping supports; continuous coast protection; atoll lagoon authority"
        manifest["metric_detail"] = {"random_domain": DETAIL_RANDOM_DOMAIN, "layout_random_domain": LAYOUT_RANDOM_DOMAIN,
            "contour_spacing_m": [20000.,8000.,3000.], "contour_max_radial_fraction": .09*config.detail_strength,
            "surface_spacing_m": [700.,240.,80.], "surface_amplitude": "strength*min(30m,.025*peak,.12*local positive height), sea-level fade100m; no atoll surface noise",
            "interpolation": "absolute metric lattice, SHA256 purpose seed, fixed uint64 corner mixing, quintic C2 value interpolation"}
        manifest["seabed_join"] = {"formula": "max p>=0,sum(p)=1 [p dot h + tau/2*(1-dot(p,p))]; all contributors in one solve",
            "tau_max_m": config.seabed_join_softness_m, "global_uplift_bound_m": config.seabed_join_softness_m/2,
            "coexistence": "smoothstep((sum(h)-sqrt(sum(h²)))/640m)",
            "depth_gate": "tau*=smoothstep((-30m-(base+L16(h)))/200m); max surface>=-30m strictly unchanged by join",
            "reef_gate": "tau*=1-max continuous atoll support envelope; inner reef/lagoon untouched",
            "limits": "no pairwise correction accumulation, no hard height clipping; isolated or zero supports unchanged; dynamic batches reserve source/network/output storage and 192 bytes per catalog feature per batch point, at most16384 points"}
    if algorithm in VOLCANIC_ALGORITHMS:
        manifest["volcano_model"] = {"stages": list(VOLCANO_STAGES), "random_domain": "ocean-island-volcanic-stages-v4",
            "selection": "SHA256 world seed and stable feature key; exposed hotspot/arc only",
            "hotspot_phase": "stage/(stages-1); thresholds 1/6,1/3,1/2; older exposed cones eroded",
            "authority": "bounded continuous summit replacement before atoll lagoon authority; land-only protection",
            "semantics": "static game morphology scenarios; no eruption, magma or calibrated geological ages"}
    if algorithm == ALGORITHM:
        manifest["volcano_model"].update({"geometry_random_domain": "ocean-island-volcanic-edifices-v5",
            "geometry": "bounded submarine base, low elongated lobed lava apron, eccentric compact upper cones; summit pits and nested vents; caldera rim and broad basin; one local outward-opening erosion amphitheatre",
            "authority": "continuous replacement full through .36 support radius, zero beyond .55; existing seabed fusion and lagoon priority retained; land-only protection",
            "derivation": "SHA256 fixed feature subseed; no query state; erosion vanishes outside upper edifice"})
        if config.volcanic_lava_strength > 0:
            manifest["volcano_model"]["ordinary_valley_policy"] = "ordinary island valley paths disabled on special v5 features; static local collapse does not extend into low apron or seabed"
            manifest["volcano_model"]["lava_geometry"] = {"random_domain": "volcanic-lava-v5", "strength": "volcanic_lava_strength; zero exactly replays the pre-lava v5 edifice", "spacing_m": [6200., 2100., 720.],
                "field": "compact soft nearest-site Voronoi with quintic domain warp; fixed 3x3 sites, seed jitter .26..74 cell, support radius1.25cell; omitted sites at least1.26cell away",
                "relief": "coarse horizontal edifice/rim deformation plus broad .090 and medium .026 target-peak accumulation; continuous summit and near-sea masks; eroded amplitude .35; no cell-boundary crack carving"}
    # Roundtrip gives immutable grid tuples their canonical JSON list form.
    manifest = json.loads(canonical_json(manifest))
    manifest["identity"] = _identity(manifest)
    return manifest


def _feature(source, config, parameter_id, key, chain, kind, x, z, stage, age, peak, radius, basis, boundary=None, boundary_kind=None, hotspot=None, velocity=None):
    fields = source.sample(x, z)
    if float(_coastal_weight(fields)) < .88:
        return None
    base = float(fields["elevation_m"])
    # Limit the maximum implied seabed slope; an impossible deep isolated cone
    # becomes a seamount rather than a vertical land pedestal.
    peak = min(peak, base + .28 * radius)
    if kind in ("hotspot", "atoll") and peak < 0:
        kind = "seamount"
    orientation = 2 * math.pi * _unit(config.world_seed, "shape-orientation", key)
    seed = int(_unit(config.world_seed, "shape-subseed", key) * (2**53 - 1))
    hotspot = hotspot or (x, z)
    velocity = velocity or (0., 0.)
    return OceanIslandFeature(key, chain, kind, float(x), float(z), float(radius), float(peak), base,
                              stage, float(age), int(fields["plate_id"]), boundary, boundary_kind, basis, seed,
                              orientation, .68 + .3 * _unit(config.world_seed, "shape-ratio", key),
                              float(hotspot[0]), float(hotspot[1]), float(velocity[0]), float(velocity[1]), source.identity, parameter_id)


def _hotspot_candidate(config, cx, cz):
    side = config.candidate_cell_m
    x = (cx + .18 + .64 * _unit(config.world_seed, "hotspot-x", cx, cz)) * side
    z = (cz + .18 + .64 * _unit(config.world_seed, "hotspot-z", cx, cz)) * side
    priority = _unit(config.world_seed, "hotspot-priority", cx, cz)
    return x, z, priority


def _same_plate_segment(source, hx, hz, vx, vz, age, plate_id):
    """Visit every crossed cell interval, including arbitrarily short diagonals.

    The frozen finite grid bounds work by nz+nx breakpoints; no step count is
    obtained by dividing a trajectory by an arbitrarily small source spacing.
    """
    spacing = source.grid["spacing_m"]
    nz, nx = source.grid["shape_zx"]
    xmin, zmin, _, _ = source.bounds_m
    times = [np.array([0., age])]
    for start, velocity, origin, count in ((hx, vx, xmin, nx), (hz, vz, zmin, nz)):
        if velocity == 0:
            continue
        crossings = (origin + np.arange(1, count) * spacing - start) / velocity
        times.append(crossings[(crossings > 0) & (crossings < age)])
    breaks = np.unique(np.concatenate(times))
    midpoints = (breaks[:-1] + breaks[1:]) * .5
    probes = np.concatenate(([0., age], midpoints))
    ix = np.clip(np.floor((hx + vx * probes - xmin) / spacing).astype(np.int64), 0, nx - 1)
    iz = np.clip(np.floor((hz + vz * probes - zmin) / spacing).astype(np.int64), 0, nz - 1)
    return bool(np.all(source.plate_id[iz, ix] == plate_id))


def _hotspots(source, config, parameter_id, density):
    xmin, zmin, xmax, zmax = source.bounds_m
    side = config.candidate_cell_m
    xs = range(math.floor(xmin / side), math.ceil(xmax / side))
    zs = range(math.floor(zmin / side), math.ceil(zmax / side))
    candidate_count = len(xs) * len(zs)
    if candidate_count > config.max_candidates:
        raise ValueError("hotspot candidate budget exceeded")
    accepted = []
    halo = math.ceil(config.min_hotspot_spacing_m / side) + 1
    for cz in zs:
        for cx in xs:
            x, z, score = _hotspot_candidate(config, cx, cz)
            if not _inside(source.bounds_m, x, z):
                continue
            if config.hotspot_count is None and score >= density:
                continue
            # Compare absolute candidates, including outside this finite source.
            # This fixed-neighbour priority rule does not depend on query windows.
            winner = True
            for nz in range(cz - halo, cz + halo + 1):
                for nx in range(cx - halo, cx + halo + 1):
                    if (nx, nz) == (cx, cz):
                        continue
                    ox, oz, other = _hotspot_candidate(config, nx, nz)
                    if other < score and math.hypot(ox - x, oz - z) < config.min_hotspot_spacing_m:
                        winner = False
                        break
                if not winner:
                    break
            if winner and float(_coastal_weight(source.sample(x, z))) >= .98:
                accepted.append((score, cx, cz, x, z))
    accepted.sort()
    if config.hotspot_count is not None:
        accepted = accepted[:config.hotspot_count]
    features = []
    terminations = []
    for _, cx, cz, hx, hz in accepted:
        fields = source.sample(hx, hz)
        plate = int(fields["plate_id"])
        velocity = source.velocities_m_per_step[plate]
        speed = float(np.linalg.norm(velocity))
        if speed > config.max_speed_m_per_step:
            raise ValueError("source plate speed exceeds declared dependency bound")
        max_age = min(config.max_age_steps, config.max_chain_length_m / max(speed, 1e-9))
        chain = f"hotspot:{config.world_seed}:{cx}:{cz}"
        # With a static plate there is one volcanic field, not coincident old islands.
        count = config.stages if speed > 10 else 1
        generated = 0
        reason = "maximum configured stage" if count > 1 else "static plate; one volcanic field"
        for stage in range(count):
            fraction = stage / (config.stages - 1)
            jitter = 0. if stage in (0, config.stages - 1) else (.35 * _unit(config.world_seed, "age-slot", cx, cz, stage) - .175) / (config.stages - 1)
            age = max_age * (fraction + jitter)
            x, z = hx + velocity[0] * age, hz + velocity[1] * age
            if not _inside(source.bounds_m, x, z):
                reason = "trajectory leaves finite source"
                break
            if not _same_plate_segment(source, hx, hz, velocity[0], velocity[1], age, plate):
                reason = "first foreign plate crossed"
                break
            key = chain + f":stage:{stage}"
            peak = 1750 * math.exp(-2.2 * fraction) - 2200 * fraction**2
            peak *= .85 + .3 * _unit(config.world_seed, "peak", cx, cz, stage)
            radius = min(config.max_support_radius_m, (42000 + 21000 * _unit(config.world_seed, "radius", cx, cz)) * (1 - .35 * fraction))
            kind = "hotspot" if peak >= 0 else "seamount"
            if config.atolls and .48 <= fraction <= .84 and _unit(config.world_seed, "atoll", cx, cz, stage) < .7:
                kind, peak = "atoll", 5 + 6 * _unit(config.world_seed, "reef-height", cx, cz, stage)
            basis = "absolute-cell fixed-slot hotspot; constant plate velocity; stop at first foreign plate"
            if kind == "atoll":
                basis += "; declared warm-water shallow-platform game scenario; old-stage platform reconstructed at -35m; not coral growth"
            feature = _feature(source, config, parameter_id, key, chain, kind, x, z, stage, age, peak, radius,
                               basis, hotspot=(hx, hz), velocity=tuple(velocity))
            if feature is None:
                reason = "coastal/continental/ocean-connection suitability fades"
                break
            features.append(feature)
            generated += 1
            if len(features) > config.max_features:
                raise ValueError("feature budget exceeded")
        terminations.append({"chain_id": chain, "generated_stages": generated, "termination": reason, "max_age_steps": max_age})
    return features, candidate_count, len(accepted), terminations


def _boundary_features(source, config, parameter_id, density):
    plate = source.plate_id
    spacing = source.grid["spacing_m"]
    xmin, zmin, _, _ = source.bounds_m
    rows = []
    # Stable absolute grid-face IDs, never connected-component enumeration.
    for axis in (0, 1):
        left = plate[:-1, :] if axis == 0 else plate[:, :-1]
        right = plate[1:, :] if axis == 0 else plate[:, 1:]
        izs, ixs = np.nonzero(left != right)
        for iz, ix in zip(izs.tolist(), ixs.tolist()):
            if len(rows) >= config.max_boundary_segments:
                raise ValueError("boundary face budget exceeded")
            pa, pb = int(plate[iz, ix]), int(plate[iz + (axis == 0), ix + (axis == 1)])
            x = xmin + (ix + (.5 if axis == 0 else 1.)) * spacing
            z = zmin + (iz + (1. if axis == 0 else .5)) * spacing
            token = _identity([axis, float(x).hex(), float(z).hex(), min(pa, pb), max(pa, pb)])[:24]
            rows.append((axis, iz, ix, pa, pb, x, z, token))
    if len(rows) > config.max_boundary_segments:
        raise ValueError("boundary face budget exceeded")
    features = []
    # An absolute spatial index gives a fixed local dependency. Same-pair PCA
    # smooths stair-step grid faces into a bounded trench tangent, without
    # reconstructing whole-window components or assigning component IDs.
    local_radius = max(3 * spacing, config.boundary_spacing_m)
    bins = {}
    for index, (_, _, _, pa, pb, x, z, _) in enumerate(rows):
        key = (min(pa, pb), max(pa, pb), math.floor(x / local_radius), math.floor(z / local_radius))
        bins.setdefault(key, []).append(index)
    for axis, iz, ix, pa, pb, anchor_x, anchor_z, token in rows:
        jz, jx = iz + (axis == 0), ix + (axis == 1)
        if max(source.continental_fraction[iz, ix], source.continental_fraction[jz, jx]) >= .2 or not (source.ocean_connected[iz, ix] and source.ocean_connected[jz, jx]):
            continue
        pair = (min(pa, pb), max(pa, pb))
        bx, bz = math.floor(anchor_x / local_radius), math.floor(anchor_z / local_radius)
        neighbours = []
        for dz in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for index in bins.get((*pair, bx + dx, bz + dz), ()):
                    row = rows[index]
                    if math.hypot(row[5] - anchor_x, row[6] - anchor_z) <= local_radius:
                        neighbours.append(row)
        face_normal = np.array([float(axis == 1), float(axis == 0)])
        normal = face_normal.copy()
        if len(neighbours) >= 3:
            positions = np.array([[row[5] - anchor_x, row[6] - anchor_z] for row in neighbours])
            weights = np.maximum(0., 1 - np.linalg.norm(positions, axis=1) / local_radius)**2
            centred = positions - np.average(positions, axis=0, weights=weights)
            covariance = (centred * weights[:, None]).T @ centred
            eigenvalues, eigenvectors = np.linalg.eigh(covariance)
            if eigenvalues[1] > 1e-6 and eigenvalues[0] < .7 * eigenvalues[1]:
                tangent = eigenvectors[:, 1]
                normal = np.array([-tangent[1], tangent[0]])
                if np.dot(normal, face_normal) < 0:
                    normal *= -1
        tangent = np.array([-normal[1], normal[0]])
        relative = float(np.dot(source.velocities_m_per_step[pb] - source.velocities_m_per_step[pa], normal))
        if abs(relative) <= 5:
            continue
        kind = "arc" if relative < 0 else "ridge"
        if (kind == "arc" and not config.arcs) or (kind == "ridge" and not config.ridge):
            continue
        x, z = anchor_x, anchor_z
        boundary = f"face:{token}"
        # Thinning uses a physical along-boundary spacing and local absolute-face
        # priorities; resolution is part of the pinned source identity.
        priority = _unit(config.world_seed, "boundary-priority", boundary)
        if priority >= density:
            continue
        # Local priority thinning preserves gaps and stable spacing along the
        # boundary. Every contender participates, independent of density.
        if any(row[7] != token and math.hypot(row[5] - anchor_x, row[6] - anchor_z) < config.boundary_spacing_m
               and _unit(config.world_seed, "boundary-priority", "face:" + row[7]) < priority for row in neighbours):
            continue
        if kind == "arc":
            # More continental material is the buoyant overriding plate; ties
            # choose lower plate ID. Both are oceanic here: declared proxy only.
            ca, cb = float(source.continental_fraction[iz, ix]), float(source.continental_fraction[jz, jx])
            side = -1 if ca > cb or (ca == cb and pa < pb) else 1
            offset = normal * side * config.arc_offset_m
            x, z = x + offset[0], z + offset[1]
            target_plate = pa if side < 0 else pb
            peak = 650 + 1050 * _unit(config.world_seed, "arc-peak", boundary)
            radius = min(config.max_support_radius_m, 34000 + 16000 * _unit(config.world_seed, "arc-radius", boundary))
            basis = f"ocean-ocean convergence {relative:.9g} m/offline-step; upper plate={target_plate}; greater continental fraction then lower plate-ID polarity proxy; normal=({normal[0]*side:g},{normal[1]*side:g}); offset={config.arc_offset_m:g}m"
        else:
            target_plate = None
            emerged = _unit(config.world_seed, "ridge-emerged", boundary) < .16
            peak = (350 + 550 * _unit(config.world_seed, "ridge-peak", boundary)) if emerged else -300 - 1200 * _unit(config.world_seed, "ridge-peak", boundary)
            radius = min(config.max_support_radius_m, 33000 + 12000 * _unit(config.world_seed, "ridge-radius", boundary))
            basis = f"ocean-ocean divergence {relative:.9g} m/offline-step; isolated ridge platform; emergent probability=0.16"
        if not _inside(source.bounds_m, x, z):
            continue
        if target_plate is not None and int(source.sample(x, z)["plate_id"]) != target_plate:
            continue
        feature = _feature(source, config, parameter_id, f"{kind}:{config.world_seed}:{token}", f"{kind}-boundary:{min(pa,pb)}:{max(pa,pb)}", kind,
                           x, z, 0, 0, peak, radius, basis, boundary, "convergent" if kind == "arc" else "divergent")
        if feature is not None:
            upper_normal = normal * side if kind == "arc" else normal
            feature = replace(feature, orientation_rad=math.atan2(tangent[1], tangent[0]),
                              boundary_anchor_x_m=float(anchor_x), boundary_anchor_z_m=float(anchor_z),
                              boundary_normal_x=float(upper_normal[0]), boundary_normal_z=float(upper_normal[1]),
                              boundary_tangent_x=float(tangent[0]), boundary_tangent_z=float(tangent[1]),
                              upper_plate_id=target_plate, boundary_relative_velocity_m_per_step=relative)
            features.append(feature)
        if len(features) > config.max_features:
            raise ValueError("boundary feature budget exceeded")
    return features, len(rows)


def _assign_volcano_stage(feature, config):
    if feature.kind not in ("hotspot", "arc") or feature.peak_elevation_m <= 0:
        return feature
    domain = "ocean-island-volcanic-stages-v4"
    if _unit(config.world_seed, domain, "selection", feature.feature_id) >= config.volcanic_fraction:
        return feature
    phase = feature.stage / (config.stages - 1) if feature.kind == "hotspot" else _unit(config.world_seed, domain, "arc-stage", feature.feature_id) * (2/3)
    index = min(3, int(phase * 6 + 1e-12))
    return replace(feature, volcano_stage=VOLCANO_STAGES[index])


def prepare_ocean_islands(source, config=None):
    """Prepare a complete bounded inventory; query never calls this function."""
    config = config or OceanIslandConfig()
    if not isinstance(source, PlateOceanSource) or not isinstance(config, OceanIslandConfig):
        raise TypeError("expected PlateOceanSource and OceanIslandConfig")
    cells, source_bytes = _check_source_budget(source, config)
    parameter_id = _identity(_config_record(config, ALGORITHM))
    density = {"none": 0., "low": .28, "medium": .54, "high": .85}[config.density]
    density *= {"continental": .65, "balanced": 1., "archipelago": 1.15, "islands": 1.15, "oceanic": 1.05, "waterworld": 1.05,
                "multi-continent": .85, "pangaea": .65, "two-continents": .8, "inland-sea": .6}[config.world_type]
    features, candidates, hotspots, boundaries = [], 0, 0, 0
    terminations = []
    if density > 0:
        features, candidates, hotspots, terminations = _hotspots(source, config, parameter_id, density)
        if config.arcs or config.ridge:
            boundary, boundaries = _boundary_features(source, config, parameter_id, density)
            features.extend(boundary)
    if len(features) > config.max_features:
        raise ValueError("combined feature budget exceeded")
    local_support_count = _check_overlap_budget(features, config)
    features = tuple(sorted((_assign_volcano_stage(f, config) for f in features), key=lambda f: f.feature_id))
    preparation = {"source_cells": cells, "source_bytes": source_bytes, "candidate_slots": candidates, "hotspots": hotspots,
                   "boundary_faces": boundaries, "feature_count": len(features), "max_local_support_count": local_support_count,
                   "dependencies": _dependencies(source, config), "dependency_radius_m": _dependencies(source, config)["conservative_geometry_and_hash_radius_m"],
                   "chain_terminations": terminations,
                   "cross_plate_policy": "stop older chain at first foreign plate; every crossed grid-cell interval checked", "source_domain": "finite; supports clipped at source edges", "query_cache_entries": 0}
    return FrozenOceanIslands(source, config, features, _manifest(source, config, features, preparation))


def save_product(product, path):
    """Atomic no-overwrite publication, validated by a cold read before linking."""
    if not isinstance(product, FrozenOceanIslands):
        raise TypeError("expected FrozenOceanIslands")
    if product.manifest["algorithm"] != ALGORITHM:
        raise ValueError("legacy v1/v2/v3/v4 products are read-only; prepare a new v5 product explicitly")
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".ocean-islands-", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            np.savez_compressed(stream, manifest_json=np.array(canonical_json(product.manifest)), **{name: getattr(product.source, name) for name in SOURCE_FIELDS})
            stream.flush()
            os.fsync(stream.fileno())
        loaded = load_product(temporary, expected_identity=product.identity)
        os.link(temporary, path)
        return loaded
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_product(path, expected_identity=None):
    try:
        manifest, arrays = _archive(path)
        if manifest.get("schema") != SCHEMA or manifest.get("algorithm") not in SUPPORTED_ALGORITHMS:
            raise ValueError("unsupported ocean island product")
        legacy = manifest["algorithm"] == LEGACY_ALGORITHM
        if ("valley_strength" in manifest["config"]) == legacy:
            raise ValueError("valley_strength configuration does not match algorithm version")
        if any((name in manifest["config"]) != (manifest["algorithm"] in (METRIC_ALGORITHM, *VOLCANIC_ALGORITHMS)) for name in ("detail_strength", "seabed_join_softness_m")):
            raise ValueError("detail configuration does not match algorithm version")
        if set(arrays) != set(SOURCE_FIELDS) or manifest["arrays"] != {name: _summary(value) for name, value in arrays.items()}:
            raise ValueError("island source array integrity mismatch")
        record = manifest["source"]
        source = PlateOceanSource(record["grid"], arrays, record["identity"], record["world_seed"], record["kind"], record["original_manifest"])
        original = record["original_manifest"]
        if original:
            payload = dict(original)
            if payload.pop("identity", None) != source.identity or _identity(payload) != source.identity:
                raise ValueError("embedded original source identity mismatch")
            original_config = original["config"]
            original_grid = {"origin_x_m": original_config["origin_x_m"], "origin_z_m": original_config["origin_z_m"],
                             "spacing_m": original_config["cell_size_m"], "shape_zx": tuple(original_config["shape"])}
            if source.world_seed != original_config["world_seed"] or dict(source.grid) != original_grid:
                raise ValueError("embedded source seed/grid mismatch")
            for name in SOURCE_FIELDS:
                summary = original["arrays"]["final/" + name]
                if (summary["sha256"] != array_sha256_raw(arrays[name]) or summary["shape"] != list(arrays[name].shape)
                        or np.dtype(summary["dtype"]) != arrays[name].dtype):
                    raise ValueError("embedded source SHA/shape/dtype mismatch")
        if ("volcanic_fraction" in manifest["config"]) != (manifest["algorithm"] in VOLCANIC_ALGORITHMS):
            raise ValueError("volcanic configuration does not match algorithm version")
        if "volcanic_lava_strength" in manifest["config"] and manifest["algorithm"] != ALGORITHM:
            raise ValueError("lava configuration does not match algorithm version")
        config = OceanIslandConfig(**dict({"volcanic_fraction": 0., "volcanic_lava_strength": 0.}, **manifest["config"]))
        product = FrozenOceanIslands(source, config, (OceanIslandFeature(**record) for record in manifest["features"]), manifest)
    except (KeyError, TypeError, OSError, EOFError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid ocean island product") from error
    if expected_identity is not None and product.identity != expected_identity:
        raise ValueError("unexpected island identity")
    return product
