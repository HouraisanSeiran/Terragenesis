"""World-coordinate local channel cuts from one shared metric channel plan."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np
from terrain_pipeline.metric_channel_plan import _mesh_from_parameters

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.metric_channel_plan import _validate_route


VERSION = "local-channel-sections-v1"


@dataclass(frozen=True)
class SectionRecipe:
    max_local_cut_m: float = 4.
    min_cells_across_width: float = 2.

    def __post_init__(self):
        if isinstance(self.max_local_cut_m, bool) or not math.isfinite(self.max_local_cut_m) or self.max_local_cut_m < 0:
            raise ValueError("max_local_cut_m must be finite and nonnegative")
        if isinstance(self.min_cells_across_width, bool) or not math.isfinite(self.min_cells_across_width) or self.min_cells_across_width <= 0:
            raise ValueError("min_cells_across_width must be finite and positive")


def _source_surface(height, fx, fz):
    x0 = np.floor(fx).astype(int)
    z0 = np.floor(fz).astype(int)
    x1 = np.minimum(x0 + 1, height.shape[1] - 1)
    z1 = np.minimum(z0 + 1, height.shape[0] - 1)
    tx = fx - x0
    tz = fz - z0
    return ((1 - tx) * (1 - tz) * height[z0, x0] +
            tx * (1 - tz) * height[z0, x1] +
            (1 - tx) * tz * height[z1, x0] + tx * tz * height[z1, x1])


def _sweep_sections(plan, gx, gz, spacing_x_m, spacing_z_m, recipe, centerline=None):
    arrays = plan["arrays"]
    params = plan["identity"]["parameters"]
    shape = gx.shape
    source = _source_surface(
        arrays["source_height_m"],
        np.clip((gx - params["origin_x_m"]) / params["spacing_x_m"], 0, arrays["source_height_m"].shape[1] - 1),
        np.clip((gz - params["origin_z_m"]) / params["spacing_z_m"], 0, arrays["source_height_m"].shape[0] - 1))
    required = np.zeros(shape, dtype=np.float64)
    refinement = np.zeros(shape, dtype=bool)
    aliased = 0
    width = arrays["nominal_width_m"].ravel()
    bed = arrays["target_bed_m"].ravel()
    active = arrays["channel_mask"].ravel()
    receiver = arrays["receiver"]
    coarse_dx = params["spacing_x_m"]
    coarse_dz = params["spacing_z_m"]
    cols = arrays["source_height_m"].shape[1]
    if centerline is None:
        segments = ((params["origin_x_m"] + cell % cols * coarse_dx,
                     params["origin_z_m"] + cell // cols * coarse_dz,
                     params["origin_x_m"] + target % cols * coarse_dx,
                     params["origin_z_m"] + target // cols * coarse_dz,
                     width[cell], width[target], bed[cell], bed[target])
                    for cell in np.flatnonzero(active)
                    for target in (int(receiver[cell]),) if target >= 0 and active[target])
    else:
        nodes = centerline["arrays"]["node_flat_index"]
        positions = centerline["arrays"]["node_world_xz_m"]
        node_lookup = {int(cell): index for index, cell in enumerate(nodes)}
        segments = ((positions[node_lookup[int(cell)], 0], positions[node_lookup[int(cell)], 1],
                     positions[node_lookup[int(target)], 0], positions[node_lookup[int(target)], 1],
                     width[cell], width[target], bed[cell], bed[target])
                    for cell, target in zip(centerline["arrays"]["edge_donor_flat_index"],
                                            centerline["arrays"]["edge_target_flat_index"]))
    for ax, az, bx, bz, width_a, width_b, bed_a, bed_b in segments:
        radius = max(width_a, width_b) / 2
        if (max(ax, bx) + radius < gx[0, 0] or min(ax, bx) - radius > gx[0, -1] or
                max(az, bz) + radius < gz[0, 0] or min(az, bz) - radius > gz[-1, 0]):
            continue
        length2 = (bx - ax) ** 2 + (bz - az) ** 2
        t = np.clip(((gx - ax) * (bx - ax) + (gz - az) * (bz - az)) / length2, 0., 1.)
        distance = np.hypot(gx - (ax + t * (bx - ax)), gz - (az + t * (bz - az)))
        local_radius = ((1 - t) * width_a + t * width_b) / 2
        inside = distance < local_radius
        if not np.any(inside):
            aliased += 1
            continue
        refinement |= inside & (2 * local_radius <
                                recipe.min_cells_across_width * max(spacing_x_m, spacing_z_m))
        taper = np.zeros(shape)
        taper[inside] = .5 * (1 + np.cos(np.pi * distance[inside] / local_radius[inside]))
        bedline = (1 - t) * bed_a + t * bed_b
        required = np.maximum(required, np.maximum(0., source - bedline) * taper)
    return source, required, refinement, aliased


def evaluate_sections(plan, x0_m, z0_m, spacing_x_m, spacing_z_m, shape_zx,
                      protected_mask, recipe: SectionRecipe, centerline=None):
    """Sweep cosine-tapered full-width cuts; overlapping segments use the deepest cut."""
    if not isinstance(recipe, SectionRecipe) or plan.get("status") != "diagnostic_not_publishable":
        raise ValueError("validated diagnostic plan and section recipe required")
    arrays = plan["arrays"]
    params = plan["identity"]["parameters"]
    if ArtifactIdentity(**plan["identity"]).sha256 != plan["identity_sha256"]:
        raise ValueError("plan identity mismatch")
    if plan["identity"]["algorithm"] != "metric-channel-plan":
        raise ValueError("wrong plan algorithm")
    for name, field in (("source_height_m", "source_height_sha256"),
                        ("discharge_m3_s", "source_discharge_sha256"),
                        ("receiver", "source_route_sha256"),
                        ("order", "source_order_sha256"),
                        ("outlet_mask", "source_outlet_sha256")):
        if array_hash(np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError("plan input differs from identity")
    source_shape = arrays["source_height_m"].shape
    if (len(source_shape) != 2 or min(source_shape) < 2 or
            arrays["channel_mask"].shape != source_shape or
            arrays["target_bed_m"].shape != source_shape or
            arrays["nominal_width_m"].shape != source_shape or
            not np.isfinite(arrays["source_height_m"]).all() or
            not np.isfinite(arrays["target_bed_m"]).all() or
            not np.isfinite(arrays["nominal_width_m"]).all()):
        raise ValueError("invalid plan geometry arrays")
    _validate_route(arrays["receiver"], arrays["order"], source_shape, arrays["outlet_mask"],
                    _mesh_from_parameters(params, source_shape),
                    historical_saved_graph=plan["identity"]["algorithm_version"] == "metric-channel-plan-v1")
    if (np.any(arrays["nominal_width_m"][arrays["channel_mask"]] <= 0) or
            np.any(arrays["target_bed_m"] > arrays["source_height_m"] + 1e-9)):
        raise ValueError("invalid active width or bed target")
    geometry_hash = digest({name: array_hash(np.ascontiguousarray(arrays[name]))
                            for name in ("target_bed_m", "nominal_width_m", "channel_mask")})
    if centerline is not None:
        from terrain_pipeline.channel_centerline import validate_centerline_for_plan
        validate_centerline_for_plan(centerline, plan)
    if len(shape_zx) != 2 or any(type(size) is not int or size < 2 for size in shape_zx):
        raise ValueError("local grid needs at least 2x2 nodes")
    if (any(isinstance(value, bool) or not math.isfinite(value)
            for value in (x0_m, z0_m, spacing_x_m, spacing_z_m)) or
            min(spacing_x_m, spacing_z_m) <= 0):
        raise ValueError("local origin and spacing must be finite; spacing positive")
    protected = np.asarray(protected_mask)
    if protected.shape != tuple(shape_zx) or protected.dtype != bool:
        raise ValueError("protected_mask must be boolean and match local grid")
    coarse_dx = params["spacing_x_m"]
    coarse_dz = params["spacing_z_m"]
    rows, cols = arrays["source_height_m"].shape
    fine_x = x0_m + np.arange(shape_zx[1]) * spacing_x_m
    fine_z = z0_m + np.arange(shape_zx[0]) * spacing_z_m
    fx = (fine_x - params["origin_x_m"]) / coarse_dx
    fz = (fine_z - params["origin_z_m"]) / coarse_dz
    if min(fx) < -1e-9 or max(fx) > cols - 1 + 1e-9 or min(fz) < -1e-9 or max(fz) > rows - 1 + 1e-9:
        raise ValueError("local grid extends outside shared source plan")
    gx, gz = np.meshgrid(fine_x, fine_z)
    source, required, needs_refinement, aliased_segments = _sweep_sections(
        plan, gx, gz, spacing_x_m, spacing_z_m, recipe, centerline)
    if not np.isfinite(source).all() or not np.isfinite(required).all():
        raise ValueError("local section geometry overflows")
    over_budget = required > recipe.max_local_cut_m + 1e-9
    protected_conflict = protected & (required > 1e-9)
    actual = np.minimum(required, recipe.max_local_cut_m)
    actual[protected] = 0.
    boundary = np.zeros(shape_zx, dtype=bool)
    boundary[0, :] = boundary[-1, :] = True
    boundary[:, 0] = boundary[:, -1] = True
    clipped = boundary & (required > 1e-9)
    node_weight = np.ones(shape_zx)
    node_weight[[0, -1], :] *= .5
    node_weight[:, [0, -1]] *= .5
    volume = float(np.sum(actual * node_weight) * spacing_x_m * spacing_z_m)
    if not math.isfinite(volume):
        raise ValueError("local cut volume overflows")
    section_version = VERSION if centerline is None else "local-channel-sections-centerline-v1"
    identity_params = {**asdict(recipe), "plan_identity_sha256": plan["identity_sha256"],
                       "plan_geometry_sha256": geometry_hash,
                       "origin_x_m": float(x0_m), "origin_z_m": float(z0_m),
                       "spacing_x_m": float(spacing_x_m), "spacing_z_m": float(spacing_z_m),
                       "protected_mask_sha256": array_hash(protected),
                       "source_surface_sha256": array_hash(source)}
    if centerline is not None:
        identity_params["centerline_identity_sha256"] = centerline["identity_sha256"]
        identity_params["centerline_geometry_sha256"] = digest({
            name: array_hash(np.ascontiguousarray(centerline["arrays"][name]))
            for name in ("node_world_xz_m", "edge_donor_flat_index", "edge_target_flat_index")})
    identity = ArtifactIdentity("Terragenesis", "local-channel-sections", section_version, 0,
                                identity_params)
    outputs = {"source_surface_m": source, "required_cut_m": required,
               "bounded_surface_m": source - actual, "actual_cut_m": actual,
               "over_budget_mask": over_budget, "protected_mask": protected.copy(),
               "protected_conflict_mask": protected_conflict, "clipped_boundary_mask": clipped,
               "needs_refinement_mask": needs_refinement}
    for value in outputs.values():
        value.flags.writeable = False
    plan_blocked = bool(np.any(arrays["over_budget_mask"]) or
                        np.any(arrays["failed_slope_edge_donor_mask"]))
    centerline_slope_failures = (int(np.count_nonzero(centerline["arrays"]["slope_failed_donor_mask"]))
                                 if centerline is not None else 0)
    centerline_budget_failures = (int(np.count_nonzero(centerline["arrays"]["local_budget_failed_mask"]))
                                  if centerline is not None else 0)
    summary = {"actual_cut_volume_m3": volume,
                        "plan_over_budget_cells": int(np.count_nonzero(arrays["over_budget_mask"])),
                        "plan_failed_slope_edges": int(np.count_nonzero(arrays["failed_slope_edge_donor_mask"])),
                        "blocked_by_plan": plan_blocked,
                        "local_budget_conflict_nodes": int(np.count_nonzero(over_budget)),
                        "needs_refinement_nodes": int(np.count_nonzero(needs_refinement)),
                        "clipped_boundary_nodes": int(np.count_nonzero(clipped)),
                        "requires_shared_fine_extension": bool(np.any(clipped)),
                        "potentially_unsampled_segments": aliased_segments,
                        "protected_conflict_nodes": int(np.count_nonzero(protected_conflict))}
    if centerline is not None:
        summary.update({"centerline_slope_failed_edges": centerline_slope_failures,
                        "centerline_budget_failed_nodes": centerline_budget_failures,
                        "blocked_by_centerline": bool(centerline_slope_failures or centerline_budget_failures)})
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": outputs, "summary": summary}


def save_sections(result, path):
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ("identity", "identity_sha256", "status", "summary")}
    record["format_version"] = 1
    record["array_sha256"] = {name: array_hash(value) for name, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent,
                                         prefix=f".{destination.name}-", suffix=".npz",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_sections(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_sections(path):
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        arrays = {name: archive[name].copy() for name in record["array_sha256"]}
        expected = {"source_surface_m", "required_cut_m", "bounded_surface_m", "actual_cut_m",
                    "over_budget_mask", "protected_mask", "protected_conflict_mask",
                    "clipped_boundary_mask", "needs_refinement_mask"}
        if set(arrays) != expected or set(archive.files) != expected | {"manifest"}:
            raise ValueError("unexpected section arrays")
    identity = ArtifactIdentity(**record["identity"])
    if (identity.sha256 != record["identity_sha256"] or
            record["status"] != "diagnostic_not_publishable" or record["format_version"] != 1):
        raise ValueError("invalid section identity")
    if any(array_hash(arrays[name]) != expected for name, expected in record["array_sha256"].items()):
        raise ValueError("section array hash mismatch")
    params = identity.record()["parameters"]
    recipe = SectionRecipe(params["max_local_cut_m"], params["min_cells_across_width"])
    if any(not math.isfinite(params[name]) or params[name] <= 0 for name in
           ("spacing_x_m", "spacing_z_m")):
        raise ValueError("invalid section spacing")
    if (array_hash(arrays["protected_mask"]) != params["protected_mask_sha256"] or
            array_hash(arrays["source_surface_m"]) != params["source_surface_sha256"]):
        raise ValueError("section source or protection differs from identity")
    shape = arrays["source_surface_m"].shape
    if len(shape) != 2 or min(shape) < 2 or any(value.shape != shape for value in arrays.values()):
        raise ValueError("invalid section array shape")
    for name in ("source_surface_m", "required_cut_m", "bounded_surface_m", "actual_cut_m"):
        if arrays[name].dtype != np.float64 or not np.isfinite(arrays[name]).all():
            raise ValueError("invalid section float array")
    for name in set(arrays) - {"source_surface_m", "required_cut_m", "bounded_surface_m", "actual_cut_m"}:
        if arrays[name].dtype != bool:
            raise ValueError("invalid section mask array")
    if (not np.allclose(arrays["source_surface_m"] - arrays["actual_cut_m"],
                        arrays["bounded_surface_m"], atol=1e-9, rtol=0) or
            np.any(arrays["actual_cut_m"] < -1e-9) or
            np.any(arrays["actual_cut_m"] > arrays["required_cut_m"] + 1e-9) or
            np.any(arrays["protected_mask"] & (arrays["actual_cut_m"] > 1e-9))):
        raise ValueError("inconsistent section cut arrays")
    expected_over = arrays["required_cut_m"] > recipe.max_local_cut_m + 1e-9
    expected_protection = arrays["protected_mask"] & (arrays["required_cut_m"] > 1e-9)
    expected_actual = np.minimum(arrays["required_cut_m"], recipe.max_local_cut_m)
    expected_actual[arrays["protected_mask"]] = 0.
    edge = np.zeros(shape, dtype=bool)
    edge[0, :] = edge[-1, :] = True
    edge[:, 0] = edge[:, -1] = True
    expected_clipped = edge & (arrays["required_cut_m"] > 1e-9)
    if (not np.array_equal(arrays["over_budget_mask"], expected_over) or
            not np.array_equal(arrays["protected_conflict_mask"], expected_protection) or
            not np.array_equal(arrays["clipped_boundary_mask"], expected_clipped) or
            not np.allclose(arrays["actual_cut_m"], expected_actual, atol=1e-9, rtol=0)):
        raise ValueError("section masks or bounded cut disagree with required geometry")
    summary = record["summary"]
    if (summary["local_budget_conflict_nodes"] != int(np.count_nonzero(expected_over)) or
            summary["protected_conflict_nodes"] != int(np.count_nonzero(expected_protection)) or
            summary["clipped_boundary_nodes"] != int(np.count_nonzero(expected_clipped)) or
            summary["needs_refinement_nodes"] != int(np.count_nonzero(arrays["needs_refinement_mask"])) or
            summary["requires_shared_fine_extension"] != bool(np.any(expected_clipped))):
        raise ValueError("section summary disagrees with masks")
    weight = np.ones(shape)
    weight[[0, -1], :] *= .5
    weight[:, [0, -1]] *= .5
    volume = float(np.sum(arrays["actual_cut_m"] * weight) *
                   params["spacing_x_m"] * params["spacing_z_m"])
    if not math.isclose(volume, record["summary"]["actual_cut_volume_m3"], abs_tol=1e-7):
        raise ValueError("section volume summary mismatch")
    for value in arrays.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": record["status"], "arrays": arrays, "summary": record["summary"]}
