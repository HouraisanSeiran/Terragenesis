"""Bounded shared centerline shaping on a fixed original-source river graph."""

from dataclasses import asdict, dataclass
import math

import numpy as np

from terrain_pipeline.mountain_source_adapter import identity, load_bundle, readonly, save_bundle
from .metric_channel_geometry import _footprint, _route_crossings, _sample
from .metric_contracts import TerrainGrid
from .metric_valley_incision import (
    _check_inputs, _metadata_terrain, _profile, _profile_overlap,
)
from .metric_channel_geometry import GeometryConfig


SCHEMA = "terragenesis-metric-valley-centerline-v1"
ALGORITHM = "anchored-bounded-original-valley-laplacian-v1"
MAX_BYTES = 128 * 1024 * 1024


@dataclass(frozen=True)
class CenterlineRecipe:
    strength: float = .25
    max_node_offset_m: float = 2.
    max_source_rise_m: float = .5
    iterations: int = 2

    def __post_init__(self):
        if (not 0. < self.strength <= .5 or self.max_node_offset_m < 0.
                or self.max_source_rise_m < 0. or self.iterations < 1
                or self.iterations > 16 or any(not math.isfinite(v) for v in (
                    self.strength, self.max_node_offset_m, self.max_source_rise_m))):
            raise ValueError("invalid bounded centerline recipe")


def _anchors(receiver):
    degree = np.bincount(receiver[receiver >= 0], minlength=len(receiver))
    return (degree != 1) | (receiver < 0)


def _turn_energy(points, receiver):
    incoming = np.full(len(receiver), -1, np.int64)
    for i, j in enumerate(receiver):
        if j >= 0 and incoming[j] < 0:
            incoming[j] = i
    total = 0.
    for i, j in enumerate(receiver):
        if j < 0 or incoming[i] < 0:
            continue
        first = points[i] - points[incoming[i]]
        second = points[j] - points[i]
        cosine = float(first @ second / (np.linalg.norm(first) * np.linalg.norm(second)))
        total += (1. - np.clip(cosine, -1., 1.)) ** 2
    return total


def _validate_shape(points, original, anchors, receiver, width, depth, terrain,
                    owner, corridor, lake, config, recipe):
    if (points.dtype != np.float64 or points.shape != original.shape
            or not np.isfinite(points).all() or not np.array_equal(points[anchors], original[anchors])):
        raise ValueError("source, junction or terminal anchor moved")
    offset = np.linalg.norm(points - original, axis=1)
    if np.any(offset > recipe.max_node_offset_m + 1e-9):
        raise ValueError("centerline exceeds original node offset")
    source, cells = _sample(terrain.elevation_m, points, terrain)
    original_source = _sample(terrain.elevation_m, original, terrain)[0]
    if (np.any(source - original_source > recipe.max_source_rise_m + 1e-9)
            or np.any(~terrain.valid_mask.ravel()[cells])
            or np.any(~corridor.ravel()[cells]) or np.any(lake.ravel()[cells])):
        raise ValueError("centerline leaves known original valley corridor")
    source_owner = owner.ravel()[_sample(terrain.elevation_m, original, terrain)[1]]
    if np.any(owner.ravel()[cells] != source_owner):
        raise ValueError("centerline crosses original source owner")
    _route_crossings(points, receiver)
    profile = _profile(points, receiver, depth, terrain, config.max_cut_m)
    _footprint(points, receiver, width, np.full(len(points), config.max_cut_m),
               terrain, owner, corridor, lake, source_owner, config.fine_spacing_m)
    _profile_overlap(points, receiver, width, profile, terrain)
    return profile


def build_valley_centerline(terrain, node_cell_ids, receiver, width_m, base_depth_m, *,
                            owner_grid, corridor_mask, lake_mask,
                            source_plan_identity_sha256, config=None, recipe=None):
    config = config or GeometryConfig(fine_spacing_m=.5, smoothing_iterations=0)
    recipe = recipe or CenterlineRecipe()
    _check_inputs(terrain, node_cell_ids, receiver, width_m, base_depth_m,
                  owner_grid, corridor_mask, lake_mask, config)
    if (not isinstance(recipe, CenterlineRecipe)
            or not isinstance(source_plan_identity_sha256, str)
            or len(source_plan_identity_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in source_plan_identity_sha256)):
        raise ValueError("centerline source plan identity and recipe required")
    cols = terrain.elevation_m.shape[1]
    original = np.column_stack((terrain.x0_m + node_cell_ids % cols * terrain.dx_m,
                                terrain.z0_m + node_cell_ids // cols * terrain.dz_m))
    anchors = _anchors(receiver)
    _validate_shape(original, original, anchors, receiver, width_m, base_depth_m,
                    terrain, owner_grid, corridor_mask, lake_mask, config, recipe)
    incoming = np.full(len(receiver), -1, np.int64)
    for i, j in enumerate(receiver):
        if j >= 0:
            incoming[j] = i
    points = original.copy()
    refusals = []
    for iteration in range(recipe.iterations):
        old_energy = _turn_energy(points, receiver)
        accepted = False
        for power in range(5):
            trial = points.copy()
            strength = recipe.strength / (2 ** power)
            for i, j in enumerate(receiver):
                if not anchors[i]:
                    trial[i] += strength * ((points[incoming[i]] + points[j]) / 2. - points[i])
            try:
                _validate_shape(trial, original, anchors, receiver, width_m, base_depth_m,
                                terrain, owner_grid, corridor_mask, lake_mask, config, recipe)
                if _turn_energy(trial, receiver) >= old_energy - 1e-12:
                    raise ValueError("turn energy does not decrease")
            except ValueError as error:
                refusals.append({"iteration": iteration, "step": power, "reason": str(error)})
                continue
            points = trial
            accepted = True
            break
        if not accepted:
            break
    arrays = dict(source_node_cell_ids=node_cell_ids.copy(), receiver=receiver.copy(),
                  original_node_xz_m=original, node_xz_m=points,
                  anchor_mask=anchors, width_m=width_m.copy(), base_depth_m=base_depth_m.copy(),
                  source_height_m=terrain.elevation_m.copy(), source_valid_mask=terrain.valid_mask.copy(),
                  owner_grid=owner_grid.copy(), corridor_mask=corridor_mask.copy(),
                  lake_mask=lake_mask.copy())
    metadata = dict(schema=SCHEMA, algorithm=ALGORITHM, terrain_metadata=_metadata_terrain(terrain),
                    source_identity_sha256=terrain.identity_sha256,
                    source_plan_identity_sha256=source_plan_identity_sha256,
                    config=asdict(config), recipe=asdict(recipe),
                    initial_turn_energy=_turn_energy(original, receiver),
                    final_turn_energy=_turn_energy(points, receiver),
                    moved_nodes=int(np.count_nonzero(np.linalg.norm(points - original, axis=1) > 1e-9)),
                    refused_steps=refusals, hydraulic_ready=False, publishable=False)
    arrays = {key: readonly(value) for key, value in arrays.items()}
    bundle = {"arrays": arrays, "metadata": metadata, "identity_sha256": identity(arrays, metadata)}
    validate_valley_centerline(bundle)
    return bundle


def validate_valley_centerline(bundle):
    if (not isinstance(bundle, dict) or set(bundle) != {"arrays", "metadata", "identity_sha256"}
            or bundle["identity_sha256"] != identity(bundle["arrays"], bundle["metadata"])
            or sum(value.nbytes for value in bundle["arrays"].values()) > MAX_BYTES):
        raise ValueError("centerline identity or byte budget mismatch")
    a, m = bundle["arrays"], bundle["metadata"]
    if (set(a) != {"source_node_cell_ids", "receiver", "original_node_xz_m", "node_xz_m",
                   "anchor_mask", "width_m", "base_depth_m", "source_height_m",
                   "source_valid_mask", "owner_grid", "corridor_mask", "lake_mask"}
            or set(m) != {"schema", "algorithm", "terrain_metadata", "source_identity_sha256",
                          "source_plan_identity_sha256", "config", "recipe", "initial_turn_energy",
                          "final_turn_energy", "moved_nodes", "refused_steps", "hydraulic_ready",
                          "publishable"}
            or m["schema"] != SCHEMA or m["algorithm"] != ALGORITHM
            or m["hydraulic_ready"] is not False or m["publishable"] is not False):
        raise ValueError("centerline schema or scope mismatch")
    terrain = TerrainGrid(a["source_height_m"], a["source_valid_mask"], **m["terrain_metadata"])
    if terrain.identity_sha256 != m["source_identity_sha256"]:
        raise ValueError("centerline original terrain identity mismatch")
    config = GeometryConfig(**m["config"])
    recipe = CenterlineRecipe(**m["recipe"])
    ids, receiver, width, depth = (a[key] for key in (
        "source_node_cell_ids", "receiver", "width_m", "base_depth_m"))
    _check_inputs(terrain, ids, receiver, width, depth, a["owner_grid"],
                  a["corridor_mask"], a["lake_mask"], config)
    cols = terrain.elevation_m.shape[1]
    original = np.column_stack((terrain.x0_m + ids % cols * terrain.dx_m,
                                terrain.z0_m + ids // cols * terrain.dz_m))
    anchors = _anchors(receiver)
    if (not np.array_equal(a["original_node_xz_m"], original)
            or not np.array_equal(a["anchor_mask"], anchors)):
        raise ValueError("centerline original node or anchor mismatch")
    _validate_shape(a["node_xz_m"], original, anchors, receiver, width, depth,
                    terrain, a["owner_grid"], a["corridor_mask"], a["lake_mask"],
                    config, recipe)
    initial = _turn_energy(original, receiver)
    final = _turn_energy(a["node_xz_m"], receiver)
    moved = int(np.count_nonzero(np.linalg.norm(a["node_xz_m"] - original, axis=1) > 1e-9))
    if (not math.isclose(m["initial_turn_energy"], initial, abs_tol=1e-10)
            or not math.isclose(m["final_turn_energy"], final, abs_tol=1e-10)
            or final > initial + 1e-10 or m["moved_nodes"] != moved):
        raise ValueError("centerline turn or movement ledger mismatch")
    return True


def save_valley_centerline(path, bundle):
    save_bundle(path, bundle, validator=validate_valley_centerline)


def load_valley_centerline(path, *, expected_sha256, expected_identity):
    bundle = load_bundle(path, expected_sha256=expected_sha256,
                         validator=validate_valley_centerline, max_bytes=MAX_BYTES)
    if bundle["identity_sha256"] != expected_identity:
        raise ValueError("external centerline identity mismatch")
    return bundle
