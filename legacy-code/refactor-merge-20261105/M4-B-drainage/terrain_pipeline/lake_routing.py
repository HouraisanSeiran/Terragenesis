"""Finite single-pool implicit Euler engineering scenarios, never publishable.

Metre stages use the supplied vertical datum; indices are (z, x). V(h) sums
positive depth times entire horizontal cell area, not node half-cell weights.
This is a cell-level estimate, not measured/subcell geometry. Piecewise-linear
supplied Q(h) is zero below spill. A path proves destination only, not river
water geometry. This independent approximation does not reproduce a paper.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np


VERSION = "lake-routing-implicit-euler-v1"
FORMAT_VERSION = 1
STATUS = "diagnostic_not_publishable"
LIMITATION = (
    "Finite supplied-flux single-pool implicit Euler engineering approximation; "
    "piecewise-linear supplied Q(h), step-end outflow, not observed hydraulics, "
    "steady state, paper reproduction or a prepared river network. Full "
    "horizontal cell estimate, not measured/subcell geometry. Downstream "
    "path is destination evidence only."
)
NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1))
MAX_STEPS = 4096
MAX_GRID_CELLS = 1000000
MAX_SOLVER_ITERATIONS = 128
MAX_RATING_POINTS = 4096
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_METADATA_BYTES = 1024 * 1024
ARRAY_NAMES = frozenset((
    "height_m", "basin_mask", "domain_mask", "protected_mask", "legal_outlet_mask",
    "legal_spill_grid_zx", "downstream_path_grid_zx", "stage_m", "storage_m3",
    "step_inflow_volume_m3", "step_loss_volume_m3", "step_outflow_volume_m3",
    "step_outflow_m3_s", "step_residual_m3", "step_solver_iterations", "wet_mask",
    "water_surface_m", "water_depth_m",
))


def _number(value, name):
    if (isinstance(value, (bool, np.bool_)) or
            not isinstance(value, (int, float, np.integer, np.floating)) or
            not math.isfinite(value)):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def _positive_integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return int(value)


@dataclass(frozen=True)
class LakeRoutingRecipe:
    initial_stage_m: float
    dt_s: float
    inflow_m3_s: tuple
    loss_m3_s: tuple
    rating_stage_m: tuple
    rating_outflow_m3_s: tuple
    max_stage_m: float
    max_steps: int = 4096
    max_grid_cells: int = 1000000
    max_solver_iterations: int = 128
    volume_abs_tolerance_m3: float = 1e-9
    volume_rel_tolerance: float = 1e-10

    def __post_init__(self):
        for name in ("initial_stage_m", "dt_s", "max_stage_m",
                     "volume_abs_tolerance_m3", "volume_rel_tolerance"):
            object.__setattr__(self, name, _number(getattr(self, name), name))
        for name in ("max_steps", "max_grid_cells", "max_solver_iterations"):
            object.__setattr__(self, name, _positive_integer(getattr(self, name), name))
        if (self.max_steps > MAX_STEPS or self.max_grid_cells > MAX_GRID_CELLS or
                self.max_solver_iterations > MAX_SOLVER_ITERATIONS):
            raise ValueError("recipe exceeds hard step/grid/solver resource ceiling")
        for name in ("inflow_m3_s", "loss_m3_s", "rating_stage_m", "rating_outflow_m3_s"):
            try:
                sequence = getattr(self, name)
                limit = MAX_RATING_POINTS if name.startswith("rating_") else MAX_STEPS
                if len(sequence) > limit:
                    raise ValueError(f"{name} exceeds hard sequence resource ceiling")
                values = tuple(_number(value, name) for value in sequence)
            except TypeError as error:
                raise ValueError(f"{name} must be a numeric sequence") from error
            object.__setattr__(self, name, values)
        if (self.dt_s <= 0 or self.initial_stage_m > self.max_stage_m or
                self.volume_abs_tolerance_m3 <= 0 or not 0 <= self.volume_rel_tolerance < 1):
            raise ValueError("invalid time, stage or volume tolerance bounds")
        if (not self.inflow_m3_s or len(self.inflow_m3_s) != len(self.loss_m3_s) or
                any(value < 0 for value in self.inflow_m3_s + self.loss_m3_s)):
            raise ValueError("flux sequences must have equal nonzero length and nonnegative values")
        if (len(self.rating_stage_m) < 2 or
                len(self.rating_stage_m) != len(self.rating_outflow_m3_s) or
                any(upper <= lower for lower, upper in zip(self.rating_stage_m, self.rating_stage_m[1:])) or
                self.rating_outflow_m3_s[0] != 0 or
                any(value <= 0 for value in self.rating_outflow_m3_s[1:]) or
                any(upper < lower for lower, upper in zip(self.rating_outflow_m3_s, self.rating_outflow_m3_s[1:]))):
            raise ValueError("rating requires increasing stages, Q(spill)=0 and positive nondecreasing Q above spill")


def _readonly(array):
    contiguous = np.ascontiguousarray(array)
    return np.frombuffer(contiguous.tobytes(), dtype=contiguous.dtype).reshape(contiguous.shape)


def _indices(value, shape, name, path=False):
    if path:
        try:
            if len(value) > MAX_GRID_CELLS:
                raise ValueError("downstream path exceeds hard resource ceiling")
        except TypeError as error:
            raise ValueError("downstream path must be a bounded sequence") from error
    indices = np.asarray(value)
    expected = indices.ndim == 2 and indices.shape[1] == 2 if path else indices.shape == (2,)
    if not expected or indices.dtype.kind not in "iu":
        raise ValueError(f"{name} requires integer (z, x) indices, without coercion")
    if any(isinstance(item, (bool, np.bool_)) for item in np.asarray(value, dtype=object).flat):
        raise ValueError(f"{name} rejects boolean indices")
    pairs = indices if path else indices.reshape(1, 2)
    if (len(pairs) == 0 or np.any(pairs < 0) or
            np.any(pairs[:, 0] >= shape[0]) or np.any(pairs[:, 1] >= shape[1])):
        raise ValueError(f"{name} indices are outside the grid")
    return np.array(indices, dtype=np.int64, copy=True)


def _connected(mask):
    count = int(np.count_nonzero(mask))
    if count == 0:
        return True
    start = tuple(np.argwhere(mask)[0])
    visited = {start}
    pending = [start]
    while pending:
        row, column = pending.pop()
        for delta_row, delta_column in NEIGHBORS:
            neighbor = (row + delta_row, column + delta_column)
            if (0 <= neighbor[0] < mask.shape[0] and 0 <= neighbor[1] < mask.shape[1] and
                    mask[neighbor] and neighbor not in visited):
                visited.add(neighbor)
                pending.append(neighbor)
    return len(visited) == count


def _array_hash(array):
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape)).encode("ascii"))
    digest.update(np.ascontiguousarray(array).tobytes())
    return digest.hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _metadata(result):
    return {name: value for name, value in result.items() if name not in ("arrays", "identity_sha256")}


def lake_routing_hash(result):
    """Integrity hash only; semantic acceptance additionally requires replay."""
    record = {"metadata": _metadata(result),
              "arrays": {name: _array_hash(array) for name, array in sorted(result["arrays"].items())}}
    return hashlib.sha256(_json(record).encode("utf-8")).hexdigest()


def evaluate_lake_routing(height_m, basin_mask, legal_spill_grid_zx,
                          spacing_x_m, spacing_z_m, source_identity,
                          recipe: LakeRoutingRecipe, downstream_path_grid_zx,
                          domain_mask, protected_mask, legal_outlet_mask,
                          origin_x_m, origin_z_m, vertical_datum):
    """Solve V(next)+dt*Q(next)=V(previous)+dt*(inflow-loss), in SI units.

    Invalid parameters raise ValueError. Infeasibility returns entire input,
    committed trajectory prefix and failed-step evidence. Stage/storage arrays
    include initial state; step arrays do not. Dry water surface is NaN and
    dry depth zero. Even feasible results remain diagnostic_not_publishable.
    """
    if not isinstance(recipe, LakeRoutingRecipe):
        raise ValueError("recipe must be LakeRoutingRecipe")
    raw_height = np.asarray(height_m)
    if raw_height.ndim != 2 or raw_height.size == 0 or raw_height.dtype.kind not in "fiu":
        raise ValueError("terrain must be a nonempty real two-dimensional grid")
    if (raw_height.size > recipe.max_grid_cells or raw_height.size > MAX_GRID_CELLS or
            len(recipe.inflow_m3_s) > recipe.max_steps):
        raise ValueError("input grid or time-step count exceeds resource bounds before copying")
    raw_basin = np.asarray(basin_mask)
    if raw_basin.shape != raw_height.shape or raw_basin.dtype != bool or not raw_basin.any():
        raise ValueError("basin must be a nonempty boolean grid matching terrain")
    if recipe.max_stage_m < float(np.min(raw_height[raw_basin])):
        raise ValueError("max stage must not lie below the minimum basin bed")
    terrain = np.array(raw_height, dtype=np.float64, copy=True)
    if not np.isfinite(terrain).all():
        raise ValueError("terrain must be finite")
    masks = {}
    for name, value in (("basin_mask", basin_mask), ("domain_mask", domain_mask),
                        ("protected_mask", protected_mask), ("legal_outlet_mask", legal_outlet_mask)):
        mask = np.asarray(value)
        if mask.dtype != bool or mask.shape != terrain.shape:
            raise ValueError(f"{name} must be a boolean grid matching terrain")
        masks[name] = np.array(mask, copy=True)
    basin = masks["basin_mask"]
    domain = masks["domain_mask"]
    protected = masks["protected_mask"]
    legal = masks["legal_outlet_mask"]
    if not basin.any():
        raise ValueError("basin must be nonempty")
    spill_array = _indices(legal_spill_grid_zx, terrain.shape, "spill")
    spill = tuple(spill_array)
    downstream = _indices(downstream_path_grid_zx, terrain.shape, "downstream path", path=True)
    spacing_x_m = _number(spacing_x_m, "spacing_x_m")
    spacing_z_m = _number(spacing_z_m, "spacing_z_m")
    origin_x_m = _number(origin_x_m, "origin_x_m")
    origin_z_m = _number(origin_z_m, "origin_z_m")
    area = spacing_x_m * spacing_z_m
    if spacing_x_m <= 0 or spacing_z_m <= 0 or not math.isfinite(area) or area == 0:
        raise ValueError("spacing must give finite positive cell area")
    if (not isinstance(source_identity, str) or not source_identity.strip() or
            not isinstance(vertical_datum, str) or not vertical_datum.strip()):
        raise ValueError("explicit source identity and vertical datum are required")
    spill_stage = float(terrain[spill])
    if recipe.rating_stage_m[0] != spill_stage:
        raise ValueError("rating first stage must equal explicit spill terrain elevation")
    input_arrays = {"height_m": terrain, **masks,
                    "legal_spill_grid_zx": spill_array, "downstream_path_grid_zx": downstream}
    parameters = {"spacing_x_m": spacing_x_m, "spacing_z_m": spacing_z_m,
                  "origin_x_m": origin_x_m, "origin_z_m": origin_z_m,
                  "vertical_datum": vertical_datum, "source_identity": source_identity,
                  "recipe": asdict(recipe)}
    floors = terrain[basin]
    minimum_stage = float(np.min(floors))

    def volume(stage):
        with np.errstate(over="ignore", invalid="ignore"):
            return float(np.sum(np.maximum(stage - floors, 0.)) * area)

    def discharge(stage):
        if stage <= spill_stage:
            return 0.
        if stage > recipe.rating_stage_m[-1]:
            raise ValueError("rating extrapolation forbidden")
        return float(np.interp(stage, recipe.rating_stage_m, recipe.rating_outflow_m3_s))

    def tolerance(*terms):
        return recipe.volume_abs_tolerance_m3 + recipe.volume_rel_tolerance * max(abs(term) for term in terms)

    initial_volume = volume(recipe.initial_stage_m)
    stages = [recipe.initial_stage_m]
    storage = [initial_volume]
    steps = []
    diagnostic = {"code": "scenario_feasible", "message": "finite engineering scenario completed",
                  "failed_step": None, "evidence": {}}

    def fail(code, message, evidence=None, step=None):
        diagnostic.update(code=code, message=message, failed_step=step, evidence=evidence or {})

    if not math.isfinite(initial_volume):
        fail("arithmetic_overflow", "initial volume is outside finite arithmetic")
    elif not _connected(basin):
        fail("basin_disconnected", "explicit basin is not four-neighbor connected")
    elif np.any(basin & ~domain) or np.any(basin & protected):
        fail("basin_domain_or_protection", "basin crosses domain or protected cells", {
            "outside_domain_cells": int(np.count_nonzero(basin & ~domain)),
            "protected_cells": int(np.count_nonzero(basin & protected))})
    elif basin[0].any() or basin[-1].any() or basin[:, 0].any() or basin[:, -1].any():
        fail("unmodeled_grid_boundary", "basin has no modeled enclosing shore at grid edge")
    elif basin[spill] or not any(
            0 <= spill[0] + delta_row < terrain.shape[0] and
            0 <= spill[1] + delta_column < terrain.shape[1] and
            basin[spill[0] + delta_row, spill[1] + delta_column]
            for delta_row, delta_column in NEIGHBORS):
        fail("invalid_spill", "spill must be a non-basin cell touching the basin")
    elif len(downstream) < 2 or tuple(downstream[0]) != spill or not legal[tuple(downstream[-1])]:
        fail("missing_legal_outlet", "spill path must start at spill and end at an explicit legal outlet")
    elif (len({tuple(point) for point in downstream}) != len(downstream) or
            np.any(np.sum(np.abs(np.diff(downstream, axis=0)), axis=1) != 1)):
        fail("invalid_downstream_adjacency", "spill path must be simple and four-neighbor connected")
    else:
        path_rows, path_columns = downstream.T
        if (np.any(~domain[path_rows, path_columns]) or
                np.any(protected[path_rows, path_columns]) or np.any(basin[path_rows, path_columns])):
            fail("path_domain_or_protection", "downstream path crosses basin, protection or domain")
        elif np.any(np.diff(terrain[path_rows, path_columns]) > 0):
            fail("uphill_downstream_path", "downstream evidence must be nonascending")
        elif terrain[tuple(downstream[-1])] >= spill_stage:
            fail("outlet_not_below_spill", "legal outflow destination must be strictly below spill")
        else:
            shore = np.zeros(terrain.shape, dtype=bool)
            for row, column in np.argwhere(basin):
                for delta_row, delta_column in NEIGHBORS:
                    neighbor = (row + delta_row, column + delta_column)
                    if not basin[neighbor]:
                        shore[neighbor] = True
            shore[spill] = False
            low_shore = shore & (terrain < recipe.max_stage_m)
            if low_shore.any():
                fail("unmodeled_low_saddle", "max stage exceeds another modeled shore elevation", {
                    "lowest_unmodeled_shore_m": float(np.min(terrain[shore])),
                    "max_stage_m": recipe.max_stage_m,
                    "conflicting_grid_zx": np.argwhere(low_shore).tolist()})
    if diagnostic["code"] == "scenario_feasible":
        if recipe.initial_stage_m > recipe.rating_stage_m[-1]:
            fail("rating_range_exceeded", "initial stage is outside supplied rating range")
        elif not _connected(basin & (terrain < recipe.initial_stage_m)):
            fail("wet_pool_disconnected", "initial wet cells violate the single connected pool assumption")
    upper_stage = min(recipe.max_stage_m, recipe.rating_stage_m[-1])
    if diagnostic["code"] == "scenario_feasible":
        for step_index, (inflow, loss) in enumerate(zip(recipe.inflow_m3_s, recipe.loss_m3_s)):
            inflow_volume = recipe.dt_s * inflow
            loss_volume = recipe.dt_s * loss
            target = storage[-1] + recipe.dt_s * (inflow - loss)
            upper_storage = volume(upper_stage)
            upper_outflow = recipe.dt_s * discharge(upper_stage)
            upper_capacity = upper_storage + upper_outflow
            evidence = {"previous_storage_m3": storage[-1], "inflow_m3_s": inflow,
                        "loss_m3_s": loss, "dt_s": recipe.dt_s}
            if not all(math.isfinite(value) for value in (
                    target, inflow_volume, loss_volume, upper_storage, upper_outflow, upper_capacity)):
                fail("arithmetic_overflow", "step flux or capacity is outside finite arithmetic", evidence, step_index)
                break
            evidence.update(target_volume_m3=target, upper_stage_m=upper_stage,
                            upper_storage_plus_outflow_m3=upper_capacity)
            if target < 0:
                fail("dry_loss_exceeds_available_water", "prescribed losses cannot be supplied", evidence, step_index)
                break
            if target > upper_capacity:
                code = "rating_range_exceeded" if recipe.rating_stage_m[-1] < recipe.max_stage_m else "spill_capacity_exceeded"
                fail(code, "no implicit root inside the bounded modeled stage range", evidence, step_index)
                break
            lower = min(minimum_stage, upper_stage)
            upper = upper_stage
            solved = False
            if target == 0:
                next_stage = min(minimum_stage, stages[-1], upper_stage)
                next_storage = 0.
                next_outflow_volume = 0.
                residual = 0.
                iterations = 0
                solved = True
            else:
                for iterations in range(1, recipe.max_solver_iterations + 1):
                    next_stage = lower + (upper - lower) * .5
                    next_storage = volume(next_stage)
                    next_outflow_volume = recipe.dt_s * discharge(next_stage)
                    residual = next_storage + next_outflow_volume - target
                    allowed = tolerance(storage[-1], next_storage, inflow_volume, loss_volume, next_outflow_volume)
                    if abs(residual) <= allowed:
                        solved = True
                        break
                    if residual > 0:
                        upper = next_stage
                    else:
                        lower = next_stage
            if not solved:
                evidence.update(last_residual_m3=residual, iterations=iterations,
                                lower_stage_m=lower, upper_stage_m=upper)
                fail("solver_resource_limit", "bounded bisection did not meet volume tolerance", evidence, step_index)
                break
            if not _connected(basin & (terrain < next_stage)):
                evidence.update(candidate_stage_m=next_stage)
                fail("wet_pool_disconnected", "candidate wet cells violate the connected single pool", evidence, step_index)
                break
            stages.append(float(next_stage))
            storage.append(float(next_storage))
            steps.append((inflow_volume, loss_volume, next_outflow_volume,
                          next_outflow_volume / recipe.dt_s, residual, iterations))
    final_stage = stages[-1]
    with np.errstate(over="ignore", invalid="ignore"):
        depth = np.where(basin, np.maximum(final_stage - terrain, 0.), 0.)
    wet = depth > 0
    water = np.full(terrain.shape, np.nan)
    water[wet] = final_stage
    step_data = np.asarray(steps, dtype=np.float64).reshape(-1, 6)
    arrays = {**input_arrays, "stage_m": np.asarray(stages), "storage_m3": np.asarray(storage),
              "step_inflow_volume_m3": step_data[:, 0], "step_loss_volume_m3": step_data[:, 1],
              "step_outflow_volume_m3": step_data[:, 2], "step_outflow_m3_s": step_data[:, 3],
              "step_residual_m3": step_data[:, 4], "step_solver_iterations": step_data[:, 5].astype(np.int64),
              "wet_mask": wet, "water_surface_m": water, "water_depth_m": depth}
    final_volume = volume(final_stage)
    total_residual = float(math.fsum(step_data[:, 4]))
    feasible = diagnostic["code"] == "scenario_feasible"
    summary = {"completed_steps": len(steps), "requested_steps": len(recipe.inflow_m3_s),
               "final_stage_m": final_stage, "initial_storage_m3": initial_volume if math.isfinite(initial_volume) else None,
               "final_storage_m3": final_volume if math.isfinite(final_volume) else None,
               "cell_area_m2": area, "wet_cells": int(np.count_nonzero(wet)),
               "total_inflow_volume_m3": float(math.fsum(step_data[:, 0])),
               "total_loss_volume_m3": float(math.fsum(step_data[:, 1])),
               "total_outflow_volume_m3": float(math.fsum(step_data[:, 2])),
               "total_residual_m3": total_residual, "limitation": LIMITATION}
    if feasible:
        geometry_volume = float(np.sum(depth) * area)
        aggregate_error = math.fsum((final_volume, -initial_volume,
                                    -summary["total_inflow_volume_m3"], summary["total_loss_volume_m3"],
                                    summary["total_outflow_volume_m3"]))
        allowed_total = math.fsum(tolerance(storage[index], storage[index + 1], *row[:3])
                                  for index, row in enumerate(step_data))
        summary.update(geometry_volume_m3=geometry_volume, aggregate_balance_residual_m3=aggregate_error,
                       cumulative_volume_tolerance_m3=allowed_total)
        if (abs(geometry_volume - final_volume) > tolerance(final_volume, geometry_volume) or
                abs(aggregate_error) > allowed_total):
            fail("geometry_or_total_balance", "final geometry or aggregate ledger failed volume tolerance")
            feasible = False
    result = {"algorithm_version": VERSION, "format_version": FORMAT_VERSION, "status": STATUS,
              "scenario_feasible": feasible, "input": parameters, "diagnostic": diagnostic,
              "summary": summary, "arrays": {name: _readonly(array) for name, array in arrays.items()}}
    result["identity_sha256"] = lake_routing_hash(result)
    return result


def _replay(result):
    try:
        if (result["algorithm_version"] != VERSION or result["format_version"] != FORMAT_VERSION or
                result["status"] != STATUS or type(result["scenario_feasible"]) is not bool or
                result["identity_sha256"] != lake_routing_hash(result)):
            raise ValueError("lake routing integrity or status mismatch")
        parameters = dict(result["input"])
        recipe = LakeRoutingRecipe(**parameters.pop("recipe"))
        arrays = result["arrays"]
        if set(arrays) != ARRAY_NAMES:
            raise ValueError("lake routing bundle has an unexpected array set")
        replayed = evaluate_lake_routing(
            arrays["height_m"], arrays["basin_mask"], arrays["legal_spill_grid_zx"],
            recipe=recipe, downstream_path_grid_zx=arrays["downstream_path_grid_zx"],
            domain_mask=arrays["domain_mask"], protected_mask=arrays["protected_mask"],
            legal_outlet_mask=arrays["legal_outlet_mask"], **parameters)
        if _json(_metadata(result)) != _json(_metadata(replayed)) or arrays.keys() != replayed["arrays"].keys():
            raise ValueError("lake routing replay metadata mismatch")
        for name, expected in replayed["arrays"].items():
            actual = arrays[name]
            if (actual.dtype != expected.dtype or actual.shape != expected.shape or
                    not np.array_equal(actual, expected, equal_nan=True)):
                raise ValueError(f"lake routing replay array mismatch: {name}")
        return replayed
    except (KeyError, TypeError, OverflowError, AttributeError) as error:
        raise ValueError("malformed lake routing bundle") from error


def save_lake_routing(result, destination):
    """Atomically link a complete replay-validated diagnostic, never overwrite."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.suffix != ".npz":
        raise ValueError("lake routing diagnostic destination must have .npz suffix")
    validated = _replay(result)
    metadata = _metadata(validated)
    metadata["identity_sha256"] = validated["identity_sha256"]
    metadata_text = _json(metadata)
    if len(metadata_text) * 4 + 256 > MAX_METADATA_BYTES:
        raise ValueError("diagnostic metadata exceeds archive byte ceiling")
    descriptor, temporary = tempfile.mkstemp(prefix=".lake-routing-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            np.savez_compressed(handle, metadata=np.asarray(metadata_text), **validated["arrays"])
            handle.flush()
            os.fsync(handle.fileno())
        with open(temporary, "rb") as handle:
            _check_archive(handle)
        os.link(temporary, destination)
    finally:
        os.unlink(temporary)
    return destination


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError(f"duplicate JSON key: {name}")
        result[name] = value
    return result


def _reject_constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _check_archive(handle):
    if os.fstat(handle.fileno()).st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("lake routing archive exceeds compressed byte ceiling")
    with zipfile.ZipFile(handle) as archive:
        entries = archive.infolist()
        expected = {name + ".npy" for name in ARRAY_NAMES} | {"metadata.npy"}
        if len(entries) != len(expected) or {entry.filename for entry in entries} != expected:
            raise ValueError("archive requires exactly the expected unique array members")
        if sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES:
            raise ValueError("lake routing archive exceeds decompressed byte ceiling")
        if any(entry.flag_bits & 1 for entry in entries):
            raise ValueError("encrypted lake routing members are unsupported")
        if archive.getinfo("metadata.npy").file_size > MAX_METADATA_BYTES:
            raise ValueError("lake routing metadata exceeds byte ceiling")
        for entry in entries:
            with archive.open(entry) as member:
                version = np.lib.format.read_magic(member)
                if version == (1, 0):
                    shape, fortran_order, dtype = np.lib.format.read_array_header_1_0(member)
                elif version == (2, 0):
                    shape, fortran_order, dtype = np.lib.format.read_array_header_2_0(member)
                else:
                    raise ValueError("unsupported lake routing array header version")
                if dtype.hasobject or fortran_order or len(shape) > 2:
                    raise ValueError("unsupported lake routing array dtype or layout")
                count = math.prod(shape)
                limit = MAX_METADATA_BYTES if entry.filename == "metadata.npy" else MAX_ARCHIVE_BYTES
                if count * dtype.itemsize > limit or member.tell() + count * dtype.itemsize != entry.file_size:
                    raise ValueError("array header exceeds bounded member size")
                if entry.filename == "metadata.npy":
                    if shape != () or dtype.kind != "U":
                        raise ValueError("invalid metadata scalar header")
                elif entry.filename in {name + ".npy" for name in (
                        "height_m", "basin_mask", "domain_mask", "protected_mask", "legal_outlet_mask",
                        "wet_mask", "water_surface_m", "water_depth_m")}:
                    if len(shape) != 2 or count > MAX_GRID_CELLS:
                        raise ValueError("archive grid exceeds hard cell ceiling")
                elif entry.filename == "downstream_path_grid_zx.npy":
                    if len(shape) != 2 or shape[1] != 2 or shape[0] > MAX_GRID_CELLS:
                        raise ValueError("archive path exceeds hard index ceiling")
                elif count > MAX_STEPS + 1:
                    raise ValueError("archive trajectory exceeds hard step ceiling")
    handle.seek(0)


def load_lake_routing(source):
    """Load immutable arrays only after hashes and full semantic replay."""
    try:
        with open(source, "rb") as handle:
            _check_archive(handle)
            return _load_checked(handle)
    except (OSError, EOFError, KeyError, TypeError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise ValueError("invalid lake routing diagnostic archive") from error


def _load_checked(handle):
    with np.load(handle, allow_pickle=False) as archive:
        metadata = archive["metadata"]
        result = json.loads(str(metadata.item()), object_pairs_hook=_unique_object,
                            parse_constant=_reject_constant)
        result["arrays"] = {name: archive[name].copy() for name in archive.files if name != "metadata"}
    return _replay(result)
