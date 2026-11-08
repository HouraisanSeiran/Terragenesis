"""Explicit metric, fixed-route channel-bed planning diagnostics."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash
from terrain_pipeline.drainage import grid_mesh as grid_mesh
from terrain_pipeline.drainage import receiver_edges_valid as receiver_edges_valid


PLAN_VERSION = "metric-channel-plan-v2-irregular"


def _mesh_from_parameters(parameters, shape):
    return grid_mesh(shape, x0_m=parameters["origin_x_m"], z0_m=parameters["origin_z_m"],
        dx_m=parameters["spacing_x_m"], dz_m=parameters["spacing_z_m"],
        world_seed=parameters.get("world_seed", 20261020))


@dataclass(frozen=True)
class ChannelRecipe:
    start_discharge_m3_s: float = .05
    reference_discharge_m3_s: float = .05
    reference_width_m: float = 3.
    reference_depth_m: float = .8
    width_exponent: float = .5
    depth_exponent: float = .3
    min_width_m: float = 1.
    max_width_m: float = 30.
    min_depth_m: float = .2
    max_depth_m: float = 3.
    min_bed_slope_m_per_m: float = .0001
    max_cut_m: float = 4.
    min_cells_across_width: float = 2.

    def __post_init__(self):
        positive = ("start_discharge_m3_s", "reference_discharge_m3_s", "reference_width_m",
                    "reference_depth_m", "min_width_m", "max_width_m", "min_depth_m",
                    "max_depth_m", "min_bed_slope_m_per_m", "min_cells_across_width")
        for name in positive:
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("width_exponent", "depth_exponent", "max_cut_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.max_width_m < self.min_width_m or self.max_depth_m < self.min_depth_m:
            raise ValueError("maximum width and depth must exceed minimum")


def _validate_route(receiver, order, shape, outlet_mask, mesh=None, *, historical_saved_graph=False):
    count = int(np.prod(shape))
    receiver = np.asarray(receiver)
    order = np.asarray(order)
    outlets = np.asarray(outlet_mask)
    if (receiver.dtype.kind not in "iu" or order.dtype.kind not in "iu" or
            receiver.size != count or order.size != count or outlets.shape != shape or
            outlets.dtype != bool):
        raise ValueError("invalid route arrays")
    receiver = receiver.reshape(-1).astype(np.int64)
    order = order.reshape(-1).astype(np.int64)
    if (np.any((receiver < -1) | (receiver >= count)) or
            not np.array_equal(np.sort(order), np.arange(count)) or
            not np.array_equal(receiver == -1, outlets.ravel())):
        raise ValueError("invalid route topology or outlets")
    rank = np.empty(count, dtype=np.int64)
    rank[order] = np.arange(count)
    if np.any((receiver >= 0) & (rank[np.maximum(receiver, 0)] >= rank)):
        raise ValueError("route receiver must precede donor")
    if historical_saved_graph:
        return receiver, order
    if mesh is None:
        mesh = grid_mesh(shape)
    if not receiver_edges_valid(receiver, mesh):
        raise ValueError("route must use actual irregular graph edges")
    return receiver, order


def plan_channel(height_m, receiver, order, outlet_mask, discharge_m3_s,
                 spacing_x_m, spacing_z_m, origin_x_m, origin_z_m,
                 sea_level_elevation_m, source_identity, recipe: ChannelRecipe, *, world_seed=20261020):
    """Return a separate plan; no source array or routed product is changed."""
    if not isinstance(recipe, ChannelRecipe) or not isinstance(source_identity, str) or not source_identity:
        raise ValueError("recipe and nonempty source identity are required")
    height = np.asarray(height_m, dtype=np.float64)
    q = np.asarray(discharge_m3_s, dtype=np.float64)
    if (height.ndim != 2 or height.size == 0 or q.shape != height.shape or
            not np.isfinite(height).all() or not np.isfinite(q).all() or np.any(q < 0)):
        raise ValueError("height and nonnegative discharge must be finite matching 2D arrays")
    for name, value in (("spacing_x_m", spacing_x_m), ("spacing_z_m", spacing_z_m)):
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if any(not math.isfinite(value) for value in
           (origin_x_m, origin_z_m, sea_level_elevation_m)):
        raise ValueError("origin and sea datum must be finite")
    mesh = grid_mesh(height.shape, x0_m=origin_x_m, z0_m=origin_z_m,
        dx_m=spacing_x_m, dz_m=spacing_z_m, world_seed=world_seed)
    downstream, ordered = _validate_route(receiver, order, height.shape, outlet_mask, mesh)
    active = q >= recipe.start_discharge_m3_s
    active_flat = active.ravel()
    for cell in np.flatnonzero(active_flat):
        next_cell = downstream[cell]
        if next_cell >= 0 and not active_flat[next_cell]:
            raise ValueError("active channel terminates before explicit outlet")
    ratio = q[active] / recipe.reference_discharge_m3_s
    width = np.zeros(height.shape, dtype=np.float64)
    depth = np.zeros(height.shape, dtype=np.float64)
    width[active] = np.clip(recipe.reference_width_m * ratio ** recipe.width_exponent,
                            recipe.min_width_m, recipe.max_width_m)
    depth[active] = np.clip(recipe.reference_depth_m * ratio ** recipe.depth_exponent,
                            recipe.min_depth_m, recipe.max_depth_m)
    if not np.isfinite(width).all() or not np.isfinite(depth).all():
        raise ValueError("nominal width or depth overflows")
    target = height.ravel().copy()
    target[active.ravel()] -= depth.ravel()[active.ravel()]
    cols = height.shape[1]
    for cell in ordered[::-1]:
        next_cell = downstream[cell]
        if next_cell < 0 or not active.flat[cell] or not active.flat[next_cell]:
            continue
        dz = mesh.node_z_m[cell] - mesh.node_z_m[next_cell]
        dx = mesh.node_x_m[cell] - mesh.node_x_m[next_cell]
        drop = recipe.min_bed_slope_m_per_m * math.hypot(dx, dz)
        target[next_cell] = min(target[next_cell], target[cell] - drop)
    target = target.reshape(height.shape)
    required_cut = np.maximum(0., height - target)
    if not np.isfinite(target).all() or not np.isfinite(required_cut).all():
        raise ValueError("planned bed or cut overflows")
    allowed_cut = np.minimum(required_cut, recipe.max_cut_m)
    bounded_bed = height - allowed_cut
    over_budget = active & (required_cut > recipe.max_cut_m + 1e-9)
    failed_edge = np.zeros(height.shape, dtype=bool)
    for cell in ordered[::-1]:
        next_cell = downstream[cell]
        if next_cell < 0 or not active.flat[cell] or not active.flat[next_cell]:
            continue
        dz = mesh.node_z_m[cell] - mesh.node_z_m[next_cell]
        dx = mesh.node_x_m[cell] - mesh.node_x_m[next_cell]
        drop = recipe.min_bed_slope_m_per_m * math.hypot(dx, dz)
        if bounded_bed.flat[next_cell] > bounded_bed.flat[cell] - drop + 1e-9:
            failed_edge.flat[cell] = True
    needs_refinement = active & (width < recipe.min_cells_across_width * max(spacing_x_m, spacing_z_m))
    params = {**asdict(recipe), "world_seed": world_seed, "routing": "irregular_graph_v1",
              "spacing_x_m": float(spacing_x_m),
              "spacing_z_m": float(spacing_z_m), "origin_x_m": float(origin_x_m),
              "origin_z_m": float(origin_z_m),
              "sea_level_elevation_m": float(sea_level_elevation_m),
              "source_identity": source_identity,
              "source_height_sha256": array_hash(np.ascontiguousarray(height, dtype="<f8")),
              "source_discharge_sha256": array_hash(np.ascontiguousarray(q, dtype="<f8")),
              "source_route_sha256": array_hash(np.ascontiguousarray(downstream)),
              "source_order_sha256": array_hash(np.ascontiguousarray(ordered)),
              "source_outlet_sha256": array_hash(np.ascontiguousarray(outlet_mask))}
    identity = ArtifactIdentity("Terragenesis", "metric-channel-plan", PLAN_VERSION, 0, params)
    arrays = {"source_height_m": height.copy(), "discharge_m3_s": q.copy(),
              "receiver": downstream.copy(), "order": ordered.copy(),
              "outlet_mask": np.asarray(outlet_mask, dtype=bool).copy(),
              "channel_mask": active, "nominal_width_m": width,
              "nominal_depth_m": depth, "target_bed_m": target,
              "bounded_bed_m": bounded_bed, "required_cut_m": required_cut,
              "over_budget_mask": over_budget, "needs_refinement_mask": needs_refinement}
    arrays["failed_slope_edge_donor_mask"] = failed_edge
    for value in arrays.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": arrays}


def save_plan(plan, path):
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    arrays = plan["arrays"]
    record = {"format_version": 1, "status": plan["status"],
              "identity": plan["identity"], "identity_sha256": plan["identity_sha256"],
              "array_sha256": {name: array_hash(np.ascontiguousarray(value))
                               for name, value in arrays.items()}}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=f".{destination.name}-",
                                         suffix=".npz", dir=destination.parent,
                                         delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **arrays)
        load_plan(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_plan(path):
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        expected = {"source_height_m", "discharge_m3_s", "receiver", "order",
                    "outlet_mask", "channel_mask", "nominal_width_m", "nominal_depth_m",
                    "target_bed_m", "bounded_bed_m", "required_cut_m", "over_budget_mask",
                    "needs_refinement_mask", "failed_slope_edge_donor_mask"}
        if set(record["array_sha256"]) != expected or set(archive.files) != expected | {"manifest"}:
            raise ValueError("invalid plan array set")
        arrays = {name: archive[name].copy() for name in record["array_sha256"]}
    identity = ArtifactIdentity(**record["identity"])
    if (record["format_version"] != 1 or record["status"] != "diagnostic_not_publishable" or
            identity.sha256 != record["identity_sha256"] or
            any(array_hash(np.ascontiguousarray(arrays[name])) != expected
                for name, expected in record["array_sha256"].items())):
        raise ValueError("invalid plan identity or arrays")
    shape = arrays["source_height_m"].shape
    if (len(shape) != 2 or any(size == 0 for size in shape) or
            any(arrays[name].shape != shape for name in expected - {"receiver", "order"}) or
            arrays["receiver"].shape != (arrays["source_height_m"].size,) or
            arrays["order"].shape != arrays["receiver"].shape):
        raise ValueError("invalid plan shapes")
    params = identity.record()["parameters"]
    float_fields = {"source_height_m", "discharge_m3_s", "nominal_width_m",
                    "nominal_depth_m", "target_bed_m", "bounded_bed_m", "required_cut_m"}
    bool_fields = {"outlet_mask", "channel_mask", "over_budget_mask",
                   "needs_refinement_mask", "failed_slope_edge_donor_mask"}
    for name in float_fields:
        if arrays[name].dtype != np.dtype("float64") or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid finite float plan array")
    for name in bool_fields:
        if arrays[name].dtype != np.dtype(bool):
            raise ValueError("invalid boolean plan array")
    for name in ("receiver", "order"):
        if arrays[name].dtype != np.dtype("int64"):
            raise ValueError("invalid route index dtype")
    historical = identity.algorithm_version == "metric-channel-plan-v1"
    mesh = None if historical else _mesh_from_parameters(params, shape)
    _validate_route(arrays["receiver"], arrays["order"], shape, arrays["outlet_mask"], mesh,
                    historical_saved_graph=historical)
    ChannelRecipe(**{name: params[name] for name in ChannelRecipe.__dataclass_fields__})
    for name, field in (("source_height_m", "source_height_sha256"),
                        ("discharge_m3_s", "source_discharge_sha256"),
                        ("receiver", "source_route_sha256"),
                        ("order", "source_order_sha256"),
                        ("outlet_mask", "source_outlet_sha256")):
        if array_hash(np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError("plan input differs from identity")
    for value in arrays.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": record["status"], "arrays": arrays}
