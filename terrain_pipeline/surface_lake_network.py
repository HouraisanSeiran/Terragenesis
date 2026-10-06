"""One-way finite lake-outflow to independently gated downstream scenarios.

No spill/drop connector geometry is generated. Static downstream feasibility
surfaces are recalculated per supplied step-end flow, not dynamic backwater.
Every bundle remains diagnostic_not_publishable, including feasible transfers.
"""

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from terrain_pipeline.channel_inundation import InundationRecipe
from terrain_pipeline.channel_reroute import RerouteRecipe
from terrain_pipeline.channel_stage import StageRecipe
from terrain_pipeline.lake_routing import LakeRoutingRecipe, evaluate_lake_routing
from terrain_pipeline.local_channel_sections import SectionRecipe
from terrain_pipeline.metric_channel_plan import ChannelRecipe, plan_channel
from terrain_pipeline.network_valley import NetworkValleyRecipe
from terrain_pipeline.surface_network_prepare import SurfaceNetworkBudget
from terrain_pipeline.surface_network_recovery import FineGrid, RecoveryRecipe, recover_surface_network
from terrain_pipeline.valley_geometry import ValleyGeometryRecipe


VERSION = "surface-lake-network-v1"
FORMAT_VERSION = 1
STATUS = "diagnostic_not_publishable"
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_MEMBERS = 4096
LIMITATION = (
    "Finite one-way step-end lake outflow drives separately recalculated static "
    "downstream engineering gates. No spill/drop connector water geometry, "
    "continuous lake-river geometry, dynamic backwater, observed hydraulics, "
    "steady state or complete network publication. Downstream is quasi-steady "
    "per step: river storage and propagation time are omitted from the combined ledger."
    " Bed/valley candidates restart from original H0 per scenario; this is not "
    "time-evolving erosion, and scenario cut volumes are not cumulative construction."
)


@dataclass(frozen=True)
class SurfaceLakeNetworkRecipe:
    max_steps: int = 16
    max_lake_cells: int = 1000000
    max_coarse_cells: int = 250000
    max_fine_cells: int = 1000000
    max_total_attempts: int = 64
    max_total_fine_work: int = 4000000
    max_total_lake_work: int = 4000000
    max_retained_bytes: int = 268435456
    discharge_abs_tolerance_m3_s: float = 1e-9
    discharge_rel_tolerance: float = 1e-10

    def __post_init__(self):
        ceilings = dict(max_steps=64, max_lake_cells=1000000, max_coarse_cells=250000,
                        max_fine_cells=1000000, max_total_attempts=128,
                        max_total_fine_work=8000000, max_total_lake_work=8000000,
                        max_retained_bytes=268435456)
        for name, ceiling in ceilings.items():
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= ceiling:
                raise ValueError(f"invalid bounded joint resource: {name}")
        for name in ("discharge_abs_tolerance_m3_s", "discharge_rel_tolerance"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("joint tolerances must be finite real numbers")
        if self.discharge_abs_tolerance_m3_s <= 0 or not 0 <= self.discharge_rel_tolerance < 1:
            raise ValueError("invalid joint discharge tolerance")


@dataclass(frozen=True)
class LakeRiverSeam:
    lake_path_grid_zx: tuple
    world_x_m: float
    world_z_m: float
    downstream_vertical_datum: str
    lake_source_identity: str
    downstream_source_identity: str

    def __post_init__(self):
        pair = self.lake_path_grid_zx
        if (not isinstance(pair, (tuple, list, np.ndarray)) or len(pair) != 2 or
                any(isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) for value in pair)):
            raise ValueError("seam lake node must be a strict integer (z, x) pair")
        object.__setattr__(self, "lake_path_grid_zx", tuple(int(value) for value in pair))
        for name in ("world_x_m", "world_z_m"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("seam world coordinates must be finite")
        for name in ("downstream_vertical_datum", "lake_source_identity", "downstream_source_identity"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError("explicit seam datum and source bindings required")


def _readonly(array):
    contiguous = np.ascontiguousarray(array)
    return np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)


def _freeze(value, memo=None):
    if memo is None:
        memo = {}
    if isinstance(value, np.ndarray):
        if id(value) not in memo:
            memo[id(value)] = _readonly(value)
        return memo[id(value)]
    if isinstance(value, dict):
        return {name: _freeze(child, memo) for name, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_freeze(child, memo) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def _retained_bytes(value):
    if isinstance(value, np.ndarray):
        return int(value.nbytes) + 256
    if isinstance(value, dict):
        return 256 + sum(128 + len(str(name)) * 4 + _retained_bytes(item) for name, item in value.items())
    if isinstance(value, (tuple, list)):
        return 128 + sum(32 + _retained_bytes(item) for item in value)
    if isinstance(value, str):
        return 64 + len(value) * 4
    return 64


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _array_hash(array):
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(_json(list(array.shape)).encode("ascii"))
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _tree(value, arrays):
    if isinstance(value, np.ndarray):
        identity = _array_hash(value)
        name = "array_" + identity
        arrays[name] = value
        return {"$array": name, "dtype": value.dtype.str, "shape": list(value.shape), "sha256": identity}
    if isinstance(value, dict):
        return {name: _tree(child, arrays) for name, child in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_tree(child, arrays) for child in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def surface_lake_network_hash(result):
    """Integrity only, never a substitute for algorithm replay."""
    payload = {name: value for name, value in result.items() if name != "identity_sha256"}
    return hashlib.sha256(_json(_tree(payload, {})).encode("utf-8")).hexdigest()


def _validated_plan(plan):
    try:
        parameters = plan["identity"]["parameters"]
        channel = ChannelRecipe(**{name: parameters[name] for name in ChannelRecipe.__dataclass_fields__})
        arrays = plan["arrays"]
        replay = plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
                              arrays["outlet_mask"], arrays["discharge_m3_s"],
                              parameters["spacing_x_m"], parameters["spacing_z_m"],
                              parameters["origin_x_m"], parameters["origin_z_m"],
                              parameters["sea_level_elevation_m"], parameters["source_identity"], channel)
        if _json(_tree(replay, {})) != _json(_tree(plan, {})):
            raise ValueError("downstream plan differs from semantic replay")
        discharge = replay["arrays"]["discharge_m3_s"].ravel()
        receiver = replay["arrays"]["receiver"]
        local = discharge.copy()
        donors = np.flatnonzero(receiver >= 0)
        np.subtract.at(local, receiver[donors], discharge[donors])
        if np.any(local < 0):
            raise ValueError("downstream plan Q is not conservative nonnegative local inflow")
        reconstructed = _accumulate(local, replay["arrays"])
        if not np.allclose(reconstructed, discharge, rtol=1e-12, atol=1e-12):
            raise ValueError("downstream plan discharge reconstruction failed")
        return replay, channel, local
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("invalid downstream original plan") from error


def _accumulate(local, arrays):
    discharge = local.copy()
    for donor in arrays["order"][::-1]:
        target = arrays["receiver"][donor]
        if target >= 0:
            discharge[target] += discharge[donor]
    if not np.isfinite(discharge).all():
        raise ValueError("downstream accumulated discharge overflow")
    return discharge


def _aligned_index(world, origin, spacing, size):
    fraction = (world - origin) / spacing
    index = round(fraction)
    if index < 0 or index >= size or origin + index * spacing != world:
        raise ValueError("seam world coordinate is not exactly aligned to a downstream node")
    return index


def _overlap(lake_inputs, wet, fine, fine_wet):
    """Conservative positive footprint intersection, never point-only overlap."""
    rows, columns = np.nonzero(fine_wet)
    world_x = fine.origin_x_m + columns * fine.spacing_x_m
    world_z = fine.origin_z_m + rows * fine.spacing_z_m
    ranges = []
    for world, origin, spacing, fine_spacing, size in (
            (world_z, lake_inputs["origin_z_m"], lake_inputs["spacing_z_m"], fine.spacing_z_m, wet.shape[0]),
            (world_x, lake_inputs["origin_x_m"], lake_inputs["spacing_x_m"], fine.spacing_x_m, wet.shape[1])):
        radius = .5 * (spacing + fine_spacing)
        lower = np.clip(np.floor((world - radius - origin) / spacing).astype(np.int64) + 1, 0, size)
        upper = np.clip(np.ceil((world + radius - origin) / spacing).astype(np.int64), 0, size)
        ranges.append((lower, upper))
    prefix = np.pad(wet.astype(np.int64).cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
    lower_z, upper_z = ranges[0]
    lower_x, upper_x = ranges[1]
    counts = prefix[upper_z, upper_x] - prefix[lower_z, upper_x] - prefix[upper_z, lower_x] + prefix[lower_z, lower_x]
    return int(np.count_nonzero(counts > 0))


def evaluate_surface_lake_network(lake_inputs, plan, coarse_domain, coarse_protected,
                                  fine, outlet_stage_m, section_recipe, stage_recipe,
                                  inundation_recipe, budget, network_recipe, valley_recipe,
                                  reroute_recipe, recovery_recipe, seam,
                                  recipe=SurfaceLakeNetworkRecipe()):
    """Recompute original D8 discharge and real recovery gates per lake time step.

    outlet_stage_m is a finite full coarse-grid boundary-stage array; only
    active original-topology outlets are passed to recovery on each step.
    seam binds a strict lake-path node, world coordinates, vertical datum and
    both source identities. Origin/spacing/elevation equality is exact.
    Lake source and downstream source may differ, but must match these bindings.
    Inputs and diagnostic prefixes never authorize standalone publication.
    """
    expected_types = ((fine, FineGrid), (section_recipe, SectionRecipe),
                      (stage_recipe, StageRecipe), (inundation_recipe, InundationRecipe),
                      (budget, SurfaceNetworkBudget), (network_recipe, NetworkValleyRecipe),
                      (valley_recipe, ValleyGeometryRecipe), (reroute_recipe, RerouteRecipe),
                      (recovery_recipe, RecoveryRecipe), (seam, LakeRiverSeam),
                      (recipe, SurfaceLakeNetworkRecipe))
    if any(not isinstance(value, expected) for value, expected in expected_types):
        raise ValueError("explicit joint seam, fine grid and all recovery recipes required")
    if not isinstance(lake_inputs, dict) or not isinstance(lake_inputs.get("recipe"), LakeRoutingRecipe):
        raise ValueError("lake_inputs must be the explicit original evaluate_lake_routing keyword inputs")
    lake_shape = np.asarray(lake_inputs["height_m"]).shape
    downstream_shape = np.asarray(plan["arrays"]["source_height_m"]).shape
    steps_requested = len(lake_inputs["recipe"].inflow_m3_s)
    if (len(lake_shape) != 2 or len(downstream_shape) != 2 or
            math.prod(lake_shape) > recipe.max_lake_cells or
            math.prod(downstream_shape) > min(recipe.max_coarse_cells, recovery_recipe.max_coarse_cells) or
            math.prod(fine.shape_zx) > min(recipe.max_fine_cells, recovery_recipe.max_fine_cells) or
            steps_requested > recipe.max_steps):
        raise ValueError("joint input exceeds hard requested grid/step resource bounds before copying")
    full_lake_work = math.prod(lake_shape) * steps_requested
    if full_lake_work > recipe.max_total_lake_work:
        raise ValueError("initial independent lake trajectory exceeds aggregate lake-work bound")
    initial_retained_estimate = (math.prod(lake_shape) * 128 + math.prod(downstream_shape) * 1024 +
                                 math.prod(fine.shape_zx) * 32 + 65536)
    if initial_retained_estimate > recipe.max_retained_bytes:
        raise ValueError("joint initial diagnostic exceeds retained-byte bound before copying")
    original, channel, local = _validated_plan(plan)
    parameters = original["identity"]["parameters"]
    arrays = original["arrays"]
    domain = np.asarray(coarse_domain)
    protected = np.asarray(coarse_protected)
    outlet_stage = np.asarray(outlet_stage_m)
    if (any(mask.shape != downstream_shape or mask.dtype != bool for mask in (domain, protected)) or
            outlet_stage.shape != downstream_shape or outlet_stage.dtype.kind not in "fiu" or
            not np.isfinite(outlet_stage).all()):
        raise ValueError("matching explicit coarse masks and finite full-grid outlet stages required")
    if (seam.lake_source_identity != lake_inputs["source_identity"] or
            seam.downstream_source_identity != parameters["source_identity"] or
            seam.downstream_vertical_datum != lake_inputs["vertical_datum"]):
        raise ValueError("seam source provenance or vertical datum binding mismatch")
    if (lake_inputs["spacing_x_m"] != parameters["spacing_x_m"] or
            lake_inputs["spacing_z_m"] != parameters["spacing_z_m"]):
        raise ValueError("lake and downstream coarse spacing must explicitly agree")
    source = seam.lake_path_grid_zx
    path = np.asarray(lake_inputs["downstream_path_grid_zx"])
    if (path.ndim != 2 or path.shape[1] != 2 or not any(tuple(node) == source for node in path) or
            source == tuple(lake_inputs["legal_spill_grid_zx"])):
        raise ValueError("injection must be an explicit downstream lake-path node outside the spill")
    if (source[0] < 0 or source[0] >= lake_shape[0] or source[1] < 0 or source[1] >= lake_shape[1] or
            np.asarray(lake_inputs["basin_mask"])[source] or
            not np.asarray(lake_inputs["domain_mask"])[source] or
            np.asarray(lake_inputs["protected_mask"])[source]):
        raise ValueError("injection lake-path node conflicts with basin/domain/protection")
    lake_world_x = lake_inputs["origin_x_m"] + source[1] * lake_inputs["spacing_x_m"]
    lake_world_z = lake_inputs["origin_z_m"] + source[0] * lake_inputs["spacing_z_m"]
    if seam.world_x_m != lake_world_x or seam.world_z_m != lake_world_z:
        raise ValueError("seam world coordinates do not exactly match the lake-path node")
    source_row = _aligned_index(seam.world_z_m, parameters["origin_z_m"], parameters["spacing_z_m"], downstream_shape[0])
    source_column = _aligned_index(seam.world_x_m, parameters["origin_x_m"], parameters["spacing_x_m"], downstream_shape[1])
    injection = source_row * downstream_shape[1] + source_column
    if arrays["source_height_m"][source_row, source_column] != np.asarray(lake_inputs["height_m"])[source]:
        raise ValueError("seam source terrain elevation mismatch")
    fine_row = _aligned_index(seam.world_z_m, fine.origin_z_m, fine.spacing_z_m, fine.shape_zx[0])
    fine_column = _aligned_index(seam.world_x_m, fine.origin_x_m, fine.spacing_x_m, fine.shape_zx[1])
    lake = evaluate_lake_routing(**lake_inputs)
    recorded_lake = {name: asdict(value) if isinstance(value, LakeRoutingRecipe) else value
                     for name, value in lake_inputs.items()}
    inputs = dict(lake_inputs=recorded_lake, plan=original, coarse_domain=domain,
                  coarse_protected=protected, fine={name: getattr(fine, name) for name in FineGrid.__dataclass_fields__},
                  outlet_stage_m=outlet_stage,
                  section_recipe=asdict(section_recipe), stage_recipe=asdict(stage_recipe),
                  inundation_recipe=asdict(inundation_recipe), budget=asdict(budget),
                  network_recipe=asdict(network_recipe), valley_recipe=asdict(valley_recipe),
                  reroute_recipe=asdict(reroute_recipe), recovery_recipe=asdict(recovery_recipe),
                  seam=asdict(seam), recipe=asdict(recipe))
    trace = []
    ledgers = []
    attempts_used = 0
    fine_work_used = 0
    lake_work_used = full_lake_work
    diagnostic = dict(code="transfer_feasible", failed_step=None, evidence={})

    def fail(code, index=None, evidence=None):
        diagnostic.update(code=code, failed_step=index, evidence=evidence or {})

    def flow_tolerance(*values):
        return recipe.discharge_abs_tolerance_m3_s + recipe.discharge_rel_tolerance * max(abs(value) for value in values)

    if not lake["scenario_feasible"]:
        fail("lake_scenario_failed", evidence=lake["diagnostic"])
    elif (not domain[source_row, source_column] or protected[source_row, source_column] or
          not fine.domain_mask[fine_row, fine_column] or fine.protected_mask[fine_row, fine_column]):
        fail("seam_domain_or_protection")
    base_local_total = float(math.fsum(local))
    dt = lake_inputs["recipe"].dt_s
    spill_stage = float(np.asarray(lake_inputs["height_m"])[tuple(lake_inputs["legal_spill_grid_zx"])])
    if diagnostic["code"] == "transfer_feasible":
        for index in range(steps_requested):
            retained = _retained_bytes((inputs, lake, trace, ledgers))
            next_retained_estimate = (math.prod(fine.shape_zx) * 512 + math.prod(downstream_shape) * 4096 +
                                      math.prod(lake_shape) * 128 + 65536)
            if retained + next_retained_estimate > recipe.max_retained_bytes:
                fail("joint_retained_memory_exhausted", index,
                     dict(retained_bytes=retained, next_estimated_bytes=next_retained_estimate,
                          max_retained_bytes=recipe.max_retained_bytes))
                break
            replay_work = math.prod(lake_shape) * (index + 1)
            if lake_work_used + replay_work > recipe.max_total_lake_work:
                fail("joint_lake_work_exhausted", index, dict(lake_work_used=lake_work_used, next_work=replay_work))
                break
            prefix_recipe = replace(lake_inputs["recipe"],
                                    inflow_m3_s=lake_inputs["recipe"].inflow_m3_s[:index + 1],
                                    loss_m3_s=lake_inputs["recipe"].loss_m3_s[:index + 1])
            step_lake = evaluate_lake_routing(**dict(lake_inputs, recipe=prefix_recipe))
            lake_work_used += replay_work
            if (not step_lake["scenario_feasible"] or
                    not np.array_equal(step_lake["arrays"]["stage_m"], lake["arrays"]["stage_m"][:index + 2]) or
                    not np.array_equal(step_lake["arrays"]["storage_m3"], lake["arrays"]["storage_m3"][:index + 2])):
                fail("lake_prefix_replay_mismatch", index)
                break
            outflow = float(step_lake["arrays"]["step_outflow_m3_s"][-1])
            injected_local = local.copy()
            injected_local[injection] += outflow
            recomputed_discharge = _accumulate(injected_local, arrays)
            source_chain = dict(lake_identity_sha256=lake["identity_sha256"],
                                original_plan_sha256=original["identity_sha256"],
                                lake_source=seam.lake_source_identity,
                                downstream_source=seam.downstream_source_identity, step=index)
            step_plan = plan_channel(arrays["source_height_m"], arrays["receiver"], arrays["order"],
                                     arrays["outlet_mask"], recomputed_discharge.reshape(downstream_shape),
                                     parameters["spacing_x_m"], parameters["spacing_z_m"],
                                     parameters["origin_x_m"], parameters["origin_z_m"],
                                     parameters["sea_level_elevation_m"], _json(source_chain), channel)
            step = dict(index=index, status="pending", lake_prefix_identity_sha256=step_lake["identity_sha256"],
                        lake_outflow_m3_s=outflow, original_local_inflow_m3_s=_readonly(local.reshape(downstream_shape)),
                        injected_local_inflow_m3_s=_readonly(injected_local.reshape(downstream_shape)),
                        recomputed_plan=step_plan, recovery=None, committed=False)
            trace.append(step)
            active = step_plan["arrays"]["channel_mask"]
            reachable = injection
            active_transfer = bool(active.flat[reachable])
            while active_transfer and arrays["receiver"][reachable] >= 0:
                reachable = int(arrays["receiver"][reachable])
                active_transfer = bool(active.flat[reachable])
            if outflow > 0 and (not active_transfer or arrays["receiver"][injection] < 0):
                step["status"] = "positive_outflow_without_active_path"
                fail(step["status"], index, dict(outflow_m3_s=outflow, original_start_threshold_m3_s=channel.start_discharge_m3_s))
                break
            if not active.any():
                if outflow != 0 or base_local_total != 0:
                    step["status"] = "positive_local_flow_without_activity"
                    fail(step["status"], index)
                    break
                step["status"] = "no_flow"
                river_outlet = 0.
            else:
                remaining_attempts = recipe.max_total_attempts - attempts_used
                remaining_fine = recipe.max_total_fine_work - fine_work_used
                if remaining_attempts < 1 or remaining_fine < math.prod(fine.shape_zx):
                    step["status"] = "joint_recovery_resource_exhausted"
                    fail(step["status"], index, dict(attempts_used=attempts_used, fine_work_used=fine_work_used))
                    break
                bounded_recovery = replace(recovery_recipe,
                    max_attempts=min(recovery_recipe.max_attempts, remaining_attempts),
                    max_total_fine_cells=min(recovery_recipe.max_total_fine_cells, remaining_fine))
                active_outlets = active & arrays["outlet_mask"]
                try:
                    recovered = recover_surface_network(step_plan, domain, protected, fine,
                        outlet_stage[active_outlets], section_recipe, stage_recipe, inundation_recipe,
                        budget, network_recipe, valley_recipe, reroute_recipe, bounded_recovery)
                except ValueError as error:
                    step["status"] = "downstream_input_gate_failed"
                    fail(step["status"], index, dict(reason=str(error)))
                    break
                attempts_used += len(recovered["attempts"])
                fine_work_used += recovered["summary"]["total_fine_cells_evaluated"]
                if _retained_bytes((inputs, lake, trace, ledgers, recovered)) > recipe.max_retained_bytes:
                    step["status"] = "joint_retained_memory_exhausted"
                    fail(step["status"], index, dict(max_retained_bytes=recipe.max_retained_bytes))
                    break
                step["recovery"] = recovered
                if not recovered["accepted"]:
                    step["status"] = "downstream_recovery_failed"
                    fail(step["status"], index, dict(recovery_status=recovered["status"], attempts=len(recovered["attempts"])))
                    break
                surface = recovered["surface"]["arrays"]
                if outflow > 0:
                    if (not recovered["final_plan"]["arrays"]["channel_mask"].flat[injection] or
                            not surface["wet_mask"][fine_row, fine_column]):
                        step["status"] = "injection_not_wet"
                        fail(step["status"], index)
                        break
                if surface["wet_mask"][fine_row, fine_column]:
                    injection_stage = float(surface["water_surface_m"][fine_row, fine_column])
                    step["injection_stage_m"] = injection_stage
                    if injection_stage >= spill_stage:
                        step["status"] = "spill_submerged_one_way_invalid"
                        fail(step["status"], index, dict(injection_stage_m=injection_stage, spill_stage_m=spill_stage))
                        break
                overlapping = _overlap(lake_inputs, step_lake["arrays"]["wet_mask"], fine, surface["wet_mask"])
                step["overlap_fine_cells"] = overlapping
                if overlapping:
                    step["status"] = "lake_river_wet_overlap"
                    fail(step["status"], index, dict(overlap_fine_cells=overlapping))
                    break
                final_arrays = recovered["final_plan"]["arrays"]
                river_outlet = float(math.fsum(final_arrays["discharge_m3_s"][final_arrays["outlet_mask"]]))
                step["status"] = "downstream_gates_passed"
            lake_change = float(lake["arrays"]["storage_m3"][index + 1] - lake["arrays"]["storage_m3"][index])
            lake_in = float(lake_inputs["recipe"].inflow_m3_s[index])
            loss = float(lake_inputs["recipe"].loss_m3_s[index])
            lake_residual = lake_change - dt * (lake_in - loss - outflow)
            river_residual = river_outlet - base_local_total - outflow
            combined = lake_change + dt * river_outlet - dt * (lake_in - loss + base_local_total)
            allowed_lake = (lake_inputs["recipe"].volume_abs_tolerance_m3 +
                lake_inputs["recipe"].volume_rel_tolerance * max(
                    lake["arrays"]["storage_m3"][index], lake["arrays"]["storage_m3"][index + 1],
                    dt * lake_in, dt * loss, dt * outflow))
            allowed_flow = flow_tolerance(river_outlet, base_local_total, outflow)
            if (abs(lake_residual) > allowed_lake + 1e-13 or abs(river_residual) > allowed_flow or
                    abs(combined) > allowed_lake + dt * allowed_flow + 1e-13):
                step["status"] = "combined_ledger_failed"
                fail(step["status"], index, dict(lake_residual_m3=lake_residual,
                                               downstream_residual_m3_s=river_residual,
                                               combined_residual_m3=combined))
                break
            ledgers.append(dict(step=index, dt_s=dt, lake_inflow_m3_s=lake_in, lake_loss_m3_s=loss,
                                lake_outflow_m3_s=outflow, downstream_local_total_m3_s=base_local_total,
                                downstream_outlet_m3_s=river_outlet, lake_storage_change_m3=lake_change,
                                lake_residual_m3=lake_residual, downstream_residual_m3_s=river_residual,
                                combined_residual_m3=combined,
                                combined_tolerance_m3=allowed_lake + dt * allowed_flow))
            step["committed"] = True
    committed = len(ledgers)
    committed_stage = float(lake["arrays"]["stage_m"][committed])
    basin = lake["arrays"]["basin_mask"]
    depth = np.where(basin, np.maximum(committed_stage - lake["arrays"]["height_m"], 0.), 0.)
    wet = depth > 0
    water = np.full(lake_shape, np.nan)
    water[wet] = committed_stage
    initial_storage = float(lake["arrays"]["storage_m3"][0])
    final_storage = float(lake["arrays"]["storage_m3"][committed])
    summary = dict(committed_steps=committed, requested_steps=steps_requested,
                   committed_final_lake_stage_m=committed_stage,
                   committed_initial_lake_storage_m3=initial_storage,
                   committed_final_lake_storage_m3=final_storage,
                   total_lake_inflow_m3=math.fsum(row["dt_s"] * row["lake_inflow_m3_s"] for row in ledgers),
                   total_lake_loss_m3=math.fsum(row["dt_s"] * row["lake_loss_m3_s"] for row in ledgers),
                   total_lake_outflow_m3=math.fsum(row["dt_s"] * row["lake_outflow_m3_s"] for row in ledgers),
                   total_downstream_local_m3=math.fsum(row["dt_s"] * row["downstream_local_total_m3_s"] for row in ledgers),
                   total_downstream_outlet_m3=math.fsum(row["dt_s"] * row["downstream_outlet_m3_s"] for row in ledgers),
                   total_combined_residual_m3=math.fsum(row["combined_residual_m3"] for row in ledgers),
                   total_combined_tolerance_m3=math.fsum(row["combined_tolerance_m3"] for row in ledgers),
                   total_attempts=attempts_used, total_fine_work=fine_work_used,
                   total_lake_work=lake_work_used, limitation=LIMITATION,
                   connector_geometry_generated=False, river_storage_or_propagation_modeled=False)
    aggregate = math.fsum((final_storage, -initial_storage, summary["total_downstream_outlet_m3"],
                          -summary["total_lake_inflow_m3"], summary["total_lake_loss_m3"],
                          -summary["total_downstream_local_m3"]))
    summary["aggregate_combined_residual_m3"] = aggregate
    if (diagnostic["code"] == "transfer_feasible" and
            abs(aggregate) > summary["total_combined_tolerance_m3"] + 1e-12):
        fail("aggregate_ledger_failed", evidence=dict(residual_m3=aggregate))
    result = dict(algorithm_version=VERSION, format_version=FORMAT_VERSION, status=STATUS,
                   transfer_feasible=diagnostic["code"] == "transfer_feasible", inputs=inputs,
                   independent_lake_diagnostic=lake, trace=trace, ledger=ledgers,
                   committed_lake_arrays=dict(stage_m=lake["arrays"]["stage_m"][:committed + 1],
                       storage_m3=lake["arrays"]["storage_m3"][:committed + 1],
                       wet_mask=wet, water_depth_m=depth, water_surface_m=water),
                   diagnostic=diagnostic, summary=summary)
    retained = _retained_bytes(result)
    if retained > recipe.max_retained_bytes:
        raise ValueError("joint final diagnostic exceeds retained-byte bound before freezing")
    summary["retained_bytes_before_freeze"] = retained
    result = _freeze(result)
    result["identity_sha256"] = surface_lake_network_hash(result)
    return result


def validate_surface_lake_network(result):
    """Replay both the lake and every downstream preparation, including failures."""
    try:
        if (result["algorithm_version"] != VERSION or result["format_version"] != FORMAT_VERSION or
                result["status"] != STATUS or type(result["transfer_feasible"]) is not bool or
                result["identity_sha256"] != surface_lake_network_hash(result)):
            raise ValueError("joint integrity or nonpublication status mismatch")
        inputs = dict(result["inputs"])
        lake_inputs = dict(inputs["lake_inputs"])
        lake_inputs["recipe"] = LakeRoutingRecipe(**lake_inputs["recipe"])
        inputs["lake_inputs"] = lake_inputs
        classes = dict(fine=FineGrid, section_recipe=SectionRecipe, stage_recipe=StageRecipe,
                       inundation_recipe=InundationRecipe, budget=SurfaceNetworkBudget,
                       network_recipe=NetworkValleyRecipe, valley_recipe=ValleyGeometryRecipe,
                       reroute_recipe=RerouteRecipe, recovery_recipe=RecoveryRecipe,
                       seam=LakeRiverSeam, recipe=SurfaceLakeNetworkRecipe)
        for name, constructor in classes.items():
            inputs[name] = constructor(**inputs[name])
        replay = evaluate_surface_lake_network(**inputs)
        if _json(_tree(result, {})) != _json(_tree(replay, {})):
            raise ValueError("joint semantic replay mismatch")
        return replay
    except (KeyError, TypeError, AttributeError, OverflowError, RecursionError) as error:
        raise ValueError("malformed joint diagnostic") from error


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate joint JSON key")
        result[name] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite joint JSON value: {value}")


def _preflight(handle):
    if os.fstat(handle.fileno()).st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("joint compressed archive exceeds byte ceiling")
    with zipfile.ZipFile(handle) as archive:
        members = archive.infolist()
        names = {entry.filename for entry in members}
        if (len(members) > MAX_MEMBERS or len(names) != len(members) or "manifest.npy" not in names or
                sum(entry.file_size for entry in members) > MAX_ARCHIVE_BYTES):
            raise ValueError("joint member count or expanded byte ceiling exceeded")
        for entry in members:
            if (not entry.filename.endswith(".npy") or "/" in entry.filename or
                    entry.flag_bits & 1):
                raise ValueError("invalid joint archive member")
            if entry.filename != "manifest.npy" and (
                    not entry.filename.startswith("array_") or len(entry.filename) != 74):
                raise ValueError("unexpected joint array member name")
            with archive.open(entry) as member:
                version = np.lib.format.read_magic(member)
                if version == (1, 0):
                    shape, fortran_order, dtype = np.lib.format.read_array_header_1_0(member)
                elif version == (2, 0):
                    shape, fortran_order, dtype = np.lib.format.read_array_header_2_0(member)
                else:
                    raise ValueError("unsupported joint NPY header")
                byte_count = math.prod(shape) * dtype.itemsize
                if (dtype.hasobject or fortran_order or len(shape) > 2 or
                        member.tell() + byte_count != entry.file_size or byte_count > MAX_ARCHIVE_BYTES):
                    raise ValueError("joint array header exceeds bounded payload")
                if entry.filename == "manifest.npy":
                    if shape != () or dtype.kind != "U" or entry.file_size > MAX_METADATA_BYTES:
                        raise ValueError("joint manifest exceeds scalar metadata bounds")
                elif dtype.kind not in "bifu" or math.prod(shape) > 2000000:
                    raise ValueError("joint array type or count exceeds hard bound")
    handle.seek(0)


def save_surface_lake_network(result, destination):
    """Atomically create a replay-validated self-contained diagnostic, never replace."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.suffix != ".npz":
        raise ValueError("joint diagnostic requires .npz destination")
    validated = validate_surface_lake_network(result)
    arrays = {}
    tree = _tree(validated, arrays)
    manifest = _json(dict(format_version=FORMAT_VERSION, tree=tree,
                          tree_sha256=hashlib.sha256(_json(tree).encode("utf-8")).hexdigest()))
    if len(manifest) * 4 + 256 > MAX_METADATA_BYTES or len(arrays) + 1 > MAX_MEMBERS:
        raise ValueError("joint diagnostic manifest exceeds archive resource ceiling")
    retained_ceiling = validated["inputs"]["recipe"]["max_retained_bytes"]
    archive_estimate = sum(array.nbytes + 256 for array in arrays.values()) + len(manifest) * 4 + 256
    if archive_estimate > min(MAX_ARCHIVE_BYTES, retained_ceiling):
        raise ValueError("joint deduplicated payload exceeds byte ceiling before compression")
    descriptor, temporary = tempfile.mkstemp(prefix=".surface-lake-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez_compressed(handle, manifest=np.asarray(manifest), **arrays)
            handle.flush()
            os.fsync(handle.fileno())
        with open(temporary, "rb") as handle:
            _preflight(handle)
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    return destination


def load_surface_lake_network(source):
    """Bound ZIP and NPY before allocation, enforce exact arrays, then semantic replay."""
    try:
        with open(source, "rb") as handle:
            _preflight(handle)
            with np.load(handle, allow_pickle=False) as archive:
                manifest = json.loads(str(archive["manifest"].item()), object_pairs_hook=_unique_object,
                                      parse_constant=_reject_constant)
                if (set(manifest) != {"format_version", "tree", "tree_sha256"} or
                        manifest["format_version"] != FORMAT_VERSION or
                        hashlib.sha256(_json(manifest["tree"]).encode("utf-8")).hexdigest() != manifest["tree_sha256"]):
                    raise ValueError("joint manifest integrity mismatch")
                used = {"manifest"}
                cache = {}

                def decode(value):
                    if isinstance(value, dict) and "$array" in value:
                        if set(value) != {"$array", "dtype", "shape", "sha256"}:
                            raise ValueError("malformed joint array reference")
                        name = value["$array"]
                        if name not in archive.files or name != "array_" + value["sha256"]:
                            raise ValueError("missing joint array binding")
                        used.add(name)
                        if name not in cache:
                            cache[name] = _readonly(archive[name])
                        array = cache[name]
                        if (array.dtype.str != value["dtype"] or list(array.shape) != value["shape"] or
                                _array_hash(array) != value["sha256"]):
                            raise ValueError("joint array integrity mismatch")
                        return array
                    if isinstance(value, dict):
                        return {name: decode(child) for name, child in value.items()}
                    if isinstance(value, list):
                        return [decode(child) for child in value]
                    return value

                result = decode(manifest["tree"])
                if used != set(archive.files):
                    raise ValueError("unexpected joint archive arrays")
            return validate_surface_lake_network(result)
    except (OSError, EOFError, KeyError, TypeError, AttributeError, RecursionError,
            zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid joint diagnostic archive") from error
