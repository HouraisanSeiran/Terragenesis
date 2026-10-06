"""Static outlet-constrained stage diagnostics on a shared channel graph."""

from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np

from terrain_pipeline.artifacts.contracts import ArtifactIdentity, array_hash, digest
from terrain_pipeline.metric_channel_plan import _validate_route


VERSION = "channel-stage-v1"


@dataclass(frozen=True)
class StageRecipe:
    min_clearance_m: float = .15
    max_depth_m: float = 3.
    max_lift_above_nominal_m: float = 1.
    min_stage_slope_m_per_m: float = 0.

    def __post_init__(self):
        for name in ("min_clearance_m", "max_depth_m", "max_lift_above_nominal_m",
                     "min_stage_slope_m_per_m"):
            value = getattr(self, name)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.min_clearance_m <= 0 or self.max_depth_m < self.min_clearance_m:
            raise ValueError("stage depth limits are inconsistent")


def solve_stage(plan, outlet_stage_m, recipe: StageRecipe, centerline=None):
    """A deterministic static feasibility surface, not a hydraulic solver."""
    if not isinstance(recipe, StageRecipe) or plan.get("status") != "diagnostic_not_publishable":
        raise ValueError("diagnostic plan and stage recipe required")
    identity = ArtifactIdentity(**plan["identity"])
    if identity.sha256 != plan["identity_sha256"] or identity.algorithm != "metric-channel-plan":
        raise ValueError("invalid plan identity")
    arrays = plan["arrays"]
    params = identity.record()["parameters"]
    shape = arrays["source_height_m"].shape
    for name, field in (("source_height_m", "source_height_sha256"),
                        ("discharge_m3_s", "source_discharge_sha256"),
                        ("receiver", "source_route_sha256"),
                        ("order", "source_order_sha256"),
                        ("outlet_mask", "source_outlet_sha256")):
        if array_hash(np.ascontiguousarray(arrays[name])) != params[field]:
            raise ValueError("plan input differs from identity")
    if (len(shape) != 2 or min(shape) < 1 or
            any(arrays[name].shape != shape for name in
                ("bounded_bed_m", "nominal_depth_m", "channel_mask", "over_budget_mask",
                 "failed_slope_edge_donor_mask")) or
            any(not np.isfinite(arrays[name]).all() for name in
                ("source_height_m", "bounded_bed_m", "nominal_depth_m")) or
            np.any(arrays["nominal_depth_m"] < 0) or
            any(arrays[name].dtype != bool for name in
                ("channel_mask", "outlet_mask", "over_budget_mask", "failed_slope_edge_donor_mask"))):
        raise ValueError("invalid plan geometry or masks")
    receiver, order = _validate_route(arrays["receiver"], arrays["order"], shape,
                                      arrays["outlet_mask"])
    active = arrays["channel_mask"].ravel()
    bounded = arrays["bounded_bed_m"].ravel()
    nominal_depth = arrays["nominal_depth_m"].ravel()
    outlets = np.flatnonzero(arrays["outlet_mask"].ravel() & active)
    supplied = np.asarray(outlet_stage_m, dtype=np.float64)
    if supplied.shape != (len(outlets),) or not np.isfinite(supplied).all():
        raise ValueError("one finite fixed stage per active explicit outlet required")
    if centerline is not None:
        from terrain_pipeline.channel_centerline import validate_centerline_for_plan
        validate_centerline_for_plan(centerline, plan)
        coords = np.full((bounded.size, 2), np.nan)
        coords[centerline["arrays"]["node_flat_index"]] = centerline["arrays"]["node_world_xz_m"]
    else:
        cols = shape[1]
        cells = np.arange(bounded.size)
        coords = np.column_stack((params["origin_x_m"] + cells % cols * params["spacing_x_m"],
                                  params["origin_z_m"] + cells // cols * params["spacing_z_m"]))
    stage = np.full(bounded.size, np.nan)
    stage[outlets] = supplied
    preferred = bounded + np.maximum(nominal_depth, recipe.min_clearance_m)
    for cell in order:
        if not active[cell] or receiver[cell] < 0:
            continue
        target = receiver[cell]
        if not active[target]:
            raise ValueError("active channel ends before outlet")
        distance = np.linalg.norm(coords[cell] - coords[target])
        stage[cell] = max(preferred[cell], stage[target] +
                          recipe.min_stage_slope_m_per_m * distance)
    invalid_depth = active & ((stage - bounded < recipe.min_clearance_m - 1e-9) |
                              (stage - bounded > recipe.max_depth_m + 1e-9))
    excessive_lift = active & (stage > preferred + recipe.max_lift_above_nominal_m + 1e-9)
    inherited = (arrays["over_budget_mask"].ravel() |
                 arrays["failed_slope_edge_donor_mask"].ravel()).copy()
    if centerline is not None:
        nodes = centerline["arrays"]["node_flat_index"]
        inherited[nodes] |= (centerline["arrays"]["slope_failed_donor_mask"] |
                             centerline["arrays"]["local_budget_failed_mask"])
    if not np.isfinite(stage[active]).all():
        raise ValueError("stage propagation did not reach explicit outlet")
    result = {"stage_m": stage.reshape(shape), "channel_mask": arrays["channel_mask"].copy(),
              "outlet_stage_m": supplied.copy(), "outlet_flat_index": outlets.astype(np.int64),
              "invalid_depth_mask": invalid_depth.reshape(shape),
              "excessive_lift_mask": excessive_lift.reshape(shape),
              "inherited_failure_mask": inherited.reshape(shape)}
    stage_identity = ArtifactIdentity("Terragenesis", "channel-stage", VERSION, 0,
                                      {**asdict(recipe), "plan_identity_sha256": plan["identity_sha256"],
                                       "bounded_bed_sha256": array_hash(arrays["bounded_bed_m"]),
                                       "nominal_depth_sha256": array_hash(arrays["nominal_depth_m"]),
                                       "channel_mask_sha256": array_hash(arrays["channel_mask"]),
                                       "outlet_stage_sha256": array_hash(supplied),
                                       "centerline_identity_sha256": centerline["identity_sha256"] if centerline else None,
                                       "stage_output_sha256": digest({name: array_hash(np.ascontiguousarray(value))
                                                                      for name, value in result.items()})})
    for value in result.values():
        value.flags.writeable = False
    return {"identity": stage_identity.record(), "identity_sha256": stage_identity.sha256,
            "status": "diagnostic_not_publishable", "arrays": result,
            "summary": {"active_nodes": int(np.count_nonzero(active)),
                        "invalid_depth_nodes": int(np.count_nonzero(invalid_depth)),
                        "excessive_lift_nodes": int(np.count_nonzero(excessive_lift)),
                        "inherited_failure_nodes": int(np.count_nonzero(inherited)),
                        "stage_feasible": not bool(np.any(invalid_depth | excessive_lift | inherited))}}


def save_stage(result, path):
    destination = Path(path)
    if destination.exists():
        raise FileExistsError(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)
    record = {key: result[key] for key in ("identity", "identity_sha256", "status", "summary")}
    record["format_version"] = 1
    record["array_sha256"] = {name: array_hash(np.ascontiguousarray(value))
                              for name, value in result["arrays"].items()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent,
                                         prefix=f".{destination.name}-", suffix=".npz", delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, manifest=json.dumps(record, sort_keys=True), **result["arrays"])
        load_stage(temporary)
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def load_stage(path):
    expected = {"stage_m", "channel_mask", "outlet_stage_m", "outlet_flat_index",
                "invalid_depth_mask", "excessive_lift_mask", "inherited_failure_mask"}
    with np.load(path, allow_pickle=False) as archive:
        record = json.loads(str(archive["manifest"].item()))
        if set(archive.files) != expected | {"manifest"} or set(record["array_sha256"]) != expected:
            raise ValueError("invalid stage array set")
        arrays = {name: archive[name].copy() for name in expected}
    identity = ArtifactIdentity(**record["identity"])
    if (record["format_version"] != 1 or record["status"] != "diagnostic_not_publishable" or
            identity.algorithm != "channel-stage" or identity.algorithm_version != VERSION or
            identity.sha256 != record["identity_sha256"] or
            any(array_hash(np.ascontiguousarray(arrays[name])) != expected_hash
                for name, expected_hash in record["array_sha256"].items())):
        raise ValueError("invalid stage identity or hashes")
    params = identity.record()["parameters"]
    StageRecipe(**{name: params[name] for name in StageRecipe.__dataclass_fields__})
    if digest({name: array_hash(np.ascontiguousarray(value)) for name, value in arrays.items()}) != params["stage_output_sha256"]:
        raise ValueError("stage output differs from identity")
    shape = arrays["stage_m"].shape
    if (len(shape) != 2 or min(shape) < 1 or
            any(arrays[name].shape != shape or arrays[name].dtype != bool for name in
                ("channel_mask", "invalid_depth_mask", "excessive_lift_mask", "inherited_failure_mask")) or
            arrays["stage_m"].dtype != np.float64 or
            not np.isfinite(arrays["stage_m"][arrays["channel_mask"]]).all() or
            arrays["outlet_stage_m"].dtype != np.float64 or not np.isfinite(arrays["outlet_stage_m"]).all() or
            arrays["outlet_flat_index"].dtype != np.int64 or
            arrays["outlet_stage_m"].shape != arrays["outlet_flat_index"].shape):
        raise ValueError("invalid stage shapes or values")
    summary = record["summary"]
    if (summary["active_nodes"] != int(np.count_nonzero(arrays["channel_mask"])) or
            summary["invalid_depth_nodes"] != int(np.count_nonzero(arrays["invalid_depth_mask"])) or
            summary["excessive_lift_nodes"] != int(np.count_nonzero(arrays["excessive_lift_mask"])) or
            summary["inherited_failure_nodes"] != int(np.count_nonzero(arrays["inherited_failure_mask"]))):
        raise ValueError("stage summary mismatch")
    if summary["stage_feasible"] != (not bool(np.any(
            arrays["invalid_depth_mask"] | arrays["excessive_lift_mask"] |
            arrays["inherited_failure_mask"]))):
        raise ValueError("stage feasibility summary mismatch")
    for value in arrays.values():
        value.flags.writeable = False
    return {"identity": identity.record(), "identity_sha256": identity.sha256,
            "status": record["status"], "arrays": arrays, "summary": summary}
